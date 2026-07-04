import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_reference_file_generator import ReferenceFileGenerator  # noqa: E402


DEFAULT_PLAN_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "reference_file_plan_smoke" / "reference_file_plan.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "scratch" / "reference_file_generation_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic table-first Pipeline B reference files from a reference file plan."
    )
    parser.add_argument("--reference-file-plan", type=Path, default=DEFAULT_PLAN_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    generator = ReferenceFileGenerator()
    manifest = generator.build_from_plan(
        reference_file_plan_path=args.reference_file_plan,
        output_dir=args.output_dir,
    )
    diagnostics = manifest.diagnostics
    print(
        json.dumps(
            {
                "manifest_path": str(args.output_dir / "generated_file_manifest.json"),
                "evidence_index_path": str(args.output_dir / "evidence_index.json"),
                "evidence_index_proposal_path": str(args.output_dir / "evidence_index_proposal.json"),
                "generation_trace_path": str(args.output_dir / "generation_trace.json"),
                "generated_file_count": diagnostics["generated_file_count"],
                "skipped_file_count": diagnostics["skipped_file_count"],
                "failed_file_count": diagnostics["failed_file_count"],
                "evidence_mapping_count": diagnostics["evidence_mapping_count"],
                "dossier_id": diagnostics["dossier_id"],
                "candidate_visible_file_count": diagnostics["candidate_visible_file_count"],
                "cross_file_constraint_count": diagnostics["cross_file_constraint_count"],
                "synthetic_artifact_count": diagnostics["synthetic_artifact_count"],
                "synthetic_artifact_role_counts": diagnostics["synthetic_artifact_role_counts"],
                "carried_forward_warnings": diagnostics["carried_forward_warnings"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
