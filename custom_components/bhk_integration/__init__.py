from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import CONF_GATEWAY_IP, CONF_GATEWAY_MAC, CONF_GATEWAY_TYPE, DOMAIN
PLATFORMS = [Platform.LIGHT]

async def async_setup(hass: HomeAssistant, config: ConfigType):
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        CONF_GATEWAY_MAC: entry.data.get(CONF_GATEWAY_MAC),
        CONF_GATEWAY_IP: entry.data.get(CONF_GATEWAY_IP),
        CONF_GATEWAY_TYPE: entry.data.get(CONF_GATEWAY_TYPE),
    }

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data.get(CONF_GATEWAY_MAC))},
        connections={(dr.CONNECTION_NETWORK_MAC, entry.data.get(CONF_GATEWAY_MAC))},
        manufacturer="ESP Gateway",
        name=f"Gateway {entry.data.get(CONF_GATEWAY_MAC)}",
        model=entry.data.get(CONF_GATEWAY_TYPE),
        sw_version=None,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
