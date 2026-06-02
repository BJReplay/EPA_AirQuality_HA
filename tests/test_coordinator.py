"""Tests for the EPA Victoria Air Quality coordinator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.epa_victoria_air_quality.const import (
    CONF_LEGACY_UNIQUE_IDS,
    DOMAIN,
    TYPE_NO2,
    TYPE_O3,
)
from homeassistant.components.epa_victoria_air_quality.coordinator import (
    EPADataUpdateCoordinator,
)
from homeassistant.components.epa_victoria_air_quality.sensor import SENSORS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import TEST_SITE_ID_1, create_mock_config_entry


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


@pytest.mark.asyncio
async def test_auto_enable_without_config_entry(hass: HomeAssistant) -> None:
    """Auto-enable exits immediately when no config entry is attached."""
    coordinator = _make_coordinator(hass)
    coordinator.config_entry = None
    coordinator.collector.get_available_sensor_keys = MagicMock(return_value=[TYPE_NO2])
    coordinator._auto_enable_available_sensors()
    coordinator.collector.get_available_sensor_keys.assert_not_called()


@pytest.mark.asyncio
async def test_auto_enable_without_known_sensor_keys(hass: HomeAssistant) -> None:
    """Auto-enable exits when available keys do not map to known sensors."""
    coordinator = _make_coordinator(hass)
    assert coordinator.config_entry is not None

    registry = er.async_get(hass)
    no2_unique_id = f"epavic_epa_api_{TEST_SITE_ID_1}_{SENSORS[TYPE_NO2].name}"
    integration_disabled = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        no2_unique_id,
        config_entry=coordinator.config_entry,
        suggested_object_id="epa_vic_no2_unknown_key_guard",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )

    coordinator.collector.get_available_sensor_keys = MagicMock(return_value=["unknown_sensor_key"])
    coordinator._auto_enable_available_sensors()
    entry = registry.async_get(integration_disabled.entity_id)
    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_entity", [True, False])
async def test_async_update_data_auto_enables_available_sensor(hass: HomeAssistant, legacy_entity: bool) -> None:
    """Available sensors are auto-enabled if they were disabled by integration defaults."""
    coordinator = _make_coordinator(hass)
    assert coordinator.config_entry is not None
    options = dict(coordinator.config_entry.options)
    options[CONF_LEGACY_UNIQUE_IDS] = legacy_entity
    hass.config_entries.async_update_entry(coordinator.config_entry, options=options)

    coordinator.collector.get_available_sensor_keys = MagicMock(return_value=[])
    await coordinator._async_update_data()

    registry = er.async_get(hass)
    no2_unique_id = f"epavic_epa_api{('_' + TEST_SITE_ID_1) if not legacy_entity else ''}_{SENSORS[TYPE_NO2].name}"
    o3_unique_id = f"epavic_epa_api{('_' + TEST_SITE_ID_1) if not legacy_entity else ''}_{SENSORS[TYPE_O3].name}"
    unrelated_unique_id = f"epavic_epa_api{('_' + TEST_SITE_ID_1) if not legacy_entity else ''}_unrelated"

    _ = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        unrelated_unique_id,
        config_entry=coordinator.config_entry,
        suggested_object_id="epa_vic_unrelated",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )
    enabled_candidate = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        no2_unique_id,
        config_entry=coordinator.config_entry,
        suggested_object_id="epa_vic_no2",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )
    user_disabled = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        o3_unique_id,
        config_entry=coordinator.config_entry,
        suggested_object_id="epa_vic_o3",
        disabled_by=er.RegistryEntryDisabler.USER,
    )

    coordinator.collector.get_available_sensor_keys = MagicMock(return_value=[TYPE_NO2, TYPE_O3])

    await coordinator._async_update_data()

    enabled_entry = registry.async_get(enabled_candidate.entity_id)
    assert enabled_entry is not None
    user_disabled_entry = registry.async_get(user_disabled.entity_id)
    assert user_disabled_entry is not None

    assert enabled_entry.disabled_by is None
    assert user_disabled_entry.disabled_by is er.RegistryEntryDisabler.USER
