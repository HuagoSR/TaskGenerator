"""Write the read-only GDPval-to-R10 compiler calibration report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from task_generator.evaluation.r10_gdpval_calibration import build_r10_gdpval_calibration_report


FROZEN_TASK_ROOTS = [
    ROOT / "artifacts/r10/r10_6_task_compilation_20260831_execute3/tasks/r10_audit_revenue_evidence_reliability",
    ROOT / "artifacts/r10/r10_6_task_compilation_20260831_execute3/tasks/r10_procurement_price_reasonableness",
    ROOT / "artifacts/r10/r10_7a_task_compilation_20260831/tasks/r10_audit_control_deficiency_evaluation",
    ROOT / "artifacts/r10/r10_7a_task_compilation_20260831/tasks/r10_procurement_delivery_acceptance",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/r10/r10_8b2_gdpval_calibration/report.json")
    args = parser.parse_args()
    report = build_r10_gdpval_calibration_report(
        task_roots=FROZEN_TASK_ROOTS,
        gdpval_distribution_path=ROOT / "artifacts/phase14/gdpval_anatomy/gdpval_task_anatomy_distribution.json",
        discrimination_path=ROOT / "artifacts/r10/r10_8b1_pilot_discrimination_20260901/report.json",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": "pass", "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
