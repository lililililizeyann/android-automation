"""Best-effort tcpdump collector for device network activity."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import BinaryIO

from android_auto import adb
from android_auto.monitor.base import Monitor, MonitorError


class NetworkMonitor(Monitor):
    """Stream device tcpdump output into ``output/network.pcap``."""

    name = "network"
    error_filename = "network_error.txt"

    def __init__(self, serial: str | None, output_dir: Path) -> None:
        super().__init__(output_dir)
        self.serial = serial
        self._process: subprocess.Popen[bytes] | None = None
        self._pcap_stream: BinaryIO | None = None
        self._error_stream: BinaryIO | None = None

    def start(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "network.pcap").unlink(missing_ok=True)
        (self.output_dir / "network_error.txt").unlink(missing_ok=True)
        support = adb.run(
            ["shell", "command", "-v", "tcpdump"],
            serial=self.serial,
            check=False,
            timeout=15.0,
        )
        if support.returncode != 0 or not support.stdout.strip():
            detail = support.stderr.strip() or "tcpdump is not available on the device"
            self.record_error(detail)
            raise MonitorError(detail)

        self._pcap_stream = (self.output_dir / "network.pcap").open("wb")
        self._error_stream = (self.output_dir / "network_error.txt").open("ab")
        command = ["adb"]
        if self.serial:
            command += ["-s", self.serial]
        command += ["exec-out", "tcpdump", "-i", "any", "-w", "-"]
        try:
            self._process = subprocess.Popen(
                command,
                stdout=self._pcap_stream,
                stderr=self._error_stream,
            )
        except Exception:
            self._close_streams()
            raise
        time.sleep(0.2)
        if self._process.poll() is not None:
            return_code = self._process.returncode
            self._close_streams()
            raise MonitorError(f"tcpdump exited immediately with code {return_code}")

    def stop(self) -> None:
        process = self._process
        if process is None:
            self._close_streams()
            return
        try:
            was_running = process.poll() is None
            if was_running:
                process.terminate()
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5.0)
            elif process.returncode not in (0, -15):
                self.record_error(f"tcpdump exited with code {process.returncode}")
        finally:
            self._close_streams()
            self._process = None

    def _close_streams(self) -> None:
        if self._pcap_stream is not None:
            self._pcap_stream.close()
            self._pcap_stream = None
        if self._error_stream is not None:
            self._error_stream.close()
            self._error_stream = None
