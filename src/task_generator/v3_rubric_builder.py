from pathlib import Path
from typing import Dict, List, Literal

from pydantic import BaseModel, Field

from task_generator.v3_teacher_runner import GoldenRun, TeacherRunnerReport
from task_generator.v3_training_annotation_builder import (
    TrainingAnnotationArtifact,
    TrainingAnnotationReport,
)
from task_generator.v3_source_schema import load_json_file


RubricReadiness = Literal["not_ready", "partial_ready", "rubric_ready"]
RubricSectionName = Literal[
    "fact_checks",
    "reasoning_checks",
    "robustness_checks",
    "compliance_checks",
]
CriterionType = Literal["fact", "reasoning", "robustness", "compliance"]
CriterionSeverity = Literal["low", "medium", "high"]
CriterionStatusHint = Literal["pass", "partial", "blocked"]


class RubricBuildRequest(BaseModel):
    training_annotation_path: str
    training_annotation_report_path: str
    golden_run_path: str
    teacher_runner_report_path: str


class RubricCriterion(BaseModel):
    criterion_id: str
    section: RubricSectionName
    criterion_type: CriterionType
    description: str
    evidence_requirements: List[Dict[str, str]] = Field(default_factory=list)
    pass_condition: str
    failure_signals: List[str] = Field(default_factory=list)
    severity: CriterionSeverity
    status_hint: CriterionStatusHint
    source_ids: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RubricSection(BaseModel):
    section_name: RubricSectionName
    criteria: List[RubricCriterion] = Field(default_factory=list)
    summary: List[str] = Field(default_factory=list)


class RubricArtifact(BaseModel):
    rubric_version: str = "v3.rubric.1"
    blueprint_id: str
    golden_run_id: str
    annotation_id: str
    readiness: RubricReadiness
    sections: List[RubricSection] = Field(default_factory=list)
    unresolved_gaps: List[str] = Field(default_factory=list)
    warning_reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class RubricDiagnostics(BaseModel):
    readiness: RubricReadiness
    section_count: int = 0
    criterion_count: int = 0
    partial_criterion_count: int = 0
    blocked_criterion_count: int = 0
    criteria_by_section: Dict[str, int] = Field(default_factory=dict)
    warning_reason_codes: List[str] = Field(default_factory=list)


class RubricReport(BaseModel):
    rubric_report_version: str = "v3.rubric_report.1"
    request: RubricBuildRequest
    blueprint_id: str
    readiness: RubricReadiness
    diagnostics: RubricDiagnostics
    notes: List[str] = Field(default_factory=list)


class RubricBuilder:
    """Build a structured, report-first rubric from deterministic teacher artifacts."""

    def build(
        self,
        training_annotation_path: str | Path,
        training_annotation_report_path: str | Path,
        golden_run_path: str | Path,
        teacher_runner_report_path: str | Path,
    ) -> tuple[RubricArtifact, RubricReport]:
        annotation = TrainingAnnotationArtifact.model_validate(load_json_file(str(training_annotation_path)))
        annotation_report = TrainingAnnotationReport.model_validate(
            load_json_file(str(training_annotation_report_path))
        )
        golden_run = GoldenRun.model_validate(load_json_file(str(golden_run_path)))
        teacher_report = TeacherRunnerReport.model_validate(load_json_file(str(teacher_runner_report_path)))

        sections = self._sections(annotation, golden_run, teacher_report)
        readiness = self._readiness(annotation_report, teacher_report, sections)
        warning_reason_codes = sorted(
            set(
                annotation_report.diagnostics.warning_reason_codes
                + teacher_report.diagnostics.warning_reason_codes
            )
        )

        artifact = RubricArtifact(
            blueprint_id=annotation.blueprint_id,
            golden_run_id=annotation.golden_run_id,
            annotation_id=annotation.annotation_id,
            readiness=readiness,
            sections=sections,
            unresolved_gaps=annotation.unresolved_gaps,
            warning_reason_codes=warning_reason_codes,
            notes=[
                "RubricBuilder V1 emits a structured contract, not an executable grader.",
                "Partial readiness and unresolved gaps are preserved rather than hidden.",
                "This artifact is designed to feed a later quality gate or export layer.",
            ],
        )
        diagnostics = self._diagnostics(artifact)
        report = RubricReport(
            request=RubricBuildRequest(
                training_annotation_path=str(training_annotation_path),
                training_annotation_report_path=str(training_annotation_report_path),
                golden_run_path=str(golden_run_path),
                teacher_runner_report_path=str(teacher_runner_report_path),
            ),
            blueprint_id=annotation.blueprint_id,
            readiness=readiness,
            diagnostics=diagnostics,
            notes=[
                "The rubric report keeps criterion counts and readiness visible for downstream gates.",
                "JSON-only output is intentional in this first rubric slice.",
            ],
        )
        return artifact, report

    def write_outputs(
        self,
        artifact: RubricArtifact,
        report: RubricReport,
        output_dir: str | Path,
    ) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        rubric_path = output_path / "rubric.json"
        report_path = output_path / "rubric_report.json"
        rubric_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {
            "rubric_path": str(rubric_path),
            "rubric_report_path": str(report_path),
        }

    def _sections(
        self,
        annotation: TrainingAnnotationArtifact,
        golden_run: GoldenRun,
        teacher_report: TeacherRunnerReport,
    ) -> List[RubricSection]:
        sections: Dict[RubricSectionName, List[RubricCriterion]] = {
            "fact_checks": [],
            "reasoning_checks": [],
            "robustness_checks": [],
            "compliance_checks": [],
        }

        for item in annotation.supervision_items:
            criterion = self._criterion_from_supervision_item(item)
            sections[criterion.section].append(criterion)

        for failure_mode in annotation.failure_modes:
            criterion = self._criterion_from_failure_mode(failure_mode)
            sections[criterion.section].append(criterion)

        self._inject_projection_summaries(sections, annotation)
        self._inject_golden_run_notes(sections, golden_run, teacher_report)

        return [
            RubricSection(
                section_name=section_name,
                criteria=criteria,
                summary=self._section_summary(section_name, criteria, annotation),
            )
            for section_name, criteria in sections.items()
        ]

    def _criterion_from_supervision_item(self, item) -> RubricCriterion:
        section = self._section_for_item(item)
        criterion_type = self._criterion_type_for_section(section)
        failure_signals = list(item.warning_codes)
        status_hint = self._status_hint(item.status)
        return RubricCriterion(
            criterion_id=item.item_id,
            section=section,
            criterion_type=criterion_type,
            description=item.expected_behavior,
            evidence_requirements=[
                {
                    "evidence_id": req.evidence_id,
                    "file_name": req.file_name,
                    "locator": req.locator,
                    "semantic_type": req.semantic_type,
                    "rationale": req.rationale,
                }
                for req in item.evidence_requirements
            ],
            pass_condition=self._pass_condition(item, section),
            failure_signals=failure_signals,
            severity=self._severity_from_codes(item.warning_codes, section),
            status_hint=status_hint,
            source_ids=[item.item_id, *item.linked_skill_ids],
            notes=item.notes,
        )

    def _criterion_from_failure_mode(self, failure_mode) -> RubricCriterion:
        section = self._section_for_failure_signal(failure_mode.signal)
        return RubricCriterion(
            criterion_id=failure_mode.failure_id,
            section=section,
            criterion_type=self._criterion_type_for_section(section),
            description=failure_mode.description,
            evidence_requirements=[],
            pass_condition=f"Avoid failure mode: {failure_mode.signal}.",
            failure_signals=[failure_mode.signal],
            severity=self._severity_from_signal(failure_mode.signal),
            status_hint="partial",
            source_ids=[failure_mode.failure_id, *failure_mode.linked_skill_ids],
            notes=[failure_mode.remediation_hint] if failure_mode.remediation_hint else [],
        )

    def _inject_projection_summaries(
        self,
        sections: Dict[RubricSectionName, List[RubricCriterion]],
        annotation: TrainingAnnotationArtifact,
    ) -> None:
        projection_map = {
            "fact_checks": annotation.rubric_projection.fact_checks,
            "reasoning_checks": annotation.rubric_projection.reasoning_checks,
            "robustness_checks": annotation.rubric_projection.robustness_checks,
            "compliance_checks": annotation.rubric_projection.compliance_checks,
        }
        for section_name, summaries in projection_map.items():
            for index, summary in enumerate(summaries, start=1):
                sections[section_name].append(
                    RubricCriterion(
                        criterion_id=self._stable_id(
                            "proj", [annotation.annotation_id, section_name, str(index)]
                        ),
                        section=section_name,
                        criterion_type=self._criterion_type_for_section(section_name),
                        description=summary,
                        evidence_requirements=[],
                        pass_condition=f"Section summary expectation is satisfied: {summary}",
                        failure_signals=[],
                        severity="medium",
                        status_hint="partial" if annotation.readiness != "annotation_ready" else "pass",
                        source_ids=[annotation.annotation_id],
                        notes=["Derived from training annotation rubric projection."],
                    )
                )

    def _inject_golden_run_notes(
        self,
        sections: Dict[RubricSectionName, List[RubricCriterion]],
        golden_run: GoldenRun,
        teacher_report: TeacherRunnerReport,
    ) -> None:
        for gap in golden_run.unresolved_gaps:
            signal = self._signal_from_gap(gap)
            section = self._section_for_failure_signal(signal)
            sections[section].append(
                RubricCriterion(
                    criterion_id=self._stable_id("gap", [golden_run.golden_run_id, gap]),
                    section=section,
                    criterion_type=self._criterion_type_for_section(section),
                    description=gap,
                    evidence_requirements=[],
                    pass_condition="The evaluator should preserve this unresolved gap as a visible caveat.",
                    failure_signals=[signal] if signal else [],
                    severity=self._severity_from_signal(signal) if signal else "medium",
                    status_hint="partial",
                    source_ids=[golden_run.golden_run_id],
                    notes=["Derived from teacher unresolved gap reporting."],
                )
            )

        for code in teacher_report.diagnostics.warning_reason_codes:
            if code == "relationship:policy_lookup":
                sections["compliance_checks"].append(
                    RubricCriterion(
                        criterion_id=self._stable_id("warn", [golden_run.golden_run_id, code]),
                        section="compliance_checks",
                        criterion_type="compliance",
                        description="Policy lookup support must remain explicit and incomplete until the policy reference exists.",
                        evidence_requirements=[],
                        pass_condition="Do not award full policy-grounded compliance credit without candidate-visible policy lookup support.",
                        failure_signals=[code],
                        severity="high",
                        status_hint="partial",
                        source_ids=[golden_run.golden_run_id],
                        notes=["Explicit warning criterion injected from teacher diagnostics."],
                    )
                )

    def _readiness(
        self,
        annotation_report: TrainingAnnotationReport,
        teacher_report: TeacherRunnerReport,
        sections: List[RubricSection],
    ) -> RubricReadiness:
        if annotation_report.readiness == "not_ready" or teacher_report.readiness == "not_ready":
            return "not_ready"
        if annotation_report.readiness == "partial_ready" or teacher_report.readiness == "partial_ready":
            return "partial_ready"
        if any(criterion.status_hint != "pass" for section in sections for criterion in section.criteria):
            return "partial_ready"
        return "rubric_ready"

    def _diagnostics(self, artifact: RubricArtifact) -> RubricDiagnostics:
        criteria = [criterion for section in artifact.sections for criterion in section.criteria]
        return RubricDiagnostics(
            readiness=artifact.readiness,
            section_count=len(artifact.sections),
            criterion_count=len(criteria),
            partial_criterion_count=sum(1 for criterion in criteria if criterion.status_hint == "partial"),
            blocked_criterion_count=sum(1 for criterion in criteria if criterion.status_hint == "blocked"),
            criteria_by_section={
                section.section_name: len(section.criteria) for section in artifact.sections
            },
            warning_reason_codes=artifact.warning_reason_codes,
        )

    def _section_for_item(self, item) -> RubricSectionName:
        if item.kind == "final_check":
            if item.name == "deliverable_presence":
                return "fact_checks"
            if item.name == "evidence_traceability":
                return "reasoning_checks"
            return "compliance_checks"
        if item.kind == "intermediate_state":
            if "policy" in item.name:
                return "compliance_checks"
            return "reasoning_checks"
        if any(code in {"single_source_support", "low_subgraph_confidence", "pipeline_a_signal_gaps"} for code in item.warning_codes):
            return "robustness_checks"
        return "reasoning_checks"

    def _section_for_failure_signal(self, signal: str) -> RubricSectionName:
        if signal in {"deferred_policy_reference", "relationship:policy_lookup"}:
            return "compliance_checks"
        if signal in {"low_subgraph_confidence", "pipeline_a_signal_gaps", "single_source_support"}:
            return "robustness_checks"
        if signal == "partial_intermediate_state":
            return "reasoning_checks"
        return "reasoning_checks"

    def _criterion_type_for_section(self, section: RubricSectionName) -> CriterionType:
        mapping = {
            "fact_checks": "fact",
            "reasoning_checks": "reasoning",
            "robustness_checks": "robustness",
            "compliance_checks": "compliance",
        }
        return mapping[section]

    def _pass_condition(self, item, section: RubricSectionName) -> str:
        if item.kind == "final_check":
            return f"Final check `{item.name}` is satisfied with the expected evidence discipline."
        if item.kind == "intermediate_state":
            return f"Intermediate state `{item.name}` is explicitly present and grounded in the required evidence."
        if section == "robustness_checks":
            return f"Reasoning for `{item.name}` stays explicit about uncertainty and provenance."
        return f"Expected behavior for `{item.name}` is covered without omitting evidence-backed reasoning."

    def _severity_from_codes(
        self, codes: List[str], section: RubricSectionName
    ) -> CriterionSeverity:
        if any(code in {"deferred_policy_reference", "relationship:policy_lookup"} for code in codes):
            return "high"
        if any(code in {"low_subgraph_confidence", "pipeline_a_signal_gaps", "single_source_support", "partial_intermediate_state"} for code in codes):
            return "medium"
        if section in {"fact_checks", "compliance_checks"}:
            return "medium"
        return "low"

    def _severity_from_signal(self, signal: str) -> CriterionSeverity:
        if signal in {"deferred_policy_reference", "relationship:policy_lookup"}:
            return "high"
        if signal in {"low_subgraph_confidence", "pipeline_a_signal_gaps", "single_source_support", "partial_intermediate_state"}:
            return "medium"
        return "low"

    def _status_hint(self, status: str) -> CriterionStatusHint:
        if status == "blocked":
            return "blocked"
        if status == "partial":
            return "partial"
        return "pass"

    def _section_summary(
        self,
        section_name: RubricSectionName,
        criteria: List[RubricCriterion],
        annotation: TrainingAnnotationArtifact,
    ) -> List[str]:
        summary = [
            f"{section_name} criterion_count={len(criteria)}",
            f"annotation_readiness={annotation.readiness}",
        ]
        if section_name == "compliance_checks" and "policy_reference.docx" in " ".join(annotation.unresolved_gaps):
            summary.append("Policy-reference-related incompleteness remains explicit in this section.")
        return summary

    def _signal_from_gap(self, gap: str) -> str:
        if "policy_reference.docx" in gap or "policy_lookup" in gap:
            return "deferred_policy_reference"
        if "single_source_support" in gap:
            return "single_source_support"
        if "low_subgraph_confidence" in gap:
            return "low_subgraph_confidence"
        if "pipeline_a_signal_gaps" in gap or "Weak Pipeline A signal:" in gap:
            return "pipeline_a_signal_gaps"
        return "partial_intermediate_state"

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        import hashlib

        raw = "|".join(parts)
        return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]}"

