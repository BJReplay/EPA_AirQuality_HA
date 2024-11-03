"""Support for EPA (Victoria) Air Quality Sensors."""

# pylint: disable=C0301, C0304, E0401, W0718, C0301

from __future__ import annotations

from typing import Optional

from datetime import datetime as dt
from datetime import timedelta

import logging
import traceback
from enum import Enum

from homeassistant.components.sensor import ( # type: ignore
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry # type: ignore
from homeassistant.const import ( # type: ignore
    ATTR_CONFIGURATION_URL,
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    ATTR_SW_VERSION,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
)

from homeassistant.helpers.device_registry import DeviceEntryType # type: ignore
from homeassistant.helpers.update_coordinator import CoordinatorEntity # type: ignore


from .const import (
    ATTR_ENTRY_TYPE,
    ATTRIBUTION,
    DOMAIN,
    MANUFACTURER,
    TYPE_AQI_PM25,
    TYPE_AQI_PM25_24H,
    TYPE_PM25,
    TYPE_PM25_24H,
)

_LOGGER = logging.getLogger(__name__)

SENSORS: dict[str, SensorEntityDescription] = {
    TYPE_AQI_PM25: SensorEntityDescription(
        key=TYPE_AQI_PM25,
        translation_key="pm25_aqi",
        device_class=SensorDeviceClass.AQI,
        name="Hourly Health Advice",
        icon="mdi:information-outline",
        state_class=None,
    ),
    TYPE_AQI_PM25_24H: SensorEntityDescription(
        key=TYPE_AQI_PM25_24H,
        translation_key="pm25_aqi_24h_average",
        device_class=SensorDeviceClass.AQI,
        name="Daily Health Advice",
        icon="mdi:information-outline",
        state_class=None,
    ),
    TYPE_PM25: SensorEntityDescription(
        key=TYPE_PM25,
        translation_key="pm25",
        name="Hourly PM2.5",
        icon="mdi:chemical-weapon",
        device_class=SensorDeviceClass.PM25,
        suggested_display_precision=1,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    TYPE_PM25_24H: SensorEntityDescription(
        key=TYPE_PM25_24H,
        translation_key="pm25_24h_average",
        device_class=SensorDeviceClass.PM25,
        name="Daily Average PM2.5",
        icon="mdi:chemical-weapon",
        suggested_display_precision=1,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
}

SCAN_INTERVAL = timedelta(minutes=30)

class SensorUpdatePolicy(Enum):
    """Sensor update policy"""
    DEFAULT = 0
    EVERY_TIME_INTERVAL = 1

def get_sensor_update_policy() -> SensorUpdatePolicy:
    """Get the sensor update policy.

    Many sensors update every five minutes (EVERY_TIME_INTERVAL), while others only update on startup or forecast fetch.

    Arguments:
        key (str): The sensor name.

    Returns:
        SensorUpdatePolicy: The update policy.
    """
    return SensorUpdatePolicy.EVERY_TIME_INTERVAL

class EPAQualitySensor(CoordinatorEntity, SensorEntity):
    """Representation of a EPA Air Quality sensor device."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator,
            entity_description: SensorEntityDescription,
            entry: ConfigEntry
    ):
        super().__init__(coordinator)

        self.entity_description = entity_description
        self._coordinator = coordinator
        self._update_policy = get_sensor_update_policy()
        self._attr_unique_id = f"{entity_description.key}"
        self._attributes = {}
        self._attr_extra_state_attributes = {}

        try:
            self._sensor_data = self._coordinator.get_sensor_value(entity_description.key)
        except Exception as e:
            _LOGGER.error("Unable to get sensor value: %s: %s", e, traceback.format_exc())
            self._sensor_data = None

        if self._sensor_data is None:
            self._attr_available = False
        else:
            self._attr_available = True

        self._attr_device_info = {
            ATTR_IDENTIFIERS: {(DOMAIN, entry.entry_id)},
            ATTR_NAME: "EPA Air Quality", #entry.title,
            ATTR_MANUFACTURER: MANUFACTURER,
            ATTR_MODEL: "EPA Air Quality",
            ATTR_ENTRY_TYPE: DeviceEntryType.SERVICE,
            ATTR_SW_VERSION: coordinator._version,
            ATTR_CONFIGURATION_URL: "https://portal.api.epa.vic.gov.au/",
        }

        self._unique_id = f"epa_api_{entity_description.name}"

    @property
    def name(self):
        """Return the name of the device.

        Returns:
            str: The device name.
        """
        return f"{self.entity_description.name}"

    @property
    def friendly_name(self):
        """Return the friendly name of the device.

        Returns:
            str: The device friendly name, which is the same as device name.
        """
        return self.entity_description.name

    @property
    def unique_id(self):
        """Return the unique ID of the sensor.

        Returns:
            str: Unique ID.
        """
        return f"epavic_{self._unique_id}"

    @property
    def native_value(self) -> Optional[int | dt | float | str | bool]:
        """Return the current value of the sensor.

        Returns:
            int | dt | float | str | bool | None: The current value of a sensor.
        """
        return self._sensor_data

    @property
    def should_poll(self) -> bool:
        """Return whether the sensor should poll.

        Returns:
            bool: Always returns False, as sensors are not polled.
        """
        return False

    async def async_added_to_hass(self):
        """Called when an entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(self._coordinator.async_add_listener(self._handle_coordinator_update))