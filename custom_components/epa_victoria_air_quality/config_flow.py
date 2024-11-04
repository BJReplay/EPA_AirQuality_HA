"""Config flow for EPA Air Quality integration."""

# pylint: disable=C0301, C0304, E0401, W0702, W0703

from __future__ import annotations
from typing import Optional, Any

import logging
from datetime import timezone
from dataclasses import dataclass


import voluptuous as vol # type: ignore
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow # type: ignore
from homeassistant.const import ( # type: ignore
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_API_KEY,
)

from homeassistant.core import callback # type: ignore
from homeassistant.data_entry_flow import FlowResult # type: ignore
from homeassistant import config_entries # type: ignore

from .const import (
    DOMAIN,
    TITLE,
)

from .collector import Collector

_LOGGER = logging.getLogger(__name__)

@config_entries.HANDLERS.register(DOMAIN)
class EPAVicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise the options flow."""
        self.config_entry = config_entry
        self.data = {}
        self.collector = Collector

    @staticmethod
    @callback
    def async_get_options_flow(
        entry: ConfigEntry,
    ) -> EPAVicOptionFlowHandler:
        """Get the options flow for this handler.

        Arguments:
            entry (ConfigEntry): The integration entry instance, contains the configuration.

        Returns:
            EPAVicOptionFlowHandler: The config flow handler instance.
        """
        return EPAVicOptionFlowHandler(entry)

    async def async_step_user(
            self, user_input: Optional[dict[str, Any]]=None
    ) -> FlowResult:
        """Handle a flow initiated by the user.

        Arguments:
            user_input (dict[str, Any] | None, optional): The config submitted by a user. Defaults to None.

        Returns:
            FlowResult: The form to show.
        """

        errors = {}

        if user_input is not None:

            try:
                # Create the collector object with the given long. and lat.
                self.collector = Collector(
                    user_input[CONF_LATITUDE],
                    user_input[CONF_LONGITUDE],
                    user_input[CONF_API_KEY],
                    ConnectionOptions.trimmed_version,
                )

                # Save the user input into self.data so it's retained
                self.data = user_input

                # Check if location is valid
                await self.collector.get_locations_data(self)
                if not self.collector.valid_location(self):
                    _LOGGER.debug("Unsupported Latitude/Longitude")
                    errors["base"] = "bad_location"
                else:
                    # Populate observations
                    await self.collector.async_update(self)

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            return self.async_create_entry(
                title= TITLE,
                data = {},
                options={
                    CONF_LATITUDE: user_input[CONF_LATITUDE],
                    CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                    CONF_API_KEY: user_input[CONF_API_KEY],
                }
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): float,
                vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): float,
                vol.Required(CONF_API_KEY, default=""): str,
            }),
            errors=errors,
            description_placeholders={
                CONF_LATITUDE: "Enter the Latitude for the location you want to monitor.",
                CONF_LONGITUDE: "Enter the Longitude for the location you want to monitor.",
                CONF_API_KEY: "Enter your API key provided by EPA Victoria.",
            }
        )

class EPAVicOptionFlowHandler(OptionsFlow):
    """Handle options."""

    def __init__(self, entry: ConfigEntry):
        """Initialize options flow.

        Arguments:
            entry (ConfigEntry): The integration entry instance, contains the configuration.
        """
        self.config_entry = entry
        self.options = dict(self.config_entry.options)

    async def async_step_init(self, user_input: dict=None) -> Any:
        """Initialise main dialogue step.

        Arguments:
            user_input (dict, optional): The input provided by the user. Defaults to None.

        Returns:
            Any: Either an error, or the configuration dialogue results.
        """

        errors = {}
        api_key = self.config_entry.options.get(CONF_API_KEY)
        site_lat = self.config_entry.options.get(CONF_LATITUDE)
        site_lon = self.config_entry.options.get(CONF_LONGITUDE)

        if user_input is not None:
            try:
                all_config_data = {**self.config_entry.options}

                api_key = user_input[CONF_API_KEY].replace(" ","")
                all_config_data[CONF_API_KEY] = api_key

                site_lat = user_input[CONF_LATITUDE].replace(" ","")
                all_config_data[CONF_LATITUDE] = site_lat

                site_lon = user_input[CONF_LONGITUDE].replace(" ","")
                all_config_data[CONF_LONGITUDE] = site_lon

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=TITLE,
                    options=all_config_data,
                )

                return self.async_create_entry(title=TITLE, data=None)
            except Exception as e:
                errors["base"] = str(e)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY, default=api_key): str,
                    vol.Required(CONF_LATITUDE, default=site_lat): float,
                    vol.Required(CONF_LONGITUDE, default=site_lon): float,
                }
            ),
            errors=errors
        )


@dataclass
class ConnectionOptions:
    """EPA options for the integration."""
    api_key: str
    site_id: str
    host: str
    latitude: float
    longitude: float
    tz: timezone
    trimmed_version: str