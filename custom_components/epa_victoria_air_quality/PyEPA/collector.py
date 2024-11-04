"""EPA API data 'collector' that downloads the observation data."""

# pylint: disable=C0103, C0301, C0302, C0304, C0321, E0401, R0902, R0914, W0105, W0702, W0706, W0718, W0719
from dataclasses import dataclass

import datetime
from datetime import datetime
from datetime import timezone
import logging
import aiohttp # type: ignore

from homeassistant.util import Throttle # type: ignore

from PyEPA.const import (
    URL_BASE,
    URL_FIND_SITE,
    URL_PARAMETERS,
    READINGS,
    AVERAGE_VALUE,
    HEALTH_ADVICE,
    TIME_SERIES_READINGS,
    UNTIL,
    PARAMETERS,
    TIME_SERIES_NAME,
    )

_LOGGER = logging.getLogger(__name__)

@dataclass
class ConnectionOptions:
    """EPA options for the integration."""
    api_key: str
    site_id: str
    host: str
    latitude: float
    longitude: float
    tz: timezone
    headers: str

class Collector:
    """Collector for PyEPA."""

    def __init__(self, latitude, longitude, headers):
        """Init collector."""
        self.locations_data = None
        self.observations_data = None
        self.site_id = None
        self.latitude = latitude
        self.longitude = longitude
        self.headers = headers
        self.until = ""
        self.aqi_pm25 = ""
        self.pm25 = float(0)
        self.aqi_pm25_24h = ""
        self.pm25_24h = float(0)
        self.last_updated = ""

    async def get_locations_data(self):
        """Get JSON location name from BOM API endpoint."""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            response = await session.get(URL_BASE + URL_FIND_SITE + "[%s,%s]", self.latitude, self.longitude)

        if response is not None and response.status == 200:
            self.locations_data = await response.json()
            if self.observations_data["records"]["siteID"] is not None:
                self.site_id = self.observations_data["records"]["siteID"]

    async def extract_observation_data(self):
        """Extracts Observation Data to individual fields"""
        if self.observations_data[PARAMETERS] is not None:
            p = self.observations_data[PARAMETERS]
            if p[TIME_SERIES_READINGS] is not None:
                for timeSeriesReadings in p:
                    match timeSeriesReadings[TIME_SERIES_NAME]:
                        case "1HR_AV":
                            self.aqi_pm25 = timeSeriesReadings[READINGS][HEALTH_ADVICE]
                            self.pm25 = timeSeriesReadings[READINGS][AVERAGE_VALUE]
                            self.until = timeSeriesReadings[READINGS][UNTIL]
                        case "24HR_AV":
                            self.aqi_pm25_24h = timeSeriesReadings[READINGS][HEALTH_ADVICE]
                            self.pm25_24h = timeSeriesReadings[READINGS][AVERAGE_VALUE]
            self.last_updated = datetime.now()

    @Throttle(datetime.timedelta(minutes=30))
    async def async_update(self):
        """Refresh the data on the collector object."""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            if self.locations_data is None:
                await self.get_locations_data()

            async with session.get(URL_BASE + self.site_id + URL_PARAMETERS) as resp:
                self.observations_data = await resp.json()
                await self.extract_observation_data() 
