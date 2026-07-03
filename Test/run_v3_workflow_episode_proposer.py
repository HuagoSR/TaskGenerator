import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_workflow_episode_proposer import WorkflowEpisodeProposer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build report-only WorkflowEpisode proposals from existing Pipeline A extraction artifacts."
    )
    parser.add_argument("--prompt-package", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--trace-edges", type=Path)
    parser.add_argument("--motif-hints", type=Path)
    parser.add_argument("--graph-diagnostics", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    proposer = WorkflowEpisodeProposer()
    report = proposer.build(
        prompt_package_path=args.prompt_package,
        candidates_path=args.candidates,
        trace_edges_path=args.trace_edges,
        motif_hints_path=args.motif_hints,
        graph_diagnostics_path=args.graph_diagnostics,
        output_dir=args.output_dir,
    )
    report_paths = proposer.write_outputs(report, args.output_dir)

    print(
        json.dumps(
            {
                "workflow_episode_proposals_path": report_paths["workflow_episode_proposals_path"],
                "workflow_episode_proposal_report_path": report_paths["workflow_episode_proposal_report_path"],
                "episode_count": report.diagnostics.episode_count,
                "low_confidence_episode_count": report.diagnostics.low_confidence_episode_count,
                "orphan_candidate_count": report.diagnostics.orphan_candidate_count,
                "missing_source_count": report.diagnostics.missing_source_count,
                "warning_codes": report.diagnostics.warning_codes,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
