from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import CONF_GATEWAY_MAC, CONF_GATEWAY_TYPE, DOMAIN
from .gateway import GatewayClient


class BHKGatewayEntity(Entity):
    """Base entity tied to a specific gateway."""

    _attr_should_poll = False

    def __init__(self, client: GatewayClient, entry_data: dict):
        self._client = client
        self._gateway_mac = entry_data[CONF_GATEWAY_MAC]
        self._gateway_type = entry_data[CONF_GATEWAY_TYPE]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._gateway_mac)},
            manufacturer="BHK-SOLUTIONS",
            name=f"Gateway {self._gateway_mac}",
            model=self._gateway_type,
        )

    @property
    def available(self) -> bool:
        return self._client.is_connected

    @property
    def client(self) -> GatewayClient:
        return self._client
