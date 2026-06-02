"""Support for EPA Air Quality, initialisation."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from aiohttp.client_exceptions import ClientConnectorError

from homeassistant import loader
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .collector import Collector
from .const import (
    CONF_AQI_SOURCE,
    CONF_LEGACY_UNIQUE_IDS,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    DEFAULT_AQI_SOURCE,
    DOMAIN,
    TITLE,
)
from .coordinator import EPADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

type EPAConfigEntry = ConfigEntry[EPAData]


async def async_migrate_entry(hass: HomeAssistant, entry: EPAConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", entry.version)

    update_kwargs: dict = {}

    if entry.version < 3:
        # All versions below 3 are migrated.
        # Changes in v3 are:
        #   - CONF_SITE_ID / CONF_API_KEY moved from entry.data to entry.options
        #   - Entry title includes the human-readable location name
        site_id = entry.options.get(CONF_SITE_ID) or entry.data.get(CONF_SITE_ID, "")
        update_kwargs["version"] = 3

        if site_id:
            # Migrate CONF_SITE_ID (and CONF_API_KEY) from data to options if absent.
            new_options = dict(entry.options)
            if not new_options.get(CONF_SITE_ID):
                new_options[CONF_SITE_ID] = site_id
                api_key = entry.data.get(CONF_API_KEY, "")
                if api_key and not new_options.get(CONF_API_KEY):
                    new_options[CONF_API_KEY] = api_key
            # Mark this entry as using legacy unique IDs so sensor.py preserves
            # the upstream format (epavic_epa_api_{name}) and avoids breaking
            # existing entity registry entries for single-site installs.
            new_options[CONF_LEGACY_UNIQUE_IDS] = True
            update_kwargs["options"] = new_options

            # Fix the entry title if it never got a location suffix.
            if entry.title == TITLE:
                location_name = new_options.get(CONF_SITE_NAME) or site_id
                update_kwargs["title"] = f"{TITLE} - {location_name}"

            # Set unique_id if missing.
            if entry.unique_id is None:
                update_kwargs["unique_id"] = site_id

    if entry.version < 4:
        new_options = dict(update_kwargs.get("options", entry.options))
        new_options.setdefault(CONF_AQI_SOURCE, DEFAULT_AQI_SOURCE)
        update_kwargs["options"] = new_options
        update_kwargs["version"] = 4

    if update_kwargs:
        hass.config_entries.async_update_entry(entry, **update_kwargs)

    _LOGGER.info("Migration to version %s successful", entry.version)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EPAConfigEntry) -> bool:
    """Set up the integration.

    * Get and sanitise options.
    * Instantiate the main class.
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
        api_key=options.get(CONF_API_KEY, ""),
        version_string=ua_version,
        epa_site_id=options.get(CONF_SITE_ID, ""),
        latitude=options.get(CONF_LATITUDE, 0),
        longitude=options.get(CONF_LONGITUDE, 0),
        session=async_get_clientsession(hass),
        aqi_source=options.get(CONF_AQI_SOURCE, DEFAULT_AQI_SOURCE),
    )
    collector.site_name = options.get(CONF_SITE_NAME, "")
    coordinator: EPADataUpdateCoordinator = EPADataUpdateCoordinator(hass=hass, collector=collector, version=ua_version)

    entry.runtime_data = EPAData(coordinator, entry)

    _LOGGER.debug("Successful init")

    opt = {**entry.options}
    hass.config_entries.async_update_entry(entry, options=opt)

    try:
        _LOGGER.debug("Running initial EPA refresh for %s", entry.title)
        await collector.async_update(no_throttle=True)
        _LOGGER.debug("Initial EPA refresh complete for %s", entry.title)
    except ClientConnectorError as ex:
        raise ConfigEntryNotReady from ex

    # One-time lookup for migrated entries that pre-date CONF_SITE_NAME storage.
    # Fetches the locations list from the API to resolve the numeric site ID to a
    # human-readable name, then persists it so this call is never repeated.
    if not entry.options.get(CONF_SITE_NAME):
        site_id = entry.options.get(CONF_SITE_ID, "")
        if site_id:
            lookup_collector = Collector(
                api_key=entry.options.get(CONF_API_KEY, ""),
                version_string=ua_version,
                latitude=hass.config.latitude,
                longitude=hass.config.longitude,
            )
            await lookup_collector.async_setup()
            site_name = next(
                (str(loc.get("label", "")) for loc in lookup_collector.get_location_list() if loc.get("value") == site_id),
                "",
            )
            if site_name:
                new_title = f"{TITLE} - {site_name}"
                hass.config_entries.async_update_entry(
                    entry,
                    options={**entry.options, CONF_SITE_NAME: site_name},
                    title=new_title,
                )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    hass.data.setdefault(DOMAIN, {})

    entry.async_on_unload(entry.add_update_listener(async_update_options))

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


async def async_remove_config_entry_device(hass: HomeAssistant, entry: ConfigEntry, device: dr.DeviceEntry) -> bool:
    """Remove a device.

    Arguments:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): Not used.
        device: The device instance.

    Returns:
        bool: Whether the removal completed successfully.

    """
    device_registry = dr.async_get(hass)
    device_registry.async_remove_device(device.id)
    return True


@dataclass
class EPAData:
    """EPA options for the integration."""

    coordinator: EPADataUpdateCoordinator
    other_data: EPAConfigEntry
