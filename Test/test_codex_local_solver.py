from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook
from pydantic import ValidationError

from task_generator.v3_codex_local_solver import (
    MODEL,
    CodexLocalCLIIdentityV1,
    CodexLocalDeliveryInspectionV1,
    CodexLocalGraderDraftV1,
    CodexLocalRunner,
    CodexLocalScreeningScopeV1,
    CodexLocalTaskBindingV1,
    CodexLocalTooling,
    _build_command,
    _copy_projection,
    _expected_deliverable,
    _projection_tree,
    _projected_files,
    _sanitized_environment,
    compile_scope,
    compile_standing_receipt,
    inspect_delivery,
    parse_codex_jsonl,
)
from Test.run_v3_codex_local_screening import _deepseek_config


def workbook_bytes(value: object = "done") -> bytes:
    workbook = Workbook()
    workbook.active["A1"] = value
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def write_package(root: Path, expected: str = "deliverable_files/result.xlsx") -> None:
    (root / "reference_files").mkdir(parents=True)
    (root / "reference_files" / "source.xlsx").write_bytes(
        workbook_bytes("source")
    )
    (root / "dataset_row.json").write_text(
        json.dumps({"task_id": root.name, "prompt": "Make a workbook"}),
        encoding="utf-8",
    )
    (root / "deliverable_contract.json").write_text(
        json.dumps({"deliverables": [{"relative_path": expected}]}),
        encoding="utf-8",
    )
    (root / "rw_task_export_report.json").write_text("{}", encoding="utf-8")
    (root / "deliverable_files").mkdir()
    (root / "deliverable_files" / "expected_deliverables.json").write_text(
        "{}", encoding="utf-8"
    )


def binding(
    index: int, route: str, motif: str, replicate: str
) -> CodexLocalTaskBindingV1:
    return CodexLocalTaskBindingV1(
        blind_task_id=f"ms_{index:016x}",
        brief_id=f"brief_{index}",
        route_id=route,
        motif=motif,
        replicate_id=replicate,
        package_fingerprint=f"{index:064x}",
        candidate_tree_sha256=f"{index + 100:064x}",
        candidate_projection_sha256=f"{index + 200:064x}",
        reality_evidence_sha256="d" * 64,
        expected_deliverable="deliverable_files/result.xlsx",
    )


def twelve_bindings() -> list[CodexLocalTaskBindingV1]:
    rows = []
    index = 0
    for route in ("skill_guided_llm", "llm_led_hybrid"):
        for motif in (
            "fan_in_reconciliation",
            "cross_check_validation",
            "policy_application",
        ):
            for replicate in ("a", "b"):
                index += 1
                rows.append(binding(index, route, motif, replicate))
    return rows


class FakePopen:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.pid = 12345
        self.returncode = 0

    def communicate(self, input=None, timeout=None):
        workspace = Path(self.kwargs["cwd"])
        target = workspace / "deliverable_files" / "result.xlsx"
        if not target.parent.exists():
            target = workspace / "deliverable_files" / "codex_local_probe.xlsx"
        target.write_bytes(workbook_bytes("created"))
        events = "\n".join(
            (
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "command_execution"},
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {"input_tokens": 11, "output_tokens": 7},
                    }
                ),
            )
        )
        return events, ""

    def poll(self):
        return self.returncode


class CodexLocalSolverTests(unittest.TestCase):
    def test_official_deepseek_key_can_be_loaded_from_ignored_raw_file(self):
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / "deepseek-key.txt"
            key_path.write_text("test-secret-value\n", encoding="utf-8")
            config = _deepseek_config(None, key_path)
            self.assertEqual(config.provider_name, "deepseek")
            self.assertEqual(config.base_url, "https://api.deepseek.com")
            self.assertEqual(config.model, "deepseek-v4-pro")
            self.assertEqual(config.api_key, "test-secret-value")

    def test_projection_excludes_governance_files(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "package"
            target = Path(temp) / "target"
            write_package(package)
            relative = {
                path.relative_to(package).as_posix()
                for path in _projected_files(package)
            }
            self.assertEqual(
                relative,
                {
                    "dataset_row.json",
                    "deliverable_contract.json",
                    "reference_files/source.xlsx",
                },
            )
            digest = _projection_tree(package)
            _copy_projection(package, target)
            self.assertEqual(_projection_tree(target), digest)
            self.assertFalse((target / "rw_task_export_report.json").exists())
            self.assertFalse(
                (target / "deliverable_files/expected_deliverables.json").exists()
            )

    def test_expected_delivery_is_exact_and_safe(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp)
            write_package(package, "deliverable_files/review_memo.xlsx")
            self.assertEqual(
                _expected_deliverable(package),
                "deliverable_files/review_memo.xlsx",
            )
            (package / "deliverable_contract.json").write_text(
                json.dumps(
                    {"deliverables": [{"relative_path": "../secret.xlsx"}]}
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "path_invalid"):
                _expected_deliverable(package)

    def test_delivery_rejects_missing_fake_empty_and_input_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "deliverable_files").mkdir()
            result = inspect_delivery(
                root, "deliverable_files/result.xlsx", set()
            )
            self.assertFalse(result.valid)
            path = root / "deliverable_files/result.xlsx"
            path.write_bytes(b"not an xlsx")
            self.assertFalse(
                inspect_delivery(root, "deliverable_files/result.xlsx", set()).valid
            )
            empty = Workbook()
            empty.active["A1"] = None
            empty.save(path)
            self.assertFalse(
                inspect_delivery(root, "deliverable_files/result.xlsx", set()).valid
            )
            value = workbook_bytes("same")
            path.write_bytes(value)
            digest = hashlib.sha256(value).hexdigest()
            self.assertFalse(
                inspect_delivery(
                    root, "deliverable_files/result.xlsx", {digest}
                ).valid
            )
            path.write_bytes(workbook_bytes("different"))
            self.assertTrue(
                inspect_delivery(
                    root, "deliverable_files/result.xlsx", {digest}
                ).valid
            )

    def test_jsonl_records_turn_command_and_usage(self):
        text = "\n".join(
            (
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "command_execution"},
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {"input_tokens": 4, "output_tokens": 3},
                    }
                ),
                "not-json",
            )
        )
        parsed = parse_codex_jsonl(text)
        self.assertTrue(parsed.turn_seen)
        self.assertTrue(parsed.command_event_seen)
        self.assertEqual(parsed.invalid_line_count, 1)
        self.assertEqual(parsed.usage["output_tokens"], 3)

    def test_command_is_fixed_and_uses_no_secret_or_provider_adapter(self):
        command = _build_command(Path("codex.cmd"), Path("work"))
        rendered = " ".join(str(item) for item in command)
        for expected in (
            "--ask-for-approval never",
            f"--model {MODEL}",
            "project_doc_max_bytes=0",
            "--disable plugins",
            "--disable apps",
            "--disable multi_agent",
            "--disable skill_search",
            "--json --ephemeral --ignore-user-config --ignore-rules",
            "--sandbox danger-full-access",
            "--skip-git-repo-check",
        ):
            self.assertIn(expected, rendered)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", rendered)
        for forbidden in (
            "TUZI",
            "DEEPSEEK",
            "E2B",
            "Stirrup",
            "auth.json",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_environment_inherits_codex_home_but_drops_model_keys(self):
        with patch.dict(
            os.environ,
            {
                "TUZI_API_KEY": "tuzi-secret",
                "DEEPSEEK_API_KEY": "deepseek-secret",
                "OPENAI_API_KEY": "openai-secret",
                "CODEX_PERMISSION_PROFILE": "desktop-read-only",
                "CODEX_SANDBOX_NETWORK_DISABLED": "1",
                "CODEX_THREAD_ID": "desktop-thread",
                "PATH": "safe-path",
            },
            clear=True,
        ):
            environment = _sanitized_environment(Path("C:/codex-home"))
        self.assertEqual(environment["CODEX_HOME"], str(Path("C:/codex-home")))
        self.assertEqual(environment["PATH"], "safe-path")
        self.assertFalse(any("API_KEY" in key for key in environment))
        self.assertEqual(
            [key for key in environment if key.startswith("CODEX_")],
            ["CODEX_HOME"],
        )
        self.assertNotIn("secret", json.dumps(environment))

    def test_scope_requires_all_twelve_matched_cells(self):
        identity = CodexLocalCLIIdentityV1(
            version="1.2.3",
            package_lock_sha256="1" * 64,
            executable_sha256="2" * 64,
            executable_path="codex.cmd",
            installation_tree_sha256="3" * 64,
        )
        scope = CodexLocalScreeningScopeV1(
            campaign_id="campaign",
            campaign_manifest_sha256="4" * 64,
            parity_report_sha256="5" * 64,
            source_fingerprint="6" * 64,
            cli=identity,
            task_bindings=twelve_bindings(),
        )
        self.assertEqual(len(scope.task_bindings), 12)
        self.assertEqual(scope.runner_retry_count, 0)
        self.assertEqual(
            scope.builtin_transport_retry_control,
            "codex_chatgpt_provider_not_user_configurable",
        )
        self.assertNotIn("sdk_retry_count", scope.model_dump())
        bad = twelve_bindings()
        bad[-1] = bad[0].model_copy(update={"blind_task_id": "ms_other"})
        with self.assertRaises(ValidationError):
            CodexLocalScreeningScopeV1(
                campaign_id="campaign",
                campaign_manifest_sha256="4" * 64,
                parity_report_sha256="5" * 64,
                source_fingerprint="6" * 64,
                cli=identity,
                task_bindings=bad,
            )

    def test_local_path_source_excludes_old_solver_stacks(self):
        source = (
            Path(__file__).parents[1]
            / "src"
            / "task_generator"
            / "v3_codex_local_solver.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "v3_codex_e2b_solver",
            "v3_rw_task_eval_stirrup_wrapper",
            "SolverExecutionBudgetLedger",
            "DeepSeekSolver",
            "TUZI_API_KEY=",
        ):
            self.assertNotIn(forbidden, source)

    def test_cli_identity_freezes_lock_executable_and_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "node_modules/@openai/codex"
            binary = root / "node_modules/.bin"
            package.mkdir(parents=True)
            binary.mkdir(parents=True)
            (package / "package.json").write_text(
                json.dumps({"version": "1.2.3"}), encoding="utf-8"
            )
            (root / "package-lock.json").write_text("lock", encoding="utf-8")
            executable = binary / ("codex.cmd" if os.name == "nt" else "codex")
            executable.write_text("launcher", encoding="utf-8")
            identity = CodexLocalTooling(root).freeze_identity()
            self.assertEqual(identity.version, "1.2.3")
            self.assertEqual(
                identity.executable_sha256,
                hashlib.sha256(b"launcher").hexdigest(),
            )

    def test_compiled_scope_is_addressed_by_actual_file_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            campaign_root = root / "campaign"
            candidate_root = (
                campaign_root / "blind_staging" / "candidate_packages"
            )
            assignments = []
            for item in twelve_bindings():
                package = candidate_root / item.blind_task_id
                write_package(package)
                assignments.append(
                    {
                        "blind_task_id": item.blind_task_id,
                        "brief_id": item.brief_id,
                        "route_id": item.route_id,
                        "motif": item.motif,
                        "replicate_id": item.replicate_id,
                        "package_fingerprint": item.package_fingerprint,
                        "reality_evidence_sha256": item.reality_evidence_sha256,
                    }
                )
            campaign_root.mkdir(parents=True, exist_ok=True)
            (campaign_root / "matched_screening_campaign.json").write_text(
                json.dumps(
                    {"campaign_id": "campaign", "assignments": assignments}
                ),
                encoding="utf-8",
            )
            parity = root / "parity.json"
            parity.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "network_mode": "none",
                        "read_only_root": True,
                        "provider_credentials_mounted": False,
                        "source_fingerprint": "f" * 64,
                    }
                ),
                encoding="utf-8",
            )
            identity = CodexLocalCLIIdentityV1(
                version="1.2.3",
                package_lock_sha256="1" * 64,
                executable_sha256="2" * 64,
                executable_path="codex.cmd",
                installation_tree_sha256="3" * 64,
            )
            with patch(
                "task_generator.v3_codex_local_solver.governed_source_fingerprint",
                return_value="f" * 64,
            ):
                _, scope_path, digest = compile_scope(
                    campaign_root=campaign_root,
                    parity_report_path=parity,
                    cli_identity=identity,
                    repository_root=root,
                    output_root=root / "output",
                )
            self.assertEqual(
                digest, hashlib.sha256(scope_path.read_bytes()).hexdigest()
            )
            receipt, receipt_path = compile_standing_receipt(
                scope_path=scope_path, output_root=root / "output"
            )
            self.assertEqual(receipt.scope_sha256, digest)
            self.assertTrue(receipt_path.is_file())

    def test_run_one_uses_one_process_and_produces_valid_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            write_package(workspace)
            scope = SimpleNamespace(
                cli=SimpleNamespace(executable_path=str(root / "codex.cmd"))
            )
            (root / "codex.cmd").write_text("fake", encoding="utf-8")
            runner = object.__new__(CodexLocalRunner)
            runner.scope = scope
            runner.output = root / "output"
            runner.codex_home = root / "codex-home"
            runner.python = Path(__file__)
            runner.popen_factory = FakePopen
            outcome, path = runner._run_one(
                kind="private_task",
                task_id="ms_test",
                workspace=workspace,
                expected="deliverable_files/result.xlsx",
                timeout=1800,
            )
            self.assertEqual(outcome.status, "pass")
            self.assertTrue(outcome.delivery.valid)
            self.assertTrue(path.is_file())
            self.assertEqual(outcome.diagnostics.usage["output_tokens"], 7)

    def test_grader_draft_requires_all_seven_unique_criteria(self):
        criterion = {
            "criterion_id": "criterion_factual_accuracy",
            "score": 1.0,
            "rationale": "This is a sufficiently long rationale.",
            "evidence_locators": ["Sheet1!A1"],
        }
        with self.assertRaises(ValidationError):
            CodexLocalGraderDraftV1(
                blind_task_id="ms",
                criteria=[criterion] * 7,
                major_defect=False,
                professional_plausibility="pass",
                effective_rubric_dimensions=7,
            )


if __name__ == "__main__":
    unittest.main()
