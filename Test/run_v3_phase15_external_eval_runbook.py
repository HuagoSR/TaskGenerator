import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_external_eval_runbook import (  # noqa: E402
    Phase15ExternalEvalRunbookBuilder,
    Phase15ExternalEvalRunbookRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_QUEUE_REPORT = PHASE15 / "clean_eval_queue" / "phase15_clean_eval_queue_report.json"
DEFAULT_TEMPLATE = PHASE15 / "external_eval_import" / "phase15_external_eval_results_template.json"
DEFAULT_OUTPUT = PHASE15 / "external_eval_runbook"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 15 external eval runbook for a permitted environment.")
    parser.add_argument("--queue-report-path", type=Path, default=DEFAULT_QUEUE_REPORT)
    parser.add_argument("--external-eval-template-path", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-model", default="gpt-4o-mini")
    parser.add_argument("--require-case", default="pipeline_b_batch_01_evidence_to_deliverable")
    parser.add_argument("--command-timeout-seconds", type=int, default=600)
    args = parser.parse_args()

    request = Phase15ExternalEvalRunbookRequest(
        queue_report_path=str(args.queue_report_path),
        external_eval_template_path=str(args.external_eval_template_path),
        output_dir=str(args.output_dir),
        require_model=args.require_model,
        require_case=args.require_case,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    runbook = Phase15ExternalEvalRunbookBuilder().build(request)
    print(
        json.dumps(
            {
                "item_count": len(runbook.items),
                "run_order": runbook.run_order,
                "warnings": runbook.warnings,
                "runbook_path": runbook.generated_files.get("runbook"),
                "powershell_script": runbook.generated_files.get("powershell_script"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
