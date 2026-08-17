from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Literal, Optional

from openpyxl import Workbook
from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_codex_local_grader import (
    CodexLocalGraderManifestV1,
    CodexLocalGraderOutcomeV1,
    CodexLocalGraderRunnerV1,
)
from task_generator.v3_codex_local_solver import (
    CodexLocalCLIIdentityV1,
    CodexLocalCampaignManifestV1,
    CodexLocalProcessOutcomeV1,
    CodexLocalTooling,
    _atomic_json,
    _copy_projection,
    _expected_deliverable,
    _now,
    _prompt,
    _projection_tree,
    _sanitized_environment,
    _sha_file,
    _terminate_process_tree,
    _tree,
    inspect_delivery,
    parse_codex_jsonl,
)
from task_generator.v3_compact_screening_grader import (
    CompactGraderBindingV2,
    CompactGraderReviewV2,
)
from task_generator.v3_external_model_policy import (
    enforce_external_model_policy,
)
from task_generator.v3_representative_codex_local import (
    RepresentativeCodexCampaignV1,
)
from task_generator.v3_source_fingerprint import governed_source_fingerprint


EXTERNAL_MODELS = ("gemini-3.1-pro-preview", "deepseek-v4-pro")
PUBLIC_PROBE_TIMEOUT_SECONDS = 300
TASK_TIMEOUT_SECONDS = 1800
INFRASTRUCTURE_FREEZE_THRESHOLD = 3


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _redact(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED_SECRET]") if secret else value


def _assert_secret_absent(value: str, secret: str) -> None:
    if secret and secret in value:
        raise ValueError("external_comparison_secret_persistence_blocked")


class ExternalStackSpecV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stack_id: Literal[
        "gemini-3.1-pro-preview@tuzi_codex",
        "deepseek-v4-pro@tuzi_codex",
    ]
    provider: Literal["tuzi"] = "tuzi"
    model: Literal["gemini-3.1-pro-preview", "deepseek-v4-pro"]
    base_url: str
    wire_api: Literal["responses"] = "responses"
    request_max_retries: Literal[0] = 0
    stream_max_retries: Literal[0] = 0
    runner_retry_count: Literal[0] = 0

    @model_validator(mode="after")
    def validate_identity(self) -> "ExternalStackSpecV1":
        if self.stack_id != f"{self.model}@tuzi_codex":
            raise ValueError("external_stack_identity_mismatch")
        enforce_external_model_policy(self.provider, self.model)
        if not self.base_url.startswith("https://"):
            raise ValueError("external_stack_https_required")
        return self


class ExternalComparisonTaskBindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    brief_id: str
    route_id: Literal["skill_guided_llm", "llm_led_hybrid"]
    motif: Literal[
        "fan_in_reconciliation",
        "cross_check_validation",
        "policy_application",
    ]
    replicate_id: Literal["a", "b"]
    domain: Literal["audit_compliance", "procurement_operations"]
    source_package_path: str
    candidate_package_path: str
    package_fingerprint: str = Field(min_length=64, max_length=64)
    candidate_tree_sha256: str = Field(min_length=64, max_length=64)
    candidate_projection_sha256: str = Field(min_length=64, max_length=64)
    reality_evidence_sha256: str = Field(min_length=64, max_length=64)
    expected_deliverable: str


class ExternalModelComparisonCampaignV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_version: Literal["v3.external_model_comparison_campaign.1"] = (
        "v3.external_model_comparison_campaign.1"
    )
    campaign_id: str
    representative_campaign_path: str
    representative_campaign_sha256: str = Field(
        min_length=64, max_length=64
    )
    baseline_solver_manifest_path: str
    baseline_solver_manifest_sha256: str = Field(
        min_length=64, max_length=64
    )
    baseline_grader_manifest_path: str
    baseline_grader_manifest_sha256: str = Field(
        min_length=64, max_length=64
    )
    baseline_grader_outcome_path: str
    baseline_grader_outcome_sha256: str = Field(
        min_length=64, max_length=64
    )
    parity_report_path: str
    parity_report_sha256: str = Field(min_length=64, max_length=64)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    cli: CodexLocalCLIIdentityV1
    baseline_stack_id: Literal[
        "gpt-5.6-sol@chatgpt_codex"
    ] = "gpt-5.6-sol@chatgpt_codex"
    external_stacks: List[ExternalStackSpecV1] = Field(
        min_length=2, max_length=2
    )
    task_bindings: List[ExternalComparisonTaskBindingV1] = Field(
        min_length=24, max_length=24
    )
    public_probe_timeout_seconds: Literal[300] = (
        PUBLIC_PROBE_TIMEOUT_SECONDS
    )
    task_timeout_seconds: Literal[1800] = TASK_TIMEOUT_SECONDS
    attempts_per_task: Literal[1] = 1
    infrastructure_freeze_threshold: Literal[3] = (
        INFRASTRUCTURE_FREEZE_THRESHOLD
    )
    private_task_upload_authorized: Literal[True] = True
    training_authorized: Literal[False] = False
    release_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_matrix(self) -> "ExternalModelComparisonCampaignV1":
        if {item.model for item in self.external_stacks} != set(
            EXTERNAL_MODELS
        ):
            raise ValueError("external_comparison_model_cohort_mismatch")
        if len({item.blind_task_id for item in self.task_bindings}) != 24:
            raise ValueError("external_comparison_task_identity_duplicate")
        cells = {
            (
                item.domain,
                item.route_id,
                item.motif,
                item.replicate_id,
            )
            for item in self.task_bindings
        }
        if len(cells) != 24:
            raise ValueError("external_comparison_matrix_incomplete")
        return self


class ExternalComparisonReceiptV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receipt_version: Literal["v3.external_model_comparison_receipt.1"] = (
        "v3.external_model_comparison_receipt.1"
    )
    scope_sha256: str = Field(min_length=64, max_length=64)
    authorization_basis: Literal[
        "user_external_model_comparison_authorization"
    ] = "user_external_model_comparison_authorization"
    issued_at: str
    consumed_at: Optional[str] = None


TaskStatus = Literal[
    "not_started",
    "running",
    "completed",
    "interrupted",
]


class ExternalTaskExecutionRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    status: TaskStatus = "not_started"
    outcome_path: Optional[str] = None
    outcome_sha256: Optional[str] = None


class ExternalStackExecutionRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stack_id: str
    status: Literal[
        "prepared",
        "running",
        "probe_failed",
        "solver_completed",
        "frozen_systemic_failure",
        "incomplete",
    ] = "prepared"
    public_probe_status: TaskStatus = "not_started"
    public_probe_outcome_path: Optional[str] = None
    public_probe_outcome_sha256: Optional[str] = None
    tasks: Dict[str, ExternalTaskExecutionRecordV1]
    systemic_failure_code: Optional[str] = None


class ExternalComparisonExecutionManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal[
        "v3.external_model_comparison_execution.1"
    ] = "v3.external_model_comparison_execution.1"
    scope_path: str
    scope_sha256: str = Field(min_length=64, max_length=64)
    receipt_path: str
    receipt_sha256: str = Field(min_length=64, max_length=64)
    status: Literal[
        "prepared",
        "running",
        "solver_completed",
        "incomplete",
    ]
    stacks: Dict[str, ExternalStackExecutionRecordV1]
    created_at: str
    updated_at: str


class ExternalComparisonGradeRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blind_task_id: str
    status: Literal[
        "not_started",
        "running",
        "completed",
        "interrupted",
        "not_eligible",
        "infrastructure_failed",
        "grading_failed",
    ] = "not_started"
    attempt_count: int = Field(ge=0, le=1)
    workspace_path: Optional[str] = None
    jsonl_path: Optional[str] = None
    stderr_path: Optional[str] = None
    raw_grade_path: Optional[str] = None
    review_path: Optional[str] = None
    review_sha256: Optional[str] = None
    duration_seconds: Optional[float] = None
    first_failure: Optional[str] = None


class ExternalComparisonGraderManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal[
        "v3.external_model_comparison_grader.1"
    ] = "v3.external_model_comparison_grader.1"
    scope_sha256: str = Field(min_length=64, max_length=64)
    execution_manifest_sha256: str = Field(min_length=64, max_length=64)
    baseline_grader_outcome_sha256: str = Field(
        min_length=64, max_length=64
    )
    status: Literal["prepared", "running", "completed", "incomplete"]
    records: Dict[str, Dict[str, ExternalComparisonGradeRecordV1]]
    created_at: str
    updated_at: str


class ExternalTaskObservationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stack_id: str
    blind_task_id: str
    domain: str
    motif: str
    route_id: str
    attempted: bool
    infrastructure_complete: bool
    exact_valid_delivery: bool
    task_failed: bool
    grade_complete: bool
    major_defect: Optional[bool] = None
    professional_plausibility: Optional[Literal["pass", "fail"]] = None
    weighted_score: Optional[float] = None
    duration_seconds: float = 0.0
    usage: Dict[str, int] = Field(default_factory=dict)


class ExternalStackSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stack_id: str
    public_probe_pass: bool
    attempted_task_count: int
    infrastructure_failure_count: int
    task_failure_count: int
    valid_delivery_count: int
    completed_grade_count: int
    major_defect_count: int
    professional_plausibility_count: int
    mean_weighted_score: Optional[float] = None
    saturation_count: int
    total_duration_seconds: float
    total_usage: Dict[str, int]
    capability_comparison_eligible: bool


class PairwiseStackComparisonV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_stack_id: str
    right_stack_id: str
    common_graded_task_count: int
    left_wins: int
    right_wins: int
    ties: int
    mean_score_delta_left_minus_right: Optional[float] = None
    decision: Literal[
        "left_substantive_winner",
        "right_substantive_winner",
        "practical_tie",
        "insufficient_common_coverage",
    ]


class ExternalStackSliceSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stack_id: str
    axis: Literal["domain", "motif"]
    value: str
    task_count: int
    attempted_task_count: int
    infrastructure_failure_count: int
    task_failure_count: int
    valid_delivery_count: int
    completed_grade_count: int
    major_defect_count: int
    professional_plausibility_count: int
    mean_weighted_score: Optional[float] = None


class ExternalModelComparisonResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_version: Literal["v3.external_model_comparison_result.1"] = (
        "v3.external_model_comparison_result.1"
    )
    campaign_id: str
    scope_sha256: str = Field(min_length=64, max_length=64)
    execution_manifest_sha256: str = Field(min_length=64, max_length=64)
    grader_manifest_sha256: str = Field(min_length=64, max_length=64)
    observations: List[ExternalTaskObservationV1]
    stack_summaries: List[ExternalStackSummaryV1]
    domain_summaries: List[ExternalStackSliceSummaryV1]
    motif_summaries: List[ExternalStackSliceSummaryV1]
    pairwise_comparisons: List[PairwiseStackComparisonV1]
    practical_ranking: List[str]
    decision: Literal[
        "comparison_complete",
        "comparison_partial_one_external",
        "comparison_incomplete",
    ]
    professional_validity: Literal["provisional"] = "provisional"
    expert_evidence_present: Literal[False] = False
    default_solver_change_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    release_authorized: Literal[False] = False
    promotion_authorized: Literal[False] = False


def _external_config(spec: ExternalStackSpecV1) -> str:
    return (
        f"model = {json.dumps(spec.model)}\n"
        'model_provider = "tuzi"\n'
        "[model_providers.tuzi]\n"
        'name = "Tuzi"\n'
        f"base_url = {json.dumps(spec.base_url.rstrip('/'))}\n"
        'env_key = "TUZI_API_KEY"\n'
        'wire_api = "responses"\n'
        "request_max_retries = 0\n"
        "stream_max_retries = 0\n"
    )


def _external_command(
    executable: Path,
    workspace: Path,
    model: str,
) -> List[str]:
    return [
        str(executable),
        "--ask-for-approval",
        "never",
        "--model",
        model,
        "exec",
        "-c",
        "project_doc_max_bytes=0",
        "-c",
        "agents.enabled=false",
        "--disable",
        "plugins",
        "--disable",
        "apps",
        "--disable",
        "multi_agent",
        "--disable",
        "skill_search",
        "--json",
        "--ephemeral",
        "--ignore-rules",
        "--sandbox",
        "danger-full-access",
        "--skip-git-repo-check",
        "-C",
        str(workspace),
        "-",
    ]


def _write_public_fixture(workspace: Path) -> str:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "reference_files").mkdir(exist_ok=True)
    (workspace / "deliverable_files").mkdir(exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Source"
    sheet.append(["Item", "Amount"])
    sheet.append(["A", 12])
    sheet.append(["B", 30])
    workbook.save(workspace / "reference_files" / "public_source.xlsx")
    _atomic_json(
        workspace / "dataset_row.json",
        {
            "task_id": "public_external_comparison_probe",
            "prompt": (
                "Create an XLSX summary containing both source rows, a total, "
                "and a Notes sheet stating that this is a public fixture."
            ),
        },
    )
    _atomic_json(
        workspace / "deliverable_contract.json",
        {
            "deliverables": [
                {
                    "relative_path": (
                        "deliverable_files/external_comparison_probe.xlsx"
                    )
                }
            ]
        },
    )
    return "deliverable_files/external_comparison_probe.xlsx"


def compile_external_comparison_scope(
    *,
    representative_campaign_path: str | Path,
    baseline_solver_manifest_path: str | Path,
    baseline_grader_manifest_path: str | Path,
    baseline_grader_outcome_path: str | Path,
    parity_report_path: str | Path,
    cli_identity: CodexLocalCLIIdentityV1,
    repository_root: str | Path,
    output_root: str | Path,
    base_url: str,
) -> tuple[ExternalModelComparisonCampaignV1, Path, Path]:
    campaign_path = Path(representative_campaign_path).resolve()
    solver_manifest_path = Path(baseline_solver_manifest_path).resolve()
    grader_manifest_path = Path(baseline_grader_manifest_path).resolve()
    grader_outcome_path = Path(baseline_grader_outcome_path).resolve()
    parity_path = Path(parity_report_path).resolve()
    campaign = RepresentativeCodexCampaignV1.model_validate_json(
        campaign_path.read_text(encoding="utf-8")
    )
    solver_manifest = CodexLocalCampaignManifestV1.model_validate_json(
        solver_manifest_path.read_text(encoding="utf-8")
    )
    grader_manifest = CodexLocalGraderManifestV1.model_validate_json(
        grader_manifest_path.read_text(encoding="utf-8")
    )
    grader_outcome = CodexLocalGraderOutcomeV1.model_validate_json(
        grader_outcome_path.read_text(encoding="utf-8")
    )
    fingerprint = governed_source_fingerprint(repository_root)
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    if not (
        campaign.reality_decision == "screening_ready"
        and solver_manifest.status == "solver_completed"
        and len(solver_manifest.task_outcome_paths) == 24
        and grader_manifest.status == "completed"
        and grader_manifest.result_sha256 == _sha_file(grader_outcome_path)
        and grader_outcome.completed_grades == 24
        and grader_outcome.screening_result.decision
        == "production_candidate_both"
        and parity.get("passed") is True
        and parity.get("network_mode") == "none"
        and parity.get("read_only_root") is True
        and parity.get("provider_credentials_mounted") is False
        and parity.get("cleanup_returncode") == 0
        and parity.get("source_fingerprint") == fingerprint
    ):
        raise ValueError("external_comparison_upstream_not_ready")
    if (
        set(solver_manifest.task_outcome_paths)
        != {item.blind_task_id for item in campaign.assignments}
        or any(
            CodexLocalProcessOutcomeV1.model_validate_json(
                Path(path).read_text(encoding="utf-8")
            ).status
            != "pass"
            for path in solver_manifest.task_outcome_paths.values()
        )
        or set(grader_manifest.records)
        != {item.blind_task_id for item in campaign.assignments}
        or any(
            item.status != "completed"
            for item in grader_manifest.records.values()
        )
    ):
        raise ValueError("external_comparison_baseline_incomplete")
    candidate_root = (
        campaign_path.parent
        / "reality"
        / "blind_staging"
        / "candidate_packages"
    )
    bindings = []
    for assignment in sorted(
        campaign.assignments, key=lambda item: item.blind_task_id
    ):
        candidate = candidate_root / assignment.blind_task_id
        expected = _expected_deliverable(candidate)
        bindings.append(
            ExternalComparisonTaskBindingV1(
                blind_task_id=assignment.blind_task_id,
                brief_id=assignment.brief_id,
                route_id=assignment.route_id,
                motif=assignment.motif,
                replicate_id=assignment.replicate_id,
                domain=assignment.domain,
                source_package_path=assignment.package_root,
                candidate_package_path=str(candidate),
                package_fingerprint=assignment.package_fingerprint,
                candidate_tree_sha256=_tree(candidate),
                candidate_projection_sha256=_projection_tree(candidate),
                reality_evidence_sha256=(
                    assignment.reality_evidence_sha256
                ),
                expected_deliverable=expected,
            )
        )
    scope = ExternalModelComparisonCampaignV1(
        campaign_id=f"{campaign.campaign_id}_external_stack_v1",
        representative_campaign_path=str(campaign_path),
        representative_campaign_sha256=_sha_file(campaign_path),
        baseline_solver_manifest_path=str(solver_manifest_path),
        baseline_solver_manifest_sha256=_sha_file(solver_manifest_path),
        baseline_grader_manifest_path=str(grader_manifest_path),
        baseline_grader_manifest_sha256=_sha_file(grader_manifest_path),
        baseline_grader_outcome_path=str(grader_outcome_path),
        baseline_grader_outcome_sha256=_sha_file(grader_outcome_path),
        parity_report_path=str(parity_path),
        parity_report_sha256=_sha_file(parity_path),
        source_fingerprint=fingerprint,
        cli=cli_identity,
        external_stacks=[
            ExternalStackSpecV1(
                stack_id=f"{model}@tuzi_codex",
                model=model,
                base_url=base_url,
            )
            for model in EXTERNAL_MODELS
        ],
        task_bindings=bindings,
    )
    encoded = _canonical_bytes(scope.model_dump(mode="json"))
    digest = _sha_bytes(encoded)
    root = Path(output_root).resolve()
    scope_path = root / "governance" / "scopes" / f"{digest}.json"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    if scope_path.exists() and scope_path.read_bytes() != encoded:
        raise ValueError("external_comparison_scope_immutable_collision")
    scope_path.write_bytes(encoded)
    receipt = ExternalComparisonReceiptV1(
        scope_sha256=digest,
        issued_at=_now(),
    )
    receipt_path = root / "governance" / "receipts" / f"{digest}.json"
    if receipt_path.exists():
        raise FileExistsError("external_comparison_receipt_exists")
    _atomic_json(receipt_path, receipt.model_dump(mode="json"))
    return scope, scope_path, receipt_path


def _failure_code(
    stdout: str,
    stderr: str,
    *,
    timed_out: bool,
    command_seen: bool,
    returncode: Optional[int],
) -> Optional[str]:
    # Codex JSONL contains candidate-visible task text as well as error events.
    # Classifying the complete stream can therefore mistake domain phrases such
    # as "unauthorized" or HTTP status codes inside the task for provider
    # failures.  Restrict stdout evidence to structured terminal error events;
    # stderr remains diagnostic-only process output and is safe to inspect in
    # full.
    error_signals: list[str] = []
    parsed_jsonl_line = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        parsed_jsonl_line = True
        if not isinstance(event, dict) or event.get("type") not in {
            "error",
            "turn.failed",
        }:
            continue
        error_signals.append(json.dumps(event, ensure_ascii=False, sort_keys=True))
    if not parsed_jsonl_line:
        error_signals.append(stdout)
    text = f"{'\n'.join(error_signals)}\n{stderr}".lower()
    if any(
        marker in text
        for marker in (
            "authentication",
            "unauthorized",
            "invalid api key",
            "401",
            "403",
        )
    ):
        return "authentication_failure"
    if any(
        marker in text
        for marker in (
            "stream disconnected",
            "incomplete chunked read",
            "peer closed connection",
            "incomplete body",
        )
    ):
        return "stream_transport_failure"
    if any(
        marker in text
        for marker in (
            "/responses",
            "unsupported",
            "protocol",
            "response.completed",
        )
    ) and returncode not in (0, None):
        return "responses_protocol_failure"
    if any(
        marker in text
        for marker in (
            "service unavailable",
            "failed to connect",
            "connection refused",
            "502",
            "503",
        )
    ):
        return "service_failure"
    if timed_out and not command_seen:
        return "timeout_without_tool_activity"
    return None


class ExternalComparisonRunner:
    def __init__(
        self,
        *,
        scope_path: str | Path,
        receipt_path: str | Path,
        output_root: str | Path,
        python_executable: str | Path,
        tuzi_api_key: str,
        popen_factory=subprocess.Popen,
    ) -> None:
        self.scope_path = Path(scope_path).resolve()
        self.receipt_path = Path(receipt_path).resolve()
        self.output = Path(output_root).resolve()
        self.python = Path(python_executable).resolve()
        self.secret = tuzi_api_key
        self.popen_factory = popen_factory
        self.scope = ExternalModelComparisonCampaignV1.model_validate_json(
            self.scope_path.read_text(encoding="utf-8")
        )
        self._validate_static()

    def _validate_static(self) -> None:
        if not self.secret:
            raise ValueError("external_comparison_tuzi_key_missing")
        if _sha_file(self.scope_path) != self.scope_path.stem:
            raise PermissionError("external_comparison_scope_hash_mismatch")
        if governed_source_fingerprint(
            Path(__file__).resolve().parents[2]
        ) != self.scope.source_fingerprint:
            raise PermissionError("external_comparison_source_drift")
        executable = Path(self.scope.cli.executable_path)
        if (
            not executable.is_file()
            or _sha_file(executable) != self.scope.cli.executable_sha256
            or CodexLocalTooling(executable.parents[2]).freeze_identity()
            != self.scope.cli
        ):
            raise PermissionError("external_comparison_cli_drift")
        for path, digest in (
            (
                self.scope.representative_campaign_path,
                self.scope.representative_campaign_sha256,
            ),
            (
                self.scope.baseline_solver_manifest_path,
                self.scope.baseline_solver_manifest_sha256,
            ),
            (
                self.scope.baseline_grader_manifest_path,
                self.scope.baseline_grader_manifest_sha256,
            ),
            (
                self.scope.baseline_grader_outcome_path,
                self.scope.baseline_grader_outcome_sha256,
            ),
            (
                self.scope.parity_report_path,
                self.scope.parity_report_sha256,
            ),
        ):
            if _sha_file(Path(path)) != digest:
                raise PermissionError("external_comparison_upstream_drift")
        for binding in self.scope.task_bindings:
            candidate = Path(binding.candidate_package_path)
            if (
                _tree(candidate) != binding.candidate_tree_sha256
                or _projection_tree(candidate)
                != binding.candidate_projection_sha256
            ):
                raise PermissionError(
                    "external_comparison_candidate_tree_drift"
                )

    def _new_manifest(self) -> ExternalComparisonExecutionManifestV1:
        tasks = {
            item.blind_task_id: ExternalTaskExecutionRecordV1(
                blind_task_id=item.blind_task_id
            )
            for item in self.scope.task_bindings
        }
        return ExternalComparisonExecutionManifestV1(
            scope_path=str(self.scope_path),
            scope_sha256=_sha_file(self.scope_path),
            receipt_path=str(self.receipt_path),
            receipt_sha256=_sha_file(self.receipt_path),
            status="prepared",
            stacks={
                spec.stack_id: ExternalStackExecutionRecordV1(
                    stack_id=spec.stack_id,
                    tasks={
                        key: value.model_copy(deep=True)
                        for key, value in tasks.items()
                    },
                )
                for spec in self.scope.external_stacks
            },
            created_at=_now(),
            updated_at=_now(),
        )

    def execute(self) -> tuple[ExternalComparisonExecutionManifestV1, Path]:
        manifest_path = self.output / "execution_manifest.json"
        if manifest_path.exists():
            manifest = ExternalComparisonExecutionManifestV1.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
        else:
            receipt = ExternalComparisonReceiptV1.model_validate_json(
                self.receipt_path.read_text(encoding="utf-8")
            )
            if (
                receipt.scope_sha256 != _sha_file(self.scope_path)
                or receipt.consumed_at is not None
            ):
                raise PermissionError(
                    "external_comparison_receipt_invalid_or_consumed"
                )
            receipt.consumed_at = _now()
            _atomic_json(
                self.receipt_path, receipt.model_dump(mode="json")
            )
            manifest = self._new_manifest()
            manifest.receipt_sha256 = _sha_file(self.receipt_path)
            _atomic_json(
                manifest_path, manifest.model_dump(mode="json")
            )
        for stack in manifest.stacks.values():
            if stack.public_probe_status == "running":
                stack.public_probe_status = "interrupted"
                stack.status = "incomplete"
            for record in stack.tasks.values():
                if record.status == "running":
                    record.status = "interrupted"
                    stack.status = "incomplete"
        manifest.status = "running"
        manifest.updated_at = _now()
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        specs = {item.stack_id: item for item in self.scope.external_stacks}
        bindings = {
            item.blind_task_id: item for item in self.scope.task_bindings
        }
        for stack_id in (
            "gemini-3.1-pro-preview@tuzi_codex",
            "deepseek-v4-pro@tuzi_codex",
        ):
            stack = manifest.stacks[stack_id]
            if stack.status in {
                "probe_failed",
                "solver_completed",
                "frozen_systemic_failure",
            }:
                continue
            spec = specs[stack_id]
            home = self.output / "runtime" / stack_id / "codex_home"
            home.mkdir(parents=True, exist_ok=True)
            (home / "config.toml").write_text(
                _external_config(spec), encoding="utf-8"
            )
            if stack.public_probe_status == "not_started":
                stack.status = "running"
                stack.public_probe_status = "running"
                manifest.updated_at = _now()
                _atomic_json(
                    manifest_path, manifest.model_dump(mode="json")
                )
                probe_workspace = (
                    self.output
                    / "execution"
                    / stack_id
                    / "public_probe"
                    / "workspace"
                )
                expected = _write_public_fixture(probe_workspace)
                outcome, outcome_path = self._run_one(
                    spec=spec,
                    codex_home=home,
                    kind="public_probe",
                    task_id="public_external_comparison_probe",
                    workspace=probe_workspace,
                    expected=expected,
                    timeout=self.scope.public_probe_timeout_seconds,
                )
                stack.public_probe_status = "completed"
                stack.public_probe_outcome_path = str(outcome_path)
                stack.public_probe_outcome_sha256 = _sha_file(outcome_path)
                if outcome.status != "pass":
                    stack.status = "probe_failed"
                    manifest.updated_at = _now()
                    _atomic_json(
                        manifest_path, manifest.model_dump(mode="json")
                    )
                    shutil.rmtree(home, ignore_errors=True)
                    continue
            elif stack.public_probe_status != "completed":
                stack.status = "incomplete"
                continue
            probe = CodexLocalProcessOutcomeV1.model_validate_json(
                Path(stack.public_probe_outcome_path).read_text(
                    encoding="utf-8"
                )
            )
            if probe.status != "pass":
                stack.status = "probe_failed"
                continue
            consecutive_code = None
            consecutive_count = 0
            for task_id in sorted(bindings):
                record = stack.tasks[task_id]
                if record.status != "not_started":
                    continue
                binding = bindings[task_id]
                workspace = (
                    self.output
                    / "execution"
                    / stack_id
                    / "tasks"
                    / task_id
                    / "workspace"
                )
                _copy_projection(
                    Path(binding.candidate_package_path), workspace
                )
                record.status = "running"
                manifest.updated_at = _now()
                _atomic_json(
                    manifest_path, manifest.model_dump(mode="json")
                )
                outcome, outcome_path = self._run_one(
                    spec=spec,
                    codex_home=home,
                    kind="private_task",
                    task_id=task_id,
                    workspace=workspace,
                    expected=binding.expected_deliverable,
                    timeout=self.scope.task_timeout_seconds,
                )
                record.status = "completed"
                record.outcome_path = str(outcome_path)
                record.outcome_sha256 = _sha_file(outcome_path)
                code = (
                    outcome.first_failure
                    if outcome.status == "infrastructure_failed"
                    else None
                )
                if code and code == consecutive_code:
                    consecutive_count += 1
                elif code:
                    consecutive_code = code
                    consecutive_count = 1
                else:
                    consecutive_code = None
                    consecutive_count = 0
                if (
                    consecutive_count
                    >= self.scope.infrastructure_freeze_threshold
                ):
                    stack.status = "frozen_systemic_failure"
                    stack.systemic_failure_code = code
                    break
                manifest.updated_at = _now()
                _atomic_json(
                    manifest_path, manifest.model_dump(mode="json")
                )
            if stack.status != "frozen_systemic_failure":
                if all(
                    item.status == "completed"
                    for item in stack.tasks.values()
                ):
                    stack.status = "solver_completed"
                else:
                    stack.status = "incomplete"
            shutil.rmtree(home, ignore_errors=True)
            manifest.updated_at = _now()
            _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        manifest.status = (
            "solver_completed"
            if all(
                stack.status in {
                    "solver_completed",
                    "probe_failed",
                    "frozen_systemic_failure",
                }
                for stack in manifest.stacks.values()
            )
            else "incomplete"
        )
        manifest.updated_at = _now()
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
        return manifest, manifest_path

    def _run_one(
        self,
        *,
        spec: ExternalStackSpecV1,
        codex_home: Path,
        kind: Literal["public_probe", "private_task"],
        task_id: str,
        workspace: Path,
        expected: str,
        timeout: int,
    ) -> tuple[CodexLocalProcessOutcomeV1, Path]:
        input_hashes = {
            _sha_file(path)
            for path in (workspace / "reference_files").glob("*.xlsx")
        }
        input_tree = _tree(workspace)
        command = _external_command(
            Path(self.scope.cli.executable_path),
            workspace,
            spec.model,
        )
        env = _sanitized_environment(codex_home)
        env["TUZI_API_KEY"] = self.secret
        started_at = _now()
        started = time.monotonic()
        process = self.popen_factory(
            command,
            cwd=str(workspace),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            ),
            start_new_session=os.name != "nt",
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(
                input=_prompt(expected, self.python),
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            _terminate_process_tree(process)
            tail_out, tail_err = process.communicate()
            stdout = (exc.stdout or "") + (tail_out or "")
            stderr = (exc.stderr or "") + (tail_err or "")
        stdout = _redact(stdout or "", self.secret)
        stderr = _redact(stderr or "", self.secret)
        diagnostics = parse_codex_jsonl(stdout)
        delivery = inspect_delivery(workspace, expected, input_hashes)
        failure_code = _failure_code(
            stdout,
            stderr,
            timed_out=timed_out,
            command_seen=diagnostics.command_event_seen,
            returncode=process.returncode,
        )
        if failure_code:
            status = "infrastructure_failed"
            first_failure = failure_code
        elif (
            process.returncode == 0
            and diagnostics.turn_seen
            and diagnostics.command_event_seen
            and delivery.valid
        ):
            status = "pass"
            first_failure = None
        else:
            status = "task_failed"
            first_failure = (
                "solver_timeout_with_tool_activity"
                if timed_out
                else delivery.failure or "solver_process_or_protocol_failure"
            )
        root = (
            self.output
            / "execution"
            / spec.stack_id
            / ("public_probe" if kind == "public_probe" else "tasks")
            / ("" if kind == "public_probe" else task_id)
        )
        root.mkdir(parents=True, exist_ok=True)
        jsonl_path = root / "codex.jsonl"
        stderr_path = root / "stderr.txt"
        jsonl_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        outcome = CodexLocalProcessOutcomeV1(
            kind=kind,
            blind_task_id=task_id,
            status=status,
            started_at=started_at,
            completed_at=_now(),
            duration_seconds=round(time.monotonic() - started, 3),
            returncode=process.returncode,
            timed_out=timed_out,
            command=command,
            workspace_path=str(workspace),
            workspace_input_tree_sha256=input_tree,
            jsonl_path=str(jsonl_path),
            jsonl_sha256=_sha_file(jsonl_path),
            stderr_path=str(stderr_path),
            stderr_sha256=_sha_file(stderr_path),
            diagnostics=diagnostics,
            delivery=delivery,
            output_tree_sha256=_tree(workspace),
            first_failure=first_failure,
        )
        _assert_secret_absent(outcome.model_dump_json(), self.secret)
        outcome_path = root / "outcome.json"
        _atomic_json(outcome_path, outcome.model_dump(mode="json"))
        return outcome, outcome_path


def grade_external_deliveries(
    *,
    scope_path: str | Path,
    execution_manifest_path: str | Path,
    output_root: str | Path,
    codex_home: str | Path,
    python_executable: str | Path,
) -> tuple[ExternalComparisonGraderManifestV1, Path]:
    scope_file = Path(scope_path).resolve()
    execution_file = Path(execution_manifest_path).resolve()
    output = Path(output_root).resolve()
    scope = ExternalModelComparisonCampaignV1.model_validate_json(
        scope_file.read_text(encoding="utf-8")
    )
    execution = ExternalComparisonExecutionManifestV1.model_validate_json(
        execution_file.read_text(encoding="utf-8")
    )
    if (
        execution.scope_sha256 != _sha_file(scope_file)
        or execution.status not in {"solver_completed", "incomplete"}
    ):
        raise ValueError("external_comparison_grader_upstream_invalid")
    manifest_path = output / "grader_manifest.json"
    if manifest_path.exists():
        manifest = ExternalComparisonGraderManifestV1.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    else:
        manifest = ExternalComparisonGraderManifestV1(
            scope_sha256=_sha_file(scope_file),
            execution_manifest_sha256=_sha_file(execution_file),
            baseline_grader_outcome_sha256=(
                scope.baseline_grader_outcome_sha256
            ),
            status="prepared",
            records={
                spec.stack_id: {
                    binding.blind_task_id: ExternalComparisonGradeRecordV1(
                        blind_task_id=binding.blind_task_id,
                        attempt_count=0,
                    )
                    for binding in scope.task_bindings
                }
                for spec in scope.external_stacks
            },
            created_at=_now(),
            updated_at=_now(),
        )
        _atomic_json(manifest_path, manifest.model_dump(mode="json"))
    if manifest.execution_manifest_sha256 != _sha_file(execution_file):
        raise PermissionError("external_comparison_execution_manifest_drift")
    manifest.status = "running"
    _atomic_json(manifest_path, manifest.model_dump(mode="json"))
    bindings = {item.blind_task_id: item for item in scope.task_bindings}
    for spec in scope.external_stacks:
        stack = execution.stacks[spec.stack_id]
        for task_id in sorted(bindings):
            record = manifest.records[spec.stack_id][task_id]
            if record.status == "running":
                record.status = "interrupted"
                continue
            if record.status != "not_started":
                continue
            solver_record = stack.tasks[task_id]
            if not solver_record.outcome_path:
                record.status = "not_eligible"
                record.first_failure = "solver_outcome_missing_not_eligible"
                continue
            solver_outcome = CodexLocalProcessOutcomeV1.model_validate_json(
                Path(solver_record.outcome_path).read_text(encoding="utf-8")
            )
            if solver_outcome.status != "pass" or not solver_outcome.delivery.valid:
                record.status = "not_eligible"
                record.first_failure = "invalid_delivery_not_eligible"
                continue
            binding = bindings[task_id]
            candidate = Path(binding.candidate_package_path)
            teacher = Path(binding.source_package_path)
            delivery = (
                Path(solver_outcome.workspace_path)
                / solver_outcome.delivery.relative_path
            )
            compact = CompactGraderBindingV2(
                blind_task_id=task_id,
                route_id=binding.route_id,
                motif=binding.motif,
                replicate_id=binding.replicate_id,
                domain=binding.domain,
                candidate_package_path=str(candidate),
                teacher_package_path=str(teacher),
                solver_outcome_sha256=_sha_file(
                    Path(solver_record.outcome_path)
                ),
                delivery_path=str(delivery),
                delivery_sha256=_sha_file(delivery),
                rubric_sha256=_sha_file(
                    teacher / "teacher" / "rubric_plan_v2.json"
                ),
                fact_anchors_sha256=_sha_file(
                    teacher
                    / "teacher"
                    / "deterministic_fact_anchors.json"
                ),
            )
            record.status = "running"
            record.attempt_count = 1
            manifest.updated_at = _now()
            _atomic_json(manifest_path, manifest.model_dump(mode="json"))
            runner = object.__new__(CodexLocalGraderRunnerV1)
            runner.output = output / "grader" / spec.stack_id
            runner.codex_home = Path(codex_home).resolve()
            runner.python = Path(python_executable).resolve()
            runner.popen_factory = subprocess.Popen
            runner.scope = SimpleNamespace(
                cli=scope.cli,
                timeout_seconds_per_task=TASK_TIMEOUT_SECONDS,
            )
            local_record = runner._run_one(compact)
            manifest.records[spec.stack_id][task_id] = (
                ExternalComparisonGradeRecordV1(
                    **local_record.model_dump(mode="json")
                )
            )
            manifest.updated_at = _now()
            _atomic_json(manifest_path, manifest.model_dump(mode="json"))
    manifest.status = (
        "completed"
        if all(
            record.status
            in {
                "completed",
                "not_eligible",
                "infrastructure_failed",
                "grading_failed",
                "interrupted",
            }
            for records in manifest.records.values()
            for record in records.values()
        )
        else "incomplete"
    )
    manifest.updated_at = _now()
    _atomic_json(manifest_path, manifest.model_dump(mode="json"))
    return manifest, manifest_path


def _summary(
    stack_id: str,
    observations: List[ExternalTaskObservationV1],
    public_probe_pass: bool,
) -> ExternalStackSummaryV1:
    rows = [item for item in observations if item.stack_id == stack_id]
    scores = [
        item.weighted_score
        for item in rows
        if item.grade_complete and item.weighted_score is not None
    ]
    total_usage: Dict[str, int] = {}
    for row in rows:
        for key, value in row.usage.items():
            total_usage[key] = total_usage.get(key, 0) + value
    valid = sum(item.exact_valid_delivery for item in rows)
    graded = sum(item.grade_complete for item in rows)
    return ExternalStackSummaryV1(
        stack_id=stack_id,
        public_probe_pass=public_probe_pass,
        attempted_task_count=sum(item.attempted for item in rows),
        infrastructure_failure_count=sum(
            item.attempted and not item.infrastructure_complete
            for item in rows
        ),
        task_failure_count=sum(item.task_failed for item in rows),
        valid_delivery_count=valid,
        completed_grade_count=graded,
        major_defect_count=sum(item.major_defect is True for item in rows),
        professional_plausibility_count=sum(
            item.professional_plausibility == "pass" for item in rows
        ),
        mean_weighted_score=(
            round(sum(scores) / len(scores), 6) if scores else None
        ),
        saturation_count=sum(score >= 0.9 for score in scores),
        total_duration_seconds=round(
            sum(item.duration_seconds for item in rows), 3
        ),
        total_usage=total_usage,
        capability_comparison_eligible=(
            public_probe_pass and valid >= 20 and graded == valid
        ),
    )


def _pairwise(
    left: ExternalStackSummaryV1,
    right: ExternalStackSummaryV1,
    observations: List[ExternalTaskObservationV1],
) -> PairwiseStackComparisonV1:
    left_rows = {
        item.blind_task_id: item
        for item in observations
        if item.stack_id == left.stack_id
        and item.grade_complete
        and item.weighted_score is not None
    }
    right_rows = {
        item.blind_task_id: item
        for item in observations
        if item.stack_id == right.stack_id
        and item.grade_complete
        and item.weighted_score is not None
    }
    common = sorted(set(left_rows) & set(right_rows))
    left_wins = sum(
        left_rows[key].weighted_score > right_rows[key].weighted_score
        for key in common
    )
    right_wins = sum(
        right_rows[key].weighted_score > left_rows[key].weighted_score
        for key in common
    )
    ties = len(common) - left_wins - right_wins
    delta = (
        round(
            sum(
                left_rows[key].weighted_score
                - right_rows[key].weighted_score
                for key in common
            )
            / len(common),
            6,
        )
        if common
        else None
    )
    if (
        len(common) < 20
        or not left.capability_comparison_eligible
        or not right.capability_comparison_eligible
    ):
        decision = "insufficient_common_coverage"
    elif left.valid_delivery_count - right.valid_delivery_count >= 3:
        decision = "left_substantive_winner"
    elif right.valid_delivery_count - left.valid_delivery_count >= 3:
        decision = "right_substantive_winner"
    elif right.major_defect_count - left.major_defect_count >= 2:
        decision = "left_substantive_winner"
    elif left.major_defect_count - right.major_defect_count >= 2:
        decision = "right_substantive_winner"
    elif delta is not None and delta >= 0.05:
        decision = "left_substantive_winner"
    elif delta is not None and delta <= -0.05:
        decision = "right_substantive_winner"
    else:
        decision = "practical_tie"
    return PairwiseStackComparisonV1(
        left_stack_id=left.stack_id,
        right_stack_id=right.stack_id,
        common_graded_task_count=len(common),
        left_wins=left_wins,
        right_wins=right_wins,
        ties=ties,
        mean_score_delta_left_minus_right=delta,
        decision=decision,
    )


def _slice_summaries(
    observations: List[ExternalTaskObservationV1],
    *,
    axis: Literal["domain", "motif"],
    values: tuple[str, ...],
    stack_ids: List[str],
) -> List[ExternalStackSliceSummaryV1]:
    summaries = []
    for stack_id in stack_ids:
        for value in values:
            rows = [
                item
                for item in observations
                if item.stack_id == stack_id
                and getattr(item, axis) == value
            ]
            scores = [
                item.weighted_score
                for item in rows
                if item.grade_complete and item.weighted_score is not None
            ]
            summaries.append(
                ExternalStackSliceSummaryV1(
                    stack_id=stack_id,
                    axis=axis,
                    value=value,
                    task_count=len(rows),
                    attempted_task_count=sum(
                        item.attempted for item in rows
                    ),
                    infrastructure_failure_count=sum(
                        item.attempted
                        and not item.infrastructure_complete
                        for item in rows
                    ),
                    task_failure_count=sum(
                        item.task_failed for item in rows
                    ),
                    valid_delivery_count=sum(
                        item.exact_valid_delivery for item in rows
                    ),
                    completed_grade_count=sum(
                        item.grade_complete for item in rows
                    ),
                    major_defect_count=sum(
                        item.major_defect is True for item in rows
                    ),
                    professional_plausibility_count=sum(
                        item.professional_plausibility == "pass"
                        for item in rows
                    ),
                    mean_weighted_score=(
                        round(sum(scores) / len(scores), 6)
                        if scores
                        else None
                    ),
                )
            )
    return summaries


def aggregate_external_comparison(
    *,
    scope_path: str | Path,
    execution_manifest_path: str | Path,
    grader_manifest_path: str | Path,
    output_path: str | Path,
) -> tuple[ExternalModelComparisonResultV1, Path]:
    scope_file = Path(scope_path).resolve()
    execution_file = Path(execution_manifest_path).resolve()
    grader_file = Path(grader_manifest_path).resolve()
    scope = ExternalModelComparisonCampaignV1.model_validate_json(
        scope_file.read_text(encoding="utf-8")
    )
    execution = ExternalComparisonExecutionManifestV1.model_validate_json(
        execution_file.read_text(encoding="utf-8")
    )
    grader = ExternalComparisonGraderManifestV1.model_validate_json(
        grader_file.read_text(encoding="utf-8")
    )
    if not (
        execution.scope_sha256 == _sha_file(scope_file)
        and grader.scope_sha256 == _sha_file(scope_file)
        and grader.execution_manifest_sha256 == _sha_file(execution_file)
        and grader.baseline_grader_outcome_sha256
        == scope.baseline_grader_outcome_sha256
    ):
        raise PermissionError("external_comparison_aggregate_hash_drift")
    baseline_outcome = CodexLocalGraderOutcomeV1.model_validate_json(
        Path(scope.baseline_grader_outcome_path).read_text(encoding="utf-8")
    )
    baseline_solver = CodexLocalCampaignManifestV1.model_validate_json(
        Path(scope.baseline_solver_manifest_path).read_text(encoding="utf-8")
    )
    bindings = {item.blind_task_id: item for item in scope.task_bindings}
    observations: List[ExternalTaskObservationV1] = []
    baseline_scores = {
        item.blind_task_id: item
        for item in baseline_outcome.screening_result.observations
    }
    for task_id in sorted(bindings):
        binding = bindings[task_id]
        solver_path = baseline_solver.task_outcome_paths[task_id]
        solver = CodexLocalProcessOutcomeV1.model_validate_json(
            Path(solver_path).read_text(encoding="utf-8")
        )
        score = baseline_scores[task_id]
        observations.append(
            ExternalTaskObservationV1(
                stack_id="gpt-5.6-sol@chatgpt_codex",
                blind_task_id=task_id,
                domain=binding.domain,
                motif=binding.motif,
                route_id=binding.route_id,
                attempted=True,
                infrastructure_complete=True,
                exact_valid_delivery=True,
                task_failed=False,
                grade_complete=True,
                major_defect=score.major_defect,
                professional_plausibility=(
                    "pass"
                    if score.professional_plausibility_pass
                    else "fail"
                ),
                weighted_score=score.weighted_score,
                duration_seconds=solver.duration_seconds,
                usage=solver.diagnostics.usage,
            )
        )
    for spec in scope.external_stacks:
        stack = execution.stacks[spec.stack_id]
        for task_id in sorted(bindings):
            binding = bindings[task_id]
            task = stack.tasks[task_id]
            outcome = (
                CodexLocalProcessOutcomeV1.model_validate_json(
                    Path(task.outcome_path).read_text(encoding="utf-8")
                )
                if task.outcome_path
                else None
            )
            grade_record = grader.records[spec.stack_id][task_id]
            review = (
                CompactGraderReviewV2.model_validate_json(
                    Path(grade_record.review_path).read_text(
                        encoding="utf-8"
                    )
                )
                if grade_record.status == "completed"
                and grade_record.review_path
                else None
            )
            observations.append(
                ExternalTaskObservationV1(
                    stack_id=spec.stack_id,
                    blind_task_id=task_id,
                    domain=binding.domain,
                    motif=binding.motif,
                    route_id=binding.route_id,
                    attempted=outcome is not None,
                    infrastructure_complete=(
                        outcome is not None
                        and outcome.status != "infrastructure_failed"
                    ),
                    exact_valid_delivery=(
                        outcome is not None
                        and outcome.status == "pass"
                        and outcome.delivery.valid
                    ),
                    task_failed=(
                        outcome is not None
                        and outcome.status == "task_failed"
                    ),
                    grade_complete=review is not None,
                    major_defect=review.major_defect if review else None,
                    professional_plausibility=(
                        review.professional_plausibility
                        if review
                        else None
                    ),
                    weighted_score=(
                        review.weighted_score if review else None
                    ),
                    duration_seconds=(
                        outcome.duration_seconds if outcome else 0.0
                    ),
                    usage=(
                        outcome.diagnostics.usage if outcome else {}
                    ),
                )
            )
    summaries = [
        _summary(
            "gpt-5.6-sol@chatgpt_codex",
            observations,
            public_probe_pass=True,
        )
    ]
    for spec in scope.external_stacks:
        stack = execution.stacks[spec.stack_id]
        probe = (
            CodexLocalProcessOutcomeV1.model_validate_json(
                Path(stack.public_probe_outcome_path).read_text(
                    encoding="utf-8"
                )
            )
            if stack.public_probe_outcome_path
            else None
        )
        summaries.append(
            _summary(
                spec.stack_id,
                observations,
                public_probe_pass=bool(
                    probe is not None and probe.status == "pass"
                ),
            )
        )
    by_stack = {item.stack_id: item for item in summaries}
    stack_ids = [
        "gpt-5.6-sol@chatgpt_codex",
        "gemini-3.1-pro-preview@tuzi_codex",
        "deepseek-v4-pro@tuzi_codex",
    ]
    pairs = [
        _pairwise(by_stack[left], by_stack[right], observations)
        for index, left in enumerate(stack_ids)
        for right in stack_ids[index + 1 :]
    ]
    ranking = sorted(
        stack_ids,
        key=lambda key: (
            -by_stack[key].valid_delivery_count,
            by_stack[key].major_defect_count,
            -by_stack[key].professional_plausibility_count,
            -(
                by_stack[key].mean_weighted_score
                if by_stack[key].mean_weighted_score is not None
                else -1.0
            ),
            by_stack[key].total_duration_seconds,
        ),
    )
    eligible_external = sum(
        by_stack[item.stack_id].capability_comparison_eligible
        for item in scope.external_stacks
    )
    decision = (
        "comparison_complete"
        if eligible_external == 2
        else (
            "comparison_partial_one_external"
            if eligible_external == 1
            else "comparison_incomplete"
        )
    )
    result = ExternalModelComparisonResultV1(
        campaign_id=scope.campaign_id,
        scope_sha256=_sha_file(scope_file),
        execution_manifest_sha256=_sha_file(execution_file),
        grader_manifest_sha256=_sha_file(grader_file),
        observations=observations,
        stack_summaries=summaries,
        domain_summaries=_slice_summaries(
            observations,
            axis="domain",
            values=("audit_compliance", "procurement_operations"),
            stack_ids=stack_ids,
        ),
        motif_summaries=_slice_summaries(
            observations,
            axis="motif",
            values=(
                "fan_in_reconciliation",
                "cross_check_validation",
                "policy_application",
            ),
            stack_ids=stack_ids,
        ),
        pairwise_comparisons=pairs,
        practical_ranking=ranking,
        decision=decision,
    )
    destination = Path(output_path).resolve()
    _atomic_json(destination, result.model_dump(mode="json"))
    return result, destination
