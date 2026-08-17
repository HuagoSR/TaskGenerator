from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_codex_local_solver import (
    CodexLocalCLIIdentityV1,
    CodexLocalScreeningScopeV1,
    CodexLocalTaskBindingV1,
    _expected_deliverable,
    _projection_tree,
    _sha_file,
    _tree,
)
from task_generator.v3_representative_production_pilot import (
    RepresentativePilotPackageReadinessV1,
    _tree_sha,
)
from task_generator.v3_representative_reality import (
    RepresentativeRealityResultV1,
    RepresentativeRealityScopeV1,
)
from task_generator.v3_source_fingerprint import governed_source_fingerprint


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if path.exists() and path.read_bytes() != encoded:
        raise ValueError("representative_codex_immutable_collision")
    path.write_bytes(encoded)


class RepresentativeCodexAssignmentV1(BaseModel):
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
    package_root: str
    package_fingerprint: str = Field(min_length=64, max_length=64)
    candidate_tree_sha256: str = Field(min_length=64, max_length=64)
    reality_evidence_sha256: str = Field(min_length=64, max_length=64)


class RepresentativeCodexCampaignV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campaign_version: Literal["v3.representative_codex_campaign.1"] = (
        "v3.representative_codex_campaign.1"
    )
    campaign_id: str
    package_readiness_sha256: str = Field(min_length=64, max_length=64)
    reality_scope_sha256: str = Field(min_length=64, max_length=64)
    reality_result_sha256: str = Field(min_length=64, max_length=64)
    assignments: List[RepresentativeCodexAssignmentV1] = Field(
        min_length=24, max_length=24
    )
    reality_decision: Literal["screening_ready"] = "screening_ready"
    professional_validity: Literal[
        "provisional_ai_assumed_sufficient_for_pilot"
    ] = "provisional_ai_assumed_sufficient_for_pilot"
    training_authorized: Literal[False] = False
    registry_mutation_authorized: Literal[False] = False
    release_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_matrix(self) -> "RepresentativeCodexCampaignV1":
        if len({item.blind_task_id for item in self.assignments}) != 24:
            raise ValueError("representative_codex_task_identity_duplicate")
        cells = {
            (
                item.route_id,
                item.motif,
                item.replicate_id,
                item.domain,
            )
            for item in self.assignments
        }
        if len(cells) != 24:
            raise ValueError("representative_codex_matrix_incomplete")
        return self


def compile_representative_codex_scope(
    *,
    campaign_root: str | Path,
    package_readiness_path: str | Path,
    reality_scope_path: str | Path,
    reality_result_path: str | Path,
    parity_report_path: str | Path,
    cli_identity: CodexLocalCLIIdentityV1,
    repository_root: str | Path,
    output_root: str | Path,
) -> tuple[CodexLocalScreeningScopeV1, Path, str]:
    root = Path(campaign_root).resolve()
    readiness_path = Path(package_readiness_path).resolve()
    reality_scope_file = Path(reality_scope_path).resolve()
    reality_result_file = Path(reality_result_path).resolve()
    parity_path = Path(parity_report_path).resolve()
    output = Path(output_root).resolve()

    readiness = RepresentativePilotPackageReadinessV1.model_validate_json(
        readiness_path.read_text(encoding="utf-8")
    )
    reality_scope = RepresentativeRealityScopeV1.model_validate_json(
        reality_scope_file.read_text(encoding="utf-8")
    )
    reality_result = RepresentativeRealityResultV1.model_validate_json(
        reality_result_file.read_text(encoding="utf-8")
    )
    parity = json.loads(parity_path.read_text(encoding="utf-8"))
    source_fingerprint = governed_source_fingerprint(repository_root)
    if not (
        readiness.decision == "packages_ready"
        and len(readiness.packages) == 24
        and reality_result.decision == "screening_ready"
        and reality_result.screening_eligible
        and len(reality_result.cases) == 24
    ):
        raise ValueError("representative_codex_upstream_not_ready")
    if not (
        parity.get("passed") is True
        and parity.get("network_mode") == "none"
        and parity.get("read_only_root") is True
        and parity.get("provider_credentials_mounted") is False
        and parity.get("cleanup_returncode") == 0
        and parity.get("source_fingerprint") == source_fingerprint
    ):
        raise ValueError("representative_codex_parity_invalid")

    scope_cases = {item.case_id: item for item in reality_scope.cases}
    result_cases = {item.case_id: item for item in reality_result.cases}
    if set(scope_cases) != set(result_cases) or set(scope_cases) != {
        item.blind_task_id for item in readiness.packages
    }:
        raise ValueError("representative_codex_reality_identity_mismatch")

    candidate_root = root / "reality" / "blind_staging" / "candidate_packages"
    assignments: List[RepresentativeCodexAssignmentV1] = []
    bindings: List[CodexLocalTaskBindingV1] = []
    for package in sorted(readiness.packages, key=lambda item: item.blind_task_id):
        case_id = package.blind_task_id
        blind = candidate_root / case_id
        if (
            _tree_sha(Path(package.package_root)) != package.package_fingerprint
            or _tree_sha(blind) != scope_cases[case_id].candidate_tree_sha256
            or result_cases[case_id].overall_decision != "pass"
        ):
            raise ValueError("representative_codex_upstream_hash_drift")
        case_payload = json.dumps(
            result_cases[case_id].model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        evidence_sha = _sha_bytes(case_payload)
        assignments.append(
            RepresentativeCodexAssignmentV1(
                blind_task_id=case_id,
                brief_id=package.brief_id,
                route_id=package.route_id,
                motif=package.motif,
                replicate_id=package.replicate_id,
                domain=package.domain,
                package_root=package.package_root,
                package_fingerprint=package.package_fingerprint,
                candidate_tree_sha256=_tree(blind),
                reality_evidence_sha256=evidence_sha,
            )
        )
        bindings.append(
            CodexLocalTaskBindingV1(
                blind_task_id=case_id,
                brief_id=package.brief_id,
                route_id=package.route_id,
                motif=package.motif,
                replicate_id=package.replicate_id,
                domain=package.domain,
                package_fingerprint=package.package_fingerprint,
                candidate_tree_sha256=_tree(blind),
                candidate_projection_sha256=_projection_tree(blind),
                reality_evidence_sha256=evidence_sha,
                expected_deliverable=_expected_deliverable(blind),
            )
        )

    campaign = RepresentativeCodexCampaignV1(
        campaign_id=f"{readiness.campaign_id}_codex_local_v1",
        package_readiness_sha256=_sha_file(readiness_path),
        reality_scope_sha256=_sha_file(reality_scope_file),
        reality_result_sha256=_sha_file(reality_result_file),
        assignments=assignments,
    )
    campaign_path = root / "representative_codex_campaign.json"
    _write_json(campaign_path, campaign.model_dump(mode="json"))
    scope = CodexLocalScreeningScopeV1(
        scope_version="v3.codex_local_screening_scope.2",
        cohort_kind="representative_production_pilot",
        campaign_id=campaign.campaign_id,
        campaign_manifest_sha256=_sha_file(campaign_path),
        parity_report_sha256=_sha_file(parity_path),
        source_fingerprint=source_fingerprint,
        cli=cli_identity,
        task_bindings=bindings,
    )
    persisted = (
        json.dumps(
            scope.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    digest = _sha_bytes(persisted)
    scope_path = output / "governance" / "scopes" / f"{digest}.json"
    scope_path.parent.mkdir(parents=True, exist_ok=True)
    if scope_path.exists() and scope_path.read_bytes() != persisted:
        raise ValueError("representative_codex_scope_immutable_collision")
    scope_path.write_bytes(persisted)
    return scope, scope_path, digest
