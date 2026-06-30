import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from task_generator.v3_source_schema import (
    ExtractedSkillCandidate,
    SkillExtractionPromptPackage,
    SkillMotifHint,
    SkillTraceEdge,
    load_skill_candidates,
    load_skill_motif_hints,
    load_skill_trace_edges,
)


def build_graph_extraction_diagnostics(
    candidates: List[ExtractedSkillCandidate],
    trace_edges: Optional[List[SkillTraceEdge]] = None,
    motif_hints: Optional[List[SkillMotifHint]] = None,
    package: Optional[SkillExtractionPromptPackage] = None,
) -> Dict[str, Any]:
    """Build a report-only diagnostic for graph-oriented extraction quality."""

    trace_edges = trace_edges or []
    motif_hints = motif_hints or []
    candidate_ids = {candidate.candidate_id for candidate in candidates}
    evidence_ids = _candidate_evidence_ids(candidates)
    known_block_ids = _known_block_ids(candidates, package)

    resource_summary = _resource_summary(candidates, evidence_ids)
    trace_summary = _trace_summary(trace_edges, candidate_ids, known_block_ids)
    motif_summary = _motif_summary(motif_hints, candidate_ids, known_block_ids)
    warnings = _warnings(candidates, trace_edges, motif_hints, resource_summary, trace_summary, motif_summary)

    return {
        "diagnostics_version": "v3.graph_extraction_diagnostics.1",
        "candidate_count": len(candidates),
        "typed_resource_summary": resource_summary,
        "trace_edge_summary": trace_summary,
        "motif_hint_summary": motif_summary,
        "warnings": warnings,
        "is_graph_ready": not any(warning["severity"] == "error" for warning in warnings),
    }


def load_graph_extraction_inputs(
    candidates_path: Path,
    trace_edges_path: Optional[Path] = None,
    motif_hints_path: Optional[Path] = None,
) -> tuple[List[ExtractedSkillCandidate], List[SkillTraceEdge], List[SkillMotifHint]]:
    candidates = load_skill_candidates(str(candidates_path))
    trace_edges = load_skill_trace_edges(str(trace_edges_path)) if trace_edges_path and trace_edges_path.exists() else []
    motif_hints = load_skill_motif_hints(str(motif_hints_path)) if motif_hints_path and motif_hints_path.exists() else []
    return candidates, trace_edges, motif_hints


def write_graph_extraction_diagnostics(report: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def _candidate_evidence_ids(candidates: Iterable[ExtractedSkillCandidate]) -> Set[str]:
    return {
        evidence.evidence_id
        for candidate in candidates
        for evidence in candidate.evidence
    }


def _known_block_ids(
    candidates: Iterable[ExtractedSkillCandidate],
    package: Optional[SkillExtractionPromptPackage],
) -> Set[str]:
    block_ids = {
        block_id
        for candidate in candidates
        for evidence in candidate.evidence
        for block_id in evidence.block_ids
    }
    if package is not None:
        block_ids.update(
            block.block_id
            for source in package.normalized_sources
            for block in source.blocks
        )
    return block_ids


def _resource_summary(candidates: List[ExtractedSkillCandidate], evidence_ids: Set[str]) -> Dict[str, Any]:
    resource_type_counts: Counter[str] = Counter()
    unknown_evidence_refs = []
    missing_required_resource_candidate_ids = []
    missing_provided_resource_candidate_ids = []

    for candidate in candidates:
        required = candidate.input_contract.required_resources
        optional = candidate.input_contract.optional_resources
        provided = candidate.output_contract.provided_resources
        if not required:
            missing_required_resource_candidate_ids.append(candidate.candidate_id)
        if not provided:
            missing_provided_resource_candidate_ids.append(candidate.candidate_id)
        for resource in [*required, *optional, *provided]:
            resource_type_counts[resource.resource_type or ""] += 1
            for evidence_ref in resource.evidence_refs:
                if evidence_ref not in evidence_ids:
                    unknown_evidence_refs.append(
                        {
                            "candidate_id": candidate.candidate_id,
                            "resource_type": resource.resource_type,
                            "subtype": resource.subtype,
                            "evidence_ref": evidence_ref,
                        }
                    )

    return {
        "resource_count": sum(resource_type_counts.values()),
        "resource_type_counts": dict(sorted(resource_type_counts.items())),
        "candidates_with_required_resources": len(candidates) - len(missing_required_resource_candidate_ids),
        "candidates_with_provided_resources": len(candidates) - len(missing_provided_resource_candidate_ids),
        "missing_required_resource_candidate_ids": missing_required_resource_candidate_ids,
        "missing_provided_resource_candidate_ids": missing_provided_resource_candidate_ids,
        "unknown_resource_evidence_refs": unknown_evidence_refs,
    }


def _trace_summary(
    trace_edges: List[SkillTraceEdge],
    candidate_ids: Set[str],
    known_block_ids: Set[str],
) -> Dict[str, Any]:
    relation_counts: Counter[str] = Counter(edge.relation_type for edge in trace_edges)
    touched_candidates = {
        candidate_id
        for edge in trace_edges
        for candidate_id in (edge.from_candidate_id, edge.to_candidate_id)
    }
    unknown_candidate_refs = []
    unknown_block_refs = []
    for edge in trace_edges:
        for candidate_id in (edge.from_candidate_id, edge.to_candidate_id):
            if candidate_id not in candidate_ids:
                unknown_candidate_refs.append(candidate_id)
        for block_id in edge.evidence_block_ids:
            if known_block_ids and block_id not in known_block_ids:
                unknown_block_refs.append(block_id)

    return {
        "trace_edge_count": len(trace_edges),
        "relation_type_counts": dict(sorted(relation_counts.items())),
        "candidate_coverage_count": len(touched_candidates),
        "candidate_coverage_ratio": round(len(touched_candidates) / max(len(candidate_ids), 1), 4),
        "unknown_candidate_refs": sorted(set(unknown_candidate_refs)),
        "unknown_block_refs": sorted(set(unknown_block_refs)),
    }


def _motif_summary(
    motif_hints: List[SkillMotifHint],
    candidate_ids: Set[str],
    known_block_ids: Set[str],
) -> Dict[str, Any]:
    motif_counts: Counter[str] = Counter(hint.motif_type for hint in motif_hints)
    touched_candidates = {
        candidate_id
        for hint in motif_hints
        for candidate_id in hint.candidate_ids
    }
    unknown_candidate_refs = []
    unknown_block_refs = []
    for hint in motif_hints:
        for candidate_id in hint.candidate_ids:
            if candidate_id not in candidate_ids:
                unknown_candidate_refs.append(candidate_id)
        for block_id in hint.evidence_block_ids:
            if known_block_ids and block_id not in known_block_ids:
                unknown_block_refs.append(block_id)

    return {
        "motif_hint_count": len(motif_hints),
        "motif_type_counts": dict(sorted(motif_counts.items())),
        "candidate_coverage_count": len(touched_candidates),
        "candidate_coverage_ratio": round(len(touched_candidates) / max(len(candidate_ids), 1), 4),
        "unknown_candidate_refs": sorted(set(unknown_candidate_refs)),
        "unknown_block_refs": sorted(set(unknown_block_refs)),
    }


def _warnings(
    candidates: List[ExtractedSkillCandidate],
    trace_edges: List[SkillTraceEdge],
    motif_hints: List[SkillMotifHint],
    resource_summary: Dict[str, Any],
    trace_summary: Dict[str, Any],
    motif_summary: Dict[str, Any],
) -> List[Dict[str, str]]:
    warnings = []
    if candidates and resource_summary["candidates_with_required_resources"] < len(candidates):
        warnings.append(
            {
                "severity": "warning",
                "code": "missing_required_typed_resources",
                "message": "Some candidates have no input_contract.required_resources.",
            }
        )
    if candidates and resource_summary["candidates_with_provided_resources"] < len(candidates):
        warnings.append(
            {
                "severity": "warning",
                "code": "missing_provided_typed_resources",
                "message": "Some candidates have no output_contract.provided_resources.",
            }
        )
    if resource_summary["unknown_resource_evidence_refs"]:
        warnings.append(
            {
                "severity": "error",
                "code": "unknown_resource_evidence_refs",
                "message": "Some SemanticResource.evidence_refs do not match candidate evidence IDs.",
            }
        )
    if len(candidates) > 1 and not trace_edges:
        warnings.append(
            {
                "severity": "warning",
                "code": "multi_candidate_without_trace_edges",
                "message": "Multiple candidates were extracted but no local trace edges were emitted.",
            }
        )
    if trace_summary["unknown_candidate_refs"] or trace_summary["unknown_block_refs"]:
        warnings.append(
            {
                "severity": "error",
                "code": "invalid_trace_refs",
                "message": "Trace edges reference unknown candidates or blocks.",
            }
        )
    if len(candidates) > 2 and not motif_hints:
        warnings.append(
            {
                "severity": "warning",
                "code": "multi_candidate_without_motif_hints",
                "message": "Multiple candidates were extracted but no motif hints were emitted.",
            }
        )
    if (
        len(candidates) > 2
        and motif_hints
        and trace_summary["candidate_coverage_ratio"] >= 0.75
        and motif_summary["candidate_coverage_ratio"] + 0.25 < trace_summary["candidate_coverage_ratio"]
    ):
        warnings.append(
            {
                "severity": "attention",
                "code": "motif_coverage_below_trace_coverage",
                "message": "Trace edges cover most candidates but motif hints cover a much smaller subset.",
            }
        )
    if resource_summary["resource_count"] >= max(len(candidates), 1) * 2:
        type_counts = resource_summary["resource_type_counts"]
        generic_count = sum(type_counts.get(resource_type, 0) for resource_type in ["SourceDocument", "DeliverableSection"])
        if generic_count / max(resource_summary["resource_count"], 1) >= 0.75:
            warnings.append(
                {
                    "severity": "attention",
                    "code": "resource_types_overly_generic",
                    "message": "Most typed resources are generic SourceDocument or DeliverableSection records.",
                }
            )
        if len(type_counts) <= 2 and len(candidates) >= 4:
            warnings.append(
                {
                    "severity": "attention",
                    "code": "low_resource_type_diversity",
                    "message": "Many candidates were extracted but typed resource diversity is low.",
                }
            )
    if motif_summary["unknown_candidate_refs"] or motif_summary["unknown_block_refs"]:
        warnings.append(
            {
                "severity": "error",
                "code": "invalid_motif_refs",
                "message": "Motif hints reference unknown candidates or blocks.",
            }
        )
    return warnings

