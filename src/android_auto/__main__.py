"""Command-line entry point for the Android ApiDemos S1 workflow."""

from __future__ import annotations

import sys
from pathlib import Path

from android_auto.adb import AdbError
from android_auto.workflow import S1Workflow, WorkflowConfig, WorkflowError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"


def main() -> int:
    try:
        config = WorkflowConfig.from_json(CONFIG_PATH)
        S1Workflow(config).run()
    except (AdbError, OSError, ValueError, WorkflowError) as exc:
        print(f"S1 workflow failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
