from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import MethodType


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_codex_local_solver import (  # noqa: E402
    CodexJSONLDiagnosticsV1,
    CodexLocalCLIIdentityV1,
    CodexLocalDeliveryInspectionV1,
)
from task_generator.v3_external_model_comparison import (  # noqa: E402
    ExternalComparisonTaskBindingV1,
    ExternalComparisonReceiptV1,
    ExternalComparisonRunner,
    ExternalComparisonExecutionManifestV1,
    ExternalStackExecutionRecordV1,
    ExternalTaskExecutionRecordV1,
    ExternalModelComparisonCampaignV1,
    ExternalStackSummaryV1,
    ExternalStackSpecV1,
    ExternalTaskObservationV1,
    _external_command,
    _external_config,
    _failure_code,
    _pairwise,
    grade_external_deliveries,
)


def _bindings() -> list[ExternalComparisonTaskBindingV1]:
    rows = []
    index = 0
    for domain in ("audit_compliance", "procurement_operations"):
        for route in ("skill_guided_llm", "llm_led_hybrid"):
            for motif in (
                "fan_in_reconciliation",
                "cross_check_validation",
                "policy_application",
            ):
                for replicate in ("a", "b"):
                    rows.append(
                        ExternalComparisonTaskBindingV1(
                            blind_task_id=f"task-{index}",
                            brief_id=f"brief-{index // 2}",
                            route_id=route,
                            motif=motif,
                            replicate_id=replicate,
                            domain=domain,
                            source_package_path=f"teacher-{index}",
                            candidate_package_path=f"candidate-{index}",
                            package_fingerprint=f"{index:064x}",
                            candidate_tree_sha256=f"{index + 24:064x}",
                            candidate_projection_sha256=(
                                f"{index + 48:064x}"
                            ),
                            reality_evidence_sha256=f"{index + 72:064x}",
                            expected_deliverable=(
                                "deliverable_files/result.xlsx"
                            ),
                        )
                    )
                    index += 1
    return rows


def _scope() -> ExternalModelComparisonCampaignV1:
    return ExternalModelComparisonCampaignV1(
        campaign_id="campaign",
        representative_campaign_path="campaign.json",
        representative_campaign_sha256="a" * 64,
        baseline_solver_manifest_path="solver.json",
        baseline_solver_manifest_sha256="b" * 64,
        baseline_grader_manifest_path="grader.json",
        baseline_grader_manifest_sha256="c" * 64,
        baseline_grader_outcome_path="outcome.json",
        baseline_grader_outcome_sha256="d" * 64,
        parity_report_path="parity.json",
        parity_report_sha256="e" * 64,
        source_fingerprint="f" * 64,
        cli=CodexLocalCLIIdentityV1(
            version="0.146.0",
            package_lock_sha256="1" * 64,
            executable_sha256="2" * 64,
            executable_path="codex.cmd",
            installation_tree_sha256="3" * 64,
        ),
        external_stacks=[
            ExternalStackSpecV1(
                stack_id="gemini-3.1-pro-preview@tuzi_codex",
                model="gemini-3.1-pro-preview",
                base_url="https://example.invalid/v1",
            ),
            ExternalStackSpecV1(
                stack_id="deepseek-v4-pro@tuzi_codex",
                model="deepseek-v4-pro",
                base_url="https://example.invalid/v1",
            ),
        ],
        task_bindings=_bindings(),
    )


class ExternalModelComparisonTests(unittest.TestCase):
    def test_scope_fixes_two_models_and_full_matrix(self):
        scope = _scope()
        self.assertEqual(len(scope.task_bindings), 24)
        self.assertEqual(scope.attempts_per_task, 1)
        self.assertFalse(scope.training_authorized)

    def test_config_is_native_responses_and_contains_no_secret(self):
        spec = ExternalStackSpecV1(
            stack_id="gemini-3.1-pro-preview@tuzi_codex",
            model="gemini-3.1-pro-preview",
            base_url="https://example.invalid/v1",
        )
        config = _external_config(spec)
        self.assertIn('wire_api = "responses"', config)
        self.assertIn("request_max_retries = 0", config)
        self.assertNotIn("temperature", config)
        self.assertNotIn("reasoning", config)
        self.assertNotIn("secret-value", config)
        command = _external_command(
            Path("codex.cmd"), Path("workspace"), spec.model
        )
        self.assertNotIn("--ignore-user-config", command)
        self.assertNotIn("secret-value", " ".join(map(str, command)))

    def test_failure_taxonomy_separates_transport_and_task(self):
        self.assertEqual(
            _failure_code(
                "",
                "stream disconnected",
                timed_out=False,
                command_seen=False,
                returncode=1,
            ),
            "stream_transport_failure",
        )
        self.assertEqual(
            _failure_code(
                "",
                "",
                timed_out=True,
                command_seen=False,
                returncode=None,
            ),
            "timeout_without_tool_activity",
        )
        self.assertIsNone(
            _failure_code(
                "",
                "",
                timed_out=True,
                command_seen=True,
                returncode=None,
            )
        )

    def test_failure_taxonomy_ignores_candidate_text_in_jsonl(self):
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "agent_message",
                            "text": "Investigate unauthorized records and HTTP 403.",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "error",
                        "message": "stream disconnected before completion",
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.failed",
                        "error": {
                            "message": "stream disconnected before completion"
                        },
                    }
                ),
            ]
        )
        self.assertEqual(
            _failure_code(
                stdout,
                "",
                timed_out=False,
                command_seen=True,
                returncode=1,
            ),
            "stream_transport_failure",
        )

    def test_probe_failure_uploads_no_private_task(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scope = _scope()
            scope_path = root / "scope.json"
            scope_path.write_text(
                scope.model_dump_json(), encoding="utf-8"
            )
            import hashlib

            scope_sha = hashlib.sha256(scope_path.read_bytes()).hexdigest()
            receipt_path = root / "receipt.json"
            receipt_path.write_text(
                ExternalComparisonReceiptV1(
                    scope_sha256=scope_sha,
                    issued_at="2026-07-31T00:00:00Z",
                ).model_dump_json(),
                encoding="utf-8",
            )
            calls = []

            def fake_run_one(self, **kwargs):
                calls.append(kwargs["kind"])
                artifact = (
                    root
                    / kwargs["spec"].stack_id
                    / "probe_outcome.json"
                )
                artifact.parent.mkdir(parents=True, exist_ok=True)
                jsonl = artifact.parent / "codex.jsonl"
                stderr = artifact.parent / "stderr.txt"
                jsonl.write_text("", encoding="utf-8")
                stderr.write_text("protocol failure", encoding="utf-8")
                outcome = {
                    "outcome_version": "v3.codex_local_process_outcome.1",
                    "kind": "public_probe",
                    "blind_task_id": "public_external_comparison_probe",
                    "status": "infrastructure_failed",
                    "started_at": "2026-07-31T00:00:00Z",
                    "completed_at": "2026-07-31T00:00:01Z",
                    "duration_seconds": 1.0,
                    "returncode": 1,
                    "timed_out": False,
                    "command": ["codex"],
                    "workspace_path": str(kwargs["workspace"]),
                    "workspace_input_tree_sha256": "4" * 64,
                    "jsonl_path": str(jsonl),
                    "jsonl_sha256": hashlib.sha256(
                        jsonl.read_bytes()
                    ).hexdigest(),
                    "stderr_path": str(stderr),
                    "stderr_sha256": hashlib.sha256(
                        stderr.read_bytes()
                    ).hexdigest(),
                    "diagnostics": (
                        CodexJSONLDiagnosticsV1().model_dump(mode="json")
                    ),
                    "delivery": CodexLocalDeliveryInspectionV1(
                        relative_path=kwargs["expected"],
                        exists=False,
                        nonempty=False,
                        xlsx_openable=False,
                        has_nonempty_sheet=False,
                        differs_from_inputs=False,
                        valid=False,
                        failure="expected_delivery_missing",
                    ).model_dump(mode="json"),
                    "output_tree_sha256": "5" * 64,
                    "first_failure": "responses_protocol_failure",
                }
                artifact.write_text(
                    __import__("json").dumps(outcome), encoding="utf-8"
                )
                from task_generator.v3_codex_local_solver import (
                    CodexLocalProcessOutcomeV1,
                )

                return (
                    CodexLocalProcessOutcomeV1.model_validate(outcome),
                    artifact,
                )

            runner = object.__new__(ExternalComparisonRunner)
            runner.scope_path = scope_path
            runner.receipt_path = receipt_path
            runner.output = root / "output"
            runner.python = Path(sys.executable)
            runner.secret = "secret-value"
            runner.scope = scope
            runner._run_one = MethodType(fake_run_one, runner)
            manifest, _ = runner.execute()
            self.assertEqual(calls, ["public_probe", "public_probe"])
            self.assertTrue(
                all(
                    stack.status == "probe_failed"
                    for stack in manifest.stacks.values()
                )
            )
            self.assertFalse(
                (root / "output" / "execution"
                 / "gemini-3.1-pro-preview@tuzi_codex"
                 / "tasks").exists()
            )

    def test_grader_does_not_grade_missing_deliveries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scope = _scope()
            scope_path = root / "scope.json"
            scope_path.write_text(
                scope.model_dump_json(), encoding="utf-8"
            )
            import hashlib

            scope_sha = hashlib.sha256(scope_path.read_bytes()).hexdigest()
            stacks = {}
            for spec in scope.external_stacks:
                stacks[spec.stack_id] = ExternalStackExecutionRecordV1(
                    stack_id=spec.stack_id,
                    status="probe_failed",
                    public_probe_status="completed",
                    tasks={
                        binding.blind_task_id: (
                            ExternalTaskExecutionRecordV1(
                                blind_task_id=binding.blind_task_id,
                                status="not_started",
                            )
                        )
                        for binding in scope.task_bindings
                    },
                )
            execution = ExternalComparisonExecutionManifestV1(
                scope_path=str(scope_path),
                scope_sha256=scope_sha,
                receipt_path="receipt.json",
                receipt_sha256="9" * 64,
                status="solver_completed",
                stacks=stacks,
                created_at="2026-07-31T00:00:00Z",
                updated_at="2026-07-31T00:00:00Z",
            )
            execution_path = root / "execution.json"
            execution_path.write_text(
                execution.model_dump_json(), encoding="utf-8"
            )
            manifest, _ = grade_external_deliveries(
                scope_path=scope_path,
                execution_manifest_path=execution_path,
                output_root=root / "grader",
                codex_home=root / "codex-home",
                python_executable=Path(sys.executable),
            )
            self.assertTrue(
                all(
                    record.status == "not_eligible"
                    and record.attempt_count == 0
                    for records in manifest.records.values()
                    for record in records.values()
                )
            )

    def test_pairwise_requires_coverage_and_uses_frozen_threshold(self):
        observations = []
        for index in range(24):
            for stack, score in (("left", 0.80), ("right", 0.74)):
                observations.append(
                    ExternalTaskObservationV1(
                        stack_id=stack,
                        blind_task_id=f"task-{index}",
                        domain="audit_compliance",
                        motif="fan_in_reconciliation",
                        route_id="llm_led_hybrid",
                        attempted=True,
                        infrastructure_complete=True,
                        exact_valid_delivery=True,
                        task_failed=False,
                        grade_complete=True,
                        major_defect=False,
                        professional_plausibility="pass",
                        weighted_score=score,
                    )
                )
        left = ExternalStackSummaryV1(
            stack_id="left",
            public_probe_pass=True,
            attempted_task_count=24,
            infrastructure_failure_count=0,
            task_failure_count=0,
            valid_delivery_count=24,
            completed_grade_count=24,
            major_defect_count=0,
            professional_plausibility_count=24,
            mean_weighted_score=0.80,
            saturation_count=0,
            total_duration_seconds=1.0,
            total_usage={},
            capability_comparison_eligible=True,
        )
        right = left.model_copy(
            update={
                "stack_id": "right",
                "mean_weighted_score": 0.74,
            }
        )
        result = _pairwise(left, right, observations)
        self.assertEqual(result.common_graded_task_count, 24)
        self.assertEqual(result.decision, "left_substantive_winner")


if __name__ == "__main__":
    unittest.main()
