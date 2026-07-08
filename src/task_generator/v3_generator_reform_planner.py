from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class GeneratorReformPlannerRequest(BaseModel):
    generated_task_gap_autopsy_path: str
    pattern_library_path: str
    pattern_mapping_path: str
    target_motif: str = "evidence_to_deliverable"
    output_dir: str


class GeneratorReformChange(BaseModel):
    change_id: str
    change_type: str
    deterministic_or_llm_candidate: str
    description: str
    target_modules: List[str] = Field(default_factory=list)
    source_patterns: List[str] = Field(default_factory=list)
    verifier_guardrails: List[str] = Field(default_factory=list)
    expected_effect: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)


class GeneratorReformSpec(BaseModel):
    spec_version: str = "v3.phase15_generator_reform_spec.1"
    created_at: str
    target_motif: str
    reform_status: str
    baseline_problem: Dict[str, Any] = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list)
    deterministic_changes: List[GeneratorReformChange] = Field(default_factory=list)
    optional_llm_candidate_changes: List[GeneratorReformChange] = Field(default_factory=list)
    validation_plan: Dict[str, Any] = Field(default_factory=dict)
    promotion_policy: Dict[str, Any] = Field(default_factory=dict)


class GeneratorReformDesignReport(BaseModel):
    report_version: str = "v3.phase15_generator_reform_design.1"
    created_at: str
    request: GeneratorReformPlannerRequest
    diagnostic_only: bool = True
    target_motif: str
    selected_patterns: List[str] = Field(default_factory=list)
    spec_path: str
    reform_summary: Dict[str, Any] = Field(default_factory=dict)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GeneratorReformPlanner:
    def build(self, request: GeneratorReformPlannerRequest) -> GeneratorReformDesignReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        autopsy = self._read_json(Path(request.generated_task_gap_autopsy_path))
        pattern_library = self._read_json(Path(request.pattern_library_path))
        mapping = self._read_json(Path(request.pattern_mapping_path))

        target_case = self._target_case(autopsy, request.target_motif)
        selected_patterns = list((mapping.get("recommended_first_reform") or {}).get("patterns_to_apply") or [])
        spec = self._spec(request.target_motif, target_case, pattern_library, selected_patterns)
        spec_path = output_dir / f"{request.target_motif}_reform_spec.json"
        self._write_json(spec_path, spec.model_dump(mode="json"))
        report = GeneratorReformDesignReport(
            created_at=self._now(),
            request=request,
            target_motif=request.target_motif,
            selected_patterns=selected_patterns,
            spec_path=str(spec_path),
            reform_summary={
                "baseline_gap": target_case.get("gap"),
                "baseline_gap_band": target_case.get("gap_band"),
                "deterministic_change_count": len(spec.deterministic_changes),
                "optional_llm_candidate_change_count": len(spec.optional_llm_candidate_changes),
                "new_file_types_required": False,
                "default_chain_mutation": False,
            },
            next_actions=[
                "Use this reform spec to generate a reform-only experiment arm.",
                "Keep LLM candidate additions disabled until the adoption gate is manually reviewed.",
                "Validate reform with candidate_ready, verifier pass, production QA, and clean paired eval.",
            ],
            notes=[
                "This report designs a reform proposal only; it does not mutate the default generator.",
                "The first reform intentionally avoids new file types to isolate productive complexity from file-ecosystem friction.",
            ],
        )
        self._write_json(output_dir / "generator_reform_design_report.json", report.model_dump(mode="json"))
        return report

    def _target_case(self, autopsy: Dict[str, Any], target_motif: str) -> Dict[str, Any]:
        for case in autopsy.get("cases") or []:
            if case.get("motif") == target_motif:
                return case
        return {
            "motif": target_motif,
            "gap": None,
            "gap_band": "unknown",
            "generator_reform_recommendation": [],
        }

    def _spec(
        self,
        target_motif: str,
        target_case: Dict[str, Any],
        pattern_library: Dict[str, Any],
        selected_patterns: List[str],
    ) -> GeneratorReformSpec:
        pattern_map = {pattern.get("pattern_id"): pattern for pattern in pattern_library.get("patterns") or []}
        deterministic_changes = [
            GeneratorReformChange(
                change_id="reform_context_role_trigger_v1",
                change_type="scenario_density",
                deterministic_or_llm_candidate="deterministic",
                description="Add actor role, business trigger, stakeholder/reviewer, deadline or review context, and decision consequence to the blueprint.",
                target_modules=["v3_pipeline_b_prototype.py", "v3_rw_task_exporter.py"],
                source_patterns=["gdpval_pattern_role_trigger_stakeholder_v1"],
                verifier_guardrails=["no hidden facts", "all trigger facts visible in prompt or reference files"],
                expected_effect=["higher workflow realism", "clearer reviewer-facing objective"],
                risks=["prose can become decorative if not tied to deliverable requirements"],
            ),
            GeneratorReformChange(
                change_id="reform_second_reference_or_manager_note_v1",
                change_type="reference_file_ecology",
                deterministic_or_llm_candidate="deterministic",
                description="Add a second evidence source or manager note using existing xlsx/docx-like generator paths, with stable evidence IDs.",
                target_modules=["v3_reference_file_planner.py", "v3_reference_file_generator.py"],
                source_patterns=["gdpval_pattern_multi_reference_evidence_ecology_v1"],
                verifier_guardrails=["stable Evidence_ID values", "candidate-visible source mapping", "no unsupported facts"],
                expected_effect=["more cross-evidence reasoning", "less template-like evidence ecology"],
                risks=["extra evidence can become frictional if not manifestable"],
            ),
            GeneratorReformChange(
                change_id="reform_reviewer_facing_deliverable_v1",
                change_type="deliverable_contract",
                deterministic_or_llm_candidate="deterministic",
                description="Replace generic structured report framing with manager-facing memo, audit finding summary, or review worksheet plus conclusion.",
                target_modules=["v3_pipeline_b_prototype.py", "v3_rubric_builder.py", "v3_rw_task_exporter.py"],
                source_patterns=[
                    "gdpval_pattern_reviewer_facing_deliverable_contract_v1",
                    "gdpval_pattern_review_workpaper_or_memo_v1",
                ],
                verifier_guardrails=["candidate-visible requirements only", "rubric maps to deliverable sections"],
                expected_effect=["higher training signal", "more realistic work product"],
                risks=["free-form writing noise if sections are not fixed"],
            ),
            GeneratorReformChange(
                change_id="reform_confirmed_unresolved_split_v1",
                change_type="productive_complexity",
                deterministic_or_llm_candidate="deterministic",
                description="Require candidates to separate confirmed findings, unresolved items, and evidence insufficiency judgments.",
                target_modules=["v3_teacher_runner.py", "v3_training_annotation_builder.py", "v3_rubric_builder.py"],
                source_patterns=[
                    "gdpval_pattern_uncertainty_exception_handling_v1",
                    "gdpval_pattern_professional_judgment_v1",
                ],
                verifier_guardrails=["unresolved item is generated from visible evidence", "rubric rewards reasoning not hidden answer matching"],
                expected_effect=["medium-gap target for evidence_to_deliverable", "better productive complexity"],
                risks=["ambiguous expected output if unresolved issue is not explicit"],
            ),
            GeneratorReformChange(
                change_id="reform_materiality_or_severity_judgment_v1",
                change_type="professional_judgment",
                deterministic_or_llm_candidate="deterministic",
                description="Add a bounded materiality, severity, or priority classification grounded in visible evidence.",
                target_modules=["v3_pipeline_b_prototype.py", "v3_rubric_builder.py"],
                source_patterns=["gdpval_pattern_professional_judgment_v1"],
                verifier_guardrails=["classification choices defined in prompt", "evidence supports every classification"],
                expected_effect=["stronger training value without new file types"],
                risks=["subjective grading if categories are not bounded"],
            ),
        ]
        optional_llm_changes = [
            GeneratorReformChange(
                change_id="llm_realism_critic_diagnostic_v1",
                change_type="llm_diagnostic_candidate",
                deterministic_or_llm_candidate="optional_llm_candidate",
                description="Use an LLM realism critic to flag thin scenario density after deterministic package generation; do not modify artifacts automatically.",
                target_modules=["future_v3_llm_candidate_layer.py", "v3_production_dashboard.py"],
                source_patterns=selected_patterns,
                verifier_guardrails=["diagnostic-only", "no artifact mutation", "reviewer policy must explicitly consume signal"],
                expected_effect=["better review prioritization"],
                risks=["critic may over-penalize evidence-closed but concise tasks"],
            ),
            GeneratorReformChange(
                change_id="llm_reference_narrative_suggestion_v1",
                change_type="llm_reference_candidate",
                deterministic_or_llm_candidate="optional_llm_candidate",
                description="Allow LLM to suggest richer manager notes only after deterministic validation rejects unsupported claims and evidence mutations.",
                target_modules=["future_v3_llm_candidate_layer.py", "v3_reference_file_generator.py"],
                source_patterns=["gdpval_pattern_role_trigger_stakeholder_v1", "gdpval_pattern_review_workpaper_or_memo_v1"],
                verifier_guardrails=["no Evidence_ID mutation", "no amount/policy/truth mutation", "unsupported claim detector required"],
                expected_effect=["higher realism if validated"],
                risks=["unsupported business context", "candidate-visible leakage"],
            ),
        ]
        return GeneratorReformSpec(
            created_at=self._now(),
            target_motif=target_motif,
            reform_status="proposal_ready_for_controlled_experiment",
            baseline_problem={
                "task_id": target_case.get("task_id"),
                "gap": target_case.get("gap"),
                "gap_band": target_case.get("gap_band"),
                "top_gap_sources": target_case.get("top_gap_sources"),
                "interpretation": target_case.get("interpretation"),
                "autopsy_recommendations": target_case.get("generator_reform_recommendation"),
            },
            constraints=[
                "do_not_introduce_new_file_types_in_first_reform",
                "do_not_lower_verifier_or_production_qa_requirements",
                "do_not_enable_weighted_good_task_score",
                "do_not_use_llm_primary_truth",
                "keep_generator_default_chain_unchanged_until_promotion_review",
            ],
            deterministic_changes=deterministic_changes,
            optional_llm_candidate_changes=optional_llm_changes,
            validation_plan={
                "experiment_arms": [
                    "baseline_deterministic",
                    "generator_reform_only",
                    "generator_reform_plus_guarded_llm_candidate",
                ],
                "minimum_tasks_per_arm": 4,
                "first_eval_target": "4-8 generated tasks with clean paired eval",
                "success_signals": [
                    "gap rises from low to medium or workflow realism improves without QA regression",
                    "candidate_ready remains true",
                    "task_verifier pass remains true",
                    "production QA does not regress",
                    "format/tool noise does not increase materially",
                ],
            },
            promotion_policy={
                "promotion_required": True,
                "allowed_decisions": ["approve", "reject", "more_evidence"],
                "rollback_required": True,
                "silent_default_chain_mutation_allowed": False,
            },
        )

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
