from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_rw_task_eval_summarizer import RwTaskEvalSummaryReport
from task_generator.v3_source_schema import load_json_file


FeedbackStatus = Literal["blocked", "analyzed"]
LikelyFailureSource = Literal[
    "prompt_deliverable_contract",
    "reference_evidence_traceability",
    "policy_reference_prompting",
    "teacher_step_operationalization",
    "rubric_alignment",
    "pipeline_a_signal_gap",
]
ActionOwner = Literal["pipeline_b", "pipeline_a", "shared"]
Priority = Literal["high", "medium", "low"]


class EvalFeedbackAnalyzerRequest(BaseModel):
    eval_summary_report_path: str
    rubric_path: str
    training_annotation_path: str
    teacher_runner_report_path: str
    quality_gate_report_path: str
    output_dir: str


class LowScoringCriterion(BaseModel):
    criterion_text: str
    awarded: float
    max_score: float
    score_ratio: float
    rubric_section: str = "unknown"
    likely_failure_source: LikelyFailureSource
    rationale: str


class RecommendedAction(BaseModel):
    action_id: str
    owner: ActionOwner
    priority: Priority
    category: str
    recommendation: str
    linked_signals: List[str] = Field(default_factory=list)


class PipelineBEvalFeedbackReport(BaseModel):
    feedback_version: str = "v3.pipeline_b_eval_feedback.1"
    request: EvalFeedbackAnalyzerRequest
    feedback_status: FeedbackStatus
    eval_evidence_use: str = "unknown"
    case_id: str = "unknown"
    run_status: str = "unknown"
    quality_gate_decision: str = "unknown"
    toolchain_completed: bool = False
    score_summary: Dict[str, Any] = Field(default_factory=dict)
    low_scoring_criteria: List[LowScoringCriterion] = Field(default_factory=list)
    likely_failure_sources: List[Dict[str, Any]] = Field(default_factory=list)
    pipeline_b_actions: List[RecommendedAction] = Field(default_factory=list)
    pipeline_a_feedback: List[RecommendedAction] = Field(default_factory=list)
    candidate_ready_blockers: List[str] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    warning_reason_codes: List[str] = Field(default_factory=list)
    do_not_update_registry: bool = True
    notes: List[str] = Field(default_factory=list)


class PipelineBEvalFeedbackAnalyzer:
    """Turn eval summary artifacts into report-only next-step guidance."""

    def analyze(
        self,
        eval_summary_report_path: str | Path,
        rubric_path: str | Path,
        training_annotation_path: str | Path,
        teacher_runner_report_path: str | Path,
        quality_gate_report_path: str | Path,
        output_dir: str | Path,
    ) -> PipelineBEvalFeedbackReport:
        summary_path = Path(eval_summary_report_path)
        rubric_path = Path(rubric_path)
        annotation_path = Path(training_annotation_path)
        teacher_path = Path(teacher_runner_report_path)
        quality_path = Path(quality_gate_report_path)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        request = EvalFeedbackAnalyzerRequest(
            eval_summary_report_path=str(summary_path),
            rubric_path=str(rubric_path),
            training_annotation_path=str(annotation_path),
            teacher_runner_report_path=str(teacher_path),
            quality_gate_report_path=str(quality_path),
            output_dir=str(output_path),
        )

        blocking_reasons: List[str] = []
        summary_report = self._load_summary(summary_path, blocking_reasons)
        rubric = self._load_json(rubric_path, "rubric", blocking_reasons)
        annotation = self._load_json(annotation_path, "training_annotation", blocking_reasons)
        teacher_report = self._load_json(teacher_path, "teacher_runner_report", blocking_reasons)
        quality_report = self._load_json(quality_path, "quality_gate_report", blocking_reasons)
        grade_report = self._load_grade_report(summary_report, blocking_reasons)

        low_scoring_criteria = self._low_scoring_criteria(rubric, grade_report)
        likely_failure_sources = self._aggregate_failure_sources(low_scoring_criteria)
        warning_reason_codes = list(summary_report.warning_reason_codes) if summary_report else []
        candidate_ready_blockers = self._candidate_ready_blockers(
            quality_report=quality_report,
            teacher_report=teacher_report,
            warning_reason_codes=warning_reason_codes,
        )
        pipeline_b_actions = self._pipeline_b_actions(
            low_scoring_criteria=low_scoring_criteria,
            warning_reason_codes=warning_reason_codes,
            annotation=annotation,
        )
        pipeline_a_feedback = self._pipeline_a_feedback(
            warning_reason_codes=warning_reason_codes,
            teacher_report=teacher_report,
        )

        sample_summary = (summary_report.samples[0] if summary_report and summary_report.samples else None)
        report = PipelineBEvalFeedbackReport(
            request=request,
            feedback_status="blocked" if blocking_reasons else "analyzed",
            eval_evidence_use=summary_report.evidence_use if summary_report else "unknown",
            case_id=summary_report.case_id if summary_report else "unknown",
            run_status=summary_report.run_status if summary_report else "unknown",
            quality_gate_decision=str(((quality_report or {}).get("decision") or {}).get("decision") or "unknown"),
            toolchain_completed=bool(summary_report and summary_report.toolchain_completed),
            score_summary={
                "sample_count": summary_report.sample_count if summary_report else 0,
                "successful_sample_count": summary_report.successful_sample_count if summary_report else 0,
                "average_score_ratio": summary_report.average_score_ratio if summary_report else None,
                "score_ratio_label": self._score_ratio_label(
                    sample_summary.score_ratio if sample_summary else None
                ),
                "draft_grade": {
                    "total_score": sample_summary.total_score if sample_summary else None,
                    "max_possible_score": sample_summary.max_possible_score if sample_summary else None,
                },
            },
            low_scoring_criteria=low_scoring_criteria,
            likely_failure_sources=likely_failure_sources,
            pipeline_b_actions=pipeline_b_actions,
            pipeline_a_feedback=pipeline_a_feedback,
            candidate_ready_blockers=candidate_ready_blockers,
            blocking_reasons=sorted(set(blocking_reasons)),
            warning_reason_codes=sorted(set(warning_reason_codes)),
            notes=self._notes(summary_report),
        )
        self.write_report(report, output_path / "pipeline_b_eval_feedback_report.json")
        return report

    def write_report(self, report: PipelineBEvalFeedbackReport, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _load_summary(
        self,
        summary_path: Path,
        blocking_reasons: List[str],
    ) -> Optional[RwTaskEvalSummaryReport]:
        if not summary_path.exists():
            blocking_reasons.append("eval_summary_report_missing")
            return None
        try:
            return RwTaskEvalSummaryReport.model_validate(load_json_file(str(summary_path)))
        except Exception:
            blocking_reasons.append("eval_summary_report_unreadable")
            return None

    def _load_json(
        self,
        path: Path,
        label: str,
        blocking_reasons: List[str],
    ) -> Optional[Dict[str, Any]]:
        if not path.exists():
            blocking_reasons.append(f"{label}_missing")
            return None
        try:
            return load_json_file(str(path))
        except Exception:
            blocking_reasons.append(f"{label}_unreadable")
            return None

    def _load_grade_report(
        self,
        summary_report: Optional[RwTaskEvalSummaryReport],
        blocking_reasons: List[str],
    ) -> Optional[Dict[str, Any]]:
        if not summary_report or not summary_report.request.grade_report_path:
            blocking_reasons.append("grade_report_path_missing_from_summary")
            return None
        grade_path = Path(summary_report.request.grade_report_path)
        if not grade_path.exists():
            blocking_reasons.append("grade_report_missing")
            return None
        try:
            return load_json_file(str(grade_path))
        except Exception:
            blocking_reasons.append("grade_report_unreadable")
            return None

    def _low_scoring_criteria(
        self,
        rubric: Optional[Dict[str, Any]],
        grade_report: Optional[Dict[str, Any]],
    ) -> List[LowScoringCriterion]:
        rubric_section_map = self._rubric_section_map(rubric)
        if not grade_report:
            return []
        samples = grade_report.get("samples") or []
        if not samples:
            return []
        criteria = ((samples[0].get("grading") or {}).get("per_criterion")) or []
        low_scoring: List[LowScoringCriterion] = []
        for item in criteria:
            awarded = float(item.get("awarded") or 0)
            max_score = float(item.get("max") or 0)
            if max_score <= 0:
                continue
            score_ratio = awarded / max_score
            if score_ratio >= 0.75:
                continue
            criterion_text = str(item.get("criterion") or "")
            low_scoring.append(
                LowScoringCriterion(
                    criterion_text=criterion_text,
                    awarded=awarded,
                    max_score=max_score,
                    score_ratio=score_ratio,
                    rubric_section=rubric_section_map.get(criterion_text, "unknown"),
                    likely_failure_source=self._failure_source_for_text(criterion_text),
                    rationale=self._rationale_for_text(criterion_text, score_ratio),
                )
            )
        return low_scoring

    def _rubric_section_map(self, rubric: Optional[Dict[str, Any]]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        if not rubric:
            return mapping
        for section in rubric.get("sections") or []:
            section_name = str(section.get("section_name") or "unknown")
            for criterion in section.get("criteria") or []:
                description = str(criterion.get("description") or "")
                if description:
                    mapping[description] = section_name
        return mapping

    def _failure_source_for_text(self, text: str) -> LikelyFailureSource:
        lowered = text.lower()
        if (
            "pipeline a" in lowered
            or "graph-signal" in lowered
            or "subgraph_edge" in lowered
            or "low_subgraph_confidence" in lowered
        ):
            return "pipeline_a_signal_gap"
        if "policy" in lowered or "withholding" in lowered:
            return "policy_reference_prompting"
        if "cite" in lowered or "visible evidence" in lowered or "evidence ids" in lowered:
            return "reference_evidence_traceability"
        if "deliverable path" in lowered:
            return "prompt_deliverable_contract"
        if any(
            phrase in lowered
            for phrase in [
                "available evidence units",
                "required deliverable sections",
                "intermediate reasoning state",
                "handle exceptions",
                "reconcile source totals",
                "consolidate period financial data",
                "apply foreign tax withholding",
            ]
        ):
            return "teacher_step_operationalization"
        if "hidden assumptions" in lowered or "manager-ready" in lowered:
            return "rubric_alignment"
        return "pipeline_a_signal_gap"

    def _rationale_for_text(self, text: str, score_ratio: float) -> str:
        source = self._failure_source_for_text(text)
        ratio_text = f"score_ratio={score_ratio:.3f}"
        if source == "policy_reference_prompting":
            return f"{ratio_text}; policy-specific judgment is under-supported in the current prompt/teacher contract."
        if source == "reference_evidence_traceability":
            return f"{ratio_text}; the grader wants tighter evidence-to-conclusion mapping than the current package enforces."
        if source == "prompt_deliverable_contract":
            return f"{ratio_text}; deliverable expectations are probably too implicit for the current candidate prompt."
        if source == "teacher_step_operationalization":
            return f"{ratio_text}; skill-specific behavior likely needs more explicit intermediate states or step-level prompting."
        if source == "rubric_alignment":
            return f"{ratio_text}; grader expectations and current deliverable framing are only partially aligned."
        return f"{ratio_text}; low score is likely entangled with weak Pipeline A graph signals or missing support diversity."

    def _aggregate_failure_sources(
        self,
        criteria: List[LowScoringCriterion],
    ) -> List[Dict[str, Any]]:
        counts: Dict[str, int] = {}
        examples: Dict[str, str] = {}
        for criterion in criteria:
            counts[criterion.likely_failure_source] = counts.get(criterion.likely_failure_source, 0) + 1
            examples.setdefault(criterion.likely_failure_source, criterion.criterion_text)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [
            {
                "failure_source": source,
                "count": count,
                "example_criterion": examples[source],
            }
            for source, count in ordered
        ]

    def _candidate_ready_blockers(
        self,
        quality_report: Optional[Dict[str, Any]],
        teacher_report: Optional[Dict[str, Any]],
        warning_reason_codes: List[str],
    ) -> List[str]:
        blockers: List[str] = []
        decision = str(((quality_report or {}).get("decision") or {}).get("decision") or "")
        if decision:
            blockers.append(f"quality_gate:{decision}")
        for code in warning_reason_codes:
            if code in {
                "low_subgraph_confidence",
                "partial_intermediate_state",
                "pipeline_a_signal_gaps",
                "single_source_support",
                "partial_ready_chain",
            }:
                blockers.append(code)
        unresolved = ((teacher_report or {}).get("unresolved_gaps")) or []
        blockers.extend(str(item) for item in unresolved[:8])
        return sorted(dict.fromkeys(blockers))

    def _pipeline_b_actions(
        self,
        low_scoring_criteria: List[LowScoringCriterion],
        warning_reason_codes: List[str],
        annotation: Optional[Dict[str, Any]],
    ) -> List[RecommendedAction]:
        actions: List[RecommendedAction] = []
        sources = {criterion.likely_failure_source for criterion in low_scoring_criteria}
        if "reference_evidence_traceability" in sources:
            actions.append(
                RecommendedAction(
                    action_id="pb_eval_fb_01",
                    owner="pipeline_b",
                    priority="high",
                    category="prompt_and_evidence_contract",
                    recommendation="Make the candidate prompt require evidence IDs or clause locators for every material conclusion, not only in general instructions.",
                    linked_signals=["reference_evidence_traceability", "draft_quality_observation"],
                )
            )
        if "teacher_step_operationalization" in sources:
            actions.append(
                RecommendedAction(
                    action_id="pb_eval_fb_02",
                    owner="pipeline_b",
                    priority="high",
                    category="teacher_runner_and_annotation",
                    recommendation="Strengthen step-level supervision so each sampled skill becomes an explicit expected operation in teacher states, annotation targets, and prompt wording.",
                    linked_signals=["teacher_step_operationalization", "partial_intermediate_state"],
                )
            )
        if "policy_reference_prompting" in sources:
            actions.append(
                RecommendedAction(
                    action_id="pb_eval_fb_03",
                    owner="pipeline_b",
                    priority="medium",
                    category="policy_reference_usage",
                    recommendation="Expose policy-rule usage more concretely in the prompt and teacher contract so policy-to-evidence mapping is not left implicit.",
                    linked_signals=["policy_reference_prompting"],
                )
            )
        if "rubric_alignment" in sources:
            actions.append(
                RecommendedAction(
                    action_id="pb_eval_fb_04",
                    owner="pipeline_b",
                    priority="medium",
                    category="rubric_alignment",
                    recommendation="Tighten the rubric descriptions to match what the draft deliverable is realistically expected to show, especially for support and conclusion framing.",
                    linked_signals=["rubric_alignment", "draft_quality_observation"],
                )
            )
        supervision_items = len((annotation or {}).get("supervision_items") or [])
        if supervision_items < 15:
            actions.append(
                RecommendedAction(
                    action_id="pb_eval_fb_05",
                    owner="pipeline_b",
                    priority="medium",
                    category="annotation_density",
                    recommendation="Increase training supervision density around the weakest rubric dimensions so grader-visible expectations are mirrored earlier in the chain.",
                    linked_signals=[f"supervision_items:{supervision_items}"],
                )
            )
        if "partial_intermediate_state" in warning_reason_codes:
            actions.append(
                RecommendedAction(
                    action_id="pb_eval_fb_06",
                    owner="pipeline_b",
                    priority="high",
                    category="intermediate_state_completion",
                    recommendation="Reduce partial teacher steps before chasing higher eval scores; the current package still asks the model to bridge too much reasoning on its own.",
                    linked_signals=["partial_intermediate_state", "partial_ready_chain"],
                )
            )
        return actions

    def _pipeline_a_feedback(
        self,
        warning_reason_codes: List[str],
        teacher_report: Optional[Dict[str, Any]],
    ) -> List[RecommendedAction]:
        actions: List[RecommendedAction] = []
        unresolved = " | ".join(((teacher_report or {}).get("unresolved_gaps")) or [])
        if "pipeline_a_signal_gaps" in warning_reason_codes:
            actions.append(
                RecommendedAction(
                    action_id="pa_eval_fb_01",
                    owner="pipeline_a",
                    priority="high",
                    category="typed_resources_and_roles",
                    recommendation="Improve persistent registry typed-resource coverage and missing core graph roles so sampled subgraphs stop relying on fallback inference.",
                    linked_signals=["pipeline_a_signal_gaps", unresolved],
                )
            )
        if "single_source_support" in warning_reason_codes:
            actions.append(
                RecommendedAction(
                    action_id="pa_eval_fb_02",
                    owner="pipeline_a",
                    priority="high",
                    category="support_diversity",
                    recommendation="Increase multi-source support for the currently sampled skills so teacher steps and grader expectations are not anchored to fragile single-source evidence.",
                    linked_signals=["single_source_support"],
                )
            )
        if "low_subgraph_confidence" in warning_reason_codes:
            actions.append(
                RecommendedAction(
                    action_id="pa_eval_fb_03",
                    owner="shared",
                    priority="medium",
                    category="transition_and_motif_evidence",
                    recommendation="Strengthen transition evidence and motif support for the sampled edge set so the next sampled package can carry higher structural confidence into Pipeline B.",
                    linked_signals=["low_subgraph_confidence"],
                )
            )
        return actions

    def _score_ratio_label(self, score_ratio: Optional[float]) -> str:
        if score_ratio is None:
            return "unknown"
        if score_ratio >= 0.85:
            return "strong"
        if score_ratio >= 0.65:
            return "mixed"
        return "weak_but_informative"

    def _notes(self, summary_report: Optional[RwTaskEvalSummaryReport]) -> List[str]:
        notes = [
            "This analyzer is report-only and does not update quality gates, registries, transition priors, or package readiness.",
            "Current rw-task grading is used here as diagnostic evidence, not as candidate_ready truth.",
        ]
        if summary_report and summary_report.evidence_use == "draft_quality_observation":
            notes.append(
                "The analyzed score came from a draft_inspection_only package and should be used to prioritize improvements, not to certify training readiness."
            )
        return notes
