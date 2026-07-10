import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_external_eval_result_builder import (  # noqa: E402
    Phase16ExternalEvalResultBuilderRequest,
    build_phase16_external_eval_results,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sanitized Phase 16 clean-eval result records from rw-task outputs.")
    parser.add_argument(
        "--runbook",
        type=Path,
        default=ROOT / "artifacts" / "phase16" / "production_eval_prep" / "phase16_external_eval_runbook.json",
    )
    parser.add_argument(
        "--existing-results",
        action="append",
        default=None,
        help="Optional sanitized result files to merge before adding the current runbook outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "phase16" / "production_eval_prep" / "result_builder",
    )
    parser.add_argument(
        "--result-output",
        type=Path,
        default=ROOT / "artifacts" / "phase16" / "production_eval_prep" / "phase16_external_eval_results.sanitized.json",
    )
    args = parser.parse_args()

    report = build_phase16_external_eval_results(
        Phase16ExternalEvalResultBuilderRequest(
            runbook_path=str(args.runbook),
            output_dir=str(args.output_dir),
            result_output_path=str(args.result_output),
            existing_result_paths=args.existing_results or [],
        )
    )
    print(
        json.dumps(
            {
                "summary": report.summary,
                "result_output_path": report.result_output_path,
                "report_path": str(args.output_dir / "phase16_external_eval_result_builder_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
