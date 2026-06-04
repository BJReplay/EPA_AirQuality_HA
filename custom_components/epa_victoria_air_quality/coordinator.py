"""The EPA VIC Air Quality coordinator."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import debounce, device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .collector import Collector
from .const import CONF_LEGACY_UNIQUE_IDS, CONF_SITE_ID, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass
class EPAData:
    """EPA options for the integration."""

    coordinator: EPADataUpdateCoordinator
    other_data: EPAConfigEntry


type EPAConfigEntry = ConfigEntry[EPAData]


class EPADataUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for EPA Air Quality API."""

    def __init__(self, hass: HomeAssistant, collector: Collector, version: str, config_entry: EPAConfigEntry) -> None:
        """Initialise the data update coordinator."""
        self.collector = collector
        self._version: str = version
        self._hass: HomeAssistant = hass
        self.config_entry = config_entry

        DEBOUNCE_TIME = 60  # in seconds

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_method=self.collector.async_update,
            setup_method=self.collector.async_setup,
            update_interval=SCAN_INTERVAL,  # EPA Updates roughly once every 30 minutes, so default 15 is reasonably aggressive.
            request_refresh_debouncer=debounce.Debouncer(hass, _LOGGER, cooldown=DEBOUNCE_TIME, immediate=True),
            config_entry=config_entry,
        )

        self.entity_registry_updated_unsub = self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self.entity_registry_updated)

    @callback
    def entity_registry_updated(self, event):
        """Handle entity registry update events."""
        action = event.data.get("action")
        if action == "remove":
            self.remove_empty_devices()
            return
        if action in ("create", "update"):
            # Startup order is: initial API refresh, then entity creation.  Trigger
            # auto-enable here so default-disabled entities are enabled immediately
            # on first startup of a new location instead of waiting for next poll.
            self._auto_enable_available_sensors()

    @staticmethod
    def expand_to_counterpart_keys(available_keys: list[str], sensor_keys: set[str]) -> set[str]:
        """Expand available keys to include corresponding hourly/daily pairs."""
        expanded_keys: set[str] = set()

        for key in available_keys:
            if key not in sensor_keys:
                continue

            expanded_keys.add(key)
            counterpart = key[:-4] if key.endswith("_24h") else f"{key}_24h"
            if counterpart in sensor_keys:
                expanded_keys.add(counterpart)

        return expanded_keys

    def remove_empty_devices(self):
        """Remove devices with no entities."""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        device_list = dr.async_entries_for_config_entry(device_registry, self.config_entry.entry_id)  # pyright: ignore[reportOptionalMemberAccess]

        for device_entry in device_list:
            entities = er.async_entries_for_device(entity_registry, device_entry.id, include_disabled_entities=True)

            if not entities:
                _LOGGER.debug("Removing orphaned device: %s", device_entry.name)
                device_registry.async_update_device(device_entry.id, remove_config_entry_id=self.config_entry.entry_id)  # pyright: ignore[reportOptionalMemberAccess]

    async def setup(self) -> bool:
        """Set up EPADataUpdateCoordinator."""
        _LOGGER.debug("setup called for EPADataUpdateCoordinator")
        return True

    @callback
    def _auto_enable_available_sensors(self) -> None:
        """Enable integration-disabled entities once EPA reports values for them."""
        if self.config_entry is None:
            return

        available_keys = self.collector.get_available_sensor_keys()
        if not available_keys:
            return

        from .sensor import (  # noqa: PLC0415
            SENSORS,  # Deferred import to prevent module-level circular import.
        )

        site_id = self.config_entry.options.get(CONF_SITE_ID, self.config_entry.entry_id)
        use_legacy_unique_ids = self.config_entry.options.get(CONF_LEGACY_UNIQUE_IDS, False)
        expanded_keys = self.expand_to_counterpart_keys(available_keys, set(SENSORS))
        available_unique_ids = {
            (f"epavic_epa_api_{SENSORS[key].name}" if use_legacy_unique_ids else f"epavic_epa_api_{site_id}_{SENSORS[key].name}")
            for key in expanded_keys
        }
        if not available_unique_ids:
            return

        entity_registry = er.async_get(self.hass)
        for entity_entry in er.async_entries_for_config_entry(entity_registry, self.config_entry.entry_id):
            if entity_entry.unique_id not in available_unique_ids:
                continue
            if entity_entry.disabled_by is not er.RegistryEntryDisabler.INTEGRATION:
                continue

            entity_registry.async_update_entity(entity_entry.entity_id, disabled_by=None)
            _LOGGER.debug("Enabled %s after EPA started reporting data", entity_entry.entity_id)

    async def _async_update_data(self) -> Any:
        """Update collector data and auto-enable newly available sensors."""
        await self.collector.async_update()
        self._auto_enable_available_sensors()
        return None

    @property
    def get_version(self) -> str:
        """Return Version.

        Returns:
            str: Integration Version

        """
        return self._version
