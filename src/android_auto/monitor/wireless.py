"""Periodic WiFi and Bluetooth system-state collector."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from android_auto import adb
from android_auto.monitor.base import Monitor


class WirelessMonitor(Monitor):
    """Poll WiFi and Bluetooth dumpsys snapshots into one log file."""

    name = "wireless"
    error_filename = "wireless.log"

    def __init__(self, serial: str | None, output_dir: Path) -> None:
        super().__init__(output_dir)
        self.serial = serial
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        (self.output_dir / "wireless.log").write_text(
            "=== wireless monitor started ===\n", encoding="utf-8"
        )
        self._capture_once()
        self._thread = threading.Thread(
            target=self._poll,
            name="android-auto-wireless-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=6.0)
            if self._thread.is_alive():
                self.record_error("wireless polling thread did not stop before timeout")
            self._thread = None
        self._append("=== wireless monitor stopped ===")

    def _poll(self) -> None:
        while not self._stop_event.wait(1.0):
            self._capture_once()

    def _capture_once(self) -> None:
        for label, command in (
            ("WiFi", ["shell", "dumpsys", "wifi"]),
            ("Bluetooth", ["shell", "dumpsys", "bluetooth_manager"]),
        ):
            try:
                result = adb.run(
                    command,
                    serial=self.serial,
                    check=False,
                    timeout=5.0,
                )
            except Exception as exc:
                self.record_error(f"{label} collection failed: {exc}")
                continue
            timestamp = datetime.now(UTC).isoformat()
            if result.returncode != 0:
                detail = result.stderr.strip() or f"exit code {result.returncode}"
                self.record_error(f"{label} collection failed: {detail}")
                continue
            self._append(f"\n=== {label} {timestamp} ===\n{result.stdout}")

    def _append(self, text: str) -> None:
        path = self.output_dir / "wireless.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text.rstrip() + "\n")
