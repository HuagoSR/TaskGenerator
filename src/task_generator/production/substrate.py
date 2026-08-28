"""Fresh, run-scoped source-to-skill substrate for the R9 production cohort."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Literal, Optional

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field

from task_generator.core.source_schema import (
    ExtractedSkillCandidate,
    NormalizedSource,
    SkillExtractionPromptPackage,
    SourceBlock,
    SourceSpan,
)
from task_generator.production.campaign import (
    ProductionDomain,
    ProductionSourceRecordV1,
    atomic_json,
    canonical_sha,
    file_sha,
    tree_sha,
)
from task_generator.substrate.skill_extractor import LLMSkillExtractor, ProviderConfig
from task_generator.substrate.skill_registry import SkillRegistryBuilder, slugify


def _visible_blocks(html: str, source_id: str) -> List[SourceBlock]:
    """Extract stable, human-readable source blocks without executing page content."""

    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script,style,noscript,nav,footer,header,aside,svg,form"):
        node.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    seen: set[str] = set()
    blocks: List[SourceBlock] = []
    offset = 0
    for node in root.select("h1,h2,h3,h4,p,li,tr"):
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if len(text) < 40 or text in seen:
            continue
        seen.add(text)
        block_id = f"block_{len(blocks) + 1:04d}"
        blocks.append(
            SourceBlock(
                block_id=block_id,
                block_type="table" if node.name == "tr" else "paragraph",
                text=text,
                source_span=SourceSpan(
                    source_id=source_id,
                    block_id=block_id,
                    start_char=offset,
                    end_char=offset + len(text),
                    quote=text[:500],
                ),
            )
        )
        offset += len(text) + 1
        if len(blocks) >= 80:
            break
    if len(blocks) < 3:
        raise ValueError("production_source_normalization_too_small")
    return blocks


def _prompt_package(
    *, campaign_id: str, domain: ProductionDomain, sources: List[NormalizedSource]
) -> SkillExtractionPromptPackage:
    source_ids = ",".join(item.source_id for item in sources)
    return SkillExtractionPromptPackage(
        request_id="skill_extract_" + canonical_sha(
            {"campaign_id": campaign_id, "domain": domain, "sources": source_ids}
        )[:16],
        normalized_sources=sources,
        instructions=(
            f"Extract reusable semantic skills only for the exact domain tag `{domain}`. "
            "Return source-grounded capabilities, not task answers, filenames, row counts, "
            "or fixed rubric language. Every candidate must cite the supplied source and block IDs."
        ),
        constraints=[
            "Return valid JSON only.",
            "Every candidate domain_tags must include the exact requested domain tag.",
            "Every candidate needs input/output semantics, capability tags, hidden difficulty, "
            "failure modes, common deliverables, assembly hints, and at least one evidence item.",
            "Use only source IDs and block IDs present in this package.",
        ],
    )


def _retryable_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "timeout", "timed out", "connection", "empty content", "empty response",
        "invalid json", "json", "schema", "truncat", "finish_reason=length",
        " 408", " 429", " 500", " 502", " 503", " 504", " 524",
    )
    return any(marker in text for marker in markers)


def _safe_error(exc: Exception, secret: str) -> str:
    return str(exc).replace(secret, "[REDACTED]")[:1000]


def _candidate_review(
    candidate: ExtractedSkillCandidate,
    *,
    domain: ProductionDomain,
    source_blocks: Dict[str, set[str]],
) -> Optional[str]:
    if domain not in candidate.domain_tags:
        return "candidate_domain_mismatch"
    if not candidate.source_ids or not set(candidate.source_ids) <= set(source_blocks):
        return "candidate_unknown_source"
    if not candidate.capability_tags or not candidate.business_meaning.strip() or not candidate.hidden_difficulty.strip():
        return "candidate_semantic_description_missing"
    if not candidate.common_failure_modes or not candidate.common_deliverables or not candidate.assembly_hints:
        return "candidate_operational_detail_missing"
    if not (candidate.input_contract.requires_semantics or candidate.output_contract.provides_semantics):
        return "candidate_semantic_contract_missing"
    if not candidate.evidence:
        return "candidate_evidence_missing"
    for evidence in candidate.evidence:
        if evidence.source_id not in source_blocks:
            return "evidence_unknown_source"
        if not evidence.block_ids or not set(evidence.block_ids) <= source_blocks[evidence.source_id]:
            return "evidence_unknown_block"
    return None


class ProductionSubstrateDomainV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain: ProductionDomain
    prompt_package_path: str
    prompt_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_source_paths: List[str] = Field(min_length=3, max_length=3)
    provider_attempt_count: int = Field(ge=1, le=2)
    provider_attempts: List[dict] = Field(min_length=1, max_length=2)
    candidate_path: str
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_candidate_path: str
    accepted_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_path: str
    review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_count: int = Field(ge=3)


class ProductionSubstrateManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_version: Literal["v3.production_substrate.1"] = "v3.production_substrate.1"
    campaign_id: str
    source_manifest_path: str
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: Literal["tuzi"] = "tuzi"
    model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    sdk_retry_count: Literal[0] = 0
    canonical_registry_sha256_before: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_registry_sha256_after: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_registry_mutated: Literal[False] = False
    scratch_registry_path: str
    scratch_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    domains: List[ProductionSubstrateDomainV1] = Field(min_length=2, max_length=2)


class ProductionSubstrateBuilder:
    """Build a fresh source-to-skill substrate without mutating the canonical registry."""

    def __init__(
        self,
        *,
        extractor_factory: Callable[[ProviderConfig], LLMSkillExtractor] = LLMSkillExtractor,
    ) -> None:
        self.extractor_factory = extractor_factory

    def build(
        self,
        *,
        campaign_id: str,
        sources: List[ProductionSourceRecordV1],
        source_manifest_path: str | Path,
        output_root: str | Path,
        canonical_registry_root: str | Path,
        provider_config: ProviderConfig,
    ) -> ProductionSubstrateManifestV1:
        if provider_config.provider_name != "tuzi" or provider_config.model != "gpt-5.6-sol":
            raise ValueError("production_substrate_provider_mismatch")
        output = Path(output_root).resolve()
        output.mkdir(parents=True, exist_ok=False)
        source_manifest = Path(source_manifest_path).resolve()
        registry_root = Path(canonical_registry_root).resolve()
        registry_before = tree_sha(registry_root)
        normalized_by_domain: Dict[ProductionDomain, List[NormalizedSource]] = defaultdict(list)
        source_blocks: Dict[str, set[str]] = {}
        normalized_root = output / "normalized_sources"
        normalized_root.mkdir()
        for source in sources:
            path = Path(source.collected_path)
            if not path.is_file() or file_sha(path) != source.content_sha256:
                raise ValueError("production_substrate_source_drift")
            blocks = _visible_blocks(path.read_text(encoding="utf-8", errors="replace"), source.source_id)
            normalized = NormalizedSource(
                normalized_source_id="normalized_" + canonical_sha(
                    {"campaign_id": campaign_id, "source_id": source.source_id, "content": source.content_sha256}
                )[:16],
                source_id=source.source_id,
                title=source.source_id.replace("_", " "),
                domain_tags=[source.domain],
                blocks=blocks,
                normalizer_version="r9_html_visible_text.1",
            )
            path = normalized_root / f"{normalized.normalized_source_id}.json"
            atomic_json(path, normalized)
            normalized_by_domain[source.domain].append(normalized)
            source_blocks[source.source_id] = {block.block_id for block in blocks}

        domain_records: List[ProductionSubstrateDomainV1] = []
        all_accepted: List[ExtractedSkillCandidate] = []
        for domain in ("audit_compliance", "procurement_operations"):
            normalized = normalized_by_domain[domain]
            if len(normalized) != 3:
                raise ValueError("production_substrate_domain_source_count")
            package = _prompt_package(campaign_id=campaign_id, domain=domain, sources=normalized)
            domain_root = output / domain
            domain_root.mkdir()
            package_path = domain_root / "skill_extraction_prompt_package.json"
            atomic_json(package_path, package)
            attempts: List[dict] = []
            candidates: Optional[List[ExtractedSkillCandidate]] = None
            for attempt in (1, 2):
                extractor = self.extractor_factory(provider_config)
                try:
                    candidates = extractor.extract(package, max_candidates=8)
                    diagnostics = getattr(extractor, "last_response_diagnostics", None)
                    attempts.append(
                        {
                            "attempt": attempt,
                            "status": "completed",
                            "diagnostics": {
                                "finish_reason": getattr(diagnostics, "finish_reason", None),
                                "prompt_tokens": getattr(diagnostics, "prompt_tokens", None),
                                "completion_tokens": getattr(diagnostics, "completion_tokens", None),
                                "response_sha256": getattr(diagnostics, "response_sha256", None),
                            },
                        }
                    )
                    break
                except Exception as exc:
                    attempts.append(
                        {
                            "attempt": attempt,
                            "status": "failed",
                            "error_type": type(exc).__name__,
                            "error_message": _safe_error(exc, provider_config.api_key),
                            "retryable": _retryable_error(exc),
                        }
                    )
                    if attempt == 2 or not _retryable_error(exc):
                        raise RuntimeError(f"production_substrate_extraction_failed:{domain}") from exc
            if candidates is None:
                raise RuntimeError("production_substrate_candidates_missing")
            canonicalized = self._canonicalize(candidates, campaign_id=campaign_id, domain=domain)
            candidate_path = domain_root / "extracted_skill_candidates.json"
            atomic_json(candidate_path, {"candidates": [item.model_dump(mode="json") for item in canonicalized]})
            accepted, review_rows = self._review(canonicalized, domain=domain, source_blocks=source_blocks)
            review_path = domain_root / "candidate_review.json"
            atomic_json(review_path, {"domain": domain, "reviews": review_rows})
            if len(accepted) < 3:
                raise ValueError(f"production_substrate_accepted_pool_too_small:{domain}")
            accepted_path = domain_root / "accepted_candidates.json"
            atomic_json(accepted_path, {"accepted_candidates": [item.model_dump(mode="json") for item in accepted]})
            all_accepted.extend(accepted)
            domain_records.append(
                ProductionSubstrateDomainV1(
                    domain=domain,
                    prompt_package_path=str(package_path),
                    prompt_package_sha256=file_sha(package_path),
                    normalized_source_paths=[str(normalized_root / f"{item.normalized_source_id}.json") for item in normalized],
                    provider_attempt_count=len(attempts),
                    provider_attempts=attempts,
                    candidate_path=str(candidate_path),
                    candidate_sha256=file_sha(candidate_path),
                    accepted_candidate_path=str(accepted_path),
                    accepted_candidate_sha256=file_sha(accepted_path),
                    review_path=str(review_path),
                    review_sha256=file_sha(review_path),
                    accepted_count=len(accepted),
                )
            )
        scratch_path = output / "scratch_registry.json"
        SkillRegistryBuilder().write_registry(scratch_path, SkillRegistryBuilder().build_entries(all_accepted))
        registry_after = tree_sha(registry_root)
        if registry_before != registry_after:
            raise RuntimeError("production_substrate_canonical_registry_mutated")
        manifest = ProductionSubstrateManifestV1(
            campaign_id=campaign_id,
            source_manifest_path=str(source_manifest),
            source_manifest_sha256=file_sha(source_manifest),
            source_tree_sha256=tree_sha(source_manifest.parent),
            canonical_registry_sha256_before=registry_before,
            canonical_registry_sha256_after=registry_after,
            scratch_registry_path=str(scratch_path),
            scratch_registry_sha256=file_sha(scratch_path),
            domains=domain_records,
        )
        atomic_json(output / "substrate_manifest.json", manifest)
        return manifest

    @staticmethod
    def _canonicalize(
        candidates: Iterable[ExtractedSkillCandidate], *, campaign_id: str, domain: ProductionDomain
    ) -> List[ExtractedSkillCandidate]:
        values = []
        for candidate in candidates:
            old_evidence_ids = [item.evidence_id for item in candidate.evidence]
            evidence_map = {
                old: "evidence_" + canonical_sha(
                    {"campaign_id": campaign_id, "domain": domain, "candidate": candidate.candidate_id, "evidence": old}
                )[:16]
                for old in old_evidence_ids
            }
            evidence = [item.model_copy(update={"evidence_id": evidence_map[item.evidence_id]}) for item in candidate.evidence]
            values.append(
                candidate.model_copy(
                    update={
                        "candidate_id": "skill_candidate_" + canonical_sha(
                            {"campaign_id": campaign_id, "domain": domain, "candidate": candidate.candidate_id, "name": candidate.proposed_name}
                        )[:16],
                        "evidence": evidence,
                        "extraction_status": "candidate",
                    }
                )
            )
        return values

    @staticmethod
    def _review(
        candidates: Iterable[ExtractedSkillCandidate], *, domain: ProductionDomain,
        source_blocks: Dict[str, set[str]],
    ) -> tuple[List[ExtractedSkillCandidate], List[dict]]:
        accepted: List[ExtractedSkillCandidate] = []
        rows: List[dict] = []
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        for candidate in candidates:
            reason = _candidate_review(candidate, domain=domain, source_blocks=source_blocks)
            name = slugify(candidate.proposed_name)
            if reason is None and candidate.candidate_id in seen_ids:
                reason = "candidate_id_not_unique"
            if reason is None and name in seen_names:
                reason = "candidate_name_not_unique"
            accepted_flag = reason is None
            rows.append({"candidate_id": candidate.candidate_id, "decision": "accepted" if accepted_flag else "rejected", "reason": reason})
            if accepted_flag:
                seen_ids.add(candidate.candidate_id)
                seen_names.add(name)
                accepted.append(candidate.model_copy(update={"extraction_status": "accepted"}))
        return accepted, rows
