from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    GATEWAY_COMMAND_PORT,
    GATEWAY_RESPONSE_PORT,
    SIGNAL_LIGHT_REGISTER,
    SIGNAL_LIGHT_STATE,
)

_LOGGER = logging.getLogger(__name__)


class UDPListener:
    """Listen for UDP messages from gateways and dispatch them."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._transport: asyncio.DatagramTransport | None = None

    async def async_start(self) -> None:
        if self._transport is not None:
            return

        loop = asyncio.get_running_loop()
        kwargs = {"local_addr": ("0.0.0.0", GATEWAY_RESPONSE_PORT)}
        reuse_port_supported = hasattr(socket, "SO_REUSEPORT")

        try:
            self._transport, _ = await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(self._hass),
                **kwargs,
            )
        except OSError as err:
            if err.errno != getattr(socket, "EADDRINUSE", 98):
                raise

            def _bind_socket() -> socket.socket:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if reuse_port_supported:
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except OSError:
                        pass
                sock.bind(("0.0.0.0", GATEWAY_RESPONSE_PORT))
                return sock

            transport, _ = await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(self._hass),
                sock=_bind_socket(),
            )
            self._transport = transport
        _LOGGER.debug("UDP listener started on port %s", GATEWAY_RESPONSE_PORT)

    async def async_stop(self) -> None:
        if self._transport is None:
            return

        self._transport.close()
        self._transport = None
        _LOGGER.debug("UDP listener stopped")


class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def datagram_received(self, data: bytes, addr) -> None:
        try:
            payload = json.loads(data.decode())
        except json.JSONDecodeError:
            _LOGGER.debug("Discarding non-JSON UDP payload from %s", addr)
            return

        msg_type = str(payload.get("type", "")).lower()
        if msg_type == "light_register":
            async_dispatcher_send(self._hass, SIGNAL_LIGHT_REGISTER, payload)
        elif msg_type == "light_state":
            async_dispatcher_send(self._hass, SIGNAL_LIGHT_STATE, payload)
        else:
            _LOGGER.debug("Ignoring unsupported UDP message type '%s'", msg_type)


async def async_send_udp_command(
    hass: HomeAssistant, host: str, payload: dict[str, Any], port: int | None = None
) -> None:
    """Send a JSON payload to the given host via UDP."""

    target_port = port or GATEWAY_COMMAND_PORT
    data = json.dumps(payload).encode()

    def _send() -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(data, (host, target_port))

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send)
