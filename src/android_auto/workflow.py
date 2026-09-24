"""Orchestration for the Android ApiDemos S1 workflow."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from android_auto import adb
from android_auto.monitor import MonitorManager, MonitorSettings
from android_auto.ui import UiNode, first_scrollable, first_text_node, parse_nodes


class WorkflowError(RuntimeError):
    """Raised when the S1 workflow cannot complete."""


@dataclass(frozen=True)
class WorkflowConfig:
    apk_path: Path
    package_name: str
    interact_rounds: int = 3
    interact_interval: float = 0.5
    device_serial: str | None = None
    output_dir: Path = Path("output")
    monitor: MonitorSettings = field(default_factory=MonitorSettings)

    @classmethod
    def from_json(cls, config_path: Path) -> WorkflowConfig:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise WorkflowError(f"Configuration must be a JSON object: {config_path}")

        project_root = config_path.parent.parent
        apk_value = data.get("apk_path")
        package_value = data.get("package_name")
        if not isinstance(apk_value, str) or not apk_value:
            raise WorkflowError("config.apk_path must be a non-empty string")
        if not isinstance(package_value, str) or not package_value:
            raise WorkflowError("config.package_name must be a non-empty string")

        apk_path = Path(apk_value)
        if not apk_path.is_absolute():
            apk_path = project_root / apk_path
        output_value = data.get("output_dir", "output")
        if not isinstance(output_value, str) or not output_value:
            raise WorkflowError("config.output_dir must be a non-empty string")
        output_dir = Path(output_value)
        if not output_dir.is_absolute():
            output_dir = project_root / output_dir

        serial_value = data.get("device_serial", "")
        if not isinstance(serial_value, str):
            raise WorkflowError("config.device_serial must be a string")
        rounds_value = data.get("interact_rounds", 3)
        interval_value = data.get("interact_interval", 0.5)
        if not isinstance(rounds_value, int) or rounds_value < 2:
            raise WorkflowError("config.interact_rounds must be an integer >= 2")
        if not isinstance(interval_value, (int, float)) or interval_value < 0:
            raise WorkflowError("config.interact_interval must be >= 0")
        monitor_value = data.get("monitor", {})
        if not isinstance(monitor_value, Mapping):
            raise WorkflowError("config.monitor must be an object")
        try:
            monitor_settings = MonitorSettings.from_mapping(monitor_value)
        except ValueError as exc:
            raise WorkflowError(str(exc)) from exc

        return cls(
            apk_path=apk_path,
            package_name=package_value,
            interact_rounds=rounds_value,
            interact_interval=float(interval_value),
            device_serial=serial_value or None,
            output_dir=output_dir,
            monitor=monitor_settings,
        )


class S1Workflow:
    """Run one clean, repeatable ApiDemos install-to-uninstall cycle."""

    def __init__(self, config: WorkflowConfig) -> None:
        self.config = config
        self.serial: str | None = config.device_serial
        self.app_may_be_installed = False
        self.cleanup_errors: list[str] = []
        self.interaction_count = 0
        self.monitor_manager: MonitorManager | None = None

    def run(self) -> None:
        """Run the workflow and raise one error if the run or cleanup fails."""
        self._step(1, "Checking device and APK", self._check_prerequisites)
        primary_error: Exception | None = None
        try:
            self._step(2, "Removing previous installation", self._remove_previous)
            self._step(3, "Installing ApiDemos", self._install)
            self._step(4, "Verifying installation", self._verify_install)
            self._step(5, "Launching ApiDemos", self._launch)
            self._step(6, "Waiting for app", self._wait_for_app)
            self._step(7, "Starting monitors", self._start_monitors)
            self._step(8, "Interacting with UI", self._interact)
            self._step(9, "Stopping monitors", self._stop_monitors)
            self._step(10, "Saving XML and screenshot", self._collect_output)
        except Exception as exc:  # cleanup must run for every post-install failure
            primary_error = exc
            self._save_failure_output()
        finally:
            self._stop_monitors()
            self._cleanup()

        if primary_error is not None:
            detail = str(primary_error)
            if self.cleanup_errors:
                detail += f"; cleanup errors: {'; '.join(self.cleanup_errors)}"
            raise WorkflowError(detail) from primary_error
        if self.cleanup_errors:
            raise WorkflowError(f"cleanup failed: {'; '.join(self.cleanup_errors)}")
        if self.monitor_manager is not None and self.monitor_manager.failures:
            for failure in self.monitor_manager.failures:
                print(f"Monitor warning: {failure}", flush=True)
        print("S1 workflow completed successfully.", flush=True)

    def _step(self, number: int, label: str, action: Callable[[], None]) -> None:
        print(f"[{number}/12] {label}...", flush=True)
        action()

    def _start_monitors(self) -> None:
        if self.serial is None:
            raise WorkflowError("Cannot start monitors before selecting a device")
        self.monitor_manager = MonitorManager.from_settings(
            self.config.monitor,
            self.serial,
            self.config.output_dir,
        )
        self.monitor_manager.start_all()

    def _stop_monitors(self) -> None:
        if self.monitor_manager is not None:
            self.monitor_manager.stop_all()

    def _check_prerequisites(self) -> None:
        available = adb.devices()
        if self.serial is not None:
            if self.serial not in available:
                raise WorkflowError(
                    f"Configured device {self.serial!r} is not available; connected: {available}"
                )
        elif len(available) == 1:
            self.serial = available[0]
        elif not available:
            raise WorkflowError("No authorized Android device is connected")
        else:
            raise WorkflowError(f"Multiple devices connected; set device_serial: {available}")

        if not self.config.apk_path.is_file():
            raise WorkflowError(f"APK does not exist: {self.config.apk_path}")
        if self.config.apk_path.stat().st_size == 0:
            raise WorkflowError(f"APK is empty: {self.config.apk_path}")
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        for stale_name in ("failure_ui.xml", "failure_screenshot.png"):
            (self.config.output_dir / stale_name).unlink(missing_ok=True)

    def _remove_previous(self) -> None:
        if not adb.is_installed(self.config.package_name, self.serial):
            print("  No previous installation found.", flush=True)
            return
        self.app_may_be_installed = True
        adb.force_stop(self.config.package_name, self.serial)
        adb.uninstall(self.config.package_name, self.serial)
        if adb.is_installed(self.config.package_name, self.serial):
            raise WorkflowError("Previous installation is still present after uninstall")

    def _install(self) -> None:
        self.app_may_be_installed = True
        adb.install(self.config.apk_path, self.serial)

    def _verify_install(self) -> None:
        if not adb.is_installed(self.config.package_name, self.serial):
            raise WorkflowError(f"Package is not installed: {self.config.package_name}")

    def _launch(self) -> None:
        adb.launch_app(self.config.package_name, self.serial)

    def _wait_for_app(self) -> None:
        if not self._wait_until(
            lambda: adb.is_foreground(self.config.package_name, self.serial),
            timeout=15.0,
        ):
            raise WorkflowError(f"App did not become foreground: {self.config.package_name}")

    def _interact(self) -> None:
        before_path = self.config.output_dir / "before_interaction.xml"
        views = self._wait_for_text_node(("Views",), before_path)
        self._tap_node(views)
        self._pause()

        current_path = self.config.output_dir / "after_views.xml"
        target = self._wait_for_text_node(
            ("Buttons", "TextFields", "Dialogs", "Controls"),
            current_path,
        )
        self._tap_node(target)
        self._pause()

        for _ in range(max(0, self.config.interact_rounds - self.interaction_count)):
            round_path = self.config.output_dir / f"interaction_{self.interaction_count}.xml"
            adb.dump_ui(round_path, self.serial)
            nodes = parse_nodes(round_path)
            scrollable = first_scrollable(nodes)
            if scrollable is not None and scrollable.bounds.bottom - scrollable.bounds.top > 100:
                left, top, right, bottom = (
                    scrollable.bounds.left,
                    scrollable.bounds.top,
                    scrollable.bounds.right,
                    scrollable.bounds.bottom,
                )
                x = (left + right) // 2
                adb.swipe(x, bottom - 120, x, top + 120, serial=self.serial)
                self.interaction_count += 1
                self._pause()
                continue

            buttons = [
                node
                for node in nodes
                if node.clickable
                and node.enabled
                and node.text
                and node.class_name
                in {"android.widget.Button", "android.widget.ToggleButton"}
            ]
            if not buttons:
                break
            button_index = max(0, self.interaction_count - 2) % len(buttons)
            button = buttons[button_index]
            self._tap_node(button)
            self._pause()

        if self.interaction_count < 2:
            raise WorkflowError("Fewer than two UI interactions were completed")

    def _wait_for_text_node(self, candidates: tuple[str, ...], path: Path) -> UiNode:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            adb.dump_ui(path, self.serial)
            nodes = parse_nodes(path)
            node = first_text_node(nodes, candidates)
            if node is not None:
                return node
            time.sleep(0.5)
        raise WorkflowError(f"Timed out waiting for UI text: {', '.join(candidates)}")

    def _collect_output(self) -> None:
        ui_path = self.config.output_dir / "ui.xml"
        screenshot_path = self.config.output_dir / "screenshot.png"
        adb.dump_ui(ui_path, self.serial)
        adb.screenshot(screenshot_path, self.serial)
        self._assert_non_empty(ui_path, "UI XML")
        self._assert_non_empty(screenshot_path, "screenshot")

    def _cleanup(self) -> None:
        if not self.app_may_be_installed or self.serial is None:
            return
        print("[11/12] Stopping application...", flush=True)
        try:
            adb.force_stop(self.config.package_name, self.serial)
        except Exception as exc:
            self.cleanup_errors.append(f"force-stop: {exc}")

        print("[12/12] Uninstalling and verifying...", flush=True)
        try:
            if adb.is_installed(self.config.package_name, self.serial):
                adb.uninstall(self.config.package_name, self.serial)
            if adb.is_installed(self.config.package_name, self.serial):
                raise WorkflowError("Package is still installed after cleanup")
        except Exception as exc:
            self.cleanup_errors.append(f"uninstall: {exc}")

    def _save_failure_output(self) -> None:
        """Best-effort capture of the device state before cleanup."""
        try:
            adb.dump_ui(self.config.output_dir / "failure_ui.xml", self.serial)
        except Exception as exc:
            self.cleanup_errors.append(f"failure UI capture: {exc}")
        try:
            adb.screenshot(self.config.output_dir / "failure_screenshot.png", self.serial)
        except Exception as exc:
            self.cleanup_errors.append(f"failure screenshot capture: {exc}")

    def _tap_node(self, node: UiNode) -> None:
        x, y = node.bounds.center
        adb.tap(x, y, self.serial)
        self.interaction_count += 1

    def _pause(self) -> None:
        if self.config.interact_interval:
            time.sleep(self.config.interact_interval)

    @staticmethod
    def _assert_non_empty(path: Path, label: str) -> None:
        if not path.is_file() or path.stat().st_size == 0:
            raise WorkflowError(f"{label} is missing or empty: {path}")

    @staticmethod
    def _wait_until(predicate: Callable[[], bool], timeout: float, interval: float = 0.5) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(interval)
        return predicate()
