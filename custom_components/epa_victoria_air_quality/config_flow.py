import requests
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN

@config_entries.HANDLERS.register(DOMAIN)
class EPAVictoriaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            api_key = user_input["api_key"]
            site_id = user_input["site_id"]

            # Validate the provided API key and site ID
            valid = await self._test_api(api_key, site_id)
            if valid:
                return self.async_create_entry(title="EPA Victoria Air Quality", data=user_input)
            else:
                errors["base"] = "auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("api_key"): str,
                vol.Required("site_id"): str,
            }),
            errors=errors,
        )

    async def _test_api(self, api_key, site_id):
        """Test the API key and site ID by making a request to the EPA API."""
        try:
            headers = {"X-API-Key": api_key}
            response = requests.get(f"https://gateway.api.epa.vic.gov.au/environmentMonitoring/v1/sites/{site_id}/parameters", headers=headers)
            response.raise_for_status()
            return True
        except requests.RequestException:
            return False
