import json
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_teacher_input_builder import (
    TeacherInputManifest,
    TeacherInputValidationReport,
)
from task_generator.v3_source_schema import load_json_file


TeacherRunReadiness = Literal["not_ready", "partial_ready", "teacher_ready"]
GoldenStepStatus = Literal["complete", "partial", "blocked"]
CheckStatus = Literal["pass", "partial", "blocked"]


class TeacherRunRequest(BaseModel):
    teacher_input_manifest_path: str
    teacher_input_validation_report_path: str


class GoldenEvidenceUse(BaseModel):
    evidence_id: str
    file_name: str
    locator: str
    physical_location: str
    semantic_type: str
    usage_note: str


class GoldenIntermediateState(BaseModel):
    state_name: str
    purpose: str
    linked_skill_ids: List[str] = Field(default_factory=list)
    required_evidence_ids: List[str] = Field(default_factory=list)
    status: GoldenStepStatus
    blocking_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GoldenStep(BaseModel):
    step_id: str
    skill_id: str
    skill_name: str
    intention: str
    expected_action: str
    linked_intermediate_states: List[str] = Field(default_factory=list)
    evidence_uses: List[GoldenEvidenceUse] = Field(default_factory=list)
    status: GoldenStepStatus
    blocking_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GoldenFinalCheck(BaseModel):
    check_name: str
    status: CheckStatus
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GoldenRun(BaseModel):
    golden_run_version: str = "v3.golden_run.1"
    golden_run_id: str
    blueprint_id: str
    teacher_input_id: str
    template_family: str
    readiness: TeacherRunReadiness
    candidate_visible_reference_files: List[Dict[str, str]] = Field(default_factory=list)
    deferred_assets: List[str] = Field(default_factory=list)
    intermediate_states: List[GoldenIntermediateState] = Field(default_factory=list)
    steps: List[GoldenStep] = Field(default_factory=list)
    final_checks: List[GoldenFinalCheck] = Field(default_factory=list)
    unresolved_gaps: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TeacherRunnerDiagnostics(BaseModel):
    selected_skill_count: int = 0
    intermediate_state_count: int = 0
    complete_step_count: int = 0
    partial_step_count: int = 0
    blocked_step_count: int = 0
    final_check_count: int = 0
    complete_final_check_count: int = 0
    partial_final_check_count: int = 0
    blocked_final_check_count: int = 0
    generated_reference_file_count: int = 0
    deferred_asset_count: int = 0
    evidence_contract_count: int = 0
    blocking_reason_codes: List[str] = Field(default_factory=list)
    warning_reason_codes: List[str] = Field(default_factory=list)


class TeacherRunnerReport(BaseModel):
    teacher_runner_version: str = "v3.teacher_runner.1"
    request: TeacherRunRequest
    blueprint_id: str
    readiness: TeacherRunReadiness
    diagnostics: TeacherRunnerDiagnostics
    unresolved_gaps: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TeacherRunner:
    """Build a deterministic teacher-mode GoldenRun scaffold from teacher input artifacts."""

    def build(
        self,
        teacher_input_manifest_path: str | Path,
        teacher_input_validation_report_path: str | Path,
    ) -> tuple[GoldenRun, TeacherRunnerReport]:
        manifest = TeacherInputManifest.model_validate(load_json_file(str(teacher_input_manifest_path)))
        validation = TeacherInputValidationReport.model_validate(
            load_json_file(str(teacher_input_validation_report_path))
        )

        intermediate_states = self._build_intermediate_states(manifest)
        steps = self._build_steps(manifest, intermediate_states)
        final_checks = self._build_final_checks(manifest, validation)
        unresolved_gaps = self._unresolved_gaps(manifest, validation, intermediate_states, steps, final_checks)
        readiness = self._readiness(validation, steps, final_checks)
        diagnostics = self._diagnostics(manifest, validation, intermediate_states, steps, final_checks)

        golden_run = GoldenRun(
            golden_run_id=self._stable_id("golden", [manifest.blueprint_id, manifest.teacher_view.subgraph_id]),
            blueprint_id=manifest.blueprint_id,
            teacher_input_id=self._stable_id("teacher_input", [manifest.blueprint_id, manifest.teacher_view.subgraph_id]),
            template_family=manifest.template_family,
            readiness=readiness,
            candidate_visible_reference_files=[
                {
                    "file_name": file_view.file_name,
                    "status": file_view.status,
                    "relative_path": file_view.relative_path or "",
                }
                for file_view in manifest.candidate_view.reference_files
            ],
            deferred_assets=manifest.teacher_view.deferred_assets,
            intermediate_states=intermediate_states,
            steps=steps,
            final_checks=final_checks,
            unresolved_gaps=unresolved_gaps,
            notes=[
                "TeacherRunner V1 is deterministic and scaffold-oriented.",
                "Missing reference assets remain explicit gaps instead of being hallucinated into teacher truth.",
                "This GoldenRun is intended to feed later training-annotation and rubric slices.",
            ],
        )

        report = TeacherRunnerReport(
            request=TeacherRunRequest(
                teacher_input_manifest_path=str(teacher_input_manifest_path),
                teacher_input_validation_report_path=str(teacher_input_validation_report_path),
            ),
            blueprint_id=manifest.blueprint_id,
            readiness=readiness,
            diagnostics=diagnostics,
            unresolved_gaps=unresolved_gaps,
            notes=[
                "Readiness follows the teacher-input validation gate and the deterministic GoldenRun scaffold status.",
                "Policy or text-reference gaps should be resolved by future reference-file generation slices.",
            ],
        )
        return golden_run, report

    def write_outputs(
        self,
        golden_run: GoldenRun,
        report: TeacherRunnerReport,
        output_dir: str | Path,
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        golden_run_path = output_path / "golden_run.json"
        report_path = output_path / "teacher_runner_report.json"
        golden_run_path.write_text(golden_run.model_dump_json(indent=2), encoding="utf-8")
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {
            "golden_run_path": str(golden_run_path),
            "teacher_runner_report_path": str(report_path),
        }

    def _build_intermediate_states(self, manifest: TeacherInputManifest) -> List[GoldenIntermediateState]:
        states = []
        evidence_contract = manifest.teacher_view.evidence_contract
        evidence_ids = [item.evidence_id for item in evidence_contract]
        deferred_assets = manifest.teacher_view.deferred_assets
        for state_name in manifest.teacher_view.required_intermediate_states:
            blocking_reasons: List[str] = []
            notes: List[str] = []
            linked_skill_ids = self._skills_for_state(state_name, manifest)
            required_ids = self._evidence_for_state(state_name, evidence_contract)
            status: GoldenStepStatus = "complete"

            if "policy" in state_name and deferred_assets:
                status = "partial"
                blocking_reasons.append("deferred_policy_reference")
                notes.append("Policy mapping depends on a deferred reference document.")
            elif "gap_review" in state_name and manifest.teacher_view.missing_or_weak_pipeline_a_signals:
                status = "partial"
                blocking_reasons.append("pipeline_a_signal_gaps")
                notes.append("This state should surface missing Pipeline A graph signals.")
            elif "subgraph_edge_evidence_review" in state_name and manifest.teacher_view.subgraph_confidence != "high":
                status = "partial"
                blocking_reasons.append("low_subgraph_confidence")
                notes.append("Subgraph compatibility is provisional in the current sampled graph.")
            elif not evidence_ids:
                status = "blocked"
                blocking_reasons.append("missing_evidence_contract")
                notes.append("No evidence anchors were available for teacher-mode supervision.")

            states.append(
                GoldenIntermediateState(
                    state_name=state_name,
                    purpose=self._state_purpose(state_name),
                    linked_skill_ids=linked_skill_ids,
                    required_evidence_ids=required_ids,
                    status=status,
                    blocking_reasons=blocking_reasons,
                    notes=notes,
                )
            )
        return states

    def _build_steps(
        self,
        manifest: TeacherInputManifest,
        intermediate_states: List[GoldenIntermediateState],
    ) -> List[GoldenStep]:
        state_by_name = {state.state_name: state for state in intermediate_states}
        steps = []
        for index, intention in enumerate(manifest.teacher_view.skill_intentions, start=1):
            linked_states = self._states_for_skill(intention.skill_id, state_by_name)
            evidence_uses = self._evidence_for_skill(intention.skill_id, intention.canonical_name, manifest)
            blocking_reasons = list(intention.common_failure_signals)
            notes = list(intention.risk_notes)
            status: GoldenStepStatus = "complete"

            if any(state_by_name[name].status == "blocked" for name in linked_states):
                status = "blocked"
                blocking_reasons.append("blocked_intermediate_state")
            elif any(state_by_name[name].status == "partial" for name in linked_states):
                status = "partial"
                blocking_reasons.append("partial_intermediate_state")

            if any("policy" in name for name in linked_states) and manifest.teacher_view.deferred_assets:
                status = "partial" if status == "complete" else status
                blocking_reasons.append("deferred_policy_reference")
                notes.append("Policy application remains partial until the reference doc is generated.")

            if not evidence_uses:
                status = "blocked"
                blocking_reasons.append("missing_supporting_evidence")
                notes.append("No candidate-visible evidence anchors were matched to this skill.")

            steps.append(
                GoldenStep(
                    step_id=self._stable_id("step", [manifest.blueprint_id, intention.skill_id, str(index)]),
                    skill_id=intention.skill_id,
                    skill_name=intention.canonical_name,
                    intention=intention.training_intent,
                    expected_action=self._expected_action(intention.canonical_name, linked_states),
                    linked_intermediate_states=linked_states,
                    evidence_uses=evidence_uses,
                    status=status,
                    blocking_reasons=sorted(set(blocking_reasons)),
                    notes=notes,
                )
            )
        return steps

    def _build_final_checks(
        self,
        manifest: TeacherInputManifest,
        validation: TeacherInputValidationReport,
    ) -> List[GoldenFinalCheck]:
        generated_file_names = {
            file_view.file_name
            for file_view in manifest.candidate_view.reference_files
            if file_view.status == "generated"
        }
        evidence_ids = [item.evidence_id for item in manifest.teacher_view.evidence_contract]
        warning_checks = {
            check.check_name: check
            for check in validation.relationship_checks
        }
        final_checks = []
        for check_name in manifest.teacher_view.required_final_checks:
            status: CheckStatus = "pass"
            blocking_reasons: List[str] = []
            notes: List[str] = []
            supporting_evidence_ids = list(evidence_ids)

            if check_name == "deliverable_presence":
                if "source_evidence.xlsx" not in generated_file_names:
                    status = "blocked"
                    blocking_reasons.append("missing_generated_reference_file")
                else:
                    notes.append("Candidate-visible source evidence exists for deliverable drafting.")
            elif check_name == "deliverable_requirement_coverage":
                if not manifest.candidate_view.deliverables:
                    status = "blocked"
                    blocking_reasons.append("missing_deliverable_contract")
                else:
                    notes.append("Deliverable requirements are explicitly available for teacher-side coverage checks.")
            elif check_name == "evidence_traceability":
                if not evidence_ids:
                    status = "blocked"
                    blocking_reasons.append("missing_evidence_contract")
                else:
                    notes.append("Evidence IDs are available for citation checks.")
            elif check_name == "policy_clause_traceability":
                relationship_check = warning_checks.get("relationship:policy_lookup")
                has_policy_evidence = any(
                    item.file_name == "policy_reference.docx" for item in manifest.teacher_view.evidence_contract
                )
                if not has_policy_evidence:
                    status = "blocked"
                    blocking_reasons.append("missing_policy_clause_evidence")
                elif relationship_check and not relationship_check.passed:
                    status = "partial"
                    blocking_reasons.append("relationship:policy_lookup")
                    notes.append("Policy clause traceability is only partially established.")
                else:
                    notes.append("Policy clauses are candidate-visible and available for explicit citation.")
            elif check_name == "conclusion_supported_by_visible_evidence":
                relationship_check = warning_checks.get("relationship:policy_lookup")
                if relationship_check and not relationship_check.passed:
                    status = "partial"
                    blocking_reasons.append("deferred_policy_reference")
                    notes.append("Visible evidence supports only part of the intended final conclusion.")

            final_checks.append(
                GoldenFinalCheck(
                    check_name=check_name,
                    status=status,
                    supporting_evidence_ids=supporting_evidence_ids,
                    blocking_reasons=blocking_reasons,
                    notes=notes,
                )
            )
        return final_checks

    def _unresolved_gaps(
        self,
        manifest: TeacherInputManifest,
        validation: TeacherInputValidationReport,
        intermediate_states: List[GoldenIntermediateState],
        steps: List[GoldenStep],
        final_checks: List[GoldenFinalCheck],
    ) -> List[str]:
        gaps = []
        for asset in manifest.teacher_view.deferred_assets:
            gaps.append(f"Deferred asset still missing for teacher mode: {asset}")
        for signal in manifest.teacher_view.missing_or_weak_pipeline_a_signals:
            gaps.append(f"Weak Pipeline A signal: {signal}")
        for check in validation.relationship_checks:
            if not check.passed:
                gaps.append(f"{check.check_name}: {check.details}")
        for state in intermediate_states:
            for reason in state.blocking_reasons:
                gaps.append(f"{state.state_name}: {reason}")
        for step in steps:
            if step.status != "complete":
                gaps.append(f"{step.skill_name}: {', '.join(step.blocking_reasons)}")
        for final_check in final_checks:
            if final_check.status != "pass":
                gaps.append(f"{final_check.check_name}: {', '.join(final_check.blocking_reasons)}")
        return sorted(set(gaps))

    def _readiness(
        self,
        validation: TeacherInputValidationReport,
        steps: List[GoldenStep],
        final_checks: List[GoldenFinalCheck],
    ) -> TeacherRunReadiness:
        blocking_validation = any(
            finding.severity == "blocking" and not finding.passed for finding in validation.findings
        )
        if blocking_validation or any(step.status == "blocked" for step in steps):
            return "not_ready"
        if any(step.status == "partial" for step in steps) or any(
            check.status == "partial" for check in final_checks
        ):
            return "partial_ready"
        return "teacher_ready"

    def _diagnostics(
        self,
        manifest: TeacherInputManifest,
        validation: TeacherInputValidationReport,
        intermediate_states: List[GoldenIntermediateState],
        steps: List[GoldenStep],
        final_checks: List[GoldenFinalCheck],
    ) -> TeacherRunnerDiagnostics:
        blocking_reason_codes = []
        warning_reason_codes = []
        for step in steps:
            target = blocking_reason_codes if step.status == "blocked" else warning_reason_codes
            target.extend(step.blocking_reasons)
        for state in intermediate_states:
            if state.status == "blocked":
                blocking_reason_codes.extend(state.blocking_reasons)
            elif state.status == "partial":
                warning_reason_codes.extend(state.blocking_reasons)
        for check in final_checks:
            if check.status == "blocked":
                blocking_reason_codes.extend(check.blocking_reasons)
            elif check.status == "partial":
                warning_reason_codes.extend(check.blocking_reasons)

        return TeacherRunnerDiagnostics(
            selected_skill_count=len(manifest.teacher_view.skill_intentions),
            intermediate_state_count=len(intermediate_states),
            complete_step_count=sum(1 for step in steps if step.status == "complete"),
            partial_step_count=sum(1 for step in steps if step.status == "partial"),
            blocked_step_count=sum(1 for step in steps if step.status == "blocked"),
            final_check_count=len(final_checks),
            complete_final_check_count=sum(1 for check in final_checks if check.status == "pass"),
            partial_final_check_count=sum(1 for check in final_checks if check.status == "partial"),
            blocked_final_check_count=sum(1 for check in final_checks if check.status == "blocked"),
            generated_reference_file_count=sum(
                1 for file_view in manifest.candidate_view.reference_files if file_view.status == "generated"
            ),
            deferred_asset_count=len(manifest.teacher_view.deferred_assets),
            evidence_contract_count=len(manifest.teacher_view.evidence_contract),
            blocking_reason_codes=sorted(set(blocking_reason_codes)),
            warning_reason_codes=sorted(
                set(warning_reason_codes + manifest.diagnostics.warning_reason_codes)
            ),
        )

    def _states_for_skill(
        self,
        skill_id: str,
        state_by_name: Dict[str, GoldenIntermediateState],
    ) -> List[str]:
        linked = [
            state_name
            for state_name, state in state_by_name.items()
            if skill_id in state.linked_skill_ids
        ]
        if not linked:
            linked = list(state_by_name)[:1]
        return linked

    def _skills_for_state(self, state_name: str, manifest: TeacherInputManifest) -> List[str]:
        selected = []
        for intention in manifest.teacher_view.skill_intentions:
            canonical = intention.canonical_name.lower()
            if "exception" in state_name and "exception" in canonical:
                selected.append(intention.skill_id)
            elif "deliverable_outline" in state_name:
                selected.append(intention.skill_id)
            elif "policy" in state_name and (
                "policy" in canonical or "tax" in canonical or "withholding" in canonical
            ):
                selected.append(intention.skill_id)
            elif "inventory" in state_name and (
                "consolidate" in canonical or "reconcile" in canonical
            ):
                selected.append(intention.skill_id)
            elif "conclusion_map" in state_name:
                selected.append(intention.skill_id)
            elif "gap_review" in state_name or "subgraph_edge_evidence_review" in state_name:
                selected.append(intention.skill_id)
        return selected or [item.skill_id for item in manifest.teacher_view.skill_intentions]

    def _evidence_for_state(
        self,
        state_name: str,
        evidence_contract,
    ) -> List[str]:
        matches = []
        for item in evidence_contract:
            semantic = item.semantic_type.lower()
            if "inventory" in state_name and semantic in {"identifier", "source_label", "business_entity"}:
                matches.append(item.evidence_id)
            elif "deliverable_outline" in state_name and semantic in {
                "identifier",
                "source_label",
                "mixed_fact",
                "policy_rule",
                "decision_rule",
            }:
                matches.append(item.evidence_id)
            elif "conclusion_map" in state_name and semantic in {"mixed_fact", "source_label"}:
                matches.append(item.evidence_id)
            elif "policy_clause_evidence_map" in state_name and semantic in {
                "policy_rule",
                "decision_rule",
                "contextual_reference",
                "business_entity",
                "mixed_fact",
            }:
                matches.append(item.evidence_id)
            elif "policy" in state_name and semantic in {
                "business_entity",
                "mixed_fact",
                "policy_rule",
                "decision_rule",
            }:
                matches.append(item.evidence_id)
            elif "exception" in state_name and semantic in {"mixed_fact", "identifier"}:
                matches.append(item.evidence_id)
            elif "gap_review" in state_name or "subgraph_edge_evidence_review" in state_name:
                matches.append(item.evidence_id)
        if not matches:
            matches = [item.evidence_id for item in evidence_contract]
        return matches

    def _evidence_for_skill(
        self,
        skill_id: str,
        canonical_name: str,
        manifest: TeacherInputManifest,
    ) -> List[GoldenEvidenceUse]:
        del skill_id
        evidence_contract = manifest.teacher_view.evidence_contract
        matched = []
        lowered = canonical_name.lower()
        for item in evidence_contract:
            semantic = item.semantic_type.lower()
            if "exception" in lowered and semantic in {"identifier", "mixed_fact"}:
                matched.append(item)
            elif "reconcile" in lowered and semantic in {"identifier", "mixed_fact", "source_label"}:
                matched.append(item)
            elif ("tax" in lowered or "policy" in lowered or "withholding" in lowered) and semantic in {
                "business_entity",
                "mixed_fact",
                "policy_rule",
                "decision_rule",
                "contextual_reference",
            }:
                matched.append(item)
            elif "consolidate" in lowered and semantic in {
                "source_label",
                "business_entity",
                "mixed_fact",
                "time_period",
            }:
                matched.append(item)
        if not matched:
            matched = evidence_contract[: min(3, len(evidence_contract))]
        return [
            GoldenEvidenceUse(
                evidence_id=item.evidence_id,
                file_name=item.file_name,
                locator=item.locator,
                physical_location=item.physical_location,
                semantic_type=item.semantic_type,
                usage_note=self._usage_note(canonical_name, item.semantic_type),
            )
            for item in matched
        ]

    def _state_purpose(self, state_name: str) -> str:
        purposes = {
            "evidence_inventory": "Include an Evidence inventory section listing each material evidence ID, source file, observed item, and intended use before drawing conclusions.",
            "deliverable_outline": "Include a Deliverable outline section with headings for evidence reviewed, supported conclusions, confirmed exceptions, unresolved items, policy mapping, and follow-up.",
            "evidence_to_conclusion_map": "Include an Evidence-to-conclusion map linking each material conclusion to specific visible evidence IDs.",
            "policy_requirement_mapping": "Map evidence items to applicable requirement logic.",
            "policy_clause_evidence_map": "Include a Policy clause mapping that links each clause ID to governed evidence IDs, applied conclusion, and unresolved policy uncertainty.",
            "exception_classification_log": "Separate confirmed exceptions from unresolved evidence gaps.",
            "pipeline_a_signal_gap_review": "Record where Pipeline A graph signals are weak or missing.",
        }
        if state_name in purposes:
            return purposes[state_name]
        if state_name.startswith("subgraph_edge_evidence_review"):
            return "Review whether sampled skill connections have enough explicit evidence."
        return "Capture a teacher-visible intermediate supervision state."

    def _expected_action(self, canonical_name: str, linked_states: List[str]) -> str:
        if any("policy_clause_evidence_map" in name for name in linked_states):
            return f"Apply {canonical_name} and write the policy-clause mapping with clause IDs, governed evidence IDs, applied conclusion, and unresolved policy uncertainty."
        if any("policy" in name for name in linked_states):
            return f"Apply {canonical_name} with explicit policy-to-evidence mapping."
        if any("exception" in name for name in linked_states):
            return f"Use {canonical_name} to classify exceptions and unresolved items."
        if any("deliverable_outline" in name for name in linked_states):
            return f"Use {canonical_name} to produce the deliverable outline and manager-ready section structure with explicit cited support."
        if any("inventory" in name or "conclusion_map" in name for name in linked_states):
            return f"Use {canonical_name} to inventory source evidence and map it to manager-ready conclusions."
        return f"Apply {canonical_name} as a teacher-supervised reasoning step."

    def _usage_note(self, canonical_name: str, semantic_type: str) -> str:
        return f"Use {semantic_type} evidence to support {canonical_name}."

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        raw = "|".join(parts)
        import hashlib

        return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"
