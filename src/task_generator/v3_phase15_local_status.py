from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


LocalStatus = Literal["ready_for_local_followup", "blocked_on_external_eval", "missing_local_evidence"]
TenantPolicyStatus = Literal["tenant_policy_denied", "not_recorded"]


class Phase15LocalStatusRequest(BaseModel):
    completion_audit_report_path: str
    postmortem_report_path: str
    external_eval_readiness_report_path: str
    permitted_eval_bundle_report_path: str
    external_eval_import_report_path: str
    external_eval_runbook_path: str
    external_eval_script_path: str
    output_dir: str


class Phase15LocalStatusReport(BaseModel):
    report_version: str = "v3.phase15_local_status.1"
    created_at: str
    diagnostic_only: bool = True
    request: Phase15LocalStatusRequest
    local_status: LocalStatus
    phase15_completion_status: Optional[str] = None
    phase15_decision: Optional[str] = None
    external_eval_package_readiness: Optional[str] = None
    permitted_eval_bundle_status: Optional[str] = None
    external_eval_import_status: Optional[str] = None
    tenant_policy_status: TenantPolicyStatus
    evidence_presence: Dict[str, bool] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)
    blocking_reasons: List[str] = Field(default_factory=list)
    next_local_command_sequence: List[str] = Field(default_factory=list)
    permitted_environment_command: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class Phase15LocalStatusBuilder:
    """Summarize the current local Phase 15 status without external calls or secrets."""

    def build(self, request: Phase15LocalStatusRequest) -> Phase15LocalStatusReport:
        output_dir = Path(request.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        completion_audit = self._load_optional(request.completion_audit_report_path)
        postmortem = self._load_optional(request.postmortem_report_path)
        readiness = self._load_optional(request.external_eval_readiness_report_path)
        bundle = self._load_optional(request.permitted_eval_bundle_report_path)
        eval_import = self._load_optional(request.external_eval_import_report_path)
        runbook = self._load_optional(request.external_eval_runbook_path)

        evidence_presence = {
            "completion_audit": bool(completion_audit),
            "postmortem": bool(postmortem),
            "external_eval_readiness": bool(readiness),
            "permitted_eval_bundle": bool(bundle),
            "external_eval_import": bool(eval_import),
            "external_eval_runbook": bool(runbook),
            "external_eval_script": Path(request.external_eval_script_path).exists(),
        }
        tenant_policy_status = self._tenant_policy_status(postmortem)
        blocking_reasons = self._blocking_reasons(
            evidence_presence=evidence_presence,
            completion_audit=completion_audit,
            postmortem=postmortem,
            eval_import=eval_import,
            tenant_policy_status=tenant_policy_status,
        )
        report = Phase15LocalStatusReport(
            created_at=datetime.now(timezone.utc).isoformat(),
            request=request,
            local_status=self._local_status(evidence_presence, tenant_policy_status, eval_import),
            phase15_completion_status=completion_audit.get("completion_status"),
            phase15_decision=postmortem.get("phase15_decision"),
            external_eval_package_readiness=readiness.get("readiness_status"),
            permitted_eval_bundle_status=bundle.get("bundle_status"),
            external_eval_import_status=eval_import.get("import_status"),
            tenant_policy_status=tenant_policy_status,
            evidence_presence=evidence_presence,
            summary=self._summary(completion_audit, postmortem, readiness, bundle, eval_import, runbook),
            blocking_reasons=blocking_reasons,
            next_local_command_sequence=[
                "D:\\miniconda3\\envs\\taskgenerator\\python.exe Test\\run_v3_phase15_external_eval_importer.py",
                "D:\\miniconda3\\envs\\taskgenerator\\python.exe Test\\run_v3_phase15_promotion_postmortem.py",
                "D:\\miniconda3\\envs\\taskgenerator\\python.exe Test\\run_v3_phase15_completion_audit.py",
                "D:\\miniconda3\\envs\\taskgenerator\\python.exe Test\\run_v3_phase15_local_status.py",
            ],
            permitted_environment_command=str(Path(request.external_eval_script_path)),
            notes=[
                "This local status report does not call external APIs.",
                "This local status report does not read .env or print secret values.",
                "A ready runbook means the package is structurally prepared for a separately permitted environment, not that this tenant is allowed to export it.",
                "A ready permitted-eval bundle is transfer logistics evidence, not clean eval completion evidence.",
            ],
        )
        (output_dir / "phase15_local_status_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _load_optional(self, path: str) -> Dict[str, Any]:
        payload_path = Path(path)
        if not payload_path.exists() or payload_path.is_dir():
            return {}
        try:
            return json.loads(payload_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _tenant_policy_status(self, postmortem: Dict[str, Any]) -> TenantPolicyStatus:
        blockers = [str(item) for item in postmortem.get("blocking_reasons") or []]
        eval_evidence = ((postmortem.get("evidence_summary") or {}).get("eval") or {})
        authorization_status = str(eval_evidence.get("external_eval_authorization_status") or "")
        if "external_eval_tenant_policy_denied" in blockers or "tenant_policy_denied" in authorization_status:
            return "tenant_policy_denied"
        return "not_recorded"

    def _local_status(
        self,
        evidence_presence: Dict[str, bool],
        tenant_policy_status: TenantPolicyStatus,
        eval_import: Dict[str, Any],
    ) -> LocalStatus:
        required_present = all(
            evidence_presence.get(key)
            for key in [
                "completion_audit",
                "postmortem",
                "external_eval_readiness",
                "permitted_eval_bundle",
                "external_eval_import",
                "external_eval_runbook",
                "external_eval_script",
            ]
        )
        if not required_present:
            return "missing_local_evidence"
        if eval_import.get("import_status") != "ready_for_closeout" or tenant_policy_status == "tenant_policy_denied":
            return "blocked_on_external_eval"
        return "ready_for_local_followup"

    def _blocking_reasons(
        self,
        evidence_presence: Dict[str, bool],
        completion_audit: Dict[str, Any],
        postmortem: Dict[str, Any],
        eval_import: Dict[str, Any],
        tenant_policy_status: TenantPolicyStatus,
    ) -> List[str]:
        blockers: List[str] = []
        for key, present in evidence_presence.items():
            if not present:
                blockers.append(f"{key}_missing")
        blockers.extend(str(item) for item in completion_audit.get("final_blockers") or [])
        blockers.extend(str(item) for item in postmortem.get("blocking_reasons") or [])
        blockers.extend(str(item) for item in eval_import.get("blocking_reasons") or [])
        if tenant_policy_status == "tenant_policy_denied":
            blockers.append("external_eval_tenant_policy_denied_in_current_environment")
        return sorted(set(blockers))

    def _summary(
        self,
        completion_audit: Dict[str, Any],
        postmortem: Dict[str, Any],
        readiness: Dict[str, Any],
        bundle: Dict[str, Any],
        eval_import: Dict[str, Any],
        runbook: Dict[str, Any],
    ) -> Dict[str, Any]:
        audit_summary = completion_audit.get("summary") or {}
        import_summary = eval_import.get("summary") or {}
        runbook_items = runbook.get("items") or []
        return {
            "audit_status_counts": audit_summary.get("status_counts"),
            "audit_item_count": audit_summary.get("item_count"),
            "audit_proven_item_count": audit_summary.get("proven_count"),
            "postmortem_recommendation": postmortem.get("recommendation"),
            "readiness_item_count": readiness.get("item_count"),
            "readiness_blocking_reasons": readiness.get("blocking_reasons") or [],
            "permitted_eval_bundle_item_count": bundle.get("item_count"),
            "permitted_eval_bundle_zip_path": bundle.get("zip_path"),
            "permitted_eval_bundle_blocking_reasons": bundle.get("blocking_reasons") or [],
            "import_complete_pair_count": import_summary.get("complete_pair_count"),
            "import_mean_reform_minus_baseline_delta": import_summary.get("mean_reform_minus_baseline_delta"),
            "runbook_item_count": len(runbook_items),
            "runbook_first_item": self._runbook_item_summary(runbook_items[0]) if runbook_items else None,
            "runbook_second_item": self._runbook_item_summary(runbook_items[1]) if len(runbook_items) > 1 else None,
        }

    def _runbook_item_summary(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "arm_id": item.get("arm_id"),
            "case_id": item.get("case_id"),
            "model": item.get("model"),
            "item_id": item.get("item_id"),
        }
