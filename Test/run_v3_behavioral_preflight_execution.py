from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_behavioral_preflight_execution import (  # noqa: E402
    BehavioralPreflightExecutor,
    behavioral_preflight_exit_code,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or execute V2-authorized public solver tool preflights. "
            "Default is non-executable dry-run."
        )
    )
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--authorization-receipt", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--real-world-python",
        type=Path,
        default=Path(r"D:\miniconda3\envs\real-world-task\python.exe"),
    )
    parser.add_argument(
        "--rw-task-root",
        type=Path,
        default=Path(r"E:\THU\2026Spring\SRT\rw-task"),
    )
    parser.add_argument("--run-external", action="store_true")
    args = parser.parse_args()
    result = BehavioralPreflightExecutor(args.campaign_root).execute(
        authorization_receipt_path=args.authorization_receipt,
        input_root=args.input_root,
        output_root=args.output_root,
        real_world_python=args.real_world_python,
        rw_task_root=args.rw_task_root,
        run_external=args.run_external,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return behavioral_preflight_exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
