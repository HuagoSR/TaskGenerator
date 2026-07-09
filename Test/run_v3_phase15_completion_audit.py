import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_completion_audit import (  # noqa: E402
    Phase15CompletionAuditRequest,
    Phase15CompletionAuditor,
)


PHASE15 = ROOT / "artifacts" / "phase15"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether Phase 15 is complete against the plan.")
    parser.add_argument("--baseline-manifest-path", type=Path, default=PHASE15 / "baseline" / "phase15_baseline_manifest.json")
    parser.add_argument("--llm-candidate-layer-report-path", type=Path, default=PHASE15 / "llm_candidate_layer" / "llm_candidate_layer_report.json")
    parser.add_argument("--gap-autopsy-report-path", type=Path, default=PHASE15 / "gap_autopsy" / "generated_task_gap_autopsy_report.json")
    parser.add_argument("--pattern-library-report-path", type=Path, default=PHASE15 / "pattern_library" / "gdpval_productive_complexity_pattern_library.json")
    parser.add_argument("--generator-reform-spec-path", type=Path, default=PHASE15 / "generator_reform" / "evidence_to_deliverable_reform_spec.json")
    parser.add_argument("--ab-experiment-report-path", type=Path, default=PHASE15 / "ab_experiment" / "phase15_ab_experiment_report.json")
    parser.add_argument("--clean-eval-queue-report-path", type=Path, default=PHASE15 / "clean_eval_queue" / "phase15_clean_eval_queue_report.json")
    parser.add_argument("--external-eval-import-report-path", type=Path, default=PHASE15 / "external_eval_import" / "phase15_external_eval_import_report.json")
    parser.add_argument("--production-dashboard-report-path", type=Path, default=PHASE15 / "production_impact" / "reform_dashboard" / "production_dashboard_report.json")
    parser.add_argument("--phase15-postmortem-report-path", type=Path, default=PHASE15 / "closeout" / "phase15_postmortem_report.json")
    parser.add_argument("--output-dir", type=Path, default=PHASE15 / "completion_audit")
    args = parser.parse_args()

    request = Phase15CompletionAuditRequest(
        baseline_manifest_path=str(args.baseline_manifest_path),
        llm_candidate_layer_report_path=str(args.llm_candidate_layer_report_path),
        gap_autopsy_report_path=str(args.gap_autopsy_report_path),
        pattern_library_report_path=str(args.pattern_library_report_path),
        generator_reform_spec_path=str(args.generator_reform_spec_path),
        ab_experiment_report_path=str(args.ab_experiment_report_path),
        clean_eval_queue_report_path=str(args.clean_eval_queue_report_path),
        external_eval_import_report_path=str(args.external_eval_import_report_path),
        production_dashboard_report_path=str(args.production_dashboard_report_path),
        phase15_postmortem_report_path=str(args.phase15_postmortem_report_path),
        output_dir=str(args.output_dir),
    )
    report = Phase15CompletionAuditor().build(request)
    print(
        json.dumps(
            {
                "completion_status": report.completion_status,
                "summary": report.summary,
                "final_blockers": report.final_blockers,
                "report_path": str(args.output_dir / "phase15_completion_audit_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
