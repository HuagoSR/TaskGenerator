import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_external_eval_result_builder import (  # noqa: E402
    Phase15ExternalEvalResultBuilder,
    Phase15ExternalEvalResultBuilderRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_RUNBOOK = PHASE15 / "external_eval_runbook" / "phase15_external_eval_runbook.json"
DEFAULT_QUEUE_REPORT = PHASE15 / "clean_eval_queue" / "phase15_clean_eval_queue_report.json"
DEFAULT_OUTPUT = PHASE15 / "external_eval_import"
DEFAULT_RESULTS = PHASE15 / "external_eval_import" / "phase15_external_eval_results.json"
DEFAULT_BUNDLE_REPORT = PHASE15 / "permitted_eval_bundle" / "phase15_permitted_eval_bundle_report.json"
DEFAULT_REQUIRE_CASES = [
    "pipeline_b_batch_01_evidence_to_deliverable",
    "pipeline_b_batch_02_evidence_to_deliverable",
    "pipeline_b_batch_03_evidence_to_deliverable",
    "pipeline_b_batch_04_evidence_to_deliverable",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sanitized Phase 15 external eval results from runbook outputs.")
    parser.add_argument("--runbook-path", type=Path, default=DEFAULT_RUNBOOK)
    parser.add_argument("--queue-report-path", type=Path, default=DEFAULT_QUEUE_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--result-output-path", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--permitted-eval-bundle-report-path", type=Path, default=DEFAULT_BUNDLE_REPORT)
    parser.add_argument("--require-model", action="append", default=None)
    parser.add_argument("--require-case", action="append", default=None)
    args = parser.parse_args()

    request = Phase15ExternalEvalResultBuilderRequest(
        runbook_path=str(args.runbook_path),
        queue_report_path=str(args.queue_report_path),
        output_dir=str(args.output_dir),
        result_output_path=str(args.result_output_path),
        permitted_eval_bundle_report_path=str(args.permitted_eval_bundle_report_path),
        require_models=args.require_model or ["gpt-4o-mini"],
        require_cases=args.require_case or DEFAULT_REQUIRE_CASES,
    )
    report = Phase15ExternalEvalResultBuilder().build(request)
    print(
        json.dumps(
            {
                "summary": report.summary,
                "result_output_path": report.result_output_path,
                "report_path": str(Path(args.output_dir) / "phase15_external_eval_result_builder_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
