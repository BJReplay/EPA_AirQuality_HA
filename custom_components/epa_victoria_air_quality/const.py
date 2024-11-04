"""Constants for the EPA Air Quality integration."""

# pylint: disable=C0304, E0401, C0301

from __future__ import annotations
from typing import Final

# Integration constants
ATTR_ENTRY_TYPE: Final = "entry_type"
ATTRIBUTION: Final = "Data retrieved from EPA (Victoria)"
COLLECTOR: Final = "collector"
CONF_SITE_ID = "site_id"
DOMAIN = "epa_victoria_air_quality"
ENTRY_TYPE_SERVICE: Final = "service"
COORDINATOR: Final = "coordinator"
EPA_URL = "https://gateway.api.epa.vic.gov.au/environmentMonitoring/v1/sites/"
TIME_FORMAT = "%H:%M:%S"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT_UTC = "%Y-%m-%d %H:%M:%S UTC"
INIT_MSG = """This is a custom integration. When troubleshooting a problem, after
reviewing open and closed issues, and the discussions.

Beta versions may also have addressed issues so look at those.

If all else fails, then open an issue and our community will try to
help: https://github.com/loryanstrant/EPA_AirQuality_HA/issues"""
MANUFACTURER = "loryanstrant"
SERVICE_UPDATE = "update_quality"
TITLE = "EPA Air Quality"
TYPE_AQI_PM25 = "aqi_pm25"
TYPE_AQI_PM25_24H = "aqi_pm25_24h"
TYPE_PM25 = "pm25"
TYPE_PM25_24H = "pm25_24h"