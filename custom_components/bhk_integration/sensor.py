from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_GATEWAY_MAC, DOMAIN
from .entity import BHKGatewayEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    client = entry_data["client"]

    async_add_entities(
        [GatewayConnectionSensor(client, entry_data)],
    )


class GatewayConnectionSensor(BHKGatewayEntity, SensorEntity):
    """Binary-like sensor indicating the websocket connection state."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["connected", "disconnected"]

    def __init__(self, client, entry_data) -> None:
        super().__init__(client, entry_data)
        self._attr_unique_id = f"{entry_data[CONF_GATEWAY_MAC]}_connection"
        self._attr_name = "Gateway connection"
        self._connected = client.is_connected
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub = self.client.add_status_listener(self._handle_status)

    async def async_will_remove_from_hass(self) -> None:
        await super().async_will_remove_from_hass()
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def native_value(self):
        return "connected" if self._connected else "disconnected"

    def _handle_status(self, connected: bool) -> None:
        if self._connected == connected:
            return
        self._connected = connected
        self.async_write_ha_state()
