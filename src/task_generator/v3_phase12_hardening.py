from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_global_pipeline_dashboard import (
    GlobalPipelineDashboardBuilder,
    GlobalPipelineDashboardReport,
)
from task_generator.v3_pipeline_a_substrate_audit import PipelineASubstrateAuditor
from task_generator.v3_pipeline_b_batch_feedback_analyzer import (
    PipelineBBatchFeedbackAnalyzer,
    PipelineBBatchFeedbackReport,
)
from task_generator.v3_pipeline_b_batch_runner import PipelineBBatchRunReport, PipelineBBatchRunner
from task_generator.v3_phase12_substrate_hardening import Phase12SubstrateHardener
from task_generator.v3_phase12_workflow_context import Phase12WorkflowContextStrengthener
from task_generator.v3_rw_task_export_validator import RwTaskExportValidator
from task_generator.v3_source_schema import load_json_file
from task_generator.v3_task_verifier import TaskVerifier
from task_generator.v3_transition_prior_store import TransitionPriorStoreBuilder
from task_generator.v3_typed_resource_patch_proposal import TypedResourcePatchProposalBuilder


NegativeControlStatus = Literal["pass", "fail"]


class Phase12HardeningRequest(BaseModel):
    phase11_regression_report_path: str
    registry_path: str
    seed_report_path: str
    readiness_report_path: str
    transition_graph_report_path: str
    composition_readiness_report_path: str
    output_root: str
    max_cases: int = 5
    allow_caution: bool = False
    motif_grammar_path: Optional[str] = None
    model: str = "gpt-5.4-pro"
    workers: int = 1
    rw_task_root: str
    python_exe: str
    max_apply_count: int = 3


class Phase12BaselineReport(BaseModel):
    phase12_baseline_version: str = "v1"
    report_date: str
    source_phase11_regression_report_path: str
    baseline_batch_report_path: str
    baseline_batch_feedback_report_path: str
    baseline_dashboard_report_path: str
    baseline_case_count: int = 0
    baseline_candidate_ready_count: int = 0
    baseline_verifier_pass_count: int = 0
    notes: List[str] = Field(default_factory=list)


class Phase12RegressionSummary(BaseModel):
    case_count: int = 0
    candidate_ready_count: int = 0
    revise_count: int = 0
    reject_count: int = 0
    verifier_pass_count: int = 0
    verifier_blocking_case_count: int = 0
    exported_count: int = 0
    candidate_ready_compatible_count: int = 0
    subgraph_confidence_counts: Dict[str, int] = Field(default_factory=dict)
    workflow_context_fit_counts: Dict[str, int] = Field(default_factory=dict)
    repeated_reason_codes: List[str] = Field(default_factory=list)


class Phase12RegressionReport(BaseModel):
    phase12_regression_version: str = "v1"
    report_date: str
    batch_report_path: str
    batch_feedback_report_path: str
    substrate_audit_report_path: str
    typed_resource_patch_proposal_report_path: str
    dashboard_report_path: str
    max_cases: int = 5
    summary: Phase12RegressionSummary
    acceptance_checks: Dict[str, bool] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class Phase12DashboardDiffReport(BaseModel):
    phase12_dashboard_diff_version: str = "v1"
    report_date: str
    baseline_dashboard_report_path: str
    current_dashboard_report_path: str
    deltas: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class Phase12NegativeControlResult(BaseModel):
    fault_id: str
    mutation_applied: bool = False
    expected_detection_layer: str
    actual_detection_layer: str = "none"
    expected_status: str
    actual_status: str = "pass"
    passed_negative_control: bool = False
    detected_reason_codes: List[str] = Field(default_factory=list)
    output_paths: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class Phase12NegativeControlReport(BaseModel):
    phase12_negative_control_version: str = "v1"
    report_date: str
    source_case_id: str
    source_case_dir: str
    result_count: int = 0
    passed_count: int = 0
    results: List[Phase12NegativeControlResult] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Phase12HardeningReport(BaseModel):
    phase12_hardening_version: str = "v1"
    request: Phase12HardeningRequest
    baseline_report_path: str
    baseline_handoff_path: str
    regression_report_path: str
    dashboard_diff_report_path: str
    negative_control_report_path: str
    substrate_hardening_report_path: str
    workflow_context_review_report_path: str
    transition_prior_report_path: str
    transition_prior_store_path: str
    notes: List[str] = Field(default_factory=list)


class Phase12HardeningRunner:
    def run(
        self,
        phase11_regression_report_path: str | Path,
        registry_path: str | Path,
        seed_report_path: str | Path,
        readiness_report_path: str | Path,
        transition_graph_report_path: str | Path,
        composition_readiness_report_path: str | Path,
        output_root: str | Path,
        max_cases: int = 5,
        allow_caution: bool = False,
        motif_grammar_path: Optional[str | Path] = None,
        model: str = "gpt-5.4-pro",
        workers: int = 1,
        rw_task_root: str | Path = Path(r"E:\THU\2026Spring\SRT\rw-task"),
        python_exe: str | Path = Path(r"D:\miniconda3\envs\real-world-task\python.exe"),
        handoff_dir: Optional[str | Path] = None,
        max_apply_count: int = 3,
    ) -> Phase12HardeningReport:
        output_root_path = Path(output_root)
        output_root_path.mkdir(parents=True, exist_ok=True)
        handoff_root = (
            Path(handoff_dir)
            if handoff_dir
            else Path("artifacts") / "historical_phase_runs" / "phase12" / "handoffs"
        )
        handoff_root.mkdir(parents=True, exist_ok=True)

        request = Phase12HardeningRequest(
            phase11_regression_report_path=str(phase11_regression_report_path),
            registry_path=str(registry_path),
            seed_report_path=str(seed_report_path),
            readiness_report_path=str(readiness_report_path),
            transition_graph_report_path=str(transition_graph_report_path),
            composition_readiness_report_path=str(composition_readiness_report_path),
            output_root=str(output_root_path),
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=str(motif_grammar_path) if motif_grammar_path else None,
            model=model,
            workers=workers,
            rw_task_root=str(rw_task_root),
            python_exe=str(python_exe),
            max_apply_count=max_apply_count,
        )

        baseline_dir = output_root_path / "phase_12_baseline"
        baseline_report, baseline_handoff_path = self._freeze_baseline(
            phase11_regression_report_path=phase11_regression_report_path,
            output_dir=baseline_dir,
            handoff_dir=handoff_root,
        )
        baseline_report_path = baseline_dir / "phase12_baseline_report.json"

        regression = self._run_regression(
            registry_path=registry_path,
            seed_report_path=seed_report_path,
            readiness_report_path=readiness_report_path,
            transition_graph_report_path=transition_graph_report_path,
            composition_readiness_report_path=composition_readiness_report_path,
            output_root=output_root_path,
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=motif_grammar_path,
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
        )
        regression_report_path = output_root_path / "phase12_candidate_ready_regression_report.json"

        dashboard_diff = self._build_dashboard_diff(
            baseline_dashboard_report_path=baseline_report.baseline_dashboard_report_path,
            current_dashboard_report_path=regression.dashboard_report_path,
            output_path=output_root_path / "phase12_dashboard_diff_report.json",
        )

        substrate = Phase12SubstrateHardener().run(
            substrate_audit_report_path=regression.substrate_audit_report_path,
            typed_resource_patch_proposals_path=output_root_path
            / f"phase12_regression_{max_cases}case_typed_resource_review"
            / "typed_resource_patch_proposals.json",
            typed_resource_patch_proposal_report_path=regression.typed_resource_patch_proposal_report_path,
            registry_path=registry_path,
            seed_report_path=seed_report_path,
            readiness_report_path=readiness_report_path,
            transition_graph_report_path=transition_graph_report_path,
            composition_readiness_report_path=composition_readiness_report_path,
            output_dir=output_root_path / "phase12_substrate_hardening",
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=motif_grammar_path,
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
            max_apply_count=max_apply_count,
        )

        workflow = Phase12WorkflowContextStrengthener().run(
            batch_report_path=substrate.post_batch_report_path,
            dashboard_report_path=substrate.post_dashboard_report_path,
            registry_path=substrate.scratch_registry_path,
            seed_report_path=seed_report_path,
            readiness_report_path=readiness_report_path,
            transition_graph_report_path=transition_graph_report_path,
            composition_readiness_report_path=composition_readiness_report_path,
            output_dir=output_root_path / "phase12_workflow_context",
            max_cases=max_cases,
            allow_caution=allow_caution,
            base_motif_grammar_path=motif_grammar_path
            or Path("SkillRegistry") / "v3_motif_graph_grammar.experimental.json",
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
        )

        transition_prior_store_path = Path("SkillRegistry") / "v3_transition_prior_store.observed.json"
        transition_prior_report_path = output_root_path / "phase12_transition_prior_observation_report.json"
        TransitionPriorStoreBuilder().build(
            batch_report_path=workflow.strengthened_batch_report_path,
            store_output_path=transition_prior_store_path,
            report_output_path=transition_prior_report_path,
        )

        negative_control = self._run_negative_controls(
            source_batch_report_path=regression.batch_report_path,
            fallback_batch_report_path=baseline_report.baseline_batch_report_path,
            output_dir=output_root_path / "phase12_fault_injection",
        )
        negative_control_report_path = output_root_path / "phase12_negative_control_report.json"

        report = Phase12HardeningReport(
            request=request,
            baseline_report_path=str(baseline_report_path),
            baseline_handoff_path=str(baseline_handoff_path),
            regression_report_path=str(regression_report_path),
            dashboard_diff_report_path=str(output_root_path / "phase12_dashboard_diff_report.json"),
            negative_control_report_path=str(negative_control_report_path),
            substrate_hardening_report_path=str(
                output_root_path / "phase12_substrate_hardening" / "phase12_substrate_audit_report.json"
            ),
            workflow_context_review_report_path=str(
                output_root_path / "phase12_workflow_context" / "phase12_workflow_context_review_report.json"
            ),
            transition_prior_report_path=str(transition_prior_report_path),
            transition_prior_store_path=str(transition_prior_store_path),
            notes=[
                "Phase 12 hardening now covers baseline freeze, deterministic regression expansion, dashboard diffing, negative controls, substrate hardening, workflow-context strengthening, and TransitionPriorStore V0 observations.",
                "Further Phase 12 work is still required for the guarded executed-eval mini-campaign and final hardening postmortem.",
            ],
        )
        (output_root_path / "phase12_hardening_report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        return report

    def _freeze_baseline(
        self,
        phase11_regression_report_path: str | Path,
        output_dir: Path,
        handoff_dir: Path,
    ) -> tuple[Phase12BaselineReport, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = load_json_file(str(phase11_regression_report_path))
        final_reference = payload.get("final_reference") or {}
        batch_report_path = str(final_reference.get("batch_report_path") or "")
        batch_feedback_report_path = str(final_reference.get("batch_feedback_report_path") or "")
        dashboard_report_path = str(final_reference.get("dashboard_report_path") or "")

        batch_report = PipelineBBatchRunReport.model_validate(load_json_file(batch_report_path))
        baseline = Phase12BaselineReport(
            report_date=date.today().isoformat(),
            source_phase11_regression_report_path=str(phase11_regression_report_path),
            baseline_batch_report_path=batch_report_path,
            baseline_batch_feedback_report_path=batch_feedback_report_path,
            baseline_dashboard_report_path=dashboard_report_path,
            baseline_case_count=batch_report.diagnostics.case_count,
            baseline_candidate_ready_count=batch_report.diagnostics.quality_decision_counts.get(
                "candidate_ready", 0
            ),
            baseline_verifier_pass_count=batch_report.diagnostics.verifier_status_counts.get("pass", 0),
            notes=[
                "This baseline freezes the final Phase 11 candidate-ready regression as the Phase 12 comparison anchor.",
                ".env remains local-only and must not enter staged files, reports, or handoff examples.",
            ],
        )
        baseline_path = output_dir / "phase12_baseline_report.json"
        baseline_path.write_text(baseline.model_dump_json(indent=2), encoding="utf-8")

        handoff_path = handoff_dir / f"PHASE_12_BASELINE_{date.today().isoformat()}.md"
        handoff_text = self._baseline_handoff_markdown(baseline)
        handoff_path.write_text(handoff_text, encoding="utf-8")
        return baseline, handoff_path

    def _run_regression(
        self,
        registry_path: str | Path,
        seed_report_path: str | Path,
        readiness_report_path: str | Path,
        transition_graph_report_path: str | Path,
        composition_readiness_report_path: str | Path,
        output_root: Path,
        max_cases: int,
        allow_caution: bool,
        motif_grammar_path: Optional[str | Path],
        model: str,
        workers: int,
        rw_task_root: str | Path,
        python_exe: str | Path,
    ) -> Phase12RegressionReport:
        batch_dir = output_root / f"phase12_regression_{max_cases}case"
        feedback_dir = output_root / f"phase12_regression_{max_cases}case_feedback"
        substrate_dir = output_root / f"phase12_regression_{max_cases}case_substrate"
        typed_patch_dir = output_root / f"phase12_regression_{max_cases}case_typed_resource_review"
        dashboard_dir = output_root / f"phase12_regression_{max_cases}case_dashboard"

        batch_report = PipelineBBatchRunner().run(
            registry_path=registry_path,
            seed_report_path=seed_report_path,
            output_dir=batch_dir,
            max_cases=max_cases,
            allow_caution=allow_caution,
            motif_grammar_path=motif_grammar_path,
            model=model,
            workers=workers,
            rw_task_root=rw_task_root,
            python_exe=python_exe,
        )
        batch_report_path = batch_dir / "pipeline_b_batch_report.json"

        batch_feedback = PipelineBBatchFeedbackAnalyzer().analyze(
            batch_report_path=batch_report_path,
            output_dir=feedback_dir,
        )
        batch_feedback_path = feedback_dir / "pipeline_b_batch_feedback_report.json"

        substrate_report = PipelineASubstrateAuditor().audit(
            batch_feedback_report_path=batch_feedback_path,
            batch_report_path=batch_report_path,
            registry_path=registry_path,
            readiness_report_path=readiness_report_path,
            transition_graph_report_path=transition_graph_report_path,
            composition_readiness_report_path=composition_readiness_report_path,
            output_dir=substrate_dir,
        )
        substrate_report_path = substrate_dir / "pipeline_a_substrate_audit_report.json"

        typed_patch_report = TypedResourcePatchProposalBuilder().build(
            substrate_audit_report_path=substrate_report_path,
            output_dir=typed_patch_dir,
            include_low_confidence=True,
        )
        typed_patch_report_path = typed_patch_dir / "typed_resource_patch_proposal_report.json"

        dashboard = GlobalPipelineDashboardBuilder().build(
            batch_report_path=batch_report_path,
            batch_feedback_report_path=batch_feedback_path,
            substrate_audit_report_path=substrate_report_path,
            typed_resource_patch_proposal_report_path=typed_patch_report_path,
            output_dir=dashboard_dir,
        )
        dashboard_path = dashboard_dir / "global_pipeline_dashboard_report.json"

        summary = Phase12RegressionSummary(
            case_count=batch_report.diagnostics.case_count,
            candidate_ready_count=batch_report.diagnostics.quality_decision_counts.get("candidate_ready", 0),
            revise_count=batch_report.diagnostics.quality_decision_counts.get("revise", 0),
            reject_count=batch_report.diagnostics.quality_decision_counts.get("reject", 0),
            verifier_pass_count=batch_report.diagnostics.verifier_status_counts.get("pass", 0),
            verifier_blocking_case_count=batch_report.diagnostics.verifier_blocking_case_count,
            exported_count=sum(1 for case in batch_report.cases if case.export_decision == "exported"),
            candidate_ready_compatible_count=sum(
                1 for case in batch_report.cases if case.validation_status == "candidate_ready_compatible"
            ),
            subgraph_confidence_counts=batch_report.diagnostics.subgraph_confidence_counts,
            workflow_context_fit_counts=batch_report.diagnostics.workflow_context_fit_counts,
            repeated_reason_codes=batch_report.diagnostics.repeated_reason_codes,
        )
        acceptance_checks = self._acceptance_checks(summary=summary, max_cases=max_cases)
        report = Phase12RegressionReport(
            report_date=date.today().isoformat(),
            batch_report_path=str(batch_report_path),
            batch_feedback_report_path=str(batch_feedback_path),
            substrate_audit_report_path=str(substrate_report_path),
            typed_resource_patch_proposal_report_path=str(typed_patch_report_path),
            dashboard_report_path=str(dashboard_path),
            max_cases=max_cases,
            summary=summary,
            acceptance_checks=acceptance_checks,
            notes=[
                "This regression uses the deterministic Pipeline B batch runner and keeps quality/verifier/export logic unchanged.",
                "Typed-resource review is included as dashboard evidence only; no promotion apply happens in this step.",
            ],
        )
        (output_root / "phase12_candidate_ready_regression_report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        return report

    def _acceptance_checks(
        self,
        summary: Phase12RegressionSummary,
        max_cases: int,
    ) -> Dict[str, bool]:
        if max_cases >= 10:
            return {
                "candidate_ready_at_least_7": summary.candidate_ready_count >= 7,
                "verifier_pass_at_least_8": summary.verifier_pass_count >= 8,
                "reject_at_most_1": summary.reject_count <= 1,
            }
        if max_cases >= 5:
            return {
                "candidate_ready_at_least_4": summary.candidate_ready_count >= 4,
                "verifier_pass_at_least_4": summary.verifier_pass_count >= 4,
                "reject_equals_0": summary.reject_count == 0,
            }
        return {}

    def _build_dashboard_diff(
        self,
        baseline_dashboard_report_path: str | Path,
        current_dashboard_report_path: str | Path,
        output_path: Path,
    ) -> Phase12DashboardDiffReport:
        baseline = GlobalPipelineDashboardReport.model_validate(load_json_file(str(baseline_dashboard_report_path)))
        current = GlobalPipelineDashboardReport.model_validate(load_json_file(str(current_dashboard_report_path)))

        baseline_train = baseline.health_summary.training_evaluation_readiness
        current_train = current.health_summary.training_evaluation_readiness
        baseline_exec = baseline.health_summary.task_executability_health
        current_exec = current.health_summary.task_executability_health
        deltas = {
            "candidate_ready_count": {
                "before": baseline_train.candidate_ready_count,
                "after": current_train.candidate_ready_count,
                "delta": current_train.candidate_ready_count - baseline_train.candidate_ready_count,
            },
            "revise_only_count": {
                "before": baseline_train.revise_only_count,
                "after": current_train.revise_only_count,
                "delta": current_train.revise_only_count - baseline_train.revise_only_count,
            },
            "verifier_pass_count": {
                "before": baseline_train.verifier_pass_count,
                "after": current_train.verifier_pass_count,
                "delta": current_train.verifier_pass_count - baseline_train.verifier_pass_count,
            },
            "verifier_blocking_case_count": {
                "before": baseline_exec.verifier_blocking_case_count,
                "after": current_exec.verifier_blocking_case_count,
                "delta": current_exec.verifier_blocking_case_count - baseline_exec.verifier_blocking_case_count,
            },
            "usable_eval_evidence_case_count": {
                "before": baseline_train.usable_eval_evidence_case_count,
                "after": current_train.usable_eval_evidence_case_count,
                "delta": current_train.usable_eval_evidence_case_count
                - baseline_train.usable_eval_evidence_case_count,
            },
        }
        report = Phase12DashboardDiffReport(
            report_date=date.today().isoformat(),
            baseline_dashboard_report_path=str(baseline_dashboard_report_path),
            current_dashboard_report_path=str(current_dashboard_report_path),
            deltas=deltas,
            notes=[
                "This diff is intentionally narrow and compares a few high-signal dashboard metrics.",
                "Phase 12 should use this as one comparison anchor, not as a substitute for case-level inspection.",
            ],
        )
        output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report

    def _run_negative_controls(
        self,
        source_batch_report_path: str | Path,
        fallback_batch_report_path: str | Path,
        output_dir: Path,
    ) -> Phase12NegativeControlReport:
        output_dir.mkdir(parents=True, exist_ok=True)
        source_case = self._select_candidate_ready_case(source_batch_report_path)
        if source_case is None:
            source_case = self._select_candidate_ready_case(fallback_batch_report_path)
        if source_case is None:
            report = Phase12NegativeControlReport(
                report_date=date.today().isoformat(),
                source_case_id="unknown",
                source_case_dir="",
                result_count=0,
                passed_count=0,
                notes=["No candidate_ready case was available for Phase 12 fault injection."],
            )
            (output_dir.parent / "phase12_negative_control_report.json").write_text(
                report.model_dump_json(indent=2), encoding="utf-8"
            )
            return report

        results = [
            self._fault_missing_evidence_id(source_case.case_dir, output_dir / "missing_evidence_id"),
            self._fault_invalid_evidence_id(source_case.case_dir, output_dir / "invalid_evidence_id"),
            self._fault_missing_policy_clause(source_case.case_dir, output_dir / "missing_policy_clause"),
            self._fault_broken_reference_column(source_case.case_dir, output_dir / "broken_reference_column"),
            self._fault_hidden_artifact_exposure(source_case.case_dir, output_dir / "hidden_artifact_exposure"),
            self._fault_deliverable_rubric_gap(source_case.case_dir, output_dir / "deliverable_rubric_gap"),
            self._fault_cyclic_execution_plan(source_case.case_dir, output_dir / "cyclic_execution_plan"),
        ]
        report = Phase12NegativeControlReport(
            report_date=date.today().isoformat(),
            source_case_id=source_case.case_id,
            source_case_dir=source_case.case_dir,
            result_count=len(results),
            passed_count=sum(1 for item in results if item.passed_negative_control),
            results=results,
            notes=[
                "Negative controls use mutated copies of a candidate_ready case; source artifacts are not modified.",
                "Current detection may land in task_verifier or export_validator depending on which structural contract is violated.",
            ],
        )
        (output_dir.parent / "phase12_negative_control_report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        return report

    def _select_candidate_ready_case(self, batch_report_path: str | Path) -> Optional[Any]:
        batch_report = PipelineBBatchRunReport.model_validate(load_json_file(str(batch_report_path)))
        for case in batch_report.cases:
            if case.quality_decision == "candidate_ready" and case.verifier_status == "pass":
                return case
        return None

    def _fault_missing_evidence_id(self, source_case_dir: str, output_dir: Path) -> Phase12NegativeControlResult:
        case_dir = self._copy_case(source_case_dir, output_dir)
        golden_path = case_dir / "teacher_runner" / "golden_run.json"
        golden = load_json_file(str(golden_path))
        for step in golden.get("steps") or []:
            if step.get("status") == "complete":
                step["evidence_uses"] = []
                break
        self._write_json(golden_path, golden)
        verifier = self._rerun_verifier(case_dir, output_dir / "task_verifier")
        return self._negative_control_result(
            fault_id="missing_evidence_id",
            expected_detection_layer="task_verifier",
            expected_status="blocking",
            verifier_report=verifier,
            output_paths={"task_verifier_report_path": str(output_dir / "task_verifier" / "task_verifier_report.json")},
            notes=["Cleared evidence_uses for one complete step to trigger unsupported_complete_step."],
        )

    def _fault_invalid_evidence_id(self, source_case_dir: str, output_dir: Path) -> Phase12NegativeControlResult:
        case_dir = self._copy_case(source_case_dir, output_dir)
        golden_path = case_dir / "teacher_runner" / "golden_run.json"
        golden = load_json_file(str(golden_path))
        mutated = False
        for step in golden.get("steps") or []:
            uses = step.get("evidence_uses") or []
            if uses:
                uses[0]["evidence_id"] = "ev_phase12_missing_reference"
                mutated = True
                break
        self._write_json(golden_path, golden)
        verifier = self._rerun_verifier(case_dir, output_dir / "task_verifier")
        notes = ["Replaced one used evidence_id with a non-declared value."] if mutated else ["No evidence use was available to mutate."]
        return self._negative_control_result(
            fault_id="invalid_evidence_id",
            expected_detection_layer="task_verifier",
            expected_status="blocking",
            verifier_report=verifier,
            output_paths={"task_verifier_report_path": str(output_dir / "task_verifier" / "task_verifier_report.json")},
            notes=notes,
        )

    def _fault_missing_policy_clause(self, source_case_dir: str, output_dir: Path) -> Phase12NegativeControlResult:
        case_dir = self._copy_case(source_case_dir, output_dir)
        teacher_path = case_dir / "teacher_input" / "teacher_input_manifest.json"
        teacher = load_json_file(str(teacher_path))
        teacher["candidate_view"]["reference_files"] = [
            item
            for item in (teacher.get("candidate_view") or {}).get("reference_files") or []
            if item.get("file_name") != "policy_reference.docx"
        ]
        self._write_json(teacher_path, teacher)
        verifier = self._rerun_verifier(case_dir, output_dir / "task_verifier")
        return self._negative_control_result(
            fault_id="missing_policy_clause",
            expected_detection_layer="task_verifier",
            expected_status="blocking",
            verifier_report=verifier,
            output_paths={"task_verifier_report_path": str(output_dir / "task_verifier" / "task_verifier_report.json")},
            notes=["Removed policy_reference.docx from candidate-visible reference files."],
        )

    def _fault_broken_reference_column(self, source_case_dir: str, output_dir: Path) -> Phase12NegativeControlResult:
        case_dir = self._copy_case(source_case_dir, output_dir)
        export_case_dir = case_dir / "rw_task_export"
        workbook_path = export_case_dir / "reference_files" / "source_evidence.xlsx"
        if workbook_path.exists():
            workbook_path.unlink()
        validation = RwTaskExportValidator().validate(
            case_dir=export_case_dir,
            output_path=output_dir / "rw_task_export_validation_report.json",
        )
        return self._negative_control_result(
            fault_id="broken_reference_column",
            expected_detection_layer="export_validator",
            expected_status="invalid",
            export_report=validation.model_dump(),
            output_paths={"rw_task_export_validation_report_path": str(output_dir / "rw_task_export_validation_report.json")},
            notes=["Deleted the exported workbook to simulate a broken candidate-visible reference dependency."],
        )

    def _fault_hidden_artifact_exposure(self, source_case_dir: str, output_dir: Path) -> Phase12NegativeControlResult:
        case_dir = self._copy_case(source_case_dir, output_dir)
        export_case_dir = case_dir / "rw_task_export"
        support_dir = export_case_dir / "artifacts" / "reference_support"
        support_dir.mkdir(parents=True, exist_ok=True)
        hidden_name = "teacher_only_phase12.txt"
        hidden_path = support_dir / hidden_name
        hidden_path.write_text("teacher-only support artifact", encoding="utf-8")
        dataset_row_path = export_case_dir / "dataset_row.json"
        dataset_row = load_json_file(str(dataset_row_path))
        references = list(dataset_row.get("reference_files") or [])
        references.append(f"reference_files\\{hidden_name}")
        dataset_row["reference_files"] = references
        candidate_copy = export_case_dir / "reference_files" / hidden_name
        candidate_copy.write_text("exposed support artifact", encoding="utf-8")
        self._write_json(dataset_row_path, dataset_row)
        validation = RwTaskExportValidator().validate(
            case_dir=export_case_dir,
            output_path=output_dir / "rw_task_export_validation_report.json",
        )
        return self._negative_control_result(
            fault_id="hidden_artifact_exposure",
            expected_detection_layer="export_validator",
            expected_status="invalid",
            export_report=validation.model_dump(),
            output_paths={"rw_task_export_validation_report_path": str(output_dir / "rw_task_export_validation_report.json")},
            notes=["Exposed a support artifact through candidate-visible reference_files."],
        )

    def _fault_deliverable_rubric_gap(self, source_case_dir: str, output_dir: Path) -> Phase12NegativeControlResult:
        case_dir = self._copy_case(source_case_dir, output_dir)
        rubric_path = case_dir / "rubric" / "rubric.json"
        rubric = load_json_file(str(rubric_path))
        sections = list(rubric.get("sections") or [])
        for section in sections:
            criteria = list(section.get("criteria") or [])
            section["criteria"] = [
                item
                for item in criteria
                if "summarize the evidence reviewed" not in ((item.get("description") or "").lower())
            ]
        rubric["sections"] = sections
        self._write_json(rubric_path, rubric)
        verifier = self._rerun_verifier(case_dir, output_dir / "task_verifier")
        return self._negative_control_result(
            fault_id="deliverable_rubric_gap",
            expected_detection_layer="task_verifier",
            expected_status="revise",
            verifier_report=verifier,
            output_paths={"task_verifier_report_path": str(output_dir / "task_verifier" / "task_verifier_report.json")},
            notes=["Removed one deliverable-alignment phrasing from rubric criteria to provoke undercoverage."],
        )

    def _fault_cyclic_execution_plan(self, source_case_dir: str, output_dir: Path) -> Phase12NegativeControlResult:
        case_dir = self._copy_case(source_case_dir, output_dir)
        dag_path = case_dir / "global_validity" / "execution_plan_dag_report.json"
        dag = load_json_file(str(dag_path))
        stages = list(dag.get("stages") or [])
        if len(stages) >= 2:
            first_id = stages[0].get("stage_id")
            last = stages[-1]
            deps = list(last.get("depends_on") or [])
            if first_id and first_id not in deps:
                deps.append(first_id)
            stages[0]["depends_on"] = [last.get("stage_id")]
            last["depends_on"] = deps
        dag["stages"] = stages
        dag["dag_valid"] = False
        dag["topological_order"] = []
        dag["validation_notes"] = list(dag.get("validation_notes") or []) + [
            "Phase 12 injected cycle for negative-control verification."
        ]
        self._write_json(dag_path, dag)
        verifier = self._rerun_verifier(case_dir, output_dir / "task_verifier")
        return self._negative_control_result(
            fault_id="cyclic_execution_plan",
            expected_detection_layer="task_verifier",
            expected_status="blocking",
            verifier_report=verifier,
            output_paths={"task_verifier_report_path": str(output_dir / "task_verifier" / "task_verifier_report.json")},
            notes=["Injected a cycle into execution_plan_dag_report.json and marked dag_valid=false."],
        )

    def _negative_control_result(
        self,
        fault_id: str,
        expected_detection_layer: str,
        expected_status: str,
        verifier_report: Optional[Dict[str, Any]] = None,
        export_report: Optional[Dict[str, Any]] = None,
        output_paths: Optional[Dict[str, str]] = None,
        notes: Optional[List[str]] = None,
    ) -> Phase12NegativeControlResult:
        actual_detection_layer = "none"
        actual_status = "pass"
        reason_codes: List[str] = []
        if verifier_report:
            diagnostics = verifier_report.get("diagnostics") or {}
            actual_status = str(verifier_report.get("verifier_status") or "pass")
            reason_codes = list(diagnostics.get("reason_codes") or [])
            if actual_status != "pass":
                actual_detection_layer = "task_verifier"
        if export_report:
            export_status = export_report.get("validation_status") or "pass"
            actual_status = str(export_status)
            findings = export_report.get("findings") or []
            reason_codes = [
                str(item.get("check_name"))
                for item in findings
                if item.get("severity") == "blocking" and not item.get("passed")
            ]
            if export_status != "candidate_ready_compatible":
                actual_detection_layer = "export_validator"
        passed = actual_detection_layer == expected_detection_layer and actual_status == expected_status
        return Phase12NegativeControlResult(
            fault_id=fault_id,
            mutation_applied=True,
            expected_detection_layer=expected_detection_layer,
            actual_detection_layer=actual_detection_layer,
            expected_status=expected_status,
            actual_status=actual_status,
            passed_negative_control=passed,
            detected_reason_codes=reason_codes,
            output_paths=output_paths or {},
            notes=notes or [],
        )

    def _rerun_verifier(self, case_dir: Path, output_dir: Path) -> Dict[str, Any]:
        report = TaskVerifier().build(
            blueprint_path=case_dir / "prototype" / "draft_task_blueprint.json",
            teacher_input_manifest_path=case_dir / "teacher_input" / "teacher_input_manifest.json",
            golden_run_path=case_dir / "teacher_runner" / "golden_run.json",
            rubric_path=case_dir / "rubric" / "rubric.json",
            task_constraint_graph_report_path=case_dir / "global_validity" / "task_constraint_graph_report.json",
            execution_plan_dag_report_path=case_dir / "global_validity" / "execution_plan_dag_report.json",
            quality_report_path=case_dir / "quality_gate" / "pipeline_b_quality_report.json",
            output_dir=output_dir,
        )
        TaskVerifier().write_outputs(report, output_dir)
        return report.model_dump()

    def _copy_case(self, source_case_dir: str, output_dir: Path) -> Path:
        if output_dir.exists():
            shutil.rmtree(output_dir)
        shutil.copytree(source_case_dir, output_dir)
        return output_dir

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _baseline_handoff_markdown(self, baseline: Phase12BaselineReport) -> str:
        return "\n".join(
            [
                f"# Phase 12 Baseline - {baseline.report_date}",
                "",
                "## Anchor",
                "",
                "Phase 12 starts from the final Phase 11 deterministic regression baseline.",
                "",
                f"- baseline batch report: `{baseline.baseline_batch_report_path}`",
                f"- baseline batch feedback report: `{baseline.baseline_batch_feedback_report_path}`",
                f"- baseline dashboard report: `{baseline.baseline_dashboard_report_path}`",
                "",
                "## Confirmed baseline counts",
                "",
                f"- case_count = {baseline.baseline_case_count}",
                f"- candidate_ready_count = {baseline.baseline_candidate_ready_count}",
                f"- verifier_pass_count = {baseline.baseline_verifier_pass_count}",
                "",
                "## Guardrails",
                "",
                "- `.env` must remain local-only and must not enter staged files.",
                "- Phase 12 should compare against this anchor instead of reinterpreting old `revise_only` snapshots as current state.",
                "- Future Phase 12 diffs should explain whether changes come from substrate repair, workflow-context repair, verifier/rubric repair, or export/eval hardening.",
            ]
        ) + "\n"
