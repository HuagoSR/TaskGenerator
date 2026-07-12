from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from task_generator.v3_source_schema import load_json_file


ProductionQADecision = Literal["blocked", "review_required", "approved_production_candidate"]
ProductionQAFindingSeverity = Literal["blocking", "warning", "info"]


class ProductionQAGateRequest(BaseModel):
    production_batch_manifest_path: str
    diversity_report_path: Optional[str] = None
    semantic_validation_report_path: Optional[str] = None
    output_dir: str


class ProductionQAFinding(BaseModel):
    finding_id: str
    severity: ProductionQAFindingSeverity
    code: str
    message: str


class ProductionQACaseDecision(BaseModel):
    case_id: str
    blueprint_id: Optional[str] = None
    current_task_state: str
    proposed_task_state: str
    decision: ProductionQADecision
    production_candidate_approved: bool = False
    findings: List[ProductionQAFinding] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class ProductionQAGateSummary(BaseModel):
    case_count: int = 0
    approved_production_candidate_count: int = 0
    review_required_count: int = 0
    blocked_count: int = 0
    blocking_finding_count: int = 0
    warning_finding_count: int = 0
    decision_counts: Dict[str, int] = Field(default_factory=dict)
    finding_code_counts: Dict[str, int] = Field(default_factory=dict)


class ProductionQAGateReport(BaseModel):
    production_qa_gate_version: str = "v3.production_qa_gate.1"
    request: ProductionQAGateRequest
    production_batch_id: str
    decisions: List[ProductionQACaseDecision] = Field(default_factory=list)
    summary: ProductionQAGateSummary
    notes: List[str] = Field(default_factory=list)


class ProductionQAGateBuilder:
    def build(
        self,
        production_batch_manifest_path: str | Path,
        output_dir: str | Path,
        diversity_report_path: str | Path | None = None,
        semantic_validation_report_path: str | Path | None = None,
    ) -> ProductionQAGateReport:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        request = ProductionQAGateRequest(
            production_batch_manifest_path=str(production_batch_manifest_path),
            diversity_report_path=str(diversity_report_path) if diversity_report_path else None,
            semantic_validation_report_path=str(semantic_validation_report_path) if semantic_validation_report_path else None,
            output_dir=str(output_path),
        )
        manifest = load_json_file(str(production_batch_manifest_path))
        diversity = load_json_file(str(diversity_report_path)) if diversity_report_path else {}
        production_batch_id = str((manifest.get("request") or {}).get("production_batch_id") or "unknown_batch")
        diversity_warnings = set((diversity.get("diagnostics") or {}).get("warnings") or [])
        semantic = load_json_file(str(semantic_validation_report_path)) if semantic_validation_report_path else {}
        semantic_records = {
            str(item.get("task_id") or ""): item for item in (semantic.get("records") or []) if isinstance(item, dict)
        }
        decisions = [
            self._decision(case, diversity_warnings, semantic.get("mode"), semantic_records.get(str(case.get("case_id") or "")))
            for case in (manifest.get("cases") or [])
            if isinstance(case, dict)
        ]
        summary = self._summary(decisions)
        report = ProductionQAGateReport(
            request=request,
            production_batch_id=production_batch_id,
            decisions=decisions,
            summary=summary,
            notes=[
                "Production QA Gate V1 is report-first and does not silently rewrite the production batch manifest.",
                "The gate promotes only from candidate_ready to a proposed production_candidate state when structural production checks pass cleanly.",
                "Diagnostic-only validity and low workflow-context fit are preserved as explicit review signals instead of being hidden.",
            ],
        )
        (output_path / "production_qa_gate_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report

    def _decision(
        self,
        case: Dict[str, object],
        diversity_warnings: set[str],
        semantic_mode: object = None,
        semantic_record: Optional[Dict[str, object]] = None,
    ) -> ProductionQACaseDecision:
        findings: List[ProductionQAFinding] = []
        case_dir = Path(str(case.get("case_dir") or ""))
        export_report = self._load_optional(case_dir / "rw_task_export" / "rw_task_export_report.json")
        export_validation = self._load_optional(
            case_dir / "rw_task_export" / "rw_task_export_validation_report.json"
        )
        verifier_report = self._load_optional(case_dir / "task_verifier" / "task_verifier_report.json")

        if case.get("batch_status") != "completed":
            findings.append(self._finding("blocking", "batch_not_completed", "Case did not complete the deterministic batch flow."))
        if case.get("task_state") != "candidate_ready":
            findings.append(self._finding("blocking", "not_candidate_ready", "Case is not in candidate_ready state."))
        if case.get("quality_decision") != "candidate_ready":
            findings.append(self._finding("blocking", "quality_gate_not_candidate_ready", "Quality gate is not candidate_ready."))
        if case.get("verifier_status") != "pass":
            findings.append(self._finding("blocking", "verifier_not_pass", "Deterministic task verifier did not pass."))
        if case.get("validation_status") != "candidate_ready_compatible":
            findings.append(self._finding("blocking", "export_validation_not_candidate_ready_compatible", "rw-task export validator did not report candidate_ready_compatible."))
        if str((export_report or {}).get("export_decision") or "") != "exported":
            findings.append(self._finding("blocking", "export_not_exported", "rw-task export decision is not exported."))
        if int((export_validation or {}).get("blocking_count") or 0) > 0:
            findings.append(self._finding("blocking", "export_validation_blockers_present", "rw-task export validation still has blocking findings."))
        if int(((verifier_report or {}).get("diagnostics") or {}).get("blocking_count") or 0) > 0:
            findings.append(self._finding("blocking", "verifier_blockers_present", "Task verifier still has blocking findings."))

        if semantic_mode == "blocking":
            if not semantic_record:
                findings.append(self._finding("blocking", "semantic_validation_missing", "Blocking semantic validation has no case record."))
            elif not bool(semantic_record.get("semantic_gate_pass")):
                findings.append(self._finding("blocking", "semantic_validation_not_pass", "LLM-assisted semantic validity gate did not pass."))
        elif semantic_mode in {"prepare", "diagnostic"}:
            if not semantic_record or not bool(semantic_record.get("semantic_gate_pass")):
                findings.append(self._finding("warning", "semantic_validation_review_required", "Semantic validity remains diagnostic or unresolved."))

        if case.get("workflow_context_fit") != "high":
            findings.append(self._finding("warning", "workflow_context_not_high", "Workflow-context fit is not yet high."))
        if case.get("global_validity_status") == "diagnostic_only":
            findings.append(self._finding("warning", "global_validity_diagnostic_only", "Global validity remains diagnostic_only and still needs explicit reviewer interpretation."))
        real_worldness_score = case.get("real_worldness_score")
        if isinstance(real_worldness_score, (int, float)) and float(real_worldness_score) < 0.85:
            findings.append(self._finding("warning", "real_worldness_below_production_target", "Real-worldness score is below the current production-target heuristic of 0.85."))
        if diversity_warnings:
            findings.append(
                self._finding(
                    "info",
                    "batch_diversity_review_present",
                    "This batch carries diversity warnings that should be reviewed at batch scope before release planning.",
                )
            )

        blocking_count = sum(1 for finding in findings if finding.severity == "blocking")
        warning_count = sum(1 for finding in findings if finding.severity == "warning")
        decision: ProductionQADecision
        proposed_state = str(case.get("task_state") or "generated")
        approved = False
        notes: List[str] = []
        if blocking_count > 0:
            decision = "blocked"
            notes.append("Resolve structural production blockers before any governed state promotion.")
        elif warning_count > 0:
            decision = "review_required"
            notes.append("Structural closure is intact, but production promotion still needs explicit reviewer sign-off.")
        else:
            decision = "approved_production_candidate"
            proposed_state = "production_candidate"
            approved = True
            notes.append("This case can be proposed as a governed production_candidate without hidden state mutation.")
        return ProductionQACaseDecision(
            case_id=str(case.get("case_id") or "unknown_case"),
            blueprint_id=self._optional_str(case.get("blueprint_id")),
            current_task_state=str(case.get("task_state") or "generated"),
            proposed_task_state=proposed_state,
            decision=decision,
            production_candidate_approved=approved,
            findings=findings,
            notes=notes,
        )

    def _summary(
        self,
        decisions: List[ProductionQACaseDecision],
    ) -> ProductionQAGateSummary:
        decision_counts: Dict[str, int] = {}
        finding_code_counts: Dict[str, int] = {}
        blocking_finding_count = 0
        warning_finding_count = 0
        for decision in decisions:
            decision_counts[decision.decision] = decision_counts.get(decision.decision, 0) + 1
            for finding in decision.findings:
                finding_code_counts[finding.code] = finding_code_counts.get(finding.code, 0) + 1
                if finding.severity == "blocking":
                    blocking_finding_count += 1
                if finding.severity == "warning":
                    warning_finding_count += 1
        return ProductionQAGateSummary(
            case_count=len(decisions),
            approved_production_candidate_count=sum(
                1 for decision in decisions if decision.decision == "approved_production_candidate"
            ),
            review_required_count=sum(1 for decision in decisions if decision.decision == "review_required"),
            blocked_count=sum(1 for decision in decisions if decision.decision == "blocked"),
            blocking_finding_count=blocking_finding_count,
            warning_finding_count=warning_finding_count,
            decision_counts=dict(sorted(decision_counts.items())),
            finding_code_counts=dict(sorted(finding_code_counts.items())),
        )

    def _load_optional(self, path: Path) -> Dict[str, object]:
        if not path.exists():
            return {}
        return load_json_file(str(path))

    def _finding(
        self,
        severity: ProductionQAFindingSeverity,
        code: str,
        message: str,
    ) -> ProductionQAFinding:
        return ProductionQAFinding(
            finding_id=f"prodqa_{code}",
            severity=severity,
            code=code,
            message=message,
        )

    def _optional_str(self, value: object) -> Optional[str]:
        if value is None:
            return None
        return str(value)
