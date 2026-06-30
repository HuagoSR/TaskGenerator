import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_pipeline_b_sampler import PipelineBSubgraphSampler  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_SEED_REPORT_PATH = ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "scratch" / "subgraph_sampler_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a report-only Pipeline B skill-resource subgraph from seed artifacts."
    )
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--seed-report", type=Path, default=DEFAULT_SEED_REPORT_PATH)
    parser.add_argument("--motif", default=None)
    parser.add_argument("--skill-count", type=int, default=4)
    parser.add_argument("--allow-caution", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    sampler = PipelineBSubgraphSampler()
    subgraph = sampler.build_subgraph(
        registry_path=args.registry_path,
        seed_report_path=args.seed_report,
        motif=args.motif,
        skill_count=args.skill_count,
        allow_caution=args.allow_caution,
    )
    outputs = sampler.write_outputs(subgraph, args.output_dir)
    diagnostics = subgraph.diagnostics
    print(
        json.dumps(
            {
                **outputs,
                "motif": subgraph.selected_motif,
                "selected_skill_count": len(subgraph.selected_skills),
                "confidence": diagnostics.confidence,
                "typed_edge_count": diagnostics.edge_counts.get("typed_resource_match", 0),
                "fallback_edge_count": (
                    diagnostics.edge_counts.get("legacy_resource_overlap", 0)
                    + diagnostics.edge_counts.get("role_sequence", 0)
                    + diagnostics.edge_counts.get("motif_cooccurrence", 0)
                ),
                "missing_or_weak_pipeline_a_signals": diagnostics.missing_or_weak_pipeline_a_signals,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
