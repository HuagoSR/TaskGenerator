from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class Phase15BaselineRequest(BaseModel):
    phase14_postmortem_path: str
    good_task_dashboard_path: str
    gdpval_gap_profile_path: str
    generated_task_gap_profile_path: str
    generated_vs_gdpval_gap_path: str
    llm_impact_path: str
    llm_adoption_path: str
    output_dir: str
    handoff_path: str


class Phase15BoundaryLock(BaseModel):
    boundary_id: str
    status: str
    rationale: str


class Phase15BaselineManifest(BaseModel):
    report_version: str = "v3.phase15_baseline_manifest.1"
    created_at: str
    request: Phase15BaselineRequest
    diagnostic_only: bool = True
    phase15_stage: str = "15.0_baseline_and_decision_boundary"
    baseline_status: str
    phase14_decision: str
    phase15_recommendation: str
    evidence_snapshot: Dict[str, Any] = Field(default_factory=dict)
    boundary_locks: List[Phase15BoundaryLock] = Field(default_factory=list)
    p0_work_items: List[Dict[str, Any]] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)
    handoff_path: str
    notes: List[str] = Field(default_factory=list)


class Phase15BaselineBuilder:
    def build(self, request: Phase15BaselineRequest) -> Phase15BaselineManifest:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        postmortem = self._read_json(Path(request.phase14_postmortem_path))
        dashboard = self._read_json(Path(request.good_task_dashboard_path))
        gdpval_gap = self._read_json(Path(request.gdpval_gap_profile_path))
        generated_gap = self._read_json(Path(request.generated_task_gap_profile_path))
        generated_vs_gdpval = self._read_json(Path(request.generated_vs_gdpval_gap_path))
        llm_impact = self._read_json(Path(request.llm_impact_path))
        llm_adoption = self._read_json(Path(request.llm_adoption_path))

        blockers = self._blockers(postmortem, dashboard, gdpval_gap, generated_gap, llm_impact)
        baseline_status = "ready_for_phase15_p0" if not blockers else "blocked_before_phase15_p0"
        manifest = Phase15BaselineManifest(
            created_at=self._now(),
            request=request,
            baseline_status=baseline_status,
            phase14_decision=str(postmortem.get("phase14_decision") or "unknown"),
            phase15_recommendation=str(postmortem.get("phase15_recommendation") or "unknown"),
            evidence_snapshot=self._evidence_snapshot(
                postmortem,
                dashboard,
                gdpval_gap,
                generated_gap,
                generated_vs_gdpval,
                llm_impact,
                llm_adoption,
            ),
            boundary_locks=self._boundary_locks(),
            p0_work_items=self._p0_work_items(generated_gap, llm_impact),
            blockers=blockers,
            next_actions=self._next_actions(blockers),
            handoff_path=str(Path(request.handoff_path)),
            notes=self._notes(),
        )
        self._write_json(output_dir / "phase15_baseline_manifest.json", manifest.model_dump(mode="json"))
        self._write_markdown(Path(request.handoff_path), manifest)
        return manifest

    def _evidence_snapshot(
        self,
        postmortem: Dict[str, Any],
        dashboard: Dict[str, Any],
        gdpval_gap: Dict[str, Any],
        generated_gap: Dict[str, Any],
        generated_vs_gdpval: Dict[str, Any],
        llm_impact: Dict[str, Any],
        llm_adoption: Dict[str, Any],
    ) -> Dict[str, Any]:
        generated_gap_records = generated_gap.get("gap_records") or []
        low_gap_motifs = [
            record.get("motif")
            for record in generated_gap_records
            if record.get("usable_for_gap_analysis") and float(record.get("score_gap") or 0) < 0.15
        ]
        high_gap_motifs = [
            record.get("motif")
            for record in generated_gap_records
            if record.get("usable_for_gap_analysis") and float(record.get("score_gap") or 0) >= 0.5
        ]
        return {
            "phase14": {
                "decision": postmortem.get("phase14_decision"),
                "phase15_recommendation": postmortem.get("phase15_recommendation"),
                "dashboard_blockers": dashboard.get("decision_summary", {}).get("primary_blockers"),
                "weighted_good_task_score_emitted": dashboard.get("weighted_good_task_score_emitted"),
            },
            "gdpval_calibration": {
                "task_count": gdpval_gap.get("task_count"),
                "usable_task_count": gdpval_gap.get("usable_task_count"),
                "score_gap_distribution": gdpval_gap.get("score_gap_distribution"),
                "use": "eval_calibration_only",
                "not_for_training_generation": True,
            },
            "generated_task_clean_pairs": {
                "clean_pair_count": generated_gap.get("clean_pair_count"),
                "blocked_pair_count": generated_gap.get("blocked_pair_count"),
                "gap_records": generated_gap_records,
                "low_gap_motifs": sorted({str(item) for item in low_gap_motifs if item}),
                "high_gap_motifs": sorted({str(item) for item in high_gap_motifs if item}),
                "recommended_first_reform_target": "evidence_to_deliverable",
            },
            "generated_vs_gdpval": {
                "comparison_readiness": generated_vs_gdpval.get("comparison_readiness"),
                "gdpval_gap_bands": generated_vs_gdpval.get("gdpval_gap_bands"),
                "generated_gap_bands": generated_vs_gdpval.get("generated_gap_bands"),
                "not_benchmark_grade": generated_vs_gdpval.get("not_benchmark_grade"),
            },
            "llm_shadow": {
                "shadow_kind_count": llm_impact.get("shadow_kind_count"),
                "total_prepared_task_shadows": llm_impact.get("total_prepared_task_shadows"),
                "total_completed_metric_count": llm_impact.get("total_completed_metric_count"),
                "impact_readiness": llm_impact.get("impact_readiness"),
                "adoption_recommendation": llm_adoption.get("recommendation"),
                "required_next_evidence": llm_adoption.get("required_next_evidence"),
            },
        }

    def _boundary_locks(self) -> List[Phase15BoundaryLock]:
        return [
            Phase15BoundaryLock(
                boundary_id="gdpval_eval_calibration_only",
                status="locked",
                rationale="GDPVal artifacts calibrate task anatomy and model-gap evidence; they must not be rewritten into training tasks.",
            ),
            Phase15BoundaryLock(
                boundary_id="llm_not_primary_truth",
                status="locked",
                rationale="LLM outputs may be reviewed as candidate evidence, critique, or narrative suggestions only.",
            ),
            Phase15BoundaryLock(
                boundary_id="good_task_profiler_observational_only",
                status="locked",
                rationale="Phase 14 evidence is sufficient for diagnosis but not a calibrated weighted GoodTaskScore.",
            ),
            Phase15BoundaryLock(
                boundary_id="production_qa_not_training_value",
                status="locked",
                rationale="Production QA remains necessary for release governance but cannot prove model separation or training value.",
            ),
            Phase15BoundaryLock(
                boundary_id="no_silent_promotion_or_sampler_update",
                status="locked",
                rationale="Generator reforms and LLM candidate roles require explicit promotion or rollback proposals after controlled evidence.",
            ),
        ]

    def _p0_work_items(self, generated_gap: Dict[str, Any], llm_impact: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "phase15_step": "15.1_llm_shadow_review",
                "status": "ready",
                "input_evidence": "20 completed LLM shadow metrics across GoldenRun, rubric, realism critic, and reference narrative.",
                "target_output": "llm_shadow_review_report.json and llm_adoption_gate_report.json",
            },
            {
                "phase15_step": "15.2_generated_task_gap_autopsy",
                "status": "ready" if int(generated_gap.get("clean_pair_count") or 0) >= 4 else "blocked",
                "input_evidence": f"generated_clean_pair_count={generated_gap.get('clean_pair_count')}",
                "target_output": "generated_task_gap_autopsy_report.json",
            },
            {
                "phase15_step": "15.3_gdpval_productive_complexity_pattern_library",
                "status": "ready",
                "input_evidence": "GDPVal clean baseline, anatomy, and gap autopsy are available.",
                "target_output": "gdpval_productive_complexity_pattern_library.json",
            },
            {
                "phase15_step": "15.4_generator_reform_design",
                "status": "ready_after_15.2_and_15.3",
                "input_evidence": "First target is evidence_to_deliverable because it is low-gap in generated clean pairs.",
                "target_output": "evidence_to_deliverable_reform_spec.json",
            },
            {
                "phase15_step": "15.5_guarded_llm_candidate_layer",
                "status": "ready_after_15.1",
                "input_evidence": f"impact_readiness={llm_impact.get('impact_readiness')}",
                "target_output": "llm_candidate_layer_report.json and validation report",
            },
        ]

    def _blockers(
        self,
        postmortem: Dict[str, Any],
        dashboard: Dict[str, Any],
        gdpval_gap: Dict[str, Any],
        generated_gap: Dict[str, Any],
        llm_impact: Dict[str, Any],
    ) -> List[str]:
        blockers: List[str] = []
        if postmortem.get("phase14_decision") != "success":
            blockers.append("phase14_postmortem_not_success")
        if dashboard.get("weighted_good_task_score_emitted") is not False:
            blockers.append("weighted_good_task_score_boundary_not_locked")
        if int(gdpval_gap.get("usable_task_count") or 0) < 8:
            blockers.append("gdpval_clean_pairs_below_phase15_baseline_target_8")
        if int(generated_gap.get("clean_pair_count") or 0) < 4:
            blockers.append("generated_clean_pairs_below_phase15_baseline_target_4")
        if int(llm_impact.get("total_completed_metric_count") or 0) < 20:
            blockers.append("llm_shadow_metrics_below_phase15_baseline_target_20")
        return blockers

    def _next_actions(self, blockers: List[str]) -> List[str]:
        if blockers:
            return [
                "Resolve Phase 15 baseline blockers before enabling generator reform experiments.",
                "Do not start LLM Candidate Mode while baseline evidence is incomplete.",
            ]
        return [
            "Run Phase 15.1 LLM shadow review and adoption gate over the 20 completed shadow outputs.",
            "Run Phase 15.2 generated task gap autopsy for the 4 clean generated task pairs.",
            "Build Phase 15.3 GDPVal productive complexity pattern library.",
            "Use evidence_to_deliverable as the first generator reform target after autopsy and pattern mapping.",
        ]

    def _notes(self) -> List[str]:
        return [
            "This is a baseline freeze; it does not call external LLMs or mutate registries.",
            "External model calls for later Phase 15 steps should be one small experiment at a time.",
            "E2B/rw-task runtime limits should be treated as experiment design constraints, not as model-quality evidence.",
        ]

    def _write_markdown(self, path: Path, manifest: Phase15BaselineManifest) -> None:
        snapshot = manifest.evidence_snapshot
        lines = [
            "# Phase 15 Baseline And Decision Boundary - 2026-07-09",
            "",
            "## Decision",
            "",
            f"- baseline_status: `{manifest.baseline_status}`",
            f"- phase14_decision: `{manifest.phase14_decision}`",
            f"- phase15_recommendation: `{manifest.phase15_recommendation}`",
            "- GDPVal use: `eval_calibration_only`",
            "- weighted GoodTaskScore: disabled",
            "- LLM Candidate Mode: not enabled by default",
            "",
            "## Evidence Snapshot",
            "",
            f"- GDPVal clean usable cases: `{snapshot['gdpval_calibration'].get('usable_task_count')} / {snapshot['gdpval_calibration'].get('task_count')}`",
            f"- GDPVal gap distribution: `{snapshot['gdpval_calibration'].get('score_gap_distribution')}`",
            f"- Generated clean pairs: `{snapshot['generated_task_clean_pairs'].get('clean_pair_count')}`",
            f"- Generated gap bands: `{snapshot['generated_vs_gdpval'].get('generated_gap_bands')}`",
            f"- LLM shadow metrics: `{snapshot['llm_shadow'].get('total_completed_metric_count')} / {snapshot['llm_shadow'].get('total_prepared_task_shadows')}`",
            f"- LLM adoption recommendation: `{snapshot['llm_shadow'].get('adoption_recommendation')}`",
            f"- First reform target: `{snapshot['generated_task_clean_pairs'].get('recommended_first_reform_target')}`",
            "",
            "## Boundary Locks",
            "",
        ]
        for lock in manifest.boundary_locks:
            lines.append(f"- `{lock.boundary_id}`: `{lock.status}` - {lock.rationale}")
        lines.extend(["", "## P0 Work Items", ""])
        for item in manifest.p0_work_items:
            lines.append(f"- `{item['phase15_step']}`: `{item['status']}` - {item['target_output']}")
        lines.extend(["", "## Blockers", ""])
        if manifest.blockers:
            for blocker in manifest.blockers:
                lines.append(f"- `{blocker}`")
        else:
            lines.append("- None.")
        lines.extend(["", "## Next Actions", ""])
        for action in manifest.next_actions:
            lines.append(f"- {action}")
        lines.extend(["", "## Notes", ""])
        for note in manifest.notes:
            lines.append(f"- {note}")
        lines.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
