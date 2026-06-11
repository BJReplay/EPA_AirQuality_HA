"""Tests for the EPA Victoria Air Quality __init__.py."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp.client_exceptions import ClientConnectorError
import pytest

from homeassistant import loader
from homeassistant.components.epa_victoria_air_quality import (
    async_migrate_entry,
    async_remove_config_entry_device,
    async_update_options,
    get_version,
)
from homeassistant.components.epa_victoria_air_quality.collector import EPAAuthError
from homeassistant.components.epa_victoria_air_quality.const import (
    CONF_AQI_SOURCE,
    CONF_LEGACY_UNIQUE_IDS,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    DEFAULT_AQI_SOURCE,
    KNOWN_SITES,
    TITLE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import (
    TEST_API_KEY_1,
    TEST_API_KEY_2,
    TEST_SITE_ID_1,
    TEST_SITE_NAME_1,
    create_mock_config_entry,
)


@pytest.mark.asyncio
async def test_migrate_entry_version_1_to_4(hass: HomeAssistant) -> None:
    """Migrating a v1 entry moves config to options and sets defaults.

    Unknown site IDs should not force a title suffix during migration.
    """
    mock_entry = MagicMock()
    mock_entry.version = 1
    mock_entry.unique_id = None
    mock_entry.title = TITLE
    mock_entry.options = {}
    mock_entry.data = {CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1}

    with patch.object(hass.config_entries, "async_update_entry") as mock_update:
        result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["version"] == 5
    assert call_kwargs["unique_id"] == TEST_SITE_ID_1
    assert "title" not in call_kwargs
    assert call_kwargs["options"][CONF_SITE_ID] == TEST_SITE_ID_1
    assert call_kwargs["options"][CONF_API_KEY] == TEST_API_KEY_1
    assert call_kwargs["options"][CONF_LEGACY_UNIQUE_IDS] is True
    assert call_kwargs["options"][CONF_AQI_SOURCE] == DEFAULT_AQI_SOURCE


@pytest.mark.asyncio
async def test_migrate_entry_version_3_to_4(hass: HomeAssistant) -> None:
    """A version-3 entry is migrated to v4 with the default AQI source."""
    mock_entry = MagicMock()
    mock_entry.version = 3

    mock_entry.options = {}

    with patch.object(hass.config_entries, "async_update_entry") as mock_update:
        result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["version"] == 5
    assert call_kwargs["options"][CONF_AQI_SOURCE] == DEFAULT_AQI_SOURCE


@pytest.mark.asyncio
async def test_migrate_entry_pre_v3_options_known_site_sets_title(hass: HomeAssistant) -> None:
    """A pre-v3 entry with a known site ID gains site name and title during migration."""
    known_site_id, known_site_name = next(iter(KNOWN_SITES.items()))

    mock_entry = MagicMock()
    mock_entry.version = 2
    mock_entry.unique_id = None
    mock_entry.title = TITLE
    mock_entry.options = {CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: known_site_id}
    mock_entry.data = {}

    with patch.object(hass.config_entries, "async_update_entry") as mock_update:
        result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["version"] == 5
    assert call_kwargs["unique_id"] == known_site_id
    assert call_kwargs["title"] == f"{TITLE} - {known_site_name}"
    assert call_kwargs["options"][CONF_SITE_ID] == known_site_id
    assert call_kwargs["options"][CONF_SITE_NAME] == known_site_name
    assert call_kwargs["options"][CONF_API_KEY] == TEST_API_KEY_1
    assert call_kwargs["options"][CONF_LEGACY_UNIQUE_IDS] is True
    assert call_kwargs["options"][CONF_AQI_SOURCE] == DEFAULT_AQI_SOURCE


@pytest.mark.asyncio
async def test_migrate_entry_already_has_site_id(hass: HomeAssistant) -> None:
    """Migration skips the data→options copy when CONF_SITE_ID is already in options."""
    mock_entry = MagicMock()
    mock_entry.version = 1
    mock_entry.unique_id = TEST_SITE_ID_1
    mock_entry.title = f"{TITLE} - {TEST_SITE_ID_1}"
    mock_entry.options = {CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1}
    mock_entry.data = {}

    with patch.object(hass.config_entries, "async_update_entry") as mock_update:
        result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["version"] == 5
    # options is always updated during migration to set CONF_LEGACY_UNIQUE_IDS.
    assert call_kwargs["options"][CONF_LEGACY_UNIQUE_IDS] is True
    assert call_kwargs["options"][CONF_AQI_SOURCE] == DEFAULT_AQI_SOURCE
    # Existing CONF_SITE_ID must be preserved unchanged.
    assert call_kwargs["options"][CONF_SITE_ID] == TEST_SITE_ID_1


@pytest.mark.asyncio
async def test_migrate_entry_version_4_to_5_replaces_site_id_with_known_name(
    hass: HomeAssistant,
) -> None:
    """Migrating to v5 replaces known site IDs in title/entity names, keeping IDs stable."""
    known_site_id, known_site_name = next((site, name) for site, name in KNOWN_SITES.items() if " " in name)

    mock_entry = MagicMock()
    mock_entry.version = 4
    mock_entry.entry_id = "test_entry_id"
    mock_entry.title = f"{TITLE} - {known_site_id}"
    mock_entry.options = {
        CONF_API_KEY: TEST_API_KEY_1,
        CONF_SITE_ID: known_site_id,
        CONF_LEGACY_UNIQUE_IDS: True,
        CONF_AQI_SOURCE: DEFAULT_AQI_SOURCE,
    }

    mock_registry = MagicMock()
    migrated_entity = MagicMock()
    migrated_entity.entity_id = f"sensor.epa_air_quality_{known_site_id.replace('-', '_')}_hourly_so2_aqi"
    migrated_entity.name = "Hourly SO2 AQI"

    unaffected_entity = MagicMock()
    unaffected_entity.entity_id = "sensor.epa_air_quality_hourly_pm25"
    unaffected_entity.name = "Hourly PM25"

    with (
        patch.object(hass.config_entries, "async_update_entry") as mock_update,
        patch(
            "homeassistant.components.epa_victoria_air_quality.er.async_get",
            return_value=mock_registry,
        ),
        patch(
            "homeassistant.components.epa_victoria_air_quality.er.async_entries_for_config_entry",
            return_value=[migrated_entity, unaffected_entity],
        ),
    ):
        result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["version"] == 5
    assert call_kwargs["title"] == f"{TITLE} - {known_site_name}"
    mock_registry.async_update_entity.assert_any_call(
        migrated_entity.entity_id,
        new_entity_id=f"sensor.epa_air_quality_{known_site_name.replace(' ', '_').lower()}_hourly_so2_aqi",
    )


@pytest.mark.asyncio
async def test_setup_entry_client_connector_error(hass: HomeAssistant) -> None:
    """Entry enters SETUP_RETRY when collector.async_update raises ClientConnectorError."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with patch("homeassistant.components.epa_victoria_air_quality.Collector") as mock_cls:
        # First call: the main collector; second call: the lookup collector (skipped
        # because CONF_SITE_NAME is already in options on this entry).
        main_collector = mock_cls.return_value
        main_collector.async_update = AsyncMock(side_effect=ClientConnectorError(MagicMock(), OSError("connection error")))
        main_collector.async_setup = AsyncMock(return_value=None)
        await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state == ConfigEntryState.SETUP_RETRY


@pytest.mark.asyncio
async def test_setup_entry_sets_collector_site_name(hass: HomeAssistant) -> None:
    """Setup seeds the collector with the saved selected site name."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with patch("homeassistant.components.epa_victoria_air_quality.Collector") as mock_cls:
        main_collector = mock_cls.return_value
        main_collector.async_update = AsyncMock(return_value=None)
        main_collector.async_setup = AsyncMock(return_value=None)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert main_collector.site_name == TEST_SITE_NAME_1


@pytest.mark.asyncio
async def test_setup_does_not_duplicate_listener(hass: HomeAssistant) -> None:
    """Setup should not add duplicate async_update_options listeners."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)
    entry.update_listeners.append(async_update_options)

    with patch("homeassistant.components.epa_victoria_air_quality.Collector") as mock_cls:
        main_collector = mock_cls.return_value
        main_collector.async_update = AsyncMock(return_value=None)
        main_collector.async_setup = AsyncMock(return_value=None)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.update_listeners.count(async_update_options) == 1


@pytest.mark.asyncio
async def test_setup_auth_failure(hass: HomeAssistant) -> None:
    """Entry enters SETUP_ERROR when collector raises auth failure."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    with patch("homeassistant.components.epa_victoria_air_quality.Collector") as mock_cls:
        main_collector = mock_cls.return_value
        main_collector.async_update = AsyncMock(side_effect=EPAAuthError("bad key"))
        main_collector.async_setup = AsyncMock(return_value=None)

        await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state == ConfigEntryState.SETUP_ERROR


@pytest.mark.asyncio
async def test_setup_entry_resolves_site_name_for_migrated_entry(hass: HomeAssistant) -> None:
    """Setup resolves and stores a human-readable site name for entries that lack CONF_SITE_NAME."""
    # Simulate a migrated entry: options only have CONF_API_KEY and CONF_SITE_ID.
    entry = create_mock_config_entry(
        options={CONF_API_KEY: TEST_API_KEY_1, CONF_SITE_ID: TEST_SITE_ID_1},
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.epa_victoria_air_quality.Collector") as mock_cls:
        # First call returns the main collector; second returns the lookup collector.
        main_collector = MagicMock()
        main_collector.async_update = AsyncMock(return_value=None)
        main_collector.async_setup = AsyncMock(return_value=None)

        lookup_collector = MagicMock()
        lookup_collector.async_setup = AsyncMock(return_value=None)
        lookup_collector.get_location_list.return_value = [
            {"value": TEST_SITE_ID_1, "label": TEST_SITE_NAME_1},
        ]

        mock_cls.side_effect = [main_collector, lookup_collector]

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.options.get(CONF_SITE_NAME) == TEST_SITE_NAME_1
    assert entry.title == f"{TITLE} - {TEST_SITE_NAME_1}"


@pytest.mark.asyncio
async def test_get_version_integration_not_found(hass: HomeAssistant) -> None:
    """get_version returns empty string when the integration cannot be resolved."""
    with patch(
        "homeassistant.loader.async_get_integration",
        side_effect=loader.IntegrationNotFound("epa_victoria_air_quality"),
    ):
        version = await get_version(hass)

    assert version == ""


@pytest.mark.asyncio
async def test_remove_config_entry_device(hass: HomeAssistant) -> None:
    """async_remove_config_entry_device removes the device and returns True."""
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    mock_device = MagicMock()
    mock_device.id = "test-device-id"

    with patch("homeassistant.components.epa_victoria_air_quality.dr.async_get") as mock_dr_get:
        mock_registry = MagicMock()
        mock_dr_get.return_value = mock_registry

        result = await async_remove_config_entry_device(hass, entry, mock_device)

    assert result is True
    mock_registry.async_remove_device.assert_called_once_with("test-device-id")


@pytest.mark.asyncio
async def test_update_options_ignore_reload(hass: HomeAssistant) -> None:
    """Should skip reload when only metadata changes."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {
        CONF_API_KEY: TEST_API_KEY_1,
        CONF_SITE_ID: TEST_SITE_ID_1,
        CONF_AQI_SOURCE: DEFAULT_AQI_SOURCE,
    }

    collector = MagicMock()
    collector.api_key = TEST_API_KEY_1
    collector.site_id = TEST_SITE_ID_1
    collector.aqi_source = DEFAULT_AQI_SOURCE
    collector.latitude = 0
    collector.longitude = 0

    entry.runtime_data = MagicMock()
    entry.runtime_data.coordinator.collector = collector

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        await async_update_options(hass, entry)

    mock_reload.assert_not_called()


@pytest.mark.asyncio
async def test_update_options_reload(hass: HomeAssistant) -> None:
    """Should reload when significant options change."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {
        CONF_API_KEY: TEST_API_KEY_2,
        CONF_SITE_ID: TEST_SITE_ID_1,
        CONF_AQI_SOURCE: DEFAULT_AQI_SOURCE,
    }

    collector = MagicMock()
    collector.api_key = TEST_API_KEY_1
    collector.site_id = TEST_SITE_ID_1
    collector.aqi_source = DEFAULT_AQI_SOURCE
    collector.latitude = 0
    collector.longitude = 0

    entry.runtime_data = MagicMock()
    entry.runtime_data.coordinator.collector = collector

    with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
        await async_update_options(hass, entry)

    mock_reload.assert_awaited_once_with("test_entry")


@pytest.mark.asyncio
async def test_update_options_skip_reload_during_reauth(hass: HomeAssistant) -> None:
    """Should not reload from listener while a reauth flow is active."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {
        CONF_API_KEY: TEST_API_KEY_2,
        CONF_SITE_ID: TEST_SITE_ID_1,
        CONF_AQI_SOURCE: DEFAULT_AQI_SOURCE,
    }

    collector = MagicMock()
    collector.api_key = TEST_API_KEY_1
    collector.site_id = TEST_SITE_ID_1
    collector.aqi_source = DEFAULT_AQI_SOURCE
    collector.latitude = 0
    collector.longitude = 0

    entry.runtime_data = MagicMock()
    entry.runtime_data.coordinator.collector = collector

    with (
        patch.object(hass.config_entries.flow, "async_progress_by_handler", return_value=[MagicMock()]) as mock_progress,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        await async_update_options(hass, entry)

    assert mock_progress.call_args_list == [
        (("epa_victoria_air_quality",), {"match_context": {"source": "reauth"}}),
        (("epa_victoria_air_quality",), {"match_context": {"source": "reconfigure"}}),
    ]
    mock_reload.assert_not_called()


@pytest.mark.asyncio
async def test_update_options_skip_reload_reauth_for_other_instance(
    hass: HomeAssistant,
) -> None:
    """Should skip listener reload when any reauth flow is active for the domain."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {
        CONF_API_KEY: TEST_API_KEY_2,
        CONF_SITE_ID: TEST_SITE_ID_1,
        CONF_AQI_SOURCE: DEFAULT_AQI_SOURCE,
    }

    collector = MagicMock()
    collector.api_key = TEST_API_KEY_1
    collector.site_id = TEST_SITE_ID_1
    collector.aqi_source = DEFAULT_AQI_SOURCE
    collector.latitude = 0
    collector.longitude = 0

    entry.runtime_data = MagicMock()
    entry.runtime_data.coordinator.collector = collector

    active_flow_context = {"source": "reauth", "entry_id": "other_entry"}

    def _progress_by_handler(_domain: str, *, match_context: dict[str, str]):
        if match_context.items() <= active_flow_context.items():
            return [MagicMock()]
        return []

    with (
        patch.object(
            hass.config_entries.flow,
            "async_progress_by_handler",
            side_effect=_progress_by_handler,
        ) as mock_progress,
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload,
    ):
        await async_update_options(hass, entry)

    assert mock_progress.call_args_list == [
        (("epa_victoria_air_quality",), {"match_context": {"source": "reauth"}}),
        (("epa_victoria_air_quality",), {"match_context": {"source": "reconfigure"}}),
    ]
    mock_reload.assert_not_called()
