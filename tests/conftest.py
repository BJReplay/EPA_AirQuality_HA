"""Pytest fixtures for EPA Victoria Air Quality tests."""

import logging

import pytest


@pytest.fixture(autouse=True)
def enable_epa_victoria_air_quality_debug_logging(caplog: pytest.LogCaptureFixture) -> None:
    """Enable debug logging for test runs."""
    caplog.set_level(logging.DEBUG, logger="homeassistant.components.epa_victoria_air_quality")
