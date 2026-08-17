from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.task_generator.v3_behavioral_authorization import (
    BehavioralAuthorizationManager,
    BehavioralPreflightPanelMemberV1,
    SolverExecutionBudgetV1,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BehavioralAuthorizationTest(unittest.TestCase):
    def _campaign(self, root: Path, *, status: str = "evaluation_ready") -> None:
        assignments = [
            {"blind_task_id": f"cmp_{index:02d}"} for index in range(12)
        ]
        _write(
            root / "campaign_manifest.json",
            {
                "comparison_id": "r6_test",
                "status": status,
                "assignments": assignments,
            },
        )
        _write(
            root / "container_parity_report.json",
            {
                "passed": True,
                "returncode": 0,
                "network_mode": "none",
                "read_only_root": True,
                "provider_credentials_mounted": False,
                "cleanup_returncode": 0,
                "external_model_execution_authorized": False,
                "source_fingerprint": "a" * 64,
            },
        )
        _write(
            root / "governance" / "route_comparison_manifest.json",
            {
                "comparison_id": "r6_test",
                "environment_contract_id": "fixed-linux-amd64-network-governed-v1",
            },
        )
        _write(
            root / "governance" / "provider_screening_outcome.json",
            {
                "comparison_id": "r6_test",
                "decision": "proceed_to_behavioral_evaluation",
            },
        )
        _write(
            root
            / "blind_staging"
            / "governance"
            / "route_blind_staging_report.json",
            {
                "comparison_id": "r6_test",
                "decision": "pass",
                "package_count": 12,
                "teacher_artifacts_included": False,
            },
        )

    @staticmethod
    def _panel() -> list[BehavioralPreflightPanelMemberV1]:
        return [
            BehavioralPreflightPanelMemberV1(
                solver_model="gpt-4o-mini",
                stratum="weak",
                provider="tuzi",
                maximum_cost_usd=1.0,
            ),
            BehavioralPreflightPanelMemberV1(
                solver_model="gemini-3.1-pro-preview",
                stratum="medium",
                provider="tuzi",
                maximum_cost_usd=2.0,
            ),
            BehavioralPreflightPanelMemberV1(
                solver_model="gpt-5.6-sol",
                stratum="strong",
                provider="tuzi",
                maximum_cost_usd=2.0,
            ),
        ]

    @staticmethod
    def _budgets() -> list[SolverExecutionBudgetV1]:
        ceilings = {
            "gpt-4o-mini": 1.0,
            "gemini-3.1-pro-preview": 2.0,
            "gpt-5.6-sol": 2.0,
        }
        return [
            SolverExecutionBudgetV1(
                solver_model=model,
                maximum_provider_calls=8,
                maximum_agent_turns=8,
                maximum_request_bytes_per_call=131072,
                maximum_completion_tokens_per_call=4096,
                maximum_provider_input_tokens=524288,
                maximum_provider_output_tokens=32768,
                input_cost_usd_per_million_tokens=1.0,
                output_cost_usd_per_million_tokens=2.0,
                maximum_contract_cost_usd=ceiling,
            )
            for model, ceiling in ceilings.items()
        ]

    def test_request_is_exact_tool_only_and_non_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._campaign(root)
            manifest_sha = _sha(root / "campaign_manifest.json")
            manager = BehavioralAuthorizationManager(root)
            request = manager.write_preflight_request(
                panel_members=self._panel(),
                container_parity_report_path=root / "container_parity_report.json",
                maximum_total_cost_usd=5.0,
            )
            current = (
                root
                / "governance"
                / "behavioral_preflight_authorization_request.json"
            )
            request_sha = _sha(current)
            self.assertTrue(
                (
                    root
                    / "governance"
                    / "behavioral_authorization_requests"
                    / f"{request_sha}.json"
                ).is_file()
            )
            self.assertEqual(request.requested_scope, "solver_tool_preflight")
            self.assertFalse(request.task_packages_uploaded)
            self.assertFalse(request.business_tasks_executed)
            self.assertFalse(request.grader_calls_authorized)
            self.assertNotIn(
                "claude-sonnet-4-6",
                {member.solver_model for member in request.panel_members},
            )
            self.assertEqual(manifest_sha, _sha(root / "campaign_manifest.json"))
            check = manager.check()
            self.assertEqual(check.decision, "authorization_required")
            self.assertFalse(check.solver_preflight_calls_made)

    def test_request_rejects_non_ready_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._campaign(root, status="packages_ready")
            with self.assertRaisesRegex(
                PermissionError, "behavioral_request_requires_evaluation_ready"
            ):
                BehavioralAuthorizationManager(root).write_preflight_request(
                    panel_members=self._panel(),
                    container_parity_report_path=root
                    / "container_parity_report.json",
                    maximum_total_cost_usd=5.0,
                )

    def test_panel_hard_blocks_claude_sonnet(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "behavioral_preflight_hard_blocked_model"
        ):
            BehavioralPreflightPanelMemberV1(
                solver_model="claude-sonnet-4-6",
                stratum="strong",
                provider="tuzi",
                maximum_cost_usd=10.0,
            )

    def test_receipt_compiles_only_from_immutable_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._campaign(root)
            manager = BehavioralAuthorizationManager(root)
            manager.write_preflight_request(
                panel_members=self._panel(),
                container_parity_report_path=root / "container_parity_report.json",
                maximum_total_cost_usd=5.0,
            )
            current = (
                root
                / "governance"
                / "behavioral_preflight_authorization_request.json"
            )
            request_sha = _sha(current)
            expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            with self.assertRaisesRegex(
                ValueError, "behavioral_receipt_requires_immutable_request_path"
            ):
                manager.compile_receipt(
                    authorization_request_path=current,
                    authorization_id="test-auth-1",
                    authorization_statement="User explicitly authorized exact request.",
                    expires_at=expiry,
                    output_path=root / "bad_receipt.json",
                )
            immutable = (
                root
                / "governance"
                / "behavioral_authorization_requests"
                / f"{request_sha}.json"
            )
            receipt_path = root / "receipt.json"
            manager.compile_receipt(
                authorization_request_path=immutable,
                authorization_id="test-auth-2",
                authorization_statement="User explicitly authorized exact request.",
                expires_at=expiry,
                output_path=receipt_path,
            )
            check = manager.check(receipt_path)
            self.assertEqual(check.decision, "ready")
            self.assertFalse(check.business_task_calls_made)
            self.assertFalse(check.grader_calls_made)

    def test_old_receipt_cannot_activate_changed_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._campaign(root)
            manager = BehavioralAuthorizationManager(root)
            manager.write_preflight_request(
                panel_members=self._panel(),
                container_parity_report_path=root / "container_parity_report.json",
                maximum_total_cost_usd=5.0,
            )
            current = (
                root
                / "governance"
                / "behavioral_preflight_authorization_request.json"
            )
            request_sha = _sha(current)
            immutable = (
                root
                / "governance"
                / "behavioral_authorization_requests"
                / f"{request_sha}.json"
            )
            receipt_path = root / "receipt.json"
            manager.compile_receipt(
                authorization_request_path=immutable,
                authorization_id="test-auth-3",
                authorization_statement="User explicitly authorized exact request.",
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(days=1)
                ).isoformat(),
                output_path=receipt_path,
            )
            changed_panel = self._panel()
            changed_panel[1] = BehavioralPreflightPanelMemberV1(
                solver_model="gpt-5.5-pro",
                stratum="medium",
                provider="tuzi",
                maximum_cost_usd=2.0,
            )
            manager.write_preflight_request(
                panel_members=changed_panel,
                container_parity_report_path=root / "container_parity_report.json",
                maximum_total_cost_usd=5.0,
            )
            check = manager.check(receipt_path)
            self.assertEqual(check.decision, "blocked")
            self.assertTrue(
                any(
                    "behavioral_receipt_request_mismatch" in reason
                    for reason in check.blocking_reasons
                )
            )

    def test_v2_request_and_receipt_bind_execution_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._campaign(root)
            manager = BehavioralAuthorizationManager(root)
            request = manager.write_preflight_request_v2(
                panel_members=self._panel(),
                solver_execution_budgets=self._budgets(),
                pricing_schedule_source="user-approved conservative schedule v1",
                container_parity_report_path=root / "container_parity_report.json",
                maximum_total_cost_usd=5.0,
            )
            self.assertFalse(request.actual_provider_billing_claimed)
            self.assertTrue(all(item.provider_sdk_retries == 0 for item in request.solver_execution_budgets))
            current = root / "governance" / "behavioral_preflight_authorization_request.json"
            request_sha = _sha(current)
            immutable = root / "governance" / "behavioral_authorization_requests" / f"{request_sha}.json"
            receipt_path = root / "receipt-v2.json"
            manager.compile_receipt_v2(
                authorization_request_path=immutable,
                authorization_id="v2-test-auth",
                authorization_statement="User explicitly authorized the exact V2 request.",
                expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                output_path=receipt_path,
            )
            self.assertEqual(manager.check_v2(receipt_path).decision, "ready")
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            payload["solver_execution_budget_sha256"] = "0" * 64
            _write(receipt_path, payload)
            check = manager.check_v2(receipt_path)
            self.assertEqual(check.decision, "blocked")
            self.assertTrue(any("budget_mismatch" in item for item in check.blocking_reasons))

    def test_v2_rejects_budget_above_member_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._campaign(root)
            budgets = self._budgets()
            budgets[0] = budgets[0].model_copy(
                update={"maximum_contract_cost_usd": 1.5}
            )
            with self.assertRaisesRegex(ValueError, "member_ceiling"):
                BehavioralAuthorizationManager(root).write_preflight_request_v2(
                    panel_members=self._panel(),
                    solver_execution_budgets=budgets,
                    pricing_schedule_source="user-approved conservative schedule v1",
                    container_parity_report_path=root / "container_parity_report.json",
                    maximum_total_cost_usd=5.5,
                )


if __name__ == "__main__":
    unittest.main()
