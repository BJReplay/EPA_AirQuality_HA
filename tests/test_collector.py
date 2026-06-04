"""Tests for the EPA Victoria Air Quality collector."""

from typing import Any, Self
from unittest.mock import MagicMock, patch

from aiohttp import ClientResponseError, ContentTypeError, RequestInfo
import pytest

from homeassistant.components.epa_victoria_air_quality.collector import Collector
from homeassistant.components.epa_victoria_air_quality.const import (
    AQI_SOURCE_OVERALL,
    NAME_PM10,
    TYPE_AQI,
    TYPE_AQI_OVERALL,
)

from . import TEST_API_KEY_1, TEST_SITE_ID_1
from .simulator.simulate import SimulatedEPA

# Melbourne-ish CBD coordinates
TEST_LAT = -37.8136
TEST_LON = 144.9631

SIM = SimulatedEPA()


class MockResponse:
    """Mock aiohttp response."""

    def __init__(self, payload: Any, status: int = 200) -> None:
        """Initialise the mock response."""
        self.status = status
        self._payload = payload

    async def json(self) -> Any:
        """Return payload."""
        return self._payload

    def __await__(self):
        """Support: resp = await session.get(url)."""

        async def _coro() -> MockResponse:
            return self

        return _coro().__await__()

    async def __aenter__(self) -> Self:
        """Support: async with session.get(url) as resp:."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit context manager."""


class MockClientSession:
    """Mock aiohttp client session, pre-loaded response queue."""

    def __init__(self, responses: list[MockResponse]) -> None:
        """Initialise with a list of responses to return in order."""
        self._responses = responses
        self._call_count = 0

    def get(self, url: str, **kwargs: Any) -> MockResponse:
        """Return the next queued response."""
        resp = self._responses[min(self._call_count, len(self._responses) - 1)]
        self._call_count += 1
        return resp

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the async context manager."""


class ErrorClientSession:
    """Mock session whose get() raises a given exception."""

    def __init__(self, exc: Exception) -> None:
        """Initialise with the exception to raise."""
        self._exc = exc

    def get(self, url: str, **kwargs: Any) -> None:
        """Raise the configured exception."""
        raise self._exc


def test_collector_init_no_site_id() -> None:
    """Collector starts with no resolved site when no site_id is provided."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    assert c.api_key == TEST_API_KEY_1
    assert c.latitude == TEST_LAT
    assert c.longitude == TEST_LON
    assert not c.site_found
    assert not c.sites_found
    assert c.site_id == ""


def test_collector_init_with_site_id() -> None:
    """Collector marks site as found when a site_id is pre-set at construction."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    assert c.site_id == TEST_SITE_ID_1
    assert c.site_found is True


@pytest.mark.asyncio
async def test_get_location_data_success() -> None:
    """Successful response sets site_id, site_name and site_found."""
    payload = SIM.get_sites_by_location(TEST_LAT, TEST_LON)
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON, session=MockClientSession([MockResponse(payload)]))  # pyright: ignore[reportArgumentType]
    await c.get_location_data()
    assert c.site_found is True
    assert c.site_id != ""
    assert c.site_name != ""


@pytest.mark.asyncio
async def test_get_location_data_key_error() -> None:
    """Missing keys in response."""
    # Record is missing siteID and siteName, KeyError during processing
    c = Collector(
        api_key=TEST_API_KEY_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=MockClientSession([MockResponse({"records": [{}]})]),  # pyright: ignore[reportArgumentType]
    )
    await c.get_location_data()
    assert c.site_found is False


@pytest.mark.asyncio
async def test_get_location_data_non_200() -> None:
    """A non-200 response leaves site_found unchanged."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON, session=MockClientSession([MockResponse({}, status=403)]))  # pyright: ignore[reportArgumentType]
    await c.get_location_data()
    assert c.site_found is False
    assert c.site_id == ""


@pytest.mark.asyncio
async def test_get_location_data_zero_coords() -> None:
    """With coordinates (0,0) the request is skipped entirely."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=0, longitude=0)
    await c.get_location_data()
    assert c.site_found is False


@pytest.mark.asyncio
async def test_get_locations_list_success() -> None:
    """Successful response populates locations_list and sets sites_found=True."""
    payload = SIM.get_sites_list()
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON, session=MockClientSession([MockResponse(payload)]))  # pyright: ignore[reportArgumentType]
    await c.get_locations_list()
    assert c.sites_found is True
    assert len(c.locations_list) > 0
    site_ids = [loc["value"] for loc in c.locations_list]
    assert "10004" not in site_ids


@pytest.mark.asyncio
async def test_get_locations_list_records_none() -> None:
    """A response with records=None still sets sites_found=True but leaves the list empty."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=MockClientSession([MockResponse({"records": None})]),  # pyright: ignore[reportArgumentType]
    )
    await c.get_locations_list()
    # sites_found is set to True after the sorted-list assignment even when records is None
    assert c.sites_found is True
    assert c.locations_list == []


@pytest.mark.asyncio
async def test_get_locations_list_key_error() -> None:
    """A record missing required keys triggers KeyError handling and sites_found=False."""
    # Missing siteType etc. = KeyError during processing
    c = Collector(
        api_key=TEST_API_KEY_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=MockClientSession([MockResponse({"records": [{"siteID": "X"}]})]),  # pyright: ignore[reportArgumentType]
    )
    await c.get_locations_list()
    assert c.sites_found is False


@pytest.mark.asyncio
async def test_get_locations_list_non_200() -> None:
    """A non-200 response leaves sites_found=False."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON, session=MockClientSession([MockResponse({}, status=403)]))  # pyright: ignore[reportArgumentType]
    await c.get_locations_list()
    assert c.sites_found is False


@pytest.mark.asyncio
async def test_get_locations_list_zero_coords() -> None:
    """With coordinates (0,0) the request is skipped entirely."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=0, longitude=0)
    await c.get_locations_list()
    assert c.sites_found is False


@pytest.mark.asyncio
async def test_get_locations_list_site_without_health_parameter() -> None:
    """Sites whose siteHealthAdvices entry has no healthParameter are excluded."""
    payload = {
        "records": [
            {
                "siteID": "99001",
                "siteName": "No Health Param Site",
                "siteType": "Standard",
                "geometry": {"coordinates": [-37.82, 144.97]},
                "siteHealthAdvices": [{}],  # Missing healthParameter
            }
        ]
    }
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON, session=MockClientSession([MockResponse(payload)]))  # pyright: ignore[reportArgumentType]
    await c.get_locations_list()
    assert c.sites_found is True
    assert len(c.locations_list) == 0  # Site excluded but no error


def test_getters_site_not_found() -> None:
    """Return zero/empty defaults when site has not been resolved."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    assert c.valid_location() is False
    assert c.valid_location_list() is False
    assert c.get_location() == ""
    assert c.get_location_list() == []
    assert c.get_aqi() == 0
    assert c.get_aqi_24h() == 0
    assert c.get_aqi_pm25() == ""
    assert c.get_aqi_pm25_24h() == ""
    assert c.get_confidence() == 0
    assert c.get_confidence_24h() == 0
    assert c.get_data_source() == ""
    assert c.get_pm25() == 0
    assert c.get_pm25_24h() == 0
    assert c.get_total_sample() == 0
    assert c.get_total_sample_24h() == 0
    assert c.get_until() == ""
    assert c.get_sensor("anything") is None


def test_get_sensor_attributes_no_site() -> None:
    """When the site is not found, sensor attributes are empty."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    assert c.get_sensor_attributes("anything") == {}


def test_log_api_readings_summary_none(caplog: pytest.LogCaptureFixture) -> None:
    """An empty summary logs the explicit none message."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)

    with caplog.at_level("DEBUG"):
        c._log_api_readings_summary([])

    assert "API readings summary: none" in caplog.text


def test_log_api_readings_summary_debug_disabled(caplog: pytest.LogCaptureFixture) -> None:
    """When DEBUG is disabled, summary logging exits immediately."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)

    with patch(
        "homeassistant.components.epa_victoria_air_quality.collector._LOGGER.isEnabledFor",
        return_value=False,
    ):
        c._log_api_readings_summary(
            [
                {
                    "name": NAME_PM10,
                    "timeSeriesReadings": [
                        {
                            "timeSeriesName": "1HR_AV",
                            "readings": [{"averageValue": 1.0}],
                        }
                    ],
                }
            ]
        )

    assert "API readings summary" not in caplog.text


def test_log_api_readings_summary_skips_bad(caplog: pytest.LogCaptureFixture) -> None:
    """Odd log payloads are skipped."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)

    with caplog.at_level("DEBUG"):
        c._log_api_readings_summary(
            [
                {"name": NAME_PM10, "timeSeriesReadings": "bad"},
                {"name": NAME_PM10, "timeSeriesReadings": [None]},
                {"name": NAME_PM10, "timeSeriesReadings": [{"timeSeriesName": "bad", "readings": [{"averageValue": 1.0}]}]},
                {"name": NAME_PM10, "timeSeriesReadings": [{"timeSeriesName": "1HR_AV", "readings": []}]},
                {"name": NAME_PM10, "timeSeriesReadings": [{"timeSeriesName": "1HR_AV", "readings": [None]}]},
            ]
        )

    assert "API readings summary: none" in caplog.text


def test_calculate_aqi_unsupported_series_none() -> None:
    """Unsupported pollutant/time-series pairs skip AQI conversion."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    assert c._calculate_aqi("NO2", "24HR_AV", 1.0) is None


def test_set_observation_rounds_measurement_values() -> None:
    """Stored float sensor values are rounded to stable precision."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)

    c._set_observation("so2", 0.7411000000000001, {})

    assert c.observation_data["so2"] == 0.7411


def test_set_overall_aqi_rounds_value() -> None:
    """Overall AQI values are rounded before being stored."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    c.sensor_attributes["pm10_aqi_value"] = {}

    c._set_overall_aqi("1HR_AV", [("pm10_aqi_value", NAME_PM10, 42.1234)])

    assert c.observation_data[TYPE_AQI_OVERALL] == 42.123


def test_collect_pollutant_readings_skips_bad() -> None:
    """Odd parameter payloads are ignored without raising."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)

    readings = c._collect_pollutant_readings(
        [
            {
                "name": "Not supported",
                "timeSeriesReadings": [{"timeSeriesName": "1HR_AV", "readings": [{"averageValue": 1.0}]}],
            },
            {
                "name": "PM10",
                "timeSeriesReadings": [None],
            },
            {
                "name": "PM10",
                "timeSeriesReadings": [{"timeSeriesName": "1HR_AV", "readings": []}],
            },
            {
                "name": "PM10",
                "timeSeriesReadings": [{"timeSeriesName": "1HR_AV", "readings": [None]}],
            },
        ]
    )

    assert readings == {}


def test_getters_site_found() -> None:
    """Return populated values when site has been resolved."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.sites_found = True
    c.site_name = "Melbourne CBD"
    c.aqi = 42.0
    c.aqi_24h = 38.0
    c.aqi_pm25 = "Good"
    c.aqi_pm25_24h = "Good"
    c.confidence = 0.95
    c.confidence_24h = 0.98
    c.data_source_1h = "1HR_AV"
    c.pm25 = 8.5
    c.pm25_24h = 7.5
    c.total_sample = 12.0
    c.total_sample_24h = 288.0
    c.until = "2024-01-01T12:00:00"
    c.observation_data = {TYPE_AQI: 42.0}

    assert c.valid_location() is True
    assert c.valid_location_list() is True
    assert c.get_location() == TEST_SITE_ID_1
    assert c.get_location_list() == c.locations_list
    assert c.get_aqi() == 42.0
    assert c.get_aqi_24h() == 38.0
    assert c.get_aqi_pm25() == "Good"
    assert c.get_aqi_pm25_24h() == "Good"
    assert c.get_confidence() == 0.95
    assert c.get_confidence_24h() == 0.98
    assert c.get_data_source() == "1HR_AV"
    assert c.get_pm25() == 8.5
    assert c.get_pm25_24h() == 7.5
    assert c.get_total_sample() == 12.0
    assert c.get_total_sample_24h() == 288.0
    assert c.get_until() == "2024-01-01T12:00:00"
    assert c.get_sensor(TYPE_AQI) == 42.0


def test_get_sensor_key_error() -> None:
    """Return fallback string when observation_data.get raises KeyError."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    mock_data = MagicMock()
    mock_data.get.side_effect = KeyError("missing")
    c.observation_data = mock_data
    result = c.get_sensor("some_key")
    assert result == "Sensor %s Not Found!"


def test_calculate_aqi_handles_index_error() -> None:
    """An IndexError from the AQI library is treated as missing AQI data."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )

    with patch(
        "homeassistant.components.epa_victoria_air_quality.collector.aqi.to_aqi",
        side_effect=IndexError("out of range"),
    ):
        assert c._calculate_aqi("O3", "1HR_AV", 14.0) is None


@pytest.mark.asyncio
async def test_extract_observation_data_normal() -> None:
    """Normal 1HR_AV+24HR_AV data with positive confidence is extracted correctly."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.observations_data = SIM.get_site_parameters(TEST_SITE_ID_1)  # pyright: ignore[reportAttributeAccessIssue]
    await c.extract_observation_data()

    assert c.aqi > 0
    assert c.aqi_24h > 0
    assert c.pm25 > 0
    assert c.pm25_24h > 0  # pyright: ignore[reportOptionalOperand]
    assert c.confidence == 0.95
    assert c.confidence_24h == 0.98
    assert c.data_source_1h == "1HR_AV"
    assert c.observation_data[TYPE_AQI] == c.aqi


@pytest.mark.asyncio
async def test_extract_observation_data_1h_zero_confidence() -> None:
    """When 1HR_AV has zero confidence/samples, 24HR_AV values are used for 1h fields."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.observations_data = {
        "parameters": [
            {
                "timeSeriesReadings": [
                    {
                        "timeSeriesName": "1HR_AV",
                        "readings": [
                            {
                                "averageValue": 5.0,
                                "healthAdvice": "Good",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0,
                                "totalSample": 0,
                            }
                        ],
                    },
                    {
                        "timeSeriesName": "24HR_AV",
                        "readings": [
                            {
                                "averageValue": 7.5,
                                "healthAdvice": "Good",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0.98,
                                "totalSample": 288.0,
                            }
                        ],
                    },
                ]
            }
        ]
    }
    await c.extract_observation_data()

    # 24HR_AV should be used as fallback for 1H fields
    assert c.pm25 == 7.5
    assert c.data_source_1h == "24HR_AV"


@pytest.mark.asyncio
async def test_extract_observation_data_24h_none_value() -> None:
    """A missing 24HR_AV PM2.5 value does not raise and leaves AQI at its default."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.observations_data = {
        "parameters": [
            {
                "timeSeriesReadings": [
                    {
                        "timeSeriesName": "1HR_AV",
                        "readings": [
                            {
                                "averageValue": 5.0,
                                "healthAdvice": "Good",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0.95,
                                "totalSample": 12.0,
                            }
                        ],
                    },
                    {
                        "timeSeriesName": "24HR_AV",
                        "readings": [
                            {
                                "averageValue": None,
                                "healthAdvice": "Unknown",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0.98,
                                "totalSample": 288.0,
                            }
                        ],
                    },
                ]
            }
        ]
    }

    await c.extract_observation_data()

    assert c.pm25 == 5.0
    assert c.aqi > 0
    assert c.pm25_24h is None
    assert c.aqi_24h == 0
    assert c.data_source_1h == "1HR_AV"


@pytest.mark.asyncio
async def test_extract_observation_data_unknown_value_treated_as_missing() -> None:
    """Literal 'Unknown' reading values are treated as missing data."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.observations_data = {
        "parameters": [
            {
                "name": "PM10",
                "timeSeriesReadings": [
                    {
                        "timeSeriesName": "1HR_AV",
                        "readings": [
                            {
                                "averageValue": "Unknown",
                                "healthAdvice": "Unknown",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0,
                                "totalSample": 0,
                            }
                        ],
                    }
                ],
            }
        ]
    }

    await c.extract_observation_data()

    assert c.get_sensor("pm10") is None
    assert c.get_sensor("pm10_advice") is None
    assert "pm10" not in c.get_available_sensor_keys()
    assert "pm10_advice" not in c.get_available_sensor_keys()


@pytest.mark.asyncio
async def test_extract_observation_data_logs_api_readings_summary(caplog: pytest.LogCaptureFixture) -> None:
    """Raw API readings are logged as a single DEBUG summary line."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.site_name = "Test Site"
    c.observations_data = {
        "parameters": [
            {
                "name": "PM10",
                "timeSeriesReadings": [
                    {
                        "timeSeriesName": "1HR_AV",
                        "readings": [
                            {
                                "averageValue": "Unknown",
                                "healthAdvice": "Unknown",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0,
                                "totalSample": 0,
                            }
                        ],
                    }
                ],
            }
        ]
    }

    with caplog.at_level("DEBUG"):
        await c.extract_observation_data()

    assert "Test Site API readings summary:" in caplog.text
    assert "PM10/1HR_AV:avg='Unknown'" in caplog.text


@pytest.mark.asyncio
async def test_extract_observation_data_no_valid_readings_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """When PARAMETERS present but pm25_24h is None and confidence is zero, a warning is logged once."""
    null_readings = {
        "parameters": [
            {
                "timeSeriesReadings": [
                    {
                        "timeSeriesName": "1HR_AV",
                        "readings": [
                            {
                                "averageValue": None,
                                "healthAdvice": "Unknown",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0,
                                "totalSample": 0,
                            }
                        ],
                    },
                    {
                        "timeSeriesName": "24HR_AV",
                        "readings": [
                            {
                                "averageValue": None,
                                "healthAdvice": "Unknown",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0,
                                "totalSample": 0,
                            }
                        ],
                    },
                ]
            }
        ]
    }
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.site_name = "Test Site"

    # First call: warning logged and flag set
    c.observations_data = null_readings
    await c.extract_observation_data()
    assert c._unavailable_logged is True
    assert "no valid readings" in caplog.text

    caplog.clear()

    # Second call: flag already set, no duplicate warning
    c.observations_data = null_readings
    await c.extract_observation_data()
    assert "no valid readings" not in caplog.text


@pytest.mark.asyncio
async def test_extract_observation_data_recovery_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    """After a no-valid-readings warning, a successful parse logs a recovery message."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.site_name = "Test Site"
    c._unavailable_logged = True  # Simulate a prior warning having been logged

    c.observations_data = SIM.get_site_parameters(TEST_SITE_ID_1)  # pyright: ignore[reportAttributeAccessIssue]
    await c.extract_observation_data()

    assert c._unavailable_logged is False
    assert "available again" in caplog.text


@pytest.mark.asyncio
async def test_extract_observation_data_no_parameters() -> None:
    """When no parameters block is present, observation_data remains empty but no error is raised."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.observations_data = {}
    await c.extract_observation_data()
    assert c.observation_data == {}


@pytest.mark.asyncio
async def test_extract_observation_data_overall_primary() -> None:
    """Overall AQI source sets the primary AQI directly from the overall candidate."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        aqi_source=AQI_SOURCE_OVERALL,
    )
    c.observations_data = {
        "parameters": [
            {
                "name": NAME_PM10,
                "timeSeriesReadings": [
                    {
                        "timeSeriesName": "1HR_AV",
                        "readings": [
                            {
                                "averageValue": 9.0,
                                "healthAdvice": "Good",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0.95,
                                "totalSample": 12.0,
                            }
                        ],
                    },
                    {
                        "timeSeriesName": "24HR_AV",
                        "readings": [
                            {
                                "averageValue": 10.0,
                                "healthAdvice": "Good",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0.98,
                                "totalSample": 288.0,
                            }
                        ],
                    },
                ],
            }
        ]
    }

    await c.extract_observation_data()

    assert c.observation_data[TYPE_AQI] == c.observation_data[TYPE_AQI_OVERALL]
    assert c.observation_data[TYPE_AQI] > 0


@pytest.mark.asyncio
async def test_extract_observation_data_overall_fallback_primary() -> None:
    """When the overall AQI exists but the primary AQI does not, the fallback path copies it over."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.observations_data = {
        "parameters": [
            {
                "name": NAME_PM10,
                "timeSeriesReadings": [
                    {
                        "timeSeriesName": "1HR_AV",
                        "readings": [
                            {
                                "averageValue": 9.0,
                                "healthAdvice": "Good",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0.95,
                                "totalSample": 12.0,
                            }
                        ],
                    },
                    {
                        "timeSeriesName": "24HR_AV",
                        "readings": [
                            {
                                "averageValue": 10.0,
                                "healthAdvice": "Good",
                                "until": "2024-01-01T12:00:00",
                                "confidence": 0.98,
                                "totalSample": 288.0,
                            }
                        ],
                    },
                ],
            }
        ]
    }

    await c.extract_observation_data()

    assert TYPE_AQI_OVERALL in c.observation_data
    assert TYPE_AQI in c.observation_data
    assert c.observation_data[TYPE_AQI] == c.observation_data[TYPE_AQI_OVERALL]


@pytest.mark.asyncio
async def test_extract_observation_data_parameter_no_time_series() -> None:
    """Parameter dict without timeSeriesReadings is skipped without error."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.aqi_pm25_24h = ""  # aqi_pm25_24h is declared but never assigned in __init__
    c.observations_data = {"parameters": [{}]}  # No timeSeriesReadings key
    await c.extract_observation_data()
    # observation_data dict is built (parameters block entered) even with no readings
    assert isinstance(c.observation_data, dict)
    assert c.last_updated is not None


@pytest.mark.asyncio
async def test_update_success() -> None:
    """Successful update populates aqi and observation_data."""
    params = SIM.get_site_parameters(TEST_SITE_ID_1)
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=MockClientSession([MockResponse(params)]),  # pyright: ignore[reportArgumentType]
    )
    await c.async_update()
    assert c.aqi > 0


@pytest.mark.asyncio
async def test_update_location_data_none() -> None:
    """When location_data is None, get_location_data() is called before the parameters fetch."""
    location_payload = SIM.get_sites_by_location(TEST_LAT, TEST_LON)
    params_payload = SIM.get_site_parameters(TEST_SITE_ID_1)

    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        # Both calls share the same session; location lookup is first, then parameters.
        session=MockClientSession([MockResponse(location_payload), MockResponse(params_payload)]),  # pyright: ignore[reportArgumentType]
    )
    c.location_data = None  # pyright: ignore[reportAttributeAccessIssue] # Force the inner get_location_data() branch
    await c.async_update()

    assert c.observations_data != {}


@pytest.mark.asyncio
async def test_update_connection_refused() -> None:
    """ConnectionRefusedError inside async_update is logged and swallowed."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=ErrorClientSession(ConnectionRefusedError("refused")),  # pyright: ignore[reportArgumentType]
    )
    await c.async_update()  # Must not raise


@pytest.mark.asyncio
async def test_update_exception() -> None:
    """Unexpected exception inside async_update is logged and swallowed."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=ErrorClientSession(RuntimeError("unexpected")),  # pyright: ignore[reportArgumentType]
    )
    await c.async_update()  # Must not raise


@pytest.mark.asyncio
async def test_setup_calls_get_locations_list() -> None:
    """async_setup calls get_locations_list when the list is empty."""
    payload = SIM.get_sites_list()
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON, session=MockClientSession([MockResponse(payload)]))  # pyright: ignore[reportArgumentType]
    await c.async_setup()
    assert c.sites_found is True


@pytest.mark.asyncio
async def test_setup_skips_when_already_populated() -> None:
    """async_setup does not fetch again when locations_list is already populated."""
    session = MagicMock()
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON, session=session)
    c.locations_list = [{"value": TEST_SITE_ID_1, "label": "Melbourne CBD"}]
    await c.async_setup()
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_setup_connection_refused() -> None:
    """ConnectionRefusedError inside async_setup is logged and swallowed."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=ErrorClientSession(ConnectionRefusedError("refused")),  # pyright: ignore[reportArgumentType]
    )
    await c.async_setup()  # Must not raise


@pytest.mark.asyncio
async def test_setup_exception() -> None:
    """Unexpected exception inside async_setup is logged and swallowed."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON, session=ErrorClientSession(RuntimeError("unexpected")))  # pyright: ignore[reportArgumentType]
    await c.async_setup()  # Must not raise


class GatewayErrorResponse:
    """Mock aiohttp response that simulates a 5xx gateway error returning HTML."""

    def __init__(self, status: int = 504) -> None:
        """Initialise with the error status code."""
        self.status = status

    async def json(self) -> Any:
        """Raise ContentTypeError as a real 504 HTML response would."""
        raise ContentTypeError(
            RequestInfo(url="https://example.com", method="GET", headers={}, real_url="https://example.com"),  # type: ignore[arg-type]
            history=(),
            status=self.status,
            message="Attempt to decode JSON with unexpected mimetype: text/html",
        )

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the async context manager."""


class GatewayErrorClientSession:
    """Mock session whose get() returns a 5xx gateway error response."""

    def __init__(self, status: int = 504) -> None:
        """Initialise with the HTTP status code to return."""
        self._status = status

    def get(self, url: str, **kwargs: Any) -> GatewayErrorResponse:
        """Return a gateway error response."""
        return GatewayErrorResponse(self._status)


@pytest.mark.asyncio
async def test_update_5xx_logs_clean_warning_not_traceback(caplog: pytest.LogCaptureFixture) -> None:
    """A 5xx response logs a friendly warning without a traceback."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=GatewayErrorClientSession(504),  # pyright: ignore[reportArgumentType]
    )
    c.site_name = "Box Hill"

    await c.async_update()

    assert c._unavailable_logged is True
    assert "HTTP 504" in caplog.text
    assert "transient" in caplog.text
    # Must not log a raw Python traceback.
    assert "Traceback" not in caplog.text
    assert "ContentTypeError" not in caplog.text


@pytest.mark.asyncio
async def test_update_5xx_logs_once_then_suppresses(caplog: pytest.LogCaptureFixture) -> None:
    """Repeated 5xx responses only log the warning on the first failure."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=GatewayErrorClientSession(503),  # pyright: ignore[reportArgumentType]
    )
    c.site_name = "Melbourne CBD"

    await c.async_update()
    caplog.clear()
    # Second call: bypass throttle with no_throttle=True.
    await c.async_update(no_throttle=True)

    # Warning must NOT appear a second time.
    assert "HTTP 503" not in caplog.text


@pytest.mark.asyncio
async def test_update_5xx_recovery_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    """After a 5xx warning, a subsequent successful response logs a recovery message."""
    params = SIM.get_site_parameters(TEST_SITE_ID_1)

    # First call: 504 gateway error.
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=GatewayErrorClientSession(504),  # pyright: ignore[reportArgumentType]
    )
    c.site_name = "Box Hill"
    await c.async_update()
    assert c._unavailable_logged is True

    # Second call: successful response — swap the session.
    c._session = MockClientSession([MockResponse(params)])  # pyright: ignore[reportAttributeAccessIssue, reportArgumentType]
    caplog.clear()
    await c.async_update(no_throttle=True)

    assert c._unavailable_logged is False
    assert "available again" in caplog.text


@pytest.mark.asyncio
async def test_update_client_response_error_logs_clean_warning(caplog: pytest.LogCaptureFixture) -> None:
    """A ClientResponseError from the session is caught and logged without a traceback."""

    def _make_client_response_error(status: int) -> ClientResponseError:
        return ClientResponseError(
            RequestInfo(url="https://example.com", method="GET", headers={}, real_url="https://example.com"),  # type: ignore[arg-type]
            history=(),
            status=status,
        )

    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
        session=ErrorClientSession(_make_client_response_error(502)),  # pyright: ignore[reportArgumentType]
    )
    c.site_name = "Box Hill"
    await c.async_update()

    assert c._unavailable_logged is True
    assert "HTTP error 502" in caplog.text
    assert "Traceback" not in caplog.text
