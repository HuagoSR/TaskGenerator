from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from task_generator.v3_route_comparison import (
    RouteComparisonAnalyzer,
    RouteComparisonManifestV1,
    RouteComparisonReportV1,
    RouteId,
)
from task_generator.v3_route_evidence_compiler import (
    RouteComparisonEvidenceCompileReportV1,
)


ConfirmationGate = Literal[
    "absolute_gates",
    "matched_environment",
    "server_candidate_reproduction",
    "rollback_verification",
    "major_validity_closure",
]


class ConfirmationGateEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate_version: Literal["v3.route_confirmation_gate_evidence.1"] = (
        "v3.route_confirmation_gate_evidence.1"
    )
    gate: ConfirmationGate
    comparison_id: str
    candidate_routes: List[RouteId] = Field(min_length=2, max_length=2)
    decision: Literal["pass", "blocked"]
    generator_independent: bool
    environment_id: Optional[str] = None
    evidence_paths: List[str] = Field(min_length=1)
    evidence_sha256: Dict[str, str]
    findings: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_shape(self) -> "ConfirmationGateEvidenceV1":
        if len(set(self.candidate_routes)) != 2:
            raise ValueError("confirmation_gate_requires_two_unique_routes")
        if set(self.evidence_sha256) != set(self.evidence_paths):
            raise ValueError("confirmation_gate_evidence_hash_coverage_mismatch")
        if self.decision == "pass" and self.findings:
            raise ValueError("passing_confirmation_gate_cannot_have_findings")
        return self


class RouteConfirmationReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_version: Literal["v3.route_confirmation_report.2"] = (
        "v3.route_confirmation_report.2"
    )
    comparison_id: str
    candidate_routes: List[RouteId] = Field(min_length=2, max_length=2)
    decision: Literal["promote_candidate", "hold", "redesign_again"]
    winning_route: Optional[RouteId] = None
    screening_report_path: str
    screening_report_sha256: str
    gate_evidence_paths: Dict[ConfirmationGate, str]
    gate_evidence_sha256: Dict[ConfirmationGate, str]
    major_validity_findings: List[str] = Field(default_factory=list)
    promotion_authorized: Literal[False] = False

    @model_validator(mode="after")
    def validate_decision(self) -> "RouteConfirmationReportV1":
        if len(set(self.candidate_routes)) != 2:
            raise ValueError("confirmation_requires_two_unique_routes")
        if set(self.gate_evidence_paths) != set(
            RouteConfirmationCompiler.REQUIRED_GATES
        ):
            raise ValueError("confirmation_gate_path_coverage_invalid")
        if set(self.gate_evidence_sha256) != set(
            RouteConfirmationCompiler.REQUIRED_GATES
        ):
            raise ValueError("confirmation_gate_hash_coverage_invalid")
        if self.decision == "promote_candidate":
            if self.winning_route not in self.candidate_routes:
                raise ValueError("confirmation_winner_not_in_candidates")
        elif self.winning_route is not None:
            raise ValueError("non_promotion_confirmation_must_not_name_winner")
        return self


class RouteConfirmationCompiler:
    REQUIRED_GATES: tuple[ConfirmationGate, ...] = (
        "absolute_gates",
        "matched_environment",
        "server_candidate_reproduction",
        "rollback_verification",
        "major_validity_closure",
    )

    def compile(
        self,
        *,
        screening_report_path: str | Path,
        gate_evidence_paths: Dict[ConfirmationGate, str | Path],
        winning_route: Optional[RouteId],
    ) -> RouteConfirmationReportV1:
        screening_path = Path(screening_report_path).resolve()
        screening = RouteComparisonReportV1.model_validate_json(
            screening_path.read_text(encoding="utf-8")
        )
        if (
            screening.decision != "advance_two_routes"
            or len(screening.confirmation_candidates) != 2
        ):
            raise ValueError("confirmation_requires_two_screening_candidates")
        if set(gate_evidence_paths) != set(self.REQUIRED_GATES):
            raise ValueError("confirmation_requires_all_gate_evidence")

        resolved_paths = {
            gate: str(Path(path).resolve())
            for gate, path in gate_evidence_paths.items()
        }
        gate_hashes = {
            gate: self._sha256_file(Path(path))
            for gate, path in resolved_paths.items()
        }
        provisional = RouteConfirmationReportV1(
            comparison_id=screening.comparison_id,
            candidate_routes=list(screening.confirmation_candidates),
            decision="hold",
            screening_report_path=str(screening_path),
            screening_report_sha256=self._sha256_file(screening_path),
            gate_evidence_paths=resolved_paths,
            gate_evidence_sha256=gate_hashes,
        )
        reasons, gates = self.verify(provisional)
        findings = [
            finding
            for gate in gates.values()
            if gate.gate == "major_validity_closure"
            for finding in gate.findings
        ]
        blocked_gates = {
            gate.gate for gate in gates.values() if gate.decision != "pass"
        }
        if not reasons:
            if winning_route not in screening.confirmation_candidates:
                raise ValueError("confirmation_winner_not_in_candidates")
            decision: Literal[
                "promote_candidate", "hold", "redesign_again"
            ] = "promote_candidate"
            selected = winning_route
        elif blocked_gates & {"absolute_gates", "major_validity_closure"}:
            decision = "redesign_again"
            selected = None
        else:
            decision = "hold"
            selected = None
        return RouteConfirmationReportV1(
            comparison_id=screening.comparison_id,
            candidate_routes=list(screening.confirmation_candidates),
            decision=decision,
            winning_route=selected,
            screening_report_path=str(screening_path),
            screening_report_sha256=self._sha256_file(screening_path),
            gate_evidence_paths=resolved_paths,
            gate_evidence_sha256=gate_hashes,
            major_validity_findings=findings,
        )

    def verify(
        self,
        report: RouteConfirmationReportV1,
    ) -> tuple[List[str], Dict[ConfirmationGate, ConfirmationGateEvidenceV1]]:
        reasons: List[str] = []
        gates: Dict[ConfirmationGate, ConfirmationGateEvidenceV1] = {}
        screening_path = Path(report.screening_report_path)
        if (
            not screening_path.is_file()
            or self._sha256_file(screening_path)
            != report.screening_report_sha256
        ):
            reasons.append("confirmation_screening_report_sha256_mismatch")
            return reasons, gates
        screening = RouteComparisonReportV1.model_validate_json(
            screening_path.read_text(encoding="utf-8")
        )
        if screening.comparison_id != report.comparison_id:
            reasons.append("confirmation_screening_comparison_id_mismatch")
        if set(screening.confirmation_candidates) != set(
            report.candidate_routes
        ):
            reasons.append("confirmation_screening_candidate_mismatch")

        for gate in self.REQUIRED_GATES:
            path = Path(report.gate_evidence_paths[gate])
            expected = report.gate_evidence_sha256[gate]
            if not path.is_file():
                reasons.append(f"confirmation_gate_evidence_missing:{gate}")
                continue
            if self._sha256_file(path) != expected:
                reasons.append(
                    f"confirmation_gate_evidence_sha256_mismatch:{gate}"
                )
                continue
            evidence = ConfirmationGateEvidenceV1.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            gates[gate] = evidence
            if evidence.gate != gate:
                reasons.append(f"confirmation_gate_identity_mismatch:{gate}")
            if evidence.comparison_id != report.comparison_id:
                reasons.append(
                    f"confirmation_gate_comparison_id_mismatch:{gate}"
                )
            if set(evidence.candidate_routes) != set(
                report.candidate_routes
            ):
                reasons.append(
                    f"confirmation_gate_candidate_routes_mismatch:{gate}"
                )
            if not evidence.generator_independent:
                reasons.append(
                    f"confirmation_gate_not_generator_independent:{gate}"
                )
            if evidence.decision != "pass":
                reasons.append(f"confirmation_gate_blocked:{gate}")
            for support_path, support_sha in evidence.evidence_sha256.items():
                support = Path(support_path)
                if not support.is_absolute():
                    support = path.parent / support
                if (
                    not support.is_file()
                    or self._sha256_file(support) != support_sha
                ):
                    reasons.append(
                        f"confirmation_gate_support_sha256_mismatch:{gate}"
                    )
        matched = gates.get("matched_environment")
        server = gates.get("server_candidate_reproduction")
        if matched and server:
            if (
                not matched.environment_id
                or matched.environment_id != server.environment_id
            ):
                reasons.append("confirmation_environment_identity_mismatch")
        return sorted(set(reasons)), gates

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


class ReconstructionPromotionRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_version: Literal["v3.reconstruction_promotion_record.2"] = (
        "v3.reconstruction_promotion_record.2"
    )
    comparison_id: str
    decision: Literal["promote", "hold", "redesign_again"]
    selected_route: Optional[RouteId] = None
    blocking_reasons: List[str] = Field(default_factory=list)
    screening_report_path: str
    screening_report_sha256: str
    confirmation_report_path: Optional[str] = None
    confirmation_report_sha256: Optional[str] = None
    rollback_required: Literal[True] = True
    opt_in_profile_only: Literal[True] = True
    canonical_registry_mutation_authorized: Literal[False] = False
    default_chain_mutation_authorized: Literal[False] = False
    release_activation_authorized: Literal[False] = False
    training_authorized: Literal[False] = False
    notes: List[str] = Field(default_factory=list)


class ReconstructionPromotionCompiler:
    """Compile a report-only R7 decision without mutating production state."""

    def compile(
        self,
        *,
        screening_report_path: str | Path,
        confirmation_report_path: str | Path | None = None,
    ) -> ReconstructionPromotionRecordV1:
        screening_path = Path(screening_report_path).resolve()
        screening = RouteComparisonReportV1.model_validate_json(
            screening_path.read_text(encoding="utf-8")
        )
        reasons = self._screening_integrity_reasons(screening)
        confirmation: RouteConfirmationReportV1 | None = None
        confirmation_path: Path | None = None

        if not screening.evidence_complete:
            reasons.append("screening_evidence_incomplete")
        if not screening.thresholds_frozen_before_results:
            reasons.append("screening_thresholds_not_frozen")
        if screening.decision == "redesign_again":
            decision = "redesign_again" if not reasons else "hold"
            return self._record(
                screening_path,
                screening.comparison_id,
                decision,
                reasons or ["screening_requires_redesign"],
            )
        if screening.decision != "advance_two_routes":
            reasons.append("screening_did_not_advance_two_routes")
        if len(screening.confirmation_candidates) != 2:
            reasons.append("screening_confirmation_candidate_count_invalid")
        if confirmation_report_path is None:
            reasons.append("confirmation_evidence_missing")
        else:
            confirmation_path = Path(confirmation_report_path).resolve()
            confirmation = RouteConfirmationReportV1.model_validate_json(
                confirmation_path.read_text(encoding="utf-8")
            )
            if confirmation.comparison_id != screening.comparison_id:
                reasons.append("confirmation_comparison_id_mismatch")
            if set(confirmation.candidate_routes) != set(
                screening.confirmation_candidates
            ):
                reasons.append("confirmation_candidate_routes_mismatch")
            confirmation_reasons, _ = RouteConfirmationCompiler().verify(
                confirmation
            )
            reasons.extend(confirmation_reasons)
            if (
                Path(confirmation.screening_report_path).resolve()
                != screening_path
                or confirmation.screening_report_sha256
                != self._sha256_file(screening_path)
            ):
                reasons.append("confirmation_screening_binding_mismatch")
            if confirmation.major_validity_findings:
                reasons.append("major_validity_findings_open")
            if confirmation.decision == "redesign_again":
                allowed_redesign_reasons = {
                    "confirmation_gate_blocked:absolute_gates",
                    "confirmation_gate_blocked:major_validity_closure",
                    "major_validity_findings_open",
                }
                decision = (
                    "redesign_again"
                    if set(reasons) <= allowed_redesign_reasons
                    else "hold"
                )
                return self._record(
                    screening_path,
                    screening.comparison_id,
                    decision,
                    reasons or ["confirmation_requires_redesign"],
                    confirmation_path,
                )
            if confirmation.decision != "promote_candidate":
                reasons.append("confirmation_did_not_select_candidate")

        if reasons or confirmation is None:
            return self._record(
                screening_path,
                screening.comparison_id,
                "hold",
                sorted(set(reasons)),
                confirmation_path,
            )
        return ReconstructionPromotionRecordV1(
            comparison_id=screening.comparison_id,
            decision="promote",
            selected_route=confirmation.winning_route,
            blocking_reasons=[],
            screening_report_path=str(screening_path),
            screening_report_sha256=self._sha256_file(screening_path),
            confirmation_report_path=str(confirmation_path),
            confirmation_report_sha256=self._sha256_file(
                confirmation_path
            ),
            notes=[
                "Promote means eligible for an opt-in candidate profile only.",
                "This record has no apply, release, registry or training authority.",
            ],
        )

    def _screening_integrity_reasons(
        self,
        screening: RouteComparisonReportV1,
    ) -> List[str]:
        reasons = []
        comparison_manifest: RouteComparisonManifestV1 | None = None
        compile_report: RouteComparisonEvidenceCompileReportV1 | None = None
        records = (
            (
                screening.comparison_manifest_path,
                screening.comparison_manifest_sha256,
                "screening_comparison_manifest",
            ),
            (
                screening.evidence_compile_report_path,
                screening.evidence_compile_report_sha256,
                "screening_evidence_compile_report",
            ),
        )
        for path_text, expected, label in records:
            if not path_text or not expected:
                reasons.append(f"{label}_binding_missing")
                continue
            path = Path(path_text)
            if (
                not path.is_file()
                or self._sha256_file(path) != expected
            ):
                reasons.append(f"{label}_sha256_mismatch")
                continue
            if label == "screening_comparison_manifest":
                comparison_manifest = RouteComparisonManifestV1.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                if comparison_manifest.comparison_id != screening.comparison_id:
                    reasons.append(
                        "screening_comparison_manifest_identity_mismatch"
                    )
            else:
                compile_report = (
                    RouteComparisonEvidenceCompileReportV1.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
                if (
                    compile_report.comparison_id != screening.comparison_id
                    or compile_report.decision != "pass"
                    or compile_report.evidence_count != 12
                ):
                    reasons.append(
                        "screening_evidence_compile_report_not_complete"
                    )
        if (
            comparison_manifest is not None
            and compile_report is not None
            and not reasons
        ):
            recomputed = RouteComparisonAnalyzer().analyze(
                comparison_manifest,
                compile_report.evidence,
            )
            fields = (
                "comparison_id",
                "stage",
                "decision",
                "evidence_complete",
                "route_aggregates",
                "confirmation_candidates",
                "blocking_reasons",
                "thresholds_frozen_before_results",
            )
            if any(
                getattr(recomputed, field) != getattr(screening, field)
                for field in fields
            ):
                reasons.append("screening_report_recomputation_mismatch")
        return reasons

    def _record(
        self,
        screening_path: Path,
        comparison_id: str,
        decision: Literal["hold", "redesign_again"],
        reasons: List[str],
        confirmation_path: Path | None = None,
    ) -> ReconstructionPromotionRecordV1:
        return ReconstructionPromotionRecordV1(
            comparison_id=comparison_id,
            decision=decision,
            blocking_reasons=sorted(set(reasons)),
            screening_report_path=str(screening_path),
            screening_report_sha256=self._sha256_file(screening_path),
            confirmation_report_path=(
                str(confirmation_path) if confirmation_path else None
            ),
            confirmation_report_sha256=(
                self._sha256_file(confirmation_path)
                if confirmation_path
                else None
            ),
            notes=[
                "The compiler is report-only and cannot mutate a release or default chain.",
            ],
        )

    @staticmethod
    def _sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
