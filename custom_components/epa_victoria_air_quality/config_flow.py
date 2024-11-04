"""Config flow for EPA Air Quality integration."""

# pylint: disable=C0301, C0304, E0401, W0702, W0703

from __future__ import annotations
from typing import Optional, Any

import voluptuous as vol # type: ignore

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow # type: ignore
from homeassistant.const import CONF_API_KEY # type: ignore
from homeassistant.core import callback # type: ignore
from homeassistant.data_entry_flow import FlowResult # type: ignore
from homeassistant import config_entries # type: ignore

from .const import (
    CONF_SITE_ID,
    DOMAIN,
    TITLE,
)

@config_entries.HANDLERS.register(DOMAIN)
class EPAVicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

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
            return self.async_create_entry(
                title= TITLE,
                data = {},
                options={
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    CONF_SITE_ID: user_input[CONF_SITE_ID]
                }
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY, default=""): str,
                vol.Required(CONF_SITE_ID, default=""): str,
            }),
            errors=errors,
            description_placeholders={
                CONF_API_KEY: "Enter your API key provided by EPA Victoria.",
                CONF_SITE_ID: "Enter the Site ID for the location you want to monitor."
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
        site_id = self.config_entry.options.get(CONF_SITE_ID)

        if user_input is not None:
            try:
                all_config_data = {**self.config_entry.options}

                api_key = user_input[CONF_API_KEY].replace(" ","")
                all_config_data[CONF_API_KEY] = api_key

                site_id = user_input[CONF_SITE_ID].replace(" ","")
                all_config_data[CONF_SITE_ID] = site_id

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
                    vol.Required(CONF_SITE_ID, default=site_id): str,
                }
            ),
            errors=errors
        )
