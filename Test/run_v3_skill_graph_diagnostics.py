import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_skill_graph_diagnostics import (  # noqa: E402
    build_graph_extraction_diagnostics,
    load_graph_extraction_inputs,
    write_graph_extraction_diagnostics,
)
from task_generator.v3_source_schema import SkillExtractionPromptPackage, load_json_file  # noqa: E402


def default_path(base_dir: Path, filename: str) -> Path:
    return base_dir / filename


def main() -> None:
    parser = argparse.ArgumentParser(description="Build report-only diagnostics for V3 graph extraction outputs.")
    parser.add_argument("--extraction-dir", type=Path, help="Directory containing extracted_skill_candidates.json and optional graph outputs.")
    parser.add_argument("--candidates", type=Path, help="Path to extracted_skill_candidates.json or accepted_skill_candidates.json.")
    parser.add_argument("--trace-edges", type=Path, help="Path to skill_trace_edges.json.")
    parser.add_argument("--motif-hints", type=Path, help="Path to skill_motif_hints.json.")
    parser.add_argument("--prompt-package", type=Path, help="Optional source prompt package for block-ref validation.")
    parser.add_argument("--output-path", type=Path, help="Output diagnostics JSON path.")
    args = parser.parse_args()

    if args.extraction_dir:
        candidates_path = args.candidates or default_path(args.extraction_dir, "extracted_skill_candidates.json")
        trace_edges_path = args.trace_edges or default_path(args.extraction_dir, "skill_trace_edges.json")
        motif_hints_path = args.motif_hints or default_path(args.extraction_dir, "skill_motif_hints.json")
        output_path = args.output_path or default_path(args.extraction_dir, "graph_extraction_diagnostics.json")
    else:
        if not args.candidates:
            raise SystemExit("Either --extraction-dir or --candidates is required.")
        candidates_path = args.candidates
        trace_edges_path = args.trace_edges
        motif_hints_path = args.motif_hints
        output_path = args.output_path or Path("graph_extraction_diagnostics.json")

    package = None
    if args.prompt_package:
        package = SkillExtractionPromptPackage.model_validate(load_json_file(str(args.prompt_package)))

    candidates, trace_edges, motif_hints = load_graph_extraction_inputs(
        candidates_path=candidates_path,
        trace_edges_path=trace_edges_path,
        motif_hints_path=motif_hints_path,
    )
    report = build_graph_extraction_diagnostics(
        candidates=candidates,
        trace_edges=trace_edges,
        motif_hints=motif_hints,
        package=package,
    )
    write_graph_extraction_diagnostics(report, output_path)

    print(
        json.dumps(
            {
                "output_path": str(output_path),
                "candidate_count": report["candidate_count"],
                "resource_count": report["typed_resource_summary"]["resource_count"],
                "trace_edge_count": report["trace_edge_summary"]["trace_edge_count"],
                "motif_hint_count": report["motif_hint_summary"]["motif_hint_count"],
                "warning_codes": [warning["code"] for warning in report["warnings"]],
                "is_graph_ready": report["is_graph_ready"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()



