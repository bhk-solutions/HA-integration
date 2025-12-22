import logging

from homeassistant.const import Platform
from homeassistant.components import network
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_GATEWAY_HW_VERSION,
    CONF_GATEWAY_IP,
    CONF_GATEWAY_MAC,
    CONF_GATEWAY_TYPE,
    CONF_LOCAL_BIND_IP,
    DOMAIN,
    SIGNAL_JOIN_WINDOW,
)
from .udp import UDPListener

PLATFORMS = [Platform.LIGHT, Platform.COVER, Platform.BUTTON]
_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType):
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("join_window_handlers", {})

    bind_ip = entry.options.get(CONF_LOCAL_BIND_IP) or entry.data.get(CONF_LOCAL_BIND_IP, "")
    if not bind_ip:
        adapters = await network.async_get_adapters(hass)
        for adapter in adapters:
            adapter_type = (
                adapter.get("type") if isinstance(adapter, dict) else getattr(adapter, "type", None)
            )
            if not adapter_type or str(adapter_type).lower() != "ethernet":
                continue
            ipv4_list = (
                adapter.get("ipv4") if isinstance(adapter, dict) else getattr(adapter, "ipv4", None)
            )
            if not ipv4_list:
                continue
            for addr in ipv4_list:
                address = (
                    addr.get("address") if isinstance(addr, dict) else getattr(addr, "address", None)
                )
                if address and not str(address).startswith("127."):
                    bind_ip = str(address)
                    break
            if bind_ip:
                break
        if bind_ip:
            _LOGGER.debug("Auto-selected wired bind IP %s for UDP", bind_ip)

    if "udp_listener" not in hass.data[DOMAIN]:
        if bind_ip:
            hass.data[DOMAIN][CONF_LOCAL_BIND_IP] = bind_ip
        listener = UDPListener(hass, bind_ip=bind_ip)
        await listener.async_start()
        hass.data[DOMAIN]["udp_listener"] = listener
    elif bind_ip and hass.data[DOMAIN].get(CONF_LOCAL_BIND_IP) not in ("", bind_ip):
        _LOGGER.warning(
            "UDP listener already running on %s; requested bind IP %s will be ignored until restart",
            hass.data[DOMAIN].get(CONF_LOCAL_BIND_IP),
            bind_ip,
        )
        hass.data[DOMAIN][CONF_LOCAL_BIND_IP] = bind_ip
    elif bind_ip and CONF_LOCAL_BIND_IP not in hass.data[DOMAIN]:
        hass.data[DOMAIN][CONF_LOCAL_BIND_IP] = bind_ip

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_GATEWAY_MAC: entry.data.get(CONF_GATEWAY_MAC),
        CONF_GATEWAY_IP: entry.data.get(CONF_GATEWAY_IP),
        CONF_GATEWAY_TYPE: entry.data.get(CONF_GATEWAY_TYPE),
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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _handle_join_window(payload):
        gw_mac = payload.get("mac") or entry.data.get(CONF_GATEWAY_MAC)
        duration = payload.get("duration_s")
        if not gw_mac:
            return
        message = f"Join window opened on gateway {gw_mac}"
        if duration:
            message += f" for {duration}s"
        hass.async_create_task(
            hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": message,
                    "title": "Gateway Join Window",
                    "notification_id": f"join_window_{gw_mac}",
                },
                blocking=False,
            )
        )

    remove = async_dispatcher_connect(hass, SIGNAL_JOIN_WINDOW, _handle_join_window)
    hass.data[DOMAIN]["join_window_handlers"][entry.entry_id] = remove

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    entry_keys = [
        key
        for key in hass.data[DOMAIN]
        if key not in ("udp_listener", "light_manager", "cover_manager")
    ]

    if not entry_keys:
        listener: UDPListener | None = hass.data[DOMAIN].pop("udp_listener", None)
        if listener:
            await listener.async_stop()
        hass.data[DOMAIN].pop(CONF_LOCAL_BIND_IP, None)

    remover = hass.data[DOMAIN].get("join_window_handlers", {}).pop(entry.entry_id, None)
    if remover:
        remover()

    return unload_ok
