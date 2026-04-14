"""Tests setup for EPA Victoria Air Quality integration."""

import copy
from typing import Any

from homeassistant.components.epa_victoria_air_quality.const import CONF_SITE_ID, DOMAIN
from homeassistant.const import CONF_API_KEY

from tests.common import MockConfigEntry

# Example valid test API keys and sites (from simulator)
TEST_API_KEY_1 = "test-key-1"
TEST_API_KEY_2 = "test-key-2"
TEST_SITE_ID_1 = "10001"
TEST_SITE_ID_2 = "10002"

DEFAULT_CONFIG = {
    CONF_API_KEY: TEST_API_KEY_1,
    CONF_SITE_ID: TEST_SITE_ID_1,
}


def create_mock_config_entry(data: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> MockConfigEntry:
    """Create a mock config entry for EPA Victoria Air Quality."""
    return MockConfigEntry(
        domain=DOMAIN,
        data=data or copy.deepcopy(DEFAULT_CONFIG),
        options=options or {},
        unique_id=f"{DEFAULT_CONFIG[CONF_API_KEY]}_{DEFAULT_CONFIG[CONF_SITE_ID]}",
        title="EPA Air Quality",
    )
