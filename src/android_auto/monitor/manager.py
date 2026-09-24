"""Lifecycle orchestration for optional runtime monitors."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from android_auto.monitor.base import Monitor
from android_auto.monitor.logcat import LogcatMonitor
from android_auto.monitor.network import NetworkMonitor
from android_auto.monitor.wireless import WirelessMonitor


@dataclass(frozen=True)
class MonitorSettings:
    """Feature flags parsed from the top-level workflow configuration."""

    logcat: bool = True
    network: bool = True
    wireless: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, object] | None) -> MonitorSettings:
        if value is None:
            return cls()
        settings: dict[str, bool] = {}
        for name in ("logcat", "network", "wireless"):
            raw = value.get(name, True)
            if not isinstance(raw, bool):
                raise ValueError(f"config.monitor.{name} must be a boolean")
            settings[name] = raw
        return cls(**settings)


class MonitorManager:
    """Start and stop monitors without allowing them to fail the S1 workflow."""

    def __init__(self, monitors: Iterable[Monitor]) -> None:
        self.monitors = list(monitors)
        self.failures: list[str] = []
        self._started = False
        self._stopped = False

    @classmethod
    def from_settings(
        cls,
        settings: MonitorSettings,
        serial: str | None,
        output_dir: Path,
    ) -> MonitorManager:
        monitors: list[Monitor] = []
        if settings.logcat:
            monitors.append(LogcatMonitor(serial, output_dir))
        if settings.network:
            monitors.append(NetworkMonitor(serial, output_dir))
        if settings.wireless:
            monitors.append(WirelessMonitor(serial, output_dir))
        return cls(monitors)

    def start_all(self) -> None:
        """Attempt every enabled monitor; one failure does not stop the others."""
        if self._started:
            return
        self._started = True
        self._stopped = False
        for monitor in self.monitors:
            try:
                monitor.start()
            except Exception as exc:
                self._record_failure(monitor, "start", exc)

    def stop_all(self) -> None:
        """Stop every monitor, including one whose start may have failed."""
        if self._stopped:
            return
        self._stopped = True
        for monitor in reversed(self.monitors):
            try:
                monitor.stop()
            except Exception as exc:
                self._record_failure(monitor, "stop", exc)

    def _record_failure(self, monitor: Monitor, phase: str, error: Exception) -> None:
        message = f"{monitor.name} {phase} failed: {error}"
        self.failures.append(message)
        try:
            monitor.record_error(message)
        except Exception as record_error:
            self.failures.append(f"{monitor.name} error recording failed: {record_error}")
