import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_evidence_to_deliverable_redesign import (  # noqa: E402
    Phase16EvidenceToDeliverableRedesignBuilder,
    Phase16RedesignRequest,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Phase 16 evidence_to_deliverable redesign, alignment, pre-eval, and postmortem reports."
    )
    parser.add_argument("--phase16-plan", type=Path, default=ROOT / "docs" / "architecture" / "phase16_evidence_to_deliverable_redesign_plan.md")
    parser.add_argument("--phase15-handoff", type=Path, default=ROOT / "docs" / "handoffs" / "PHASE_15B_COMPLETION_2026-07-09.md")
    parser.add_argument("--phase15-strong-eval", type=Path, default=ROOT / "artifacts" / "phase15" / "eval_results" / "phase15_strong_model_eval_report.json")
    parser.add_argument("--phase15-gap-delta", type=Path, default=ROOT / "artifacts" / "phase15" / "eval_results" / "phase15_gap_delta_report.json")
    parser.add_argument("--phase15-failure-autopsy", type=Path, default=ROOT / "artifacts" / "phase15" / "failure_autopsy" / "phase15_reform_failure_autopsy_report.json")
    parser.add_argument("--phase15-postmortem", type=Path, default=ROOT / "artifacts" / "phase15" / "phase15b_closeout" / "phase15b_postmortem_report.json")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts" / "phase16")
    parser.add_argument("--contract-path", type=Path, default=ROOT / "SkillRegistry" / "evidence_to_deliverable_contract_v2.experimental.json")
    parser.add_argument("--baseline-handoff", type=Path, default=ROOT / "docs" / "handoffs" / "PHASE_16_BASELINE_2026-07-10.md")
    parser.add_argument(
        "--completion-handoff",
        type=Path,
        default=ROOT / "docs" / "handoffs" / "PHASE_16_EVIDENCE_TO_DELIVERABLE_REDESIGN_BLOCKED_2026-07-10.md",
    )
    parser.add_argument(
        "--allow-external-eval",
        action="store_true",
        help="Record that scoped external eval is allowed. This runner still does not call external APIs.",
    )
    parser.add_argument(
        "--external-eval-results",
        type=Path,
        default=None,
        help="Optional JSON file containing imported Phase 16 clean paired eval records.",
    )
    args = parser.parse_args()

    report = Phase16EvidenceToDeliverableRedesignBuilder().build(
        Phase16RedesignRequest(
            phase16_plan_path=str(args.phase16_plan),
            phase15_handoff_path=str(args.phase15_handoff),
            phase15_strong_eval_path=str(args.phase15_strong_eval),
            phase15_gap_delta_path=str(args.phase15_gap_delta),
            phase15_failure_autopsy_path=str(args.phase15_failure_autopsy),
            phase15_postmortem_path=str(args.phase15_postmortem),
            output_root=str(args.output_root),
            contract_path=str(args.contract_path),
            baseline_handoff_path=str(args.baseline_handoff),
            completion_handoff_path=str(args.completion_handoff),
            allow_external_eval=args.allow_external_eval,
            external_eval_results_path=str(args.external_eval_results) if args.external_eval_results else None,
        )
    )
    print(
        json.dumps(
            {
                "phase16_decision": report.phase16_decision,
                "phase17_recommendation": report.phase17_recommendation,
                "contract_v2_created": report.summary.get("contract_v2_created"),
                "negative_controls": f"{report.summary.get('negative_controls_detected')}/{report.summary.get('negative_controls_total')}",
                "external_eval_run": report.summary.get("external_eval_run"),
                "phase16_report": report.outputs.get("phase16_report"),
                "phase16_postmortem_handoff": report.outputs.get("phase16_postmortem_handoff"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
