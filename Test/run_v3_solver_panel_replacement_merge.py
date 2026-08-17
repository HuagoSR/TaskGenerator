from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_behavioral_validation import (  # noqa: E402
    SolverToolPreflightReportV1,
)
from task_generator.v3_evaluation_calibration import SolverPanelMemberV1  # noqa: E402
from task_generator.v3_solver_panel_admission import (  # noqa: E402
    SolverPanelAdmissionCompiler,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Merge hash-bound retained and replacement preflight evidence into "
            "a final frozen solver panel. This runner makes no external calls."
        )
    )
    parser.add_argument("--admission-plan", type=Path, required=True)
    parser.add_argument("--replacement-boundary", type=Path, required=True)
    parser.add_argument("--replacement-authorization-request", type=Path, required=True)
    parser.add_argument("--retained-frozen-panel", type=Path, required=True)
    parser.add_argument("--retained-evidence-integrity", type=Path, required=True)
    parser.add_argument("--replacement-evidence-integrity", type=Path, required=True)
    parser.add_argument("--replacement-members", type=Path, required=True)
    parser.add_argument("--final-panel-id", required=True)
    parser.add_argument("--final-panel-output", type=Path, required=True)
    parser.add_argument("--merge-report-output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.replacement_members.read_text(encoding="utf-8"))
    members = []
    for item in payload.get("members", []):
        report_path = Path(item["preflight_report_path"]).resolve()
        members.append(
            SolverPanelMemberV1(
                solver_model=item["solver_model"],
                stratum=item["stratum"],
                preflight_report_path=str(report_path),
                preflight_report=SolverToolPreflightReportV1.model_validate_json(
                    report_path.read_text(encoding="utf-8")
                ),
                provider=item["provider"],
                maximum_cost_per_task_usd=item["maximum_cost_per_task_usd"],
            )
        )
    report = SolverPanelAdmissionCompiler().merge_replacement_evidence(
        admission_plan_path=args.admission_plan,
        replacement_boundary_path=args.replacement_boundary,
        replacement_authorization_request_path=args.replacement_authorization_request,
        retained_frozen_panel_path=args.retained_frozen_panel,
        retained_evidence_integrity_path=args.retained_evidence_integrity,
        replacement_evidence_integrity_path=args.replacement_evidence_integrity,
        replacement_members=members,
        final_panel_id=args.final_panel_id,
        output_panel_path=args.final_panel_output,
    )
    args.merge_report_output.parent.mkdir(parents=True, exist_ok=True)
    args.merge_report_output.write_text(
        report.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
