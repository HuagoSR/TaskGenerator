from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_deliverable_contract import (  # noqa: E402
    DeliverableContractCompiler,
    DeliverableContractValidator,
    inspect_delivery,
)


DEFAULT_FIXTURES = ROOT / "Test" / "fixtures" / "pipeline_reconstruction" / "deliverable_contract"
DEFAULT_OUTPUT = ROOT / "artifacts" / "pipeline_reconstruction" / "deliverable_contract_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the offline R0/R1 deliverable-contract negative controls and submission-path smoke."
    )
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.output_dir.exists():
        if not args.overwrite:
            raise SystemExit("output_dir_exists_without_overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True)

    compiler = DeliverableContractCompiler()
    validator = DeliverableContractValidator()
    negative_results = []
    for fixture_path in sorted(args.fixture_dir.glob("slot_*.json")):
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        contract = compiler.build(
            fixture["case_id"],
            fixture["deliverable_specs"],
            fixture["reference_files"],
        )
        validation = validator.validate(
            contract,
            fixture["prompt"],
            fixture["reference_files"],
        )
        failed_checks = sorted(item.check_name for item in validation.findings if not item.passed)
        expected = sorted(fixture["expected_failed_checks"])
        negative_results.append(
            {
                "fixture": fixture_path.name,
                "failure_taxonomy": fixture["failure_taxonomy"],
                "validation_status": validation.validation_status,
                "failed_checks": failed_checks,
                "expected_failed_checks": expected,
                "passed": validation.validation_status == "invalid"
                and set(expected).issubset(failed_checks),
            }
        )

    valid_root = args.output_dir / "valid_submission"
    delivery_dir = valid_root / "run_case" / "deliverable_files"
    delivery_dir.mkdir(parents=True)
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.active.append(["status"])
    workbook.active.append(["complete"])
    workbook.save(delivery_dir / "review_output.xlsx")
    valid_contract = compiler.build(
        "valid_submission",
        [{"file_name": "review_output.xlsx"}],
    )
    valid_prompt = compiler.compile_prompt(
        "Review the supplied public synthetic evidence.",
        valid_contract,
    )
    valid_contract_report = validator.validate(valid_contract, valid_prompt, [])
    valid_delivery_report = inspect_delivery(valid_root, valid_contract)

    report = {
        "smoke_version": "v3.deliverable_contract_smoke.1",
        "external_calls": False,
        "fixture_count": len(negative_results),
        "negative_controls": negative_results,
        "valid_submission": {
            "contract_status": valid_contract_report.validation_status,
            "delivery_status": valid_delivery_report.delivery_status,
            "valid_count": valid_delivery_report.valid_count,
        },
    }
    report["passed"] = (
        len(negative_results) == 3
        and all(item["passed"] for item in negative_results)
        and valid_contract_report.validation_status == "pass"
        and valid_delivery_report.delivery_status == "valid"
    )
    report_path = args.output_dir / "deliverable_contract_smoke_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "report_path": str(report_path)}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
