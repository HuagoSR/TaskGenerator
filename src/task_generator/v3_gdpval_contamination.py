from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from pydantic import BaseModel, Field


def normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def text_sha256(value: str) -> str:
    return hashlib.sha256(normalized_text(value).encode("utf-8")).hexdigest()


def token_ngrams(value: str, size: int = 12) -> Iterable[str]:
    tokens = normalized_text(value).split()
    for index in range(max(0, len(tokens) - size + 1)):
        yield hashlib.sha256(" ".join(tokens[index : index + size]).encode("utf-8")).hexdigest()


class ProtectedGDPValIndex(BaseModel):
    version: str = "v3.gdpval_protected_index.1"
    task_count: int = 0
    task_ids: List[str] = Field(default_factory=list)
    prompt_hashes: Dict[str, str] = Field(default_factory=dict)
    protected_uri_hashes: Dict[str, str] = Field(default_factory=dict)
    reference_file_hashes: Dict[str, str] = Field(default_factory=dict)
    twelve_token_hash_to_task_ids: Dict[str, List[str]] = Field(default_factory=dict)
    contains_raw_prompt: bool = False


class GDPValContaminationLedger(BaseModel):
    version: str = "v3.gdpval_contamination_ledger.1"
    source_manifest_path: str
    source_records: List[Dict[str, Any]] = Field(default_factory=list)
    generation_root: str
    generation_process_accessed_gdpval: bool = False
    external_provider_received_gdpval: bool = False
    exact_task_id_hits: List[Dict[str, str]] = Field(default_factory=list)
    protected_uri_hits: List[Dict[str, str]] = Field(default_factory=list)
    exact_prompt_hash_hits: List[Dict[str, str]] = Field(default_factory=list)
    exact_reference_hash_hits: List[Dict[str, str]] = Field(default_factory=list)
    twelve_token_review_hits: List[Dict[str, Any]] = Field(default_factory=list)
    decision: str = "pass"
    blocking_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    contains_raw_gdpval_content: bool = False


def build_protected_index(rows: Iterable[Dict[str, Any]], reference_root: Optional[Path] = None) -> ProtectedGDPValIndex:
    task_ids: List[str] = []
    prompt_hashes: Dict[str, str] = {}
    uri_hashes: Dict[str, str] = {}
    file_hashes: Dict[str, str] = {}
    ngram_map: Dict[str, List[str]] = {}
    for row in rows:
        task_id = str(row.get("task_id") or "")
        prompt = str(row.get("prompt") or "")
        if task_id:
            task_ids.append(task_id)
        if task_id and prompt:
            prompt_hashes[text_sha256(prompt)] = task_id
            for digest in token_ngrams(prompt):
                ngram_map.setdefault(digest, []).append(task_id)
        for key in ("reference_file_hf_uris", "reference_file_urls"):
            for uri in row.get(key) or []:
                uri_hashes[hashlib.sha256(str(uri).encode("utf-8")).hexdigest()] = task_id
        if reference_root and reference_root.exists():
            for name in row.get("reference_files") or []:
                candidate = reference_root / str(name)
                if candidate.is_file():
                    file_hashes[hashlib.sha256(candidate.read_bytes()).hexdigest()] = task_id
    return ProtectedGDPValIndex(
        task_count=len(task_ids),
        task_ids=sorted(task_ids),
        prompt_hashes=prompt_hashes,
        protected_uri_hashes=uri_hashes,
        reference_file_hashes=file_hashes,
        twelve_token_hash_to_task_ids={key: sorted(set(value)) for key, value in ngram_map.items()},
    )


def audit_generation(
    source_manifest_path: str | Path,
    generation_root: str | Path,
    protected_index: ProtectedGDPValIndex,
) -> GDPValContaminationLedger:
    source_path = Path(source_manifest_path)
    root = Path(generation_root)
    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    ledger = GDPValContaminationLedger(
        source_manifest_path=str(source_path),
        source_records=list(source_payload.get("sources") or []),
        generation_root=str(root),
        notes=[
            "GDPVal is checked only after generation as an isolated release gate.",
            "No semantic-similarity result may be used to tune or rewrite generated tasks.",
        ],
    )
    for path in sorted(root.rglob("*")) if root.exists() else []:
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in protected_index.reference_file_hashes:
            ledger.exact_reference_hash_hits.append({"path": relative, "task_id": protected_index.reference_file_hashes[digest]})
        if path.suffix.lower() not in {".json", ".md", ".txt", ".yaml", ".yml", ".csv"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for task_id in protected_index.task_ids:
            if task_id and task_id in text:
                ledger.exact_task_id_hits.append({"path": relative, "task_id": task_id})
        for uri_hash, task_id in protected_index.protected_uri_hashes.items():
            for token in re.findall(r"https?://[^\s\"']+|hf://[^\s\"']+", text):
                if hashlib.sha256(token.rstrip(").,]").encode("utf-8")).hexdigest() == uri_hash:
                    ledger.protected_uri_hits.append({"path": relative, "task_id": task_id})
        prompt_digest = text_sha256(text)
        if prompt_digest in protected_index.prompt_hashes:
            ledger.exact_prompt_hash_hits.append({"path": relative, "task_id": protected_index.prompt_hashes[prompt_digest]})
        hit_counts: Counter[str] = Counter()
        for ngram_digest in token_ngrams(text):
            for task_id in protected_index.twelve_token_hash_to_task_ids.get(ngram_digest, []):
                hit_counts[task_id] += 1
        for task_id, count in hit_counts.items():
            ledger.twelve_token_review_hits.append({"path": relative, "task_id": task_id, "matching_12_token_window_count": count})

    if ledger.exact_task_id_hits:
        ledger.blocking_reasons.append("exact_gdpval_task_id_present")
    if ledger.protected_uri_hits:
        ledger.blocking_reasons.append("gdpval_uri_present")
    if ledger.exact_prompt_hash_hits:
        ledger.blocking_reasons.append("exact_gdpval_prompt_present")
    if ledger.exact_reference_hash_hits:
        ledger.blocking_reasons.append("exact_gdpval_reference_file_present")
    if ledger.blocking_reasons:
        ledger.decision = "blocked"
    elif ledger.twelve_token_review_hits:
        ledger.decision = "manual_review"
    return ledger


def aggregate_domain_feasibility(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    occupations: Dict[str, Dict[str, Any]] = {}
    sectors: Counter[str] = Counter()
    for row in rows:
        sector = str(row.get("sector") or "")
        occupation = str(row.get("occupation") or "")
        sectors[sector] += 1
        record = occupations.setdefault(
            occupation,
            {"sector": sector, "task_count": 0, "reference_extensions": Counter(), "deliverable_extensions": Counter()},
        )
        record["task_count"] += 1
        record["reference_extensions"].update(Path(name).suffix.lower() for name in row.get("reference_files") or [])
        record["deliverable_extensions"].update(Path(name).suffix.lower() for name in row.get("deliverable_files") or [])
    hard_file_exts = {".wav", ".mp3", ".mp4", ".psd", ".step", ".zip", ".py", ".ipynb", ".overpassql", ".yaml"}
    high_stakes_terms = {"lawyer", "nurse", "pharmacist", "social worker", "compliance"}
    output = []
    for occupation, record in sorted(occupations.items()):
        all_exts = set(record["reference_extensions"]) | set(record["deliverable_extensions"])
        lowered = occupation.lower()
        file_risk = "high" if all_exts & hard_file_exts else "standard"
        expert_risk = "high" if any(term in lowered for term in high_stakes_terms) else "standard"
        recommendation = "defer" if "high" in {file_risk, expert_risk} else "candidate"
        output.append(
            {
                "occupation": occupation,
                "sector": record["sector"],
                "task_count": record["task_count"],
                "reference_extensions": dict(sorted(record["reference_extensions"].items())),
                "deliverable_extensions": dict(sorted(record["deliverable_extensions"].items())),
                "file_risk": file_risk,
                "expert_risk": expert_risk,
                "recommendation": recommendation,
            }
        )
    return {
        "version": "v3.gdpval_domain_feasibility.1",
        "task_count": sum(sectors.values()),
        "sector_count": len(sectors),
        "occupation_count": len(output),
        "sector_task_counts": dict(sorted(sectors.items())),
        "occupations": output,
        "contains_prompt": False,
        "contains_rubric": False,
        "usage_boundary": "eval_calibration_only_metadata_audit",
    }
