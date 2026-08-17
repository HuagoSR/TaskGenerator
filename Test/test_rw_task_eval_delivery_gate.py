from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.task_generator.v3_deliverable_contract import DeliverableContractCompiler
from src.task_generator.v3_rw_task_eval_prep import (
    RwTaskEvalPrepReport,
    RwTaskEvalPrepRequest,
)
from src.task_generator.v3_rw_task_eval_runner import RwTaskEvalRunner


class RwTaskEvalDeliveryGateTests(unittest.TestCase):
    def test_grading_is_not_run_without_exact_valid_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prep = self._prep(root)
            runner = RwTaskEvalRunner()
            with patch(
                "src.task_generator.v3_rw_task_eval_runner.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as mocked:
                records, inspection, _ = runner._execute_commands(
                    commands=prep.would_run_commands,
                    output_dir=root / "runner_report",
                    timeout_seconds=10,
                    grading_model="grader",
                    rw_task_root=str(root),
                    prep_report=prep,
                )
            self.assertEqual(1, mocked.call_count)
            self.assertEqual(["succeeded", "not_run"], [item.status for item in records])
            self.assertEqual("delivery_inspection", records[-1].failure_stage)
            self.assertIsNotNone(inspection)
            self.assertEqual("invalid", inspection.delivery_status)

    def test_grading_runs_after_exact_openable_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prep = self._prep(root)
            solver_output = Path(prep.would_run_commands[0][5])

            def run_side_effect(*args, **kwargs):
                if run_side_effect.calls == 0:
                    delivery = solver_output / "run_case" / "deliverable_files"
                    delivery.mkdir(parents=True)
                    from openpyxl import Workbook

                    workbook = Workbook()
                    workbook.active.append(["value"])
                    workbook.save(delivery / "output.xlsx")
                run_side_effect.calls += 1
                return subprocess.CompletedProcess([], 0, "", "")

            run_side_effect.calls = 0
            runner = RwTaskEvalRunner()
            with patch(
                "src.task_generator.v3_rw_task_eval_runner.subprocess.run",
                side_effect=run_side_effect,
            ) as mocked:
                records, inspection, _ = runner._execute_commands(
                    commands=prep.would_run_commands,
                    output_dir=root / "runner_report",
                    timeout_seconds=10,
                    grading_model="grader",
                    rw_task_root=str(root),
                    prep_report=prep,
                )
            self.assertEqual(2, mocked.call_count)
            self.assertEqual(["succeeded", "succeeded"], [item.status for item in records])
            self.assertIsNotNone(inspection)
            self.assertEqual("valid", inspection.delivery_status)

    def _prep(self, root: Path) -> RwTaskEvalPrepReport:
        case_dir = root / "eval_input" / "case"
        case_dir.mkdir(parents=True)
        contract = DeliverableContractCompiler().build(
            "case",
            [{"file_name": "output.xlsx"}],
        )
        (case_dir / "deliverable_contract.json").write_text(
            contract.model_dump_json(indent=2),
            encoding="utf-8",
        )
        (case_dir / "dataset_row.json").write_text(
            json.dumps(
                {
                    "task_id": "case",
                    "reference_files": [],
                    "deliverable_files": ["deliverable_files/output.xlsx"],
                    "extra": {"deliverable_contract": contract.model_dump(mode="json")},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        solver_output = root / "solver_output"
        grade_output = root / "grade_output"
        commands = [
            [
                "python",
                "-m",
                "task_generator.v3_rw_task_eval_stirrup_wrapper",
                str(root / "eval_input"),
                "--output",
                str(solver_output),
            ],
            [
                "python",
                "-m",
                "bench_standalone.grade_deliverables",
                str(solver_output),
                "--out-dir",
                str(grade_output),
            ],
        ]
        request = RwTaskEvalPrepRequest(
            case_dir=str(case_dir),
            validation_report_path=str(root / "validation.json"),
            eval_input_dir=str(root / "eval_input"),
            model="solver",
            rw_task_root=str(root),
            python_exe="python",
        )
        return RwTaskEvalPrepReport(
            request=request,
            case_id="case",
            batch_case_id="case",
            blueprint_id="blueprint",
            rw_task_task_id="case",
            evaluated_model_name="solver",
            prep_status="prepared",
            evaluation_mode="candidate_ready_eval_candidate",
            eval_input_case_dir=str(case_dir),
            would_run_commands=commands,
        )


if __name__ == "__main__":
    unittest.main()
