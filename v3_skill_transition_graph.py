import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from v3_skill_registry import SkillRegistryBuilder, stable_id
from v3_source_schema import (
    ExtractedSkillCandidate,
    SemanticResource,
    SkillMotifHint,
    SkillRegistryEntry,
    SkillTraceEdge,
    load_json_file,
    load_skill_candidates,
    load_skill_motif_hints,
    load_skill_trace_edges,
)


RESOURCE_ALIASES = {
    "netprofit": "MonetaryAmount",
    "profit": "MonetaryAmount",
    "revenue": "MonetaryAmount",
    "expense": "MonetaryAmount",
    "amount": "MonetaryAmount",
    "currency": "MonetaryAmount",
    "financialmetric": "FinancialMetric",
    "metric": "FinancialMetric",
    "period": "TimePeriod",
    "date": "TimePeriod",
    "entity": "Entity",
    "company": "Entity",
    "jurisdiction": "Jurisdiction",
    "policy": "PolicyRule",
    "rule": "PolicyRule",
    "requirement": "ComplianceRequirement",
    "control": "ControlEvidence",
    "evidence": "ControlEvidence",
    "sample": "AuditSample",
    "exception": "ExceptionRecord",
    "finding": "AuditFinding",
    "difference": "ReconciliationDifference",
    "deliverable": "DeliverableSection",
    "report": "DeliverableSection",
    "memo": "DeliverableSection",
    "workbook": "DeliverableSection",
}


class SkillTransitionGraphBuilder:
    """Report-only graph builder for Pipeline A composability signals."""

    def __init__(self) -> None:
        self.registry_builder = SkillRegistryBuilder()

    def build_reports(
        self,
        candidates: List[ExtractedSkillCandidate],
        accepted_candidates: List[ExtractedSkillCandidate],
        registry_entries: List[SkillRegistryEntry],
        trace_edges: Optional[List[SkillTraceEdge]] = None,
        motif_hints: Optional[List[SkillMotifHint]] = None,
        readiness_report: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        trace_edges = trace_edges or self._fallback_trace_edges(candidates)
        motif_hints = motif_hints or self._fallback_motif_hints(candidates)
        accepted_ids = {candidate.candidate_id for candidate in accepted_candidates} or {
            candidate.candidate_id for candidate in candidates
        }
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        skill_id_by_candidate = self._skill_id_by_candidate(registry_entries, candidates)
        readiness_by_skill = self._readiness_by_skill(readiness_report)

        edge_records = []
        for trace_edge in trace_edges:
            left = candidate_by_id.get(trace_edge.from_candidate_id)
            right = candidate_by_id.get(trace_edge.to_candidate_id)
            if left is None or right is None:
                continue
            left_skill_id = skill_id_by_candidate.get(left.candidate_id, "")
            right_skill_id = skill_id_by_candidate.get(right.candidate_id, "")
            edge_scope = "registry_mapped" if left_skill_id and right_skill_id else "candidate_local"
            if left.candidate_id not in accepted_ids or right.candidate_id not in accepted_ids:
                decision = "blocked"
                reason_codes = ["candidate_not_accepted"]
                score = 0.0
                compatibility = 0.0
            else:
                compatibility, compatibility_reasons = self._resource_compatibility(left, right)
                readiness_weight, readiness_reasons = self._readiness_weight(
                    left_skill_id,
                    right_skill_id,
                    readiness_by_skill,
                )
                motif_bonus, motif_reasons = self._motif_bonus(left.candidate_id, right.candidate_id, motif_hints)
                local_prior = min(max(trace_edge.weight_hint, 0.0), 1.0) * 0.35
                trace_bonus, trace_reasons = self._trace_compatibility_bonus(trace_edge, compatibility)
                score = round(local_prior + compatibility * 0.4 + readiness_weight * 0.15 + motif_bonus + trace_bonus, 4)
                reason_codes = sorted(
                    set(trace_edge.reason_codes + compatibility_reasons + readiness_reasons + motif_reasons + trace_reasons)
                )
                decision = self._edge_decision(score, reason_codes)

            edge_records.append(
                {
                    "edge_id": stable_id(
                        "skill_edge",
                        f"{trace_edge.from_candidate_id}->{trace_edge.to_candidate_id}:{trace_edge.relation_type}",
                    ),
                    "from_candidate_id": trace_edge.from_candidate_id,
                    "to_candidate_id": trace_edge.to_candidate_id,
                    "from_skill_id": skill_id_by_candidate.get(trace_edge.from_candidate_id, ""),
                    "to_skill_id": skill_id_by_candidate.get(trace_edge.to_candidate_id, ""),
                    "edge_scope": edge_scope,
                    "relation_type": trace_edge.relation_type,
                    "edge_decision": decision,
                    "edge_score": score,
                    "compatibility_score": round(compatibility, 4),
                    "transition_prior": round(min(max(trace_edge.weight_hint, 0.0), 1.0), 4),
                    "evidence_block_ids": trace_edge.evidence_block_ids,
                    "reason_codes": reason_codes,
                    "success_count": 0,
                    "failure_count": 0,
                }
            )

        transition_report = self._transition_report(
            candidates,
            accepted_candidates,
            registry_entries,
            edge_records,
            motif_hints,
        )
        composition_report = self._composition_report(
            candidates,
            registry_entries,
            edge_records,
            motif_hints,
            skill_id_by_candidate,
            readiness_by_skill,
        )
        return transition_report, composition_report

    def _fallback_trace_edges(self, candidates: List[ExtractedSkillCandidate]) -> List[SkillTraceEdge]:
        edges = []
        for left, right in zip(candidates, candidates[1:]):
            left_sources = set(left.source_ids)
            right_sources = set(right.source_ids)
            if left_sources and right_sources and not (left_sources & right_sources):
                continue
            edges.append(
                SkillTraceEdge(
                    from_candidate_id=left.candidate_id,
                    to_candidate_id=right.candidate_id,
                    relation_type="local_order",
                    evidence_block_ids=sorted(
                        {
                            block_id
                            for candidate in (left, right)
                            for evidence in candidate.evidence
                            for block_id in evidence.block_ids
                        }
                    ),
                    reason_codes=["fallback_candidate_order"],
                    weight_hint=0.35,
                )
            )
        return edges

    def _fallback_motif_hints(self, candidates: List[ExtractedSkillCandidate]) -> List[SkillMotifHint]:
        if len(candidates) < 2:
            return []
        text = " ".join(
            " ".join(
                [
                    candidate.proposed_name,
                    " ".join(candidate.capability_tags),
                    " ".join(candidate.common_deliverables),
                    candidate.business_meaning,
                ]
            ).lower()
            for candidate in candidates
        )
        motif_type = "evidence_to_deliverable"
        reason = "fallback_deliverable_or_synthesis_signal"
        if any(term in text for term in ["reconcile", "reconciliation", "tie", "corroborate"]):
            motif_type = "fan_in_reconciliation"
            reason = "fallback_reconciliation_signal"
        elif any(term in text for term in ["policy", "rule", "requirement", "compliance"]):
            motif_type = "policy_application"
            reason = "fallback_policy_or_compliance_signal"
        elif any(term in text for term in ["exception", "deficienc", "severity", "remediation"]):
            motif_type = "exception_escalation"
            reason = "fallback_exception_signal"
        elif any(term in text for term in ["validate", "verify", "check", "test"]):
            motif_type = "cross_check_validation"
            reason = "fallback_validation_signal"
        return [
            SkillMotifHint(
                motif_type=motif_type,
                candidate_ids=[candidate.candidate_id for candidate in candidates[:6]],
                evidence_block_ids=sorted(
                    {
                        block_id
                        for candidate in candidates[:6]
                        for evidence in candidate.evidence
                        for block_id in evidence.block_ids
                    }
                ),
                confidence=0.3,
                reason_codes=[reason],
                summary="Deterministic fallback motif inferred from candidate names, tags, and deliverables.",
            )
        ]

    def _skill_id_by_candidate(
        self,
        registry_entries: List[SkillRegistryEntry],
        candidates: List[ExtractedSkillCandidate],
    ) -> Dict[str, str]:
        ref_to_skill = {
            source_candidate_id: entry.skill_id
            for entry in registry_entries
            for source_candidate_id in entry.source_candidate_ids
        }
        mapping = {}
        for candidate in candidates:
            candidate_ref = self.registry_builder._candidate_ref(candidate)
            skill_id = ref_to_skill.get(candidate_ref)
            if skill_id:
                mapping[candidate.candidate_id] = skill_id
        return mapping

    def _readiness_by_skill(self, readiness_report: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not readiness_report:
            return {}
        return {
            record.get("skill_id", ""): record
            for record in readiness_report.get("records", [])
            if record.get("skill_id")
        }

    def _readiness_weight(
        self,
        left_skill_id: str,
        right_skill_id: str,
        readiness_by_skill: Dict[str, Dict[str, Any]],
    ) -> Tuple[float, List[str]]:
        reason_codes = []
        weights = []
        for skill_id in (left_skill_id, right_skill_id):
            record = readiness_by_skill.get(skill_id)
            if not record:
                reason_codes.append("missing_readiness_signal")
                weights.append(0.5)
                continue
            decision = record.get("readiness_decision", "")
            if decision == "exclude_until_revised":
                reason_codes.append("readiness_exclude_until_revised")
                weights.append(0.0)
            elif decision == "sample_with_caution":
                reason_codes.append("readiness_sample_with_caution")
                weights.append(0.45)
            else:
                reason_codes.append("readiness_sample_ready")
                weights.append(float(record.get("sampling_weight", 0.8)))
        return min(weights) if weights else 0.5, reason_codes

    def _motif_bonus(
        self,
        left_candidate_id: str,
        right_candidate_id: str,
        motif_hints: List[SkillMotifHint],
    ) -> Tuple[float, List[str]]:
        for hint in motif_hints:
            ids = hint.candidate_ids
            if left_candidate_id in ids and right_candidate_id in ids:
                return min(max(hint.confidence, 0.0), 1.0) * 0.1, [f"motif_{hint.motif_type}"]
        return 0.0, []

    def _resource_compatibility(
        self,
        left: ExtractedSkillCandidate,
        right: ExtractedSkillCandidate,
    ) -> Tuple[float, List[str]]:
        provided = self._provided_resources(left)
        required = self._required_resources(right)
        if not provided or not required:
            return 0.25, ["missing_typed_resources"]

        best_score = 0.0
        best_reasons = ["resource_mismatch"]
        for provided_resource in provided:
            for required_resource in required:
                score, reasons = self._resource_pair_score(provided_resource, required_resource)
                if score > best_score:
                    best_score = score
                    best_reasons = reasons
        return best_score, best_reasons

    def _provided_resources(self, candidate: ExtractedSkillCandidate) -> List[SemanticResource]:
        resources = list(candidate.output_contract.provided_resources)
        if not resources:
            resources = [self._infer_resource(item, candidate) for item in candidate.output_contract.provides_semantics]
        return resources

    def _required_resources(self, candidate: ExtractedSkillCandidate) -> List[SemanticResource]:
        resources = list(candidate.input_contract.required_resources)
        if not resources:
            resources = [self._infer_resource(item, candidate) for item in candidate.input_contract.requires_semantics]
        return resources

    def _infer_resource(self, text: str, candidate: ExtractedSkillCandidate) -> SemanticResource:
        compact = re.sub(r"[^a-z0-9]+", "", text.lower())
        resource_type = ""
        for key, value in RESOURCE_ALIASES.items():
            if key in compact:
                resource_type = value
                break
        if not resource_type and ":" in text:
            resource_type = text.split(":", 1)[0]
        if not resource_type:
            resource_type = "UnknownResource"
        subtype = text.split(":", 1)[1] if ":" in text else text
        return SemanticResource(
            resource_type=resource_type,
            subtype=subtype,
            attributes={},
            domain=candidate.domain_tags[0] if candidate.domain_tags else "",
            evidence_refs=[evidence.evidence_id for evidence in candidate.evidence],
        )

    def _resource_pair_score(
        self,
        provided: SemanticResource,
        required: SemanticResource,
    ) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []
        provided_type = self._canonical_resource_type(provided.resource_type, provided.subtype)
        required_type = self._canonical_resource_type(required.resource_type, required.subtype)
        if provided_type == required_type:
            score += 0.65
            reasons.append("resource_type_match")
        elif provided.subtype and self._canonical_resource_type(provided.subtype, "") == required_type:
            score += 0.5
            reasons.append("resource_subtype_satisfies_type")
        elif required.subtype and provided_type == self._canonical_resource_type(required.subtype, ""):
            score += 0.4
            reasons.append("resource_type_satisfies_subtype")

        if provided.domain and required.domain and provided.domain == required.domain:
            score += 0.15
            reasons.append("resource_domain_match")
        elif not required.domain or not provided.domain:
            score += 0.05
            reasons.append("resource_domain_unspecified")

        missing_attrs = [
            key
            for key, value in required.attributes.items()
            if value == "required" and key not in provided.attributes
        ]
        if missing_attrs:
            score -= 0.25
            reasons.append("missing_required_resource_attributes")
        else:
            score += 0.1
            reasons.append("required_resource_attributes_satisfied")
        return max(0.0, min(round(score, 4), 1.0)), reasons

    def _canonical_resource_type(self, resource_type: str, subtype: str) -> str:
        for raw in (resource_type, subtype):
            compact = re.sub(r"[^a-z0-9]+", "", raw.lower())
            if compact in RESOURCE_ALIASES:
                return RESOURCE_ALIASES[compact]
        return resource_type.strip() or "UnknownResource"

    def _edge_decision(self, score: float, reason_codes: List[str]) -> str:
        reason_set = set(reason_codes)
        if "readiness_exclude_until_revised" in reason_set or "candidate_not_accepted" in reason_set:
            return "blocked"
        if "source_trace_resource_compatible_unverified" in reason_set and score >= 0.25:
            return "caution"
        if "missing_required_resource_attributes" in reason_set and score < 0.6:
            return "caution"
        if score >= 0.55:
            return "usable"
        if score >= 0.3:
            return "caution"
        return "blocked"

    def _trace_compatibility_bonus(self, trace_edge: SkillTraceEdge, compatibility: float) -> Tuple[float, List[str]]:
        reason_set = set(trace_edge.reason_codes)
        if compatibility > 0:
            return 0.0, []
        if "resource_compatible" not in reason_set:
            return 0.0, []
        if trace_edge.relation_type not in {"local_order", "cross_check", "validation", "fan_in", "fan_out"}:
            return 0.0, []
        return 0.08, ["source_trace_resource_compatible_unverified"]

    def _transition_report(
        self,
        candidates: List[ExtractedSkillCandidate],
        accepted_candidates: List[ExtractedSkillCandidate],
        registry_entries: List[SkillRegistryEntry],
        edge_records: List[Dict[str, Any]],
        motif_hints: List[SkillMotifHint],
    ) -> Dict[str, Any]:
        edge_counts = Counter(edge["edge_decision"] for edge in edge_records)
        edge_scope_counts = Counter(edge.get("edge_scope", "unknown") for edge in edge_records)
        motif_counts = Counter(hint.motif_type for hint in motif_hints)
        mapped_candidate_count = sum(1 for candidate in candidates if candidate.candidate_id in self._skill_id_by_candidate(registry_entries, candidates))
        return {
            "transition_graph_version": "v3.transition_graph.1",
            "candidate_count": len(candidates),
            "accepted_candidate_count": len(accepted_candidates),
            "registry_entry_count": len(registry_entries),
            "registry_mapped_candidate_count": mapped_candidate_count,
            "candidate_local_candidate_count": max(0, len(candidates) - mapped_candidate_count),
            "edge_count": len(edge_records),
            "edge_decision_counts": dict(sorted(edge_counts.items())),
            "edge_scope_counts": dict(sorted(edge_scope_counts.items())),
            "registry_mapped_edge_count": edge_scope_counts.get("registry_mapped", 0),
            "candidate_local_edge_count": edge_scope_counts.get("candidate_local", 0),
            "motif_count": len(motif_hints),
            "motif_counts": dict(sorted(motif_counts.items())),
            "edges": edge_records,
            "motif_hints": [hint.model_dump(mode="json") for hint in motif_hints],
            "notes": [
                "This report is non-destructive and does not update SkillRegistryEntry.",
                "Edges come from local source traces or deterministic adjacent-candidate fallback, not all-pairs LLM successor judging.",
                "edge_scope=registry_mapped means both endpoints map to persistent registry entries; edge_scope=candidate_local means at least one endpoint is experiment-only, which is expected in calibration-only runs.",
            ],
        }

    def _composition_report(
        self,
        candidates: List[ExtractedSkillCandidate],
        registry_entries: List[SkillRegistryEntry],
        edge_records: List[Dict[str, Any]],
        motif_hints: List[SkillMotifHint],
        skill_id_by_candidate: Dict[str, str],
        readiness_by_skill: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        incoming = Counter(edge["to_candidate_id"] for edge in edge_records if edge["edge_decision"] == "usable")
        outgoing = Counter(edge["from_candidate_id"] for edge in edge_records if edge["edge_decision"] == "usable")
        records = []
        for candidate in candidates:
            skill_id = skill_id_by_candidate.get(candidate.candidate_id, "")
            readiness = readiness_by_skill.get(skill_id, {})
            roles = self._role_hints(candidate, incoming[candidate.candidate_id], outgoing[candidate.candidate_id])
            records.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "skill_id": skill_id,
                    "proposed_name": candidate.proposed_name,
                    "graph_role_hints": roles,
                    "readiness_decision": readiness.get("readiness_decision", "unknown"),
                    "incoming_usable_edge_count": incoming[candidate.candidate_id],
                    "outgoing_usable_edge_count": outgoing[candidate.candidate_id],
                    "required_resource_count": len(self._required_resources(candidate)),
                    "provided_resource_count": len(self._provided_resources(candidate)),
                    "reason_codes": self._role_reason_codes(candidate, roles),
                }
            )
        role_counts = Counter(role for record in records for role in record["graph_role_hints"])
        edge_counts = Counter(edge["edge_decision"] for edge in edge_records)
        edge_scope_counts = Counter(edge.get("edge_scope", "unknown") for edge in edge_records)
        return {
            "composition_readiness_version": "v3.composition_readiness.1",
            "candidate_count": len(candidates),
            "registry_entry_count": len(registry_entries),
            "registry_mapped_candidate_count": sum(1 for record in records if record["skill_id"]),
            "candidate_local_candidate_count": sum(1 for record in records if not record["skill_id"]),
            "role_counts": dict(sorted(role_counts.items())),
            "edge_decision_counts": dict(sorted(edge_counts.items())),
            "edge_scope_counts": dict(sorted(edge_scope_counts.items())),
            "motif_counts": dict(sorted(Counter(hint.motif_type for hint in motif_hints).items())),
            "records": records,
            "notes": [
                "This is a report-only graph-role readiness layer for future Pipeline B sampling.",
                "Graph roles are heuristic hints, not final task assembly decisions.",
                "Records with empty skill_id are candidate-local calibration signals and should not be treated as persistent registry-ready evidence.",
            ],
        }

    def _role_hints(self, candidate: ExtractedSkillCandidate, incoming_count: int, outgoing_count: int) -> List[str]:
        required = self._required_resources(candidate)
        provided = self._provided_resources(candidate)
        text = " ".join(
            [
                candidate.proposed_name,
                " ".join(candidate.capability_tags),
                " ".join(candidate.common_deliverables),
                " ".join(candidate.output_contract.provides_semantics),
            ]
        ).lower()
        roles = []
        if len(required) <= 1 and provided:
            roles.append("starter")
        if required and provided and {r.resource_type for r in required} != {r.resource_type for r in provided}:
            roles.append("transform")
        if len(required) >= 2 or incoming_count >= 2:
            roles.append("fan_in")
        if any(term in text for term in ["validate", "check", "exception", "finding", "deficienc", "verify"]):
            roles.append("validator")
        if any(term in text for term in ["deliverable", "report", "memo", "workbook", "section", "narrative"]):
            roles.append("synthesis")
        if outgoing_count >= 2:
            roles.append("fan_out")
        return sorted(set(roles or ["unclassified"]))

    def _role_reason_codes(self, candidate: ExtractedSkillCandidate, roles: List[str]) -> List[str]:
        reason_codes = []
        if "unclassified" in roles:
            reason_codes.append("insufficient_port_or_role_signal")
        if not candidate.input_contract.required_resources and not candidate.output_contract.provided_resources:
            reason_codes.append("typed_resources_inferred_from_legacy_semantics")
        return reason_codes


def load_optional_trace_edges(path: Optional[str | Path]) -> List[SkillTraceEdge]:
    if path is None or not Path(path).exists():
        return []
    return load_skill_trace_edges(str(path))


def load_optional_motif_hints(path: Optional[str | Path]) -> List[SkillMotifHint]:
    if path is None or not Path(path).exists():
        return []
    return load_skill_motif_hints(str(path))


def load_optional_json(path: Optional[str | Path]) -> Optional[Dict[str, Any]]:
    if path is None or not Path(path).exists():
        return None
    return load_json_file(str(path))


def write_graph_report(path: str | Path, payload: Dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
