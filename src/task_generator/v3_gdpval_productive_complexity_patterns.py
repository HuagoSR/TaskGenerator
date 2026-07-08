from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class GDPValProductivePatternRequest(BaseModel):
    gdpval_anatomy_report_path: str
    gdpval_anatomy_distribution_path: str
    gdpval_gap_autopsy_path: str
    output_dir: str


class GDPValProductivePattern(BaseModel):
    pattern_id: str
    source: str = "GDPVal finance/audit calibration subset"
    productive_complexity_type: str
    description: str
    translatable_to_taskgenerator: bool
    safe_to_implement_without_new_file_types: bool
    target_taskgenerator_motifs: List[str] = Field(default_factory=list)
    target_generator_layers: List[str] = Field(default_factory=list)
    required_changes: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


class GDPValProductivePatternLibraryReport(BaseModel):
    report_version: str = "v3.phase15_gdpval_productive_complexity_patterns.1"
    created_at: str
    request: GDPValProductivePatternRequest
    diagnostic_only: bool = True
    use: str = "eval_calibration_only"
    not_for_training_generation: bool = True
    pattern_count: int
    patterns: List[GDPValProductivePattern] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PatternToGeneratorMappingReport(BaseModel):
    report_version: str = "v3.phase15_pattern_to_generator_mapping.1"
    created_at: str
    diagnostic_only: bool = True
    mappings: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_first_reform: Dict[str, Any] = Field(default_factory=dict)


class GDPValProductivePatternBuilder:
    def build(self, request: GDPValProductivePatternRequest) -> GDPValProductivePatternLibraryReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        anatomy = self._read_json(Path(request.gdpval_anatomy_report_path))
        distribution = self._read_json(Path(request.gdpval_anatomy_distribution_path))
        autopsy = self._read_json(Path(request.gdpval_gap_autopsy_path))

        patterns = self._patterns(anatomy, distribution, autopsy)
        report = GDPValProductivePatternLibraryReport(
            created_at=self._now(),
            request=request,
            pattern_count=len(patterns),
            patterns=patterns,
            next_actions=[
                "Map the evidence_ecology and reviewer_facing_output patterns into evidence_to_deliverable reform first.",
                "Keep PDF/OCR/email expansion out of Phase 15 unless a later experiment explicitly opens new file types.",
                "Use these patterns as reform constraints, not as GDPVal task rewrites.",
            ],
            notes=[
                "GDPVal remains eval_calibration_only and not_for_training_generation.",
                "Patterns are abstracted from anatomy/gap evidence; they are not copied task templates.",
                "safe_to_implement_without_new_file_types means current xlsx/docx-like generator layers can approximate the pattern.",
            ],
        )
        mapping = self._mapping_report(patterns)
        self._write_json(output_dir / "gdpval_productive_complexity_pattern_library.json", report.model_dump(mode="json"))
        self._write_json(output_dir / "pattern_to_generator_mapping_report.json", mapping.model_dump(mode="json"))
        return report

    def _patterns(
        self,
        anatomy: Dict[str, Any],
        distribution: Dict[str, Any],
        autopsy: Dict[str, Any],
    ) -> List[GDPValProductivePattern]:
        signal_counts = autopsy.get("productive_complexity_signal_counts") or {}
        gap_counts = autopsy.get("gap_band_counts") or {}
        motif_counts = distribution.get("motif_counts") or {}
        reasoning_counts = distribution.get("reasoning_requirement_counts") or {}
        deliverable_counts = distribution.get("deliverable_type_counts") or {}
        high_cases = [
            case.get("task_id")
            for case in autopsy.get("cases") or []
            if case.get("gap_band") == "high" and case.get("usable_for_gap_analysis")
        ]
        base_evidence = {
            "task_count": anatomy.get("task_count"),
            "usable_task_count": autopsy.get("usable_task_count"),
            "high_gap_case_count": len(high_cases),
            "gap_band_counts": gap_counts,
        }
        return [
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_role_trigger_stakeholder_v1",
                productive_complexity_type="role_and_trigger_pattern",
                description="A professional role receives a concrete business trigger and must produce work for a named stakeholder or review context.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["evidence_to_deliverable", "policy_application", "fan_in_reconciliation"],
                target_generator_layers=["blueprint_prototype", "reference_file_planner", "prompt_export"],
                required_changes=["add actor role", "add business trigger", "add recipient/reviewer context", "add decision consequence"],
                risks=["could add prose without increasing actual reasoning if not tied to evidence"],
                evidence={**base_evidence, "workflow_realism_features": "explicit professional role and stakeholder context recur in high-gap cases"},
            ),
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_multi_reference_evidence_ecology_v1",
                productive_complexity_type="evidence_ecology_pattern",
                description="The task requires locating and reconciling claims across multiple reference sources or source sections.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["evidence_to_deliverable", "cross_check_validation", "fan_in_reconciliation"],
                target_generator_layers=["reference_file_planner", "reference_file_generator", "evidence_index"],
                required_changes=["add second reference source", "add source-vs-summary mismatch", "require evidence provenance"],
                risks=["could increase run time", "could become frictional if evidence IDs are unstable"],
                evidence={**base_evidence, "cross_file_reasoning_count": reasoning_counts.get("cross_file_synthesis"), "multi_reference_signal": signal_counts.get("multi_reference_workflow")},
            ),
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_reviewer_facing_deliverable_contract_v1",
                productive_complexity_type="deliverable_contract_pattern",
                description="The deliverable is a reviewer-facing work product with explicit structure, limitations, and decision-use context.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["evidence_to_deliverable", "policy_application"],
                target_generator_layers=["blueprint_prototype", "rubric_builder", "rw_task_exporter"],
                required_changes=["convert generic report into manager memo or audit finding summary", "require supported/unresolved split", "make rubric candidate-visible"],
                risks=["unscorable free-form writing if rubric does not stay structured"],
                evidence={**base_evidence, "deliverable_counts": deliverable_counts},
            ),
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_cross_file_reasoning_v1",
                productive_complexity_type="cross_file_reasoning_pattern",
                description="The model must connect evidence from one file to calculations, classifications, or conclusions in another.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["cross_check_validation", "fan_in_reconciliation", "evidence_to_deliverable"],
                target_generator_layers=["motif_graph_grammar", "reference_file_planner", "teacher_runner"],
                required_changes=["add cross-evidence dependency", "require citation for each conclusion", "separate confirmed and conflicting evidence"],
                risks=["can become hidden-answer matching if evidence links are not candidate-visible"],
                evidence={**base_evidence, "hypothesis": "H1 cross-file evidence localization supports useful gap"},
            ),
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_calculation_reconciliation_v1",
                productive_complexity_type="calculation_reconciliation_pattern",
                description="The task combines numeric computation with reconciliation to a control total, schedule, or exception list.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["fan_in_reconciliation", "cross_check_validation", "evidence_to_deliverable"],
                target_generator_layers=["motif_graph_grammar", "reference_file_generator", "golden_run"],
                required_changes=["add control total", "add reconciliation difference explanation", "require numeric trace"],
                risks=["grader complexity may rise", "numeric targets must remain evidence-grounded"],
                evidence={**base_evidence, "spreadsheet_calculation_count": reasoning_counts.get("spreadsheet_calculation"), "reconciliation_count": reasoning_counts.get("reconciliation")},
            ),
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_policy_compliance_application_v1",
                productive_complexity_type="policy_or_compliance_pattern",
                description="The task requires applying visible policy criteria to evidence and explaining the supported decision.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["policy_application", "cross_check_validation"],
                target_generator_layers=["reference_file_generator", "rubric_builder", "task_verifier"],
                required_changes=["add policy excerpt", "require policy-to-evidence citation", "avoid hidden policy truth"],
                risks=["policy truth leakage", "unsupported legal/compliance claims"],
                evidence={**base_evidence, "policy_application_count": reasoning_counts.get("policy_application"), "hypothesis": "H4 policy/application tasks separate models differently"},
            ),
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_professional_judgment_v1",
                productive_complexity_type="professional_judgment_pattern",
                description="The task asks for a grounded recommendation or classification rather than only a mechanical extraction.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["evidence_to_deliverable", "policy_application"],
                target_generator_layers=["blueprint_prototype", "teacher_runner", "rubric_builder"],
                required_changes=["add severity/materiality classification", "require limitation statement", "require recommendation with evidence"],
                risks=["subjective grading if rubric lacks observable criteria"],
                evidence={**base_evidence, "exception_handling_count": reasoning_counts.get("exception_handling")},
            ),
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_uncertainty_exception_handling_v1",
                productive_complexity_type="uncertainty_or_exception_pattern",
                description="The task includes unresolved, conflicting, or exception evidence that must be separated from confirmed findings.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["evidence_to_deliverable", "cross_check_validation", "fan_in_reconciliation"],
                target_generator_layers=["reference_file_planner", "evidence_index", "rubric_builder"],
                required_changes=["add exception log or ambiguity trap", "require unresolved issue section", "score confirmed-vs-unresolved separation"],
                risks=["ambiguous expected output if trap is not manifestable"],
                evidence={**base_evidence, "exception_handling_count": reasoning_counts.get("exception_handling"), "assumption_handling_count": reasoning_counts.get("assumption_handling")},
            ),
            GDPValProductivePattern(
                pattern_id="gdpval_pattern_review_workpaper_or_memo_v1",
                productive_complexity_type="reviewer_facing_output_pattern",
                description="The output is framed as a workpaper, manager memo, audit finding, or executive review artifact.",
                translatable_to_taskgenerator=True,
                safe_to_implement_without_new_file_types=True,
                target_taskgenerator_motifs=["evidence_to_deliverable", "fan_in_reconciliation", "policy_application"],
                target_generator_layers=["blueprint_prototype", "package_assembler", "rw_task_exporter"],
                required_changes=["name the reviewer audience", "include conclusion and limitations", "preserve structured deliverable expectations"],
                risks=["format noise if presentation aesthetics dominate reasoning"],
                evidence={**base_evidence, "document_or_slide_count": (deliverable_counts.get("document_report") or 0) + (deliverable_counts.get("slide_deck") or 0)},
            ),
        ]

    def _mapping_report(self, patterns: List[GDPValProductivePattern]) -> PatternToGeneratorMappingReport:
        mappings = [
            {
                "pattern_id": pattern.pattern_id,
                "target_taskgenerator_motifs": pattern.target_taskgenerator_motifs,
                "target_generator_layers": pattern.target_generator_layers,
                "safe_to_implement_without_new_file_types": pattern.safe_to_implement_without_new_file_types,
                "phase15_priority": "P0" if "evidence_to_deliverable" in pattern.target_taskgenerator_motifs else "P1",
            }
            for pattern in patterns
        ]
        return PatternToGeneratorMappingReport(
            created_at=self._now(),
            mappings=mappings,
            recommended_first_reform={
                "motif": "evidence_to_deliverable",
                "patterns_to_apply": [
                    "gdpval_pattern_role_trigger_stakeholder_v1",
                    "gdpval_pattern_multi_reference_evidence_ecology_v1",
                    "gdpval_pattern_reviewer_facing_deliverable_contract_v1",
                    "gdpval_pattern_uncertainty_exception_handling_v1",
                    "gdpval_pattern_review_workpaper_or_memo_v1",
                ],
                "guardrails": [
                    "no new file type required for first reform",
                    "no hidden ground truth",
                    "keep verifier and production QA unchanged",
                    "validate with A/B/C clean paired eval",
                ],
            },
        )

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
