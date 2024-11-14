"""The EPA VIC Air Quality coordinator."""

import datetime
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import debounce, device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .collector import Collector
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class EPADataUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for EPA Air Quality API."""

    def __init__(self, hass: HomeAssistant, collector: Collector, version: str) -> None:
        """Initialise the data update coordinator."""
        self.collector = collector
        self._version: str = version
        self._hass: HomeAssistant = hass

        DEFAULT_SCAN_INTERVAL = datetime.timedelta(
            minutes=SCAN_INTERVAL
        )  # EPA Updates roughly once every 30 minutes
        DEBOUNCE_TIME = 60  # in seconds

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_method=self.collector.async_update,
            update_interval=DEFAULT_SCAN_INTERVAL,
            request_refresh_debouncer=debounce.Debouncer(
                hass, _LOGGER, cooldown=DEBOUNCE_TIME, immediate=True
            ),
        )

        self.entity_registry_updated_unsub = self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self.entity_registry_updated
        )

    @callback
    def entity_registry_updated(self, event):
        """Handle entity registry update events."""
        if event.data["action"] == "remove":
            self.remove_empty_devices()

    def remove_empty_devices(self):
        """Remove devices with no entities."""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        device_list = dr.async_entries_for_config_entry(
            device_registry, self.config_entry.entry_id
        )

        for device_entry in device_list:
            entities = er.async_entries_for_device(
                entity_registry, device_entry.id, include_disabled_entities=True
            )

            if not entities:
                _LOGGER.debug("Removing orphaned device: %s", device_entry.name)
                device_registry.async_update_device(
                    device_entry.id, remove_config_entry_id=self.config_entry.entry_id
                )

    async def setup(self) -> bool:
        """Set up EPADataUpdateCoordinator."""
        _LOGGER.debug("setup called for EPADataUpdateCoordinator")
        return True

    @property
    def get_version(self) -> str:
        """Return Version.

        Returns:
            str: Integration Version

        """
        return self._version
