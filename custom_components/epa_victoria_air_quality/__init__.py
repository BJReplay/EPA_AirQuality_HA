"""Support for EPA Air Quality, initialisation."""

from dataclasses import dataclass
import logging
from typing import Any

from aiohttp.client_exceptions import ClientConnectorError

from homeassistant import loader
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .collector import Collector
from .const import CONF_SITE_ID, DOMAIN
from .coordinator import EPADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type EPAConfigEntry = ConfigEntry[EPAData]

# async def async_setup(hass: HomeAssistant, config: dict):
#     """Set up the EPA component."""
#     hass.data.setdefault(DOMAIN, {})
#     return True


async def async_migrate_entry(hass: HomeAssistant, entry: EPAConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", entry.version)

    if entry.version == 0:
        new = {**entry.data}
        if CONF_SITE_ID in new:
            new[CONF_SITE_ID] = entry.data[CONF_SITE_ID]

        entry.version = 1
        hass.config_entries.async_update_entry(entry, data=new)

    _LOGGER.info("Migration to version %s successful", entry.version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EPAConfigEntry) -> bool:
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

    version = await get_version(hass)
    ua_version = get_ua_version(version)

    options = entry.options
    collector: Collector = Collector(
        api_key=options.get(CONF_API_KEY),
        version_string=ua_version,
        epa_site_id=options.get(CONF_SITE_ID),
        latitude=options.get(CONF_LATITUDE),
        longitude=options.get(CONF_LONGITUDE),
    )
    coordinator: EPADataUpdateCoordinator = EPADataUpdateCoordinator(
        hass=hass, collector=collector, version=ua_version
    )

    entry.runtime_data = EPAData(coordinator, entry)

    _LOGGER.debug("Successful init")

    opt = {**entry.options}
    hass.config_entries.async_update_entry(entry, options=opt)

    try:
        await collector.async_update()
    except ClientConnectorError as ex:
        raise ConfigEntryNotReady from ex
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    # update_listener = entry.add_update_listener(async_update_options)
    # hass.data[DOMAIN][entry.entry_id][UPDATE_LISTENER] = update_listener

    return True


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
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


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


@dataclass
class EPAData:
    """EPA options for the integration."""

    coordinator: EPADataUpdateCoordinator
    other_data: dict[str, Any]
