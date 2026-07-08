from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_production_batch_runner import ProductionBatchRunner
from task_generator.v3_source_schema import load_json_file


ExperimentArmId = Literal[
    "baseline_deterministic",
    "generator_reform_only",
    "generator_reform_plus_guarded_llm_candidate",
]
ExperimentArmStatus = Literal["executed", "skipped", "planned_only", "blocked"]


class Phase15AbExperimentRequest(BaseModel):
    experiment_id: str
    registry_path: str
    seed_report_path: str
    workflow_asset_path: Optional[str] = None
    motif_grammar_path: Optional[str] = None
    reform_spec_path: str
    llm_candidate_layer_path: str
    output_dir: str
    target_motif: str = "evidence_to_deliverable"
    max_cases_per_arm: int = 4
    skill_count: int = 4
    model: str = "gpt-5.4-pro"
    workers: int = 1
    rw_task_root: str
    python_exe: str
    execute_baseline: bool = True
    execute_reform_proxy: bool = True


class Phase15ArmSummary(BaseModel):
    arm_id: ExperimentArmId
    arm_status: ExperimentArmStatus
    production_batch_id: str
    manifest_path: Optional[str] = None
    batch_report_path: Optional[str] = None
    candidate_ready_count: int = 0
    completed_case_count: int = 0
    failed_case_count: int = 0
    task_state_counts: Dict[str, int] = Field(default_factory=dict)
    comparable_for_clean_paired_eval: bool = False
    reform_application_status: str = "not_applicable"
    llm_candidate_status: str = "not_applicable"
    reason_codes: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15AbExperimentReport(BaseModel):
    report_version: str = "v3.phase15_ab_experiment.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15AbExperimentRequest
    arms: List[Phase15ArmSummary] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    next_actions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase15AbExperimentRunner:
    """Run and ledger a controlled Phase 15 A/B/C experiment without hidden promotion."""

    def run(self, request: Phase15AbExperimentRequest) -> Phase15AbExperimentReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        reform_spec = load_json_file(request.reform_spec_path)
        candidate_layer = load_json_file(request.llm_candidate_layer_path)
        arms: List[Phase15ArmSummary] = []

        arms.append(self._baseline_arm(request, output_dir) if request.execute_baseline else self._planned_arm(
            request,
            "baseline_deterministic",
            "baseline_not_executed",
        ))
        arms.append(self._reform_proxy_arm(request, output_dir, reform_spec) if request.execute_reform_proxy else self._planned_arm(
            request,
            "generator_reform_only",
            "reform_proxy_not_executed",
        ))
        arms.append(self._llm_candidate_arm(request, output_dir, candidate_layer))

        report = Phase15AbExperimentReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            arms=arms,
            summary=self._summary(arms),
            next_actions=self._next_actions(arms),
            notes=[
                "This experiment runner is report-first and does not promote generator reforms into the default production chain.",
                "The reform-only arm executes the current production chain with an explicit Phase 15 reform-spec experiment flag.",
                "The guarded LLM candidate arm remains blocked unless the candidate layer reports approved candidate roles.",
            ],
        )
        (output_dir / "phase15_ab_experiment_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _baseline_arm(
        self,
        request: Phase15AbExperimentRequest,
        output_dir: Path,
    ) -> Phase15ArmSummary:
        batch_id = f"{request.experiment_id}_baseline"
        artifact = self._run_production_batch(request, output_dir / "baseline_deterministic", batch_id)
        return Phase15ArmSummary(
            arm_id="baseline_deterministic",
            arm_status="executed",
            production_batch_id=batch_id,
            manifest_path=artifact.manifest_path,
            batch_report_path=artifact.batch_report_path,
            candidate_ready_count=artifact.manifest.summary.candidate_ready_count,
            completed_case_count=artifact.manifest.summary.completed_case_count,
            failed_case_count=artifact.manifest.summary.failed_case_count,
            task_state_counts=artifact.manifest.summary.task_state_counts,
            comparable_for_clean_paired_eval=artifact.manifest.summary.candidate_ready_count >= request.max_cases_per_arm,
            reform_application_status="not_applicable_baseline",
            reason_codes=[],
            notes=["Baseline uses the current deterministic production runner without generator reform overlay."],
        )

    def _reform_proxy_arm(
        self,
        request: Phase15AbExperimentRequest,
        output_dir: Path,
        reform_spec: Dict[str, Any],
    ) -> Phase15ArmSummary:
        batch_id = f"{request.experiment_id}_reform_proxy"
        arm_dir = output_dir / "generator_reform_only"
        artifact = self._run_production_batch(request, arm_dir, batch_id, phase15_reform_spec_path=request.reform_spec_path)
        overlay_path = arm_dir / "reform_application_ledger.json"
        deterministic_changes = reform_spec.get("deterministic_changes") or []
        overlay = {
            "ledger_version": "v3.phase15_reform_application_ledger.1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "target_motif": request.target_motif,
            "production_batch_manifest_path": artifact.manifest_path,
            "reform_spec_path": request.reform_spec_path,
            "application_status": "applied_experiment_flag",
            "clean_ab_treatment_ready": artifact.manifest.summary.candidate_ready_count >= request.max_cases_per_arm,
            "deterministic_change_count": len(deterministic_changes),
            "deterministic_changes": [
                {
                    "change_id": change.get("change_id"),
                    "change_type": change.get("change_type"),
                    "application_state": "applied_by_experiment_flag",
                    "required_before_clean_ab_eval": False,
                }
                for change in deterministic_changes
            ],
            "guardrails": reform_spec.get("constraints") or [],
            "notes": [
                "This ledger makes the Phase 15 reform boundary explicit.",
                "The batch artifacts were generated with an explicit Phase 15 reform spec path and should remain isolated from the default chain until promotion review.",
            ],
        }
        overlay_path.write_text(self._json_dumps(overlay), encoding="utf-8")
        return Phase15ArmSummary(
            arm_id="generator_reform_only",
            arm_status="executed",
            production_batch_id=batch_id,
            manifest_path=artifact.manifest_path,
            batch_report_path=artifact.batch_report_path,
            candidate_ready_count=artifact.manifest.summary.candidate_ready_count,
            completed_case_count=artifact.manifest.summary.completed_case_count,
            failed_case_count=artifact.manifest.summary.failed_case_count,
            task_state_counts=artifact.manifest.summary.task_state_counts,
            comparable_for_clean_paired_eval=artifact.manifest.summary.candidate_ready_count >= request.max_cases_per_arm,
            reform_application_status="applied_experiment_flag",
            reason_codes=[],
            notes=[
                f"Reform application ledger written to {overlay_path}.",
                "This arm uses an explicit experiment flag; do not promote the same changes into the default chain without later review.",
            ],
        )

    def _llm_candidate_arm(
        self,
        request: Phase15AbExperimentRequest,
        output_dir: Path,
        candidate_layer: Dict[str, Any],
    ) -> Phase15ArmSummary:
        approved_roles = candidate_layer.get("approved_candidate_roles") or []
        diagnostic_roles = candidate_layer.get("diagnostic_only_roles") or []
        batch_id = f"{request.experiment_id}_llm_candidate"
        if not approved_roles:
            arm_dir = output_dir / "generator_reform_plus_guarded_llm_candidate"
            arm_dir.mkdir(parents=True, exist_ok=True)
            sidecar = {
                "sidecar_version": "v3.phase15_llm_candidate_arm.1",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "arm_status": "blocked",
                "approved_candidate_roles": approved_roles,
                "diagnostic_only_roles": diagnostic_roles,
                "reason_codes": ["no_llm_roles_approved_for_candidate_experiment"],
                "notes": [
                    "LLM candidate arm is intentionally blocked by the adoption gate.",
                    "Diagnostic-only roles may inform review triage but cannot mutate artifacts.",
                ],
            }
            (arm_dir / "llm_candidate_arm_sidecar.json").write_text(
                self._json_dumps(sidecar),
                encoding="utf-8",
            )
            return Phase15ArmSummary(
                arm_id="generator_reform_plus_guarded_llm_candidate",
                arm_status="blocked",
                production_batch_id=batch_id,
                comparable_for_clean_paired_eval=False,
                reform_application_status="blocked_until_reform_clean_ab_ready",
                llm_candidate_status="blocked_no_approved_roles",
                reason_codes=["no_llm_roles_approved_for_candidate_experiment"],
                notes=["No LLM candidate role passed the conservative Phase 15 adoption gate."],
            )

        return Phase15ArmSummary(
            arm_id="generator_reform_plus_guarded_llm_candidate",
            arm_status="planned_only",
            production_batch_id=batch_id,
            comparable_for_clean_paired_eval=False,
            reform_application_status="requires_clean_reform_arm_first",
            llm_candidate_status="approved_roles_present_but_not_executed",
            reason_codes=["one_by_one_llm_execution_required"],
            notes=[
                "Approved candidate roles exist, but this runner does not batch-call LLMs.",
                "Run guarded LLM sidecars one task at a time after the deterministic reform arm is clean.",
            ],
        )

    def _planned_arm(
        self,
        request: Phase15AbExperimentRequest,
        arm_id: ExperimentArmId,
        reason_code: str,
    ) -> Phase15ArmSummary:
        return Phase15ArmSummary(
            arm_id=arm_id,
            arm_status="planned_only",
            production_batch_id=f"{request.experiment_id}_{arm_id}",
            reason_codes=[reason_code],
            notes=["Arm execution was disabled by request."],
        )

    def _run_production_batch(
        self,
        request: Phase15AbExperimentRequest,
        output_dir: Path,
        batch_id: str,
        phase15_reform_spec_path: Optional[str] = None,
    ):
        return ProductionBatchRunner().run(
            production_batch_id=batch_id,
            mode="candidate_run",
            registry_path=request.registry_path,
            seed_report_path=request.seed_report_path,
            workflow_asset_path=request.workflow_asset_path,
            motif_grammar_path=request.motif_grammar_path,
            phase15_reform_spec_path=phase15_reform_spec_path,
            output_dir=output_dir,
            motifs=[request.target_motif],
            skill_count=request.skill_count,
            max_cases=request.max_cases_per_arm,
            model=request.model,
            workers=request.workers,
            rw_task_root=request.rw_task_root,
            python_exe=request.python_exe,
        )

    def _summary(self, arms: List[Phase15ArmSummary]) -> Dict[str, Any]:
        return {
            "arm_count": len(arms),
            "executed_arm_count": sum(1 for arm in arms if arm.arm_status == "executed"),
            "blocked_arm_count": sum(1 for arm in arms if arm.arm_status == "blocked"),
            "clean_paired_eval_ready_arm_count": sum(1 for arm in arms if arm.comparable_for_clean_paired_eval),
            "candidate_ready_by_arm": {
                arm.arm_id: arm.candidate_ready_count
                for arm in arms
            },
            "reason_codes": sorted({code for arm in arms for code in arm.reason_codes}),
        }

    def _next_actions(self, arms: List[Phase15ArmSummary]) -> List[str]:
        reason_codes = {code for arm in arms for code in arm.reason_codes}
        actions = []
        if not any(arm.arm_id == "generator_reform_only" and arm.comparable_for_clean_paired_eval for arm in arms):
            actions.append("Bring the deterministic reform arm to candidate-ready parity before clean A/B/C eval.")
        if "no_llm_roles_approved_for_candidate_experiment" in reason_codes:
            actions.append("Keep LLM candidate arm blocked; use diagnostic-only realism critic signals only if needed for reviewer triage.")
        if any(arm.arm_id == "baseline_deterministic" and arm.candidate_ready_count > 0 for arm in arms):
            actions.append("Use the baseline arm as the Phase 15 regression anchor for later clean reform comparison.")
        return actions

    def _json_dumps(self, payload: Dict[str, Any]) -> str:
        import json

        return json.dumps(payload, ensure_ascii=False, indent=2)
