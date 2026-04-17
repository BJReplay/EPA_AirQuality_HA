"""Tests for the EPA Victoria Air Quality coordinator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.epa_victoria_air_quality.coordinator import (
    EPADataUpdateCoordinator,
)
from homeassistant.core import HomeAssistant

from . import create_mock_config_entry


def _make_coordinator(hass: HomeAssistant) -> EPADataUpdateCoordinator:
    """Create a coordinator with a mocked collector and config entry."""
    mock_collector = MagicMock()
    mock_collector.async_update = AsyncMock(return_value=None)
    mock_collector.async_setup = AsyncMock(return_value=None)
    entry = create_mock_config_entry()
    entry.add_to_hass(hass)
    coordinator = EPADataUpdateCoordinator(
        hass=hass,
        collector=mock_collector,
        version="1.0",
    )
    # Attach config_entry
    coordinator.config_entry = entry
    return coordinator


@pytest.mark.asyncio
async def test_coordinator_setup(hass: HomeAssistant) -> None:
    """setup() returns True."""
    coordinator = _make_coordinator(hass)
    result = await coordinator.setup()
    assert result is True


@pytest.mark.asyncio
async def test_entity_registry_updated_remove(hass: HomeAssistant) -> None:
    """entity_registry_updated triggers remove_empty_devices when action is 'remove'."""
    coordinator = _make_coordinator(hass)

    with patch.object(coordinator, "remove_empty_devices") as mock_remove:
        mock_event = MagicMock()
        mock_event.data = {"action": "remove"}
        coordinator.entity_registry_updated(mock_event)

    mock_remove.assert_called_once()


@pytest.mark.asyncio
async def test_entity_registry_updated_non_remove(hass: HomeAssistant) -> None:
    """entity_registry_updated does NOT trigger remove_empty_devices for other actions."""
    coordinator = _make_coordinator(hass)

    with patch.object(coordinator, "remove_empty_devices") as mock_remove:
        mock_event = MagicMock()
        mock_event.data = {"action": "update"}
        coordinator.entity_registry_updated(mock_event)

    mock_remove.assert_not_called()


@pytest.mark.asyncio
async def test_remove_empty_devices_removes_orphan(hass: HomeAssistant) -> None:
    """remove_empty_devices removes a device that has no associated entities."""
    coordinator = _make_coordinator(hass)

    mock_device = MagicMock()
    mock_device.id = "orphan-device-id"
    mock_device.name = "Orphan Device"

    with (
        patch("homeassistant.components.epa_victoria_air_quality.coordinator.er.async_get") as mock_er_get,
        patch("homeassistant.components.epa_victoria_air_quality.coordinator.dr.async_get") as mock_dr_get,
        patch(
            "homeassistant.components.epa_victoria_air_quality.coordinator.dr.async_entries_for_config_entry",
            return_value=[mock_device],
        ),
        patch(
            "homeassistant.components.epa_victoria_air_quality.coordinator.er.async_entries_for_device",
            return_value=[],  # No entities, device is orphaned
        ),
    ):
        mock_registry = MagicMock()
        mock_er_get.return_value = mock_registry
        mock_dr_registry = MagicMock()
        mock_dr_get.return_value = mock_dr_registry

        coordinator.remove_empty_devices()

    mock_dr_registry.async_update_device.assert_called_once_with(
        "orphan-device-id",
        remove_config_entry_id=coordinator.config_entry.entry_id,  # pyright: ignore[reportOptionalMemberAccess]
    )


@pytest.mark.asyncio
async def test_remove_empty_devices_keeps_device_with_entities(hass: HomeAssistant) -> None:
    """remove_empty_devices keeps a device that still has associated entities."""
    coordinator = _make_coordinator(hass)

    mock_device = MagicMock()
    mock_device.id = "active-device-id"

    with (
        patch("homeassistant.components.epa_victoria_air_quality.coordinator.er.async_get") as mock_er_get,
        patch("homeassistant.components.epa_victoria_air_quality.coordinator.dr.async_get") as mock_dr_get,
        patch(
            "homeassistant.components.epa_victoria_air_quality.coordinator.dr.async_entries_for_config_entry",
            return_value=[mock_device],
        ),
        patch(
            "homeassistant.components.epa_victoria_air_quality.coordinator.er.async_entries_for_device",
            return_value=[MagicMock()],  # One entity, device has entities, keep it
        ),
    ):
        mock_registry = MagicMock()
        mock_er_get.return_value = mock_registry
        mock_dr_registry = MagicMock()
        mock_dr_get.return_value = mock_dr_registry

        coordinator.remove_empty_devices()

    mock_dr_registry.async_update_device.assert_not_called()


@pytest.mark.asyncio
async def test_get_version_property(hass: HomeAssistant) -> None:
    """get_version returns the version string provided at construction time."""
    coordinator = _make_coordinator(hass)
    assert coordinator.get_version == "1.0"
