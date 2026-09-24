import json
from pathlib import Path

import pytest

from android_auto import adb
from android_auto.monitor import Monitor, MonitorManager, MonitorSettings
from android_auto.workflow import S1Workflow, WorkflowConfig, WorkflowError


def write_config(config_path: Path, **overrides: object) -> None:
    data: dict[str, object] = {
        "apk_path": "data/ApiDemos-debug.apk",
        "package_name": "io.appium.android.apis",
    }
    data.update(overrides)
    config_path.parent.mkdir()
    config_path.write_text(json.dumps(data), encoding="utf-8")


def test_workflow_config_defaults_to_project_output(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "config.json"
    write_config(config_path)

    config = WorkflowConfig.from_json(config_path)

    assert config.output_dir == tmp_path / "output"


def test_workflow_config_resolves_explicit_output_dir(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "config.json"
    write_config(config_path, output_dir="output")

    config = WorkflowConfig.from_json(config_path)

    assert config.output_dir == tmp_path / "output"


def test_workflow_config_rejects_empty_output_dir(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "config.json"
    write_config(config_path, output_dir="")

    with pytest.raises(WorkflowError, match="config.output_dir"):
        WorkflowConfig.from_json(config_path)


def test_workflow_config_parses_monitor_flags(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "config.json"
    write_config(
        config_path,
        monitor={"logcat": False, "network": True, "wireless": False},
    )

    config = WorkflowConfig.from_json(config_path)

    assert config.monitor == MonitorSettings(logcat=False, network=True, wireless=False)


class RecordingMonitor(Monitor):
    name = "recording"
    error_filename = "recording.log"

    def __init__(self, output_dir: Path, events: list[str]) -> None:
        super().__init__(output_dir)
        self.events = events

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")


class FailingMonitor(Monitor):
    name = "failing"
    error_filename = "failing.log"

    def __init__(self, output_dir: Path) -> None:
        super().__init__(output_dir)

    def start(self) -> None:
        raise RuntimeError("not available")

    def stop(self) -> None:
        raise RuntimeError("stop failed")


def test_monitor_interface_and_manager_lifecycle(tmp_path: Path) -> None:
    events: list[str] = []
    manager = MonitorManager(
        [FailingMonitor(tmp_path / "output"), RecordingMonitor(tmp_path / "output", events)]
    )

    manager.start_all()
    manager.stop_all()
    manager.stop_all()

    assert events == ["start", "stop"]
    assert len(manager.failures) == 2
    assert "failing start failed" in manager.failures[0]
    assert "failing stop failed" in manager.failures[1]
    assert "not available" in (tmp_path / "output" / "failing.log").read_text(encoding="utf-8")


def test_monitor_failure_is_non_fatal_to_manager(tmp_path: Path) -> None:
    events: list[str] = []
    manager = MonitorManager(
        [FailingMonitor(tmp_path / "output"), RecordingMonitor(tmp_path / "output", events)]
    )

    manager.start_all()

    assert events == ["start"]
    assert manager.failures


def test_workflow_monitor_failure_does_not_fail_s1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    apk_path = tmp_path / "ApiDemos-debug.apk"
    apk_path.write_bytes(b"apk")
    output_dir = tmp_path / "output"
    config = WorkflowConfig(
        apk_path=apk_path,
        package_name="io.appium.android.apis",
        output_dir=output_dir,
    )
    workflow = S1Workflow(config)
    workflow.serial = "test-device"
    manager = MonitorManager([FailingMonitor(output_dir)])

    monkeypatch.setattr(
        MonitorManager,
        "from_settings",
        classmethod(lambda cls, settings, serial, output: manager),
    )

    workflow._start_monitors()
    workflow._stop_monitors()

    assert manager.failures


def test_collect_output_writes_files_directly_to_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    config = WorkflowConfig(
        apk_path=tmp_path / "ApiDemos-debug.apk",
        package_name="io.appium.android.apis",
        output_dir=output_dir,
    )
    workflow = S1Workflow(config)

    def fake_dump_ui(local_path: Path, serial: str | None = None) -> None:
        local_path.write_text("<hierarchy />", encoding="utf-8")

    def fake_screenshot(local_path: Path, serial: str | None = None) -> None:
        local_path.write_bytes(b"PNG")

    monkeypatch.setattr(adb, "dump_ui", fake_dump_ui)
    monkeypatch.setattr(adb, "screenshot", fake_screenshot)

    workflow._collect_output()

    assert (output_dir / "ui.xml").read_text(encoding="utf-8") == "<hierarchy />"
    assert (output_dir / "screenshot.png").read_bytes() == b"PNG"
    assert {path.name for path in output_dir.iterdir()} == {"ui.xml", "screenshot.png"}
