from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from task_generator.core.scenario_first import ProfessionalRuleSetV1, ScenarioBibleV1, WorkSeedV1
from task_generator.planning.scenario_evidence_experiment import (
    ConditionBlindFindingV1,
    ConditionBlindPairReviewV1,
    OfficialDeepSeekConditionBlindReviewer,
    ScenarioEvidenceAdmissionReportV1,
    ScenarioEvidenceCampaignScopeV1,
    ScenarioEvidenceExperiment,
    ScenarioEvidenceExperimentPlanV1,
    ScenarioEvidenceSessionV1,
    aggregate_experiment,
    compile_campaign_scope,
)
from task_generator.substrate.professional_skills import (
    LoadedProfessionalSkillV1,
    ProfessionalSkillCatalogEntryV1,
)


def _seed() -> WorkSeedV1:
    return WorkSeedV1.model_validate({
        "seed_id": "seed-audit", "domain": "audit_compliance", "role": "Audit Senior",
        "public_sources": [{"source_id": "s", "normalized_source_id": "n", "block_ids": ["b"], "locator": "https://example.test/source", "abstraction_note": "method only"}],
        "trigger_event": "conflicting report", "business_goal": "evaluate evidence", "typical_inputs": ["report"],
        "natural_questions": ["what corroboration is needed"], "expected_deliverable": "workpaper", "audience": "manager", "abstraction_boundary": "not organization facts",
    })


def _rules() -> ProfessionalRuleSetV1:
    return ProfessionalRuleSetV1.model_validate({
        "rule_set_id": "rules-audit", "domain": "audit_compliance", "rules": [{
            "rule_id": "rule-1", "title": "Reliable evidence", "source_refs": [{"source_id": "s", "normalized_source_id": "n", "block_ids": ["b"], "locator": "https://example.test/rule", "abstraction_note": "method only"}],
            "applicability_conditions": ["report used as evidence"], "evidence_requirements": ["corroborate"], "exceptions": [], "forbidden_assumptions": ["report is self-validating"], "acceptable_handling": ["follow up"],
        }],
    })


def _bible() -> ScenarioBibleV1:
    return ScenarioBibleV1.model_validate({
        "scenario_id": "scenario-audit", "work_seed_id": "seed-audit", "rule_set_id": "rules-audit", "organization_name": "Example Co",
        "roles": [{"role_id": "senior", "title": "Audit Senior", "authorities": ["document evidence"]}],
        "facts": [
            {"fact_id": "f1", "kind": "organization", "statement": "Example Co is audited.", "occurred_at": 1, "knowledge": "confirmed", "rule_ids": []},
            {"fact_id": "f2", "kind": "open_issue", "statement": "The report needs corroboration.", "occurred_at": 2, "knowledge": "unresolved", "rule_ids": ["rule-1"]},
            {"fact_id": "f3", "kind": "treatment", "statement": "Obtain corroborating system evidence before reliance.", "occurred_at": 3, "knowledge": "confirmed", "rule_ids": ["rule-1"]},
        ],
        "correct_treatments": ["Obtain corroborating system evidence before reliance."],
    })


def _skill() -> LoadedProfessionalSkillV1:
    entry = ProfessionalSkillCatalogEntryV1(
        contract_version="r10.professional_skill_catalog_entry.1", skill_id="r10.audit", name="audit-skill",
        description="Use for audit evidence reliability.", domain="audit_compliance", relative_path="audit", version="0.1.0", status="curated",
    )
    return LoadedProfessionalSkillV1(entry=entry, skill_markdown="---\nname: audit-skill\ndescription: Use for audit evidence reliability.\n---\n\n# Audit", reference_markdown={"references/source-map.md": "source-a"})


class ScenarioEvidenceExperimentTests(unittest.TestCase):
    def _session(self, condition: str) -> ScenarioEvidenceSessionV1:
        bible, rules, skill = _bible(), _rules(), _skill()
        return ScenarioEvidenceSessionV1(
            session_id=f"session-{condition}", scenario_id=bible.scenario_id, domain="audit_compliance", condition=condition,
            bible_sha256=bible.canonical_sha256(), rule_set_sha256=rules.canonical_sha256(),
            skill_id=skill.entry.skill_id if condition == "with_skill" else None,
            skill_sha256=ScenarioEvidenceExperiment.sha256_json(skill.model_dump(mode="json")) if condition == "with_skill" else None,
            skill_source_ids=["source-a"] if condition == "with_skill" else [],
            image="taskgenerator-eval:test", image_sha256="a" * 64,
        )

    @staticmethod
    def _valid_output(workspace: Path, *, with_skill: bool, leak: bool = False, omit_no_skill_sources: bool = False) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Evidence"
        sheet.append(["Invoice", "Amount"])
        sheet.append(["INV-01", 100])
        workbook.save(workspace / "candidate" / "report.xlsx")
        (workspace / "candidate" / "controller_note.txt").write_text("The controller sent the report for the review file." + (" Exception" if leak else ""), encoding="utf-8")
        (workspace / "teacher" / "scenario_extension.json").write_text(json.dumps({"facts": []}), encoding="utf-8")
        artifacts = []
        for name in ("report.xlsx", "controller_note.txt"):
            entry = {"path": f"candidate/{name}", "fact_ids": ["f1", "f2"], "professional_judgments": ["Assess report reliability"]}
            if with_skill or not omit_no_skill_sources:
                entry["skill_source_ids"] = ["source-a"] if with_skill else []
            artifacts.append(entry)
        (workspace / "teacher" / "evidence_map.json").write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")

    def test_staging_preserves_ab_difference_only_at_skill_package(self):
        experiment, bible, rules, skill = ScenarioEvidenceExperiment(), _bible(), _rules(), _skill()
        with tempfile.TemporaryDirectory() as root:
            without_workspace = Path(root) / "without"
            with_workspace = Path(root) / "with"
            experiment.stage_session(workspace=without_workspace, session=self._session("without_skill"), bible=bible, rules=rules, skill=None)
            experiment.stage_session(workspace=with_workspace, session=self._session("with_skill"), bible=bible, rules=rules, skill=skill)
            self.assertFalse((without_workspace / "teacher" / "professional_skill").exists())
            self.assertTrue((with_workspace / "teacher" / "professional_skill" / "SKILL.md").is_file())
            self.assertEqual((without_workspace / "teacher" / "scenario_bible.json").read_bytes(), (with_workspace / "teacher" / "scenario_bible.json").read_bytes())

    def test_admission_accepts_valid_bundle_and_blocks_leakage(self):
        experiment, bible, rules = ScenarioEvidenceExperiment(), _bible(), _rules()
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            experiment.stage_session(workspace=workspace, session=self._session("without_skill"), bible=bible, rules=rules, skill=None)
            self._valid_output(workspace, with_skill=False)
            self.assertEqual(experiment.admit(session=self._session("without_skill"), workspace=workspace, bible=bible).decision, "pass")
            self._valid_output(workspace, with_skill=False, leak=True)
            report = experiment.admit(session=self._session("without_skill"), workspace=workspace, bible=bible)
            self.assertEqual(report.decision, "blocked")
            self.assertIn("answer_leakage_absent", [item.code for item in report.findings if not item.passed])

    def test_source_attribution_is_optional_and_does_not_control_admission(self):
        experiment, bible, rules = ScenarioEvidenceExperiment(), _bible(), _rules()
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            session = self._session("without_skill")
            experiment.stage_session(workspace=workspace, session=session, bible=bible, rules=rules, skill=None)
            self._valid_output(workspace, with_skill=False, omit_no_skill_sources=True)
            self.assertEqual(experiment.admit(session=session, workspace=workspace, bible=bible).decision, "pass")
            payload = json.loads((workspace / "teacher" / "evidence_map.json").read_text(encoding="utf-8"))
            payload["artifacts"][0]["skill_source_ids"] = ["optional-source"]
            (workspace / "teacher" / "evidence_map.json").write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(experiment.admit(session=session, workspace=workspace, bible=bible).decision, "pass")

    def test_with_skill_does_not_require_file_level_source_attribution(self):
        experiment, bible, rules, skill = ScenarioEvidenceExperiment(), _bible(), _rules(), _skill()
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            session = self._session("with_skill")
            experiment.stage_session(workspace=workspace, session=session, bible=bible, rules=rules, skill=skill)
            self._valid_output(workspace, with_skill=True)
            payload = json.loads((workspace / "teacher" / "evidence_map.json").read_text(encoding="utf-8"))
            payload["artifacts"][0].pop("skill_source_ids")
            payload["artifacts"][1].pop("skill_source_ids")
            (workspace / "teacher" / "evidence_map.json").write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(experiment.admit(session=session, workspace=workspace, bible=bible).decision, "pass")
            payload["artifacts"][0]["skill_source_ids"] = [1]
            (workspace / "teacher" / "evidence_map.json").write_text(json.dumps(payload), encoding="utf-8")
            report = experiment.admit(session=session, workspace=workspace, bible=bible)
            closed = next(item for item in report.findings if item.code == "evidence_map_closed")
            self.assertIn("evidence_map_skill_source_invalid", closed.details["errors"])

    def test_admission_accepts_registered_extension_fact_and_blocks_unregistered_one(self):
        experiment, bible, rules = ScenarioEvidenceExperiment(), _bible(), _rules()
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            session = self._session("without_skill")
            experiment.stage_session(workspace=workspace, session=session, bible=bible, rules=rules, skill=None)
            self._valid_output(workspace, with_skill=False)
            (workspace / "teacher" / "scenario_extension.json").write_text(json.dumps({"facts": [{"fact_id": "extension_fact_1", "statement": "A system export was produced after close."}]}), encoding="utf-8")
            payload = json.loads((workspace / "teacher" / "evidence_map.json").read_text(encoding="utf-8"))
            payload["artifacts"][0]["fact_ids"].append("extension_fact_1")
            (workspace / "teacher" / "evidence_map.json").write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(experiment.admit(session=session, workspace=workspace, bible=bible).decision, "pass")
            payload["artifacts"][0]["fact_ids"][-1] = "extension_unregistered"
            (workspace / "teacher" / "evidence_map.json").write_text(json.dumps(payload), encoding="utf-8")
            report = experiment.admit(session=session, workspace=workspace, bible=bible)
            closed = next(item for item in report.findings if item.code == "evidence_map_closed")
            self.assertIn("evidence_map_fact_reference_invalid", closed.details["errors"])

    def test_admission_blocks_invalid_or_duplicate_extension_registry(self):
        experiment, bible, rules = ScenarioEvidenceExperiment(), _bible(), _rules()
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            session = self._session("without_skill")
            experiment.stage_session(workspace=workspace, session=session, bible=bible, rules=rules, skill=None)
            self._valid_output(workspace, with_skill=False)
            (workspace / "teacher" / "scenario_extension.json").write_text(json.dumps({"facts": [{"fact_id": "bad-id", "statement": "Invalid ID."}]}), encoding="utf-8")
            report = experiment.admit(session=session, workspace=workspace, bible=bible)
            self.assertIn("teacher_outputs_present", [item.code for item in report.findings if not item.passed])
            (workspace / "teacher" / "scenario_extension.json").write_text(json.dumps({"facts": [{"fact_id": "extension_fact_1", "statement": "One."}, {"fact_id": "extension_fact_1", "statement": "Two."}]}), encoding="utf-8")
            report = experiment.admit(session=session, workspace=workspace, bible=bible)
            self.assertIn("teacher_outputs_present", [item.code for item in report.findings if not item.passed])

    def test_blind_payload_excludes_teacher_and_skill_identity(self):
        experiment, bible, rules = ScenarioEvidenceExperiment(), _bible(), _rules()
        with tempfile.TemporaryDirectory() as root:
            workspaces = {}
            for condition in ("without_skill", "with_skill"):
                workspace = Path(root) / condition
                experiment.stage_session(workspace=workspace, session=self._session(condition), bible=bible, rules=rules, skill=_skill() if condition == "with_skill" else None)
                self._valid_output(workspace, with_skill=condition == "with_skill")
                workspaces[condition] = workspace
            _, payload = experiment.blind_payload(seed=_seed(), rules=rules, workspaces=workspaces, scenario_id=bible.scenario_id)
            rendered = json.dumps(payload).casefold()
            self.assertNotIn("professional_skill", rendered)
            self.assertNotIn("correct_treatment", rendered)
            self.assertNotIn("source-a", rendered)

    def test_blind_reviewer_retries_only_invalid_json(self):
        calls = []
        def executor(_body, _key, _timeout):
            calls.append(1)
            content = "not json" if len(calls) == 1 else json.dumps({"findings": [{"favored_bundle": "bundle_2", "dimension": "judgment_depth", "file_paths": ["report.xlsx"], "reason": "The evidence requires corroboration across the table and controller note."}], "summary": "bundle 2 is stronger"})
            return 200, {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {"total_tokens": 4}}
        with tempfile.TemporaryDirectory() as root:
            review = OfficialDeepSeekConditionBlindReviewer(executor).review(scenario_id="scenario-audit", bundle_order=("without_skill", "with_skill"), payload={"bundles": []}, api_key="secret", output_root=Path(root) / "review")
        self.assertEqual(review.decision, "pass")
        self.assertEqual(review.provider_retry_count, 1)

    def test_blind_reviewer_reports_actual_nonretryable_call_count(self):
        with tempfile.TemporaryDirectory() as root:
            review = OfficialDeepSeekConditionBlindReviewer(lambda *_: (400, {})).review(
                scenario_id="scenario-audit", bundle_order=("without_skill", "with_skill"),
                payload={"bundles": []}, api_key="secret", output_root=Path(root) / "review",
            )
        self.assertEqual(review.decision, "incomplete")
        self.assertEqual(review.provider_call_count, 1)
        self.assertEqual(review.provider_retry_count, 0)

    def test_aggregate_requires_two_improvements_per_domain(self):
        b1, b2 = _bible(), _bible().model_copy(update={"scenario_id": "scenario-procurement"})
        sessions = []
        for bible in (b1, b2):
            for condition in ("without_skill", "with_skill"):
                sessions.append(self._session(condition).model_copy(update={"session_id": f"{bible.scenario_id}-{condition}", "scenario_id": bible.scenario_id}))
        plan = ScenarioEvidenceExperimentPlanV1(sessions=sessions)
        reports = [
            ScenarioEvidenceAdmissionReportV1(session_id=item.session_id, decision="pass", findings=[])
            for item in sessions
        ]
        reviews = []
        for bible in (b1, b2):
            reviews.append(ConditionBlindPairReviewV1(scenario_id=bible.scenario_id, bundle_order=("without_skill", "with_skill"), provider_call_count=1, decision="pass", findings=[
                ConditionBlindFindingV1(favored_bundle="bundle_2", dimension="professional_realism", file_paths=["report.xlsx"], reason="The table reflects a plausible operational report with supporting narrative."),
                ConditionBlindFindingV1(favored_bundle="bundle_2", dimension="judgment_depth", file_paths=["controller_note.txt"], reason="The note and report create a substantive evidence reliability decision."),
            ]))
        self.assertEqual(aggregate_experiment(plan=plan, admissions=reports, reviews=reviews).decision, "skill_effect_supported")

    def test_campaign_scope_requires_exact_complete_pair_and_private_authorization(self):
        sessions = []
        for scenario_id in ("scenario-audit", "scenario-procurement"):
            for condition in ("without_skill", "with_skill"):
                sessions.append(self._session(condition).model_copy(update={"session_id": f"{scenario_id}-{condition}", "scenario_id": scenario_id}))
        plan = ScenarioEvidenceExperimentPlanV1(sessions=sessions)
        scope = compile_campaign_scope(campaign_id="r10-restart", source_commit="a" * 40, plan=plan)
        self.assertEqual(scope.plan_sha256, plan.canonical_sha256())
        self.assertTrue(scope.private_upload_authorization_required)
        with self.assertRaises(ValueError):
            ScenarioEvidenceCampaignScopeV1(campaign_id="bad", source_commit="a" * 40, plan_sha256=plan.canonical_sha256(), sessions=sessions[:3])


if __name__ == "__main__":
    unittest.main()
