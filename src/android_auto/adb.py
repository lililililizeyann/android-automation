"""Small, typed wrapper around the adb CLI.

This module owns all direct interaction with the ``adb`` executable.  Higher
layers should call these helpers instead of constructing subprocess commands.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

log = logging.getLogger(__name__)


class AdbError(RuntimeError):
    """Raised when an adb command fails or times out."""


def run(
    args: Sequence[str],
    serial: str | None = None,
    check: bool = True,
    timeout: float = 30.0,
) -> subprocess.CompletedProcess[str]:
    """Run an adb command. ``args`` excludes the leading ``adb``."""
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    log.debug("exec: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb timed out after {timeout:g}s: {' '.join(cmd)}") from exc
    if check and result.returncode != 0:
        raise AdbError(f"adb failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr}")
    return result


def run_bytes(
    args: Sequence[str],
    serial: str | None = None,
    check: bool = True,
    timeout: float = 30.0,
) -> bytes:
    """Run an adb command and return binary stdout."""
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    log.debug("exec: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb timed out after {timeout:g}s: {' '.join(cmd)}") from exc
    if check and result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")
        raise AdbError(f"adb failed ({result.returncode}): {' '.join(cmd)}\n{stderr}")
    return result.stdout


def devices() -> list[str]:
    """Return serial numbers of devices in 'device' state."""
    result = run(["devices"])
    return [
        line.split()[0]
        for line in result.stdout.splitlines()[1:]
        if line.strip() and len(line.split()) >= 2 and line.split()[1] == "device"
    ]


def install(apk_path: Path, serial: str | None = None) -> None:
    """Install an APK on the selected device."""
    run(["install", str(apk_path)], serial=serial, timeout=120.0)


def uninstall(package_name: str, serial: str | None = None) -> None:
    """Uninstall a package."""
    run(["uninstall", package_name], serial=serial, timeout=60.0)


def is_installed(package_name: str, serial: str | None = None) -> bool:
    """Return whether the package manager reports an installed package."""
    result = run(
        ["shell", "pm", "path", package_name],
        serial=serial,
        check=False,
        timeout=15.0,
    )
    return result.returncode == 0 and result.stdout.strip().startswith("package:")


def launch_app(package_name: str, serial: str | None = None) -> None:
    """Launch the package's launcher activity through the Android launcher."""
    run(
        ["shell", "monkey", "-p", package_name, "1"],
        serial=serial,
        timeout=30.0,
    )


def force_stop(package_name: str, serial: str | None = None) -> None:
    """Force-stop a package."""
    run(["shell", "am", "force-stop", package_name], serial=serial, timeout=30.0)


def tap(x: int, y: int, serial: str | None = None) -> None:
    """Tap a screen coordinate."""
    run(["shell", "input", "tap", str(x), str(y)], serial=serial, timeout=15.0)


def input_text(text: str, serial: str | None = None) -> None:
    """Send text through ``adb shell input text``."""
    encoded = text.replace("%", "%25").replace(" ", "%s")
    run(["shell", "input", "text", encoded], serial=serial, timeout=15.0)


def swipe(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 500,
    serial: str | None = None,
) -> None:
    """Swipe between two screen coordinates."""
    run(
        [
            "shell",
            "input",
            "swipe",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            str(duration_ms),
        ],
        serial=serial,
        timeout=15.0,
    )


def keyevent(key: str, serial: str | None = None) -> None:
    """Send an Android key event."""
    run(["shell", "input", "keyevent", key], serial=serial, timeout=15.0)


def dump_ui(local_path: Path, serial: str | None = None) -> None:
    """Dump the current UI hierarchy and pull it to ``local_path``."""
    remote_path = "/sdcard/android_auto_window.xml"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        ["shell", "uiautomator", "dump", remote_path],
        serial=serial,
        timeout=30.0,
    )
    run(
        ["pull", remote_path, str(local_path)],
        serial=serial,
        timeout=30.0,
    )


def screenshot(local_path: Path, serial: str | None = None) -> None:
    """Capture a PNG screenshot to ``local_path``."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    data = run_bytes(
        ["exec-out", "screencap", "-p"],
        serial=serial,
        timeout=30.0,
    )
    local_path.write_bytes(data)


def is_foreground(package_name: str, serial: str | None = None) -> bool:
    """Return whether Android reports ``package_name`` as the foreground app."""
    activity = run(
        ["shell", "dumpsys", "activity", "activities"],
        serial=serial,
        check=False,
        timeout=20.0,
    ).stdout
    window = run(
        ["shell", "dumpsys", "window", "windows"],
        serial=serial,
        check=False,
        timeout=20.0,
    ).stdout
    package_pattern = re.compile(rf"(?<![\w.]){re.escape(package_name)}(?:[/\s]|$)")
    return any(
        package_pattern.search(line)
        for line in (*activity.splitlines(), *window.splitlines())
        if "mResumedActivity" in line
        or "mFocusedApp" in line
        or "mCurrentFocus" in line
        or "mFocusedWindow" in line
    )
