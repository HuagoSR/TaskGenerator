import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_skill_registry import SkillRegistryBuilder  # noqa: E402
from v3_skill_transition_graph import (  # noqa: E402
    SkillTransitionGraphBuilder,
    load_optional_json,
    load_optional_motif_hints,
    load_optional_trace_edges,
    write_graph_report,
)
from v3_source_schema import load_skill_candidates  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_READINESS_REPORT_PATH = ROOT / "SkillRegistry" / "v3_registry_sampling_readiness_report.json"
DEFAULT_TRANSITION_REPORT_PATH = ROOT / "SkillRegistry" / "v3_skill_transition_graph_report.json"
DEFAULT_COMPOSITION_REPORT_PATH = ROOT / "SkillRegistry" / "v3_composition_readiness_report.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build report-only V3 skill transition graph and composition readiness reports.")
    parser.add_argument("--candidates", type=Path, required=True, help="extracted_skill_candidates.json path.")
    parser.add_argument("--accepted-candidates", type=Path, default=None, help="accepted_skill_candidates.json path. Defaults to candidates.")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--trace-edges", type=Path, default=None, help="skill_trace_edges.json path.")
    parser.add_argument("--motif-hints", type=Path, default=None, help="skill_motif_hints.json path.")
    parser.add_argument("--readiness-report", type=Path, default=DEFAULT_READINESS_REPORT_PATH)
    parser.add_argument("--transition-report-path", type=Path, default=DEFAULT_TRANSITION_REPORT_PATH)
    parser.add_argument("--composition-report-path", type=Path, default=DEFAULT_COMPOSITION_REPORT_PATH)
    args = parser.parse_args()

    candidates = load_skill_candidates(str(args.candidates))
    accepted_candidates = (
        load_skill_candidates(str(args.accepted_candidates))
        if args.accepted_candidates is not None and args.accepted_candidates.exists()
        else candidates
    )
    registry_entries = SkillRegistryBuilder().load_registry(args.registry_path)
    trace_edges = load_optional_trace_edges(args.trace_edges)
    motif_hints = load_optional_motif_hints(args.motif_hints)
    readiness_report = load_optional_json(args.readiness_report)

    transition_report, composition_report = SkillTransitionGraphBuilder().build_reports(
        candidates=candidates,
        accepted_candidates=accepted_candidates,
        registry_entries=registry_entries,
        trace_edges=trace_edges,
        motif_hints=motif_hints,
        readiness_report=readiness_report,
    )
    write_graph_report(args.transition_report_path, transition_report)
    write_graph_report(args.composition_report_path, composition_report)
    print(
        json.dumps(
            {
                "transition_report_path": str(args.transition_report_path),
                "composition_report_path": str(args.composition_report_path),
                "edge_count": transition_report["edge_count"],
                "edge_decision_counts": transition_report["edge_decision_counts"],
                "motif_count": transition_report["motif_count"],
                "role_counts": composition_report["role_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
