import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_transition_prior_store import TransitionPriorStoreBuilder  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_BATCH_REPORT = SCRATCH / "phase12_hardening_smoke" / "phase12_regression_5case" / "pipeline_b_batch_report.json"
DEFAULT_STORE_OUTPUT = ROOT / "SkillRegistry" / "v3_transition_prior_store.observed.json"
DEFAULT_REPORT_OUTPUT = SCRATCH / "phase12_hardening_smoke" / "phase12_transition_prior_observation_report.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build observed-only transition prior observations from a Pipeline B batch report."
    )
    parser.add_argument("--batch-report", type=Path, default=DEFAULT_BATCH_REPORT)
    parser.add_argument("--store-output", type=Path, default=DEFAULT_STORE_OUTPUT)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT)
    args = parser.parse_args()

    artifact = TransitionPriorStoreBuilder().build(
        batch_report_path=args.batch_report,
        store_output_path=args.store_output,
        report_output_path=args.report_output,
    )
    print(
        json.dumps(
            {
                "store_output_path": str(args.store_output),
                "report_output_path": str(args.report_output),
                "observation_count": artifact.diagnostics.observation_count,
                "candidate_ready_observation_count": artifact.diagnostics.candidate_ready_observation_count,
                "motif_counts": artifact.diagnostics.motif_counts,
                "role_context_count": artifact.diagnostics.role_context_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
