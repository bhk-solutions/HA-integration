from homeassistant.const import Platform
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_GATEWAY_HW_VERSION,
    CONF_GATEWAY_IP,
    CONF_GATEWAY_MAC,
    CONF_GATEWAY_TYPE,
    CONF_GATEWAY_WS_PATH,
    CONF_GATEWAY_WS_PORT,
    DEFAULT_WEBSOCKET_PATH,
    DEFAULT_WEBSOCKET_PORT,
    DOMAIN,
)
from .gateway import GatewayClient

PLATFORMS = [Platform.LIGHT, Platform.SENSOR]

async def async_setup(hass: HomeAssistant, config: ConfigType):
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})

    client = GatewayClient(
        hass,
        entry.data[CONF_GATEWAY_MAC],
        entry.data[CONF_GATEWAY_IP],
        entry.data.get(CONF_GATEWAY_WS_PORT, DEFAULT_WEBSOCKET_PORT),
        entry.data.get(CONF_GATEWAY_WS_PATH, DEFAULT_WEBSOCKET_PATH),
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        CONF_GATEWAY_MAC: entry.data.get(CONF_GATEWAY_MAC),
        CONF_GATEWAY_IP: entry.data.get(CONF_GATEWAY_IP),
        CONF_GATEWAY_TYPE: entry.data.get(CONF_GATEWAY_TYPE),
        CONF_GATEWAY_WS_PORT: entry.data.get(CONF_GATEWAY_WS_PORT, DEFAULT_WEBSOCKET_PORT),
        CONF_GATEWAY_WS_PATH: entry.data.get(CONF_GATEWAY_WS_PATH, DEFAULT_WEBSOCKET_PATH),
        CONF_GATEWAY_HW_VERSION: entry.data.get(CONF_GATEWAY_HW_VERSION),
    }

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.data.get(CONF_GATEWAY_MAC))},
        connections={(dr.CONNECTION_NETWORK_MAC, entry.data.get(CONF_GATEWAY_MAC))},
        manufacturer="BHK-SOLUTIONS",
        name=f"Gateway {entry.data.get(CONF_GATEWAY_MAC)}",
        model=entry.data.get(CONF_GATEWAY_TYPE),
        hw_version=entry.data.get(CONF_GATEWAY_HW_VERSION),
    )

    await client.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id)
        client: GatewayClient = entry_data["client"]
        await client.async_stop()

    return unload_ok
