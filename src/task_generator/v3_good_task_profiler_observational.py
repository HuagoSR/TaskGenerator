from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GoodTaskProfilerObservationalRequest(BaseModel):
    gdpval_anatomy_jsonl_path: str
    gdpval_gap_autopsy_report_path: str
    runnable_slice_manifest_path: str
    taskgenerator_comparison_plan_path: str
    generated_task_eval_summary_path: str = ""
    output_dir: str


class ObservationDimension(BaseModel):
    value: str
    evidence: List[str] = Field(default_factory=list)


class ObservationalTaskProfile(BaseModel):
    profile_version: str = "v3.good_task_observational_profile.1"
    task_id: str
    source: str
    use: str
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    not_for_training_generation: bool = False
    queue_role: str = ""
    evaluation_status: str = "not_evaluated"
    deliverable_type: str = "unknown"
    deliverable_format: str = "unknown"
    reference_file_count: int = 0
    motif_or_motifs: List[str] = Field(default_factory=list)
    reasoning_requirements: List[str] = Field(default_factory=list)
    model_scores: Dict[str, Optional[float]] = Field(default_factory=dict)
    observed_gap: Optional[float] = None
    gap_band: str = "not_available"
    runnability_status: str = "unknown"
    grading_status: str = "unknown"
    productive_complexity: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="unknown"))
    frictional_complexity: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="unknown"))
    model_separation_quality: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="not_observed"))
    evidence_closure: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="unknown"))
    workflow_realism: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="unknown"))
    training_value: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="unknown"))
    evaluation_stability: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="unknown"))
    format_noise_risk: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="unknown"))
    tool_failure_risk: ObservationDimension = Field(default_factory=lambda: ObservationDimension(value="unknown"))
    gap_hypotheses: List[Dict[str, Any]] = Field(default_factory=list)
    human_or_llm_autopsy_notes: List[str] = Field(default_factory=list)


class GoodTaskProfilerObservationalReport(BaseModel):
    report_version: str = "v3.good_task_profiler_observational.1"
    created_at: str
    request: GoodTaskProfilerObservationalRequest
    diagnostic_only: bool = True
    not_benchmark_grade: bool = True
    scored_profiler_status: str = "not_enabled"
    weighted_good_task_score_emitted: bool = False
    profile_count: int
    gdpval_profile_count: int
    taskgenerator_profile_count: int
    evaluated_profile_count: int
    pending_eval_profile_count: int
    distribution_report_path: str
    profile_jsonl_path: str
    profiles: List[ObservationalTaskProfile] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GoodTaskProfilerDistributionReport(BaseModel):
    report_version: str = "v3.good_task_profiler_observational_distribution.1"
    created_at: str
    profile_count: int
    source_counts: Dict[str, int] = Field(default_factory=dict)
    queue_role_counts: Dict[str, int] = Field(default_factory=dict)
    evaluation_status_counts: Dict[str, int] = Field(default_factory=dict)
    deliverable_type_counts: Dict[str, int] = Field(default_factory=dict)
    gap_band_counts: Dict[str, int] = Field(default_factory=dict)
    productive_complexity_counts: Dict[str, int] = Field(default_factory=dict)
    frictional_complexity_counts: Dict[str, int] = Field(default_factory=dict)
    format_noise_risk_counts: Dict[str, int] = Field(default_factory=dict)
    tool_failure_risk_counts: Dict[str, int] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class GoodTaskProfilerObservationalBuilder:
    def build(self, request: GoodTaskProfilerObservationalRequest) -> GoodTaskProfilerObservationalReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        anatomy_by_id = self._read_jsonl_by_id(Path(request.gdpval_anatomy_jsonl_path))
        autopsy = self._read_json(Path(request.gdpval_gap_autopsy_report_path))
        runnable = self._read_json(Path(request.runnable_slice_manifest_path))
        generated_plan = self._read_json(Path(request.taskgenerator_comparison_plan_path))
        generated_eval = self._read_optional_json(Path(request.generated_task_eval_summary_path))

        autopsy_by_id = {str(item.get("task_id") or ""): item for item in autopsy.get("cases") or []}
        generated_gap_by_id = {str(item.get("task_id") or ""): item for item in generated_eval.get("gap_records") or []}
        generated_scores_by_id: Dict[str, Dict[str, Optional[float]]] = {}
        for item in generated_eval.get("model_scores") or []:
            task_id = str(item.get("task_id") or "")
            model = str(item.get("model") or "")
            if task_id and model:
                generated_scores_by_id.setdefault(task_id, {})[model] = self._as_float(item.get("score_ratio"))
        profiles: List[ObservationalTaskProfile] = []
        for group_name in ["gdpval_seed_cases", "gdpval_holdout_cases", "next_gdpval_eval_queue"]:
            for record in runnable.get(group_name) or []:
                task_id = str(record.get("task_id") or "")
                profiles.append(
                    self._gdpval_profile(
                        queue_record=record,
                        anatomy=anatomy_by_id.get(task_id, {}),
                        autopsy=autopsy_by_id.get(task_id, {}),
                    )
                )
        for record in generated_plan.get("selected_tasks") or []:
            task_id = str(record.get("task_id") or "")
            profiles.append(
                self._taskgenerator_profile(
                    record,
                    gap_record=generated_gap_by_id.get(task_id, {}),
                    model_scores=generated_scores_by_id.get(task_id, {}),
                )
            )

        profile_jsonl_path = output_dir / "good_task_observational_profiles.jsonl"
        profile_jsonl_path.write_text(
            "".join(json.dumps(profile.model_dump(mode="json"), ensure_ascii=False) + "\n" for profile in profiles),
            encoding="utf-8",
        )
        distribution = self._distribution(profiles)
        distribution_path = output_dir / "good_task_observational_distribution_report.json"
        self._write_json(distribution_path, distribution.model_dump(mode="json"))

        report = GoodTaskProfilerObservationalReport(
            created_at=self._now(),
            request=request,
            profile_count=len(profiles),
            gdpval_profile_count=sum(1 for profile in profiles if profile.source == "openai/gdpval"),
            taskgenerator_profile_count=sum(1 for profile in profiles if profile.source == "taskgenerator/phase13_reviewed_release"),
            evaluated_profile_count=sum(1 for profile in profiles if profile.evaluation_status == "clean_paired_eval"),
            pending_eval_profile_count=sum(1 for profile in profiles if profile.evaluation_status in {"pending_eval", "needs_model_rerun"}),
            distribution_report_path=str(distribution_path),
            profile_jsonl_path=str(profile_jsonl_path),
            profiles=profiles,
            notes=[
                "GoodTaskProfiler-Observational V1 records evidence fields only.",
                "No weighted GoodTaskScore is emitted by this report.",
                "Generated TaskGenerator profiles are pending diagnostic comparison until executed eval evidence exists.",
            ],
        )
        self._write_json(output_dir / "good_task_profiler_observational_report.json", report.model_dump(mode="json"))
        return report

    def _gdpval_profile(
        self,
        *,
        queue_record: Dict[str, Any],
        anatomy: Dict[str, Any],
        autopsy: Dict[str, Any],
    ) -> ObservationalTaskProfile:
        queue_role = str(queue_record.get("queue_role") or "")
        clean_status = str(queue_record.get("clean_status") or "not_evaluated")
        evaluation_status = self._gdpval_eval_status(queue_role, clean_status)
        productive_signals = [str(item) for item in autopsy.get("productive_complexity_signals") or []]
        frictional_signals = [str(item) for item in autopsy.get("frictional_complexity_signals") or []]
        gap_band = str(queue_record.get("gap_band") or autopsy.get("gap_band") or "not_available")
        return ObservationalTaskProfile(
            task_id=str(queue_record.get("task_id") or ""),
            source="openai/gdpval",
            use="eval_calibration_only",
            not_for_training_generation=True,
            queue_role=queue_role,
            evaluation_status=evaluation_status,
            deliverable_type=str(queue_record.get("deliverable_type") or anatomy.get("deliverable_type") or "unknown"),
            deliverable_format=str(queue_record.get("deliverable_format") or anatomy.get("deliverable_format") or "unknown"),
            reference_file_count=int(queue_record.get("reference_file_count") or anatomy.get("reference_file_count") or 0),
            motif_or_motifs=[str(item) for item in (queue_record.get("likely_skill_motifs") or anatomy.get("likely_skill_motifs") or [])],
            reasoning_requirements=[str(item) for item in (queue_record.get("reasoning_requirements") or anatomy.get("reasoning_requirements") or [])],
            model_scores={str(k): self._as_float(v) for k, v in (anatomy.get("clean_eval", {}).get("model_scores") or {}).items()},
            observed_gap=self._as_float(queue_record.get("score_gap") if queue_record.get("score_gap") is not None else autopsy.get("observed_gap")),
            gap_band=gap_band,
            runnability_status=self._runnability_status(queue_role, autopsy),
            grading_status="completed" if evaluation_status == "clean_paired_eval" else "not_completed",
            productive_complexity=self._productive_complexity(productive_signals, anatomy),
            frictional_complexity=self._frictional_complexity(frictional_signals, queue_role),
            model_separation_quality=self._model_separation_quality(gap_band, evaluation_status),
            evidence_closure=self._evidence_closure(anatomy),
            workflow_realism=self._workflow_realism(anatomy),
            training_value=ObservationDimension(
                value="not_training_use",
                evidence=["GDPVal tasks are calibration-only and not_for_training_generation."],
            ),
            evaluation_stability=self._evaluation_stability(evaluation_status, autopsy),
            format_noise_risk=self._format_noise_risk(autopsy),
            tool_failure_risk=self._tool_failure_risk(autopsy, queue_role),
            gap_hypotheses=[item for item in autopsy.get("hypothesis_evidence") or []],
            human_or_llm_autopsy_notes=[str(item) for item in autopsy.get("autopsy_notes") or []],
        )

    def _taskgenerator_profile(
        self,
        record: Dict[str, Any],
        *,
        gap_record: Dict[str, Any],
        model_scores: Dict[str, Optional[float]],
    ) -> ObservationalTaskProfile:
        motif = str(record.get("motif") or "")
        usable = bool(gap_record.get("usable_for_gap_analysis"))
        observed_gap = self._as_float(gap_record.get("score_gap"))
        gap_band = self._gap_band(observed_gap) if usable else "not_available"
        evaluation_status = "clean_paired_eval" if usable else "pending_eval"
        return ObservationalTaskProfile(
            task_id=str(record.get("task_id") or ""),
            source="taskgenerator/phase13_reviewed_release",
            use="generated_training_candidate_diagnostic_comparison",
            not_for_training_generation=False,
            queue_role=str(record.get("queue_role") or "taskgenerator_comparison_eval_candidate"),
            evaluation_status=evaluation_status,
            deliverable_type="generated_release_task",
            deliverable_format="release_bundle",
            reference_file_count=0,
            motif_or_motifs=[motif] if motif else [],
            reasoning_requirements=self._generated_reasoning_requirements(motif),
            model_scores=model_scores,
            observed_gap=observed_gap,
            gap_band=gap_band,
            runnability_status="runnable_clean" if usable else "not_yet_measured",
            grading_status="completed" if usable else "not_run",
            productive_complexity=ObservationDimension(
                value="candidate",
                evidence=[f"Phase 13 reviewed release motif: {motif}", "Selected for generated-vs-GDPVal comparison."],
            ),
            frictional_complexity=ObservationDimension(
                value="low_observed" if usable else "unknown_until_eval",
                evidence=["Clean paired generated-task eval exists."] if usable else ["No executed comparison evidence yet."],
            ),
            model_separation_quality=self._model_separation_quality(gap_band, evaluation_status),
            evidence_closure=ObservationDimension(value="phase13_release_claim", evidence=[str(record.get("decision") or "")]),
            workflow_realism=ObservationDimension(value="phase13_reviewed", evidence=[f"motif:{motif}", str(record.get("blueprint_id") or "")]),
            training_value=ObservationDimension(value="candidate", evidence=["Task is from reviewed strict Phase 13 release."]),
            evaluation_stability=ObservationDimension(
                value="clean_single_run" if usable else "pending_eval",
                evidence=["Both configured model sides completed and graded."] if usable else ["Requires rw-task diagnostic comparison."],
            ),
            format_noise_risk=ObservationDimension(
                value="not_dominant_observed" if usable else "unknown_until_eval",
                evidence=["No format failure in generated eval summary."] if usable else ["No generated comparison grading evidence yet."],
            ),
            tool_failure_risk=ObservationDimension(
                value="low_observed" if usable else "unknown_until_eval",
                evidence=["No execution failure in generated eval summary."] if usable else ["No generated comparison execution evidence yet."],
            ),
            gap_hypotheses=[
                {
                    "hypothesis_id": "TG_COMPARE",
                    "status": "observed_clean_pair" if usable else "pending_eval",
                    "rationale": (
                        f"Generated task clean pair observed with gap={observed_gap:.3f}."
                        if usable and observed_gap is not None
                        else "Generated task selected to compare Phase 13 motif behavior against GDPVal clean slice."
                    ),
                }
            ],
            human_or_llm_autopsy_notes=[
                "Generated-task profile is observational with one clean paired comparison."
                if usable
                else "Generated-task profile is observational and pending executed comparison."
            ],
        )

    def _gdpval_eval_status(self, queue_role: str, clean_status: str) -> str:
        if queue_role == "current_clean_seed":
            return "clean_paired_eval"
        if queue_role == "runnability_friction_holdout":
            return "needs_model_rerun"
        if queue_role == "next_gdpval_eval_candidate":
            return "pending_eval"
        return clean_status or "not_evaluated"

    def _runnability_status(self, queue_role: str, autopsy: Dict[str, Any]) -> str:
        if queue_role == "runnability_friction_holdout":
            return "friction_holdout"
        if autopsy.get("usable_for_gap_analysis"):
            return "runnable_clean"
        return "not_yet_measured"

    def _productive_complexity(self, signals: List[str], anatomy: Dict[str, Any]) -> ObservationDimension:
        if signals:
            value = "high" if len(signals) >= 5 else "medium"
            return ObservationDimension(value=value, evidence=signals)
        requirements = [str(item) for item in anatomy.get("reasoning_requirements") or []]
        if requirements:
            return ObservationDimension(value="candidate", evidence=requirements)
        return ObservationDimension(value="unknown", evidence=[])

    def _frictional_complexity(self, signals: List[str], queue_role: str) -> ObservationDimension:
        if queue_role == "runnability_friction_holdout":
            return ObservationDimension(value="high", evidence=signals or ["runnability_friction_holdout"])
        if signals:
            return ObservationDimension(value="medium", evidence=signals)
        return ObservationDimension(value="low_observed", evidence=["No frictional signal in current reports."])

    def _model_separation_quality(self, gap_band: str, evaluation_status: str) -> ObservationDimension:
        if evaluation_status != "clean_paired_eval":
            return ObservationDimension(value="not_observed", evidence=[evaluation_status])
        if gap_band == "high":
            return ObservationDimension(value="high_observed_gap", evidence=["clean paired eval gap >= 0.5"])
        if gap_band == "medium":
            return ObservationDimension(value="medium_observed_gap", evidence=["clean paired eval gap >= 0.15"])
        return ObservationDimension(value="low_observed_gap", evidence=["clean paired eval gap below medium threshold"])

    def _evidence_closure(self, anatomy: Dict[str, Any]) -> ObservationDimension:
        density = str(anatomy.get("evidence_density") or "unknown")
        reference_count = int(anatomy.get("reference_file_count") or 0)
        evidence = [f"evidence_density:{density}", f"reference_file_count:{reference_count}"]
        if density == "high" or reference_count >= 3:
            return ObservationDimension(value="strong_observed", evidence=evidence)
        if density == "medium":
            return ObservationDimension(value="medium_observed", evidence=evidence)
        return ObservationDimension(value="light_observed", evidence=evidence)

    def _workflow_realism(self, anatomy: Dict[str, Any]) -> ObservationDimension:
        features = [str(item) for item in anatomy.get("workflow_realism_features") or []]
        if len(features) >= 4:
            return ObservationDimension(value="high", evidence=features)
        if features:
            return ObservationDimension(value="medium", evidence=features)
        return ObservationDimension(value="unknown", evidence=[])

    def _evaluation_stability(self, evaluation_status: str, autopsy: Dict[str, Any]) -> ObservationDimension:
        if evaluation_status == "clean_paired_eval" and not autopsy.get("grader_bias_suspected"):
            return ObservationDimension(value="clean_single_run", evidence=["Both model sides graded after sanitized regrade."])
        if evaluation_status == "needs_model_rerun":
            return ObservationDimension(value="unstable_needs_rerun", evidence=["At least one model side lacks usable deliverable."])
        return ObservationDimension(value="pending_eval", evidence=[evaluation_status])

    def _format_noise_risk(self, autopsy: Dict[str, Any]) -> ObservationDimension:
        if autopsy.get("format_noise_suspected"):
            return ObservationDimension(value="suspected", evidence=[str(autopsy.get("rubric_gap_category_counts") or {})])
        if autopsy:
            return ObservationDimension(value="not_dominant_observed", evidence=[str(autopsy.get("rubric_gap_category_counts") or {})])
        return ObservationDimension(value="unknown_until_eval", evidence=[])

    def _tool_failure_risk(self, autopsy: Dict[str, Any], queue_role: str) -> ObservationDimension:
        signals = [str(item) for item in autopsy.get("frictional_complexity_signals") or []]
        if queue_role == "runnability_friction_holdout" or autopsy.get("tool_noise_suspected"):
            return ObservationDimension(value="high", evidence=signals)
        if signals:
            return ObservationDimension(value="medium", evidence=signals)
        if autopsy:
            return ObservationDimension(value="low_observed", evidence=["No tool-noise flag in autopsy."])
        return ObservationDimension(value="unknown_until_eval", evidence=[])

    def _generated_reasoning_requirements(self, motif: str) -> List[str]:
        mapping = {
            "evidence_to_deliverable": ["evidence_synthesis", "deliverable_construction"],
            "cross_check_validation": ["cross_check_validation", "reconciliation"],
            "fan_in_reconciliation": ["fan_in_reconciliation", "multi_source_synthesis"],
            "policy_application": ["policy_application", "exception_handling"],
        }
        return mapping.get(motif, [motif] if motif else [])

    def _distribution(self, profiles: List[ObservationalTaskProfile]) -> GoodTaskProfilerDistributionReport:
        return GoodTaskProfilerDistributionReport(
            created_at=self._now(),
            profile_count=len(profiles),
            source_counts=dict(Counter(profile.source for profile in profiles)),
            queue_role_counts=dict(Counter(profile.queue_role for profile in profiles)),
            evaluation_status_counts=dict(Counter(profile.evaluation_status for profile in profiles)),
            deliverable_type_counts=dict(Counter(profile.deliverable_type for profile in profiles)),
            gap_band_counts=dict(Counter(profile.gap_band for profile in profiles)),
            productive_complexity_counts=dict(Counter(profile.productive_complexity.value for profile in profiles)),
            frictional_complexity_counts=dict(Counter(profile.frictional_complexity.value for profile in profiles)),
            format_noise_risk_counts=dict(Counter(profile.format_noise_risk.value for profile in profiles)),
            tool_failure_risk_counts=dict(Counter(profile.tool_failure_risk.value for profile in profiles)),
            notes=[
                "Distribution is observational only.",
                "Generated-task profiles are pending eval and should not be compared as completed gaps yet.",
            ],
        )

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _read_optional_json(self, path: Path) -> Dict[str, Any]:
        if not str(path) or not path.exists():
            return {}
        return self._read_json(path)

    def _read_jsonl_by_id(self, path: Path) -> Dict[str, Dict[str, Any]]:
        values: Dict[str, Dict[str, Any]] = {}
        if not path.exists():
            return values
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            values[str(payload.get("task_id") or "")] = payload
        return values

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _as_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _gap_band(self, gap: Optional[float]) -> str:
        if gap is None:
            return "not_available"
        if gap >= 0.5:
            return "high"
        if gap >= 0.15:
            return "medium"
        return "low"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
