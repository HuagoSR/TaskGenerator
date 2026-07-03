from pathlib import Path
from typing import Dict, List, Literal

from pydantic import BaseModel, Field

from task_generator.v2_schema import (
    CapabilityProfile,
    FailureMode,
    RubricProjection,
    SupervisionTarget,
    SupervisionTargets,
    TrainingAnnotation,
)
from task_generator.v3_teacher_input_builder import TeacherInputManifest
from task_generator.v3_teacher_runner import GoldenRun, TeacherRunnerReport
from task_generator.v3_source_schema import load_json_file


AnnotationReadiness = Literal["not_ready", "partial_ready", "annotation_ready"]
SupervisionKind = Literal["intermediate_state", "golden_step", "final_check"]


class TrainingAnnotationRequest(BaseModel):
    golden_run_path: str
    teacher_runner_report_path: str
    teacher_input_manifest_path: str


class EvidenceRequirement(BaseModel):
    evidence_id: str
    file_name: str
    locator: str
    semantic_type: str
    rationale: str


class StepSupervisionItem(BaseModel):
    item_id: str
    kind: SupervisionKind
    name: str
    linked_skill_ids: List[str] = Field(default_factory=list)
    expected_behavior: str
    evidence_requirements: List[EvidenceRequirement] = Field(default_factory=list)
    status: str
    warning_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class FailurePattern(BaseModel):
    failure_id: str
    severity: str
    signal: str
    description: str
    linked_skill_ids: List[str] = Field(default_factory=list)
    remediation_hint: str = ""


class TrainingAnnotationArtifact(BaseModel):
    training_annotation_version: str = "v3.training_annotation.1"
    annotation_id: str
    blueprint_id: str
    golden_run_id: str
    readiness: AnnotationReadiness
    capability_profile: CapabilityProfile
    supervision_targets: SupervisionTargets
    supervision_items: List[StepSupervisionItem] = Field(default_factory=list)
    failure_modes: List[FailurePattern] = Field(default_factory=list)
    hidden_traps: List[str] = Field(default_factory=list)
    expected_reasoning_path: List[str] = Field(default_factory=list)
    unresolved_gaps: List[str] = Field(default_factory=list)
    rubric_projection: RubricProjection
    legacy_v2_projection: TrainingAnnotation
    notes: List[str] = Field(default_factory=list)


class TrainingAnnotationDiagnostics(BaseModel):
    readiness: AnnotationReadiness
    supervision_item_count: int = 0
    intermediate_item_count: int = 0
    golden_step_item_count: int = 0
    final_check_item_count: int = 0
    failure_mode_count: int = 0
    hidden_trap_count: int = 0
    unresolved_gap_count: int = 0
    partial_item_count: int = 0
    blocked_item_count: int = 0
    warning_reason_codes: List[str] = Field(default_factory=list)


class TrainingAnnotationReport(BaseModel):
    training_annotation_report_version: str = "v3.training_annotation_report.1"
    request: TrainingAnnotationRequest
    blueprint_id: str
    readiness: AnnotationReadiness
    diagnostics: TrainingAnnotationDiagnostics
    notes: List[str] = Field(default_factory=list)


class TrainingAnnotationBuilder:
    """Build teacher-derived training annotations from current Pipeline B artifacts."""

    def build(
        self,
        golden_run_path: str | Path,
        teacher_runner_report_path: str | Path,
        teacher_input_manifest_path: str | Path,
    ) -> tuple[TrainingAnnotationArtifact, TrainingAnnotationReport]:
        golden_run = GoldenRun.model_validate(load_json_file(str(golden_run_path)))
        teacher_report = TeacherRunnerReport.model_validate(load_json_file(str(teacher_runner_report_path)))
        teacher_manifest = TeacherInputManifest.model_validate(load_json_file(str(teacher_input_manifest_path)))

        evidence_by_id = {
            item.evidence_id: item for item in teacher_manifest.teacher_view.evidence_contract
        }
        capability_profile = self._capability_profile(teacher_manifest)
        supervision_targets = self._supervision_targets(golden_run)
        supervision_items = self._supervision_items(golden_run, teacher_manifest, evidence_by_id)
        failure_modes = self._failure_modes(golden_run, teacher_report, teacher_manifest)
        hidden_traps = self._hidden_traps(teacher_manifest, teacher_report)
        expected_reasoning_path = self._expected_reasoning_path(golden_run)
        rubric_projection = self._rubric_projection(golden_run, teacher_report)
        readiness = self._readiness(teacher_report, supervision_items)
        legacy_projection = TrainingAnnotation(
            annotation_id=self._stable_id("ann", [golden_run.blueprint_id, golden_run.golden_run_id]),
            blueprint_id=golden_run.blueprint_id,
            capability_profile=capability_profile,
            supervision_targets=supervision_targets,
            failure_modes=[
                FailureMode(failure_id=item.failure_id, description=item.description)
                for item in failure_modes
            ],
            rubric_projection=rubric_projection,
        )

        artifact = TrainingAnnotationArtifact(
            annotation_id=self._stable_id("ann", [golden_run.blueprint_id, golden_run.golden_run_id]),
            blueprint_id=golden_run.blueprint_id,
            golden_run_id=golden_run.golden_run_id,
            readiness=readiness,
            capability_profile=capability_profile,
            supervision_targets=supervision_targets,
            supervision_items=supervision_items,
            failure_modes=failure_modes,
            hidden_traps=hidden_traps,
            expected_reasoning_path=expected_reasoning_path,
            unresolved_gaps=golden_run.unresolved_gaps,
            rubric_projection=rubric_projection,
            legacy_v2_projection=legacy_projection,
            notes=[
                "TrainingAnnotationBuilder V1 is derived entirely from deterministic teacher artifacts.",
                "Partial teacher readiness is preserved as supervision metadata rather than hidden.",
                "This artifact is intended to feed the first RubricBuilder slice.",
            ],
        )

        diagnostics = self._diagnostics(artifact, teacher_report)
        report = TrainingAnnotationReport(
            request=TrainingAnnotationRequest(
                golden_run_path=str(golden_run_path),
                teacher_runner_report_path=str(teacher_runner_report_path),
                teacher_input_manifest_path=str(teacher_input_manifest_path),
            ),
            blueprint_id=golden_run.blueprint_id,
            readiness=readiness,
            diagnostics=diagnostics,
            notes=[
                "The report preserves unresolved gaps and warning codes for downstream rubric building.",
                "A richer V3 annotation artifact is emitted together with a V2-compatible projection.",
            ],
        )
        return artifact, report

    def write_outputs(
        self,
        artifact: TrainingAnnotationArtifact,
        report: TrainingAnnotationReport,
        output_dir: str | Path,
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        annotation_path = output_path / "training_annotation.json"
        report_path = output_path / "training_annotation_report.json"
        annotation_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {
            "training_annotation_path": str(annotation_path),
            "training_annotation_report_path": str(report_path),
        }

    def _capability_profile(self, teacher_manifest: TeacherInputManifest) -> CapabilityProfile:
        primary = sorted(
            {
                tag
                for intention in teacher_manifest.teacher_view.skill_intentions
                for tag in intention.capability_tags
            }
        )
        secondary = sorted(
            {
                f"motif:{teacher_manifest.teacher_view.selected_motif}",
                *(
                    f"role:{role}"
                    for intention in teacher_manifest.teacher_view.skill_intentions
                    for role in intention.graph_role_hints
                ),
                *(
                    f"risk:{signal}"
                    for intention in teacher_manifest.teacher_view.skill_intentions
                    for signal in intention.common_failure_signals
                ),
                *(
                    f"gap:{signal}"
                    for signal in teacher_manifest.teacher_view.missing_or_weak_pipeline_a_signals
                ),
            }
        )
        return CapabilityProfile(primary_capabilities=primary, secondary_capabilities=secondary)

    def _supervision_targets(self, golden_run: GoldenRun) -> SupervisionTargets:
        final_outcomes = [
            SupervisionTarget(
                target_id=check.check_name,
                target_type=self._final_check_target_type(check.check_name),
                description=self._final_check_description(check.check_name, check.status),
            )
            for check in golden_run.final_checks
        ]
        intermediate_outcomes = [
            SupervisionTarget(
                target_id=item.state_name,
                target_type="reasoning_check",
                description=f"Verify the teacher-visible state `{item.state_name}` is covered with the required evidence discipline.",
            )
            for item in golden_run.intermediate_states
        ] + [
            SupervisionTarget(
                target_id=step.step_id,
                target_type="reasoning_or_robustness_check" if step.status != "complete" else "reasoning_check",
                description=f"Verify the expected reasoning behavior for `{step.skill_name}`.",
            )
            for step in golden_run.steps
        ]
        return SupervisionTargets(final_outcomes=final_outcomes, intermediate_outcomes=intermediate_outcomes)

    def _supervision_items(
        self,
        golden_run: GoldenRun,
        teacher_manifest: TeacherInputManifest,
        evidence_by_id: Dict[str, object],
    ) -> List[StepSupervisionItem]:
        items: List[StepSupervisionItem] = []
        for state in golden_run.intermediate_states:
            items.append(
                StepSupervisionItem(
                    item_id=self._stable_id("sup", [golden_run.golden_run_id, state.state_name]),
                    kind="intermediate_state",
                    name=state.state_name,
                    linked_skill_ids=state.linked_skill_ids,
                    expected_behavior=state.purpose,
                    evidence_requirements=self._requirements_for_ids(
                        state.required_evidence_ids,
                        evidence_by_id,
                        rationale_prefix="Teacher should ground this state in",
                    ),
                    status=state.status,
                    warning_codes=state.blocking_reasons,
                    notes=state.notes,
                )
            )
        for step in golden_run.steps:
            items.append(
                StepSupervisionItem(
                    item_id=step.step_id,
                    kind="golden_step",
                    name=step.skill_name,
                    linked_skill_ids=[step.skill_id],
                    expected_behavior=step.expected_action,
                    evidence_requirements=[
                        EvidenceRequirement(
                            evidence_id=item.evidence_id,
                            file_name=item.file_name,
                            locator=item.locator,
                            semantic_type=item.semantic_type,
                            rationale=item.usage_note,
                        )
                        for item in step.evidence_uses
                    ],
                    status=step.status,
                    warning_codes=step.blocking_reasons,
                    notes=step.notes,
                )
            )
        for check in golden_run.final_checks:
            items.append(
                StepSupervisionItem(
                    item_id=self._stable_id("sup", [golden_run.golden_run_id, check.check_name]),
                    kind="final_check",
                    name=check.check_name,
                    linked_skill_ids=[item.skill_id for item in teacher_manifest.teacher_view.skill_intentions],
                    expected_behavior=self._final_check_description(check.check_name, check.status),
                    evidence_requirements=self._requirements_for_ids(
                        check.supporting_evidence_ids,
                        evidence_by_id,
                        rationale_prefix="Final check should be auditable from",
                    ),
                    status=check.status,
                    warning_codes=check.blocking_reasons,
                    notes=check.notes,
                )
            )
        return items

    def _failure_modes(
        self,
        golden_run: GoldenRun,
        teacher_report: TeacherRunnerReport,
        teacher_manifest: TeacherInputManifest,
    ) -> List[FailurePattern]:
        patterns: List[FailurePattern] = []
        for code in teacher_report.diagnostics.warning_reason_codes:
            patterns.append(
                FailurePattern(
                    failure_id=self._stable_id("fm", [golden_run.golden_run_id, code]),
                    severity=self._failure_severity(code),
                    signal=code,
                    description=self._failure_description(code),
                    linked_skill_ids=self._linked_skills_for_signal(code, golden_run, teacher_manifest),
                    remediation_hint=self._remediation_hint(code),
                )
            )
        return patterns

    def _hidden_traps(
        self,
        teacher_manifest: TeacherInputManifest,
        teacher_report: TeacherRunnerReport,
    ) -> List[str]:
        traps = list(teacher_manifest.teacher_view.hidden_requirements)
        traps.extend(f"Pipeline-gap trap: {gap}" for gap in teacher_report.unresolved_gaps if "Weak Pipeline A signal:" in gap)
        traps.extend(
            f"Deferred-asset trap: {asset}"
            for asset in teacher_manifest.teacher_view.deferred_assets
        )
        return traps

    def _expected_reasoning_path(self, golden_run: GoldenRun) -> List[str]:
        path = [state.state_name for state in golden_run.intermediate_states]
        path.extend(step.skill_name for step in golden_run.steps)
        path.extend(check.check_name for check in golden_run.final_checks)
        return path

    def _rubric_projection(
        self,
        golden_run: GoldenRun,
        teacher_report: TeacherRunnerReport,
    ) -> RubricProjection:
        fact_checks = [
            self._final_check_description(check.check_name, check.status)
            for check in golden_run.final_checks
            if check.check_name in {"deliverable_presence", "deliverable_requirement_coverage", "evidence_traceability"}
        ]
        reasoning_checks = [
            step.expected_action
            for step in golden_run.steps
        ]
        robustness_checks = [
            self._failure_description(code)
            for code in teacher_report.diagnostics.warning_reason_codes
            if code in {"partial_intermediate_state", "single_source_support", "pipeline_a_signal_gaps"}
        ]
        compliance_checks = [
            self._final_check_description(check.check_name, check.status)
            for check in golden_run.final_checks
            if check.check_name in {"policy_clause_traceability", "conclusion_supported_by_visible_evidence"}
        ]
        return RubricProjection(
            fact_checks=fact_checks,
            reasoning_checks=reasoning_checks,
            robustness_checks=robustness_checks,
            compliance_checks=compliance_checks,
        )

    def _readiness(
        self,
        teacher_report: TeacherRunnerReport,
        supervision_items: List[StepSupervisionItem],
    ) -> AnnotationReadiness:
        if teacher_report.readiness == "not_ready" or any(item.status == "blocked" for item in supervision_items):
            return "not_ready"
        if teacher_report.readiness == "partial_ready" or any(item.status == "partial" for item in supervision_items):
            return "partial_ready"
        return "annotation_ready"

    def _diagnostics(
        self,
        artifact: TrainingAnnotationArtifact,
        teacher_report: TeacherRunnerReport,
    ) -> TrainingAnnotationDiagnostics:
        return TrainingAnnotationDiagnostics(
            readiness=artifact.readiness,
            supervision_item_count=len(artifact.supervision_items),
            intermediate_item_count=sum(1 for item in artifact.supervision_items if item.kind == "intermediate_state"),
            golden_step_item_count=sum(1 for item in artifact.supervision_items if item.kind == "golden_step"),
            final_check_item_count=sum(1 for item in artifact.supervision_items if item.kind == "final_check"),
            failure_mode_count=len(artifact.failure_modes),
            hidden_trap_count=len(artifact.hidden_traps),
            unresolved_gap_count=len(artifact.unresolved_gaps),
            partial_item_count=sum(1 for item in artifact.supervision_items if item.status == "partial"),
            blocked_item_count=sum(1 for item in artifact.supervision_items if item.status == "blocked"),
            warning_reason_codes=sorted(
                set(teacher_report.diagnostics.warning_reason_codes)
            ),
        )

    def _requirements_for_ids(
        self,
        evidence_ids: List[str],
        evidence_by_id: Dict[str, object],
        rationale_prefix: str,
    ) -> List[EvidenceRequirement]:
        requirements = []
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                continue
            requirements.append(
                EvidenceRequirement(
                    evidence_id=evidence.evidence_id,
                    file_name=evidence.file_name,
                    locator=evidence.locator,
                    semantic_type=evidence.semantic_type,
                    rationale=f"{rationale_prefix} `{evidence.evidence_id}`.",
                )
            )
        return requirements

    def _final_check_target_type(self, check_name: str):
        mapping = {
            "deliverable_presence": "binary_check",
            "deliverable_requirement_coverage": "binary_check",
            "evidence_traceability": "reasoning_check",
            "policy_clause_traceability": "reasoning_check",
            "conclusion_supported_by_visible_evidence": "reasoning_or_robustness_check",
        }
        return mapping.get(check_name, "reasoning_check")

    def _final_check_description(self, check_name: str, status: str) -> str:
        base = {
            "deliverable_presence": "Check that the expected deliverable path is supportable from the generated reference package.",
            "deliverable_requirement_coverage": "Check that the deliverable follows the required section order, populates required sections in place, places Evidence inventory before conclusions and Follow-up, and keeps conclusion bullets locally supported.",
            "evidence_traceability": "Check that every material conclusion bullet carries local bracketed support with exact candidate-visible Evidence_ID values rather than source labels.",
            "policy_clause_traceability": "Check that every policy-sensitive conclusion bullet carries local bracketed policy clause IDs together with exact supporting Evidence_ID values.",
            "conclusion_supported_by_visible_evidence": "Check that each supported conclusion, confirmed exception, and unresolved item is locally supported by exact visible evidence IDs rather than hidden assumptions or source labels.",
        }.get(check_name, f"Check `{check_name}`.")
        if status != "pass":
            return f"{base} Current status: {status}."
        return base

    def _failure_severity(self, code: str) -> str:
        if code in {"deferred_policy_reference", "relationship:policy_lookup"}:
            return "high"
        if code in {"low_subgraph_confidence", "pipeline_a_signal_gaps"}:
            return "medium"
        return "medium"

    def _failure_description(self, code: str) -> str:
        descriptions = {
            "deferred_policy_reference": "The model acts as if policy support exists even though the policy reference file is still missing.",
            "low_subgraph_confidence": "The model overcommits to a skill composition that is still backed only by fallback resource inference.",
            "partial_intermediate_state": "The model skips or compresses an intermediate reasoning state that the teacher contract expected to stay explicit.",
            "pipeline_a_signal_gaps": "The model hides missing graph-signal uncertainty instead of acknowledging it.",
            "relationship:policy_lookup": "The model claims policy-grounded conclusions without a complete policy lookup artifact.",
            "single_source_support": "The model treats a single source as decisive without preserving provenance caution.",
        }
        return descriptions.get(code, f"Failure mode triggered by `{code}`.")

    def _linked_skills_for_signal(
        self,
        code: str,
        golden_run: GoldenRun,
        teacher_manifest: TeacherInputManifest,
    ) -> List[str]:
        if code == "deferred_policy_reference":
            return [
                step.skill_id
                for step in golden_run.steps
                if "deferred_policy_reference" in step.blocking_reasons
            ]
        if code == "single_source_support":
            return [
                intention.skill_id
                for intention in teacher_manifest.teacher_view.skill_intentions
                if "single_source_support" in intention.common_failure_signals
            ]
        return [item.skill_id for item in teacher_manifest.teacher_view.skill_intentions]

    def _remediation_hint(self, code: str) -> str:
        hints = {
            "deferred_policy_reference": "Require an explicit unresolved note until the policy document is generated.",
            "low_subgraph_confidence": "Keep provenance and uncertainty visible in the reasoning trace.",
            "partial_intermediate_state": "Force the intermediate state to appear as a separate supervision checkpoint.",
            "pipeline_a_signal_gaps": "Teach the model to surface graph uncertainty instead of hiding it.",
            "relationship:policy_lookup": "Do not award full policy-grounded reasoning without a candidate-visible policy lookup source.",
            "single_source_support": "Require provenance wording and caution language when only one source supports the claim.",
        }
        return hints.get(code, "")

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        import hashlib

        raw = "|".join(parts)
        return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"
