"""Tests for the EPA Victoria Air Quality collector."""

import contextlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.components.epa_victoria_air_quality.collector import Collector
from homeassistant.components.epa_victoria_air_quality.const import TYPE_AQI

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

        async def _coro() -> "MockResponse":
            return self

        return _coro().__await__()

    async def __aenter__(self) -> "MockResponse":
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

    async def __aenter__(self) -> "MockClientSession":
        """Enter the async context manager."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the async context manager."""


@contextlib.contextmanager
def mock_sessions(*session_response_lists: list[MockResponse]):
    """Return mock sessions."""
    sessions = [MockClientSession(list(r)) for r in session_response_lists]
    call_idx = [0]

    def factory(*args: Any, **kwargs: Any) -> MockClientSession:
        idx = call_idx[0]
        result = sessions[min(idx, len(sessions) - 1)]
        call_idx[0] += 1
        return result

    with patch(
        "homeassistant.components.epa_victoria_air_quality.collector.aiohttp.ClientSession",
        side_effect=factory,
    ):
        yield


def mock_session(*responses: MockResponse):
    """Single session returning the given responses."""
    return mock_sessions(list(responses))


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
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with mock_session(MockResponse(payload)):
        await c.get_location_data()
    assert c.site_found is True
    assert c.site_id != ""
    assert c.site_name != ""


@pytest.mark.asyncio
async def test_get_location_data_key_error() -> None:
    """Missing keys in response."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    # Record is missing siteID and siteName, KeyError during processing
    with mock_session(MockResponse({"records": [{}]})):
        await c.get_location_data()
    assert c.site_found is False


@pytest.mark.asyncio
async def test_get_location_data_non_200() -> None:
    """A non-200 response leaves site_found unchanged."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with mock_session(MockResponse({}, status=403)):
        await c.get_location_data()
    assert c.site_found is False
    assert c.site_id == ""


@pytest.mark.asyncio
async def test_get_location_data_zero_coords() -> None:
    """With coordinates (0,0) the request is skipped entirely."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=0, longitude=0)
    with mock_session(MockResponse({})):
        await c.get_location_data()
    assert c.site_found is False


@pytest.mark.asyncio
async def test_get_locations_list_success() -> None:
    """Successful response populates locations_list and sets sites_found=True."""
    payload = SIM.get_sites_list()
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with mock_session(MockResponse(payload)):
        await c.get_locations_list()
    assert c.sites_found is True
    assert len(c.locations_list) > 0
    site_ids = [loc["value"] for loc in c.locations_list]
    assert "10004" not in site_ids


@pytest.mark.asyncio
async def test_get_locations_list_records_none() -> None:
    """A response with records=None still sets sites_found=True but leaves the list empty."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with mock_session(MockResponse({"records": None})):
        await c.get_locations_list()
    # sites_found is set to True after the sorted-list assignment even when records is None
    assert c.sites_found is True
    assert c.locations_list == []


@pytest.mark.asyncio
async def test_get_locations_list_key_error() -> None:
    """A record missing required keys triggers KeyError handling and sites_found=False."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    # Missing siteType etc. = KeyError during processing
    with mock_session(MockResponse({"records": [{"siteID": "X"}]})):
        await c.get_locations_list()
    assert c.sites_found is False


@pytest.mark.asyncio
async def test_get_locations_list_non_200() -> None:
    """A non-200 response leaves sites_found=False."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with mock_session(MockResponse({}, status=403)):
        await c.get_locations_list()
    assert c.sites_found is False


@pytest.mark.asyncio
async def test_get_locations_list_zero_coords() -> None:
    """With coordinates (0,0) the request is skipped entirely."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=0, longitude=0)
    with mock_session(MockResponse({})):
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
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with mock_session(MockResponse(payload)):
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
    assert c.pm25_24h > 0
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
async def test_extract_observation_data_no_parameters() -> None:
    """Empty observations_data leaves observation_data dict empty."""
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
async def test_async_update_success() -> None:
    """Successful update populates aqi and observation_data."""
    params = SIM.get_site_parameters(TEST_SITE_ID_1)
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    with mock_session(MockResponse(params)):
        await c.async_update()
    assert c.aqi > 0


@pytest.mark.asyncio
async def test_async_update_location_data_none() -> None:
    """When location_data is None, get_location_data() is called before the parameters fetch."""
    location_payload = SIM.get_sites_by_location(TEST_LAT, TEST_LON)
    params_payload = SIM.get_site_parameters(TEST_SITE_ID_1)

    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    c.location_data = None  # pyright: ignore[reportAttributeAccessIssue] # Force the inner get_location_data() branch

    # Session call order inside async_update:
    #   1st ClientSession() – outer session used for the parameters GET
    #   2nd ClientSession() – created inside get_location_data() for the find-site GET
    with mock_sessions(
        [MockResponse(params_payload)],  # outer session responses
        [MockResponse(location_payload)],  # get_location_data session responses
    ):
        await c.async_update()

    assert c.observations_data != {}


@pytest.mark.asyncio
async def test_async_update_connection_refused() -> None:
    """ConnectionRefusedError inside async_update is logged and swallowed."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    with patch(
        "homeassistant.components.epa_victoria_air_quality.collector.aiohttp.ClientSession",
        side_effect=ConnectionRefusedError("refused"),
    ):
        await c.async_update()  # Must not raise


@pytest.mark.asyncio
async def test_async_update_exception() -> None:
    """Unexpected exception inside async_update is logged and swallowed."""
    c = Collector(
        api_key=TEST_API_KEY_1,
        epa_site_id=TEST_SITE_ID_1,
        latitude=TEST_LAT,
        longitude=TEST_LON,
    )
    with patch(
        "homeassistant.components.epa_victoria_air_quality.collector.aiohttp.ClientSession",
        side_effect=RuntimeError("unexpected"),
    ):
        await c.async_update()  # Must not raise


@pytest.mark.asyncio
async def test_async_setup_calls_get_locations_list() -> None:
    """async_setup calls get_locations_list when the list is empty."""
    payload = SIM.get_sites_list()
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with mock_session(MockResponse(payload)):
        await c.async_setup()
    assert c.sites_found is True


@pytest.mark.asyncio
async def test_async_setup_skips_when_already_populated() -> None:
    """async_setup does not fetch again when locations_list is already populated."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    c.locations_list = [{"value": TEST_SITE_ID_1, "label": "Melbourne CBD"}]
    with patch("homeassistant.components.epa_victoria_air_quality.collector.aiohttp.ClientSession") as mock_cls:
        await c.async_setup()
    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_connection_refused() -> None:
    """ConnectionRefusedError inside async_setup is logged and swallowed."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with patch(
        "homeassistant.components.epa_victoria_air_quality.collector.aiohttp.ClientSession",
        side_effect=ConnectionRefusedError("refused"),
    ):
        await c.async_setup()  # Must not raise


@pytest.mark.asyncio
async def test_async_setup_exception() -> None:
    """Unexpected exception inside async_setup is logged and swallowed."""
    c = Collector(api_key=TEST_API_KEY_1, latitude=TEST_LAT, longitude=TEST_LON)
    with patch(
        "homeassistant.components.epa_victoria_air_quality.collector.aiohttp.ClientSession",
        side_effect=RuntimeError("unexpected"),
    ):
        await c.async_setup()  # Must not raise
