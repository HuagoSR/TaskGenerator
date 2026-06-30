import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_calibration_registry_admission import CalibrationRegistryAdmissionReviewer  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_OUTPUT_PATH = ROOT / "SkillRegistry" / "v3_calibration_registry_admission_report.json"
DEFAULT_ACCEPTED_CANDIDATE_PATHS = [
    ROOT
    / "Test"
    / "v3_web_source_collections"
    / "pipeline_a_batches"
    / "audit_evidence_reconciliation"
    / "pipeline_a_run_graph_calibration"
    / "review"
    / "accepted_skill_candidates.json",
    ROOT
    / "Test"
    / "v3_web_source_collections"
    / "pipeline_a_batches"
    / "internal_control_testing"
    / "pipeline_a_run_graph_calibration"
    / "review"
    / "accepted_skill_candidates.json",
    ROOT
    / "Test"
    / "v3_web_source_collections"
    / "pipeline_a_batches"
    / "compliance_documentation_review"
    / "pipeline_a_run_graph_calibration"
    / "review"
    / "accepted_skill_candidates.json",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Review graph calibration accepted candidates for possible registry admission.")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument(
        "--accepted-candidates",
        action="append",
        type=Path,
        default=[],
        help="accepted_skill_candidates.json path. Can be repeated. Defaults to the 3 web-source graph calibration runs.",
    )
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    candidate_paths = args.accepted_candidates or DEFAULT_ACCEPTED_CANDIDATE_PATHS
    report = CalibrationRegistryAdmissionReviewer().build_report(
        registry_path=args.registry_path,
        accepted_candidate_paths=candidate_paths,
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "output_path": str(args.output_path),
                "candidate_count": report["candidate_count"],
                "admission_decision_counts": report["admission_decision_counts"],
                "reason_code_counts": report["reason_code_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()



