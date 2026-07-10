import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase14_postmortem import (  # noqa: E402
    Phase14PostmortemBuilder,
    Phase14PostmortemRequest,
)


PHASE14 = ROOT / "artifacts" / "phase14"
DEFAULT_CLEAN_BASELINE = PHASE14 / "gdpval_clean_baseline" / "gdpval_clean_baseline_report.json"
DEFAULT_GAP_AUTOPSY = PHASE14 / "gdpval_gap_autopsy" / "gdpval_gap_autopsy_report.json"
DEFAULT_DASHBOARD = PHASE14 / "good_task_dashboard" / "good_task_dashboard_report.json"
DEFAULT_LLM_IMPACT = PHASE14 / "llm_impact" / "llm_impact_evaluation_report.json"
DEFAULT_LLM_ADOPTION = PHASE14 / "llm_impact" / "llm_adoption_recommendation_report.json"
DEFAULT_OUTPUT = PHASE14 / "postmortem"
DEFAULT_HANDOFF = (
    ROOT
    / "artifacts"
    / "historical_phase_runs"
    / "phase14"
    / "PHASE_14_GDPTASK_CALIBRATION_BLOCKED_2026-07-08.md"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 14 postmortem and Phase 15 decision handoff.")
    parser.add_argument("--clean-baseline-path", type=Path, default=DEFAULT_CLEAN_BASELINE)
    parser.add_argument("--gap-autopsy-path", type=Path, default=DEFAULT_GAP_AUTOPSY)
    parser.add_argument("--dashboard-path", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--llm-impact-path", type=Path, default=DEFAULT_LLM_IMPACT)
    parser.add_argument("--llm-adoption-path", type=Path, default=DEFAULT_LLM_ADOPTION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--handoff-path", type=Path, default=DEFAULT_HANDOFF)
    args = parser.parse_args()
    request = Phase14PostmortemRequest(
        clean_baseline_path=str(args.clean_baseline_path),
        gap_autopsy_path=str(args.gap_autopsy_path),
        dashboard_path=str(args.dashboard_path),
        llm_impact_path=str(args.llm_impact_path),
        llm_adoption_path=str(args.llm_adoption_path),
        output_dir=str(args.output_dir),
        handoff_path=str(args.handoff_path),
    )
    report = Phase14PostmortemBuilder().build(request)
    print(
        json.dumps(
            {
                "phase14_decision": report.phase14_decision,
                "phase15_recommendation": report.phase15_recommendation,
                "criterion_statuses": {item.criterion_id: item.status for item in report.success_criteria},
                "blockers": report.blockers,
                "report_path": str(Path(args.output_dir) / "phase14_postmortem_report.json"),
                "handoff_path": report.handoff_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
