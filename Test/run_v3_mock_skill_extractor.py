import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_skill_extractor import MockSkillExtractor  # noqa: E402
from v3_skill_graph_diagnostics import (  # noqa: E402
    build_graph_extraction_diagnostics,
    write_graph_extraction_diagnostics,
)
from v3_source_schema import SkillExtractionPromptPackage, load_json_file  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic V3 mock skill extractor on a prompt package.")
    parser.add_argument("--prompt-package", type=Path, required=True, help="Path to skill_extraction_prompt_package.json.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for extracted skill candidates.")
    parser.add_argument("--max-candidates", type=int, default=8, help="Maximum number of candidates to emit.")
    args = parser.parse_args()

    package = SkillExtractionPromptPackage.model_validate(load_json_file(str(args.prompt_package)))
    extractor = MockSkillExtractor()
    candidates = extractor.extract(package, max_candidates=args.max_candidates)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_payload = {
        "request_id": package.request_id,
        "extractor": "mock_rule_based_v0",
        "candidate_count": len(candidates),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    report_payload = {
        "request_id": package.request_id,
        "normalized_source_count": len(package.normalized_sources),
        "candidate_count": len(candidates),
        "trace_edge_count": len(extractor.last_trace_edges),
        "motif_hint_count": len(extractor.last_motif_hints),
        "candidate_names": [candidate.proposed_name for candidate in candidates],
        "warning": "Mock extractor output is for pipeline testing only; replace with LLM extraction for production.",
    }

    with open(args.output_dir / "extracted_skill_candidates.json", "w", encoding="utf-8") as f:
        json.dump(candidate_payload, f, ensure_ascii=False, indent=2)
    with open(args.output_dir / "skill_extraction_report.json", "w", encoding="utf-8") as f:
        json.dump(report_payload, f, ensure_ascii=False, indent=2)
    with open(args.output_dir / "skill_trace_edges.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "request_id": package.request_id,
                "trace_edge_count": len(extractor.last_trace_edges),
                "trace_edges": [edge.model_dump(mode="json") for edge in extractor.last_trace_edges],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    with open(args.output_dir / "skill_motif_hints.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "request_id": package.request_id,
                "motif_hint_count": len(extractor.last_motif_hints),
                "motif_hints": [hint.model_dump(mode="json") for hint in extractor.last_motif_hints],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    diagnostics = build_graph_extraction_diagnostics(
        candidates=candidates,
        trace_edges=extractor.last_trace_edges,
        motif_hints=extractor.last_motif_hints,
        package=package,
    )
    write_graph_extraction_diagnostics(diagnostics, args.output_dir / "graph_extraction_diagnostics.json")

    print(json.dumps(report_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
