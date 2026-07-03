import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_pipeline_b_batch_runner import (
    PipelineBBatchCaseSummary,
    PipelineBBatchRunReport,
)
from task_generator.v3_source_schema import load_json_file


FindingCategory = Literal["systemic", "motif_specific", "case_specific", "external_eval_candidate"]
FindingSeverity = Literal["high", "medium", "low", "info"]
ActionOwner = Literal["pipeline_a", "pipeline_b", "evaluation", "governance"]


SYSTEMIC_REASON_HINTS = {
    "low_subgraph_confidence": "Pipeline A selected skills still depend on fallback resource inference.",
    "pipeline_a_signal_gaps": "Selected cases carry missing Pipeline A graph/readiness signals.",
    "single_source_support": "Selected skills are supported by too little source diversity.",
    "partial_ready_chain": "The package chain stays partial across otherwise runnable cases.",
    "partial_intermediate_state": "Teacher/intermediate-state completion remains partial.",
}

CASE_OR_MOTIF_REASON_HINTS = {
    "blocked_rubric_criteria": "Rubric contains blocking criteria for this case or motif.",
    "blocked_training_annotation_items": "Training annotation contains blocking supervision items for this case or motif.",
    "not_ready_chain": "The case has a not-ready upstream chain.",
    "unresolved_gap": "The case carries unresolved teacher or annotation gaps.",
    "package_readiness:reject": "The package was rejected before draft-compatible export.",
}


class PipelineBBatchFeedbackRequest(BaseModel):
    batch_report_path: str
    output_dir: str


class BatchCaseArtifactSnapshot(BaseModel):
    case_id: str
    motif: str
    motif_grammar_id: Optional[str] = None
    workflow_context_fit: Optional[str] = None
    filled_roles: List[str] = Field(default_factory=list)
    missing_roles: List[str] = Field(default_factory=list)
    quality_blocking_count: int = 0
    quality_revise_count: int = 0
    teacher_readiness: Optional[str] = None
    teacher_blocking_reason_codes: List[str] = Field(default_factory=list)
    teacher_unresolved_gaps: List[str] = Field(default_factory=list)
    annotation_readiness: Optional[str] = None
    annotation_blocked_item_count: int = 0
    rubric_readiness: Optional[str] = None
    rubric_blocked_criterion_count: int = 0
    artifact_read_errors: List[str] = Field(default_factory=list)


class BatchFeedbackFinding(BaseModel):
    finding_id: str
    category: FindingCategory
    severity: FindingSeverity
    reason_code: str
    message: str
    affected_case_ids: List[str] = Field(default_factory=list)
    affected_motifs: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


class ExternalEvalCandidate(BaseModel):
    case_id: str
    motif: str
    case_dir: str
    eval_mode: Optional[str] = None
    readiness_label: str = "draft_inspection_only"
    reason: str = ""
    warnings: List[str] = Field(default_factory=list)


class PrioritizedBatchAction(BaseModel):
    action_id: str
    priority: int
    owner: ActionOwner
    title: str
    rationale: str
    linked_reason_codes: List[str] = Field(default_factory=list)
    linked_case_ids: List[str] = Field(default_factory=list)
    recommended_next_step: str = ""


class PipelineBBatchFeedbackDiagnostics(BaseModel):
    case_count: int = 0
    systemic_finding_count: int = 0
    motif_specific_finding_count: int = 0
    case_specific_finding_count: int = 0
    external_eval_candidate_count: int = 0
    reason_case_coverage: Dict[str, int] = Field(default_factory=dict)
    priority_reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class PipelineBBatchFeedbackReport(BaseModel):
    batch_feedback_version: str = "v3.pipeline_b_batch_feedback.1"
    request: PipelineBBatchFeedbackRequest
    batch_report_path: str
    batch_diagnostics: Dict[str, Any] = Field(default_factory=dict)
    case_artifact_snapshots: List[BatchCaseArtifactSnapshot] = Field(default_factory=list)
    findings: List[BatchFeedbackFinding] = Field(default_factory=list)
    prioritized_actions: List[PrioritizedBatchAction] = Field(default_factory=list)
    external_eval_candidates: List[ExternalEvalCandidate] = Field(default_factory=list)
    diagnostics: PipelineBBatchFeedbackDiagnostics
    notes: List[str] = Field(default_factory=list)


class PipelineBBatchFeedbackAnalyzer:
    """Analyze Pipeline B batch smoke output without mutating registry or priors."""

    def analyze(
        self,
        batch_report_path: str | Path,
        output_dir: str | Path,
    ) -> PipelineBBatchFeedbackReport:
        batch_path = Path(batch_report_path)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = PipelineBBatchFeedbackRequest(
            batch_report_path=str(batch_path),
            output_dir=str(output_path),
        )
        batch_report = PipelineBBatchRunReport.model_validate(load_json_file(str(batch_path)))
        reason_to_cases = self._reason_to_cases(batch_report.cases)
        case_snapshots = [self._case_snapshot(case) for case in batch_report.cases]
        findings = self._findings(batch_report.cases, reason_to_cases, case_snapshots)
        external_candidates = self._external_eval_candidates(batch_report.cases)
        actions = self._prioritized_actions(findings, external_candidates)
        diagnostics = self._diagnostics(
            batch_report=batch_report,
            findings=findings,
            external_candidates=external_candidates,
            reason_to_cases=reason_to_cases,
        )
        report = PipelineBBatchFeedbackReport(
            request=request,
            batch_report_path=str(batch_path),
            batch_diagnostics=batch_report.diagnostics.model_dump(),
            case_artifact_snapshots=case_snapshots,
            findings=findings,
            prioritized_actions=actions,
            external_eval_candidates=external_candidates,
            diagnostics=diagnostics,
            notes=[
                "This analyzer is report-only and does not mutate SkillRegistry, readiness reports, or transition priors.",
                "Systemic findings are based on case coverage, not repeated mentions within one case.",
                "External eval candidates remain draft inspection candidates unless a future quality gate marks them candidate_ready.",
            ],
        )
        self.write_outputs(report, output_path)
        return report

    def write_outputs(self, report: PipelineBBatchFeedbackReport, output_dir: str | Path) -> Dict[str, str]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        report_path = output_path / "pipeline_b_batch_feedback_report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return {"batch_feedback_report_path": str(report_path)}

    def _reason_to_cases(
        self,
        cases: List[PipelineBBatchCaseSummary],
    ) -> Dict[str, List[PipelineBBatchCaseSummary]]:
        reason_to_cases: Dict[str, List[PipelineBBatchCaseSummary]] = defaultdict(list)
        for case in cases:
            for reason_code in sorted(set(case.reason_codes + case.warning_reason_codes)):
                reason_to_cases[reason_code].append(case)
        return dict(reason_to_cases)

    def _case_snapshot(self, case: PipelineBBatchCaseSummary) -> BatchCaseArtifactSnapshot:
        case_dir = Path(case.case_dir)
        errors: List[str] = []
        quality = self._load_optional(case_dir / "quality_gate" / "pipeline_b_quality_report.json", errors)
        teacher = self._load_optional(case_dir / "teacher_runner" / "teacher_runner_report.json", errors)
        annotation = self._load_optional(case_dir / "training_annotation" / "training_annotation_report.json", errors)
        rubric = self._load_optional(case_dir / "rubric" / "rubric_report.json", errors)
        subgraph = self._load_optional(case_dir / "subgraph_sampler" / "pipeline_b_subgraph_report.json", errors)
        subgraph_diagnostics = (subgraph or {}).get("diagnostics") or {}
        return BatchCaseArtifactSnapshot(
            case_id=case.case_id,
            motif=case.motif,
            motif_grammar_id=subgraph_diagnostics.get("motif_grammar_id"),
            workflow_context_fit=subgraph_diagnostics.get("workflow_context_fit"),
            filled_roles=list(subgraph_diagnostics.get("filled_roles") or []),
            missing_roles=list(subgraph_diagnostics.get("missing_roles") or []),
            quality_blocking_count=int(((quality or {}).get("decision") or {}).get("blocking_count") or 0),
            quality_revise_count=int(((quality or {}).get("decision") or {}).get("revise_count") or 0),
            teacher_readiness=(teacher or {}).get("readiness"),
            teacher_blocking_reason_codes=list(
                (((teacher or {}).get("diagnostics") or {}).get("blocking_reason_codes") or [])
            ),
            teacher_unresolved_gaps=list((teacher or {}).get("unresolved_gaps") or []),
            annotation_readiness=(annotation or {}).get("readiness"),
            annotation_blocked_item_count=int(
                (((annotation or {}).get("diagnostics") or {}).get("blocked_item_count") or 0)
            ),
            rubric_readiness=(rubric or {}).get("readiness"),
            rubric_blocked_criterion_count=int(
                (((rubric or {}).get("diagnostics") or {}).get("blocked_criterion_count") or 0)
            ),
            artifact_read_errors=errors,
        )

    def _load_optional(self, path: Path, errors: List[str]) -> Optional[Dict[str, Any]]:
        if not path.exists():
            errors.append(f"missing:{path}")
            return None
        try:
            return load_json_file(str(path))
        except Exception as exc:
            errors.append(f"unreadable:{path}:{type(exc).__name__}")
            return None

    def _findings(
        self,
        cases: List[PipelineBBatchCaseSummary],
        reason_to_cases: Dict[str, List[PipelineBBatchCaseSummary]],
        snapshots: List[BatchCaseArtifactSnapshot],
    ) -> List[BatchFeedbackFinding]:
        findings: List[BatchFeedbackFinding] = []
        case_count = max(len(cases), 1)
        for reason_code, affected_cases in sorted(reason_to_cases.items()):
            affected_case_ids = sorted(case.case_id for case in affected_cases)
            affected_motifs = sorted(set(case.motif for case in affected_cases))
            coverage = len(affected_case_ids)
            if reason_code in SYSTEMIC_REASON_HINTS and coverage >= max(2, case_count // 2):
                findings.append(
                    self._finding(
                        category="systemic",
                        severity="high" if reason_code in {"low_subgraph_confidence", "pipeline_a_signal_gaps"} else "medium",
                        reason_code=reason_code,
                        message=SYSTEMIC_REASON_HINTS[reason_code],
                        affected_case_ids=affected_case_ids,
                        affected_motifs=affected_motifs,
                        evidence={"case_coverage": coverage, "batch_case_count": len(cases)},
                    )
                )
            elif reason_code in CASE_OR_MOTIF_REASON_HINTS:
                category: FindingCategory = "motif_specific" if len(affected_motifs) == 1 else "case_specific"
                findings.append(
                    self._finding(
                        category=category,
                        severity="high" if "blocked" in reason_code or "reject" in reason_code else "medium",
                        reason_code=reason_code,
                        message=CASE_OR_MOTIF_REASON_HINTS[reason_code],
                        affected_case_ids=affected_case_ids,
                        affected_motifs=affected_motifs,
                        evidence={"case_coverage": coverage, "batch_case_count": len(cases)},
                    )
                )

        for candidate in self._external_eval_candidates(cases):
            findings.append(
                self._finding(
                    category="external_eval_candidate",
                    severity="info",
                    reason_code="draft_external_eval_candidate",
                    message="Draft-compatible case can be selected for a guarded external rw-task smoke.",
                    affected_case_ids=[candidate.case_id],
                    affected_motifs=[candidate.motif],
                    evidence={"eval_mode": candidate.eval_mode, "readiness_label": candidate.readiness_label},
                )
            )

        for snapshot in snapshots:
            if snapshot.quality_blocking_count or snapshot.annotation_blocked_item_count or snapshot.rubric_blocked_criterion_count:
                findings.append(
                    self._finding(
                        category="case_specific",
                        severity="high",
                        reason_code="case_blocking_artifacts",
                        message="Case artifacts contain blocking quality, annotation, or rubric signals.",
                        affected_case_ids=[snapshot.case_id],
                        affected_motifs=[snapshot.motif],
                        evidence=snapshot.model_dump(),
                    )
                )
            if snapshot.missing_roles:
                findings.append(
                    self._finding(
                        category="motif_specific",
                        severity="medium",
                        reason_code="missing_motif_roles",
                        message="Sampler report shows that required motif roles were not fully covered by the selected subgraph.",
                        affected_case_ids=[snapshot.case_id],
                        affected_motifs=[snapshot.motif],
                        evidence={
                            "motif_grammar_id": snapshot.motif_grammar_id,
                            "workflow_context_fit": snapshot.workflow_context_fit,
                            "missing_roles": snapshot.missing_roles,
                            "filled_roles": snapshot.filled_roles,
                        },
                    )
                )
        return findings

    def _external_eval_candidates(
        self,
        cases: List[PipelineBBatchCaseSummary],
    ) -> List[ExternalEvalCandidate]:
        candidates: List[ExternalEvalCandidate] = []
        for case in cases:
            if (
                case.package_readiness == "revise_only"
                and case.validation_status == "draft_compatible"
                and case.eval_prep_status == "prepared"
            ):
                candidates.append(
                    ExternalEvalCandidate(
                        case_id=case.case_id,
                        motif=case.motif,
                        case_dir=case.case_dir,
                        eval_mode=case.eval_mode,
                        readiness_label="draft_inspection_only",
                        reason="Case is revise_only but structurally draft-compatible and prepared for eval dry-run.",
                        warnings=sorted(set(case.reason_codes + case.warning_reason_codes)),
                    )
                )
        return candidates

    def _prioritized_actions(
        self,
        findings: List[BatchFeedbackFinding],
        external_candidates: List[ExternalEvalCandidate],
    ) -> List[PrioritizedBatchAction]:
        by_reason = {finding.reason_code: finding for finding in findings}
        actions: List[PrioritizedBatchAction] = []
        substrate_codes = [
            code
            for code in ["low_subgraph_confidence", "pipeline_a_signal_gaps", "single_source_support"]
            if code in by_reason
        ]
        if substrate_codes:
            linked_cases = sorted(
                set(case_id for code in substrate_codes for case_id in by_reason[code].affected_case_ids)
            )
            actions.append(
                PrioritizedBatchAction(
                    action_id="batch_action_pipeline_a_resource_substrate",
                    priority=1,
                    owner="pipeline_a",
                    title="Improve typed resource, support diversity, and transition evidence for sampled skills.",
                    rationale="The same substrate warnings appear across multiple batch cases, so this is not a single-task prompt issue.",
                    linked_reason_codes=substrate_codes,
                    linked_case_ids=linked_cases,
                    recommended_next_step="Run a report-first Pipeline A typed-resource/support audit for the selected batch skill IDs before tuning candidate prompts again.",
                )
            )
        blocking_codes = [
            code
            for code in ["blocked_rubric_criteria", "blocked_training_annotation_items", "not_ready_chain", "unresolved_gap", "case_blocking_artifacts"]
            if code in by_reason
        ]
        if blocking_codes:
            linked_cases = sorted(
                set(case_id for code in blocking_codes for case_id in by_reason[code].affected_case_ids)
            )
            actions.append(
                PrioritizedBatchAction(
                    action_id="batch_action_inspect_rejected_motifs",
                    priority=2,
                    owner="pipeline_b",
                    title="Inspect rejected motif/case artifacts before expanding the batch.",
                    rationale="At least one case was rejected because annotation or rubric artifacts carried blocking signals.",
                    linked_reason_codes=blocking_codes,
                    linked_case_ids=linked_cases,
                    recommended_next_step="Open the rejected case's teacher_runner_report, training_annotation_report, and rubric_report to identify whether the motif needs stronger evidence planning or should be held out.",
                )
            )
        if "missing_motif_roles" in by_reason:
            actions.append(
                PrioritizedBatchAction(
                    action_id="batch_action_role_coverage_alignment",
                    priority=2,
                    owner="pipeline_b",
                    title="Inspect motif-role coverage gaps before moving to true role-filling sampling.",
                    rationale="The sampler can already surface which required motif roles are still missing, so the next improvement should target role coverage rather than prompt tuning.",
                    linked_reason_codes=["missing_motif_roles"],
                    linked_case_ids=sorted(by_reason["missing_motif_roles"].affected_case_ids),
                    recommended_next_step="Review subgraph sampler reports for repeated missing roles and decide whether the gap belongs to motif grammar, graph-role labels, or typed-resource coverage.",
                )
            )
        if external_candidates:
            actions.append(
                PrioritizedBatchAction(
                    action_id="batch_action_guarded_external_draft_smoke",
                    priority=3,
                    owner="evaluation",
                    title="Optionally run a tiny guarded external draft smoke on selected draft-compatible cases.",
                    rationale="The candidates are structurally compatible and eval-prepared, but remain revise_only and not final training data.",
                    linked_reason_codes=["draft_external_eval_candidate"],
                    linked_case_ids=[candidate.case_id for candidate in external_candidates],
                    recommended_next_step="Use at most two analyzer-selected draft cases for gpt-5.4-pro smoke after confirming API/network permission.",
                )
            )
        return sorted(actions, key=lambda action: action.priority)

    def _diagnostics(
        self,
        batch_report: PipelineBBatchRunReport,
        findings: List[BatchFeedbackFinding],
        external_candidates: List[ExternalEvalCandidate],
        reason_to_cases: Dict[str, List[PipelineBBatchCaseSummary]],
    ) -> PipelineBBatchFeedbackDiagnostics:
        category_counts = Counter(finding.category for finding in findings)
        reason_case_coverage = {
            reason_code: len(cases)
            for reason_code, cases in sorted(reason_to_cases.items())
        }
        role_case_coverage = Counter()
        for case in batch_report.cases:
            for role in case.missing_roles:
                role_case_coverage[role] += 1
        priority_reason_codes = [
            finding.reason_code
            for finding in findings
            if finding.category == "systemic" and finding.severity in {"high", "medium"}
        ]
        return PipelineBBatchFeedbackDiagnostics(
            case_count=len(batch_report.cases),
            systemic_finding_count=category_counts.get("systemic", 0),
            motif_specific_finding_count=category_counts.get("motif_specific", 0),
            case_specific_finding_count=category_counts.get("case_specific", 0),
            external_eval_candidate_count=len(external_candidates),
            reason_case_coverage={
                **reason_case_coverage,
                **{f"missing_role:{role}": count for role, count in sorted(role_case_coverage.items())},
            },
            priority_reason_codes=sorted(set(priority_reason_codes)),
            notes=[
                "Case coverage counts each affected case once even if a reason appears in both reason_codes and warning_reason_codes.",
                "Draft external candidates are not candidate_ready packages.",
            ],
        )

    def _finding(
        self,
        category: FindingCategory,
        severity: FindingSeverity,
        reason_code: str,
        message: str,
        affected_case_ids: List[str],
        affected_motifs: List[str],
        evidence: Dict[str, Any],
    ) -> BatchFeedbackFinding:
        return BatchFeedbackFinding(
            finding_id=self._stable_id("batch_find", [category, reason_code, *affected_case_ids]),
            category=category,
            severity=severity,
            reason_code=reason_code,
            message=message,
            affected_case_ids=affected_case_ids,
            affected_motifs=affected_motifs,
            evidence=evidence,
        )

    def _stable_id(self, prefix: str, parts: List[str]) -> str:
        import hashlib

        digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:10]
        return f"{prefix}_{digest}"


def write_batch_feedback_report(report: PipelineBBatchFeedbackReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
