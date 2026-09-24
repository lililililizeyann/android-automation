"""Background Android logcat collector."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import BinaryIO

from android_auto.monitor.base import Monitor, MonitorError


class LogcatMonitor(Monitor):
    """Stream ``adb logcat`` into ``output/logcat.txt``."""

    name = "logcat"
    error_filename = "logcat.txt"

    def __init__(self, serial: str | None, output_dir: Path) -> None:
        super().__init__(output_dir)
        self.serial = serial
        self._process: subprocess.Popen[bytes] | None = None
        self._stream: BinaryIO | None = None

    def start(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._stream = (self.output_dir / "logcat.txt").open("wb")
        command = ["adb"]
        if self.serial:
            command += ["-s", self.serial]
        command += ["logcat"]
        try:
            self._process = subprocess.Popen(
                command,
                stdout=self._stream,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            self._close_stream()
            raise
        time.sleep(0.1)
        if self._process.poll() is not None:
            return_code = self._process.returncode
            self._close_stream()
            raise MonitorError(f"adb logcat exited immediately with code {return_code}")

    def stop(self) -> None:
        process = self._process
        if process is None:
            self._close_stream()
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5.0)
            elif process.returncode not in (0, -15):
                self.record_error(f"adb logcat exited with code {process.returncode}")
        finally:
            self._close_stream()
            self._process = None

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None
