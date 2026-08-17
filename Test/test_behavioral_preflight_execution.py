from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_behavioral_authorization import (  # noqa: E402
    BehavioralAgentProtocolProbeAuthorizationRequestV1,
    BehavioralAuthorizationManager,
    BehavioralPreflightPanelMemberV1,
)
from task_generator.v3_behavioral_preflight_execution import (  # noqa: E402
    BehavioralPreflightExecutionManifestV1,
    BehavioralPreflightExecutor,
    behavioral_preflight_exit_code,
    behavioral_request_timeout_seconds,
)
from task_generator.v3_behavioral_validation import SolverToolPreflight  # noqa: E402
from task_generator.v3_solver_execution_budget import (  # noqa: E402
    SolverExecutionBudgetLedger,
    SolverExecutionBudgetV1,
    inspect_solver_process_outcome,
)
from task_generator.v3_source_fingerprint import governed_source_fingerprint  # noqa: E402


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class BehavioralPreflightExecutionTest(unittest.TestCase):
    def test_protocol_probe_uses_its_bounded_timeout_field(self) -> None:
        request = BehavioralAgentProtocolProbeAuthorizationRequestV1(
            comparison_id="comparison",
            panel_member=BehavioralPreflightPanelMemberV1(
                solver_model="gpt-5.6-sol",
                stratum="strong",
                provider="tuzi",
                maximum_cost_usd=1.0,
            ),
            solver_execution_budget=SolverExecutionBudgetV1(
                solver_model="gpt-5.6-sol",
                maximum_provider_calls=2,
                maximum_agent_turns=2,
                maximum_request_bytes_per_call=32768,
                maximum_completion_tokens_per_call=4096,
                maximum_provider_input_tokens=65536,
                maximum_provider_output_tokens=8192,
                input_cost_usd_per_million_tokens=10.0,
                output_cost_usd_per_million_tokens=30.0,
                maximum_contract_cost_usd=1.0,
            ),
            environment_contract_id="fixed-linux-amd64-network-governed-v1",
            timeout_seconds=600,
            maximum_total_cost_usd=1.0,
            campaign_manifest_sha256="a" * 64,
            route_comparison_manifest_sha256="b" * 64,
            provider_screening_report_sha256="c" * 64,
            route_blind_staging_report_sha256="d" * 64,
            container_parity_report_path="parity.json",
            container_parity_report_sha256="e" * 64,
            behavioral_code_fingerprint="f" * 64,
            frozen_blind_task_ids=["blind"],
            pricing_schedule_source="test conservative schedule",
            user_action_required="Explicit authorization is required before execution.",
        )
        self.assertEqual(behavioral_request_timeout_seconds(request), 600)

    def test_manifest_exit_code_fails_closed(self) -> None:
        common = {
            "comparison_id": "test-comparison",
            "authorization_request_sha256": "a" * 64,
            "authorization_receipt_sha256": "b" * 64,
            "fixture_contract": "create_copy_edit_save_submit_xlsx_v1",
            "run_external": True,
            "records": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        for status in ("blocked", "indeterminate", "running"):
            manifest = BehavioralPreflightExecutionManifestV1(
                status=status, **common
            )
            self.assertEqual(behavioral_preflight_exit_code(manifest), 1)
        for status in ("dry_run_ready", "completed"):
            manifest = BehavioralPreflightExecutionManifestV1(
                status=status, **common
            )
            self.assertEqual(behavioral_preflight_exit_code(manifest), 0)

    def _authorized(self, root: Path) -> tuple[Path, Path]:
        _write(
            root / "campaign_manifest.json",
            {
                "comparison_id": "test-comparison",
                "status": "evaluation_ready",
                "assignments": [
                    {"blind_task_id": f"blind-{index}"} for index in range(12)
                ],
            },
        )
        _write(
            root / "governance" / "route_comparison_manifest.json",
            {"environment_contract_id": "test-environment"},
        )
        _write(
            root / "governance" / "provider_screening_outcome.json",
            {"decision": "proceed_to_behavioral_evaluation"},
        )
        _write(
            root / "blind_staging" / "governance" / "route_blind_staging_report.json",
            {"decision": "pass", "package_count": 12, "teacher_artifacts_included": False},
        )
        parity = root / "parity.json"
        _write(
            parity,
            {
                "passed": True,
                "returncode": 0,
                "network_mode": "none",
                "read_only_root": True,
                "provider_credentials_mounted": False,
                "cleanup_returncode": 0,
                "external_model_execution_authorized": False,
                "source_fingerprint": governed_source_fingerprint(ROOT),
            },
        )
        members = []
        budgets = []
        for model, stratum, cost in [
            ("weak-model", "weak", 1.0),
            ("medium-model", "medium", 2.0),
            ("strong-model", "strong", 2.0),
        ]:
            members.append(
                BehavioralPreflightPanelMemberV1(
                    solver_model=model,
                    stratum=stratum,
                    provider="test-provider",
                    maximum_cost_usd=cost,
                )
            )
            budgets.append(
                SolverExecutionBudgetV1(
                    solver_model=model,
                    maximum_provider_calls=4,
                    maximum_agent_turns=4,
                    maximum_request_bytes_per_call=65536,
                    maximum_completion_tokens_per_call=2048,
                    maximum_provider_input_tokens=262144,
                    maximum_provider_output_tokens=8192,
                    input_cost_usd_per_million_tokens=1,
                    output_cost_usd_per_million_tokens=2,
                    maximum_contract_cost_usd=cost,
                )
            )
        manager = BehavioralAuthorizationManager(root)
        manager.write_preflight_request_v2(
            panel_members=members,
            solver_execution_budgets=budgets,
            pricing_schedule_source="test conservative schedule",
            container_parity_report_path=parity,
            maximum_total_cost_usd=5,
        )
        current = manager.current_request_path
        import hashlib

        request_sha = hashlib.sha256(current.read_bytes()).hexdigest()
        immutable = manager.immutable_request_root / f"{request_sha}.json"
        receipt = root / "receipt.json"
        manager.compile_receipt_v2(
            authorization_request_path=immutable,
            authorization_id="test-v2-receipt",
            authorization_statement="User explicitly authorized this exact V2 test request.",
            expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            output_path=receipt,
        )
        input_root = root / "public_input"
        case = input_root / "solver_tool_preflight"
        fixture = SolverToolPreflight().create_fixture(case)
        _write(
            case / "dataset_row.json",
            {
                "task_id": "solver_tool_preflight",
                "prompt": Path(fixture["prompt_path"]).read_text(encoding="utf-8"),
                "reference_files": ["reference_files/copy_template.xlsx"],
                "deliverable_files": [
                    "deliverable_files/created_workbook.xlsx",
                    "deliverable_files/edited_template.xlsx",
                ],
                "extra": {
                    "tool_only_preflight": True,
                    "business_task": False,
                    "grader_authorized": False,
                },
            },
        )
        return receipt, input_root

    def test_dry_run_is_public_and_non_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, input_root = self._authorized(root)
            result = BehavioralPreflightExecutor(root).execute(
                authorization_receipt_path=receipt,
                input_root=input_root,
                output_root=root / "outputs",
                real_world_python=sys.executable,
                rw_task_root=root,
            )
            self.assertEqual(result.status, "dry_run_ready")
            self.assertFalse(result.run_external)
            self.assertTrue(result.public_fixture_only)
            self.assertTrue(all("--budget-contract" in item.command for item in result.records))
            manifests = list(
                (root / "governance" / "behavioral_preflight_executions").glob(
                    "*.json"
                )
            )
            self.assertEqual(len(manifests), 1)
            self.assertEqual(manifests[0].stem, result.authorization_request_sha256)
            self.assertTrue(
                all(
                    Path(item.budget_contract_path).parent.name
                    == result.authorization_request_sha256
                    for item in result.records
                )
            )
            self.assertFalse(
                (root / "governance" / "behavioral_preflight_execution_manifest.json").exists()
            )

    def test_blind_id_in_fixture_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, input_root = self._authorized(root)
            row_path = input_root / "solver_tool_preflight" / "dataset_row.json"
            row = json.loads(row_path.read_text(encoding="utf-8"))
            row["prompt"] += " blind-3"
            _write(row_path, row)
            with self.assertRaisesRegex(ValueError, "no_blind_ids"):
                BehavioralPreflightExecutor(root).execute(
                    authorization_receipt_path=receipt,
                    input_root=input_root,
                    output_root=root / "outputs",
                    real_world_python=sys.executable,
                    rw_task_root=root,
                )

    def test_receipt_is_single_use_after_external_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, input_root = self._authorized(root)

            def fake_runner(command, **kwargs):
                model = command[command.index("--model") + 1]
                output = Path(command[command.index("--output") + 1])
                run_root = output / "run_solver_tool_preflight"
                deliverable = run_root / "deliverable_files" / "result.xlsx"
                deliverable.parent.mkdir(parents=True)
                deliverable.write_bytes(b"result")
                budget_path = Path(command[command.index("--budget-contract") + 1])
                budget = SolverExecutionBudgetV1.model_validate_json(
                    budget_path.read_text(encoding="utf-8")
                )
                outcome = inspect_solver_process_outcome(
                    solver_model=model,
                    output_root=run_root,
                    budget=budget,
                    usage=SolverExecutionBudgetLedger(budget).usage,
                    finish_signal_received=True,
                )
                (run_root / "solver_process_outcome.json").write_text(
                    outcome.model_dump_json(indent=2), encoding="utf-8"
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            executor = BehavioralPreflightExecutor(root)
            dry_run = executor.execute(
                authorization_receipt_path=receipt,
                input_root=input_root,
                output_root=root / "outputs",
                real_world_python=sys.executable,
                rw_task_root=root,
            )
            self.assertEqual(dry_run.status, "dry_run_ready")
            result = executor.execute(
                authorization_receipt_path=receipt,
                input_root=input_root,
                output_root=root / "outputs",
                real_world_python=sys.executable,
                rw_task_root=root,
                run_external=True,
                command_runner=fake_runner,
            )
            self.assertEqual(result.status, "completed")
            self.assertTrue(all(item.attempt_count == 1 for item in result.records))
            self.assertTrue(
                all(
                    Path(item.process_stdout_path).parent
                    == root / "process_logs"
                    for item in result.records
                )
            )
            with self.assertRaisesRegex(PermissionError, "already_consumed"):
                executor.execute(
                    authorization_receipt_path=receipt,
                    input_root=input_root,
                    output_root=root / "outputs",
                    real_world_python=sys.executable,
                    rw_task_root=root,
                    run_external=True,
                    command_runner=fake_runner,
                )

    def test_source_drift_blocks_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt, input_root = self._authorized(root)
            with patch(
                "task_generator.v3_behavioral_preflight_execution.governed_source_fingerprint",
                return_value="0" * 64,
            ):
                with self.assertRaisesRegex(PermissionError, "source_fingerprint_drift"):
                    BehavioralPreflightExecutor(root).execute(
                        authorization_receipt_path=receipt,
                        input_root=input_root,
                        output_root=root / "outputs",
                        real_world_python=sys.executable,
                        rw_task_root=root,
                    )


if __name__ == "__main__":
    unittest.main()
