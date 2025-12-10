import asyncio
import socket
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_GATEWAY_IP,
    CONF_GATEWAY_MAC,
    CONF_GATEWAY_TYPE,
    CONF_RETRY_INTERVAL,
    DEFAULT_RETRY_INTERVAL,
    DISCOVERY_BROADCAST_PORT,
    DISCOVERY_MESSAGE,
    DOMAIN,
    GATEWAY_RESPONSE_PORT,
)


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_RETRY_INTERVAL, default=DEFAULT_RETRY_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        )
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BHK Integration."""

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        discovery = await self._async_discover_gateway(
            user_input.get(CONF_RETRY_INTERVAL, DEFAULT_RETRY_INTERVAL)
        )

        if discovery is None:
            errors["base"] = "no_gateway_found"
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        await self.async_set_unique_id(discovery[CONF_GATEWAY_MAC])
        self._abort_if_unique_id_configured()

        title = f"Gateway {discovery[CONF_GATEWAY_MAC]}"
        return self.async_create_entry(title=title, data=discovery)

    async def _async_discover_gateway(self, retry_interval: int) -> Mapping[str, Any] | None:
        """Send discovery broadcast and wait for a gateway response."""

        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        sock.bind(("0.0.0.0", GATEWAY_RESPONSE_PORT))

        try:
            while True:
                await loop.run_in_executor(
                    None,
                    sock.sendto,
                    DISCOVERY_MESSAGE.encode(),
                    ("255.255.255.255", DISCOVERY_BROADCAST_PORT),
                )

                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 1024), timeout=retry_interval
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    response = data.decode().strip()
                except UnicodeDecodeError:
                    continue

                gateway = self._parse_gateway_response(response, addr[0])
                if gateway:
                    return gateway
        finally:
            sock.close()

    def _parse_gateway_response(self, response: str, sender_ip: str) -> Mapping[str, Any] | None:
        """Validate and parse the gateway response string."""

        if not response.startswith("ESP-GATEWAY"):
            return None

        parts = response.split("|")
        info: dict[str, Any] = {}

        for part in parts[1:]:
            if "=" not in part:
                continue
            key, value = part.split("=", maxsplit=1)
            key = key.strip().lower()
            info[key] = value.strip()

        mac = info.get("mac")
        if mac is None:
            return None

        return {
            CONF_GATEWAY_MAC: mac,
            CONF_GATEWAY_IP: info.get("ip", sender_ip),
            CONF_GATEWAY_TYPE: info.get("type", "unknown"),
        }
