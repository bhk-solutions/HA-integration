from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_GATEWAY_MAC, DOMAIN
from .entity import BHKGatewayEntity

_LOGGER = logging.getLogger(__name__)

DEFAULT_LIGHT_ENDPOINTS = (1,)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]

    entities = [
        BHKLightEntity(client, entry_data, endpoint)
        for endpoint in DEFAULT_LIGHT_ENDPOINTS
    ]

    async_add_entities(entities)


class BHKLightEntity(BHKGatewayEntity, LightEntity):
    """Light entity bound to a gateway endpoint via websocket."""

    def __init__(self, client, entry_data, endpoint: int) -> None:
        super().__init__(client, entry_data)
        self._endpoint = endpoint
        self._attr_unique_id = f"{entry_data[CONF_GATEWAY_MAC]}_light_{endpoint}"
        self._attr_name = f"Gateway {entry_data[CONF_GATEWAY_MAC]} Light {endpoint}"
        self._is_on = False
        self._unsub_message = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub_message = self.client.add_message_listener(self._handle_message)

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        if self._unsub_message:
            self._unsub_message()
            self._unsub_message = None

    def _handle_message(self, payload: dict[str, Any]) -> None:
        if payload.get("type") != "light_state":
            return
        if payload.get("endpoint") != self._endpoint:
            return

        state = str(payload.get("state", "")).lower()
        new_state = state == "on"
        if new_state != self._is_on:
            self._is_on = new_state
            self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_command("on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command("off")

    async def _send_command(self, state: str) -> None:
        try:
            await self.client.async_send(
                {
                    "type": "set_light",
                    "endpoint": self._endpoint,
                    "state": state,
                }
            )
        except ConnectionError as err:
            _LOGGER.warning(
                "Unable to send command to gateway %s endpoint %s: %s",
                self._gateway_mac,
                self._endpoint,
                err,
            )
