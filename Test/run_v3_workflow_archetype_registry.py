import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_workflow_archetype_registry import (  # noqa: E402
    WorkflowArchetypeRegistryBuilder,
)


DEFAULT_OUTPUT_PATH = ROOT / "SkillRegistry" / "v3_workflow_archetype_registry.experimental.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an experimental WorkflowArchetype registry from WorkflowEpisode proposal reports."
    )
    parser.add_argument("--episode-report", action="append", default=[], type=Path)
    parser.add_argument("--episode-report-dir", action="append", default=[], type=Path)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    builder = WorkflowArchetypeRegistryBuilder()
    report_paths = builder.collect_episode_reports(
        episode_report_paths=args.episode_report,
        episode_report_dirs=args.episode_report_dir,
    )
    artifact = builder.build(report_paths, args.output_path)
    written_path = builder.write_output(artifact, args.output_path)

    print(
        json.dumps(
            {
                "output_path": written_path,
                "episode_report_count": artifact.diagnostics.episode_report_count,
                "input_episode_count": artifact.diagnostics.input_episode_count,
                "accepted_episode_count": artifact.diagnostics.accepted_episode_count,
                "archetype_count": artifact.diagnostics.archetype_count,
                "unmatched_episode_count": artifact.diagnostics.unmatched_episode_count,
                "warning_codes": artifact.diagnostics.warning_codes,
                "archetype_names": [record.name for record in artifact.archetypes],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
