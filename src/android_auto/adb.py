"""Thin wrapper around the adb CLI."""
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)


def run(
    args: list[str],
    serial: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run an adb command. `args` excludes the leading 'adb'."""
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += args
    log.debug("exec: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"adb failed: {' '.join(cmd)}\n{result.stderr}")
    return result


def devices() -> list[str]:
    """Return serial numbers of devices in 'device' state."""
    result = run(["devices"])
    return [
        line.split()[0]
        for line in result.stdout.splitlines()[1:]
        if line.strip() and len(line.split()) >= 2 and line.split()[1] == "device"
    ]
