"""Support for EPA Air Quality, intialisation."""

# pylint: disable=C0301, C0304, C0321, E0401, E1135, W0613, W0702, W0718

import logging
import traceback
from datetime import timedelta
import asyncio

from homeassistant import loader # type: ignore
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.const import CONF_API_KEY, Platform # type: ignore
from homeassistant.core import HomeAssistant, ServiceCall  # type: ignore
from homeassistant.exceptions import ConfigEntryNotReady # type: ignore
from homeassistant.helpers import aiohttp_client # type: ignore
from homeassistant.helpers.device_registry import async_get as device_registry # type: ignore
from homeassistant.util import dt as dt_util # type: ignore

from .const import (
    CONF_SITE_ID,
    DOMAIN,
    EPA_URL,
    INIT_MSG,
    SERVICE_UPDATE,
)

from .epaapi import ConnectionOptions, EPAApi
from .coordinator import EPAVicUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SELECT,]

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
        ConfigEntryNotReady: Instructs Home Assistant that the integration is not yet ready when a load failure occurrs.

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

    options = ConnectionOptions(
        entry.options[CONF_API_KEY],
        entry.options[CONF_SITE_ID],
        EPA_URL,
        tz,
    )

    epa = EPAApi(aiohttp_client.async_get_clientsession(hass), options)

    epa.entry = entry
    epa.entry_options = {**entry.options}
    epa.hass = hass

    if not hass.data.get(DOMAIN):
        hass.data[DOMAIN] = {}

    if hass.data[DOMAIN].get('has_loaded', False):
        init_msg = '' # if the integration has already successfully loaded previously then do not display the full version nag on reload.
        epa.previously_loaded = True
    else:
        init_msg = INIT_MSG

    try:
        version = ''
        integration = await loader.async_get_integration(hass, DOMAIN)
        version = str(integration.version)
    except loader.IntegrationNotFound:
        pass

    raw_version = version.replace('v','')
    epa.headers = {
        'Accept': 'application/json',
        'User-Agent': 'ha-epa-integration/'+raw_version[:raw_version.rfind('.')],
        'X-API-Key': options.api_key
    }
    _LOGGER.debug("Session headers: %s", epa.headers)

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


    coordinator = EPAVicUpdateCoordinator(hass, epa, version)
    if not await coordinator.setup():
        raise ConfigEntryNotReady('Internal error: Coordinator setup failed')
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    hass.data[DOMAIN]['has_loaded'] = True

    async def action_call_update_air_quality(call: ServiceCall):
        """Handle action.

        Arguments:
            call (ServiceCall): Not used.
        """
        _LOGGER.info("Action: Fetching air quality")
        await coordinator.service_event_update()

    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE, action_call_update_air_quality
    )

    return True

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
        entry (ConfigEntry): Not ussed.
        device: The device instance.

    Returns:
        bool: Whether the removal completed successfully.
    """
    device_registry(hass).async_remove_device(device.id)
    return True

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Reconfigure the integration when options get updated.

    * Changing API key or Site ID results in a restart.

    Arguments:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The integration entry instance, contains the configuration.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]

    def tasks_cancel():
        try:
            # Terminate epaapi tasks in progress
            for task, cancel in coordinator.epa.tasks.items():
                _LOGGER.debug("Cancelling EPAAPI task %s", task)
                cancel.cancel()
            # Terminate coordinator tasks in progress
            for task, cancel in coordinator.tasks.items():
                _LOGGER.debug("Cancelling coordinator task %s", task)
                if isinstance(cancel, asyncio.Task):
                    cancel.cancel()
                else:
                    cancel()
            coordinator.tasks = {}
        except Exception as e:
            _LOGGER.error("Cancelling tasks failed: %s: %s", e, traceback.format_exc())
        coordinator.epa.tasks = {}

    try:
        reload = False

        def changed(config):
            return hass.data[DOMAIN]['entry_options'].get(config) != entry.options.get(config)

        # Config changes, which when changed will cause a reload.
        if changed(CONF_API_KEY):
            hass.data[DOMAIN]['old_api_key'] = hass.data[DOMAIN]['entry_options'].get(CONF_API_KEY)
        if changed(CONF_SITE_ID):
            hass.data[DOMAIN]['old_site_id'] = hass.data[DOMAIN]['entry_options'].get(CONF_SITE_ID)
        reload = changed(CONF_API_KEY) or changed(CONF_SITE_ID)

        if reload:
            determination = 'The integration will reload'
        else:
            determination = 'Refresh sensors only'
        _LOGGER.debug("Options updated, action: %s", determination)
        if not reload:
            await coordinator.epa.set_options(entry.options)
            await coordinator.epa.get_quality_update()
            coordinator.set_data_updated(True)
            await coordinator.update_integration_listeners()
            coordinator.set_data_updated(False)

            hass.data[DOMAIN]['entry_options'] = entry.options
            coordinator.epa.entry_options = entry.options
        else:
            # Reload
            tasks_cancel()
            await hass.config_entries.async_reload(entry.entry_id)
    except:
        _LOGGER.debug(traceback.format_exc())
        # Restart on exception
        tasks_cancel()
        await hass.config_entries.async_reload(entry.entry_id)