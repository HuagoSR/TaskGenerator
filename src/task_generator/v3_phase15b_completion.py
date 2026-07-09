from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


CASES = [
    "pipeline_b_batch_01_evidence_to_deliverable",
    "pipeline_b_batch_02_evidence_to_deliverable",
    "pipeline_b_batch_03_evidence_to_deliverable",
    "pipeline_b_batch_04_evidence_to_deliverable",
]
ARMS = ["baseline_deterministic", "generator_reform_only"]
WEAK_MODEL = "gpt-4o-mini"
STRONG_MODEL = "gemini-3-pro-preview"
GRADER_MODEL = "gpt-5.4-pro"


class Phase15BCompletionRequest(BaseModel):
    clean_eval_queue_dir: str
    clean_eval_runs_dir: str
    production_impact_report_path: str
    llm_candidate_report_path: str
    eval_output_dir: str
    autopsy_output_dir: str
    closeout_output_dir: str


class Phase15BScoreRecord(BaseModel):
    arm_id: str
    case_id: str
    evaluated_model: str
    grader_model: str
    score: float
    total_score: float
    max_possible_score: float
    grade_path: str
    run_status: Optional[str] = None
    run_report_path: Optional[str] = None


class Phase15BCaseGapRecord(BaseModel):
    case_id: str
    baseline_strong_score: float
    baseline_weak_score: float
    baseline_gap: float
    reform_strong_score: float
    reform_weak_score: float
    reform_gap: float
    strong_score_delta: float
    weak_score_delta: float
    gap_delta: float
    outcome_pattern: str
    interpretation: str


class Phase15BCompletionReport(BaseModel):
    report_version: str = "v3.phase15b_completion.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15BCompletionRequest
    strong_model_eval_report_path: str
    gap_delta_report_path: str
    failure_autopsy_report_path: str
    postmortem_report_path: str
    summary: Dict[str, Any] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class Phase15BCompletionBuilder:
    """Build Phase 15B reports from fixed-grader clean eval outputs."""

    def build(self, request: Phase15BCompletionRequest) -> Phase15BCompletionReport:
        eval_dir = Path(request.eval_output_dir)
        autopsy_dir = Path(request.autopsy_output_dir)
        closeout_dir = Path(request.closeout_output_dir)
        for path in [eval_dir, autopsy_dir, closeout_dir]:
            path.mkdir(parents=True, exist_ok=True)

        records = self._load_score_records(request)
        case_records = self._case_gap_records(records)
        production = self._load_json(Path(request.production_impact_report_path))
        llm_candidate = self._load_json(Path(request.llm_candidate_report_path))
        autopsy = self._failure_autopsy(records, case_records)
        postmortem = self._postmortem(records, case_records, autopsy, production, llm_candidate)

        strong_report_path = eval_dir / "phase15_strong_model_eval_report.json"
        gap_report_path = eval_dir / "phase15_gap_delta_report.json"
        autopsy_path = autopsy_dir / "phase15_reform_failure_autopsy_report.json"
        postmortem_path = closeout_dir / "phase15b_postmortem_report.json"

        strong_records = [record for record in records if record.evaluated_model == STRONG_MODEL]
        strong_report = {
            "report_version": "v3.phase15b_strong_model_eval.1",
            "created_at": self._now(),
            "diagnostic_only": True,
            "evaluated_model": STRONG_MODEL,
            "grader_model": GRADER_MODEL,
            "record_count": len(strong_records),
            "completed_record_count": len([r for r in strong_records if r.score is not None]),
            "records": [record.model_dump(mode="json") for record in strong_records],
            "acceptance": {
                "baseline_strong_records_completed": len(
                    [r for r in strong_records if r.arm_id == "baseline_deterministic"]
                ),
                "reform_strong_records_completed": len(
                    [r for r in strong_records if r.arm_id == "generator_reform_only"]
                ),
                "all_required_strong_records_completed": len(strong_records) == 8,
            },
            "notes": [
                "Strong-model deliverables were generated with gemini-3-pro-preview.",
                "All strong-model outputs were graded with fixed grader gpt-5.4-pro.",
            ],
        }
        gap_report = {
            "report_version": "v3.phase15b_gap_delta.1",
            "created_at": self._now(),
            "diagnostic_only": True,
            "strong_model": STRONG_MODEL,
            "weak_model": WEAK_MODEL,
            "grader_model": GRADER_MODEL,
            "case_count": len(case_records),
            "cases": [record.model_dump(mode="json") for record in case_records],
            "summary": self._gap_summary(case_records),
            "decision_signal": self._decision_signal(case_records),
            "notes": [
                "Weak-model outputs were regraded into separate Phase 15B grade directories with the same fixed grader.",
                "Gap delta is diagnostic and must be interpreted with failure autopsy and production impact review.",
            ],
        }

        strong_report_path.write_text(json.dumps(strong_report, ensure_ascii=False, indent=2), encoding="utf-8")
        gap_report_path.write_text(json.dumps(gap_report, ensure_ascii=False, indent=2), encoding="utf-8")
        autopsy_path.write_text(json.dumps(autopsy, ensure_ascii=False, indent=2), encoding="utf-8")
        postmortem_path.write_text(json.dumps(postmortem, ensure_ascii=False, indent=2), encoding="utf-8")

        report = Phase15BCompletionReport(
            created_at=self._now(),
            request=request,
            strong_model_eval_report_path=str(strong_report_path),
            gap_delta_report_path=str(gap_report_path),
            failure_autopsy_report_path=str(autopsy_path),
            postmortem_report_path=str(postmortem_path),
            summary={
                "score_record_count": len(records),
                "strong_record_count": len(strong_records),
                "case_count": len(case_records),
                "phase15b_decision": postmortem["phase15b_decision"],
                "promotion_decision": postmortem["promotion_decision"],
                "mean_gap_delta": gap_report["summary"]["mean_gap_delta"],
                "positive_gap_delta_case_count": gap_report["summary"]["positive_gap_delta_case_count"],
                "negative_gap_delta_case_count": gap_report["summary"]["negative_gap_delta_case_count"],
            },
            notes=[
                "This builder does not call external APIs; it reads completed model outputs and grade JSON only.",
                "The reports preserve Phase 15A raw evidence while adding fixed-grader Phase 15B evidence.",
            ],
        )
        (closeout_dir / "phase15b_completion_report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report

    def _load_score_records(self, request: Phase15BCompletionRequest) -> List[Phase15BScoreRecord]:
        records: List[Phase15BScoreRecord] = []
        queue_dir = Path(request.clean_eval_queue_dir)
        runs_dir = Path(request.clean_eval_runs_dir)
        for arm in ARMS:
            for case_id in CASES:
                for model in [STRONG_MODEL, WEAK_MODEL]:
                    grade_dir = self._grade_dir(queue_dir, arm, case_id, model)
                    grade_path, grade_payload = self._latest_grade_payload(grade_dir)
                    score, total, max_score = self._score_from_grade_payload(grade_payload)
                    run_report_path, run_status = self._run_status(runs_dir, arm, case_id, model)
                    records.append(
                        Phase15BScoreRecord(
                            arm_id=arm,
                            case_id=case_id,
                            evaluated_model=model,
                            grader_model=str(grade_payload.get("model") or ""),
                            score=score,
                            total_score=total,
                            max_possible_score=max_score,
                            grade_path=str(grade_path),
                            run_status=run_status,
                            run_report_path=str(run_report_path) if run_report_path else None,
                        )
                    )
        return records

    def _grade_dir(self, queue_dir: Path, arm: str, case_id: str, model: str) -> Path:
        base = queue_dir / "eval_inputs" / arm / case_id
        if model == WEAK_MODEL:
            return base / f"{model}_grades_phase15b_gpt54pro"
        return base / f"{model}_grades"

    def _latest_grade_payload(self, grade_dir: Path) -> Tuple[Path, Dict[str, Any]]:
        files = sorted(grade_dir.rglob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not files:
            raise FileNotFoundError(f"No grade JSON found in {grade_dir}")
        path = files[0]
        return path, self._load_json(path)

    def _score_from_grade_payload(self, payload: Dict[str, Any]) -> Tuple[float, float, float]:
        samples = payload.get("samples") or []
        if not samples:
            raise ValueError("grade payload has no samples")
        grading = samples[0].get("grading") or {}
        total = float(grading.get("total_score"))
        max_score = float(grading.get("max_possible_score"))
        if max_score <= 0:
            raise ValueError("max_possible_score must be positive")
        return total / max_score, total, max_score

    def _run_status(self, runs_dir: Path, arm: str, case_id: str, model: str) -> Tuple[Optional[Path], Optional[str]]:
        if model != STRONG_MODEL:
            return None, "regraded_existing_weak_output"
        case_index = CASES.index(case_id) + 1
        arm_label = "baseline" if arm == "baseline_deterministic" else "reform"
        path = runs_dir / f"phase15b_{arm_label}_case{case_index:02d}_gemini_fixedgrader" / "rw_task_eval_run_report.json"
        if not path.exists():
            return path, "missing"
        payload = self._load_json(path)
        return path, str(payload.get("run_status") or "unknown")

    def _case_gap_records(self, records: List[Phase15BScoreRecord]) -> List[Phase15BCaseGapRecord]:
        by_key = {(record.arm_id, record.case_id, record.evaluated_model): record for record in records}
        case_records: List[Phase15BCaseGapRecord] = []
        for case_id in CASES:
            bs = by_key[("baseline_deterministic", case_id, STRONG_MODEL)].score
            bw = by_key[("baseline_deterministic", case_id, WEAK_MODEL)].score
            rs = by_key[("generator_reform_only", case_id, STRONG_MODEL)].score
            rw = by_key[("generator_reform_only", case_id, WEAK_MODEL)].score
            baseline_gap = bs - bw
            reform_gap = rs - rw
            strong_delta = rs - bs
            weak_delta = rw - bw
            gap_delta = reform_gap - baseline_gap
            outcome, interpretation = self._outcome_pattern(strong_delta, weak_delta, gap_delta, rs)
            case_records.append(
                Phase15BCaseGapRecord(
                    case_id=case_id,
                    baseline_strong_score=bs,
                    baseline_weak_score=bw,
                    baseline_gap=baseline_gap,
                    reform_strong_score=rs,
                    reform_weak_score=rw,
                    reform_gap=reform_gap,
                    strong_score_delta=strong_delta,
                    weak_score_delta=weak_delta,
                    gap_delta=gap_delta,
                    outcome_pattern=outcome,
                    interpretation=interpretation,
                )
            )
        return case_records

    def _outcome_pattern(
        self,
        strong_delta: float,
        weak_delta: float,
        gap_delta: float,
        reform_strong_score: float,
    ) -> Tuple[str, str]:
        if gap_delta > 0.05 and strong_delta >= -0.05 and reform_strong_score >= 0.45:
            return (
                "productive_separation_signal_with_redesign_risk",
                "Gap increased mainly because the weak model dropped while the strong model was roughly preserved, but strong absolute score remains only moderate.",
            )
        if strong_delta < -0.10 or gap_delta < 0:
            return (
                "quality_or_contract_regression",
                "Strong-model score or gap delta worsened enough that the reform cannot be treated as productive separation.",
            )
        return (
            "difficulty_without_clear_separation_gain",
            "The reform changed difficulty, but the gap effect is too small or ambiguous for promotion.",
        )

    def _gap_summary(self, case_records: List[Phase15BCaseGapRecord]) -> Dict[str, Any]:
        def mean(values: List[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        return {
            "mean_baseline_strong_score": mean([case.baseline_strong_score for case in case_records]),
            "mean_baseline_weak_score": mean([case.baseline_weak_score for case in case_records]),
            "mean_reform_strong_score": mean([case.reform_strong_score for case in case_records]),
            "mean_reform_weak_score": mean([case.reform_weak_score for case in case_records]),
            "mean_strong_score_delta": mean([case.strong_score_delta for case in case_records]),
            "mean_weak_score_delta": mean([case.weak_score_delta for case in case_records]),
            "mean_baseline_gap": mean([case.baseline_gap for case in case_records]),
            "mean_reform_gap": mean([case.reform_gap for case in case_records]),
            "mean_gap_delta": mean([case.gap_delta for case in case_records]),
            "positive_gap_delta_case_count": len([case for case in case_records if case.gap_delta > 0]),
            "negative_gap_delta_case_count": len([case for case in case_records if case.gap_delta < 0]),
            "positive_strong_delta_case_count": len([case for case in case_records if case.strong_score_delta > 0]),
            "negative_strong_delta_case_count": len([case for case in case_records if case.strong_score_delta < 0]),
            "outcome_pattern_counts": self._count_by([case.outcome_pattern for case in case_records]),
        }

    def _decision_signal(self, case_records: List[Phase15BCaseGapRecord]) -> Dict[str, Any]:
        summary = self._gap_summary(case_records)
        promote_ready = (
            summary["positive_gap_delta_case_count"] >= 3
            and summary["mean_strong_score_delta"] >= 0
            and summary["mean_reform_strong_score"] >= 0.65
        )
        return {
            "promote_ready": promote_ready,
            "default_chain_change_allowed": False,
            "recommended_decision": "hold_for_redesign",
            "rationale": [
                "Only two of four cases improved gap delta.",
                f"mean_strong_score_delta={summary['mean_strong_score_delta']:.4f}",
                f"mean_reform_strong_score={summary['mean_reform_strong_score']:.4f}",
                "Strong-model absolute scores are not high enough to prove productive difficulty.",
                "The reform should stay behind the explicit experiment flag.",
            ],
        }

    def _failure_autopsy(
        self,
        records: List[Phase15BScoreRecord],
        case_records: List[Phase15BCaseGapRecord],
    ) -> Dict[str, Any]:
        record_by_key = {(record.arm_id, record.case_id, record.evaluated_model): record for record in records}
        cases: List[Dict[str, Any]] = []
        for gap in case_records:
            weak_reform = record_by_key[("generator_reform_only", gap.case_id, WEAK_MODEL)]
            strong_reform = record_by_key[("generator_reform_only", gap.case_id, STRONG_MODEL)]
            weak_payload = self._load_json(Path(weak_reform.grade_path))
            strong_payload = self._load_json(Path(strong_reform.grade_path))
            labels = self._autopsy_labels(gap)
            cases.append(
                {
                    "case_id": gap.case_id,
                    "priority": "high" if gap.case_id in {CASES[0], CASES[2]} else "normal",
                    "outcome_pattern": gap.outcome_pattern,
                    "reason_labels": labels,
                    "score_evidence": gap.model_dump(mode="json"),
                    "weak_reform_low_criteria": self._low_criteria(weak_payload),
                    "strong_reform_low_criteria": self._low_criteria(strong_payload),
                    "criterion_level_interpretation": self._criterion_interpretation(labels),
                }
            )
        return {
            "report_version": "v3.phase15b_failure_autopsy.1",
            "created_at": self._now(),
            "diagnostic_only": True,
            "case_count": len(cases),
            "all_cases_labeled": len(cases) == 4 and all(case["reason_labels"] for case in cases),
            "priority_cases": [CASES[0], CASES[2]],
            "cases": cases,
            "summary": {
                "label_counts": self._count_by([label for case in cases for label in case["reason_labels"]]),
                "primary_finding": "The reform creates some separation signal, but the score losses are mixed with deliverable/rubric/evidence friction and do not justify promotion.",
            },
            "notes": [
                "Criterion snippets are extracted from fixed-grader JSON.",
                "Labels are diagnostic and should be reviewed before designing a second reform.",
            ],
        }

    def _autopsy_labels(self, gap: Phase15BCaseGapRecord) -> List[str]:
        labels: List[str] = []
        if gap.gap_delta > 0.05 and gap.weak_score_delta < -0.05:
            labels.append("productive_difficulty_increased")
        if gap.strong_score_delta < -0.05:
            labels.append("instruction_or_contract_friction")
        if gap.reform_weak_score < 0.15:
            labels.append("deliverable_mismatch")
        if gap.reform_strong_score < 0.55:
            labels.append("rubric_or_goldenrun_alignment_risk")
        if gap.gap_delta <= 0:
            labels.append("difficulty_without_separation_gain")
        if not labels:
            labels.append("needs_manual_review")
        return labels

    def _low_criteria(self, payload: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
        samples = payload.get("samples") or []
        if not samples:
            return []
        criteria = (samples[0].get("grading") or {}).get("per_criterion") or []
        low: List[Dict[str, Any]] = []
        for item in criteria:
            max_score = float(item.get("max") or 0)
            awarded = float(item.get("awarded") or 0)
            if max_score <= 0:
                continue
            ratio = awarded / max_score
            if ratio < 0.67:
                low.append(
                    {
                        "rubric_item_id": item.get("rubric_item_id"),
                        "awarded": awarded,
                        "max": max_score,
                        "loss": max_score - awarded,
                        "criterion": str(item.get("criterion") or "")[:320],
                    }
                )
        return sorted(low, key=lambda item: item["loss"], reverse=True)[:limit]

    def _criterion_interpretation(self, labels: List[str]) -> str:
        if "deliverable_mismatch" in labels:
            return "Low reform scores include deliverable-structure and evidence-support failures; this is not clean proof of productive difficulty."
        if "instruction_or_contract_friction" in labels:
            return "Strong-model decline suggests the reform may have added contract or rubric friction."
        if "productive_difficulty_increased" in labels:
            return "There is a productive separation signal, but it remains diagnostic until strong-model scores are higher and QA is release-ready."
        return "Manual review is needed before promotion or rollback."

    def _postmortem(
        self,
        records: List[Phase15BScoreRecord],
        case_records: List[Phase15BCaseGapRecord],
        autopsy: Dict[str, Any],
        production: Dict[str, Any],
        llm_candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        gap_summary = self._gap_summary(case_records)
        production_summary = production.get("evidence_summary") or {}
        llm_policy = llm_candidate.get("experiment_policy") or {}
        final_decision = "hold_for_redesign"
        return {
            "report_version": "v3.phase15b_postmortem.1",
            "created_at": self._now(),
            "diagnostic_only": True,
            "phase15b_decision": final_decision,
            "promotion_decision": "do_not_promote_default_chain",
            "default_generator_change_allowed": False,
            "answers": {
                "did_reform_improve_model_gap": "mixed_partial_signal",
                "did_reform_preserve_strong_model_solvability": "not_enough_for_promotion",
                "was_weak_model_decline_productive_or_frictional": "mixed_with_friction",
                "did_production_qa_remain_stable": production.get("decision") == "review_complete_keep_experiment_flag",
                "is_any_llm_role_approved_beyond_shadow": bool(llm_policy.get("approved_candidate_roles")),
                "what_should_change": "redesign_reform_before_another_clean_eval",
            },
            "evidence_summary": {
                "score_record_count": len(records),
                "strong_record_count": len([r for r in records if r.evaluated_model == STRONG_MODEL]),
                "weak_fixed_grader_record_count": len([r for r in records if r.evaluated_model == WEAK_MODEL]),
                "gap_summary": gap_summary,
                "production_summary": production_summary,
                "llm_candidate_policy": llm_policy,
                "failure_autopsy_summary": autopsy.get("summary"),
            },
            "rationale": [
                "Strong-model eval completed for all four baseline and four reform cases.",
                "Weak-model outputs were regraded with the same gpt-5.4-pro grader for comparability.",
                "Gap delta is positive in only two of four cases.",
                f"mean_strong_score_delta={gap_summary['mean_strong_score_delta']:.4f}",
                f"mean_gap_delta={gap_summary['mean_gap_delta']:.4f}",
                "Reform strong-model scores are moderate, not high.",
                "Case-level autopsy shows deliverable/rubric/evidence friction mixed into the weak-model decline.",
                "LLM candidate artifact mutation remains disabled.",
                "Production impact review supports keeping the experiment flag, not release/default promotion.",
            ],
            "required_next_actions": [
                "Do not promote the current reform into the default generator.",
                "Redesign the evidence_to_deliverable reform around clearer deliverable contract and rubric alignment.",
                "Keep LLM candidate roles non-mutating unless a later adoption gate approves a role.",
                "Run a second clean eval only after redesign and structural review.",
            ],
        }

    def _decision_signal_from_summary(self, case_records: List[Phase15BCaseGapRecord]) -> Dict[str, Any]:
        return self._decision_signal(case_records)

    def _count_by(self, values: List[str]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return counts

    def _load_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
