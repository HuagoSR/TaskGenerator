from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import socket
from typing import Any, Dict, List, Sequence
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from task_generator.v3_source_collector import (
    CollectedSourceRecord,
    SourceCollectionRequest,
    SourceCollectionReport,
    build_collection_request,
    write_collected_sources,
)
from task_generator.v3_source_schema import dump_json_file


SERPER_SEARCH_URL = "https://google.serper.dev/search"
DEFAULT_WEBFETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_SOURCE_BYTES = 5 * 1024 * 1024
ALLOWED_SOURCE_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
TRANSPARENT_PROXY_BENCHMARK_NETWORK = ipaddress.ip_network("198.18.0.0/15")


@dataclass
class SearchHit:
    query: str
    rank: int
    title: str
    url: str
    snippet: str


def _excerpt(text: str, limit: int = 1200) -> str:
    compact = " ".join(text.split())
    return compact[:limit].strip()


def _why_relevant(topic: str, title: str) -> str:
    return (
        f"This source was selected because it appears directly relevant to the topic '{topic}' "
        f"and may contain reusable workflow details, evidence handling patterns, or domain procedures for {title!r}."
    )


class DirectWebSourceCollector:
    def __init__(
        self,
        *,
        api_key: str,
        search_timeout_seconds: int = 180,
        fetch_timeout_seconds: int = 180,
        search_result_count: int = 5,
    ) -> None:
        self.api_key = api_key
        self.search_timeout_seconds = search_timeout_seconds
        self.fetch_timeout_seconds = fetch_timeout_seconds
        self.search_result_count = search_result_count

    def build_request(
        self,
        *,
        topic: str,
        domain_tags: Sequence[str],
        queries: Sequence[str],
        source_count: int,
        collector_model: str = "direct_serper_trafilatura",
        search_backend: str = "serper_direct",
    ) -> SourceCollectionRequest:
        return build_collection_request(
            topic=topic,
            domain_tags=list(domain_tags),
            queries=list(queries),
            source_count=source_count,
            collector_model=collector_model,
            e2b_template="not_applicable",
            search_backend=search_backend,
        )

    def collect(
        self,
        *,
        output_dir: str,
        request: SourceCollectionRequest,
        seed_urls: Sequence[str] = (),
    ) -> Dict[str, Any]:
        search_metadata: List[Dict[str, Any]] = []
        records: List[CollectedSourceRecord] = []
        failures: List[Dict[str, Any]] = []
        seen_urls: set[str] = set()

        with httpx.Client(follow_redirects=True, timeout=self.search_timeout_seconds) as client:
            if seed_urls:
                hits = [
                    SearchHit(
                        query="exact_url",
                        rank=rank,
                        title=url,
                        url=url,
                        snippet="",
                    )
                    for rank, url in enumerate(seed_urls, start=1)
                ]
                search_metadata.extend(
                    {
                        "query": hit.query,
                        "rank": hit.rank,
                        "title": hit.title,
                        "url": hit.url,
                        "snippet": hit.snippet,
                    }
                    for hit in hits
                )
            else:
                hits = self._search(client, request, search_metadata)
            for hit in hits:
                if len(records) >= request.source_count:
                    break
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                try:
                    fetched = self._fetch_record(hit)
                except Exception as exc:
                    failures.append(
                        {
                            "query": hit.query,
                            "title": hit.title,
                            "url": hit.url,
                            "error": str(exc),
                        }
                    )
                    continue
                if fetched is None:
                    failures.append(
                        {
                            "query": hit.query,
                            "title": hit.title,
                            "url": hit.url,
                            "error": "Main text extraction returned too little readable content.",
                        }
                    )
                    continue
                records.append(
                    CollectedSourceRecord(
                        title=fetched["title"],
                        url=hit.url,
                        text_excerpt=fetched["text_excerpt"],
                        domain_tags=request.domain_tags,
                        why_relevant=_why_relevant(request.topic, fetched["title"]),
                        raw_text=fetched["raw_text"],
                        collection_trace=[
                            (
                                f"exact_url:{hit.url}"
                                if hit.query == "exact_url"
                                else f"search_query:{hit.query}"
                            ),
                            f"source_rank:{hit.rank}",
                            "collector_backend:direct",
                            "content_extraction:trafilatura",
                        ],
                        metadata={
                            "search_query": hit.query,
                            "search_rank": hit.rank,
                            "search_snippet": hit.snippet,
                            "collector_backend": "direct",
                        },
                    )
                )

        report = write_collected_sources(output_dir, request, records)
        report.notes.extend(
            [
                (
                    "This collection was produced by deterministic code using exact public URLs, httpx fetch, and trafilatura extraction."
                    if seed_urls
                    else "This collection was produced by deterministic code using Serper search, httpx fetch, and trafilatura extraction."
                ),
                "No Stirrup agent or E2B sandbox was used for this run.",
            ]
        )
        dump_json_file(report, f"{output_dir}/collection_report.json")
        metadata = {
            "backend": "direct",
            "input_mode": "exact_urls" if seed_urls else "serper_search",
            "search_queries": request.queries,
            "search_result_count": self.search_result_count,
            "search_hits_examined": len(search_metadata),
            "record_count": len(records),
            "failure_count": len(failures),
            "failures": failures,
            "search_metadata": search_metadata,
            "report_status": report.status,
        }
        metadata_path = Path(output_dir) / "artifacts" / "direct_collection_metadata.json"
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "request": request,
            "report": report,
            "metadata": metadata,
        }

    def _search(
        self,
        client: httpx.Client,
        request: SourceCollectionRequest,
        search_metadata: List[Dict[str, Any]],
    ) -> List[SearchHit]:
        hits: List[SearchHit] = []
        for query in request.queries:
            response = client.post(
                SERPER_SEARCH_URL,
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": self.search_result_count},
            )
            response.raise_for_status()
            payload = response.json()
            organic = payload.get("organic", []) or []
            for rank, result in enumerate(organic, start=1):
                url = str(result.get("link", "") or "").strip()
                if not url:
                    continue
                hit = SearchHit(
                    query=query,
                    rank=rank,
                    title=str(result.get("title", "") or "").strip(),
                    url=url,
                    snippet=str(result.get("snippet", "") or "").strip(),
                )
                hits.append(hit)
                search_metadata.append(
                    {
                        "query": query,
                        "rank": rank,
                        "title": hit.title,
                        "url": hit.url,
                        "snippet": hit.snippet,
                    }
                )
        return hits

    def _fetch_record(self, hit: SearchHit) -> Dict[str, str] | None:
        current_url = hit.url
        body = b""
        encoding = "utf-8"
        with httpx.Client(
            follow_redirects=False,
            timeout=self.fetch_timeout_seconds,
            headers=DEFAULT_WEBFETCH_HEADERS,
        ) as client:
            for _ in range(6):
                self._validate_public_url(current_url)
                with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise RuntimeError("Redirect response did not include a location header.")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type and not any(content_type.startswith(item) for item in ALLOWED_SOURCE_CONTENT_TYPES):
                        raise RuntimeError(f"Unsupported public source content type: {content_type}")
                    chunks = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_SOURCE_BYTES:
                            raise RuntimeError("Public source response exceeded the 5 MiB production limit.")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    break
            else:
                raise RuntimeError("Public source exceeded the redirect limit.")
        text = body.decode(encoding, errors="replace")
        raw_text = trafilatura.extract(text, output_format="markdown") or ""
        excerpt = _excerpt(raw_text)
        if len(excerpt) < 120:
            fallback = _excerpt(hit.snippet)
            if len(fallback) < 120:
                return None
            excerpt = fallback
        return {
            "title": hit.title or hit.url,
            "text_excerpt": excerpt,
            "raw_text": raw_text.strip(),
        }

    def _validate_public_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("Only public http/https source URLs are allowed.")
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith(".localhost"):
            raise RuntimeError("Localhost source URLs are forbidden.")
        try:
            literal_host = ipaddress.ip_address(host)
        except ValueError:
            literal_host = None
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        }
        if not addresses:
            raise RuntimeError("Source URL did not resolve to an address.")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            proxy_mapped_public_https = (
                literal_host is None
                and parsed.scheme == "https"
                and ip in TRANSPARENT_PROXY_BENCHMARK_NETWORK
            )
            if not ip.is_global and not proxy_mapped_public_https:
                raise RuntimeError(f"Source URL resolved to a non-public address: {address}")
