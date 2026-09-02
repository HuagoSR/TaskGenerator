from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from task_generator.core.deliverable_contract import DeliverableContractCompiler
from task_generator.evaluation.r10_behavioral import (
    R10BehavioralScopeV1,
    R10PilotTaskBindingV1,
    R10JudgeDraftV1,
    R10JudgeReviewV1,
    R10ModelTaskResultV1,
    TeacherAnchorCheckV1,
    aggregate_behavioral_result,
    audit_teacher_anchors,
    diagnose_pilot_discrimination,
    finalize_judge_review,
    inspect_delivery,
)
from task_generator.planning.scenario_task_compiler import (
    TaskSpecificRubricCriterionV1,
    TaskSpecificRubricV1,
)

TEST_ROOT = Path(__file__).resolve().parents[2] / "Test"
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))
from run_r10_behavioral_pilot import (
    REMOTE_CODEX_AUTH_DIR, REMOTE_TUZI_ENV_FILE, TUZI_CODEX_STACK, _codex_turn_completed, _remote_command,
    _record_probe, _remote_script, _run_remote, _scp_command, _scope_sha256, _stage_solver, _write_agent_script,
)
from run_r10_skill_compiler import _ssh
from r10_local_codex_judge import _redact, local_codex_command


def workbook_bytes(value: str) -> bytes:
    workbook = Workbook()
    workbook.active["A1"] = value
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def write_docx(path: Path, text: str = "Memo") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"/>")
        archive.writestr("word/document.xml", f"<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>")


def rubric() -> TaskSpecificRubricV1:
    return TaskSpecificRubricV1(criteria=[
        TaskSpecificRubricCriterionV1(criterion_id="c1", decision_id="d1", weight=0.5, description="one"),
        TaskSpecificRubricCriterionV1(criterion_id="c2", decision_id="d2", weight=0.5, description="two"),
        TaskSpecificRubricCriterionV1(criterion_id="c3", decision_id="d3", weight=0.0 + 0.000001, description="three"),
    ])


_SOLVERS = ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode")


def pilot_bindings() -> list[R10PilotTaskBindingV1]:
    return [
        R10PilotTaskBindingV1(
            task_id=f"task-{index}", domain="audit_compliance" if index < 2 else "procurement_operations",
            package_root=f"/task/{index}", package_tree_sha256=f"{index:064x}",
            candidate_tree_sha256=f"{index + 4:064x}", task_compilation_sha256=f"{index + 8:064x}",
            deliverable_contract_sha256=f"{index + 12:064x}", expected_delivery="deliverable_files/result.xlsx",
        )
        for index in range(4)
    ]


def pilot_review(task_id: str, judge_id: str, score: float, major: bool = False) -> R10JudgeReviewV1:
    return R10JudgeReviewV1.model_validate({
        "task_id": task_id, "judge_id": judge_id, "weighted_score": score, "major_defect": major,
        "assessments": [
            {"decision_id": f"d{index}", "rating": "met", "major_error": major and index == 0,
             "evidence_paths": [f"candidate/file-{index}.txt"], "rationale": "fixture assessment"}
            for index in range(3)
        ],
    })


def pilot_records(
    scores: dict[str, dict[str, tuple[float, float] | None]],
    *,
    major: dict[str, dict[str, tuple[bool, bool]]] | None = None,
) -> list[R10ModelTaskResultV1]:
    records: list[R10ModelTaskResultV1] = []
    for task_id, by_solver in scores.items():
        for solver in _SOLVERS:
            pair = by_solver[solver]
            reviews = []
            if pair is not None:
                major_pair = (major or {}).get(task_id, {}).get(solver, (False, False))
                reviews = [
                    pilot_review(task_id, judge, score, is_major)
                    for judge, score, is_major in zip(_SOLVERS, pair, major_pair)
                ]
            records.append(R10ModelTaskResultV1(
                task_id=task_id, solver_id=solver, delivery_valid=True, reviews=reviews,
            ))
    return records


class R10BehavioralTests(unittest.TestCase):

    def test_teacher_anchor_audit_blocks_false_percentage_relation(self):
        audit = audit_teacher_anchors([TeacherAnchorCheckV1(
            check_id="variation", decision_id="delivery", kind="percentage_threshold",
            relation="within", source_paths=["candidate/contract.txt"],
            numerator=Decimal("3"), denominator=Decimal("40"), threshold=Decimal("5"),
        )])
        self.assertEqual(audit.decision, "blocked")
        self.assertEqual(audit.findings[0].observed, "3/40=7.500%")

    def test_teacher_anchor_audit_accepts_corrected_percentage_relation(self):
        audit = audit_teacher_anchors([TeacherAnchorCheckV1(
            check_id="variation", decision_id="delivery", kind="percentage_threshold",
            relation="exceeds", source_paths=["candidate/contract.txt"],
            numerator=Decimal("3"), denominator=Decimal("40"), threshold=Decimal("5"),
        )])
        self.assertEqual(audit.decision, "pass")

    def test_judge_schema_requires_all_declared_assessment_fields(self) -> None:
        schema = R10JudgeDraftV1.model_json_schema()
        assessment = schema["$defs"]["DecisionAssessmentV1"]
        self.assertEqual(set(assessment["properties"]), set(assessment["required"]))
    def test_scope_hash_uses_canonical_json_not_an_inherited_mixin(self):
        bindings = [
            R10PilotTaskBindingV1(task_id=f"task-{index}", domain="audit_compliance" if index < 2 else "procurement_operations", package_root=f"/task/{index}", package_tree_sha256=f"{index:064x}", candidate_tree_sha256=f"{index + 4:064x}", task_compilation_sha256=f"{index + 8:064x}", deliverable_contract_sha256=f"{index + 12:064x}", expected_delivery="deliverable_files/result.xlsx")
            for index in range(4)
        ]
        scope = R10BehavioralScopeV1(campaign_id="campaign", source_commit="a" * 40, image="image", image_sha256="b" * 64, bindings=bindings)
        self.assertEqual(_scope_sha256(scope), _scope_sha256(scope))

    def test_solver_stage_excludes_teacher_material(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            task = root / "task"
            (task / "reference_files").mkdir(parents=True)
            (task / "reference_files" / "source.txt").write_text("candidate", encoding="utf-8")
            (task / "teacher").mkdir()
            (task / "teacher" / "truth.json").write_text("teacher", encoding="utf-8")
            (task / "TASK.md").write_text("candidate task", encoding="utf-8")
            (task / "deliverable_contract.json").write_text("{}", encoding="utf-8")
            workspace = root / "workspace"
            _stage_solver(task, workspace)
            self.assertEqual({item.name for item in workspace.iterdir()}, {"TASK.md", "deliverable_contract.json", "reference_files", "deliverable_files"})

    def test_remote_stack_commands_are_native_and_secret_mount_is_scoped(self):
        gpt = _remote_script("/tmp/work", stack="gpt-5.6-sol@chatgpt_codex")
        deepseek = _remote_script("/tmp/work", stack="deepseek-v4-pro@official_opencode")
        self.assertIn("codex", gpt)
        self.assertNotIn("DEEPSEEK_API_KEY", gpt)
        self.assertIn("opencode run", deepseek)
        self.assertIn("/run/secrets/deepseek_api_key", deepseek)
        self.assertNotIn("tuzi", deepseek.casefold())
        self.assertNotIn("stirrup", deepseek.casefold())
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", gpt)
        self.assertNotIn("--ask-for-approval", gpt)
        self.assertNotIn("--sandbox danger-full-access", gpt)
        self.assertIn("CODEX_HOME=/run/codex-home", gpt)
        self.assertIn("PIP_TARGET=/tmp/r10-pylibs", deepseek)
        self.assertIn("PYTHONPATH=/tmp/r10-pylibs", deepseek)

    def test_r10_10_model_and_reasoning_overrides_are_allowlisted(self):
        terra = _remote_script(
            "/tmp/work", stack="gpt-5.6-sol@chatgpt_codex", grade=True,
            model_override="gpt-5.6-terra", codex_reasoning_effort="medium",
        )
        flash = _remote_script(
            "/tmp/work", stack="deepseek-v4-pro@official_opencode", grade=True,
            model_override="deepseek-v4-flash", opencode_variant="high",
        )
        self.assertIn("--model gpt-5.6-terra", terra)
        self.assertIn("model_reasoning_effort=medium", terra)
        self.assertIn("--model deepseek/deepseek-v4-flash --variant high", flash)
        with self.assertRaises(ValueError):
            _remote_script(
                "/tmp/work", stack="gpt-5.6-sol@chatgpt_codex",
                model_override="gpt-5.4-pro",
            )

    def test_tuzi_codex_uses_ephemeral_responses_provider_without_chatgpt_auth(self):
        script = _remote_script("/tmp/work", stack=TUZI_CODEX_STACK, grade=True)
        command = _remote_command("/remote/workspace", stack=TUZI_CODEX_STACK)
        self.assertIn("model_provider = \"tuzi\"", script)
        self.assertIn("wire_api = \"responses\"", script)
        self.assertIn("request_max_retries = 0", script)
        self.assertIn("stream_max_retries = 0", script)
        self.assertIn("TUZI_API_KEY", script)
        self.assertIn("TUZI_API_KEY=$(printf '%s' \"$TUZI_API_KEY\" | tr -d '\\r\\n')", script)
        self.assertIn("tr -d '\\r\\n'", script)
        self.assertNotIn("--ignore-user-config", script)
        self.assertNotIn("auth_dir:/run/codex-home", command)
        self.assertIn(REMOTE_TUZI_ENV_FILE, command)
        self.assertIn("eval_tuzi_env:ro", command)

    def test_tuzi_stack_is_a_valid_r10_solver_and_judge_identity(self):
        bindings = [
            R10PilotTaskBindingV1(task_id=f"task-{index}", domain="audit_compliance" if index < 2 else "procurement_operations", package_root=f"/task/{index}", package_tree_sha256=f"{index:064x}", candidate_tree_sha256=f"{index + 4:064x}", task_compilation_sha256=f"{index + 8:064x}", deliverable_contract_sha256=f"{index + 12:064x}", expected_delivery="deliverable_files/result.xlsx")
            for index in range(4)
        ]
        scope = R10BehavioralScopeV1(
            campaign_id="tuzi-campaign", source_commit="a" * 40, image="image", image_sha256="b" * 64,
            solver_stacks=(TUZI_CODEX_STACK, "deepseek-v4-pro@official_opencode"),
            judges=(TUZI_CODEX_STACK, "deepseek-v4-pro@official_opencode"), bindings=bindings,
        )
        self.assertEqual(scope.solver_stacks[0], TUZI_CODEX_STACK)

    def test_remote_transport_uses_mounted_script_without_stdin_or_tty(self):
        command = _remote_command("/remote/workspace", stack="gpt-5.6-sol@chatgpt_codex")
        self.assertIn("/workspace/.r10_agent.sh", command)
        self.assertNotIn("docker run -i", command)
        self.assertNotIn("sh -s", command)
        self.assertIn(REMOTE_CODEX_AUTH_DIR, command)
        self.assertIn(":/run/codex-home:rw", command)
        self.assertIn("rm -rf pylibs .pylibs .venv .cache node_modules __pycache__", command)
        self.assertIn("rm -rf .r10_return", command)
        self.assertIn("deliverable_files .docx_office_check", command)
        self.assertIn("rm -rf pylibs .pylibs", command)
        self.assertNotIn("cp -aL . ", command)

    def test_remote_return_imports_only_allowlisted_evidence(self):
        from subprocess import CompletedProcess
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as root:
            local = Path(root) / "workspace"
            local.mkdir()
            (local / "input.txt").write_text("candidate input", encoding="utf-8")

            def scp(source: str, destination: str, **_kwargs):
                if source.startswith("huago-cone:"):
                    returned = Path(destination) / ".r10_return"
                    (returned / "deliverable_files").mkdir(parents=True)
                    (returned / "deliverable_files" / "result.xlsx").write_bytes(workbook_bytes("result"))
                    (returned / "agent.jsonl").write_text('{"type":"turn.completed"}\n', encoding="utf-8")
                return CompletedProcess([], 0, "", "")

            ssh_results = [
                CompletedProcess([], 0, "", ""),
                CompletedProcess([], 0, "remote complete", ""),
                CompletedProcess([], 1, "", "terminal event absent"),
            ]
            with patch("run_r10_behavioral_pilot._scp", side_effect=scp), patch(
                "run_r10_behavioral_pilot._ssh", side_effect=ssh_results
            ):
                code, stdout, stderr = _run_remote(
                    host="huago-cone", remote="/remote/workspace", local=local,
                    stack="deepseek-v4-pro@official_opencode",
                )

            self.assertEqual(code, 0)
            self.assertEqual(stdout, "remote complete")
            self.assertEqual(stderr, "")
            self.assertTrue((local / "deliverable_files" / "result.xlsx").is_file())
            self.assertTrue((local / "agent.jsonl").is_file())
            self.assertFalse((local / "pylibs").exists())
            self.assertFalse((local / ".r10_agent.sh").exists())

    def test_failed_return_download_never_merges_partial_evidence(self):
        from subprocess import CompletedProcess
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as root:
            local = Path(root) / "workspace"
            local.mkdir()

            def scp(source: str, destination: str, **_kwargs):
                if source.startswith("huago-cone:"):
                    returned = Path(destination) / ".r10_return"
                    returned.mkdir(parents=True)
                    (returned / "agent.jsonl").write_text("partial", encoding="utf-8")
                    return CompletedProcess([], 124, "", "timeout")
                return CompletedProcess([], 0, "", "")

            ssh_results = [
                CompletedProcess([], 0, "", ""),
                CompletedProcess([], 0, "remote complete", ""),
                CompletedProcess([], 1, "", "terminal event absent"),
            ]
            with patch("run_r10_behavioral_pilot._scp", side_effect=scp), patch(
                "run_r10_behavioral_pilot._ssh", side_effect=ssh_results
            ):
                code, _stdout, stderr = _run_remote(
                    host="huago-cone", remote="/remote/workspace", local=local,
                    stack="deepseek-v4-pro@official_opencode",
                )

            self.assertEqual(code, 124)
            self.assertIn("r10_remote_download_failed", stderr)
            self.assertFalse((local / "agent.jsonl").exists())

    def test_remote_scp_transport_is_noninteractive_and_bounded(self):
        command = _scp_command("source", "huago-cone:/remote")
        self.assertEqual(command[:2], ["scp", "-r"])
        self.assertIn("BatchMode=yes", command)
        self.assertIn("ConnectTimeout=30", command)
        self.assertIn("ServerAliveInterval=15", command)
        self.assertIn("ServerAliveCountMax=2", command)

    def test_remote_ssh_transport_uses_keepalive_for_quiet_agent_runs(self):
        from unittest.mock import patch

        with patch("run_r10_skill_compiler._run") as run:
            _ssh("huago-cone", "true", timeout=9)
        command = run.call_args.args[0]
        self.assertEqual(command[0], "ssh")
        self.assertIn("BatchMode=yes", command)
        self.assertIn("ConnectTimeout=30", command)
        self.assertIn("ServerAliveInterval=15", command)
        self.assertIn("ServerAliveCountMax=4", command)

    def test_remote_gpt_requires_a_completed_turn_event(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "agent.jsonl"
            path.write_text('{"type":"turn.started"}\n', encoding="utf-8")
            self.assertFalse(_codex_turn_completed(path))
            path.write_text('{"type":"turn.started"}\n{"type":"turn.completed"}\n', encoding="utf-8")
            self.assertTrue(_codex_turn_completed(path))

    def test_public_probe_persists_delivery_models_as_json(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)

            def complete_probe(**kwargs):
                workspace = kwargs["local"]
                output = workspace / "deliverable_files"
                (output / "probe.xlsx").write_bytes(workbook_bytes("probe"))
                write_docx(output / "probe.docx", "probe")
                (workspace / "docx_office_opened.txt").write_text("deliverable_files/probe.docx\n", encoding="utf-8")
                (workspace / "agent.jsonl").write_text('{"type":"turn.completed"}\n', encoding="utf-8")
                return 0, "", ""

            with patch("run_r10_behavioral_pilot._run_remote", side_effect=complete_probe):
                self.assertTrue(_record_probe(
                    output_root=root_path, host="host", remote_root="/remote",
                    stack="gpt-5.6-sol@chatgpt_codex",
                ))
            payload = json.loads((root_path / "public_probes" / "gpt-5.6-sol@chatgpt_codex" / "probe_result.json").read_text(encoding="utf-8"))
            self.assertTrue(payload["xlsx"]["valid"])

    def test_local_judge_command_is_workspace_limited_and_has_no_remote_transport(self):
        workspace = Path("C:/public/r10-workspace")
        command = local_codex_command(command="codex", model="gpt-5.6-sol", workspace=workspace)
        self.assertIn("--approve-for-me", command)
        self.assertNotIn("--sandbox", command)  # --approve-for-me selects workspace-write in Codex 0.149.1.
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ephemeral", command)
        rendered = " ".join(command)
        self.assertNotIn("docker", rendered.casefold())
        self.assertNotIn("ssh", rendered.casefold())
        self.assertNotIn("auth.json", rendered.casefold())

    def test_local_judge_diagnostics_redact_credential_shaped_text(self):
        output = _redact("Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz\napi_key=secret-value")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", output)
        self.assertNotIn("secret-value", output)
        self.assertIn("[REDACTED]", output)

    def test_mounted_linux_script_is_written_with_lf_only(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "agent.sh"
            _write_agent_script(path, "set -eu\r\necho ready\r\n")
            self.assertEqual(path.read_bytes(), b"set -eu\necho ready\n")

    def test_xlsx_delivery_rejects_copy_and_accepts_real_workbook(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            (workspace / "deliverable_files").mkdir()
            result = workspace / "deliverable_files" / "review.xlsx"
            source = workbook_bytes("source")
            result.write_bytes(source)
            copy = inspect_delivery(workspace, expected="deliverable_files/review.xlsx", input_hashes={__import__("hashlib").sha256(source).hexdigest()})
            self.assertFalse(copy.valid)
            self.assertEqual(copy.first_failure, "delivery_copies_input")
            result.write_bytes(workbook_bytes("analysis"))
            valid = inspect_delivery(workspace, expected="deliverable_files/review.xlsx", input_hashes=set())
            self.assertTrue(valid.valid)
            self.assertEqual(valid.format, "xlsx")

    def test_docx_delivery_requires_ooxml_and_content(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            (workspace / "deliverable_files").mkdir()
            result = workspace / "deliverable_files" / "memo.docx"
            result.write_bytes(b"not a document")
            self.assertFalse(inspect_delivery(workspace, expected="deliverable_files/memo.docx", input_hashes=set(), verify_docx_with_office=False).valid)
            write_docx(result)
            valid = inspect_delivery(workspace, expected="deliverable_files/memo.docx", input_hashes=set(), verify_docx_with_office=False)
            self.assertTrue(valid.valid)
            self.assertEqual(valid.format, "docx")

    def test_judge_score_is_recomputed_from_ratings(self):
        strict_rubric = TaskSpecificRubricV1(criteria=[
            TaskSpecificRubricCriterionV1(criterion_id="c1", decision_id="d1", weight=0.5, description="one"),
            TaskSpecificRubricCriterionV1(criterion_id="c2", decision_id="d2", weight=0.3, description="two"),
            TaskSpecificRubricCriterionV1(criterion_id="c3", decision_id="d3", weight=0.2, description="three"),
        ])
        draft = R10JudgeDraftV1.model_validate({"task_id": "task", "assessments": [
            {"decision_id": "d1", "rating": "met", "major_error": False, "evidence_paths": ["a"], "rationale": "ok"},
            {"decision_id": "d2", "rating": "partial", "major_error": False, "evidence_paths": ["b"], "rationale": "partial"},
            {"decision_id": "d3", "rating": "not_met", "major_error": True, "evidence_paths": ["c"], "rationale": "miss"},
        ]})
        review = finalize_judge_review(judge_id="gpt-5.6-sol@chatgpt_codex", draft=draft, rubric=strict_rubric)
        self.assertEqual(review.weighted_score, 0.65)
        self.assertTrue(review.major_defect)

    def test_aggregate_requires_three_valid_deliveries_per_solver(self):
        records = []
        for solver in ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"):
            for index in range(4):
                reviews = []
                if index < 3:
                    for judge in ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"):
                        reviews.append({"task_id": f"task-{index}", "judge_id": judge, "assessments": [
                            {"decision_id": "d1", "rating": "met", "major_error": False, "evidence_paths": ["a"], "rationale": "ok"},
                            {"decision_id": "d2", "rating": "met", "major_error": False, "evidence_paths": ["b"], "rationale": "ok"},
                            {"decision_id": "d3", "rating": "met", "major_error": False, "evidence_paths": ["c"], "rationale": "ok"},
                        ], "weighted_score": 1.0, "major_defect": False})
                records.append(R10ModelTaskResultV1(task_id=f"task-{index}", solver_id=solver, delivery_valid=index < 3, reviews=reviews))
        result = aggregate_behavioral_result(records)
        self.assertEqual(result.decision, "behaviorally_admitted")
        self.assertTrue(result.low_model_separation)

    def test_repeated_evidence_insufficiency_is_revision_candidate(self):
        records = []
        for solver in ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"):
            for index in range(4):
                reviews = []
                for judge in ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"):
                    reviews.append({"task_id": f"task-{index}", "judge_id": judge, "assessments": [
                        {"decision_id": "d1", "rating": "met", "major_error": False, "evidence_paths": ["a"], "rationale": "ok", "evidence_insufficient": True},
                        {"decision_id": "d2", "rating": "met", "major_error": False, "evidence_paths": ["b"], "rationale": "ok"},
                        {"decision_id": "d3", "rating": "met", "major_error": False, "evidence_paths": ["c"], "rationale": "ok"},
                    ], "weighted_score": 1.0, "major_defect": False})
                records.append(R10ModelTaskResultV1(task_id=f"task-{index}", solver_id=solver, delivery_valid=True, reviews=reviews))
        result = aggregate_behavioral_result(records)
        self.assertEqual(result.decision, "task_design_revision_candidate")
        self.assertEqual(result.recurring_insufficient_evidence_decisions, ["d1"])

    def test_repeated_cross_stack_major_error_requires_anchor_review(self):
        records = []
        for solver in ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"):
            for index in range(4):
                reviews = []
                for judge in ("gpt-5.6-sol@chatgpt_codex", "deepseek-v4-pro@official_opencode"):
                    reviews.append({"task_id": f"task-{index}", "judge_id": judge, "assessments": [
                        {"decision_id": "d1", "rating": "not_met", "major_error": index == 0, "evidence_paths": ["a"], "rationale": "same issue"},
                        {"decision_id": "d2", "rating": "met", "major_error": False, "evidence_paths": ["b"], "rationale": "ok"},
                        {"decision_id": "d3", "rating": "met", "major_error": False, "evidence_paths": ["c"], "rationale": "ok"},
                    ], "weighted_score": 0.7, "major_defect": index == 0})
                records.append(R10ModelTaskResultV1(task_id=f"task-{index}", solver_id=solver, delivery_valid=True, reviews=reviews))
        result = aggregate_behavioral_result(records)
        self.assertEqual(result.decision, "task_design_revision_candidate")
        self.assertEqual(result.recurring_major_error_decisions, ["d1"])

    def test_pilot_discrimination_classifies_saturation_near_tie_clean_and_ambiguous(self):
        records = pilot_records({
            "task-0": {solver: (1.0, 1.0) for solver in _SOLVERS},
            "task-1": {
                _SOLVERS[0]: (0.94, 0.94), _SOLVERS[1]: (0.93, 0.93),
            },
            "task-2": {
                _SOLVERS[0]: (0.92, 0.92), _SOLVERS[1]: (0.80, 0.80),
            },
            "task-3": {
                _SOLVERS[0]: (1.0, 1.0), _SOLVERS[1]: (0.50, 0.875),
            },
        }, major={"task-3": {_SOLVERS[1]: (True, False)}})
        aggregate = aggregate_behavioral_result(records)
        report = diagnose_pilot_discrimination(
            records, behavioral_result=aggregate, bindings=pilot_bindings(),
        )
        classifications = {item.task_id: item.classification for item in report.task_diagnoses}
        self.assertEqual(classifications, {
            "task-0": "saturated", "task-1": "near_tie",
            "task-2": "cleanly_discriminative", "task-3": "judge_ambiguous",
        })
        self.assertEqual(report.cohort_decision, "compiler_revision_candidate")
        self.assertIn("score_saturation", report.compiler_signals)
        self.assertIn("judge_boundary_ambiguous", report.compiler_signals)

    def test_pilot_discrimination_needs_two_clean_tasks_for_scale_discussion(self):
        records = pilot_records({
            "task-0": {_SOLVERS[0]: (0.90, 0.90), _SOLVERS[1]: (0.80, 0.80)},
            "task-1": {_SOLVERS[0]: (0.91, 0.91), _SOLVERS[1]: (0.80, 0.80)},
            "task-2": {solver: (1.0, 1.0) for solver in _SOLVERS},
            "task-3": {solver: (1.0, 1.0) for solver in _SOLVERS},
        })
        report = diagnose_pilot_discrimination(
            records, behavioral_result=aggregate_behavioral_result(records), bindings=pilot_bindings(),
        )
        self.assertEqual(report.cleanly_discriminative_count, 2)
        self.assertEqual(report.cohort_decision, "scale_discussion_ready")

    def test_pilot_discrimination_marks_missing_judge_score_incomplete(self):
        records = pilot_records({
            "task-0": {_SOLVERS[0]: (0.90, 0.90), _SOLVERS[1]: (0.80, 0.80)},
            "task-1": {solver: (1.0, 1.0) for solver in _SOLVERS},
            "task-2": {solver: (1.0, 1.0) for solver in _SOLVERS},
            "task-3": {solver: (1.0, 1.0) for solver in _SOLVERS},
        })
        missing = next(item for item in records if item.task_id == "task-0" and item.solver_id == _SOLVERS[0])
        records[records.index(missing)] = missing.model_copy(update={"reviews": missing.reviews[:1]})
        report = diagnose_pilot_discrimination(
            records, behavioral_result=aggregate_behavioral_result(records), bindings=pilot_bindings(),
        )
        diagnosis = next(item for item in report.task_diagnoses if item.task_id == "task-0")
        self.assertEqual(diagnosis.classification, "incomplete")
        self.assertFalse(report.input_complete)

    def test_pilot_discrimination_rejects_aggregate_or_binding_fingerprint_drift(self):
        records = pilot_records({
            f"task-{index}": {solver: (1.0, 1.0) for solver in _SOLVERS}
            for index in range(4)
        })
        aggregate = aggregate_behavioral_result(records)
        with self.assertRaisesRegex(ValueError, "behavioral_result_drift"):
            diagnose_pilot_discrimination(
                records,
                behavioral_result=aggregate.model_copy(update={"low_model_separation": False}),
                bindings=pilot_bindings(),
            )
        drifted = pilot_bindings()
        drifted[0] = drifted[0].model_copy(update={"task_id": "unexpected-task"})
        with self.assertRaisesRegex(ValueError, "record_binding_drift"):
            diagnose_pilot_discrimination(records, behavioral_result=aggregate, bindings=drifted)

    def test_diagnose_pilot_cli_is_read_only_and_writes_a_report(self):
        from unittest.mock import patch
        from task_generator.cli.scenario_first import main

        records = pilot_records({
            f"task-{index}": {solver: (1.0, 1.0) for solver in _SOLVERS}
            for index in range(4)
        })
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            records_path = root_path / "records.json"
            result_path = root_path / "result.json"
            bindings_path = root_path / "scope.json"
            output = root_path / "report.json"
            records_path.write_text(json.dumps([item.model_dump(mode="json") for item in records]), encoding="utf-8")
            result_path.write_text(json.dumps({"aggregate": aggregate_behavioral_result(records).model_dump(mode="json")}), encoding="utf-8")
            bindings_path.write_text(json.dumps({"bindings": [item.model_dump(mode="json") for item in pilot_bindings()]}), encoding="utf-8")
            input_bytes = (records_path.read_bytes(), result_path.read_bytes(), bindings_path.read_bytes())
            with patch("sys.argv", [
                "taskgen-scenario-first", "--action", "diagnose-pilot",
                "--records", str(records_path), "--behavioral-result", str(result_path),
                "--bindings", str(bindings_path), "--output", str(output),
            ]):
                main()
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["cohort_decision"], "compiler_revision_candidate")
            self.assertEqual(input_bytes, (records_path.read_bytes(), result_path.read_bytes(), bindings_path.read_bytes()))


if __name__ == "__main__":
    unittest.main()
