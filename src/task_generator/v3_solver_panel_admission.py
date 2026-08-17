from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_behavioral_preflight_evidence import (
    BehavioralEvidenceIntegrityReportV1,
)
from task_generator.v3_behavioral_validation import SolverToolPreflightReportV1
from task_generator.v3_evaluation_calibration import (
    EvaluationCalibrationCompiler,
    FrozenSolverPanelV1,
    SolverPanelMemberV1,
)


FailureClass = Literal[
    "none",
    "invalid_file_content",
    "agent_nonconvergence",
    "model_gateway_agent_protocol_indeterminate",
    "non_delivery",
    "tool_contract_failure",
    "evidence_integrity_failure",
]


class SolverPanelAdmissionMemberV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solver_model: str
    stratum: Literal["weak", "medium", "strong"]
    preflight_status: Literal["pass", "fail", "not_evaluated"]
    evidence_integrity: Literal["pass", "blocked"]
    failure_class: FailureClass
    action: Literal["retain", "replace", "evidence_blocked"]
    prior_evidence_reusable: bool
    same_model_retry_allowed: Literal[False] = False
    reason_codes: List[str] = Field(default_factory=list)


class SolverPanelAdmissionPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_version: Literal["v3.solver_panel_admission.1"] = (
        "v3.solver_panel_admission.1"
    )
    panel_id: str
    frozen_panel_sha256: str
    evidence_integrity_sha256: str
    authorization_request_sha256: str
    members: List[SolverPanelAdmissionMemberV1]
    retained_models: List[str]
    replacement_required_strata: List[Literal["weak", "medium", "strong"]]
    decision: Literal[
        "panel_ready",
        "retain_passing_replace_failed",
        "evidence_redesign_required",
    ]
    next_external_execution_authorized: Literal[False] = False
    blind_package_execution_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class SolverPanelReplacementSlotV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stratum: Literal["weak", "medium", "strong"]
    failed_model: str
    failure_class: FailureClass
    candidate_model: None = None
    status: Literal["candidate_selection_required"] = "candidate_selection_required"


class SolverPanelReplacementBoundaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    boundary_version: Literal["v3.solver_panel_replacement_boundary.1"] = (
        "v3.solver_panel_replacement_boundary.1"
    )
    admission_plan_sha256: str
    retained_models: List[str]
    slots: List[SolverPanelReplacementSlotV1]
    maximum_external_models: int
    prohibited_models: List[str]
    require_distinct_candidates: Literal[True] = True
    require_per_model_budget: Literal[True] = True
    require_fresh_container_parity: Literal[True] = True
    require_exact_authorization: Literal[True] = True
    reuse_passing_evidence_without_call: Literal[True] = True
    decision: Literal["candidate_selection_required"] = "candidate_selection_required"
    external_execution_authorized: Literal[False] = False
    blind_package_execution_authorized: Literal[False] = False


class SolverPanelReplacementMergeReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_version: Literal["v3.solver_panel_replacement_merge.1"] = (
        "v3.solver_panel_replacement_merge.1"
    )
    admission_plan_sha256: str
    replacement_boundary_sha256: str
    replacement_authorization_request_sha256: str
    retained_frozen_panel_sha256: str
    retained_evidence_integrity_sha256: str
    replacement_evidence_integrity_sha256: str
    final_panel_path: str
    final_panel_sha256: str
    final_panel: FrozenSolverPanelV1
    retained_models: List[str]
    replacement_models: List[str]
    decision: Literal["pass"] = "pass"
    external_execution_authorized: Literal[False] = False
    blind_package_execution_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class SolverPanelAdmissionCompiler:
    def compile(
        self,
        *,
        frozen_panel_path: str | Path,
        evidence_integrity_path: str | Path,
    ) -> SolverPanelAdmissionPlanV1:
        panel_path = Path(frozen_panel_path).resolve()
        integrity_path = Path(evidence_integrity_path).resolve()
        panel = FrozenSolverPanelV1.model_validate_json(
            panel_path.read_text(encoding="utf-8")
        )
        integrity = BehavioralEvidenceIntegrityReportV1.model_validate_json(
            integrity_path.read_text(encoding="utf-8")
        )
        integrity_by_model = {item.solver_model: item for item in integrity.records}
        panel_models = {item.solver_model for item in panel.members}
        if panel_models != set(integrity_by_model):
            raise ValueError("solver_panel_integrity_model_scope_mismatch")
        decisions: list[SolverPanelAdmissionMemberV1] = []
        for member in panel.members:
            persisted_path = Path(member.preflight_report_path)
            persisted = SolverToolPreflightReportV1.model_validate_json(
                persisted_path.read_text(encoding="utf-8")
            )
            if persisted != member.preflight_report:
                raise ValueError(
                    f"solver_panel_persisted_report_mismatch:{member.solver_model}"
                )
            integrity_record = integrity_by_model[member.solver_model]
            if integrity_record.decision != "pass":
                decisions.append(
                    SolverPanelAdmissionMemberV1(
                        solver_model=member.solver_model,
                        stratum=member.stratum,
                        preflight_status=persisted.status,
                        evidence_integrity="blocked",
                        failure_class="evidence_integrity_failure",
                        action="evidence_blocked",
                        prior_evidence_reusable=False,
                        reason_codes=integrity_record.blocking_reasons,
                    )
                )
                continue
            failure_class, reasons = self._classify(persisted)
            passed = persisted.status == "pass" and persisted.eligible_for_business_eval
            decisions.append(
                SolverPanelAdmissionMemberV1(
                    solver_model=member.solver_model,
                    stratum=member.stratum,
                    preflight_status=persisted.status,
                    evidence_integrity="pass",
                    failure_class=failure_class,
                    action="retain" if passed else "replace",
                    prior_evidence_reusable=passed,
                    reason_codes=reasons,
                )
            )
        if any(item.action == "evidence_blocked" for item in decisions):
            decision = "evidence_redesign_required"
        elif all(item.action == "retain" for item in decisions):
            decision = "panel_ready"
        else:
            decision = "retain_passing_replace_failed"
        return SolverPanelAdmissionPlanV1(
            panel_id=panel.panel_id,
            frozen_panel_sha256=self._sha(panel_path),
            evidence_integrity_sha256=self._sha(integrity_path),
            authorization_request_sha256=integrity.authorization_request_sha256,
            members=decisions,
            retained_models=sorted(
                item.solver_model for item in decisions if item.action == "retain"
            ),
            replacement_required_strata=sorted(
                [item.stratum for item in decisions if item.action == "replace"],
                key={"weak": 0, "medium": 1, "strong": 2}.get,
            ),
            decision=decision,
            notes=[
                "Passing, hash-complete public preflight evidence may be retained without another provider call.",
                "Failed models are replacement candidates, not automatically retryable models.",
                "This plan grants no external, blind-package, business, grader or mutation authority.",
            ],
        )

    def compile_replacement_boundary(
        self,
        *,
        admission_plan_path: str | Path,
    ) -> SolverPanelReplacementBoundaryV1:
        plan_path = Path(admission_plan_path).resolve()
        plan = SolverPanelAdmissionPlanV1.model_validate_json(
            plan_path.read_text(encoding="utf-8")
        )
        if plan.decision != "retain_passing_replace_failed":
            raise ValueError("replacement_boundary_requires_replace_decision")
        replacements = [item for item in plan.members if item.action == "replace"]
        return SolverPanelReplacementBoundaryV1(
            admission_plan_sha256=self._sha(plan_path),
            retained_models=plan.retained_models,
            slots=[
                SolverPanelReplacementSlotV1(
                    stratum=item.stratum,
                    failed_model=item.solver_model,
                    failure_class=item.failure_class,
                )
                for item in replacements
            ],
            maximum_external_models=len(replacements),
            prohibited_models=sorted(
                {item.solver_model for item in replacements}
                | {"claude-sonnet-4-6"}
            ),
        )

    def merge_replacement_evidence(
        self,
        *,
        admission_plan_path: str | Path,
        replacement_boundary_path: str | Path,
        replacement_authorization_request_path: str | Path,
        retained_frozen_panel_path: str | Path,
        retained_evidence_integrity_path: str | Path,
        replacement_evidence_integrity_path: str | Path,
        replacement_members: List[SolverPanelMemberV1],
        final_panel_id: str,
        output_panel_path: str | Path,
    ) -> SolverPanelReplacementMergeReportV1:
        from task_generator.v3_behavioral_authorization import (
            BehavioralPreflightAuthorizationRequestV3,
        )

        admission_path = Path(admission_plan_path).resolve()
        boundary_path = Path(replacement_boundary_path).resolve()
        request_path = Path(replacement_authorization_request_path).resolve()
        retained_panel_path = Path(retained_frozen_panel_path).resolve()
        retained_integrity_path = Path(retained_evidence_integrity_path).resolve()
        replacement_integrity_path = Path(replacement_evidence_integrity_path).resolve()
        paths = (
            admission_path,
            boundary_path,
            request_path,
            retained_panel_path,
            retained_integrity_path,
            replacement_integrity_path,
        )
        if any(not path.is_file() for path in paths):
            raise FileNotFoundError("solver_panel_replacement_merge_evidence_missing")
        admission = SolverPanelAdmissionPlanV1.model_validate_json(
            admission_path.read_text(encoding="utf-8")
        )
        boundary = SolverPanelReplacementBoundaryV1.model_validate_json(
            boundary_path.read_text(encoding="utf-8")
        )
        request = BehavioralPreflightAuthorizationRequestV3.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        retained_panel = FrozenSolverPanelV1.model_validate_json(
            retained_panel_path.read_text(encoding="utf-8")
        )
        retained_integrity = BehavioralEvidenceIntegrityReportV1.model_validate_json(
            retained_integrity_path.read_text(encoding="utf-8")
        )
        replacement_integrity = BehavioralEvidenceIntegrityReportV1.model_validate_json(
            replacement_integrity_path.read_text(encoding="utf-8")
        )
        request_sha = self._sha(request_path)
        chain_checks = {
            "admission_boundary": boundary.admission_plan_sha256
            == self._sha(admission_path),
            "request_admission": request.admission_plan_sha256
            == self._sha(admission_path),
            "request_boundary": request.replacement_boundary_sha256
            == self._sha(boundary_path),
            "request_panel": request.retained_frozen_panel_sha256
            == self._sha(retained_panel_path),
            "request_retained_integrity": request.retained_evidence_integrity_sha256
            == self._sha(retained_integrity_path),
            "admission_panel": admission.frozen_panel_sha256
            == self._sha(retained_panel_path),
            "admission_integrity": admission.evidence_integrity_sha256
            == self._sha(retained_integrity_path),
            "replacement_request": replacement_integrity.authorization_request_sha256
            == request_sha,
            "retained_integrity": retained_integrity.decision == "pass",
            "replacement_integrity": replacement_integrity.decision == "pass",
        }
        failed_chain = sorted(
            name for name, passed in chain_checks.items() if not passed
        )
        if failed_chain:
            raise ValueError(
                "solver_panel_replacement_merge_chain_mismatch:"
                + ",".join(failed_chain)
            )
        retained_models = set(boundary.retained_models)
        retained_members = [
            item for item in retained_panel.members if item.solver_model in retained_models
        ]
        if {item.solver_model for item in retained_members} != retained_models:
            raise ValueError("solver_panel_replacement_retained_member_missing")
        retained_integrity_by_model = {
            item.solver_model: item for item in retained_integrity.records
        }
        for member in retained_members:
            record = retained_integrity_by_model.get(member.solver_model)
            report_path = Path(member.preflight_report_path)
            if (
                record is None
                or record.decision != "pass"
                or member.preflight_report.status != "pass"
                or not member.preflight_report.eligible_for_business_eval
                or not report_path.is_file()
                or SolverToolPreflightReportV1.model_validate_json(
                    report_path.read_text(encoding="utf-8")
                )
                != member.preflight_report
            ):
                raise ValueError("solver_panel_replacement_retained_member_invalid")

        authorized_by_model = {item.solver_model: item for item in request.panel_members}
        replacement_by_model = {item.solver_model: item for item in replacement_members}
        replacement_integrity_by_model = {
            item.solver_model: item for item in replacement_integrity.records
        }
        if (
            len(replacement_by_model) != len(replacement_members)
            or set(replacement_by_model) != set(authorized_by_model)
            or set(replacement_integrity_by_model) != set(authorized_by_model)
        ):
            raise ValueError("solver_panel_replacement_member_scope_mismatch")
        for model, member in replacement_by_model.items():
            authorized = authorized_by_model[model]
            integrity_record = replacement_integrity_by_model[model]
            report_path = Path(member.preflight_report_path)
            if (
                member.stratum != authorized.stratum
                or member.provider != authorized.provider
                or member.maximum_cost_per_task_usd > authorized.maximum_cost_usd
                or integrity_record.decision != "pass"
                or member.preflight_report.status != "pass"
                or not member.preflight_report.eligible_for_business_eval
                or not report_path.is_file()
                or SolverToolPreflightReportV1.model_validate_json(
                    report_path.read_text(encoding="utf-8")
                )
                != member.preflight_report
            ):
                raise ValueError(
                    f"solver_panel_replacement_member_invalid:{model}"
                )
        final_panel = EvaluationCalibrationCompiler().freeze_solver_panel(
            panel_id=final_panel_id,
            members=retained_members + replacement_members,
        )
        if final_panel.decision != "pass":
            raise ValueError(
                "solver_panel_replacement_final_panel_blocked:"
                + ",".join(final_panel.blocking_reasons)
            )
        destination = Path(output_panel_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = final_panel.model_dump(mode="json")
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=destination.parent
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        os.replace(temporary, destination)
        return SolverPanelReplacementMergeReportV1(
            admission_plan_sha256=self._sha(admission_path),
            replacement_boundary_sha256=self._sha(boundary_path),
            replacement_authorization_request_sha256=request_sha,
            retained_frozen_panel_sha256=self._sha(retained_panel_path),
            retained_evidence_integrity_sha256=self._sha(retained_integrity_path),
            replacement_evidence_integrity_sha256=self._sha(
                replacement_integrity_path
            ),
            final_panel_path=str(destination),
            final_panel_sha256=self._sha(destination),
            final_panel=final_panel,
            retained_models=sorted(retained_models),
            replacement_models=sorted(replacement_by_model),
            notes=[
                "The final panel combines retained hash-complete evidence with newly authorized replacement evidence.",
                "This merge grants no external, blind-package, grader, release or mutation authority.",
            ],
        )

    @staticmethod
    def _classify(
        report: SolverToolPreflightReportV1,
    ) -> tuple[FailureClass, list[str]]:
        if report.status == "pass" and report.eligible_for_business_eval:
            return "none", []
        failure_reasons = [
            item.failure_reason for item in report.attempts if item.failure_reason
        ]
        if any("provider_call_ceiling_reached" in item for item in failure_reasons):
            return "agent_nonconvergence", ["provider_call_ceiling_reached"]
        if any("solver_protocol_blocked:" in item for item in failure_reasons):
            return (
                "model_gateway_agent_protocol_indeterminate",
                ["consecutive_empty_assistant_responses"],
            )
        delivery = report.delivery_inspection
        if any(item.exists and item.nonempty and not item.openable for item in delivery.records):
            return "invalid_file_content", ["expected_deliverable_unopenable"]
        if delivery.valid_count == 0 and all(not item.exists for item in delivery.records):
            return "non_delivery", ["expected_deliverables_missing"]
        return "tool_contract_failure", [report.first_failure or "preflight_failed"]

    @staticmethod
    def _sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
