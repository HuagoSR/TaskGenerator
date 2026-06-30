import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_pipeline_b_prototype import PipelineBPrototypeBuilder  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_SEED_REPORT_PATH = ROOT / "SkillRegistry" / "v3_pipeline_b_seed_set_report.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "pipeline_b" / "prototype_01"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a minimal report-only Pipeline B prototype from Pipeline A seed artifacts."
    )
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--seed-report", type=Path, default=DEFAULT_SEED_REPORT_PATH)
    parser.add_argument("--motif", default=None)
    parser.add_argument("--skill-count", type=int, default=4)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    builder = PipelineBPrototypeBuilder()
    report = builder.build_report(
        registry_path=args.registry_path,
        seed_report_path=args.seed_report,
        motif=args.motif,
        skill_count=args.skill_count,
    )
    outputs = builder.write_outputs(report, args.output_dir)
    print(
        json.dumps(
            {
                **outputs,
                "motif": report["motif"],
                "selected_skill_count": report["selected_skill_count"],
                "prototype_confidence": report["assembly_diagnostics"]["prototype_confidence"],
                "missing_or_weak_pipeline_a_signals": report["assembly_diagnostics"][
                    "missing_or_weak_pipeline_a_signals"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
