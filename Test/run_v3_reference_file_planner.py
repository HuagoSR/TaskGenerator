import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_reference_file_planner import ReferenceFilePlanner  # noqa: E402


DEFAULT_BLUEPRINT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "prototype_from_subgraph_smoke" / "draft_task_blueprint.json"
)
DEFAULT_SUBGRAPH_REPORT_PATH = (
    ROOT / "artifacts" / "pipeline_b" / "scratch" / "subgraph_sampler_smoke" / "pipeline_b_subgraph_report.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "scratch" / "reference_file_plan_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a report-only Pipeline B reference-file plan from a draft TaskBlueprint."
    )
    parser.add_argument("--blueprint", type=Path, default=DEFAULT_BLUEPRINT_PATH)
    parser.add_argument("--subgraph-report", type=Path, default=DEFAULT_SUBGRAPH_REPORT_PATH)
    parser.add_argument("--without-subgraph", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    planner = ReferenceFilePlanner()
    plan = planner.build_plan(
        blueprint_path=args.blueprint,
        subgraph_report_path=None if args.without_subgraph else args.subgraph_report,
    )
    outputs = planner.write_outputs(plan, args.output_dir)
    diagnostics = plan.diagnostics
    print(
        json.dumps(
            {
                **outputs,
                "blueprint_id": plan.blueprint_id,
                "planned_file_count": diagnostics.planned_file_count,
                "planned_table_count": diagnostics.planned_table_count,
                "planned_text_section_count": diagnostics.planned_text_section_count,
                "planned_evidence_anchor_count": diagnostics.planned_evidence_anchor_count,
                "subgraph_confidence": diagnostics.subgraph_confidence,
                "planner_warnings": diagnostics.planner_warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
