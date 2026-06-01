"""EPA API data collector that downloads the observation data."""

from collections.abc import Mapping
import datetime
from datetime import datetime as dt
import logging
import traceback
from typing import cast

from aiohttp import ClientResponseError, ClientSession
import aqicalc as aqi
# import aqi
from geopy import distance

from homeassistant.helpers.selector import SelectOptionDict
from homeassistant.util import Throttle

from .const import (
    AQI_SOURCE_OVERALL,
    AQI_SOURCE_PM25,
    ATTR_CONFIDENCE,
    ATTR_DATA_SOURCE,
    ATTR_TOTAL_SAMPLE,
    AVERAGE_VALUE,
    CONFIDENCE,
    COORDINATES,
    DEFAULT_AQI_SOURCE,
    DISTANCE,
    GEOMETRY,
    HEALTH_ADVICE,
    HEALTH_PARAMETER,
    NAME_CO,
    NAME_NO2,
    NAME_O3,
    NAME_PM10,
    NAME_PM25,
    NAME_SO2,
    PARAM_NAME,
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
    TYPE_PM25_24H,
    TYPE_PM25_AQI_VALUE,
    TYPE_PM25_AQI_VALUE_24H,
    TYPE_SO2,
    TYPE_SO2_24H,
    TYPE_SO2_ADVICE,
    TYPE_SO2_ADVICE_24H,
    TYPE_SO2_AQI_VALUE,
    UNTIL,
    URL_BASE,
    URL_FIND_SITE,
    URL_LIST_SITE,
    URL_PARAMETERS,
)

_LOGGER = logging.getLogger(__name__)

HOURLY = "1HR_AV"
DAILY = "24HR_AV"

POLLUTANT_SENSOR_MAP: dict[str, dict[str, str | None]] = {
    NAME_PM25: {
        "hourly_measure": TYPE_PM25,
        "daily_measure": TYPE_PM25_24H,
        "hourly_aqi": TYPE_PM25_AQI_VALUE,
        "daily_aqi": TYPE_PM25_AQI_VALUE_24H,
        "hourly_advice": TYPE_AQI_PM25,
        "daily_advice": TYPE_AQI_PM25_24H,
    },
    NAME_PM10: {
        "hourly_measure": TYPE_PM10,
        "daily_measure": TYPE_PM10_24H,
        "hourly_aqi": TYPE_PM10_AQI_VALUE,
        "daily_aqi": TYPE_PM10_AQI_VALUE_24H,
        "hourly_advice": TYPE_PM10_ADVICE,
        "daily_advice": TYPE_PM10_ADVICE_24H,
    },
    NAME_NO2: {
        "hourly_measure": TYPE_NO2,
        "daily_measure": TYPE_NO2_24H,
        "hourly_aqi": TYPE_NO2_AQI_VALUE,
        "daily_aqi": None,
        "hourly_advice": TYPE_NO2_ADVICE,
        "daily_advice": TYPE_NO2_ADVICE_24H,
    },
    NAME_O3: {
        "hourly_measure": TYPE_O3,
        "daily_measure": TYPE_O3_24H,
        "hourly_aqi": TYPE_O3_AQI_VALUE,
        "daily_aqi": None,
        "hourly_advice": TYPE_O3_ADVICE,
        "daily_advice": TYPE_O3_ADVICE_24H,
    },
    NAME_SO2: {
        "hourly_measure": TYPE_SO2,
        "daily_measure": TYPE_SO2_24H,
        "hourly_aqi": TYPE_SO2_AQI_VALUE,
        "daily_aqi": None,
        "hourly_advice": TYPE_SO2_ADVICE,
        "daily_advice": TYPE_SO2_ADVICE_24H,
    },
    NAME_CO: {
        "hourly_measure": TYPE_CO,
        "daily_measure": TYPE_CO_24H,
        "hourly_aqi": None,
        "daily_aqi": None,
        "hourly_advice": TYPE_CO_ADVICE,
        "daily_advice": TYPE_CO_ADVICE_24H,
    },
}

POLLUTANT_AQI_CONSTANTS: dict[str, dict[str, str | None]] = {
    NAME_PM25: {HOURLY: aqi.POLLUTANT_PM25, DAILY: aqi.POLLUTANT_PM25},
    NAME_PM10: {HOURLY: aqi.POLLUTANT_PM10, DAILY: aqi.POLLUTANT_PM10},
    NAME_NO2: {HOURLY: aqi.POLLUTANT_NO2_1H, DAILY: None},
    NAME_O3: {HOURLY: aqi.POLLUTANT_O3_1H, DAILY: None},
    NAME_SO2: {HOURLY: aqi.POLLUTANT_SO2_1H, DAILY: None},
    NAME_CO: {HOURLY: None, DAILY: None},
}

AQI_SENSOR_KEYS = {
    TYPE_AQI,
    TYPE_AQI_24H,
    TYPE_AQI_OVERALL,
    TYPE_AQI_OVERALL_24H,
    TYPE_PM25_AQI_VALUE,
    TYPE_PM25_AQI_VALUE_24H,
    TYPE_PM10_AQI_VALUE,
    TYPE_PM10_AQI_VALUE_24H,
    TYPE_NO2_AQI_VALUE,
    TYPE_O3_AQI_VALUE,
    TYPE_SO2_AQI_VALUE,
}

MEASUREMENT_SENSOR_KEYS = {
    TYPE_PM25,
    TYPE_PM25_24H,
    TYPE_PM10,
    TYPE_PM10_24H,
    TYPE_NO2,
    TYPE_NO2_24H,
    TYPE_O3,
    TYPE_O3_24H,
    TYPE_SO2,
    TYPE_SO2_24H,
    TYPE_CO,
    TYPE_CO_24H,
}

STORED_FLOAT_PRECISION_BY_KEY = {
    **dict.fromkeys(AQI_SENSOR_KEYS, 3),
    **dict.fromkeys(MEASUREMENT_SENSOR_KEYS, 4),
}


class Collector:
    """Collector for PyEPA."""

    def __init__(
        self,
        api_key: str,
        version_string: str = "1.0",
        epa_site_id: str = "",
        latitude: float = 0,
        longitude: float = 0,
        session: ClientSession | None = None,
        aqi_source: str = DEFAULT_AQI_SOURCE,
    ) -> None:
        """Init collector."""
        self._session: ClientSession | None = session
        self.location_data: dict = {}
        self.locations_list: list[SelectOptionDict] = []
        self.observation_data: dict = {}
        self.latitude: float = latitude
        self.longitude: float = longitude
        self.api_key: str = api_key
        self.version_string: str = version_string
        self.aqi_source: str = aqi_source
        self.until: str = ""
        self.site_id: str = ""
        self.site_name: str = ""
        self.aqi: float = 0
        self.aqi_24h: float = 0
        self.aqi_pm25: str = ""
        self.aqi_pm25_24h: str = ""
        self.confidence: float = 0
        self.confidence_24h: float = 0
        self.data_source_1h: str = ""
        self.observations_data: dict = {}
        self.pm25: float = 0
        self.pm25_24h: float | None = 0
        self.total_sample: float = 0
        self.total_sample_24h: float = 0
        self.last_updated: dt = dt.fromtimestamp(0)
        self.site_found: bool = False
        self.sites_found: bool = False
        self.available_sensor_keys: set[str] = set()
        self.sensor_attributes: dict[str, dict[str, str | float]] = {}
        self._unavailable_logged: bool = False
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
        session = self._session
        if session is not None and self.latitude != 0 and self.longitude != 0:
            url = f"{URL_BASE}{URL_FIND_SITE}[{self.latitude},{self.longitude}]"
            response = await session.get(url, headers=self.headers, ssl=False)

            if response is not None and response.status == 200:
                self.location_data = await response.json()
                try:
                    self.site_id = self.location_data[RECORDS][0][SITE_ID]
                    self.site_name = self.location_data[RECORDS][0][SITE_NAME]
                    _LOGGER.debug("Site %s (%s) located", self.site_name, self.site_id)
                    self.site_found = True
                except KeyError:
                    _LOGGER.error(
                        "Exception in get_location_data() for site %s: %s",
                        self.site_id,
                        traceback.format_exc(),
                    )
                    self.site_found = False

    async def get_locations_list(self):
        """Get JSON location list from EPA API endpoint."""
        session = self._session
        if session is not None and self.latitude != 0 and self.longitude != 0:
            url = f"{URL_BASE}{URL_LIST_SITE}"
            response = await session.get(url, headers=self.headers, ssl=False)

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
                                    record.get(SITE_HEALTH_ADVICES) is not None and record.get(SITE_HEALTH_ADVICES)[0] is not None  # pyright: ignore[reportOptionalSubscript]
                                ):  # Get Health Site Advices
                                    siteHealthAdvices = record[SITE_HEALTH_ADVICES][0]
                                    if siteHealthAdvices.get(HEALTH_PARAMETER) is not None:  # If site has a Health Parameter
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
                    sorted_locs = sorted(temp_loc_list, key=lambda itm: itm.get(DISTANCE))
                    self.locations_list: list[SelectOptionDict] = [
                        SelectOptionDict(label=location[SITE_NAME], value=location[SITE_ID]) for location in sorted_locs
                    ]
                    _LOGGER.debug("Site list loaded: %s sites", len(self.locations_list))
                    self.sites_found = True
                except KeyError:
                    _LOGGER.error(
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

    def get_pm25_24h(self) -> float | None:
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
        return ""

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

    def get_sensor_attributes(self, key: str) -> dict[str, str | float]:
        """Return extra state attributes for a sensor."""
        if not self.site_found:
            return {}
        return self.sensor_attributes.get(key, {})

    def get_available_sensor_keys(self) -> list[str]:
        """Return the currently available sensor keys."""
        return list(self.available_sensor_keys)

    def _log_api_readings_summary(self, parameters: list[dict[str, object]]) -> None:
        """Log one-line summary of raw API readings for troubleshooting."""
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return

        summary_parts: list[str] = []
        for parameter in parameters:
            pollutant_name = str(parameter.get(PARAM_NAME, "unknown"))
            time_series_readings = parameter.get(TIME_SERIES_READINGS)
            if not isinstance(time_series_readings, list):
                continue

            for time_series_reading in time_series_readings:
                if not isinstance(time_series_reading, dict):
                    continue
                time_series_name = time_series_reading.get(TIME_SERIES_NAME)
                if time_series_name not in (HOURLY, DAILY):
                    continue

                readings = time_series_reading.get(READINGS, [])
                if not isinstance(readings, list) or not readings:
                    continue

                reading = readings[0]
                if not isinstance(reading, dict):
                    continue

                summary_parts.append(
                    f"{pollutant_name}/{time_series_name}:"
                    f"avg={reading.get(AVERAGE_VALUE)!r},"
                    f"advice={reading.get(HEALTH_ADVICE)!r},"
                    f"conf={reading.get(CONFIDENCE)!r},"
                    f"sample={reading.get(TOTAL_SAMPLE)!r}"
                )

        site = self.site_name or self.site_id or "unknown_site"
        if summary_parts:
            _LOGGER.debug("%s API readings summary: %s", site, " | ".join(summary_parts))
        else:
            _LOGGER.debug("%s API readings summary: none", site)

    def _build_sensor_attributes(
        self,
        reading: Mapping[str, object],
        *,
        include_data_source: bool,
        source_label: str | None = None,
    ) -> dict[str, str | float]:
        """Build state attributes for a single reading-backed sensor."""
        confidence_value = cast(str | float | int, reading.get(CONFIDENCE, 0) or 0)
        sample_value = cast(str | float | int, reading.get(TOTAL_SAMPLE, 0) or 0)
        attributes: dict[str, str | float] = {
            ATTR_CONFIDENCE: float(confidence_value),
            ATTR_TOTAL_SAMPLE: float(sample_value),
            UNTIL: str(reading.get(UNTIL, "")),
        }
        if include_data_source:
            attributes[ATTR_DATA_SOURCE] = source_label or ""
        return attributes

    def _calculate_aqi(self, pollutant_name: str, time_series_name: str, value: str | float | None) -> float | None:
        """Return the AQI for a pollutant/time series pair when supported."""
        if value is None:
            return None
        try:
            numeric_value = float(value)
        except TypeError, ValueError:
            return None
        pollutant_constant = POLLUTANT_AQI_CONSTANTS.get(pollutant_name, {}).get(time_series_name)
        if pollutant_constant is None:
            return None
        try:
            return float(aqi.to_aqi([(pollutant_constant, numeric_value)]))
        except IndexError:
            _LOGGER.debug(
                "AQI calculation out of range for pollutant=%s series=%s value=%s",
                pollutant_name,
                time_series_name,
                numeric_value,
            )
            return None

    def _normalise_sensor_value(self, key: str | None, value: str | float | None) -> str | float | None:
        """Round stored numeric sensor values to stable precision."""
        if key is None or not isinstance(value, float):
            return value
        precision = STORED_FLOAT_PRECISION_BY_KEY.get(key)
        return value if precision is None else round(value, precision)

    def _collect_pollutant_readings(
        self,
        parameters: list[dict[str, object]],
    ) -> dict[str, dict[str, dict[str, str | float | None]]]:
        """Collect the first hourly and daily readings for each supported pollutant."""
        pollutant_readings: dict[str, dict[str, dict[str, str | float | None]]] = {}
        for parameter in parameters:
            pollutant_name = parameter.get(PARAM_NAME)
            if pollutant_name is None and len(parameters) == 1:
                # Preserve backwards compatibility with older payloads/tests that only
                # expose a single unnamed PM2.5 parameter block.
                pollutant_name = NAME_PM25
            if not isinstance(pollutant_name, str) or pollutant_name not in POLLUTANT_SENSOR_MAP:
                continue

            time_series_readings = parameter.get(TIME_SERIES_READINGS)
            if not isinstance(time_series_readings, list):
                continue

            for time_series_reading in time_series_readings:
                if not isinstance(time_series_reading, dict):
                    continue

                time_series_name = time_series_reading.get(TIME_SERIES_NAME)
                readings = time_series_reading.get(READINGS)
                if time_series_name not in (HOURLY, DAILY) or not isinstance(readings, list) or not readings:
                    continue

                first_reading = readings[0]
                if not isinstance(first_reading, dict):
                    continue

                pollutant_readings.setdefault(pollutant_name, {})[time_series_name] = cast(
                    dict[str, str | float | None],
                    first_reading,
                )

        return pollutant_readings

    def _process_pollutant_readings(
        self,
        pollutant_name: str,
        readings_by_series: dict[str, dict[str, str | float | None]],
        hourly_overall_candidates: list[tuple[str, str, float]],
        daily_overall_candidates: list[tuple[str, str, float]],
    ) -> None:
        """Store readings for one pollutant across hourly and daily series."""
        mapping = POLLUTANT_SENSOR_MAP[pollutant_name]

        hourly_reading = readings_by_series.get(HOURLY)
        if hourly_reading is not None:
            hourly_value = cast(str | float | None, hourly_reading.get(AVERAGE_VALUE))
            hourly_attributes = self._build_sensor_attributes(
                hourly_reading,
                include_data_source=True,
                source_label=HOURLY,
            )
            self._set_observation(mapping["hourly_measure"], hourly_value, hourly_attributes)
            if hourly_value is not None:
                self._set_observation(mapping["hourly_advice"], hourly_reading.get(HEALTH_ADVICE), hourly_attributes)

            hourly_aqi = self._calculate_aqi(pollutant_name, HOURLY, hourly_value)
            self._set_observation(mapping["hourly_aqi"], hourly_aqi, hourly_attributes)
            if mapping["hourly_aqi"] is not None and hourly_aqi is not None:
                hourly_overall_candidates.append((mapping["hourly_aqi"], pollutant_name, hourly_aqi))

        daily_reading = readings_by_series.get(DAILY)
        if daily_reading is not None:
            daily_value = cast(str | float | None, daily_reading.get(AVERAGE_VALUE))
            daily_attributes = self._build_sensor_attributes(
                daily_reading,
                include_data_source=False,
            )
            self._set_observation(mapping["daily_measure"], daily_value, daily_attributes)
            if daily_value is not None:
                self._set_observation(mapping["daily_advice"], daily_reading.get(HEALTH_ADVICE), daily_attributes)

            daily_aqi = self._calculate_aqi(pollutant_name, DAILY, daily_value)
            self._set_observation(mapping["daily_aqi"], daily_aqi, daily_attributes)
            if mapping["daily_aqi"] is not None and daily_aqi is not None:
                daily_overall_candidates.append((mapping["daily_aqi"], pollutant_name, daily_aqi))

        if (
            pollutant_name == NAME_PM25
            and daily_reading is not None
            and (
                hourly_reading is None
                or float(hourly_reading.get(CONFIDENCE, 0) or 0) <= 0
                or float(hourly_reading.get(TOTAL_SAMPLE, 0) or 0) <= 0
            )
        ):
            # Preserve the existing PM2.5 fallback when hourly data is absent
            # or considered unreliable by confidence/sample count.
            fallback_value = daily_reading.get(AVERAGE_VALUE)
            fallback_value = cast(str | float | None, fallback_value)
            fallback_attributes = self._build_sensor_attributes(
                daily_reading,
                include_data_source=True,
                source_label=DAILY,
            )
            self._set_observation(TYPE_PM25, fallback_value, fallback_attributes)
            if fallback_value is not None:
                self._set_observation(TYPE_AQI_PM25, daily_reading.get(HEALTH_ADVICE), fallback_attributes)
            fallback_aqi = self._calculate_aqi(NAME_PM25, DAILY, fallback_value)
            self._set_observation(TYPE_PM25_AQI_VALUE, fallback_aqi, fallback_attributes)
            if fallback_aqi is not None:
                hourly_overall_candidates.append((TYPE_PM25_AQI_VALUE, NAME_PM25, fallback_aqi))

        if pollutant_name == NAME_PM25 and daily_reading is not None and daily_reading.get(AVERAGE_VALUE) is None:
            # Retain explicit None for compatibility with legacy pm25_24h behavior.
            self.observation_data[TYPE_PM25_24H] = None

    def _set_observation(self, key: str | None, value: str | float | None, attributes: dict[str, str | float]) -> None:
        """Store a sensor value and its attributes when the key/value is valid."""
        if isinstance(value, str) and value.strip().lower() == "unknown":
            value = None
        value = self._normalise_sensor_value(key, value)
        if key is None or value is None:
            return
        self.observation_data[key] = value
        self.sensor_attributes[key] = attributes
        self.available_sensor_keys.add(key)

    def _set_primary_aqi(self, time_series_name: str, key: str, label: str) -> None:
        """Set the primary AQI sensor for the configured source."""
        target_key = TYPE_AQI if time_series_name == HOURLY else TYPE_AQI_24H
        value = self.observation_data.get(key)
        if value is None:
            return
        attributes = dict(self.sensor_attributes.get(key, {}))
        attributes["aqi_source"] = label
        self.observation_data[target_key] = value
        self.sensor_attributes[target_key] = attributes
        self.available_sensor_keys.add(target_key)

    def _set_overall_aqi(self, time_series_name: str, candidates: list[tuple[str, str, float]]) -> None:
        """Set explicit and primary overall AQI values from candidate subindices."""
        if not candidates:
            return
        source_key, pollutant_name, value = max(candidates, key=lambda candidate: candidate[2])
        target_key = TYPE_AQI_OVERALL if time_series_name == HOURLY else TYPE_AQI_OVERALL_24H
        attributes = dict(self.sensor_attributes.get(source_key, {}))
        attributes["aqi_source"] = pollutant_name
        self.observation_data[target_key] = cast(float, self._normalise_sensor_value(target_key, value))
        self.sensor_attributes[target_key] = attributes
        self.available_sensor_keys.add(target_key)

        if self.aqi_source == AQI_SOURCE_OVERALL:
            self._set_primary_aqi(time_series_name, target_key, AQI_SOURCE_OVERALL)

    def _sync_legacy_fields(self) -> None:
        """Keep legacy collector fields aligned with the observation map."""
        self.aqi = float(self.observation_data.get(TYPE_AQI) or 0)
        self.aqi_24h = float(self.observation_data.get(TYPE_AQI_24H) or 0)
        self.aqi_pm25 = str(self.observation_data.get(TYPE_AQI_PM25) or "")
        self.aqi_pm25_24h = str(self.observation_data.get(TYPE_AQI_PM25_24H) or "")
        self.pm25 = float(self.observation_data.get(TYPE_PM25) or 0)
        pm25_24h_value = self.observation_data.get(TYPE_PM25_24H, 0)
        self.pm25_24h = float(pm25_24h_value) if pm25_24h_value is not None else None

        hourly_attrs = self.sensor_attributes.get(TYPE_PM25, {}) or self.sensor_attributes.get(TYPE_AQI, {})
        daily_attrs = self.sensor_attributes.get(TYPE_PM25_24H, {}) or self.sensor_attributes.get(TYPE_AQI_24H, {})
        self.confidence = float(hourly_attrs.get(ATTR_CONFIDENCE, 0) or 0)
        self.total_sample = float(hourly_attrs.get(ATTR_TOTAL_SAMPLE, 0) or 0)
        self.data_source_1h = str(hourly_attrs.get(ATTR_DATA_SOURCE, ""))
        self.confidence_24h = float(daily_attrs.get(ATTR_CONFIDENCE, 0) or 0)
        self.total_sample_24h = float(daily_attrs.get(ATTR_TOTAL_SAMPLE, 0) or 0)
        self.until = str((hourly_attrs or daily_attrs).get(UNTIL, ""))

    async def extract_observation_data(self):
        """Extract Observation Data to individual fields."""
        parameters: list[dict[str, object]] = []
        self.observation_data = {}
        self.sensor_attributes = {}
        self.available_sensor_keys = set()
        parameters_data = self.observations_data.get(PARAMETERS)
        if isinstance(parameters_data, list):
            parameters = [parameter for parameter in parameters_data if isinstance(parameter, dict)]
            self._log_api_readings_summary(parameters)
            pollutant_readings = self._collect_pollutant_readings(parameters)

            hourly_overall_candidates: list[tuple[str, str, float]] = []
            daily_overall_candidates: list[tuple[str, str, float]] = []

            for pollutant_name, readings_by_series in pollutant_readings.items():
                self._process_pollutant_readings(
                    pollutant_name,
                    readings_by_series,
                    hourly_overall_candidates,
                    daily_overall_candidates,
                )

            self._set_overall_aqi(HOURLY, hourly_overall_candidates)
            self._set_overall_aqi(DAILY, daily_overall_candidates)

            if self.aqi_source == AQI_SOURCE_PM25:
                self._set_primary_aqi(HOURLY, TYPE_PM25_AQI_VALUE, AQI_SOURCE_PM25)
                self._set_primary_aqi(DAILY, TYPE_PM25_AQI_VALUE_24H, AQI_SOURCE_PM25)

            if TYPE_AQI not in self.observation_data and TYPE_AQI_OVERALL in self.observation_data:
                self._set_primary_aqi(HOURLY, TYPE_AQI_OVERALL, AQI_SOURCE_OVERALL)
            if TYPE_AQI_24H not in self.observation_data and TYPE_AQI_OVERALL_24H in self.observation_data:
                self._set_primary_aqi(DAILY, TYPE_AQI_OVERALL_24H, AQI_SOURCE_OVERALL)

            self._sync_legacy_fields()

            data_valid = bool(self.available_sensor_keys)
            if data_valid:
                self.last_updated = dt.now()
                if self._unavailable_logged:
                    _LOGGER.info("%s data is available again", self.site_name)
                    self._unavailable_logged = False
            elif not self._unavailable_logged:
                _LOGGER.warning("%s returned observation data but no valid readings", self.site_name)
                self._unavailable_logged = True
        elif not self._unavailable_logged:
            _LOGGER.warning("%s returned no observation data", self.site_name)
            self._unavailable_logged = True

    @Throttle(datetime.timedelta(minutes=5))
    async def async_update(self):
        """Refresh the data on the collector object."""
        try:
            session = self._session
            if session is not None:
                if self.location_data is None:
                    await self.get_location_data()

                _LOGGER.debug("Updating %s observation data", self.site_name)
                async with session.get(URL_BASE + self.get_location() + URL_PARAMETERS, headers=self.headers, ssl=False) as resp:
                    if resp.status >= 500:
                        if not self._unavailable_logged:
                            _LOGGER.warning(
                                "%s air quality readings could not be updated: the service returned HTTP %d (transient error, will retry)",
                                self.site_name,
                                resp.status,
                            )
                            self._unavailable_logged = True
                        return
                    self.observations_data = await resp.json()
                    await self.extract_observation_data()
        except ConnectionRefusedError as e:
            if not self._unavailable_logged:
                _LOGGER.warning("Connection refused for site %s: %s", self.site_name, e)
                self._unavailable_logged = True
        except ClientResponseError as e:
            if not self._unavailable_logged:
                _LOGGER.warning(
                    "%s air quality readings could not be updated: HTTP error %d (will retry)",
                    self.site_name,
                    e.status,
                )
                self._unavailable_logged = True
        except Exception:  # noqa: BLE001
            if not self._unavailable_logged:
                _LOGGER.warning(
                    "Exception in async_update() for site %s: %s",
                    self.site_name,
                    traceback.format_exc(),
                )
                self._unavailable_logged = True

    async def async_setup(self):
        """Set up the location list for the collector object."""
        try:
            if self.locations_list is None or self.locations_list == []:
                await self.get_locations_list()

        except ConnectionRefusedError as e:
            _LOGGER.error("Connection error in async_setup, connection refused: %s", e)
        except Exception:  # noqa: BLE001
            _LOGGER.error(
                "Exception in async_setup(): %s",
                traceback.format_exc(),
            )
