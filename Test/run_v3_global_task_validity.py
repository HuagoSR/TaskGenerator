import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_global_task_validity import GlobalTaskValidityBuilder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build report-only global validity diagnostics from existing Pipeline B artifacts."
    )
    parser.add_argument("--blueprint", type=Path, required=True)
    parser.add_argument("--reference-file-plan", type=Path, required=True)
    parser.add_argument("--generated-file-manifest", type=Path, required=True)
    parser.add_argument("--teacher-input-manifest", type=Path, required=True)
    parser.add_argument("--golden-run", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--prototype-report", type=Path)
    parser.add_argument("--subgraph-report", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    builder = GlobalTaskValidityBuilder()
    outputs = builder.build(
        blueprint_path=args.blueprint,
        reference_file_plan_path=args.reference_file_plan,
        generated_file_manifest_path=args.generated_file_manifest,
        teacher_input_manifest_path=args.teacher_input_manifest,
        golden_run_path=args.golden_run,
        rubric_path=args.rubric,
        quality_report_path=args.quality_report,
        output_dir=args.output_dir,
        prototype_report_path=args.prototype_report,
        subgraph_report_path=args.subgraph_report,
    )
    report_paths = builder.write_outputs(*outputs, output_dir=args.output_dir)
    global_report = outputs[0]

    print(
        json.dumps(
            {
                "global_task_validity_report_path": report_paths["global_task_validity_report_path"],
                "real_worldness_score": global_report.real_worldness.real_worldness_score,
                "difficulty_overall": global_report.difficulty_profile.overall_difficulty,
                "recommended_next_layer": global_report.recommended_next_layer,
                "artifact_error_count": len(global_report.artifact_errors),
                "finding_count": len(global_report.findings),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
