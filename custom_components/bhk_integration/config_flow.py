import asyncio
import json
import socket
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import network
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_GATEWAY_HW_VERSION,
    CONF_GATEWAY_IP,
    CONF_GATEWAY_MAC,
    CONF_GATEWAY_TYPE,
    CONF_RETRY_INTERVAL,
    DEFAULT_RETRY_INTERVAL,
    DISCOVERY_BROADCAST_PORT,
    DISCOVERY_MESSAGE,
    DISCOVERY_WINDOW,
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

    def __init__(self) -> None:
        self._discovered_gateways: dict[str, dict[str, Any]] = {}

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        discovered = await self._async_discover_gateways(
            user_input.get(CONF_RETRY_INTERVAL, DEFAULT_RETRY_INTERVAL)
        )

        if not discovered:
            errors["base"] = "no_gateway_found"
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        self._discovered_gateways = {gw[CONF_GATEWAY_MAC]: gw for gw in discovered}

        available = [
            gw
            for gw in discovered
            if not self._is_configured(gw[CONF_GATEWAY_MAC])
        ]

        if not available:
            errors["base"] = "no_new_gateway"
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        if len(available) == 1:
            return await self._async_create_entry(available[0])

        return await self.async_step_select_gateway()

    async def async_step_select_gateway(self, user_input=None) -> FlowResult:
        errors = {}

        options = {
            mac: f"{mac} ({gateway.get(CONF_GATEWAY_IP)})"
            for mac, gateway in self._discovered_gateways.items()
            if not self._is_configured(mac)
        }

        if not options:
            return self.async_abort(reason="no_new_gateway")

        schema = vol.Schema({vol.Required(CONF_GATEWAY_MAC): vol.In(options)})

        if user_input is None:
            return self.async_show_form(
                step_id="select_gateway", data_schema=schema, errors=errors
            )

        mac = user_input[CONF_GATEWAY_MAC]
        gateway = self._discovered_gateways.get(mac)
        if gateway is None:
            errors["base"] = "no_gateway_found"
            return self.async_show_form(
                step_id="select_gateway", data_schema=schema, errors=errors
            )

        return await self._async_create_entry(gateway)

    async def _async_discover_gateways(self, retry_interval: int) -> list[Mapping[str, Any]]:
        """Send discovery broadcast and wait for gateway responses."""

        loop = asyncio.get_running_loop()
        broadcast_addresses = await network.async_get_ipv4_broadcast_addresses(self.hass)
        addresses = [str(address) for address in broadcast_addresses]
        if not addresses:
            addresses = ["255.255.255.255"]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setblocking(False)
        sock.bind(("0.0.0.0", GATEWAY_RESPONSE_PORT))

        discovered: dict[str, Mapping[str, Any]] = {}
        end_time = loop.time() + DISCOVERY_WINDOW
        next_send = loop.time()

        try:
            while loop.time() < end_time:
                now = loop.time()
                if now >= next_send:
                    for address in addresses:
                        try:
                            sock.sendto(
                                DISCOVERY_MESSAGE.encode(),
                                (address, DISCOVERY_BROADCAST_PORT),
                            )
                        except OSError:
                            continue
                    next_send = now + retry_interval

                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 1024),
                        timeout=max(
                            0,
                            min(next_send - loop.time(), end_time - loop.time()),
                        ),
                    )
                except asyncio.TimeoutError:
                    continue

                try:
                    response = data.decode().strip()
                except UnicodeDecodeError:
                    continue

                gateway = self._parse_gateway_response(response, addr[0])
                if gateway:
                    discovered[gateway[CONF_GATEWAY_MAC]] = gateway
        finally:
            sock.close()

        return list(discovered.values())

    def _parse_gateway_response(self, response: str, sender_ip: str) -> Mapping[str, Any] | None:
        """Validate and parse the gateway response string."""

        payload: dict[str, Any]
        try:
            payload = json.loads(response)
        except json.JSONDecodeError:
            return None

        normalized = {str(key).lower(): value for key, value in payload.items()}

        mac = normalized.get("mac")
        if not mac:
            return None

        return {
            CONF_GATEWAY_MAC: mac,
            CONF_GATEWAY_IP: normalized.get("ip", sender_ip),
            CONF_GATEWAY_TYPE: normalized.get("type") or normalized.get("device", "unknown"),
            CONF_GATEWAY_HW_VERSION: normalized.get("hardware_version")
            or normalized.get("version"),
        }

    def _is_configured(self, mac: str) -> bool:
        for entry in self._async_current_entries():
            if entry.data.get(CONF_GATEWAY_MAC) == mac:
                return True
        return False

    async def _async_create_entry(self, discovery: Mapping[str, Any]) -> FlowResult:
        await self.async_set_unique_id(discovery[CONF_GATEWAY_MAC])
        self._abort_if_unique_id_configured()

        title = f"Gateway {discovery[CONF_GATEWAY_MAC]}"
        return self.async_create_entry(title=title, data=discovery)
