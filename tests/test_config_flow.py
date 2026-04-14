"""Tests for the EPA Victoria Air Quality config flow."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.epa_victoria_air_quality.config_flow import (
    EPAVicConfigFlow,
    EPAVicOptionFlowHandler,
)
from homeassistant.components.epa_victoria_air_quality.const import CONF_SITE_ID, DOMAIN
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from . import (
    TEST_API_KEY_1,
    TEST_API_KEY_2,
    TEST_SITE_ID_1,
    TEST_SITE_ID_2,
    create_mock_config_entry,
)


@pytest.mark.asyncio
async def test_full_user_flow(hass: HomeAssistant) -> None:
    """Test the full user config flow."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location_list.return_value = [{"value": TEST_SITE_ID_1, "label": "Test Site"}]
        mock_collector.get_location.return_value = TEST_SITE_ID_1
        mock_collector.async_update = AsyncMock(return_value=None)

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"

        # Submit API key
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"

        # Submit site selection
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1}
        )
        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result.get("title") == "EPA Air Quality"
        assert result.get("options") == {CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1}


@pytest.mark.asyncio
async def test_options_flow(hass: HomeAssistant) -> None:
    """Test the options flow."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location_list.return_value = [{"value": TEST_SITE_ID_2, "label": "Test Site 2"}]
        mock_collector.get_location.return_value = TEST_SITE_ID_2
        mock_collector.async_update = AsyncMock(return_value=None)

        mock_config_entry = create_mock_config_entry()
        mock_config_entry.add_to_hass(hass)
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"

        # Update API key
        result = await hass.config_entries.options.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_2})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"

        # Update site
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_2, CONF_SITE_ID: TEST_SITE_ID_2}
        )
        assert result.get("type") == FlowResultType.CREATE_ENTRY
        assert result.get("title") == "EPA Air Quality"
        assert result.get("data", {}).get(CONF_API_KEY) == TEST_API_KEY_2
        assert result.get("data", {}).get(CONF_SITE_ID) == TEST_SITE_ID_2


@pytest.mark.asyncio
async def test_user_flow_bad_api_key(hass: HomeAssistant) -> None:
    """Test config flow with an invalid API key (location list fails)."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = False
        mock_collector.get_location_list.return_value = []
        mock_collector.get_location.return_value = None

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"

        # Submit API key (invalid)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: "bad-key"})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"
        assert result.get("errors", {}).get("base") == "bad_api"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_user_flow_exception(hass: HomeAssistant) -> None:
    """Test config flow with an exception during Collector setup."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(side_effect=Exception("boom"))
        mock_collector.valid_location_list.return_value = False
        mock_collector.get_location_list.return_value = []
        mock_collector.get_location.return_value = None

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"

        # Submit API key (raises exception)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: "any-key"})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "user"
        assert result.get("errors", {}).get("base") == "unknown"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_location_flow_key_changed(hass: HomeAssistant) -> None:
    """Test location step with changed API key triggers key_changed error."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location_list.return_value = [{"value": TEST_SITE_ID_1, "label": "Test Site"}]
        mock_collector.get_location.return_value = TEST_SITE_ID_1
        mock_collector.async_update = AsyncMock(return_value=None)

        # Start flow and advance to location step
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("step_id") == "location"

        # Submit with a different API key
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: "DIFFERENT", CONF_SITE_ID: TEST_SITE_ID_1}
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"
        assert result.get("errors", {}).get("base") == "key_changed"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_location_flow_exception(hass: HomeAssistant) -> None:
    """Test location step with exception during update."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location_list.return_value = [{"value": TEST_SITE_ID_1, "label": "Test Site"}]
        mock_collector.get_location.return_value = TEST_SITE_ID_1
        mock_collector.async_update = AsyncMock(side_effect=Exception("fail"))

        # Start flow and advance to location step
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("step_id") == "location"

        # Submit with valid API key and site, but update fails
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1}
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"
        assert result.get("errors", {}).get("base") == "unknown"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_location_flow_collector_none_direct(hass: HomeAssistant) -> None:
    """Directly test location step when collector is None (should redirect to user step)."""
    flow: Any = EPAVicConfigFlow()
    flow.hass = hass
    flow.collector = None
    # Should call async_step_user and return its result (a form with step_id 'user')
    result = await flow.async_step_location(user_input=None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_location_flow_valid_location_list_becomes_false(hass: HomeAssistant) -> None:
    """Test location step re-validation when valid_location_list returns False on entry."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        # First call (user step): True → advance; next two calls (location step): False → bad_api
        mock_collector.valid_location_list.side_effect = [True, False, False]
        mock_collector.get_location_list.return_value = []
        mock_collector.get_location.return_value = None

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"
        assert result.get("errors", {}).get("base") == "bad_api"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_options_flow_bad_api_key(hass: HomeAssistant) -> None:
    """Test options flow init with a bad API key."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = False

        mock_config_entry = create_mock_config_entry()
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"

        result = await hass.config_entries.options.async_configure(result["flow_id"], user_input={CONF_API_KEY: "bad-key"})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "init"
        assert result.get("errors", {}).get("base") == "bad_api"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_options_flow_location_collector_none_direct(hass: HomeAssistant) -> None:
    """Directly test options location step when _collector is None."""
    mock_config_entry = create_mock_config_entry()
    mock_config_entry.add_to_hass(hass)
    handler = EPAVicOptionFlowHandler(mock_config_entry)
    handler.hass = hass
    # _collector is None by default
    result = await handler.async_step_location(user_input=None)
    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "location"
    assert result.get("errors", {}).get("base") == "unknown"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_options_flow_location_key_changed(hass: HomeAssistant) -> None:
    """Test options flow location step with a changed API key."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location_list.return_value = [{"value": TEST_SITE_ID_1, "label": "Test Site"}]
        mock_collector.get_location.return_value = TEST_SITE_ID_1
        mock_collector.async_update = AsyncMock(return_value=None)

        mock_config_entry = create_mock_config_entry()
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("step_id") == "location"

        # Submit with a different API key
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: "DIFFERENT", CONF_SITE_ID: TEST_SITE_ID_1}
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"
        assert result.get("errors", {}).get("base") == "key_changed"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_options_flow_location_exception(hass: HomeAssistant) -> None:
    """Test options flow location step with exception during update."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location_list.return_value = [{"value": TEST_SITE_ID_1, "label": "Test Site"}]
        mock_collector.get_location.return_value = TEST_SITE_ID_1
        mock_collector.async_update = AsyncMock(return_value=None)

        mock_config_entry = create_mock_config_entry()
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
        result = await hass.config_entries.options.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("step_id") == "location"

        # Make the update raise an exception
        mock_collector.async_update = AsyncMock(side_effect=Exception("fail"))

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1}
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"
        assert result.get("errors", {}).get("base") == "unknown"  # pyright: ignore[reportOptionalMemberAccess]
