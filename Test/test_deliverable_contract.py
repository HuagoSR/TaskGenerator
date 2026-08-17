from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.task_generator.v3_deliverable_contract import (
    DeliverableContractCompiler,
    DeliverableContractValidator,
    DeliverableSpecV1,
    inspect_delivery,
)
from src.task_generator.v3_rw_task_export_validator import RwTaskExportValidator


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "Test" / "fixtures" / "pipeline_reconstruction" / "deliverable_contract"


class DeliverableContractTests(unittest.TestCase):
    def test_path_and_format_contract_is_strict(self):
        with self.assertRaises(ValidationError):
            DeliverableSpecV1(
                file_name="output.xlsx",
                relative_path="../output.xlsx",
                format="xlsx",
            )
        with self.assertRaises(ValidationError):
            DeliverableSpecV1(
                file_name="output.xlsx",
                relative_path="deliverable_files/output.docx",
                format="xlsx",
            )
        with self.assertRaises(ValidationError):
            DeliverableSpecV1(
                file_name="output.xlsx",
                relative_path="deliverable_files/output.xlsx",
                format="docx",
            )

    def test_f4_3_negative_control_fixtures_are_blocked(self):
        compiler = DeliverableContractCompiler()
        validator = DeliverableContractValidator()
        fixture_paths = sorted(FIXTURE_ROOT.glob("slot_*.json"))
        self.assertEqual(3, len(fixture_paths))
        for path in fixture_paths:
            with self.subTest(path=path.name):
                fixture = json.loads(path.read_text(encoding="utf-8"))
                contract = compiler.build(
                    fixture["case_id"],
                    fixture["deliverable_specs"],
                    fixture["reference_files"],
                )
                report = validator.validate(
                    contract,
                    fixture["prompt"],
                    fixture["reference_files"],
                )
                failed = {item.check_name for item in report.findings if not item.passed}
                self.assertEqual("invalid", report.validation_status)
                self.assertTrue(set(fixture["expected_failed_checks"]).issubset(failed))

    def test_compiled_prompt_and_explicit_template_contract_pass(self):
        compiler = DeliverableContractCompiler()
        contract = compiler.build(
            "case_ok",
            [
                {
                    "file_name": "review_output.xlsx",
                    "creation_mode": "copy_then_edit",
                    "source_template": "reference_files/review_template.xlsx",
                }
            ],
            ["reference_files/review_template.xlsx"],
        )
        prompt = compiler.compile_prompt("Review the evidence and document the result.", contract)
        report = DeliverableContractValidator().validate(
            contract,
            prompt,
            ["reference_files/review_template.xlsx"],
        )
        self.assertEqual("pass", report.validation_status)
        self.assertIn("deliverable_files/review_output.xlsx", prompt)

    def test_delivery_inspection_requires_exact_nonempty_openable_file(self):
        compiler = DeliverableContractCompiler()
        contract = compiler.build("case_delivery", [{"file_name": "output.xlsx"}])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            delivery_dir = root / "run_case" / "deliverable_files"
            delivery_dir.mkdir(parents=True)

            wrong = delivery_dir / "wrong.xlsx"
            self._xlsx(wrong)
            wrong_report = inspect_delivery(root, contract)
            self.assertEqual("invalid", wrong_report.delivery_status)
            self.assertEqual([str(wrong)], wrong_report.wrong_name_or_path_files)

            wrong.unlink()
            (delivery_dir / "output.xlsx").write_bytes(b"")
            empty_report = inspect_delivery(root, contract)
            self.assertEqual("invalid", empty_report.delivery_status)
            self.assertIn("expected_deliverable_empty", empty_report.records[0].reason_codes)

            self._xlsx(delivery_dir / "output.xlsx")
            valid_report = inspect_delivery(root, contract)
            self.assertEqual("valid", valid_report.delivery_status)
            self.assertEqual(1, valid_report.valid_count)

    def test_export_validator_blocks_contract_prompt_conflict(self):
        compiler = DeliverableContractCompiler()
        contract = compiler.build("case_export", [{"file_name": "expected.xlsx"}])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "reference_files").mkdir()
            deliverable_dir = root / "deliverable_files"
            deliverable_dir.mkdir()
            (root / "artifacts").mkdir()
            (root / "deliverable_contract.json").write_text(
                contract.model_dump_json(indent=2),
                encoding="utf-8",
            )
            (deliverable_dir / "expected_deliverables.json").write_text(
                json.dumps(
                    {
                        "case_id": "case_export",
                        "deliverables": ["deliverable_files/expected.xlsx"],
                    }
                ),
                encoding="utf-8",
            )
            row = {
                "task_id": "case_export",
                "sector": "Finance",
                "occupation": "Auditor",
                "motif": "cross_check_validation",
                "prompt": "Create wrong.xlsx and submit it.",
                "reference_files": [],
                "deliverable_files": ["deliverable_files/expected.xlsx"],
                "rubric": "- criterion",
                "rubric_json": json.dumps([{"criterion": "criterion"}]),
                "extra": {
                    "export_status": "candidate_ready_export",
                    "not_final_training_data": False,
                    "rw_task_export_ready": True,
                    "deliverable_contract_mode": "blocking",
                    "deliverable_contract": contract.model_dump(mode="json"),
                },
            }
            (root / "dataset_row.json").write_text(
                json.dumps(row),
                encoding="utf-8",
            )
            report = RwTaskExportValidator().validate(root)
            self.assertEqual("invalid", report.validation_status)
            failed = {item.check_name for item in report.findings if not item.passed}
            self.assertIn(
                "deliverable_contract:prompt_output_name_conflicts",
                failed,
            )

    @staticmethod
    def _xlsx(path: Path) -> None:
        from openpyxl import Workbook

        workbook = Workbook()
        workbook.active.append(["value"])
        workbook.active.append([1])
        workbook.save(path)


if __name__ == "__main__":
    unittest.main()
