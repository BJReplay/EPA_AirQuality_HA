"""Support for EPA Air Quality, initialisation."""

# pylint: disable=C0301, C0304, C0321, E0401, E1135, W0613, W0702, W0718

import logging
import traceback
import os
from datetime import timedelta
import datetime
import asyncio

from homeassistant import loader # type: ignore
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, Platform # type: ignore
from homeassistant.core import HomeAssistant, callback  # type: ignore
from homeassistant.exceptions import ConfigEntryNotReady # type: ignore
from homeassistant.helpers import aiohttp_client # type: ignore
from homeassistant.helpers.device_registry import async_get as device_registry # type: ignore
from homeassistant.util import dt as dt_util # type: ignore
from homeassistant.helpers import debounce # type: ignore
from homeassistant.helpers import device_registry as dr # type: ignore
from homeassistant.helpers import entity_registry as er # type: ignore
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator # type: ignore
from aiohttp.client_exceptions import ClientConnectorError # type: ignore

from .collector import ConnectionOptions, Collector

from .const import (
    CONF_SITE_ID,
    COLLECTOR,
    COORDINATOR,
    DOMAIN,
    INIT_MSG,
    SERVICE_UPDATE,
    URL_BASE
)


_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

DEFAULT_SCAN_INTERVAL = datetime.timedelta(minutes=5)
DEBOUNCE_TIME = 60  # in seconds

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the EPA component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration.

    * Get and sanitise options.
    * Instantiate the main class.
    * Load API usage.
    * Instantiate the coordinator.

    Arguments:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The integration entry instance, contains the configuration.

    Raises:
        ConfigEntryNotReady: Instructs Home Assistant that the integration is not yet ready when a load failure occurs.

    Returns:
        bool: Whether setup has completed successfully.
    """

    # async_get_time_zone() mandated in HA core 2024.6.0
    try:
        dt_util.async_get_time_zone # pylint: disable=W0104
        asynctz = True
    except:
        asynctz = False
    if asynctz:
        tz = await dt_util.async_get_time_zone(hass.config.time_zone)
    else:
        tz = dt_util.get_time_zone(hass.config.time_zone)

    headers = {}

    options = ConnectionOptions(
        entry.options[CONF_API_KEY],
        entry.options[CONF_SITE_ID],
        entry.options[URL_BASE],
        entry.options[CONF_LATITUDE],
        entry.options[CONF_LONGITUDE],
        tz,
        headers,
    )

    try:
        version = ''
        integration = await loader.async_get_integration(hass, DOMAIN)
        version = str(integration.version)
    except loader.IntegrationNotFound:
        pass

    raw_version = version.replace('v','')
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'ha-epa-integration/'+raw_version[:raw_version.rfind('.')],
        'X-API-Key': options.api_key
    }
    _LOGGER.debug("Session headers: %s", headers)

    options = ConnectionOptions(
        entry.options[CONF_API_KEY],
        entry.options[CONF_SITE_ID],
        entry.options[URL_BASE],
        entry.options[CONF_LATITUDE],
        entry.options[CONF_LONGITUDE],
        tz,
        headers,
    )

    if not hass.data.get(DOMAIN):
        hass.data[DOMAIN] = {}

    if hass.data[DOMAIN].get('has_loaded', False):
        init_msg = '' # if the integration has already successfully loaded previously then do not display the full version nag on reload.
    else:
        init_msg = INIT_MSG


    _LOGGER.debug("Successful init")

    _LOGGER.info(
        "%sepa integration version: %s%s%s",
        ('\n' + '-'*67 + '\n') if init_msg != '' else '',
        version,
        ('\n\n' + init_msg) if init_msg != '' else '',('\n' + '-'*67) if init_msg != '' else '',
    )

    opt = {**entry.options}
    hass.config_entries.async_update_entry(entry, options=opt)
    hass.data[DOMAIN]['entry_options'] = entry.options

    collector = Collector(options.latitude, options.longitude, options.api_key)

    try:
        await collector.async_update()
    except ClientConnectorError as ex:
        raise ConfigEntryNotReady from ex
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    coordinator = EPADataUpdateCoordinator(hass=hass, collector=collector)
    await coordinator.async_refresh()

    hass_data = hass.data.setdefault(DOMAIN, {})
    hass_data[entry.entry_id] = {
        COLLECTOR: collector,
        COORDINATOR: coordinator,
    }

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    hass.data[DOMAIN]['has_loaded'] = True

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Handle config entry updates."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    This also removes the services available.

    Arguments:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The integration entry instance, contains the configuration.

    Returns:
        bool: Whether the unload completed successfully.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    hass.services.async_remove(DOMAIN, SERVICE_UPDATE)

    return unload_ok

async def async_remove_config_entry_device(hass: HomeAssistant, entry: ConfigEntry, device) -> bool:
    """Remove a device.

    Arguments:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): Not used.
        device: The device instance.

    Returns:
        bool: Whether the removal completed successfully.
    """
    device_registry(hass).async_remove_device(device.id)
    return True

class EPADataUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for Bureau of Meteorology."""

    def __init__(self, hass: HomeAssistant, collector: Collector) -> None:
        """Initialise the data update coordinator."""
        self.collector = collector
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
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        device_list = dr.async_entries_for_config_entry(
            dev_reg, self.config_entry.entry_id
        )

        for device_entry in device_list:
            entities = er.async_entries_for_device(
                ent_reg, device_entry.id, include_disabled_entities=True
            )

            if not entities:
                _LOGGER.debug("Removing orphaned device: %s", device_entry.name)
                dev_reg.async_update_device(
                    device_entry.id, remove_config_entry_id=self.config_entry.entry_id
                )