"""EPA API data collector that downloads the observation data."""

import datetime
from datetime import datetime as dt
import logging
import traceback

import aiohttp
import aqi
from geopy import distance

from homeassistant.helpers.selector import SelectOptionDict
from homeassistant.util import Throttle

from .const import (
    ATTR_CONFIDENCE,
    ATTR_CONFIDENCE_24H,
    ATTR_DATA_SOURCE,
    ATTR_TOTAL_SAMPLE,
    ATTR_TOTAL_SAMPLE_24H,
    AVERAGE_VALUE,
    CONFIDENCE,
    COORDINATES,
    DISTANCE,
    GEOMETRY,
    HEALTH_ADVICE,
    HEALTH_PARAMETER,
    PARAMETERS,
    READINGS,
    RECORDS,
    SITE_HEALTH_ADVICES,
    SITE_ID,
    SITE_NAME,
    SITE_TYPE,
    SITE_TYPE_SENSOR,
    SITE_TYPE_STANDARD,
    TIME_SERIES_NAME,
    TIME_SERIES_READINGS,
    TOTAL_SAMPLE,
    TYPE_AQI,
    TYPE_AQI_24H,
    TYPE_AQI_PM25,
    TYPE_AQI_PM25_24H,
    TYPE_PM25,
    TYPE_PM25_24H,
    UNTIL,
    URL_BASE,
    URL_FIND_SITE,
    URL_LIST_SITE,
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
        self.location_data: dict = {}
        self.locations_list: list[SelectOptionDict] = []
        self.observation_data: dict = {}
        self.latitude: float = latitude
        self.longitude: float = longitude
        self.api_key: str = api_key
        self.version_string: str = version_string
        self.until: str = ""
        self.site_id: str = ""
        self.site_name: str = ""
        self.aqi: float = 0
        self.aqi_24h: float = 0
        self.aqi_pm25: str = ""
        self.aqi_pm25_24h: str
        self.confidence: float = 0
        self.confidence_24h: float = 0
        self.data_source_1h: str = ""
        self.pm25: float = 0
        self.pm25_24h: float = 0
        self.total_sample: float = 0
        self.total_sample_24h: float = 0
        self.last_updated: dt = dt.fromtimestamp(0)
        self.site_found: bool = False
        self.sites_found: bool = False
        self.headers: dict = {
            "Accept": "application/json",
            "User-Agent": "ha-epa-integration/" + self.version_string,
            "X-API-Key": self.api_key,
        }

        if epa_site_id != "":
            self.site_id = epa_site_id
            self.site_found = True

    async def get_location_data(self):
        """Get JSON location name from EPA API endpoint."""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            if self.latitude != 0 and self.longitude != 0:
                url = f"{URL_BASE}{URL_FIND_SITE}[{self.latitude},{self.longitude}]"
                response = await session.get(url)

                if response is not None and response.status == 200:
                    self.location_data = await response.json()
                    try:
                        self.site_id = self.location_data[RECORDS][0][SITE_ID]
                        self.site_name = self.location_data[RECORDS][0][SITE_NAME]
                        _LOGGER.debug("EPA Site ID Located: %s", self.site_id)
                        self.site_found = True
                    except KeyError:
                        _LOGGER.debug(
                            "Exception in get_location_data(): %s",
                            traceback.format_exc(),
                        )
                        self.site_found = False

    async def get_locations_list(self):
        """Get JSON location list from EPA API endpoint."""
        async with aiohttp.ClientSession(headers=self.headers) as session:
            if self.latitude != 0 and self.longitude != 0:
                url = f"{URL_BASE}{URL_LIST_SITE}"
                response = await session.get(url)

                if response is not None and response.status == 200:
                    temp_loc_list = []
                    locations_list = await response.json()
                    try:
                        records: dict = {}
                        record: dict = {}
                        siteHealthAdvices: dict = {}
                        if locations_list.get(RECORDS) is not None:
                            records = locations_list[RECORDS]
                            for record in records:
                                site_id = record[SITE_ID]
                                site_name = record[SITE_NAME]
                                site_type = record[SITE_TYPE]
                                if site_type in (
                                    SITE_TYPE_SENSOR,
                                    SITE_TYPE_STANDARD,
                                ):  # If it isn't a camera
                                    if (
                                        record.get(SITE_HEALTH_ADVICES)[0] is not None
                                    ):  # Get Health Site Advices
                                        siteHealthAdvices = record[SITE_HEALTH_ADVICES][
                                            0
                                        ]
                                        if (
                                            siteHealthAdvices.get(HEALTH_PARAMETER)
                                            is not None
                                        ):  # If site has a Health Parameter
                                            latitude = record[GEOMETRY][COORDINATES][0]
                                            longitude = record[GEOMETRY][COORDINATES][1]
                                            temp_loc_list.append(
                                                {
                                                    SITE_ID: site_id,
                                                    SITE_NAME: site_name,
                                                    DISTANCE: distance.geodesic(
                                                        (latitude, longitude),
                                                        (self.latitude, self.longitude),
                                                    ).meters,
                                                }
                                            )
                        sorted_locs = sorted(
                            temp_loc_list, key=lambda itm: itm.get(DISTANCE)
                        )
                        self.locations_list: list[SelectOptionDict] = [
                            SelectOptionDict(
                                label=location[SITE_NAME], value=location[SITE_ID]
                            )
                            for location in sorted_locs
                        ]
                        _LOGGER.debug("EPA Site List Loaded")
                        self.sites_found = True
                    except KeyError:
                        _LOGGER.debug(
                            "Exception in get_locations_list(): %s",
                            traceback.format_exc(),
                        )
                        self.sites_found = False

    def valid_location(self) -> bool:
        """Return true if a valid location has been found from the latitude and longitude.

        Returns:
            bool: True if a valid EPA location has been found

        """
        return self.site_found

    def valid_location_list(self) -> bool:
        """Return true if a valid location list has been loaded.

        Returns:
            bool: True if a valid EPA location list has been loaded

        """
        return self.sites_found

    def get_location(self) -> str:
        """Return the EPA Site Location GUID.

        Returns:
            str: EPA Site Location GUID

        """
        if self.site_found:
            return self.site_id
        return ""

    def get_location_list(self) -> list:
        """Return the EPA Site Location GUID.

        Returns:
            str: EPA Site Location GUID

        """
        if self.sites_found:
            return self.locations_list
        return []

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

    def get_confidence(self) -> float:
        """Return the EPA reading confidence.

        Returns:
            float: EPA reading confidence

        """
        if self.site_found:
            return self.confidence
        return 0

    def get_confidence_24h(self) -> float:
        """Return the EPA reading confidence over 24 hours.

        Returns:
            float: EPA reading confidence over 24 hours

        """
        if self.site_found:
            return self.confidence_24h
        return 0

    def get_data_source(self) -> str:
        """Return the EPA Reading Data Source.

        Returns:
            str: EPA Site Reading Data Source for the 1 Hour Reading

        """
        if self.site_found:
            return self.data_source_1h
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

    def get_total_sample(self) -> float:
        """Return the EPA reading total samples.

        Returns:
            float: EPA reading total samples

        """
        if self.site_found:
            return self.total_sample
        return 0

    def get_total_sample_24h(self) -> float:
        """Return the EPA reading total samples over 24 hours.

        Returns:
            float: EPA reading total samples over 24 hours

        """
        if self.site_found:
            return self.total_sample_24h
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
        parameters: dict = {}
        time_series_readings: dict = {}
        time_series_reading: dict = {}
        self.observation_data = {}
        if self.observations_data.get(PARAMETERS) is not None:
            parameters = self.observations_data[PARAMETERS][0]
            if parameters.get(TIME_SERIES_READINGS) is not None:
                time_series_readings = parameters[TIME_SERIES_READINGS]
                for time_series_reading in time_series_readings:
                    reading: dict = time_series_reading[READINGS][0]
                    match time_series_reading[TIME_SERIES_NAME]:
                        case "1HR_AV":
                            self.confidence = reading[CONFIDENCE]
                            self.total_sample = reading[TOTAL_SAMPLE]
                            if self.confidence > 0 and self.total_sample > 0:
                                self.aqi_pm25 = reading[HEALTH_ADVICE]
                                self.pm25 = reading[AVERAGE_VALUE]
                                self.aqi = aqi.to_aqi([(aqi.POLLUTANT_PM25, self.pm25)])
                                self.data_source_1h = time_series_reading[
                                    TIME_SERIES_NAME
                                ]
                            self.until = reading[UNTIL]
                        case "24HR_AV":
                            self.confidence_24h = reading[CONFIDENCE]
                            self.total_sample_24h = reading[TOTAL_SAMPLE]
                            self.aqi_pm25_24h = reading[HEALTH_ADVICE]
                            self.pm25_24h = reading[AVERAGE_VALUE]
                            self.aqi_24h = aqi.to_aqi(
                                [(aqi.POLLUTANT_PM25, self.pm25_24h)]
                            )
                            if (
                                self.confidence == 0
                                and self.total_sample == 0
                                and self.confidence_24h > 0
                                and self.total_sample_24h > 0
                            ):
                                # Update 1 Hour readings
                                self.aqi_pm25 = self.aqi_pm25_24h
                                self.pm25 = self.pm25_24h
                                self.aqi = self.aqi_24h
                                self.data_source_1h = time_series_reading[
                                    TIME_SERIES_NAME
                                ]

            self.last_updated = dt.now()
            self.observation_data = {
                TYPE_AQI: self.aqi,
                TYPE_AQI_24H: self.aqi_24h,
                TYPE_AQI_PM25: self.aqi_pm25,
                TYPE_AQI_PM25_24H: self.aqi_pm25_24h,
                TYPE_PM25: self.pm25,
                TYPE_PM25_24H: self.pm25_24h,
                ATTR_CONFIDENCE: self.confidence,
                ATTR_CONFIDENCE_24H: self.confidence_24h,
                ATTR_DATA_SOURCE: self.data_source_1h,
                ATTR_TOTAL_SAMPLE: self.total_sample,
                ATTR_TOTAL_SAMPLE_24H: self.total_sample_24h,
                UNTIL: self.until,
            }

    @Throttle(datetime.timedelta(minutes=5))
    async def async_update(self):
        """Refresh the data on the collector object."""
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                if self.location_data is None:
                    await self.get_location_data()

                async with session.get(
                    URL_BASE + self.get_location() + URL_PARAMETERS
                ) as resp:
                    self.observations_data = await resp.json()
                    await self.extract_observation_data()
        except ConnectionRefusedError as e:
            _LOGGER.error("Connection error in async_update, connection refused: %s", e)
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Exception in async_update(): %s",
                traceback.format_exc(),
            )

    async def async_setup(self):
        """Set up the location list for the collector object."""
        try:
            if self.locations_list is None or self.locations_list == []:
                await self.get_locations_list()

        except ConnectionRefusedError as e:
            _LOGGER.error("Connection error in async_setup, connection refused: %s", e)
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Exception in async_setup(): %s",
                traceback.format_exc(),
            )
