"""Support for EPA Air Quality, initialisation."""

import logging

from aiohttp.client_exceptions import ClientConnectorError

from homeassistant import loader
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .collector import Collector
from .config_flow import ConnectionOptions
from .const import (
    COLLECTOR,
    CONF_SITE_ID,
    COORDINATOR,
    DOMAIN,
    INIT_MSG,
    SERVICE_UPDATE,
    UPDATE_LISTENER,
)
from .coordinator import EPADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the EPA component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    if config_entry.version == 0:
        new = {**config_entry.data}
        if CONF_SITE_ID in new:
            new[CONF_SITE_ID] = config_entry.data[CONF_SITE_ID]

        config_entry.version = 1
        hass.config_entries.async_update_entry(config_entry, data=new)

    _LOGGER.info("Migration to version %s successful", config_entry.version)
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

    tz = await get_tz(hass)
    _LOGGER.debug("tz: %s", tz)

    version = await get_version(hass)
    _LOGGER.debug("version: %s", version)

    ua_version = get_ua_version(version)
    _LOGGER.debug("ua_version: %s", ua_version)

    options = ConnectionOptions(
        entry.options[CONF_API_KEY],
        entry.options.get(CONF_SITE_ID, ""),
        entry.options.get(CONF_LATITUDE, 0),
        entry.options.get(CONF_LONGITUDE, 0),
        ua_version,
    )
    _LOGGER.debug(options)

    if not hass.data.get(DOMAIN):
        hass.data[DOMAIN] = {}

    if hass.data[DOMAIN].get("has_loaded", False):
        init_msg = ""  # if the integration has already successfully loaded previously then do not display the full version nag on reload.
    else:
        init_msg = INIT_MSG

    _LOGGER.debug("Successful init")

    _LOGGER.info(
        "%sepa integration version: %s%s%s",
        ("\n" + "-" * 67 + "\n") if init_msg != "" else "",
        version,
        ("\n\n" + init_msg) if init_msg != "" else "",
        ("\n" + "-" * 67) if init_msg != "" else "",
    )

    opt = {**entry.options}
    hass.config_entries.async_update_entry(entry, options=opt)
    hass.data[DOMAIN]["entry_options"] = entry.options

    collector = Collector(
        api_key=options.api_key,
        version_string=options.ua_version,
        epa_site_id=options.site_id,
        latitude=options.latitude,
        longitude=options.longitude,
    )

    try:
        await collector.async_update()
    except ClientConnectorError as ex:
        raise ConfigEntryNotReady from ex
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    coordinator = EPADataUpdateCoordinator(
        hass=hass, collector=collector, version=version
    )
    await coordinator.async_refresh()

    hass_data = hass.data.setdefault(DOMAIN, {})
    hass_data[entry.entry_id] = {
        COLLECTOR: collector,
        COORDINATOR: coordinator,
    }

    # entry.async_on_unload(entry.add_update_listener(async_update_options))
    # await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    update_listener = entry.add_update_listener(async_update_options)
    hass.data[DOMAIN][entry.entry_id][UPDATE_LISTENER] = update_listener

    hass.data[DOMAIN]["has_loaded"] = True

    return True


async def get_tz(hass: HomeAssistant) -> str:
    """Return tz using async_get_time_zone() as mandated in HA core 2024.6.0.

    Args:
        hass (HomeAssistant): hass reference

    Returns:
        str: Time Zone

    """

    tz = ""
    try:
        tz = await dt_util.async_get_time_zone(hass.config.time_zone)
    except:
        tz = dt_util.get_time_zone(hass.config.time_zone)
    return tz


async def get_version(hass: HomeAssistant) -> str:
    """Get trimmed version string for use in User Agent String.

    Args:
        hass (HomeAssistant): hass Reference

    Returns:
        str: Trimmed Version String

    """
    try:
        version = ""
        integration = await loader.async_get_integration(hass, DOMAIN)
        version = str(integration.version)
    except loader.IntegrationNotFound:
        pass

    return version


def get_ua_version(version: str) -> str:
    """Get trimmed version string for use in User Agent String.

    Args:
        version (str): version string

    Returns:
        str: Trimmed Version String

    """

    raw_version = version.replace("v", "")

    return raw_version[: raw_version.rfind(".")]


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


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device
) -> bool:
    """Remove a device.

    Arguments:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): Not used.
        device: The device instance.

    Returns:
        bool: Whether the removal completed successfully.

    """
    dr(hass).async_remove_device(device.id)
    return True
