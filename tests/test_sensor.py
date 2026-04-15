"""Tests for the EPA Victoria Air Quality sensor platform."""

from datetime import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.epa_victoria_air_quality.const import (
    ATTR_CONFIDENCE,
    ATTR_DATA_SOURCE,
    CONF_LEGACY_UNIQUE_IDS,
    TYPE_AQI_PM25,
    TYPE_AQI_PM25_24H,
)
from homeassistant.components.epa_victoria_air_quality.coordinator import (
    EPADataUpdateCoordinator,
)
from homeassistant.components.epa_victoria_air_quality.sensor import (
    SENSORS,
    EPAQualitySensor,
)
from homeassistant.core import HomeAssistant

from . import DEFAULT_OPTIONS, TEST_SITE_ID_1, create_mock_config_entry


def _make_mock_collector(sensor_data: object = 8.5) -> MagicMock:
    """Return a mock Collector pre-loaded with sensible air quality data."""
    mock = MagicMock()
    mock.get_sensor.return_value = sensor_data
    mock.get_confidence.return_value = 0.95
    mock.get_confidence_24h.return_value = 0.98
    mock.get_total_sample.return_value = 12.0
    mock.get_total_sample_24h.return_value = 288.0
    mock.get_data_source.return_value = "1HR_AV"
    mock.until = "2024-01-01T12:00:00"
    mock.async_update = AsyncMock(return_value=None)
    return mock


def _make_sensor(
    hass: HomeAssistant,
    sensor_key: str = TYPE_AQI_PM25,
    sensor_data: object = "Good",
) -> tuple[EPAQualitySensor, MagicMock]:
    """Create an EPAQualitySensor with a mocked coordinator, without full HA setup."""
    mock_collector = _make_mock_collector(sensor_data)
    mock_coordinator = MagicMock(spec=EPADataUpdateCoordinator)
    mock_coordinator.hass = hass
    mock_coordinator.collector = mock_collector
    mock_coordinator.get_version = "1.0"
    mock_coordinator.async_add_listener = MagicMock(return_value=lambda: None)

    entry = create_mock_config_entry()
    entry.add_to_hass(hass)

    description = SENSORS[sensor_key]
    sensor = EPAQualitySensor(mock_coordinator, description, entry)
    sensor.hass = hass
    return sensor, mock_collector


async def _setup_integration(hass: HomeAssistant) -> MagicMock:
    """Set up the EPA integration with a mocked Collector and return the mock."""
    mock_collector_inst = _make_mock_collector()

    with patch(
        "homeassistant.components.epa_victoria_air_quality.Collector",
        return_value=mock_collector_inst,
    ):
        entry = create_mock_config_entry()
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return mock_collector_inst


@pytest.mark.asyncio
async def test_sensor_init_with_data(hass: HomeAssistant) -> None:
    """Sensor initialises as available when get_sensor returns a value."""
    sensor, _ = _make_sensor(hass, TYPE_AQI_PM25, sensor_data="Good")
    assert sensor._attr_available is True
    assert sensor._sensor_data == "Good"


@pytest.mark.asyncio
async def test_sensor_init_no_data(hass: HomeAssistant) -> None:
    """Sensor initialises as unavailable when get_sensor returns None."""
    sensor, _ = _make_sensor(hass, TYPE_AQI_PM25, sensor_data=None)
    assert sensor._attr_available is False
    assert sensor._sensor_data is None


@pytest.mark.asyncio
async def test_sensor_init_key_error(hass: HomeAssistant) -> None:
    """KeyError from get_sensor in __init__ is handled and sensor set unavailable."""
    mock_collector = _make_mock_collector()
    mock_collector.get_sensor.side_effect = KeyError("missing key")

    mock_coordinator = MagicMock(spec=EPADataUpdateCoordinator)
    mock_coordinator.hass = hass
    mock_coordinator.collector = mock_collector
    mock_coordinator.get_version = "1.0"
    mock_coordinator.async_add_listener = MagicMock(return_value=lambda: None)

    entry = create_mock_config_entry()
    entry.add_to_hass(hass)
    sensor = EPAQualitySensor(mock_coordinator, SENSORS[TYPE_AQI_PM25], entry)

    assert sensor._sensor_data is None
    assert sensor._attr_available is False


@pytest.mark.asyncio
async def test_sensor_name(hass: HomeAssistant) -> None:
    """The name property combines the entry title with the measurement description."""
    sensor, _ = _make_sensor(hass)
    assert sensor.name == f"{sensor._entry.title} {SENSORS[TYPE_AQI_PM25].name}"


@pytest.mark.asyncio
async def test_sensor_friendly_name(hass: HomeAssistant) -> None:
    """The friendly_name property mirrors the name property."""
    sensor, _ = _make_sensor(hass)
    assert sensor.friendly_name == sensor.name


@pytest.mark.asyncio
async def test_sensor_suggested_object_id(hass: HomeAssistant) -> None:
    """The suggested_object_id matches the original v1 format (no site_id).

    This preserves existing entity IDs like sensor.epa_air_quality_hourly_health_advice
    and gives _2, _3 suffixes to additional instances.
    """
    sensor, _ = _make_sensor(hass)
    assert sensor.suggested_object_id == f"epa_air_quality {SENSORS[TYPE_AQI_PM25].name}"


@pytest.mark.asyncio
async def test_sensor_unique_id(hass: HomeAssistant) -> None:
    """New config entries (no legacy flag) use the site-id-prefixed unique ID format."""
    sensor, _ = _make_sensor(hass)

    expected = f"epavic_epa_api_{TEST_SITE_ID_1}_{SENSORS[TYPE_AQI_PM25].name}"
    assert sensor.unique_id == expected


@pytest.mark.asyncio
async def test_sensor_unique_id_legacy(hass: HomeAssistant) -> None:
    """Migrated (legacy) entries preserve the upstream unique ID format to avoid orphaning entity registry entries."""

    legacy_options = {**DEFAULT_OPTIONS, CONF_LEGACY_UNIQUE_IDS: True}
    entry = create_mock_config_entry(options=legacy_options)
    entry.add_to_hass(hass)

    mock_collector = _make_mock_collector()
    mock_coordinator = MagicMock(spec=EPADataUpdateCoordinator)
    mock_coordinator.hass = hass
    mock_coordinator.collector = mock_collector
    mock_coordinator.get_version = "1.0"
    mock_coordinator.async_add_listener = MagicMock(return_value=lambda: None)

    sensor = EPAQualitySensor(mock_coordinator, SENSORS[TYPE_AQI_PM25], entry)
    expected = f"epavic_epa_api_{SENSORS[TYPE_AQI_PM25].name}"
    assert sensor.unique_id == expected


@pytest.mark.asyncio
async def test_sensor_should_poll_false(hass: HomeAssistant) -> None:
    """The should_poll property always returns False (coordinator-driven updates)."""
    sensor, _ = _make_sensor(hass)
    assert sensor.should_poll is False


@pytest.mark.asyncio
async def test_sensor_native_value(hass: HomeAssistant) -> None:
    """The native_value property returns the stored _sensor_data."""
    sensor, _ = _make_sensor(hass, TYPE_AQI_PM25, sensor_data="Good")
    assert sensor.native_value == "Good"


@pytest.mark.asyncio
async def test_sensor_state_non_24h(hass: HomeAssistant) -> None:
    """The state for a non-24h sensor populates 1h attributes."""
    sensor, _ = _make_sensor(hass, TYPE_AQI_PM25, sensor_data="Good")
    state = sensor.state
    assert state == "Good"
    assert ATTR_CONFIDENCE in sensor._attr_extra_state_attributes
    assert ATTR_DATA_SOURCE in sensor._attr_extra_state_attributes


@pytest.mark.asyncio
async def test_sensor_state_24h(hass: HomeAssistant) -> None:
    """The state for a 24h sensor populates 24h-specific attributes."""
    sensor, _ = _make_sensor(hass, TYPE_AQI_PM25_24H, sensor_data="Good")
    state = sensor.state
    assert state == "Good"
    assert ATTR_CONFIDENCE in sensor._attr_extra_state_attributes
    # 24h path should NOT have ATTR_DATA_SOURCE
    assert ATTR_DATA_SOURCE not in sensor._attr_extra_state_attributes


@pytest.mark.asyncio
async def test_sensor_state_datetime_value(hass: HomeAssistant) -> None:
    """The state returns an ISO format string when _sensor_data is a datetime."""
    sensor, _ = _make_sensor(hass, TYPE_AQI_PM25, sensor_data=dt(2024, 1, 1, 12, 0, 0))
    state = sensor.state
    assert state == "2024-01-01T12:00:00"


@pytest.mark.asyncio
async def test_handle_coordinator_update_with_data(hass: HomeAssistant) -> None:
    """_handle_coordinator_update sets available=True when data is present."""
    sensor, mock_collector = _make_sensor(hass, TYPE_AQI_PM25, sensor_data="Good")
    mock_collector.get_sensor.return_value = "Fair"
    sensor.async_write_ha_state = MagicMock()  # entity not registered; skip state write
    sensor._handle_coordinator_update()
    assert sensor._sensor_data == "Fair"
    assert sensor._attr_available is True


@pytest.mark.asyncio
async def test_handle_coordinator_update_no_data(hass: HomeAssistant) -> None:
    """_handle_coordinator_update sets available=False when data is None."""
    sensor, mock_collector = _make_sensor(hass, TYPE_AQI_PM25, sensor_data="Good")
    mock_collector.get_sensor.return_value = None
    sensor.async_write_ha_state = MagicMock()  # entity not registered; skip state write
    sensor._handle_coordinator_update()
    assert sensor._sensor_data is None
    assert sensor._attr_available is False


@pytest.mark.asyncio
async def test_handle_coordinator_update_key_error(hass: HomeAssistant) -> None:
    """The _handle_coordinator_update method handles KeyError from get_sensor gracefully."""
    sensor, mock_collector = _make_sensor(hass, TYPE_AQI_PM25, sensor_data="Good")
    mock_collector.get_sensor.side_effect = KeyError("gone")
    sensor.async_write_ha_state = MagicMock()  # entity not registered; skip state write
    sensor._handle_coordinator_update()
    assert sensor._sensor_data is None
    assert sensor._attr_available is False


@pytest.mark.asyncio
async def test_sensor_async_update(hass: HomeAssistant) -> None:
    """The async_update method delegates to the underlying collector."""
    sensor, mock_collector = _make_sensor(hass)
    await sensor.async_update()
    mock_collector.async_update.assert_called_once()


@pytest.mark.asyncio
async def test_async_added_to_hass_registers_listener(hass: HomeAssistant) -> None:
    """The async_added_to_hass method registers _handle_coordinator_update as a coordinator listener."""
    sensor, _ = _make_sensor(hass)
    await sensor.async_added_to_hass()
    sensor._coordinator.async_add_listener.assert_any_call(  # pyright: ignore[reportAttributeAccessIssue]
        sensor._handle_coordinator_update
    )
