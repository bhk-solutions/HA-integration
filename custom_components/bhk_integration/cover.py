from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
)
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
    SIGNAL_COVER_REGISTER,
    SIGNAL_COVER_STATE,
)
from .udp import async_send_udp_command

_LOGGER = logging.getLogger(__name__)


@dataclass
class CoverEntryContext:
    entry_id: str
    gateway_mac: str | None
    gateway_ip: str | None
    gateway_type: str | None
    hardware_version: str | None
    async_add_entities: AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    manager: CoverManager = hass.data[DOMAIN].get("cover_manager")
    if manager is None:
        manager = CoverManager(hass)
        hass.data[DOMAIN]["cover_manager"] = manager

    manager.register_entry(entry, async_add_entities)


class CoverManager:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._entities: dict[str, BHKCoverEntity] = {}
        self._contexts: dict[str, CoverEntryContext] = {}
        self._remove_callbacks = [
            async_dispatcher_connect(hass, SIGNAL_COVER_REGISTER, self._handle_register),
            async_dispatcher_connect(hass, SIGNAL_COVER_STATE, self._handle_state),
        ]

    def register_entry(
        self, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
    ) -> None:
        entry_data = self._hass.data[DOMAIN][entry.entry_id]
        context = CoverEntryContext(
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
            self._hass.data[DOMAIN].pop("cover_manager", None)

    @callback
    def _handle_register(self, payload: dict[str, Any]) -> None:
        data = {str(k).lower(): v for k, v in payload.items()}
        unique_id = data.get("unique_id") or data.get("mac")
        if not unique_id:
            _LOGGER.debug("Ignoring cover register payload without unique_id: %s", payload)
            return

        if unique_id in self._entities:
            self._entities[unique_id].update_from_register(payload)
            return

        context = self._resolve_context(data.get("gateway_mac"))
        if context is None:
            _LOGGER.debug("No entry context available; cannot create cover %s", unique_id)
            return

        entity = BHKCoverEntity(context, payload)
        self._entities[unique_id] = entity
        context.async_add_entities([entity])

        if "state" in data or "position" in data:
            entity.process_state(payload)

    @callback
    def _handle_state(self, payload: dict[str, Any]) -> None:
        data = {str(k).lower(): v for k, v in payload.items()}
        unique_id = data.get("unique_id") or data.get("mac")
        if not unique_id:
            _LOGGER.debug("Ignoring cover state payload without unique_id: %s", payload)
            return

        entity = self._entities.get(unique_id)
        if entity is None:
            _LOGGER.debug("State update received for unknown cover %s", unique_id)
            return

        entity.process_state(payload)

    def _resolve_context(self, gateway_mac: str | None) -> CoverEntryContext | None:
        if gateway_mac:
            for context in self._contexts.values():
                if context.gateway_mac and context.gateway_mac.lower() == gateway_mac.lower():
                    return context
        return next(iter(self._contexts.values()), None)


class BHKCoverEntity(CoverEntity):
    _attr_should_poll = False
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, context: CoverEntryContext, payload: dict[str, Any]) -> None:
        self.entry_id = context.entry_id
        normalized = {str(k).lower(): v for k, v in payload.items()}
        unique_id = normalized.get("unique_id") or normalized.get("mac")
        self._attr_unique_id = unique_id
        self._gateway_mac = normalized.get("gateway_mac") or context.gateway_mac
        self._gateway_ip = context.gateway_ip
        self._gateway_type = context.gateway_type
        self._hardware_version = context.hardware_version
        self._attr_name = payload.get("name") or f"Cover {unique_id}"
        self._attr_is_closed: bool | None = None
        self._attr_current_cover_position: int | None = None
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

    def update_from_register(self, payload: dict[str, Any]) -> None:
        name = payload.get("name")
        if name and name != self._attr_name:
            self._attr_name = name
            self.async_write_ha_state()

    def process_state(self, payload: dict[str, Any]) -> None:
        data = {str(k).lower(): v for k, v in payload.items()}
        raw_state = str(data.get("state", "")).lower()
        new_is_closed: bool | None
        if raw_state in ("open", "opened"):
            new_is_closed = False
        elif raw_state in ("close", "closed"):
            new_is_closed = True
        elif raw_state in ("opening", "closing"):
            new_is_closed = None
        else:
            new_is_closed = self._attr_is_closed

        position = data.get("position")
        new_position: int | None = self._attr_current_cover_position
        if isinstance(position, (int, float)):
            new_position = max(0, min(100, int(position)))

        if new_is_closed != self._attr_is_closed or new_position != self._attr_current_cover_position:
            self._attr_is_closed = new_is_closed
            self._attr_current_cover_position = new_position
            self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_send_command("OPEN")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_send_command("CLOSE")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get("position")
        if position is None:
            return
        percent = max(0, min(100, int(position)))
        await self._async_send_command(f"P:{percent}")

    async def _async_send_command(self, command: str | None = None) -> None:
        if not self._gateway_ip:
            _LOGGER.warning(
                "Cannot send cover command for %s; gateway IP unknown", self._attr_unique_id
            )
            return

        if not command:
            _LOGGER.debug("No command specified for cover %s", self._attr_unique_id)
            return

        payload: dict[str, Any] = {
            "type": "cover_command",
            "unique_id": self._attr_unique_id,
        }
        payload["command"] = command

        _LOGGER.info(
            "Sending cover command for %s to %s:%s -> %s",
            self._attr_unique_id,
            self._gateway_ip,
            GATEWAY_COMMAND_PORT,
            payload,
        )
        await async_send_udp_command(self.hass, self._gateway_ip, payload)
