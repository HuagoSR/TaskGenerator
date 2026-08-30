"""Minimal admission and review contracts for agent-compiled R10 Skill packages."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import Field

from task_generator.core.scenario_first import ScenarioFirstModel
from task_generator.substrate.professional_skills import ProfessionalSkillCatalogEntryV1, ProfessionalSkillLoader


CompilerDecision = Literal["pass", "blocked", "incomplete"]


class SkillCompilerManifestV1(ScenarioFirstModel):
    """One compact provenance record for a complete compiler-agent batch."""

    manifest_version: Literal["r10.skill_compiler_manifest.1"] = "r10.skill_compiler_manifest.1"
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    model: Literal["gpt-5.6-sol"] = "gpt-5.6-sol"
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decision: CompilerDecision
    first_failure: str | None = None


class SkillContentReviewV1(ScenarioFirstModel):
    review_version: Literal["r10.skill_content_review.1"] = "r10.skill_content_review.1"
    skill_id: str
    provider: Literal["deepseek"] = "deepseek"
    model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    provider_call_count: int = Field(ge=0, le=2)
    provider_retry_count: int = Field(default=0, ge=0, le=1)
    decision: CompilerDecision
    response_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    supported_source_ids: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    first_failure: str | None = None


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def admit_compiled_skill(*, entry: ProfessionalSkillCatalogEntryV1, package_root: Path, forbidden_terms: set[str]) -> list[str]:
    """Keep only hard package, provenance, and answer-separation boundaries."""
    errors: list[str] = []
    try:
        loaded = ProfessionalSkillLoader().load_skill(entry, skills_root=package_root.parent)
    except Exception:
        return ["compiled_skill_package_invalid"]
    if package_root.name != entry.relative_path:
        errors.append("compiled_skill_path_mismatch")
    source_map = loaded.reference_markdown.get("references/source-map.md", "")
    urls = re.findall(r"https://[^\s)]+", source_map)
    allowed_hosts = {"pcaobus.org", "www.pcaobus.org", "acquisition.gov", "www.acquisition.gov", "dau.edu", "www.dau.edu"}
    if not urls:
        errors.append("compiled_skill_source_map_missing_urls")
    if any(urllib.parse.urlparse(url).hostname not in allowed_hosts for url in urls):
        errors.append("compiled_skill_source_host_not_allowed")
    text = (loaded.skill_markdown + "\n" + source_map).casefold()
    if any(term.casefold() in text for term in forbidden_terms):
        errors.append("compiled_skill_contains_private_or_answer_content")
    if "candidate/" in text or "teacher/" in text:
        errors.append("compiled_skill_prescribes_task_layout")
    return sorted(set(errors))


class OfficialDeepSeekSkillContentReviewer:
    """Independent content/source review; it never writes the Skill."""

    def __init__(self, request_executor: Callable[[dict[str, Any], str, int], tuple[int, dict[str, Any]]] | None = None) -> None:
        self.request_executor = request_executor or self._official_request

    def review(self, *, entry: ProfessionalSkillCatalogEntryV1, package_root: Path, api_key: str, timeout_seconds: int = 300) -> SkillContentReviewV1:
        skill = (package_root / "SKILL.md").read_text(encoding="utf-8")
        source_map = (package_root / "references" / "source-map.md").read_text(encoding="utf-8")
        body = {
            "model": "deepseek-v4-pro",
            "messages": [
                {"role": "system", "content": "Review a factory-side professional Skill. Return JSON only with decision (pass or blocked), supported_source_ids, and issues. Pass only if it is a concise occupational-situation review guide, preserves candidate decision space, and its non-obvious guidance is plausibly supported by the supplied source map. Do not rewrite the Skill."},
                {"role": "user", "content": json.dumps({"skill_id": entry.skill_id, "skill": skill, "source_map": source_map}, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"}, "thinking": {"type": "enabled"}, "max_tokens": 3000, "stream": False,
        }
        first_failure: str | None = None
        for attempt in range(2):
            try:
                status, response = self.request_executor(body, api_key, timeout_seconds)
                content = ((response.get("choices") or [{}])[0].get("message") or {}).get("content") if isinstance(response, dict) else None
                if not 200 <= status < 300:
                    failure = f"provider_http_{status}"
                elif not content:
                    failure = "empty_provider_content"
                else:
                    raw = json.loads(content)
                    decision = raw.get("decision")
                    if decision not in {"pass", "blocked"}:
                        failure = "provider_json_or_schema_invalid"
                    else:
                        return SkillContentReviewV1(skill_id=entry.skill_id, decision=decision, provider_call_count=attempt + 1, provider_retry_count=attempt, response_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(), supported_source_ids=[item for item in raw.get("supported_source_ids", []) if isinstance(item, str)], issues=[item for item in raw.get("issues", []) if isinstance(item, str)])
            except Exception as exc:
                failure = f"provider_transport_failure:{type(exc).__name__}"
            if first_failure is None:
                first_failure = failure
            retryable = failure in {"empty_provider_content", "provider_json_or_schema_invalid", "provider_http_408", "provider_http_429"} or failure.startswith("provider_http_5") or failure.startswith("provider_transport_failure")
            if not retryable:
                break
        return SkillContentReviewV1(skill_id=entry.skill_id, decision="incomplete", provider_call_count=2 if first_failure and retryable else 1, provider_retry_count=1 if first_failure and retryable else 0, first_failure=first_failure)

    @staticmethod
    def _official_request(body: dict[str, Any], api_key: str, timeout_seconds: int) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request("https://api.deepseek.com/chat/completions", data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return int(response.status), json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return int(exc.code), {}
