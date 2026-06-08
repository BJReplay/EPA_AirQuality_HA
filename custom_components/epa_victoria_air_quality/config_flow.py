"""Config flow for EPA Air Quality integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .collector import Collector
from .const import (
    AQI_SOURCE_OVERALL,
    AQI_SOURCE_PM25,
    CONF_AQI_SOURCE,
    CONF_SITE_ID,
    CONF_SITE_NAME,
    DEFAULT_AQI_SOURCE,
    DOMAIN,
    TITLE,
)

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class EPAVicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    def __init__(self) -> None:
        """Initialise the config flow."""
        self.data = {}
        self.collector: Collector | None = None
        self._reauth_api_key: str = ""

    VERSION = 4

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

    def _get_consistent_existing_api_key(self) -> str:
        """Return the shared API key across existing entries, if there is exactly one."""

        keys = {
            api_key
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if (api_key := str(entry.options.get(CONF_API_KEY, "")).strip())
        }
        return keys.pop() if len(keys) == 1 else ""

    def _entries_with_api_key(self, api_key: str) -> list[ConfigEntry]:
        """Return all EPA config entries using the given API key."""
        normalised_key = api_key.strip()
        if not normalised_key:
            return []
        return [
            entry
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if str(entry.options.get(CONF_API_KEY, "")).strip() == normalised_key
        ]

    async def _async_validate_api_key(self, api_key: str) -> dict[str, str]:
        """Validate an API key by loading the EPA location list."""
        collector = Collector(
            api_key=api_key,
            latitude=self.hass.config.latitude,
            longitude=self.hass.config.longitude,
            session=async_get_clientsession(self.hass),
        )
        await collector.async_setup()
        if collector.valid_location_list():
            return {}
        _LOGGER.debug("Unable to retrieve location list from EPA")
        return {"base": "bad_api"}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initiated by the user.

        Arguments:
            user_input (dict[str, Any] | None, optional): The config submitted by a user. Defaults to None.

        Returns:
            ConfigFlowResult: The next step or form to show.

        """

        errors = {}

        if user_input is not None:
            try:
                # Create the collector object with the given parameters
                self.collector = Collector(
                    api_key=user_input[CONF_API_KEY],
                    latitude=self.hass.config.latitude,
                    longitude=self.hass.config.longitude,
                    session=async_get_clientsession(self.hass),
                )

                # Save the user input into self.data so it's retained
                self.data = user_input

                # Check if location is valid
                await self.collector.async_setup()
                if not self.collector.valid_location_list():
                    _LOGGER.error("Unable to retrieve location list from EPA")
                    errors["base"] = "bad_api"
                else:
                    return await self.async_step_location()

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_API_KEY,
                        default=self.data.get(CONF_API_KEY) or self._get_consistent_existing_api_key(),
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders={
                CONF_API_KEY: "Enter your API key provided by EPA Victoria.",
            },
        )

    async def async_step_location(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initiated by the user.

        Arguments:
            user_input (dict[str, Any] | None, optional): The config submitted by a user. Defaults to None.

        Returns:
            ConfigFlowResult: The form or created entry.

        """
        errors = {}

        if self.collector is None:
            return await self.async_step_user()

        if not self.collector.valid_location_list():
            await self.collector.async_setup()
            if not self.collector.valid_location_list():
                _LOGGER.error("Unable to retrieve location list from EPA")
                errors["base"] = "bad_api"

        epa_locs: list[SelectOptionDict] = self.collector.get_location_list()
        present_key = self.data.get(CONF_API_KEY)

        if user_input is not None:
            try:
                site_id = user_input[CONF_SITE_ID]
                location_label = next(
                    (str(loc.get("label", "")) for loc in epa_locs if loc.get("value") == site_id),
                    "",
                )

                # Create the collector object with the given parameters
                self.collector = Collector(
                    api_key=user_input[CONF_API_KEY],
                    latitude=self.hass.config.latitude,
                    longitude=self.hass.config.longitude,
                    epa_site_id=site_id,
                    session=async_get_clientsession(self.hass),
                )
                self.collector.site_name = location_label

                # Save the user input into self.data so it's retained
                self.data = user_input
                if self.data.get(CONF_API_KEY) != present_key:
                    errors["base"] = "key_changed"
                elif any(e.options.get(CONF_SITE_ID) == site_id for e in self.hass.config_entries.async_entries(DOMAIN)):
                    errors["base"] = "already_configured_location"
                else:
                    await self.async_set_unique_id(site_id)
                    self._abort_if_unique_id_configured()

                    entry_title = f"{TITLE} - {location_label}" if location_label else TITLE

                    options = {
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_SITE_ID: site_id,
                        CONF_SITE_NAME: location_label,
                        CONF_AQI_SOURCE: user_input.get(CONF_AQI_SOURCE, DEFAULT_AQI_SOURCE),
                    }

                    return self.async_create_entry(
                        title=entry_title,
                        data={},
                        options=options,
                    )

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY, default=self.data.get(CONF_API_KEY)): str,
                    vol.Required(CONF_SITE_ID, default=self.collector.get_location()): SelectSelector(
                        SelectSelectorConfig(
                            options=epa_locs,
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="choose_site",
                        )
                    ),
                    vol.Optional(
                        CONF_AQI_SOURCE,
                        default=self.data.get(CONF_AQI_SOURCE, DEFAULT_AQI_SOURCE),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(label="PM2.5", value=AQI_SOURCE_PM25),
                                SelectOptionDict(label="Overall", value=AQI_SOURCE_OVERALL),
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
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

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle a flow initiated by reauthentication."""
        # Keep one active reauth flow at a time.
        if any(
            progress_flow["flow_id"] != self.flow_id and progress_flow.get("context", {}).get("source") == "reauth"
            for progress_flow in self.hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        ):
            return self.async_abort(reason="reauth_already_in_progress")

        self._reauth_api_key = str(entry_data.get(CONF_API_KEY, "")).strip()
        if not self._reauth_api_key:
            self._reauth_api_key = str(self._get_reauth_entry().options.get(CONF_API_KEY, "")).strip()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm and apply reauthentication."""
        errors: dict[str, str] = {}

        if user_input is not None:
            new_api_key = str(user_input[CONF_API_KEY]).strip()
            errors = await self._async_validate_api_key(new_api_key)

            if not errors:
                matching_entries = self._entries_with_api_key(self._reauth_api_key)
                if not matching_entries:
                    matching_entries = [self._get_reauth_entry()]
                for entry in matching_entries:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        options={**entry.options, CONF_API_KEY: new_api_key},
                    )

                for entry in matching_entries:
                    # During reauth we perform one explicit reload per entry;
                    # listener-driven reload is suppressed in async_update_options.
                    await self.hass.config_entries.async_reload(entry.entry_id)

                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
        )


class EPAVicOptionFlowHandler(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise options flow."""
        self._entry: ConfigEntry = config_entry
        self._options = dict(config_entry.options)
        self._collector: Collector | None = None
        self._validated_api_key: str = ""
        self.data = {}

    async def _async_build_collector(self, api_key: str) -> tuple[Collector, dict[str, str]]:
        """Build collector and validate API key.

        Returns the collector and any errors encountered.
        """
        errors: dict[str, str] = {}
        collector = Collector(
            api_key=api_key,
            latitude=self.hass.config.latitude,
            longitude=self.hass.config.longitude,
            session=async_get_clientsession(self.hass),
        )
        await collector.async_setup()
        if not collector.valid_location_list():
            _LOGGER.debug("Unable to retrieve location list from EPA")
            errors["base"] = "bad_api"
        return collector, errors

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Initialise options flow with API key entry.

        Arguments:
            user_input (dict, optional): The input provided by the user. Defaults to None.

        Returns:
            Any: Either an error, or the next step.

        """
        errors: dict[str, str] = {}
        api_key = self._options.get(CONF_API_KEY, "")

        if user_input is not None:
            self.data = user_input
            api_key = user_input[CONF_API_KEY].replace(" ", "")
            self._collector, errors = await self._async_build_collector(api_key)

            if not errors:
                self._validated_api_key = api_key
                return await self.async_step_location()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY, default=api_key): str,
                }
            ),
            errors=errors,
        )

    async def async_step_location(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initiated by the user.

        Arguments:
            user_input (dict[str, Any] | None, optional): The config submitted by a user. Defaults to None.

        Returns:
            ConfigFlowResult: The form or created entry.

        """
        errors = {}

        if self._collector is None:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
            return self.async_show_form(
                step_id="location",
                data_schema=None,
                errors=errors,
            )
        site_id = self._options.get(CONF_SITE_ID, self._collector.get_location())
        epa_locs: list[SelectOptionDict] = self._collector.get_location_list()
        present_key = self.data.get(CONF_API_KEY)

        if user_input is not None:
            try:
                # Save the user input into self.data so it's retained
                self.data = user_input
                if self.data.get(CONF_API_KEY) != present_key:
                    errors["base"] = "key_changed"
                else:
                    site_id = user_input[CONF_SITE_ID]
                    location_label = next(
                        (str(loc.get("label", "")) for loc in epa_locs if loc.get("value") == site_id),
                        "",
                    )

                    if any(
                        e.entry_id != self._entry.entry_id and e.options.get(CONF_SITE_ID) == site_id
                        for e in self.hass.config_entries.async_entries(DOMAIN)
                    ):
                        errors["base"] = "already_configured_location"
                    else:
                        self._collector.site_id = site_id
                        self._collector.site_name = location_label

                        # Populate observations for the selected site.
                        await self._collector.async_update()

                        entry_title = f"{TITLE} - {location_label}" if location_label else TITLE

                        all_config_data = {**self._options}
                        all_config_data[CONF_API_KEY] = self._validated_api_key
                        all_config_data[CONF_SITE_ID] = site_id
                        all_config_data[CONF_SITE_NAME] = location_label
                        all_config_data[CONF_AQI_SOURCE] = user_input.get(
                            CONF_AQI_SOURCE,
                            self._options.get(CONF_AQI_SOURCE, DEFAULT_AQI_SOURCE),
                        )

                        # Update the config entry title to reflect the selected location.
                        self.hass.config_entries.async_update_entry(self._entry, title=entry_title)

                        return self.async_create_entry(title=entry_title, data=all_config_data)

            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY, default=self.data.get(CONF_API_KEY)): str,
                    vol.Required(CONF_SITE_ID, default=site_id): SelectSelector(
                        SelectSelectorConfig(
                            options=epa_locs,
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="choose_site",
                        )
                    ),
                    vol.Optional(
                        CONF_AQI_SOURCE,
                        default=self._options.get(CONF_AQI_SOURCE, DEFAULT_AQI_SOURCE),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(label="PM2.5", value=AQI_SOURCE_PM25),
                                SelectOptionDict(label="Overall", value=AQI_SOURCE_OVERALL),
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
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
