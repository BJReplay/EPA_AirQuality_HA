"""Tests for the EPA Victoria Air Quality config flow."""

from typing import Any
from unittest.mock import AsyncMock, call, patch

import pytest

from homeassistant.components.epa_victoria_air_quality.config_flow import (
    EPAVicConfigFlow,
)
from homeassistant.components.epa_victoria_air_quality.const import (
    AQI_SOURCE_OVERALL,
    AQI_SOURCE_PM25,
    CONF_AQI_SOURCE,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    DEFAULT_AQI_SOURCE,
    DOMAIN,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from . import (
    DEFAULT_OPTIONS,
    TEST_API_KEY_1,
    TEST_API_KEY_2,
    TEST_SITE_ID_1,
    TEST_SITE_ID_2,
    TEST_SITE_NAME_2,
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
        mock_collector.site_name = "Test Site"

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
        assert result.get("title") == "EPA Air Quality - Test Site"
        assert result.get("options") == {
            CONF_API_KEY: TEST_API_KEY_1,
            CONF_SITE_ID: TEST_SITE_ID_1,
            CONF_SITE_NAME: "Test Site",
            CONF_AQI_SOURCE: DEFAULT_AQI_SOURCE,
        }


@pytest.mark.asyncio
async def test_options_flow(hass: HomeAssistant) -> None:
    """Options flow exposes limited options and persists them."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "init"
    assert result["data_schema"]({})[CONF_AQI_SOURCE] == DEFAULT_AQI_SOURCE  # pyright: ignore[reportIndexIssue, reportTypedDictNotRequiredAccess, reportOptionalCall, reportOptionalSubscript]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_AQI_SOURCE: AQI_SOURCE_OVERALL},
    )
    assert result.get("type") == FlowResultType.CREATE_ENTRY
    assert result.get("data", {}).get(CONF_AQI_SOURCE) == AQI_SOURCE_OVERALL
    assert result.get("data", {}).get(CONF_API_KEY) == TEST_API_KEY_1
    assert result.get("data", {}).get(CONF_SITE_ID) == TEST_SITE_ID_1


@pytest.mark.asyncio
async def test_options_flow_default_uses_entry_value(hass: HomeAssistant) -> None:
    """Options flow defaults to the current values."""
    entry = create_mock_config_entry(options={**DEFAULT_OPTIONS, CONF_AQI_SOURCE: AQI_SOURCE_OVERALL})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "init"
    assert result["data_schema"]({})[CONF_AQI_SOURCE] == AQI_SOURCE_OVERALL  # pyright: ignore[reportIndexIssue, reportTypedDictNotRequiredAccess, reportOptionalCall, reportOptionalSubscript]


@pytest.mark.asyncio
async def test_options_flow_exception_returns_unknown(hass: HomeAssistant) -> None:
    """Options flow returns unknown error if updating the entry fails."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with patch.object(hass.config_entries, "async_update_entry", side_effect=Exception("fail")):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={CONF_AQI_SOURCE: AQI_SOURCE_PM25},
        )

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "init"
    assert result.get("errors", {}).get("base") == "unknown"  # pyright: ignore[reportOptionalMemberAccess]


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
async def test_location_flow_creates_entry(hass: HomeAssistant) -> None:
    """Test location step creates entry."""
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

        # Submit with valid API key and site.
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1}
        )
        assert result.get("type") == FlowResultType.CREATE_ENTRY


@pytest.mark.asyncio
async def test_location_flow_defaults_to_nearest_site(hass: HomeAssistant) -> None:
    """Location step defaults site selector to nearest listed site if collector location is empty."""
    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location.return_value = ""
        mock_collector.get_location_list.return_value = [
            {"value": TEST_SITE_ID_2, "label": "Nearest Site"},
            {"value": TEST_SITE_ID_1, "label": "Second Nearest Site"},
        ]

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "location"
    assert result["data_schema"]({})[CONF_SITE_ID] == TEST_SITE_ID_2  # pyright: ignore[reportTypedDictNotRequiredAccess, reportIndexIssue, reportOptionalCall, reportOptionalSubscript]


@pytest.mark.asyncio
async def test_location_flow_exception(hass: HomeAssistant) -> None:
    """Test location step handles unexpected exceptions."""
    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch(
            "homeassistant.components.epa_victoria_air_quality.config_flow.EPAVicConfigFlow.async_set_unique_id",
            new=AsyncMock(side_effect=Exception("fail")),
        ),
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location_list.return_value = [{"value": TEST_SITE_ID_1, "label": "Test Site"}]
        mock_collector.get_location.return_value = TEST_SITE_ID_1

        # Start flow and advance to location step
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("step_id") == "location"

        # Submit with valid API key and site, but force an internal exception.
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
        # First call (user step): True = advance; then location step: False = bad_api
        mock_collector.valid_location_list.side_effect = [True, False, False]
        mock_collector.get_location_list.return_value = []
        mock_collector.get_location.return_value = None

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"
        assert result.get("errors", {}).get("base") == "bad_api"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_user_flow_duplicate_location_rejected(hass: HomeAssistant) -> None:
    """Config flow location step rejects a site already configured in another entry."""
    existing_entry = create_mock_config_entry()
    existing_entry.add_to_hass(hass)

    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True
        mock_collector.get_location_list.return_value = [{"value": TEST_SITE_ID_1, "label": "Test Site"}]
        mock_collector.get_location.return_value = TEST_SITE_ID_1
        mock_collector.async_update = AsyncMock(return_value=None)

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1})
        assert result.get("step_id") == "location"

        # Select the already-configured site
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1}
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "location"
        assert result.get("errors", {}).get("base") == "already_configured_location"  # pyright: ignore[reportOptionalMemberAccess]
        # Confirm no API call was made for the duplicate
        mock_collector.async_update.assert_not_called()


@pytest.mark.asyncio
async def test_reauth_updates_all_having_same_key(hass: HomeAssistant) -> None:
    """Reauth updates API key for every entry sharing the previous key."""
    entry_1 = create_mock_config_entry()
    entry_1.add_to_hass(hass)

    entry_2 = create_mock_config_entry(
        options={
            **DEFAULT_OPTIONS,
            CONF_SITE_ID: TEST_SITE_ID_2,
            CONF_SITE_NAME: TEST_SITE_NAME_2,
        }
    )
    entry_2.add_to_hass(hass)

    unrelated = create_mock_config_entry(
        options={
            **DEFAULT_OPTIONS,
            CONF_API_KEY: TEST_API_KEY_2,
            CONF_SITE_ID: "10003",
            CONF_SITE_NAME: "Test Site 3",
        }
    )
    unrelated.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry_1.entry_id},
            data=entry_1.options,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "new-shared-key"},
        )
        assert result.get("type") == FlowResultType.ABORT
        assert result.get("reason") == "reauth_successful"

    updated_1 = hass.config_entries.async_get_entry(entry_1.entry_id)
    updated_2 = hass.config_entries.async_get_entry(entry_2.entry_id)
    updated_3 = hass.config_entries.async_get_entry(unrelated.entry_id)

    assert updated_1 is not None
    assert updated_2 is not None
    assert updated_3 is not None
    assert updated_1.options[CONF_API_KEY] == "new-shared-key"
    assert updated_2.options[CONF_API_KEY] == "new-shared-key"
    assert updated_3.options[CONF_API_KEY] == TEST_API_KEY_2
    assert mock_reload.await_args_list == [call(entry_1.entry_id), call(entry_2.entry_id)]


@pytest.mark.asyncio
async def test_reauth_aborts_in_progress(hass: HomeAssistant) -> None:
    """Reauth flow aborts if another reauth flow is active."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries.flow,
        "async_progress_by_handler",
        return_value=[
            {
                "flow_id": "another-flow",
                "context": {"source": "reauth"},
            }
        ],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.options,
        )

    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "reauth_already_in_progress"


@pytest.mark.asyncio
async def test_reauth_confirm_bad_api(hass: HomeAssistant) -> None:
    """Reauth confirm keeps form open with bad_api when key validation fails."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = False

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.options,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "bad-key"},
        )

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "reauth_confirm"
    assert result.get("errors", {}).get("base") == "bad_api"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_reauth_with_empty_previous_key(hass: HomeAssistant) -> None:
    """Reauth falls back to the reauth entry options key when entry data lacks API key."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        # No CONF_API_KEY in incoming reauth data.
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data={},
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "new-key"},
        )

    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "reauth_successful"
    mock_reload.assert_awaited_once_with(entry.entry_id)
    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    assert updated_entry.options[CONF_API_KEY] == "new-key"


@pytest.mark.asyncio
async def test_entries_with_api_key_empt(hass: HomeAssistant) -> None:
    """Helper returns an empty list when asked with a blank API key."""
    flow: Any = EPAVicConfigFlow()
    flow.hass = hass

    assert flow._entries_with_api_key("   ") == []


@pytest.mark.asyncio
async def test_reauth_with_non_matching_previous_key(hass: HomeAssistant) -> None:
    """Reauth falls back to the reauth entry when the previous key matches no entries."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        # Previous key does not match any entry, so fallback branch is used.
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data={CONF_API_KEY: "missing-old-key"},
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "another-new-key"},
        )

    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "reauth_successful"
    mock_reload.assert_awaited_once_with(entry.entry_id)
    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    assert updated_entry.options[CONF_API_KEY] == "another-new-key"


@pytest.mark.asyncio
async def test_reauth_reload_once(hass: HomeAssistant) -> None:
    """Reauth performs one explicit reload even if listeners are present."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    # Simulate an already loaded entry that has an update listener registered.
    entry.update_listeners.append(AsyncMock(return_value=None))

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.options,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "single-reload-key"},
        )
        assert result.get("type") == FlowResultType.ABORT
        assert result.get("reason") == "reauth_successful"
        await hass.async_block_till_done()

    mock_reload.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_reconfigure_updates_all_having_same_key(hass: HomeAssistant) -> None:
    """Reconfigure updates API key for every entry sharing the previous key."""
    entry_1 = create_mock_config_entry()
    entry_1.add_to_hass(hass)

    entry_2 = create_mock_config_entry(
        options={
            **DEFAULT_OPTIONS,
            CONF_SITE_ID: TEST_SITE_ID_2,
            CONF_SITE_NAME: TEST_SITE_NAME_2,
        }
    )
    entry_2.add_to_hass(hass)

    unrelated = create_mock_config_entry(
        options={
            **DEFAULT_OPTIONS,
            CONF_API_KEY: TEST_API_KEY_2,
            CONF_SITE_ID: "10003",
            CONF_SITE_NAME: "Test Site 3",
        }
    )
    unrelated.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry_1.entry_id},
            data=entry_1.options,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reconfigure_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "new-shared-key"},
        )
        assert result.get("type") == FlowResultType.ABORT
        assert result.get("reason") == "reconfigured"

    updated_1 = hass.config_entries.async_get_entry(entry_1.entry_id)
    updated_2 = hass.config_entries.async_get_entry(entry_2.entry_id)
    updated_3 = hass.config_entries.async_get_entry(unrelated.entry_id)

    assert updated_1 is not None
    assert updated_2 is not None
    assert updated_3 is not None
    assert updated_1.options[CONF_API_KEY] == "new-shared-key"
    assert updated_2.options[CONF_API_KEY] == "new-shared-key"
    assert updated_3.options[CONF_API_KEY] == TEST_API_KEY_2
    assert mock_reload.await_args_list == [call(entry_1.entry_id), call(entry_2.entry_id)]


@pytest.mark.asyncio
async def test_reconfigure_confirm_bad_api(hass: HomeAssistant) -> None:
    """Reconfigure confirm keeps form open with bad_api when key validation fails."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls:
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = False

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=entry.options,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reconfigure_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "bad-key"},
        )

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "reconfigure_confirm"
    assert result.get("errors", {}).get("base") == "bad_api"  # pyright: ignore[reportOptionalMemberAccess]


@pytest.mark.asyncio
async def test_reconfigure_confirm_defaults_to_current_api_key(hass: HomeAssistant) -> None:
    """Reconfigure confirm defaults the API key field to the current entry key."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
        data=entry.options,
    )

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "reconfigure_confirm"
    assert result["data_schema"]({})[CONF_API_KEY] == TEST_API_KEY_1  # pyright: ignore[reportIndexIssue, reportTypedDictNotRequiredAccess, reportOptionalCall, reportOptionalSubscript]
    assert result["data_schema"]({})["apply_to_all"] is True  # pyright: ignore[reportIndexIssue, reportTypedDictNotRequiredAccess, reportOptionalCall, reportOptionalSubscript]


@pytest.mark.asyncio
async def test_reconfigure_updates_current_when_apply_to_all_false(hass: HomeAssistant) -> None:
    """Reconfigure updates only the selected entry when apply_to_all is false."""
    entry_1 = create_mock_config_entry()
    entry_1.add_to_hass(hass)

    entry_2 = create_mock_config_entry(
        options={
            **DEFAULT_OPTIONS,
            CONF_SITE_ID: TEST_SITE_ID_2,
            CONF_SITE_NAME: TEST_SITE_NAME_2,
        }
    )
    entry_2.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry_1.entry_id},
            data=entry_1.options,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reconfigure_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "new-only-one-key", "apply_to_all": False},
        )
        assert result.get("type") == FlowResultType.ABORT
        assert result.get("reason") == "reconfigured"

    updated_1 = hass.config_entries.async_get_entry(entry_1.entry_id)
    updated_2 = hass.config_entries.async_get_entry(entry_2.entry_id)

    assert updated_1 is not None
    assert updated_2 is not None
    assert updated_1.options[CONF_API_KEY] == "new-only-one-key"
    assert updated_2.options[CONF_API_KEY] == TEST_API_KEY_1
    mock_reload.assert_awaited_once_with(entry_1.entry_id)


@pytest.mark.asyncio
async def test_reconfigure_with_empty_previous_key(hass: HomeAssistant) -> None:
    """Reconfigure falls back to the reconfigure entry key when entry data lacks API key."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        # No CONF_API_KEY in incoming reconfigure data.
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data={},
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reconfigure_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "new-key"},
        )

    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "reconfigured"
    mock_reload.assert_awaited_once_with(entry.entry_id)
    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    assert updated_entry.options[CONF_API_KEY] == "new-key"


@pytest.mark.asyncio
async def test_reconfigure_with_none_entry_data(hass: HomeAssistant) -> None:
    """Reconfigure handles None entry data by falling back to the entry options key."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=None,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reconfigure_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "new-key-from-none"},
        )

    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "reconfigured"
    mock_reload.assert_awaited_once_with(entry.entry_id)
    updated_entry = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated_entry is not None
    assert updated_entry.options[CONF_API_KEY] == "new-key-from-none"


@pytest.mark.asyncio
async def test_reconfigure_aborts_active_reauth_flow(hass: HomeAssistant) -> None:
    """Reconfigure aborts active reauth flow for matching entries."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()),
    ):
        mock_collector = mock_collector_cls.return_value
        mock_collector.async_setup = AsyncMock(return_value=None)
        mock_collector.valid_location_list.return_value = True

        reauth_result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.options,
        )
        assert reauth_result.get("type") == FlowResultType.FORM

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=entry.options,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reconfigure_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: "another-new-key"},
        )

    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "reconfigured"
    assert not hass.config_entries.flow.async_progress_by_handler(
        DOMAIN,
        match_context={"source": "reauth", "entry_id": entry.entry_id},
    )


@pytest.mark.asyncio
async def test_reconfigure_abort_when_key_unchanged(hass: HomeAssistant) -> None:
    """Reconfigure aborts early when submitted API key matches current key."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.epa_victoria_air_quality.config_flow.Collector", autospec=True) as mock_collector_cls,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data=entry.options,
        )
        assert result.get("type") == FlowResultType.FORM
        assert result.get("step_id") == "reconfigure_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_API_KEY: TEST_API_KEY_1},
        )

    assert result.get("type") == FlowResultType.ABORT
    assert result.get("reason") == "not_reconfigured"
    mock_collector_cls.assert_not_called()
    mock_reload.assert_not_awaited()
