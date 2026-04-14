"""Tests for the EPA Victoria Air Quality __init__.py."""

from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp.client_exceptions import ClientConnectorError
import pytest

from homeassistant import loader
from homeassistant.components.epa_victoria_air_quality import (
    async_migrate_entry,
    async_remove_config_entry_device,
    get_version,
)
from homeassistant.components.epa_victoria_air_quality.const import (
    CONF_SITE_ID,
    CONF_SITE_NAME,
    DOMAIN,
    TITLE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import TEST_API_KEY_1, TEST_SITE_ID_1, TEST_SITE_NAME_1, create_mock_config_entry


@pytest.mark.asyncio
async def test_async_migrate_entry_version_1_to_3(hass: HomeAssistant) -> None:
    """Migrating a v1 entry moves config to options, sets unique_id and title."""
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
    assert call_kwargs["version"] == 3
    assert call_kwargs["unique_id"] == TEST_SITE_ID_1
    assert call_kwargs["title"] == f"{TITLE} - {TEST_SITE_ID_1}"
    assert call_kwargs["options"][CONF_SITE_ID] == TEST_SITE_ID_1
    assert call_kwargs["options"][CONF_API_KEY] == TEST_API_KEY_1


@pytest.mark.asyncio
async def test_async_migrate_entry_version_3_unchanged(hass: HomeAssistant) -> None:
    """A version-3 entry is the current format and passes through unchanged."""
    mock_entry = MagicMock()
    mock_entry.version = 3

    with patch.object(hass.config_entries, "async_update_entry") as mock_update:
        result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_async_migrate_entry_options_already_has_site_id(hass: HomeAssistant) -> None:
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
    assert call_kwargs["version"] == 3
    # options must be unchanged — no second copy of CONF_SITE_ID from data.
    assert "options" not in call_kwargs


@pytest.mark.asyncio
async def test_async_setup_entry_client_connector_error(hass: HomeAssistant) -> None:
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
async def test_async_setup_entry_resolves_site_name_for_migrated_entry(hass: HomeAssistant) -> None:
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
async def test_async_remove_config_entry_device(hass: HomeAssistant) -> None:
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
