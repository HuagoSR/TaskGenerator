import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_baseline import (  # noqa: E402
    Phase15BaselineBuilder,
    Phase15BaselineRequest,
)


PHASE14 = ROOT / "artifacts" / "phase14"
PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_POSTMORTEM = PHASE14 / "postmortem" / "phase14_postmortem_report.json"
DEFAULT_DASHBOARD = PHASE14 / "good_task_dashboard" / "good_task_dashboard_report.json"
DEFAULT_GDPVAL_GAP = PHASE14 / "gdpval_clean_baseline" / "gdpval_clean_gap_profile.json"
DEFAULT_GENERATED_GAP = PHASE14 / "generated_task_comparison_eval_summary" / "generated_task_gap_profile.json"
DEFAULT_GENERATED_VS_GDPVAL = PHASE14 / "generated_vs_gdpval" / "generated_vs_gdpval_gap_report.json"
DEFAULT_LLM_IMPACT = PHASE14 / "llm_impact" / "llm_impact_evaluation_report.json"
DEFAULT_LLM_ADOPTION = PHASE14 / "llm_impact" / "llm_adoption_recommendation_report.json"
DEFAULT_OUTPUT = PHASE15 / "baseline"
DEFAULT_HANDOFF = (
    ROOT
    / "artifacts"
    / "historical_phase_runs"
    / "phase15"
    / "PHASE_15_BASELINE_2026-07-09.md"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze Phase 14 evidence as the Phase 15 baseline.")
    parser.add_argument("--phase14-postmortem-path", type=Path, default=DEFAULT_POSTMORTEM)
    parser.add_argument("--good-task-dashboard-path", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--gdpval-gap-profile-path", type=Path, default=DEFAULT_GDPVAL_GAP)
    parser.add_argument("--generated-task-gap-profile-path", type=Path, default=DEFAULT_GENERATED_GAP)
    parser.add_argument("--generated-vs-gdpval-gap-path", type=Path, default=DEFAULT_GENERATED_VS_GDPVAL)
    parser.add_argument("--llm-impact-path", type=Path, default=DEFAULT_LLM_IMPACT)
    parser.add_argument("--llm-adoption-path", type=Path, default=DEFAULT_LLM_ADOPTION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--handoff-path", type=Path, default=DEFAULT_HANDOFF)
    args = parser.parse_args()

    request = Phase15BaselineRequest(
        phase14_postmortem_path=str(args.phase14_postmortem_path),
        good_task_dashboard_path=str(args.good_task_dashboard_path),
        gdpval_gap_profile_path=str(args.gdpval_gap_profile_path),
        generated_task_gap_profile_path=str(args.generated_task_gap_profile_path),
        generated_vs_gdpval_gap_path=str(args.generated_vs_gdpval_gap_path),
        llm_impact_path=str(args.llm_impact_path),
        llm_adoption_path=str(args.llm_adoption_path),
        output_dir=str(args.output_dir),
        handoff_path=str(args.handoff_path),
    )
    manifest = Phase15BaselineBuilder().build(request)
    print(
        json.dumps(
            {
                "baseline_status": manifest.baseline_status,
                "phase14_decision": manifest.phase14_decision,
                "phase15_recommendation": manifest.phase15_recommendation,
                "blockers": manifest.blockers,
                "report_path": str(Path(args.output_dir) / "phase15_baseline_manifest.json"),
                "handoff_path": manifest.handoff_path,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
