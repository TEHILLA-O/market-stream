"""Optional IPC bridge to a kdb+ / KDB-X process.

Unlicensed PyKX can speak IPC, but it cannot embed q. This process never
claims to be running q unless a query round-trip succeeds.

If nothing is listening, the platform stays in Python reference mode.
"""

from __future__ import annotations

import socket

from marketstream.core.logging import get_logger
from marketstream.core.models import MarketEvent

log = get_logger("qbridge")


class QBridge:
    def __init__(self, host: str, port: int, enabled: bool) -> None:
        self.host = host
        self.port = port
        self.enabled = enabled
        self.mode = "python"
        self.connected = False
        self.detail = "Python reference mode. No q runtime is connected."
        self._conn = None
        self.published = 0
        self.failures = 0
        if enabled:
            self.probe()

    def probe(self) -> None:
        if not self.enabled:
            self.detail = "Q bridge disabled by MARKETSTREAM_Q_ENABLED=false. Python reference mode."
            return
        try:
            with socket.create_connection((self.host, self.port), timeout=0.3):
                pass
        except OSError:
            self.mode = "python"
            self.connected = False
            self.detail = (
                f"No q process is listening on {self.host}:{self.port}. "
                "Analytics, the tickerplant, and Query Lab are running the Python "
                "reference implementation. This is not kdb+."
            )
            return
        try:
            import os

            os.environ.setdefault("PYKX_UNLICENSED", "true")
            import pykx as kx

            self._conn = kx.SyncQConnection(host=self.host, port=self.port)
            self._conn("tables[]")
            self.mode = "kdb"
            self.connected = True
            self.detail = f"Connected to q at {self.host}:{self.port} through PyKX IPC."
            log.info("q_connected", host=self.host, port=self.port)
        except Exception as exc:  # noqa: BLE001 — connection failure must not stop the app
            self.mode = "python"
            self.connected = False
            self._conn = None
            self.detail = (
                f"A port is open at {self.host}:{self.port} but q IPC did not come up ({exc}). "
                "Staying in Python reference mode."
            )

    def publish(self, event: MarketEvent) -> None:
        if not self.connected or self._conn is None:
            return
        try:
            self._conn(
                "{[row] .ms.ingest row}",
                event.model_dump(mode="json"),
            )
            self.published += 1
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            self.connected = False
            self.mode = "python"
            self.detail = f"q ingest failed ({exc}). Fell back to Python reference mode."
            log.warning("q_publish_failed", error=str(exc))

    def query(self, expression: str):
        if not self.connected or self._conn is None:
            raise RuntimeError(self.detail)
        return self._conn(expression)

    def status(self) -> dict:
        return {
            "mode": self.mode,
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            "published": self.published,
            "failures": self.failures,
            "detail": self.detail,
            "engine": "kdb" if self.mode == "kdb" else "python-reference",
        }
