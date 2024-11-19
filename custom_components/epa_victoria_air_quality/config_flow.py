"""Config flow for EPA Air Quality integration."""

from __future__ import annotations

from copy import deepcopy
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
from .const import CONF_SITE_ID, DOMAIN, TITLE

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
        config_entry: ConfigEntry,
    ) -> EPAVicOptionFlowHandler:
        """Get the options flow for this handler.

        Arguments:
            config_entry (ConfigEntry): The integration entry instance, contains the configuration.

        Returns:
            EPAVicOptionFlowHandler: The config flow handler instance.

        """
        return EPAVicOptionFlowHandler(config_entry)

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
                await self.collector.async_setup()
                if not self.collector.valid_location_list():
                    _LOGGER.debug("Unable to retrieve location list from EPA")
                    errors["base"] = "bad_api"
                else:
                    # Get the API Key
                    options = {
                        CONF_API_KEY: user_input[CONF_API_KEY],
                    }
                    return await self.async_step_location()

                options = {
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
        errors = {}

        if not self.collector.valid_location_list():
            await self.collector.async_setup()
            if not self.collector.valid_location_list():
                _LOGGER.debug("Unable to retrieve location list from EPA")
                errors["base"] = "bad_api"

        epa_locs: list[SelectOptionDict] = self.collector.get_location_list()

        if user_input is not None:
            try:
                # Create the collector object with the given parameters
                self.collector = Collector(
                    api_key=user_input[CONF_API_KEY],
                    latitude=self.hass.config.latitude,
                    longitude=self.hass.config.longitude,
                    epa_site_id=user_input[CONF_SITE_ID],
                )

                # Save the user input into self.data so it's retained
                self.data = user_input

                # Populate observations
                await self.collector.async_update()

                options = {
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
                        CONF_SITE_ID, default=self.collector.get_location()
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=epa_locs,
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="choose_site",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                CONF_API_KEY: "Enter your API key provided by EPA Victoria.",
                CONF_SITE_ID: "Enter your the EPA Victoria Site ID, or leave as is to determine from location.",
            },
        )


class EPAVicOptionFlowHandler(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input: dict | None = None) -> Any:
        """Initialise main dialogue step.

        Arguments:
            user_input (dict, optional): The input provided by the user. Defaults to None.

        Returns:
            Any: Either an error, or the configuration dialogue results.

        """

        _options = deepcopy(dict(self.config_entry.options))
        errors = {}
        api_key = _options.get(CONF_API_KEY)
        latitude = _options.get(CONF_LATITUDE)
        longitude = _options.get(CONF_LONGITUDE)
        try:
            site_id = _options.get(CONF_SITE_ID)
        except KeyError:
            site_id = "Determine from Location"

        collector: Collector = Collector(
            api_key=api_key, latitude=latitude, longitude=longitude
        )
        await collector.async_setup()
        if not collector.valid_location_list():
            _LOGGER.debug("Unable to retrieve location list from EPA")
            errors["base"] = "bad_api"

        epa_locs: list[SelectOptionDict] = collector.get_location_list()

        if user_input is not None:
            all_config_data = {**_options}

            site_id = user_input[CONF_SITE_ID]
            all_config_data[CONF_SITE_ID] = site_id

            api_key = user_input[CONF_API_KEY].replace(" ", "")
            all_config_data[CONF_API_KEY] = api_key

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=TITLE,
                options=all_config_data,
            )

            self.data = user_input

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                title=TITLE,
                options=all_config_data,
            )
            await collector.async_update()

            return self.async_create_entry(title=TITLE, data=None)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY, default=api_key): str,
                    vol.Required(CONF_SITE_ID, default=site_id): SelectSelector(
                        SelectSelectorConfig(
                            options=epa_locs,
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="choose_site",
                        )
                    ),
                }
            ),
            errors=errors,
        )
