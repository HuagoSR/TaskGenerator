from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_behavioral_validation import (  # noqa: E402
    SolverToolPreflightReportV1,
)
from task_generator.v3_evaluation_calibration import (  # noqa: E402
    EvaluationCalibrationCompiler,
    GraderScoreObservationV1,
    ProfessionalValidityReviewV1,
    SolverPanelMemberV1,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze solver-panel or analyze grader/professional evidence. "
            "This utility makes no provider, solver or grader calls."
        )
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "freeze-panel",
            "grader-stability",
            "validate-professional-review",
        ],
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--panel-id", default="r6_frozen_solver_panel")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    compiler = EvaluationCalibrationCompiler()
    if args.action == "freeze-panel":
        members = []
        for item in payload.get("members", []):
            preflight_path = Path(item["preflight_report_path"])
            members.append(
                SolverPanelMemberV1(
                    solver_model=item["solver_model"],
                    stratum=item["stratum"],
                    preflight_report_path=str(preflight_path.resolve()),
                    preflight_report=(
                        SolverToolPreflightReportV1.model_validate_json(
                            preflight_path.read_text(encoding="utf-8")
                        )
                    ),
                    provider=item["provider"],
                    maximum_cost_per_task_usd=(
                        item["maximum_cost_per_task_usd"]
                    ),
                )
            )
        result = compiler.freeze_solver_panel(
            panel_id=args.panel_id,
            members=members,
        )
    elif args.action == "grader-stability":
        records = payload.get("observations", payload)
        result = compiler.analyze_grader_stability(
            observations=[
                GraderScoreObservationV1.model_validate(item)
                for item in records
            ]
        )
    else:
        result = ProfessionalValidityReviewV1.model_validate(payload)
    _write(args.output, result.model_dump(mode="json"))
    print(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )
    decision = getattr(result, "decision", None)
    if decision in {"blocked", "not_evaluated"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
