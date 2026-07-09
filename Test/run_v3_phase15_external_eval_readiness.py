import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_external_eval_readiness import (  # noqa: E402
    Phase15ExternalEvalReadinessChecker,
    Phase15ExternalEvalReadinessRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_RUNBOOK = PHASE15 / "external_eval_runbook" / "phase15_external_eval_runbook.json"
DEFAULT_SCRIPT = PHASE15 / "external_eval_runbook" / "run_phase15_first_pair_external_eval.ps1"
DEFAULT_TEMPLATE = PHASE15 / "external_eval_import" / "phase15_external_eval_results_template.json"
DEFAULT_OUTPUT = PHASE15 / "external_eval_readiness"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Phase 15 external eval handoff readiness.")
    parser.add_argument("--runbook-path", type=Path, default=DEFAULT_RUNBOOK)
    parser.add_argument("--powershell-script-path", type=Path, default=DEFAULT_SCRIPT)
    parser.add_argument("--results-template-path", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    request = Phase15ExternalEvalReadinessRequest(
        runbook_path=str(args.runbook_path),
        powershell_script_path=str(args.powershell_script_path),
        results_template_path=str(args.results_template_path),
        output_dir=str(args.output_dir),
    )
    report = Phase15ExternalEvalReadinessChecker().build(request)
    print(
        json.dumps(
            {
                "readiness_status": report.readiness_status,
                "item_count": report.item_count,
                "blocking_reasons": report.blocking_reasons,
                "warnings": report.warnings,
                "report_path": str(Path(args.output_dir) / "phase15_external_eval_readiness_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
