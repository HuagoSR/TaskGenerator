import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_local_status import (  # noqa: E402
    Phase15LocalStatusBuilder,
    Phase15LocalStatusRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_OUTPUT = PHASE15 / "local_status"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize current local Phase 15 status without external calls.")
    parser.add_argument("--completion-audit-report-path", type=Path, default=PHASE15 / "completion_audit" / "phase15_completion_audit_report.json")
    parser.add_argument("--postmortem-report-path", type=Path, default=PHASE15 / "closeout" / "phase15_postmortem_report.json")
    parser.add_argument("--external-eval-readiness-report-path", type=Path, default=PHASE15 / "external_eval_readiness" / "phase15_external_eval_readiness_report.json")
    parser.add_argument("--permitted-eval-bundle-report-path", type=Path, default=PHASE15 / "permitted_eval_bundle" / "phase15_permitted_eval_bundle_report.json")
    parser.add_argument("--external-eval-import-report-path", type=Path, default=PHASE15 / "external_eval_import" / "phase15_external_eval_import_report.json")
    parser.add_argument("--external-eval-runbook-path", type=Path, default=PHASE15 / "external_eval_runbook" / "phase15_external_eval_runbook.json")
    parser.add_argument("--external-eval-script-path", type=Path, default=PHASE15 / "external_eval_runbook" / "run_phase15_first_pair_external_eval.ps1")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    request = Phase15LocalStatusRequest(
        completion_audit_report_path=str(args.completion_audit_report_path),
        postmortem_report_path=str(args.postmortem_report_path),
        external_eval_readiness_report_path=str(args.external_eval_readiness_report_path),
        permitted_eval_bundle_report_path=str(args.permitted_eval_bundle_report_path),
        external_eval_import_report_path=str(args.external_eval_import_report_path),
        external_eval_runbook_path=str(args.external_eval_runbook_path),
        external_eval_script_path=str(args.external_eval_script_path),
        output_dir=str(args.output_dir),
    )
    report = Phase15LocalStatusBuilder().build(request)
    print(
        json.dumps(
            {
                "local_status": report.local_status,
                "phase15_completion_status": report.phase15_completion_status,
                "phase15_decision": report.phase15_decision,
                "external_eval_package_readiness": report.external_eval_package_readiness,
                "permitted_eval_bundle_status": report.permitted_eval_bundle_status,
                "external_eval_import_status": report.external_eval_import_status,
                "tenant_policy_status": report.tenant_policy_status,
                "blocking_reasons": report.blocking_reasons,
                "report_path": str(Path(args.output_dir) / "phase15_local_status_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
