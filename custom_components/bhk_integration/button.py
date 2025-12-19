from __future__ import annotations

import logging
from uuid import uuid4

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_GATEWAY_HW_VERSION,
    CONF_GATEWAY_IP,
    CONF_GATEWAY_MAC,
    CONF_GATEWAY_TYPE,
    DEFAULT_JOIN_WINDOW_SECONDS,
    DOMAIN,
)
from .udp import async_send_udp_command

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    button = BHKOpenJoinButton(hass, entry.entry_id, entry_data)
    async_add_entities([button])


class BHKOpenJoinButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry_id: str, entry_data: dict) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._gateway_mac = entry_data.get(CONF_GATEWAY_MAC)
        self._gateway_ip = entry_data.get(CONF_GATEWAY_IP)
        self._gateway_type = entry_data.get(CONF_GATEWAY_TYPE)
        self._hardware_version = entry_data.get(CONF_GATEWAY_HW_VERSION)
        self._attr_unique_id = f"{self._gateway_mac}_open_join"
        self._attr_name = "Open Join Window"

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

    async def async_press(self) -> None:
        if not self._gateway_ip or not self._gateway_mac:
            _LOGGER.warning("Gateway IP/MAC missing; cannot open join window")
            return

        payload = {
            "type": "open_join",
            "target_mac": self._gateway_mac,
            "duration_s": DEFAULT_JOIN_WINDOW_SECONDS,
            "req_id": str(uuid4()),
        }
        _LOGGER.info(
            "Sending open_join to %s for %ss", self._gateway_ip, DEFAULT_JOIN_WINDOW_SECONDS
        )
        await async_send_udp_command(self.hass, self._gateway_ip, payload)
