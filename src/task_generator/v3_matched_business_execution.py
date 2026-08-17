from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from typing import Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_matched_screening import (
    MatchedBusinessAuthorizationRequestV1,
    MatchedScreeningAnalyzer,
    MatchedScreeningCampaign,
    MatchedScreeningResultV1,
    RUBRIC_WEIGHTS,
    ScreeningCriterionGradeV1,
    ScreeningGraderReviewV1,
    ScreeningTaskObservationV1,
    SolverSelectionV1,
    deepseek_solver_environment,
)
from task_generator.v3_matched_solver_preflight import DeepSeekSolverPreflightReportV1
from task_generator.v3_semantic_review_executor import (
    SemanticReviewExecutionError,
    SemanticReviewExecutor,
)
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_solver_execution_budget import SolverProcessOutcomeV1
from task_generator.v3_source_fingerprint import governed_source_fingerprint
from task_generator.v3_validity_utility import UtilityProfileV1, ValidityVectorV1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(root: Path) -> str:
    rows = [
        f"{item.relative_to(root).as_posix()}:{_sha(item)}"
        for item in sorted(path for path in root.rglob("*") if path.is_file())
    ]
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def _deliverable_tree(root: Path) -> Optional[str]:
    files = sorted(item for item in root.rglob("*") if item.is_file())
    if not files:
        return None
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(item.read_bytes()).digest())
    return digest.hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_single_case_dataset(root: str | Path, blind_task_id: str) -> Path:
    dataset = Path(root)
    cases = list(dataset.glob("*/dataset_row.json"))
    expected = dataset / blind_task_id / "dataset_row.json"
    if len(cases) != 1 or cases[0] != expected:
        raise ValueError("matched_business_single_case_dataset_invalid")
    row = json.loads(expected.read_text(encoding="utf-8"))
    if row.get("task_id") != blind_task_id:
        raise ValueError("matched_business_single_case_identity_mismatch")
    return expected.parent


class MatchedBusinessAuthorizationReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal["v3.matched_business_authorization_receipt.1"] = (
        "v3.matched_business_authorization_receipt.1"
    )
    campaign_id: str
    authorization_request_sha256: str = Field(min_length=64, max_length=64)
    campaign_manifest_sha256: str = Field(min_length=64, max_length=64)
    staging_report_sha256: str = Field(min_length=64, max_length=64)
    solver_selection_sha256: str = Field(min_length=64, max_length=64)
    parity_report_sha256: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    blind_package_fingerprints: Dict[str, str]
    candidate_tree_sha256: Dict[str, str]
    reality_evidence_sha256: Dict[str, str]
    authorized_solver: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    solver_task_count: Literal[12] = 12
    solver_total_cost_ceiling_usd: Literal[12.0] = 12.0
    grader_model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    grader_maximum_provider_calls: Literal[24] = 24
    grader_maximum_total_cost_usd: Literal[0.5] = 0.5
    authorized_by_user: Literal[True]
    authorization_statement: str = Field(min_length=16)
    issued_at: str
    expires_at: str
    expert_review_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    release_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False

    def model_post_init(self, __context: object) -> None:
        keys = set(self.blind_package_fingerprints)
        if len(keys) != 12 or set(self.candidate_tree_sha256) != keys or set(self.reality_evidence_sha256) != keys:
            raise ValueError("matched_business_receipt_twelve_task_binding_mismatch")


class ScreeningGraderDraftV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    criteria: List[ScreeningCriterionGradeV1] = Field(min_length=7, max_length=7)
    major_defect: bool
    major_defect_reason: Optional[str] = None
    professional_plausibility: Literal["pass", "fail"]
    effective_rubric_dimensions: int = Field(ge=0, le=7)
    route_identity_seen: Literal[False] = False


class MatchedBusinessTaskRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    solver_status: Literal["pending", "running", "succeeded", "task_failed", "infrastructure_failed"]
    solver_attempt_count: int = Field(ge=0, le=1)
    command: List[str]
    budget_path: str
    solver_input_root: str
    solver_input_tree_sha256: str
    stdout_path: Optional[str] = None
    stdout_sha256: Optional[str] = None
    stderr_path: Optional[str] = None
    stderr_sha256: Optional[str] = None
    outcome_path: Optional[str] = None
    outcome_sha256: Optional[str] = None
    delivery_valid: bool = False
    first_failure: Optional[str] = None
    grader_status: Literal["not_eligible", "pending", "completed", "infrastructure_failed"] = "not_eligible"
    grader_attempt_count: int = Field(default=0, ge=0, le=2)
    grader_review_path: Optional[str] = None
    grader_review_sha256: Optional[str] = None
    grader_first_failure_path: Optional[str] = None
    grader_attempt_artifacts: Dict[str, str] = Field(default_factory=dict)


class MatchedBusinessExecutionManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.matched_business_execution.1"] = "v3.matched_business_execution.1"
    campaign_id: str
    authorization_request_sha256: str
    authorization_receipt_sha256: str
    status: Literal["running", "completed", "incomplete"]
    records: List[MatchedBusinessTaskRecordV1] = Field(min_length=12, max_length=12)
    solver_provider_calls: int = Field(default=0, ge=0, le=144)
    solver_contract_cost_usd: float = Field(default=0.0, ge=0.0, le=12.0)
    grader_provider_calls: int = Field(default=0, ge=0, le=24)
    grader_reserved_cost_usd: float = Field(default=0.0, ge=0.0, le=0.5)
    result_path: Optional[str] = None
    result_sha256: Optional[str] = None
    expert_review_executed: Literal[False] = False
    training_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False
    created_at: str
    updated_at: str


class MatchedBusinessGovernance:
    def __init__(self, campaign_root: str | Path):
        self.root = Path(campaign_root).resolve()
        self.campaign = MatchedScreeningCampaign(self.root)
        self.current_request = self.root / "governance" / "business_screening_authorization_request.json"
        self.immutable_root = self.root / "governance" / "business_screening_authorization_requests"

    def compile_solver_selection(self, preflight_report_path: str | Path) -> tuple[SolverSelectionV1, Path]:
        report_path = Path(preflight_report_path).resolve()
        report = DeepSeekSolverPreflightReportV1.model_validate_json(report_path.read_text(encoding="utf-8"))
        if report.status != "pass" or not report.eligible_for_business_eval or report.first_failure:
            raise ValueError("matched_business_deepseek_preflight_not_passed")
        if not report.outcome_path or not report.outcome_sha256:
            raise ValueError("matched_business_preflight_outcome_missing")
        outcome_path = Path(report.outcome_path)
        if not outcome_path.is_file() or _sha(outcome_path) != report.outcome_sha256:
            raise ValueError("matched_business_preflight_outcome_hash_mismatch")
        outcome = SolverProcessOutcomeV1.model_validate_json(outcome_path.read_text(encoding="utf-8"))
        if outcome.process_status != "succeeded" or outcome.solver_model != "deepseek-v4-pro":
            raise ValueError("matched_business_preflight_outcome_invalid")
        deliverable_root = outcome_path.parent / "deliverable_files"
        if _deliverable_tree(deliverable_root) != outcome.output_tree_sha256:
            raise ValueError("matched_business_preflight_output_tree_drift")
        for path_text, digest in ((report.stdout_path, report.stdout_sha256), (report.stderr_path, report.stderr_sha256)):
            path = Path(path_text)
            if not path.is_file() or _sha(path) != digest:
                raise ValueError("matched_business_preflight_process_log_drift")
        selection = SolverSelectionV1(
            selected_provider="deepseek", selected_model="deepseek-v4-pro",
            selection_reason="deepseek_preflight_pass",
            preflight_report_path=str(report_path), preflight_report_sha256=_sha(report_path),
        )
        path = self.root / "governance" / "solver_selection.json"
        _write(path, selection.model_dump(mode="json"))
        return selection, path

    def compile_receipt(self, *, request_path: str | Path, authorization_statement: str, expires_at: str) -> tuple[MatchedBusinessAuthorizationReceiptV1, Path]:
        exact = Path(request_path).resolve()
        request_sha = _sha(exact)
        if exact.parent != self.immutable_root.resolve() or exact.name != f"{request_sha}.json":
            raise ValueError("matched_business_receipt_requires_immutable_request")
        request = MatchedBusinessAuthorizationRequestV1.model_validate_json(exact.read_text(encoding="utf-8"))
        self._validate_request(request, request_sha)
        receipt = MatchedBusinessAuthorizationReceiptV1(
            campaign_id=request.campaign_id,
            authorization_request_sha256=request_sha,
            campaign_manifest_sha256=request.campaign_manifest_sha256,
            staging_report_sha256=request.staging_report_sha256,
            solver_selection_sha256=request.solver_selection_sha256,
            parity_report_sha256=request.parity_report_sha256,
            source_fingerprint=request.source_fingerprint,
            blind_package_fingerprints=request.blind_package_fingerprints,
            candidate_tree_sha256=request.candidate_tree_sha256,
            reality_evidence_sha256=request.reality_evidence_sha256,
            authorized_by_user=True, authorization_statement=authorization_statement,
            issued_at=_now(), expires_at=expires_at,
        )
        path = self.root / "governance" / "business_screening_authorization_receipts" / f"{request_sha}.json"
        if path.exists():
            raise FileExistsError("matched_business_receipt_exists")
        _write(path, receipt.model_dump(mode="json"))
        return receipt, path

    def execute(
        self, *, receipt_path: str | Path, output_root: str | Path,
        real_world_python: str | Path, rw_task_root: str | Path,
        provider_config: ProviderConfig,
        command_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        grader_call: Optional[Callable[[dict, str, Optional[str]], ScreeningGraderDraftV1]] = None,
    ) -> tuple[MatchedBusinessExecutionManifestV1, Path]:
        receipt_file = Path(receipt_path).resolve()
        receipt = MatchedBusinessAuthorizationReceiptV1.model_validate_json(receipt_file.read_text(encoding="utf-8"))
        request_path = self.immutable_root / f"{receipt.authorization_request_sha256}.json"
        request = MatchedBusinessAuthorizationRequestV1.model_validate_json(request_path.read_text(encoding="utf-8"))
        self._validate_request(request, receipt.authorization_request_sha256)
        for key in ("campaign_id", "campaign_manifest_sha256", "staging_report_sha256", "solver_selection_sha256", "parity_report_sha256", "source_fingerprint", "blind_package_fingerprints", "candidate_tree_sha256", "reality_evidence_sha256"):
            if getattr(receipt, key) != getattr(request, key):
                raise PermissionError(f"matched_business_receipt_{key}_mismatch")
        if datetime.fromisoformat(receipt.expires_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            raise PermissionError("matched_business_receipt_expired")
        if provider_config.provider_name != "deepseek" or provider_config.model != "deepseek-v4-pro":
            raise PermissionError("matched_business_provider_mismatch")
        output = Path(output_root).resolve() / receipt.authorization_request_sha256
        try:
            output.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("matched_business_output_outside_campaign") from exc
        manifest_path = output / "matched_business_execution.json"
        if manifest_path.exists() or (output / "execution_state.json").exists():
            raise PermissionError("matched_business_receipt_already_consumed")
        output.mkdir(parents=True, exist_ok=True)
        _write(output / "execution_state.json", {"status": "preparing", "request_sha256": receipt.authorization_request_sha256, "receipt_sha256": _sha(receipt_file), "started_at": _now()})
        campaign = self.campaign.read()
        candidate_root = self.root / "blind_staging" / "candidate_packages"
        budget_root = output / "budgets"
        records = []
        for assignment in sorted(campaign.assignments, key=lambda item: item.blind_task_id):
            session_input = output / "session_inputs" / assignment.blind_task_id
            copied_case = session_input / assignment.blind_task_id
            shutil.copytree(candidate_root / assignment.blind_task_id, copied_case)
            validate_single_case_dataset(session_input, assignment.blind_task_id)
            if _tree(copied_case) != request.candidate_tree_sha256[assignment.blind_task_id]:
                raise PermissionError("matched_business_session_input_tree_mismatch")
            budget_path = budget_root / f"{assignment.blind_task_id}.json"
            _write(budget_path, request.solver_budget_per_task.model_dump(mode="json"))
            solver_output = output / "solver" / assignment.blind_task_id
            records.append(MatchedBusinessTaskRecordV1(
                blind_task_id=assignment.blind_task_id, solver_status="pending", solver_attempt_count=0,
                command=[str(Path(real_world_python).resolve()), "-m", "task_generator.v3_rw_task_eval_stirrup_wrapper", str(session_input), "--output", str(solver_output), "-w", "1", "--model", request.selected_solver.selected_model, "--budget-contract", str(budget_path)],
                budget_path=str(budget_path), solver_input_root=str(session_input),
                solver_input_tree_sha256=_tree(copied_case), grader_status="pending",
            ))
        now = _now()
        manifest = MatchedBusinessExecutionManifestV1(
            campaign_id=campaign.campaign_id,
            authorization_request_sha256=receipt.authorization_request_sha256,
            authorization_receipt_sha256=_sha(receipt_file), status="running",
            records=records, created_at=now, updated_at=now,
        )
        _write(output / "execution_state.json", {"status": "running", "request_sha256": receipt.authorization_request_sha256, "receipt_sha256": _sha(receipt_file), "started_at": now})
        _write(manifest_path, manifest.model_dump(mode="json"))
        env = deepseek_solver_environment()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        rw_root = Path(rw_task_root).resolve()
        if not Path(real_world_python).is_file() or not rw_root.is_dir():
            raise FileNotFoundError("matched_business_runtime_missing")
        assignment_by_id = {item.blind_task_id: item for item in campaign.assignments}
        for record in manifest.records:
            record.solver_status = "running"
            record.solver_attempt_count = 1
            manifest.updated_at = _now(); _write(manifest_path, manifest.model_dump(mode="json"))
            try:
                completed = command_runner(record.command, cwd=str(rw_root), env=env, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=1800, check=False)
                stdout, stderr = completed.stdout or "", completed.stderr or ""
                returncode = completed.returncode
            except subprocess.TimeoutExpired as exc:
                stdout, stderr, returncode = exc.stdout or "", exc.stderr or "", None
                record.first_failure = "solver_process_timeout"
                record.solver_status = "infrastructure_failed"
            secret = env.get("AGENT_API_KEY", "")
            for name, content in (("stdout", stdout), ("stderr", stderr)):
                text = content.decode("utf-8", "replace") if isinstance(content, bytes) else content
                if secret: text = text.replace(secret, "[REDACTED]")
                path = output / "process_logs" / f"{record.blind_task_id}.{name}.txt"
                path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding="utf-8")
                setattr(record, f"{name}_path", str(path)); setattr(record, f"{name}_sha256", _sha(path))
            solver_root = output / "solver" / record.blind_task_id
            candidates = list(solver_root.glob("run_*/solver_process_outcome.json"))
            if len(candidates) == 1:
                outcome_path = candidates[0]
                outcome = SolverProcessOutcomeV1.model_validate_json(outcome_path.read_text(encoding="utf-8"))
                record.outcome_path, record.outcome_sha256 = str(outcome_path), _sha(outcome_path)
                manifest.solver_provider_calls += outcome.usage.provider_calls
                manifest.solver_contract_cost_usd = round(manifest.solver_contract_cost_usd + outcome.usage.contract_cost_usd, 12)
                if outcome.process_status == "succeeded" and returncode == 0:
                    record.solver_status, record.delivery_valid = "succeeded", True
                    record.first_failure = None
                else:
                    record.first_failure = record.first_failure or outcome.first_failure or "solver_task_failed"
                    infrastructure = any(token in record.first_failure.lower() for token in ("provider", "transport", "timeout", "authentication", "rate_limit"))
                    record.solver_status = "infrastructure_failed" if infrastructure else "task_failed"
            elif record.solver_status == "running":
                record.solver_status = "infrastructure_failed"
                record.first_failure = "solver_process_outcome_missing"
            if record.delivery_valid:
                self._grade(record, output, candidate_root / record.blind_task_id, Path(assignment_by_id[record.blind_task_id].package_root), provider_config, grader_call, manifest)
            else:
                record.grader_status = "not_eligible"
            manifest.updated_at = _now(); _write(manifest_path, manifest.model_dump(mode="json"))
        observations = self._observations(campaign, manifest)
        result = MatchedScreeningAnalyzer().analyze(campaign.campaign_id, observations)
        result_path = output / "matched_screening_result.json"
        _write(result_path, result.model_dump(mode="json"))
        manifest.result_path, manifest.result_sha256 = str(result_path), _sha(result_path)
        manifest.status = "incomplete" if result.decision == "incomplete" else "completed"
        manifest.updated_at = _now(); _write(manifest_path, manifest.model_dump(mode="json"))
        _write(output / "execution_state.json", {"status": manifest.status, "request_sha256": receipt.authorization_request_sha256, "receipt_sha256": _sha(receipt_file), "manifest_sha256": _sha(manifest_path), "finished_at": _now()})
        return manifest, manifest_path

    def _grade(self, record, output, candidate_package, teacher_package, config, grader_call, manifest):
        if manifest.grader_provider_calls >= 24:
            record.grader_status = "infrastructure_failed"
            return
        delivery = next((output / "solver" / record.blind_task_id).glob("run_*/deliverable_files/*.xlsx"))
        executor = SemanticReviewExecutor(config, max_tokens=4000, input_token_hard_limit=20000, max_retries=0)
        payload = {
            "blind_task_id": record.blind_task_id,
            "candidate_prompt": json.loads((candidate_package / "dataset_row.json").read_text(encoding="utf-8"))["prompt"],
            "rubric": json.loads((teacher_package / "teacher" / "rubric_plan_v2.json").read_text(encoding="utf-8")),
            "fact_anchors": json.loads((teacher_package / "teacher" / "deterministic_fact_anchors.json").read_text(encoding="utf-8")),
            "deliverable": executor._xlsx_content(delivery),
        }
        system = "Grade the route-blind professional XLSX using exactly the seven supplied rubric criteria. Return 0, 0.5, or 1 per criterion with evidence locators. Do not infer route identity. Do not return a total score."
        first_feedback = None
        for attempt in (1, 2):
            record.grader_attempt_count = attempt
            raw_path = output / "grader" / record.blind_task_id / f"attempt_{attempt}.raw.txt"
            diagnostics_path = output / "grader" / record.blind_task_id / f"attempt_{attempt}.diagnostics.json"
            try:
                draft = grader_call(payload, system, first_feedback) if grader_call else executor._call(system, payload, ScreeningGraderDraftV1, {"blind_task_id": record.blind_task_id}, format_feedback=first_feedback)
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(executor.last_raw_response_content if grader_call is None else draft.model_dump_json(), encoding="utf-8")
                _write(diagnostics_path, executor.last_diagnostics if grader_call is None else {"mock": True})
                record.grader_attempt_artifacts[str(raw_path)] = _sha(raw_path)
                record.grader_attempt_artifacts[str(diagnostics_path)] = _sha(diagnostics_path)
                manifest.grader_provider_calls += 1
                manifest.grader_reserved_cost_usd = round(manifest.grader_provider_calls * (0.5 / 24), 12)
                scores = {item.criterion_id: item.score for item in draft.criteria}
                weighted = round(sum(scores[key] * RUBRIC_WEIGHTS[key] for key in RUBRIC_WEIGHTS), 6)
                review = ScreeningGraderReviewV1(**draft.model_dump(mode="json"), weighted_score=weighted)
                review_path = output / "grader" / record.blind_task_id / "review.json"
                _write(review_path, review.model_dump(mode="json"))
                record.grader_status, record.grader_review_path, record.grader_review_sha256 = "completed", str(review_path), _sha(review_path)
                return
            except Exception as exc:
                if not raw_path.exists():
                    raw_path.parent.mkdir(parents=True, exist_ok=True); raw_path.write_text(getattr(executor, "last_raw_response_content", ""), encoding="utf-8")
                _write(diagnostics_path, {"error_type": type(exc).__name__, "failure_code": getattr(exc, "failure_code", "schema_failure"), **getattr(executor, "last_diagnostics", {})})
                record.grader_attempt_artifacts[str(raw_path)] = _sha(raw_path)
                record.grader_attempt_artifacts[str(diagnostics_path)] = _sha(diagnostics_path)
                if getattr(exc, "failure_code", None) != "input_token_ceiling":
                    manifest.grader_provider_calls += 1
                    manifest.grader_reserved_cost_usd = round(manifest.grader_provider_calls * (0.5 / 24), 12)
                if attempt == 1:
                    record.grader_first_failure_path = str(diagnostics_path)
                eligible = isinstance(exc, (SemanticReviewExecutionError, ValueError)) and (not isinstance(exc, SemanticReviewExecutionError) or exc.retry_eligible or exc.failure_code in {"invalid_json", "schema_failure", "empty_response", "truncated_response"})
                if attempt == 1 and eligible:
                    first_feedback = "Return valid JSON matching the required schema; preserve the same substantive judgment."
                    continue
                record.grader_status = "infrastructure_failed"
                return

    def _observations(self, campaign, manifest):
        by_id = {item.blind_task_id: item for item in manifest.records}
        rows = []
        for assignment in campaign.assignments:
            record = by_id[assignment.blind_task_id]
            validity = ValidityVectorV1.model_validate_json((Path(assignment.package_root) / "governance" / "validity_vector.json").read_text(encoding="utf-8"))
            utility = UtilityProfileV1.model_validate_json((Path(assignment.package_root) / "governance" / "utility_profile.json").read_text(encoding="utf-8"))
            review = ScreeningGraderReviewV1.model_validate_json(Path(record.grader_review_path).read_text(encoding="utf-8")) if record.grader_review_path else None
            rows.append(ScreeningTaskObservationV1(
                blind_task_id=assignment.blind_task_id, route_id=assignment.route_id,
                motif=assignment.motif, replicate_id=assignment.replicate_id,
                infrastructure_complete=record.solver_status != "infrastructure_failed" and record.grader_status != "infrastructure_failed",
                offline_validity_pass=validity.overall_status != "blocked",
                exact_valid_delivery=record.delivery_valid,
                major_defect=review.major_defect if review else False,
                professional_plausibility_pass=review.professional_plausibility == "pass" if review else False,
                productive_complexity_pass=utility.productive_complexity_coverage == 1.0 and all(item.status != "blocked" for item in utility.productive_complexity),
                skill_causal_pass=utility.skill_causal_coverage == 1.0,
                effective_rubric_dimensions=review.effective_rubric_dimensions if review else 0,
                weighted_score=review.weighted_score if review else None,
            ))
        return rows

    def _validate_request(self, request, request_sha):
        campaign = self.campaign.read()
        candidate_root = self.root / "blind_staging" / "candidate_packages"
        parity = Path(request.parity_report_path)
        selection = Path(request.selected_solver.preflight_report_path)
        checks = {
            "active": self.current_request.is_file() and _sha(self.current_request) == request_sha,
            "immutable": (self.immutable_root / f"{request_sha}.json").is_file() and _sha(self.immutable_root / f"{request_sha}.json") == request_sha,
            "campaign": request.campaign_manifest_sha256 == _sha(self.campaign.manifest_path),
            "staging": request.staging_report_sha256 == _sha(self.root / "blind_staging" / "governance" / "route_blind_staging_report.json"),
            "selection": (self.root / "governance" / "solver_selection.json").is_file() and request.solver_selection_sha256 == _sha(self.root / "governance" / "solver_selection.json"),
            "parity": parity.is_file() and request.parity_report_sha256 == _sha(parity),
            "source": request.source_fingerprint == governed_source_fingerprint(Path(__file__).resolve().parents[2]) == campaign.source_fingerprint,
            "preflight": selection.is_file() and _sha(selection) == request.selected_solver.preflight_report_sha256,
        }
        for assignment in campaign.assignments:
            checks[f"package:{assignment.blind_task_id}"] = request.blind_package_fingerprints.get(assignment.blind_task_id) == assignment.package_fingerprint
            checks[f"tree:{assignment.blind_task_id}"] = request.candidate_tree_sha256.get(assignment.blind_task_id) == _tree(candidate_root / assignment.blind_task_id)
            checks[f"reality:{assignment.blind_task_id}"] = request.reality_evidence_sha256.get(assignment.blind_task_id) == assignment.reality_evidence_sha256
        failed = sorted(key for key, value in checks.items() if not value)
        if failed: raise PermissionError("matched_business_request_state_mismatch:" + ",".join(failed))
