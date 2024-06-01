import logging
import requests
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    CONF_API_KEY,
    CONF_SITE_ID,
    STATE_CLASS_MEASUREMENT,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=30)

SENSOR_TYPES = {
    "hourly_average": {
        "name": "Hourly Average",
        "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        "device_class": "pm25",
        "icon": "mdi:chemical-weapon",
        "value_template": "{{ value_json['parameters'][0]['timeSeriesReadings'][0]['readings'][0]['averageValue'] }}"
    },
    "hourly_health_advice": {
        "name": "Hourly Health Advice",
        "unit": None,
        "device_class": None,
        "icon": "mdi:information-outline",
        "value_template": "{{ value_json['parameters'][0]['timeSeriesReadings'][0]['readings'][0]['healthAdvice'] }}"
    },
    "daily_average": {
        "name": "Daily Average",
        "unit": CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        "device_class": "pm25",
        "icon": "mdi:chemical-weapon",
        "value_template": "{{ value_json['parameters'][0]['timeSeriesReadings'][1]['readings'][0]['averageValue'] }}"
    },
    "daily_health_advice": {
        "name": "Daily Health Advice",
        "unit": None,
        "device_class": None,
        "icon": "mdi:information-outline",
        "value_template": "{{ value_json['parameters'][0]['timeSeriesReadings'][1]['readings'][0]['healthAdvice'] }}"
    },
}

def setup_platform(hass, config, add_entities, discovery_info=None):
    api_key = config.get(CONF_API_KEY)
    site_id = config.get(CONF_SITE_ID)

    coordinator = EPADataUpdateCoordinator(hass, api_key, site_id)

    sensors = []
    for sensor_type in SENSOR_TYPES:
        sensors.append(EPAQualitySensor(coordinator, sensor_type))
    
    add_entities(sensors, True)

class EPADataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api_key, site_id):
        self.api_key = api_key
        self.site_id = site_id

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        try:
            headers = {"X-API-Key": self.api_key}
            response = requests.get(f"https://gateway.api.epa.vic.gov.au/environmentMonitoring/v1/sites/{self.site_id}/parameters", headers=headers)
            response.raise_for_status()
            data = response.json()
            return data
        except requests.RequestException as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

class EPAQualitySensor(SensorEntity):
    def __init__(self, coordinator, sensor_type):
        self.coordinator = coordinator
        self.sensor_type = sensor_type
        sensor_info = SENSOR_TYPES[sensor_type]
        self._attr_name = f"EPA {coordinator.site_id} {sensor_info['name']}"
        self._attr_unique_id = f"epa_victoria_air_quality_{coordinator.site_id}_{sensor_type}"
        self._attr_unit_of_measurement = sensor_info["unit"]
        self._attr_icon = sensor_info["icon"]
        self._attr_device_class = sensor_info["device_class"]
        self._attr_state_class = STATE_CLASS_MEASUREMENT if sensor_info["unit"] else None
        self._attr_state = None

    @property
    def state(self):
        if self.coordinator.data:
            try:
                return eval(self.sensor_type)["value_template"]
            except (KeyError, IndexError):
                return None
        return None

    @property
    def extra_state_attributes(self):
        if self.coordinator.data:
            try:
                param = eval(self.sensor_type)["value_template"]
                return {
                    "site_id": self.coordinator.site_id,
                    "update_time": param.get("update_time"),
                    "unit": param.get("unit"),
                }
            except (KeyError, IndexError):
                return {}
        return {}

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.site_id)},
            name="EPA Victoria Air Quality",
            manufacturer="EPA Victoria",
            model="Air Quality Sensor",
        )

    def update(self):
        self.coordinator.async_request_refresh()
