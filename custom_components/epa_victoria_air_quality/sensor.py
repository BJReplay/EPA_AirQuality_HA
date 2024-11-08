"""Support for EPA (Victoria) Air Quality Sensors."""

from __future__ import annotations

from datetime import datetime as dt, timedelta
from enum import Enum
import logging
import traceback

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_CONFIGURATION_URL,
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    ATTR_SW_VERSION,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EPAConfigEntry
from .collector import Collector
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
from .coordinator import EPADataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SENSORS: dict[str, SensorEntityDescription] = {
    TYPE_AQI_PM25: SensorEntityDescription(
        key=TYPE_AQI_PM25,
        translation_key="pm25_aqi",
        name="Hourly Health Advice",
        icon="mdi:information-outline",
        native_unit_of_measurement=None,
        state_class=None,
        suggested_display_precision=None,
        suggested_unit_of_measurement=None,
    ),
    TYPE_AQI_PM25_24H: SensorEntityDescription(
        key=TYPE_AQI_PM25_24H,
        translation_key="pm25_aqi_24h_average",
        name="Daily Health Advice",
        icon="mdi:information-outline",
        native_unit_of_measurement=None,
        state_class=None,
        suggested_display_precision=None,
        suggested_unit_of_measurement=None,
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

SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EPAConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed entry in HA.

    Arguments:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The integration entry instance, contains the configuration.
        async_add_entities (AddEntitiesCallback): The Home Assistant callback to add entities.

    """
    data = entry.runtime_data
    coordinator: EPADataUpdateCoordinator = data.coordinator
    entities = []

    for sensor_types in SENSORS:
        sen = EPAQualitySensor(coordinator, SENSORS[sensor_types], entry)
        entities.append(sen)

    async_add_entities(entities, update_before_add=False)


class SensorUpdatePolicy(Enum):
    """Sensor update policy."""

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


class EPAQualitySensor(CoordinatorEntity[EPADataUpdateCoordinator], SensorEntity):
    """Representation of a EPA Air Quality sensor device."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EPADataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        entry: EPAConfigEntry,
    ) -> None:
        """Initialse Sensor."""

        data = entry.runtime_data
        coordinator: EPADataUpdateCoordinator = data.coordinator
        collector: Collector = coordinator.collector
        sensor_name = entity_description.key
        super().__init__(coordinator)

        self.entity_description = entity_description
        self.sensor_name = sensor_name
        self._coordinator = coordinator
        self._collector: Collector = collector
        self._update_policy = get_sensor_update_policy()
        self._attr_unique_id = f"{entity_description.key}"
        self._attributes = {}
        self._attr_extra_state_attributes = {}

        try:
            self._sensor_data = self._collector.get_sensor(entity_description.key)
        except Exception as e:
            _LOGGER.error(
                "Unable to get sensor %s value. Exception: %s",
                entity_description.key,
                e,
            )
            self._sensor_data = None

        if self._sensor_data is None:
            self._attr_available = False
        else:
            self._attr_available = True

        self._attr_device_info = {
            ATTR_IDENTIFIERS: {(DOMAIN, entry.entry_id)},
            ATTR_NAME: "EPA Air Quality",  # entry.title,
            ATTR_MANUFACTURER: MANUFACTURER,
            ATTR_MODEL: "EPA Air Quality",
            ATTR_ENTRY_TYPE: DeviceEntryType.SERVICE,
            ATTR_SW_VERSION: self._coordinator.get_version,
            ATTR_CONFIGURATION_URL: "https://portal.api.epa.vic.gov.au/",
        }

        self._unique_id = f"epa_api_{entity_description.name}"

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator.

        Some sensors are updated periodically every five minutes (those with an update policy of
        SensorUpdatePolicy.EVERY_TIME_INTERVAL), while the remaining sensors update after each
        forecast update or when the date changes.
        """

        try:
            self._sensor_data = self._collector.get_sensor(self.entity_description.key)
        except Exception as e:
            _LOGGER.error(
                "Unable to get sensor value: %s: %s", e, traceback.format_exc()
            )
            self._sensor_data = None

        if self._sensor_data is None:
            self._attr_available = False
        else:
            self._attr_available = True

        self.async_write_ha_state()

    async def async_update(self):
        """Refresh the data on the collector object."""
        await self._collector.async_update()

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
    def native_value(self) -> int | dt | float | str | bool | None:
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

    # @property
    # def state(self):
    #     """Return the state of the sensor."""
    #     match self.sensor_name:
    #         case "pm25":
    #             return self._collector.get_pm25
    #         case "pm25_24h":
    #             return self._collector.get_pm25_24h
    #         case "aqi_pm25":
    #             return self._collector.get_aqi_pm25
    #         case "aqi_pm25_24h":
    #             return self._collector.get_aqi_pm25_24h
    #         case "until":
    #             return self._collector.get_until
    #         case _:
    #             return self._collector.get_sensor(self.sensor_name)

    async def async_added_to_hass(self):
        """Call when an entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )
