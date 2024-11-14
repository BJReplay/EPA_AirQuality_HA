"""EPA API data collector that downloads the observation data."""

import datetime
from datetime import datetime as dt
import logging
import traceback

import aiohttp
import aqi

from homeassistant.util import Throttle

from .const import (
    AVERAGE_VALUE,
    HEALTH_ADVICE,
    PARAMETERS,
    READINGS,
    RECORDS,
    SITE_ID,
    TIME_SERIES_NAME,
    TIME_SERIES_READINGS,
    TYPE_AQI,
    TYPE_AQI_24H,
    TYPE_AQI_PM25,
    TYPE_AQI_PM25_24H,
    TYPE_PM25,
    TYPE_PM25_24H,
    UNTIL,
    URL_BASE,
    URL_FIND_SITE,
    URL_PARAMETERS,
)

_LOGGER = logging.getLogger(__name__)


class Collector:
    """Collector for PyEPA."""

    def __init__(
        self,
        api_key: str,
        version_string: str = "1.0",
        epa_site_id: str = "",
        latitude: float = 0,
        longitude: float = 0,
    ) -> None:
        """Init collector."""
        self.locations_data = {}
        self.observation_data = {}
        self.latitude = latitude
        self.longitude = longitude
        self.api_key = api_key
        self.version_string = version_string
        self.until = ""
        self.site_id = ""
        self.aqi = float(0)
        self.aqi_24h = float(0)
        self.aqi_pm25 = ""
        self.aqi_pm25_24h = ""
        self.pm25 = float(0)
        self.pm25_24h = float(0)
        self.last_updated = ""
        self.site_found = False

        self.headers = {
            "Accept": "application/json",
            "User-Agent": "ha-epa-integration/" + self.version_string,
            "X-API-Key": self.api_key,
        }

        if epa_site_id != "":
            self.site_id = epa_site_id
            self.site_found = True

    async def get_locations_data(self):
        """Get JSON location name from EPA API endpoint."""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            if self.latitude != 0 and self.longitude != 0:
                url = f"{URL_BASE}{URL_FIND_SITE}[{self.latitude},{self.longitude}]"
                response = await session.get(url)

                if response is not None and response.status == 200:
                    self.locations_data = await response.json()
                    try:
                        self.site_id = self.locations_data[RECORDS][0][SITE_ID]
                        _LOGGER.debug("EPA Site ID Located: %s", self.site_id)
                        self.site_found = True
                    except:
                        _LOGGER.debug(
                            "Exception in get_locations_data(): %s",
                            traceback.format_exc(),
                        )
                        self.site_found = False

    def valid_location(self) -> bool:
        """Return true if a valid location has been found from the latitude and longitude.

        Returns:
            bool: True if a valid EPA location has been found

        """
        return self.site_found

    def get_location(self) -> str:
        """Return the EPA Site Location GUID.

        Returns:
            str: EPA Site Location GUID

        """
        if self.site_found:
            return self.site_id
        return ""

    def get_aqi(self) -> float:
        """Return the EPA Site aqi.

        Returns:
            float: EPA Site Calculated API

        """
        if self.site_found:
            return self.aqi
        return 0

    def get_aqi_24h(self) -> float:
        """Return the EPA Site aqi_24h.

        Returns:
            float: EPA Site Calculated API 24h Average

        """
        if self.site_found:
            return self.aqi_24h
        return 0

    def get_aqi_pm25(self) -> str:
        """Return the EPA Site aqi_pm25.

        Returns:
            str: EPA Site aqi_pm25

        """
        if self.site_found:
            return self.aqi_pm25
        return ""

    def get_aqi_pm25_24h(self) -> str:
        """Return the EPA Site aqi_pm25_24h.

        Returns:
            str: EPA Site aqi_pm25_24h

        """
        if self.site_found:
            return self.aqi_pm25_24h
        return ""

    def get_pm25(self) -> float:
        """Return the EPA Site pm25.

        Returns:
            str: EPA Site pm25

        """
        if self.site_found:
            return self.pm25
        return 0

    def get_pm25_24h(self) -> float:
        """Return the EPA Site pm25_24h.

        Returns:
            str: EPA Site pm25_24h

        """
        if self.site_found:
            return self.pm25_24h
        return 0

    def get_until(self) -> str:
        """Return the EPA Reading Validity.

        Returns:
            str: EPA Site Reading Validity Time

        """
        if self.site_found:
            return self.until
        return 0

    def get_sensor(self, key: str):
        """Return A sensor.

        Returns:
            Any: EPA Site Sensor

        """
        if self.site_found:
            try:
                return self.observation_data.get(key)
            except KeyError:
                return "Sensor %s Not Found!"
        return None

    async def extract_observation_data(self):
        """Extract Observation Data to individual fields."""
        parameters = {}
        time_series_readings = {}
        time_series_reading = {}
        self.observation_data = {}
        if self.observations_data.get(PARAMETERS) is not None:
            parameters = self.observations_data[PARAMETERS][0]
            if parameters.get(TIME_SERIES_READINGS) is not None:
                time_series_readings = parameters[TIME_SERIES_READINGS]
                for time_series_reading in time_series_readings:
                    reading = time_series_reading[READINGS][0]
                    match time_series_reading[TIME_SERIES_NAME]:
                        case "1HR_AV":
                            self.aqi_pm25 = reading[HEALTH_ADVICE]
                            self.pm25 = reading[AVERAGE_VALUE]
                            self.aqi = aqi.to_aqi([(aqi.POLLUTANT_PM25, self.pm25)])
                            self.until = reading[UNTIL]
                        case "24HR_AV":
                            self.aqi_pm25_24h = reading[HEALTH_ADVICE]
                            self.pm25_24h = reading[AVERAGE_VALUE]
                            self.aqi_24h = aqi.to_aqi(
                                [(aqi.POLLUTANT_PM25, self.pm25_24h)]
                            )
            self.last_updated = dt.now()
            self.observation_data = {
                TYPE_AQI: self.aqi,
                TYPE_AQI_24H: self.aqi_24h,
                TYPE_AQI_PM25: self.aqi_pm25,
                TYPE_AQI_PM25_24H: self.aqi_pm25_24h,
                TYPE_PM25: self.pm25,
                TYPE_PM25_24H: self.pm25_24h,
                UNTIL: self.until,
            }

    @Throttle(datetime.timedelta(minutes=5))
    async def async_update(self):
        """Refresh the data on the collector object."""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                if self.locations_data is None:
                    await self.get_locations_data()

                async with session.get(
                    URL_BASE + self.site_id + URL_PARAMETERS
                ) as resp:
                    self.observations_data = await resp.json()
                    await self.extract_observation_data()
        except:
            _LOGGER.debug(
                "Exception in get_locations_data(): %s",
                traceback.format_exc(),
            )
