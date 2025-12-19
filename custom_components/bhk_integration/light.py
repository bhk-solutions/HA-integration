from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_GATEWAY_HW_VERSION,
    CONF_GATEWAY_IP,
    CONF_GATEWAY_MAC,
    CONF_GATEWAY_TYPE,
    DOMAIN,
    GATEWAY_ALIVE_TIMEOUT,
    GATEWAY_COMMAND_PORT,
    SIGNAL_DEVICE_JOIN,
    SIGNAL_GATEWAY_ALIVE,
    SIGNAL_LIGHT_REGISTER,
    SIGNAL_LIGHT_STATE,
    SIGNAL_ZB_REPORT,
)
from .udp import async_send_udp_command

_LOGGER = logging.getLogger(__name__)


@dataclass
class LightEntryContext:
    entry_id: str
    gateway_mac: str | None
    gateway_ip: str | None
    gateway_type: str | None
    hardware_version: str | None
    async_add_entities: AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: LightManager = hass.data[DOMAIN].get("light_manager")
    if manager is None:
        manager = LightManager(hass)
        hass.data[DOMAIN]["light_manager"] = manager

    manager.register_entry(entry, async_add_entities)


class LightManager:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._entities: dict[str, BHKLightEntity] = {}
        self._contexts: dict[str, LightEntryContext] = {}
        self._last_alive: dict[str, datetime] = {}
        self._watchdog_unsub = async_track_time_interval(
            hass, self._watchdog, timedelta(seconds=15)
        )
        self._remove_callbacks = [
            async_dispatcher_connect(hass, SIGNAL_LIGHT_REGISTER, self._handle_register),
            async_dispatcher_connect(hass, SIGNAL_LIGHT_STATE, self._handle_state),
            async_dispatcher_connect(hass, SIGNAL_DEVICE_JOIN, self._handle_device_join),
            async_dispatcher_connect(hass, SIGNAL_ZB_REPORT, self._handle_zb_report),
            async_dispatcher_connect(hass, SIGNAL_GATEWAY_ALIVE, self._handle_gateway_alive),
        ]

    def register_entry(
        self, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
    ) -> None:
        entry_data = self._hass.data[DOMAIN][entry.entry_id]
        context = LightEntryContext(
            entry_id=entry.entry_id,
            gateway_mac=entry_data.get(CONF_GATEWAY_MAC),
            gateway_ip=entry_data.get(CONF_GATEWAY_IP),
            gateway_type=entry_data.get(CONF_GATEWAY_TYPE),
            hardware_version=entry_data.get(CONF_GATEWAY_HW_VERSION),
            async_add_entities=async_add_entities,
        )
        self._contexts[entry.entry_id] = context
        entry.async_on_unload(lambda: self.unregister_entry(entry.entry_id))

    def unregister_entry(self, entry_id: str) -> None:
        self._contexts.pop(entry_id, None)
        for unique_id in [
            uid for uid, entity in self._entities.items() if entity.entry_id == entry_id
        ]:
            self._entities.pop(unique_id)

        if not self._contexts:
            for remove in self._remove_callbacks:
                remove()
            self._remove_callbacks.clear()
            if self._watchdog_unsub:
                self._watchdog_unsub()
                self._watchdog_unsub = None
            self._hass.data[DOMAIN].pop("light_manager", None)

    @callback
    def _handle_register(self, payload: dict[str, Any]) -> None:
        data = {str(k).lower(): v for k, v in payload.items()}
        unique_id = data.get("unique_id") or data.get("mac")
        if not unique_id:
            _LOGGER.debug("Ignoring register payload without unique_id: %s", payload)
            return

        if unique_id in self._entities:
            self._entities[unique_id].update_from_register(payload)
            return

        context = self._resolve_context(data.get("gateway_mac"))
        if context is None:
            _LOGGER.debug("No entry context available; cannot create light %s", unique_id)
            return

        entity = BHKLightEntity(context, payload)
        self._entities[unique_id] = entity
        context.async_add_entities([entity])

        if "state" in data:
            entity.process_state(payload)

    @callback
    def _handle_device_join(self, payload: dict[str, Any]) -> None:
        data = {str(k).lower(): v for k, v in payload.items()}
        device_type = data.get("device_type") or ""
        dev_id = data.get("id") or data.get("ieee") or ""
        if not dev_id:
            _LOGGER.debug("device_join missing id: %s", payload)
            return
        # Expect endpoints info from payload (may be single endpoint field or desc packets)
        ep = data.get("endpoint")
        if ep is None:
            eps = data.get("eps") or data.get("endpoints") or []
        else:
            eps = [ep]
        # Only handle our light type
        if "3lights" not in str(device_type).lower():
            return
        gateway_mac = data.get("gateway_mac")
        for ep_val in eps:
            unique_id = f"{dev_id}_{ep_val}"
            name = f"Light {ep_val}"
            register_payload = {
                "type": "light_register",
                "unique_id": unique_id,
                "name": name,
                "gateway_mac": gateway_mac,
                "id": dev_id,
                "endpoint": ep_val,
                "device_type": device_type,
            }
            self._handle_register(register_payload)

    @callback
    def _handle_state(self, payload: dict[str, Any]) -> None:
        data = {str(k).lower(): v for k, v in payload.items()}
        unique_id = data.get("unique_id") or data.get("mac")
        if not unique_id:
            _LOGGER.debug("Ignoring state payload without unique_id: %s", payload)
            return

        entity = self._entities.get(unique_id)
        if entity is None:
            _LOGGER.debug("State update received for unknown light %s", unique_id)
            return

        entity.process_state(payload)

    @callback
    def _handle_zb_report(self, payload: dict[str, Any]) -> None:
        data = {str(k).lower(): v for k, v in payload.items()}
        dev_id = data.get("id") or data.get("ieee")
        ep = data.get("endpoint")
        st = data.get("st")
        if dev_id is None or ep is None:
            return
        unique_id = f"{dev_id}_{ep}"
        entity = self._entities.get(unique_id)
        if not entity:
            return
        # st may be int/bool
        if st is not None:
            state_payload = {"state": "on" if str(st) in ("1", "True", "true", "on") else "off"}
            entity.process_state(state_payload)
        # mark available on any incoming report
        if entity.set_available(True):
            entity.async_write_ha_state()

    @callback
    def _handle_gateway_alive(self, payload: dict[str, Any]) -> None:
        gw_mac = payload.get("mac") or payload.get("gateway_mac")
        if not gw_mac:
            return
        self._last_alive[gw_mac.lower()] = datetime.utcnow()
        self._update_availability(gw_mac, True)

    @callback
    def _watchdog(self, _now) -> None:
        cutoff = datetime.utcnow() - timedelta(seconds=GATEWAY_ALIVE_TIMEOUT)
        for gw_mac, ts in list(self._last_alive.items()):
            available = ts >= cutoff
            self._update_availability(gw_mac, available)

    def _update_availability(self, gateway_mac: str, available: bool) -> None:
        gw = gateway_mac.lower()
        for entity in self._entities.values():
            if entity.gateway_mac and entity.gateway_mac.lower() == gw:
                if entity.set_available(available):
                    entity.async_write_ha_state()

    def _resolve_context(self, gateway_mac: str | None) -> LightEntryContext | None:
        if gateway_mac:
            for context in self._contexts.values():
                if context.gateway_mac and context.gateway_mac.lower() == gateway_mac.lower():
                    return context
        return next(iter(self._contexts.values()), None)


class BHKLightEntity(LightEntity):
    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(self, context: LightEntryContext, payload: dict[str, Any]) -> None:
        self.entry_id = context.entry_id
        normalized = {str(k).lower(): v for k, v in payload.items()}
        unique_id = normalized.get("unique_id") or normalized.get("mac")
        self._attr_unique_id = unique_id
        self._gateway_mac = normalized.get("gateway_mac") or context.gateway_mac
        self._gateway_ip = context.gateway_ip
        self._gateway_type = context.gateway_type
        self._hardware_version = context.hardware_version
        self._is_on = False
        self._id = normalized.get("id") or normalized.get("ieee")
        self._endpoint = normalized.get("endpoint")
        self._device_type = normalized.get("device_type")
        self._attr_name = payload.get("name") or f"Light {unique_id}"
        self._attr_available = True
        if self._gateway_mac:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, self._gateway_mac)},
                manufacturer="BHK-SOLUTIONS",
                name=f"Gateway {self._gateway_mac}",
                model=self._gateway_type,
                hw_version=self._hardware_version,
            )
        else:
            self._attr_device_info = None

    @property
    def is_on(self) -> bool:
        return self._is_on

    def update_from_register(self, payload: dict[str, Any]) -> None:
        name = payload.get("name")
        if name and name != self._attr_name:
            self._attr_name = name
            self.async_write_ha_state()
        normalized = {str(k).lower(): v for k, v in payload.items()}
        if normalized.get("id"):
            self._id = normalized.get("id")
        if normalized.get("endpoint") is not None:
            self._endpoint = normalized.get("endpoint")
        if normalized.get("device_type"):
            self._device_type = normalized.get("device_type")

    def process_state(self, payload: dict[str, Any]) -> None:
        data = {str(k).lower(): v for k, v in payload.items()}
        state = str(data.get("state", "")).lower()
        new_state = state == "on"
        if new_state != self._is_on:
            self._is_on = new_state
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_send_command("ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_command("OFF")

    async def _async_send_command(self, state: str) -> None:
        if not self._gateway_ip:
            _LOGGER.warning(
                "Cannot send command for %s; gateway IP unknown", self._attr_unique_id
            )
            return
        if not self._id or self._endpoint is None:
            _LOGGER.warning(
                "Cannot send command for %s; missing id/endpoint", self._attr_unique_id
            )
            return

        payload = {
            "type": "forward_command",
            "id": self._id,
            "endpoint": self._endpoint,
            "cmd": state.lower(),
        }
        _LOGGER.info(
            "Sending light command for %s to %s:%s -> %s",
            self._attr_unique_id,
            self._gateway_ip,
            GATEWAY_COMMAND_PORT,
            payload,
        )
        await async_send_udp_command(self.hass, self._gateway_ip, payload)

    @property
    def gateway_mac(self) -> str | None:
        return self._gateway_mac

    def set_available(self, available: bool) -> bool:
        if self._attr_available == available:
            return False
        self._attr_available = available
        return True
