import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from v3_source_schema import RawSource, dump_json_file


CollectionStatus = Literal["success", "partial_success", "failed"]


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "source_collection"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceCollectionRequest(BaseModel):
    request_id: str
    topic: str
    domain_tags: List[str] = Field(default_factory=list)
    queries: List[str] = Field(default_factory=list)
    source_count: int = 3
    collector_model: str = ""
    e2b_template: str = "rw-task-sandbox:stable"
    search_backend: str = "serper"
    created_at: str = Field(default_factory=utc_now)
    notes: List[str] = Field(default_factory=list)


class CollectedSourceRecord(BaseModel):
    title: str
    url: str
    text_excerpt: str
    domain_tags: List[str] = Field(default_factory=list)
    retrieved_at: str = Field(default_factory=utc_now)
    why_relevant: str
    source_type: str = "web_page"
    raw_text: str = ""
    collection_trace: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SourceCollectionReport(BaseModel):
    request_id: str
    status: CollectionStatus
    requested_source_count: int
    collected_source_count: int
    accepted_source_count: int
    collector_model: str
    e2b_template: str
    search_backend: str = ""
    validation_errors: List[str] = Field(default_factory=list)
    raw_source_paths: List[str] = Field(default_factory=list)
    raw_text_paths: List[str] = Field(default_factory=list)
    manifest_path: str = ""
    notes: List[str] = Field(default_factory=list)


def build_collection_request(
    topic: str,
    domain_tags: List[str],
    queries: List[str],
    source_count: int,
    collector_model: str,
    e2b_template: str,
    search_backend: str = "serper",
) -> SourceCollectionRequest:
    request_key = "::".join([topic, ",".join(domain_tags), ",".join(queries), str(source_count)])
    return SourceCollectionRequest(
        request_id=stable_id("source_collect_req", request_key),
        topic=topic,
        domain_tags=sorted(set(domain_tags)),
        queries=queries or [topic],
        source_count=source_count,
        collector_model=collector_model,
        e2b_template=e2b_template,
        search_backend=search_backend,
        notes=[
            "Collector gathers source materials only.",
            "Collector must not extract skills, generate tasks, or write rubrics.",
        ],
    )


def build_collection_prompt(request: SourceCollectionRequest) -> str:
    schema = {
        "sources": [
            {
                "title": "Source title",
                "url": "https://example.com/source",
                "text_excerpt": "A readable excerpt of the source material, not just a search result snippet.",
                "domain_tags": request.domain_tags,
                "retrieved_at": "ISO-8601 timestamp",
                "why_relevant": "Why this source is useful for later semantic skill extraction.",
                "source_type": "web_page",
                "raw_text": "Optional longer excerpt or notes copied from the public source.",
                "collection_trace": ["Search/query step and selection rationale."],
                "metadata": {"publisher": "optional", "query": "optional"},
            }
        ]
    }
    return (
        "# Source Collection Task\n\n"
        "You are collecting public source material for a later source-to-skill extraction pipeline.\n"
        "Your job is only to find and save source materials. Do not extract skills, do not create tasks, "
        "and do not write rubrics.\n\n"
        f"Topic: {request.topic}\n"
        f"Domain tags: {', '.join(request.domain_tags)}\n"
        f"Target source count: {request.source_count}\n"
        f"Suggested queries: {json.dumps(request.queries, ensure_ascii=False)}\n\n"
        "Requirements:\n"
        "- Use web search to find public, citable, relevant materials.\n"
        "- Prefer professional guides, regulatory guidance, case writeups, audit/accounting explainers, or public examples.\n"
        "- Use at most 3 web_search calls and at most 5 fetch_web_page calls.\n"
        "- Once you have enough evidence for the target source count, stop searching and finish immediately.\n"
        "- Each source must include a URL, title, readable excerpt, retrieval timestamp, and relevance rationale.\n"
        "- The excerpt must contain actual source content, not just a search result title or URL.\n"
        "- Do not include private, paywalled-only, or credentialed materials.\n"
        "- Do not include GDPVal rubrics, answer traces, or generated deliverables.\n"
        "- Prefer finishing with 3 good sources over continuing to search for perfect sources.\n"
        "- Finish by returning only JSON matching this shape:\n\n"
        f"```json\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n```\n"
    )


def load_collection_manifest(path: str | Path) -> List[CollectedSourceRecord]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return records_from_payload(payload)


def records_from_payload(payload: Any) -> List[CollectedSourceRecord]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if isinstance(payload, dict) and "sources" in payload:
        payload = payload["sources"]
    if not isinstance(payload, list):
        raise ValueError("Collection manifest must contain a sources array.")
    return [CollectedSourceRecord.model_validate(item) for item in payload]


def validate_records(records: List[CollectedSourceRecord], requested_count: int) -> List[str]:
    errors: List[str] = []
    if len(records) < requested_count:
        errors.append(f"collected_source_count_below_requested:{len(records)}<{requested_count}")
    seen_urls = set()
    for idx, record in enumerate(records, start=1):
        prefix = f"source_{idx}"
        if not record.title.strip():
            errors.append(f"{prefix}:missing_title")
        if not record.url.strip().lower().startswith(("http://", "https://")):
            errors.append(f"{prefix}:missing_or_invalid_url")
        if record.url in seen_urls:
            errors.append(f"{prefix}:duplicate_url")
        seen_urls.add(record.url)
        if len(record.text_excerpt.strip()) < 120:
            errors.append(f"{prefix}:excerpt_too_short")
        if not record.domain_tags:
            errors.append(f"{prefix}:missing_domain_tags")
        if not record.retrieved_at.strip():
            errors.append(f"{prefix}:missing_retrieved_at")
        if not record.why_relevant.strip():
            errors.append(f"{prefix}:missing_relevance_rationale")
        if not record.collection_trace:
            errors.append(f"{prefix}:missing_collection_trace")
    return errors


def write_collected_sources(
    output_dir: str | Path,
    request: SourceCollectionRequest,
    records: List[CollectedSourceRecord],
) -> SourceCollectionReport:
    out = Path(output_dir)
    raw_source_dir = out / "raw_sources"
    raw_text_dir = out / "raw_text"
    artifacts_dir = out / "artifacts"
    raw_source_dir.mkdir(parents=True, exist_ok=True)
    raw_text_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    validation_errors = validate_records(records, request.source_count)
    accepted_records = [
        record
        for idx, record in enumerate(records, start=1)
        if not any(error.startswith(f"source_{idx}:") for error in validation_errors)
    ]

    raw_source_paths: List[str] = []
    raw_text_paths: List[str] = []
    manifest_sources: List[Dict[str, Any]] = []
    for record in accepted_records:
        source_id = stable_id("web_src", f"{record.url}::{record.title}")
        text_path = raw_text_dir / f"{source_id}.md"
        source_text = record.raw_text.strip() or record.text_excerpt.strip()
        text_path.write_text(
            "\n".join(
                [
                    f"# {record.title}",
                    "",
                    f"URL: {record.url}",
                    f"Retrieved at: {record.retrieved_at}",
                    "",
                    source_text,
                    "",
                    "## Relevance",
                    record.why_relevant,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        raw_source = RawSource(
            source_id=source_id,
            source_type="web_page",
            domain_tags=sorted(set(record.domain_tags + request.domain_tags)),
            url_or_path=record.url,
            retrieved_at=record.retrieved_at,
            title=record.title,
            raw_text_path=str(text_path.resolve()),
            collector_model=request.collector_model,
            collection_trace=record.collection_trace,
            metadata={
                "collection_request_id": request.request_id,
                "why_relevant": record.why_relevant,
                "source_metadata": record.metadata,
            },
        )
        raw_source_path = raw_source_dir / f"{source_id}.json"
        dump_json_file(raw_source, str(raw_source_path))
        raw_source_paths.append(str(raw_source_path))
        raw_text_paths.append(str(text_path))
        manifest_sources.append(
            {
                "source_id": source_id,
                "title": record.title,
                "url": record.url,
                "raw_source_path": str(raw_source_path),
                "raw_text_path": str(text_path),
                "domain_tags": raw_source.domain_tags,
            }
        )

    status: CollectionStatus
    if len(accepted_records) >= request.source_count and not validation_errors:
        status = "success"
    elif accepted_records:
        status = "partial_success"
    else:
        status = "failed"

    manifest_path = out / "manifest.json"
    manifest = {
        "request_id": request.request_id,
        "collector_model": request.collector_model,
        "e2b_template": request.e2b_template,
        "search_backend": request.search_backend,
        "source_count": len(manifest_sources),
        "sources": manifest_sources,
        "validation_errors": validation_errors,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return SourceCollectionReport(
        request_id=request.request_id,
        status=status,
        requested_source_count=request.source_count,
        collected_source_count=len(records),
        accepted_source_count=len(accepted_records),
        collector_model=request.collector_model,
        e2b_template=request.e2b_template,
        search_backend=request.search_backend,
        validation_errors=validation_errors,
        raw_source_paths=raw_source_paths,
        raw_text_paths=raw_text_paths,
        manifest_path=str(manifest_path),
        notes=[
            "Collector output contains source materials only.",
            "Skill extraction and registry updates must be run as separate Pipeline A steps.",
        ],
    )
