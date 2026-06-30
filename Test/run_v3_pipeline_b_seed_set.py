import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_pipeline_b_seed_set import PipelineBSeedSetBuilder  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_READINESS_REPORT_PATH = ROOT / "SkillRegistry" / "v3_registry_sampling_readiness_report.json"
DEFAULT_OUTPUT_PATH = ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a report-only Pipeline B seed skill set from Pipeline A outputs.")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--readiness-report", type=Path, default=DEFAULT_READINESS_REPORT_PATH)
    parser.add_argument("--target-count", type=int, default=20)
    parser.add_argument("--caution-limit", type=int, default=5)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    report = PipelineBSeedSetBuilder().build_report(
        registry_path=args.registry_path,
        readiness_report_path=args.readiness_report,
        target_count=args.target_count,
        caution_limit=args.caution_limit,
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "output_path": str(args.output_path),
                "selected_count": report["selected_count"],
                "selected_readiness_counts": report["selected_readiness_counts"],
                "selected_motif_counts": report["selected_motif_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()



