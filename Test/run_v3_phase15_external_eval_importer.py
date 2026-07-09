import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_external_eval_importer import (  # noqa: E402
    Phase15ExternalEvalImporter,
    Phase15ExternalEvalImportRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_QUEUE_REPORT = PHASE15 / "clean_eval_queue" / "phase15_clean_eval_queue_report.json"
DEFAULT_EXTERNAL_RESULTS = PHASE15 / "external_eval_import" / "phase15_external_eval_results.json"
DEFAULT_OUTPUT = PHASE15 / "external_eval_import"


def main() -> None:
    parser = argparse.ArgumentParser(description="Import sanitized Phase 15 external clean-eval results.")
    parser.add_argument("--queue-report-path", type=Path, default=DEFAULT_QUEUE_REPORT)
    parser.add_argument("--external-results-path", type=Path, default=DEFAULT_EXTERNAL_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-model", action="append", default=None)
    parser.add_argument("--require-case", action="append", default=None)
    args = parser.parse_args()

    request = Phase15ExternalEvalImportRequest(
        queue_report_path=str(args.queue_report_path),
        external_results_path=str(args.external_results_path),
        output_dir=str(args.output_dir),
        require_models=args.require_model or ["gpt-4o-mini"],
        require_cases=args.require_case or ["pipeline_b_batch_01_evidence_to_deliverable"],
    )
    report = Phase15ExternalEvalImporter().build(request)
    print(
        json.dumps(
            {
                "import_status": report.import_status,
                "summary": report.summary,
                "blocking_reasons": report.blocking_reasons,
                "report_path": str(Path(args.output_dir) / "phase15_external_eval_import_report.json"),
                "template_path": str(Path(args.output_dir) / "phase15_external_eval_results_template.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
