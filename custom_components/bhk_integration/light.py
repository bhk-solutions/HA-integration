from homeassistant.components.light import LightEntity
from .const import DOMAIN

class BHKLight(LightEntity):
    """Representation of a BHK test light."""

    def __init__(self, hass, device_id, endpoint):
        self._attr_unique_id = f"{device_id}_{endpoint}"
        self._attr_name = f"BHK Light {device_id} EP{endpoint}"
        self._state = False
        self._device_id = device_id
        self._endpoint = endpoint
        self._mqtt = hass.components.mqtt

        # Subscribe to state
        self._mqtt.subscribe(
            f"bhk/device/{device_id}/{endpoint}/state",
            self._handle_state,
        )

    def _handle_state(self, msg):
        payload = msg.payload.decode().upper()
        self._state = payload == "ON"
        self.async_write_ha_state()

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):
        await self._mqtt.async_publish(
            f"bhk/device/{self._device_id}/{self._endpoint}/set", "ON"
        )

    async def async_turn_off(self, **kwargs):
        await self._mqtt.async_publish(
            f"bhk/device/{self._device_id}/{self._endpoint}/set", "OFF"
        )
