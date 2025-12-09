from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import DOMAIN

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BHK Integration."""

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(step_id="user")

        return self.async_create_entry(title="BHK Bridge", data={})
