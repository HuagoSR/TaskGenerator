from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.task_generator.v3_behavioral_preflight_evidence import (
    BehavioralPreflightEvidenceAuditor,
)
from src.task_generator.v3_behavioral_preflight_execution import (
    BehavioralPreflightExecutionManifestV1,
    BehavioralPreflightExecutionRecordV1,
)
from src.task_generator.v3_solver_execution_budget import (
    SolverExecutionBudgetLedger,
    SolverExecutionBudgetV1,
    inspect_solver_process_outcome,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BehavioralPreflightEvidenceTest(unittest.TestCase):
    def _fixture(self, root: Path) -> Path:
        model = "test-model"
        output = root / "outputs" / model
        run = output / "run_solver_tool_preflight"
        deliverable = run / "deliverable_files" / "result.xlsx"
        deliverable.parent.mkdir(parents=True)
        deliverable.write_bytes(b"result")
        budget = SolverExecutionBudgetV1(
            solver_model=model,
            maximum_provider_calls=1,
            maximum_agent_turns=1,
            maximum_request_bytes_per_call=1024,
            maximum_completion_tokens_per_call=256,
            maximum_provider_input_tokens=1024,
            maximum_provider_output_tokens=256,
            input_cost_usd_per_million_tokens=1,
            output_cost_usd_per_million_tokens=1,
            maximum_contract_cost_usd=1,
        )
        outcome = inspect_solver_process_outcome(
            solver_model=model,
            output_root=run,
            budget=budget,
            usage=SolverExecutionBudgetLedger(budget).usage,
            finish_signal_received=True,
            expected_deliverable_paths=["deliverable_files/result.xlsx"],
        )
        outcome_path = run / "solver_process_outcome.json"
        outcome_path.write_text(outcome.model_dump_json(indent=2), encoding="utf-8")
        stdout = root / "process_logs" / "test-model.stdout.txt"
        stderr = root / "process_logs" / "test-model.stderr.txt"
        stdout.parent.mkdir()
        stdout.write_text("stdout", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        record = BehavioralPreflightExecutionRecordV1(
            solver_model=model,
            status="succeeded",
            attempt_count=1,
            command=["python"],
            budget_contract_path=str(root / "budget.json"),
            budget_contract_sha256="pending",
            output_root=str(output),
            returncode=0,
            outcome_path=str(outcome_path),
            outcome_sha256=_sha(outcome_path),
            process_stdout_path=str(stdout),
            process_stdout_sha256=_sha(stdout),
            process_stderr_path=str(stderr),
            process_stderr_sha256=_sha(stderr),
        )
        budget_path = root / "budget.json"
        budget_path.write_text(budget.model_dump_json(indent=2), encoding="utf-8")
        record.budget_contract_sha256 = _sha(budget_path)
        manifest = BehavioralPreflightExecutionManifestV1(
            comparison_id="comparison",
            authorization_request_sha256="a" * 64,
            authorization_receipt_sha256="b" * 64,
            fixture_contract="create_copy_edit_save_submit_xlsx_v1",
            run_external=True,
            status="completed",
            records=[record],
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        manifest_path = root / "manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return manifest_path

    def test_complete_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._fixture(root)
            report = BehavioralPreflightEvidenceAuditor(root).audit(manifest)
            self.assertEqual(report.decision, "pass")

    def test_overwritten_process_log_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._fixture(root)
            (root / "process_logs" / "test-model.stdout.txt").write_text(
                "overwritten", encoding="utf-8"
            )
            report = BehavioralPreflightEvidenceAuditor(root).audit(manifest)
            self.assertEqual(report.decision, "blocked")
            self.assertIn(
                "test-model:stdout_sha256_mismatch", report.blocking_reasons
            )

    def test_mutated_output_tree_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self._fixture(root)
            deliverable = (
                root
                / "outputs"
                / "test-model"
                / "run_solver_tool_preflight"
                / "deliverable_files"
                / "result.xlsx"
            )
            deliverable.write_bytes(b"mutated")
            report = BehavioralPreflightEvidenceAuditor(root).audit(manifest)
            self.assertEqual(report.decision, "blocked")
            self.assertIn(
                "test-model:output_tree_sha256_mismatch", report.blocking_reasons
            )


if __name__ == "__main__":
    unittest.main()
