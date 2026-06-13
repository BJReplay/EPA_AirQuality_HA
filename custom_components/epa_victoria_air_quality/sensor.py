"""Support for EPA (Victoria) Air Quality Sensors."""

from datetime import datetime as dt
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
    CONCENTRATION_PARTS_PER_BILLION,
    CONCENTRATION_PARTS_PER_MILLION,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EPAConfigEntry
from .collector import Collector
from .const import (
    AQI_SOURCE_OVERALL,
    ATTR_ENTRY_TYPE,
    ATTRIBUTION,
    CONF_AQI_SOURCE,
    CONF_LEGACY_UNIQUE_IDS,
    CONF_SITE_ID,
    DOMAIN,
    MANUFACTURER,
    TYPE_AQI,
    TYPE_AQI_24H,
    TYPE_AQI_OVERALL,
    TYPE_AQI_OVERALL_24H,
    TYPE_AQI_PM25,
    TYPE_AQI_PM25_24H,
    TYPE_CO,
    TYPE_CO_24H,
    TYPE_CO_ADVICE,
    TYPE_CO_ADVICE_24H,
    TYPE_NO2,
    TYPE_NO2_24H,
    TYPE_NO2_ADVICE,
    TYPE_NO2_ADVICE_24H,
    TYPE_NO2_AQI_VALUE,
    TYPE_O3,
    TYPE_O3_24H,
    TYPE_O3_ADVICE,
    TYPE_O3_ADVICE_24H,
    TYPE_O3_AQI_VALUE,
    TYPE_PM10,
    TYPE_PM10_24H,
    TYPE_PM10_ADVICE,
    TYPE_PM10_ADVICE_24H,
    TYPE_PM10_AQI_VALUE,
    TYPE_PM10_AQI_VALUE_24H,
    TYPE_PM25,
    TYPE_PM25_AQI_VALUE,
    TYPE_PM25_AQI_VALUE_24H,
    TYPE_SO2,
    TYPE_SO2_24H,
    TYPE_SO2_ADVICE,
    TYPE_SO2_ADVICE_24H,
    TYPE_SO2_AQI_VALUE,
    UNTIL,
)
from .coordinator import EPADataUpdateCoordinator

PARALLEL_UPDATES = 0

# When enabled, sensor entities always write state updates to Recorder, even if the value has not changed.
FORCE_UPDATE_SENSOR_HISTORY = False

_LOGGER = logging.getLogger(__name__)


def _is_daily_sensor(key: str) -> bool:
    """Return whether a sensor key represents a daily metric."""
    return key.endswith("_24h")


def _aqi_description(
    key: str,
    pollutant: str,
    *,
    entity_registry_enabled_default: bool = True,
) -> SensorEntityDescription:
    daily = _is_daily_sensor(key)
    return SensorEntityDescription(
        key=key,
        translation_key="daily_aqi_pollutant" if daily else "hourly_aqi_pollutant",
        translation_placeholders={"pollutant": pollutant},
        name=f"{'Daily' if daily else 'Hourly'} {pollutant} AQI",
        device_class=SensorDeviceClass.AQI,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=entity_registry_enabled_default,
    )


def _measurement_description(
    key: str,
    pollutant: str,
    *,
    device_class: SensorDeviceClass,
    native_unit_of_measurement: str,
    entity_registry_enabled_default: bool = True,
) -> SensorEntityDescription:
    daily = _is_daily_sensor(key)
    return SensorEntityDescription(
        key=key,
        translation_key="daily_measurement" if daily else "hourly_measurement",
        translation_placeholders={"pollutant": pollutant},
        name=f"{'Daily' if daily else 'Hourly'} {pollutant}",
        device_class=device_class,
        suggested_display_precision=1,
        native_unit_of_measurement=native_unit_of_measurement,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=entity_registry_enabled_default,
    )


def _health_advice_description(
    key: str,
    pollutant: str,
    *,
    entity_registry_enabled_default: bool = True,
) -> SensorEntityDescription:
    daily = _is_daily_sensor(key)
    return SensorEntityDescription(
        key=key,
        translation_key="daily_health_advice" if daily else "hourly_health_advice",
        translation_placeholders={"pollutant": pollutant},
        name=f"{'Daily' if daily else 'Hourly'} {pollutant} Health Advice",
        entity_registry_enabled_default=entity_registry_enabled_default,
    )


def _primary_aqi_description(key: str) -> SensorEntityDescription:
    """Build the primary AQI entity description."""
    daily = _is_daily_sensor(key)
    return SensorEntityDescription(
        key=key,
        translation_key="daily_primary_aqi" if daily else "hourly_primary_aqi",
        name="Daily AQI" if daily else "Hourly AQI",
        device_class=SensorDeviceClass.AQI,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
    )


def _primary_health_advice_description(key: str) -> SensorEntityDescription:
    """Build the primary health advice entity description."""
    daily = _is_daily_sensor(key)
    return SensorEntityDescription(
        key=key,
        translation_key=("daily_primary_health_advice" if daily else "hourly_primary_health_advice"),
        name="Daily Health Advice" if daily else "Hourly Health Advice",
    )


def _overall_aqi_description(
    key: str,
    *,
    entity_registry_enabled_default: bool = True,
) -> SensorEntityDescription:
    """Build the overall AQI entity description."""
    daily = _is_daily_sensor(key)
    return SensorEntityDescription(
        key=key,
        translation_key="daily_overall_aqi" if daily else "hourly_overall_aqi",
        name="Daily Overall AQI" if daily else "Hourly Overall AQI",
        device_class=SensorDeviceClass.AQI,
        suggested_display_precision=0,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=entity_registry_enabled_default,
    )


SENSORS: dict[str, SensorEntityDescription] = {
    TYPE_AQI_PM25: _primary_health_advice_description(TYPE_AQI_PM25),
    TYPE_AQI_PM25_24H: _primary_health_advice_description(TYPE_AQI_PM25_24H),
    TYPE_PM25: _measurement_description(
        TYPE_PM25,
        "PM2.5",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    ),
    TYPE_AQI: _primary_aqi_description(TYPE_AQI),
    TYPE_AQI_24H: _primary_aqi_description(TYPE_AQI_24H),
    TYPE_AQI_OVERALL: _overall_aqi_description(TYPE_AQI_OVERALL),
    TYPE_AQI_OVERALL_24H: _overall_aqi_description(TYPE_AQI_OVERALL_24H),
    TYPE_PM25_AQI_VALUE: _aqi_description(TYPE_PM25_AQI_VALUE, "PM2.5"),
    TYPE_PM25_AQI_VALUE_24H: _aqi_description(TYPE_PM25_AQI_VALUE_24H, "PM2.5"),
    TYPE_PM10: _measurement_description(
        TYPE_PM10,
        "PM10",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        entity_registry_enabled_default=False,
    ),
    TYPE_PM10_24H: _measurement_description(
        TYPE_PM10_24H,
        "PM10",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        entity_registry_enabled_default=False,
    ),
    TYPE_PM10_AQI_VALUE: _aqi_description(
        TYPE_PM10_AQI_VALUE,
        "PM10",
        entity_registry_enabled_default=False,
    ),
    TYPE_PM10_AQI_VALUE_24H: _aqi_description(
        TYPE_PM10_AQI_VALUE_24H,
        "PM10",
        entity_registry_enabled_default=False,
    ),
    TYPE_PM10_ADVICE: _health_advice_description(
        TYPE_PM10_ADVICE,
        "PM10",
        entity_registry_enabled_default=False,
    ),
    TYPE_PM10_ADVICE_24H: _health_advice_description(
        TYPE_PM10_ADVICE_24H,
        "PM10",
        entity_registry_enabled_default=False,
    ),
    TYPE_NO2: _measurement_description(
        TYPE_NO2,
        "NO2",
        device_class=SensorDeviceClass.NITROGEN_DIOXIDE,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_BILLION,
        entity_registry_enabled_default=False,
    ),
    TYPE_NO2_24H: _measurement_description(
        TYPE_NO2_24H,
        "NO2",
        device_class=SensorDeviceClass.NITROGEN_DIOXIDE,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_BILLION,
        entity_registry_enabled_default=False,
    ),
    TYPE_NO2_AQI_VALUE: _aqi_description(
        TYPE_NO2_AQI_VALUE,
        "NO2",
        entity_registry_enabled_default=False,
    ),
    TYPE_NO2_ADVICE: _health_advice_description(
        TYPE_NO2_ADVICE,
        "NO2",
        entity_registry_enabled_default=False,
    ),
    TYPE_NO2_ADVICE_24H: _health_advice_description(
        TYPE_NO2_ADVICE_24H,
        "NO2",
        entity_registry_enabled_default=False,
    ),
    TYPE_O3: _measurement_description(
        TYPE_O3,
        "O3",
        device_class=SensorDeviceClass.OZONE,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_BILLION,
        entity_registry_enabled_default=False,
    ),
    TYPE_O3_24H: _measurement_description(
        TYPE_O3_24H,
        "O3",
        device_class=SensorDeviceClass.OZONE,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_BILLION,
        entity_registry_enabled_default=False,
    ),
    TYPE_O3_AQI_VALUE: _aqi_description(
        TYPE_O3_AQI_VALUE,
        "O3",
        entity_registry_enabled_default=False,
    ),
    TYPE_O3_ADVICE: _health_advice_description(
        TYPE_O3_ADVICE,
        "O3",
        entity_registry_enabled_default=False,
    ),
    TYPE_O3_ADVICE_24H: _health_advice_description(
        TYPE_O3_ADVICE_24H,
        "O3",
        entity_registry_enabled_default=False,
    ),
    TYPE_SO2: _measurement_description(
        TYPE_SO2,
        "SO2",
        device_class=SensorDeviceClass.SULPHUR_DIOXIDE,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_BILLION,
        entity_registry_enabled_default=False,
    ),
    TYPE_SO2_24H: _measurement_description(
        TYPE_SO2_24H,
        "SO2",
        device_class=SensorDeviceClass.SULPHUR_DIOXIDE,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_BILLION,
        entity_registry_enabled_default=False,
    ),
    TYPE_SO2_AQI_VALUE: _aqi_description(
        TYPE_SO2_AQI_VALUE,
        "SO2",
        entity_registry_enabled_default=False,
    ),
    TYPE_SO2_ADVICE: _health_advice_description(
        TYPE_SO2_ADVICE,
        "SO2",
        entity_registry_enabled_default=False,
    ),
    TYPE_SO2_ADVICE_24H: _health_advice_description(
        TYPE_SO2_ADVICE_24H,
        "SO2",
        entity_registry_enabled_default=False,
    ),
    TYPE_CO: _measurement_description(
        TYPE_CO,
        "CO",
        device_class=SensorDeviceClass.CO,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        entity_registry_enabled_default=False,
    ),
    TYPE_CO_24H: _measurement_description(
        TYPE_CO_24H,
        "CO",
        device_class=SensorDeviceClass.CO,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        entity_registry_enabled_default=False,
    ),
    TYPE_CO_ADVICE: _health_advice_description(
        TYPE_CO_ADVICE,
        "CO",
        entity_registry_enabled_default=False,
    ),
    TYPE_CO_ADVICE_24H: _health_advice_description(
        TYPE_CO_ADVICE_24H,
        "CO",
        entity_registry_enabled_default=False,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EPAConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add sensors for passed entry in HA.

    Arguments:
        hass (HomeAssistant): The Home Assistant instance.
        entry (ConfigEntry): The integration entry instance, contains the configuration.
        async_add_entities (AddEntitiesCallback): The Home Assistant callback to add entities.

    """
    data = entry.runtime_data
    coordinator: EPADataUpdateCoordinator = data.coordinator
    entities = [EPAQualitySensor(coordinator, description, entry) for description in SENSORS.values()]

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
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: EPADataUpdateCoordinator,
        entity_description: SensorEntityDescription,
        entry: EPAConfigEntry,
    ) -> None:
        """Initialise Sensor."""

        collector: Collector = coordinator.collector
        sensor_name = entity_description.key
        super().__init__(coordinator)

        self.entity_description: SensorEntityDescription = entity_description
        self.sensor_name: str = sensor_name
        self._coordinator: EPADataUpdateCoordinator = coordinator
        self._collector: Collector = collector
        self._update_policy: SensorUpdatePolicy = get_sensor_update_policy()
        self._entry: EPAConfigEntry = entry
        self._attr_force_update = FORCE_UPDATE_SENSOR_HISTORY

        available_keys = self._collector.get_available_sensor_keys()
        if available_keys:
            expanded_keys = EPADataUpdateCoordinator.expand_to_counterpart_keys(available_keys, set(SENSORS))
            if sensor_name in expanded_keys:
                # When startup data proves existence, register as enabled.
                self._attr_entity_registry_enabled_default = True

        if entry.options.get(CONF_LEGACY_UNIQUE_IDS, False):
            # Preserve the upstream unique ID format for entries migrated from v1/v2
            # so existing entity registry entries are not orphaned.
            self._attr_unique_id = f"epavic_epa_api_{entity_description.name}"
        else:
            site_id = entry.options.get(CONF_SITE_ID, entry.entry_id)
            self._attr_unique_id = f"epavic_epa_api_{site_id}_{entity_description.name}"
        self._attributes: dict = {}
        self._attr_extra_state_attributes: dict = {}

        try:
            self._sensor_data = self._collector.get_sensor(entity_description.key)
        except KeyError as e:
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
            ATTR_NAME: entry.title,
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
        except KeyError as e:
            _LOGGER.error("Unable to get sensor value: %s: %s", e, traceback.format_exc())
            self._sensor_data = None

        if self._sensor_data is None:
            self._attr_available = False
        else:
            self._attr_available = True

        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Refresh the data on the collector object."""
        await self._collector.async_update()

    @property
    def name(self) -> str:
        """Return the name of the sensor.

        Returns:
            str: Sensor name.

        """
        return str(self.entity_description.name)

    @property
    def friendly_name(self) -> str:
        """Return the friendly name of the sensor.

        Returns:
            str: The sensor friendly name.

        """
        return self.name

    @property
    def _primary_aqi_source_label(self) -> str:
        """Return a UI label for the configured primary AQI source."""
        return "Overall" if self._entry.options.get(CONF_AQI_SOURCE) == AQI_SOURCE_OVERALL else "PM2.5"

    @property
    def suggested_object_id(self) -> str:
        """Return a stable base slug for the entity ID.

        Returns:
            str: Suggested entity object ID.

        """
        description_name = self.entity_description.name
        return description_name if isinstance(description_name, str) else self.sensor_name

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

    @property
    def state(self) -> StateType:
        """Return the state of the sensor."""
        self._attr_extra_state_attributes = dict(self._collector.get_sensor_attributes(self.entity_description.key))
        if self.entity_description.key in (TYPE_AQI, TYPE_AQI_24H):
            self._attr_extra_state_attributes.setdefault("configured_source", self._primary_aqi_source_label)
        self._attr_extra_state_attributes.setdefault(UNTIL, self._collector.until)

        value = self.native_value
        if isinstance(value, dt):
            return value.isoformat()
        return value

    async def async_added_to_hass(self) -> None:
        """Call when an entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(self._coordinator.async_add_listener(self._handle_coordinator_update))
