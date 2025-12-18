from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_GATEWAY_HW_VERSION,
    CONF_GATEWAY_IP,
    CONF_GATEWAY_MAC,
    CONF_GATEWAY_TYPE,
    DOMAIN,
    GATEWAY_COMMAND_PORT,
    SIGNAL_DEVICE_JOIN,
    SIGNAL_LIGHT_REGISTER,
    SIGNAL_LIGHT_STATE,
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
        self._remove_callbacks = [
            async_dispatcher_connect(hass, SIGNAL_LIGHT_REGISTER, self._handle_register),
            async_dispatcher_connect(hass, SIGNAL_LIGHT_STATE, self._handle_state),
            async_dispatcher_connect(hass, SIGNAL_DEVICE_JOIN, self._handle_device_join),
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
        ieee = data.get("ieee")
        ep = data.get("endpoint")
        if not ieee or ep is None:
            _LOGGER.debug("device_join missing ieee/endpoint: %s", payload)
            return

        # Determine type from clusters (strings like "0x0006" or ints)
        in_clusters = data.get("in_clusters") or []
        try:
            cluster_ids = [
                str(c).lower() if isinstance(c, str) else f"0x{int(c):04x}"
                for c in in_clusters
            ]
        except Exception:  # noqa: BLE001
            cluster_ids = []

        if "0x0006" not in cluster_ids:
            _LOGGER.debug("device_join ep %s lacks OnOff cluster; ignoring: %s", ep, payload)
            return

        unique_id = data.get("unique_id") or f"{ieee}_{ep}"
        name = payload.get("name") or f"Light {ep}"
        gateway_mac = data.get("gateway_mac")
        register_payload = {
            "type": "light_register",
            "unique_id": unique_id,
            "name": name,
            "gateway_mac": gateway_mac,
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
        self._attr_name = payload.get("name") or f"Light {unique_id}"
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

        payload = {
            "type": "light_command",
            "unique_id": self._attr_unique_id,
            "state": state,
        }
        _LOGGER.info(
            "Sending light command for %s to %s:%s -> %s",
            self._attr_unique_id,
            self._gateway_ip,
            GATEWAY_COMMAND_PORT,
            payload,
        )
        await async_send_udp_command(self.hass, self._gateway_ip, payload)
