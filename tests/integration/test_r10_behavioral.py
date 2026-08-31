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
    R10ModelTaskResultV1,
    TeacherAnchorCheckV1,
    aggregate_behavioral_result,
    audit_teacher_anchors,
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
from run_r10_behavioral_pilot import _remote_command, _remote_script, _scope_sha256, _stage_solver, _write_agent_script
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

    def test_remote_transport_uses_mounted_script_without_stdin_or_tty(self):
        command = _remote_command("/remote/workspace", stack="gpt-5.6-sol@chatgpt_codex")
        self.assertIn("/workspace/.r10_agent.sh", command)
        self.assertNotIn("docker run -i", command)
        self.assertNotIn("sh -s", command)

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


if __name__ == "__main__":
    unittest.main()
