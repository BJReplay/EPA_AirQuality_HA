"""Config flow for EPA Air Quality integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .collector import Collector
from .const import CONF_SITE_ID, DOMAIN, SITE_ID, SITE_NAME, TITLE

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class EPAVicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    def __init__(self) -> None:
        """Initialise the config flow."""
        self.data = {}
        self.collector: Collector = None

    VERSION = 2

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
        self, user_input: dict[str, Any] | None = None
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
                # Create the collector object with the given parameters
                self.collector = Collector(
                    api_key=user_input[CONF_API_KEY],
                    latitude=self.hass.config.latitude,
                    longitude=self.hass.config.longitude,
                )

                # Save the user input into self.data so it's retained
                self.data = user_input

                # Check if location is valid
                await self.collector.get_location_data()
                await self.collector.async_setup()
                if not self.collector.valid_location_list():
                    _LOGGER.debug("Unable to retrieve location list from EPA")
                    errors["base"] = "bad_api"
                else:
                    # Move onto the next step of the config flow
                    options = {
                        CONF_API_KEY: user_input[CONF_API_KEY],
                    }
                    return await self.async_step_location()

                options = {
                    CONF_LATITUDE: self.hass.config.latitude,
                    CONF_LONGITUDE: self.hass.config.longitude,
                    CONF_API_KEY: user_input[CONF_API_KEY],
                }

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            return self.async_create_entry(
                title=TITLE,
                data={},
                options=options,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY, default=""): str,
                }
            ),
            errors=errors,
            description_placeholders={
                CONF_API_KEY: "Enter your API key provided by EPA Victoria.",
            },
        )

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initiated by the user.

        Arguments:
            user_input (dict[str, Any] | None, optional): The config submitted by a user. Defaults to None.

        Returns:
            FlowResult: The form to show.

        """

        locations: list[SelectOptionDict]
        errors = {}

        if not self.collector.valid_location_list():
            await self.collector.async_setup()
            if not self.collector.valid_location_list():
                _LOGGER.debug("Unable to retrieve location list from EPA")
                errors["base"] = "bad_api"

        locations: list[SelectOptionDict] = [
            SelectOptionDict(label=location[SITE_NAME], value=location[SITE_ID])
            for location in self.collector.get_location_list()
        ]

        if user_input is not None:
            try:
                # Create the collector object with the given parameters
                self.collector = Collector(
                    api_key=user_input[CONF_API_KEY],
                    latitude=user_input[CONF_LATITUDE],
                    longitude=user_input[CONF_LONGITUDE],
                    epa_site_id=user_input[CONF_SITE_ID],
                )

                # Save the user input into self.data so it's retained
                self.data = user_input

                # Check if location is valid
                await self.collector.get_location_data()
                if not self.collector.valid_location():
                    _LOGGER.debug("Unsupported Latitude/Longitude")
                    errors["base"] = "bad_location"
                else:
                    # Populate observations
                    await self.collector.async_update()

                options = {
                    CONF_LATITUDE: user_input[CONF_LATITUDE],
                    CONF_LONGITUDE: user_input[CONF_LONGITUDE],
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_SITE_ID: user_input[CONF_SITE_ID],
                }

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

            return self.async_create_entry(
                title=TITLE,
                data={},
                options=options,
            )

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_KEY, default=self.data.get(CONF_API_KEY)
                    ): str,
                    vol.Required(
                        CONF_LATITUDE, default=self.hass.config.latitude
                    ): float,
                    vol.Required(
                        CONF_LONGITUDE, default=self.hass.config.longitude
                    ): float,
                    #                    vol.Optional(CONF_SITE_ID, default="Determine from Location"): str,
                    vol.Required(
                        CONF_SITE_ID, default=self.collector.get_location()
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=locations,
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="choose_site",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                CONF_API_KEY: "Enter your API key provided by EPA Victoria.",
                CONF_LATITUDE: "Enter the Latitude for the location you want to monitor.",
                CONF_LONGITUDE: "Enter the Longitude for the location you want to monitor.",
                CONF_SITE_ID: "Enter your the EPA Victoria Site ID, or leave as is to determine from location.",
            },
        )


class EPAVicOptionFlowHandler(OptionsFlow):
    """Handle options."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize options flow.

        Arguments:
            entry (ConfigEntry): The integration entry instance, contains the configuration.

        """
        self._entry = entry
        self._options = entry.options
        self.data = {}
        self.collector: Collector = Collector(
            api_key=self._options.get(CONF_API_KEY),
            latitude=self._options.get(CONF_LATITUDE),
            longitude=self._options.get(CONF_LONGITUDE),
        )

    async def async_step_init(self, user_input: dict | None = None) -> Any:
        """Initialise main dialogue step.

        Arguments:
            user_input (dict, optional): The input provided by the user. Defaults to None.

        Returns:
            Any: Either an error, or the configuration dialogue results.

        """

        errors = {}
        api_key = self._options.get(CONF_API_KEY)
        site_lat = self._options.get(CONF_LATITUDE)
        site_lon = self._options.get(CONF_LONGITUDE)
        try:
            site_id = self._options.get(CONF_SITE_ID)
        except KeyError:
            site_id = "Determine from Location"

        if user_input is not None:
            all_config_data = {**self._options}

            all_config_data[CONF_SITE_ID] = site_id

            api_key = user_input[CONF_API_KEY].replace(" ", "")
            all_config_data[CONF_API_KEY] = api_key

            site_lat = user_input[CONF_LATITUDE]
            all_config_data[CONF_LATITUDE] = site_lat

            site_lon = user_input[CONF_LONGITUDE]
            all_config_data[CONF_LONGITUDE] = site_lon

            self.hass.config_entries.async_update_entry(
                self._entry,
                title=TITLE,
                options=all_config_data,
            )

            self.data = user_input

            # Check if location is valid
            await self.collector.get_location_data()
            if not self.collector.valid_location():
                _LOGGER.debug("Unsupported Latitude/Longitude")
                errors["base"] = "bad_location"
            else:
                # Populate observations
                site_id = self.collector.get_location()
                all_config_data[CONF_SITE_ID] = site_id
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    title=TITLE,
                    options=all_config_data,
                )
                if self.collector.valid_location:
                    await self.collector.async_update()

            return self.async_create_entry(title=TITLE, data=None)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY, default=api_key): str,
                    vol.Required(CONF_LATITUDE, default=site_lat): float,
                    vol.Required(CONF_LONGITUDE, default=site_lon): float,
                    vol.Optional(CONF_SITE_ID, default=site_id): str,
                }
            ),
            errors=errors,
        )
