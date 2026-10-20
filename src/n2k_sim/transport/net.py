"""Output transports: UDP broadcast/unicast with batching, TCP server, file recorder."""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

UDP_MAX_DATAGRAM = 1400
UDP_FLUSH_INTERVAL = 0.05  # s
TCP_MAX_BUFFER = 1_000_000  # bytes queued per client before it is dropped


class RateMeter:
    """Bytes per second over a sliding 2 s window."""

    def __init__(self, window: float = 2.0):
        self._window = window
        self._events: deque[tuple[float, int]] = deque()

    def add(self, n: int) -> None:
        now = time.monotonic()
        self._events.append((now, n))
        while self._events and now - self._events[0][0] > self._window:
            self._events.popleft()

    @property
    def rate(self) -> float:
        now = time.monotonic()
        while self._events and now - self._events[0][0] > self._window:
            self._events.popleft()
        return sum(n for _, n in self._events) / self._window


@dataclass
class Status:
    enabled: bool
    host: str
    port: int
    bytes_per_s: float = 0.0
    clients: int = 0
    error: str | None = None


class UdpOutput:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self._sock: socket.socket | None = None
        self._buffer = bytearray()
        self._last_flush = time.monotonic()
        self._meter = RateMeter()
        self.error: str | None = None

    async def start(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setblocking(False)
            self._sock = sock
            self.error = None
        except OSError as e:
            self.error = str(e)

    def send(self, lines: list[bytes]) -> None:
        """Queues complete lines; flushes when a datagram is full or the flush interval passed."""
        for line in lines:
            if len(self._buffer) + len(line) > UDP_MAX_DATAGRAM:
                self._flush()
            self._buffer += line
        if time.monotonic() - self._last_flush >= UDP_FLUSH_INTERVAL:
            self._flush()

    def _flush(self) -> None:
        self._last_flush = time.monotonic()
        if not self._buffer or self._sock is None:
            self._buffer.clear()
            return
        try:
            self._sock.sendto(bytes(self._buffer), (self.host, self.port))
            self._meter.add(len(self._buffer))
            self.error = None
        except OSError as e:
            if self.error != str(e):
                log.warning("UDP send to %s:%s failed: %s", self.host, self.port, e)
            self.error = str(e)
        self._buffer.clear()

    async def stop(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None

    def status(self) -> Status:
        return Status(True, self.host, self.port, self._meter.rate, 0, self.error)


class TcpOutput:
    """TCP server streaming to all connected clients; anything clients send is discarded."""

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self._server: asyncio.base_events.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._meter = RateMeter()
        self.error: str | None = None

    async def start(self) -> None:
        try:
            self._server = await asyncio.start_server(self._handle, self.host, self.port, reuse_address=True)
            self.error = None
        except OSError as e:
            self.error = str(e)
            log.warning("TCP server on %s:%s failed: %s", self.host, self.port, e)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.add(writer)
        log.info("TCP client connected: %s", writer.get_extra_info("peername"))
        try:
            while await reader.read(4096):
                pass  # input is ignored
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self._drop(writer)

    def _drop(self, writer: asyncio.StreamWriter) -> None:
        if writer in self._clients:
            self._clients.discard(writer)
            writer.close()

    def send(self, lines: list[bytes]) -> None:
        if not self._clients or not lines:
            return
        data = b"".join(lines)
        for writer in list(self._clients):
            transport = writer.transport
            if transport.is_closing() or transport.get_write_buffer_size() > TCP_MAX_BUFFER:
                self._drop(writer)
                continue
            writer.write(data)
            self._meter.add(len(data))

    async def stop(self) -> None:
        for writer in list(self._clients):
            self._drop(writer)
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def status(self) -> Status:
        return Status(True, self.host, self.port, self._meter.rate, len(self._clients), self.error)


class Recorder:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path: Path | None = None
        self._file = None

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.path = self.directory / f"{stamp}.raw"
        self._file = self.path.open("ab")

    def send(self, lines: list[bytes]) -> None:
        if self._file:
            self._file.write(b"".join(lines))

    def stop(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
