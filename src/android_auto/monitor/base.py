"""Common monitor interface and error-output helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Monitor(ABC):
    """A best-effort runtime collector with an explicit lifecycle."""

    name = "monitor"
    error_filename: str | None = None

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    @property
    def error_path(self) -> Path | None:
        if self.error_filename is None:
            return None
        return self.output_dir / self.error_filename

    @abstractmethod
    def start(self) -> None:
        """Start collecting data."""

    @abstractmethod
    def stop(self) -> None:
        """Stop collecting data and release resources."""

    def record_error(self, message: str) -> None:
        """Append a human-readable monitor error without raising it."""
        path = self.error_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[monitor error] {message}\n")


class MonitorError(RuntimeError):
    """Raised internally when a monitor cannot start or stop cleanly."""
