"""Tests setup for EPA Victoria Air Quality integration."""

import copy
from typing import Any

from homeassistant.components.epa_victoria_air_quality.const import (
    CONF_AQI_SOURCE,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    DEFAULT_AQI_SOURCE,
    DOMAIN,
)
from homeassistant.const import CONF_API_KEY

from tests.common import MockConfigEntry

# Example valid test API keys and sites (from simulator)
TEST_API_KEY_1 = "test-key-1"
TEST_API_KEY_2 = "test-key-2"
TEST_SITE_ID_1 = "10001"
TEST_SITE_ID_2 = "10002"
TEST_SITE_NAME_1 = "Test Site 1"
TEST_SITE_NAME_2 = "Test Site 2"

DEFAULT_OPTIONS = {
    CONF_API_KEY: TEST_API_KEY_1,
    CONF_SITE_ID: TEST_SITE_ID_1,
    CONF_SITE_NAME: TEST_SITE_NAME_1,
    CONF_AQI_SOURCE: DEFAULT_AQI_SOURCE,
}


def create_mock_config_entry(
    data: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    **kwargs: Any,
) -> MockConfigEntry:
    """Create a mock config entry for EPA Victoria Air Quality.

    Defaults to the v4 format: config stored in options, empty data.
    Pass explicit ``data`` / ``options`` to test migration scenarios.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        data=data if data is not None else {},
        options=options if options is not None else copy.deepcopy(DEFAULT_OPTIONS),
        unique_id=TEST_SITE_ID_1,
        title=f"EPA Air Quality - {TEST_SITE_NAME_1}",
        version=4,
        **kwargs,
    )
