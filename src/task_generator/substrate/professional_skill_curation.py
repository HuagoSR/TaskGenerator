"""One-batch, source-bound curation for the two R10 professional Skills."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import Field, model_validator

from task_generator.core.scenario_first import ScenarioFirstModel
from task_generator.substrate.professional_skills import ProfessionalSkillCatalogV1


CurationDecision = Literal["pass", "blocked", "incomplete"]
EvidenceKind = Literal["rule", "practice", "failure_mode"]


class ProfessionalSkillCurationSourceV1(ScenarioFirstModel):
    source_id: str = Field(min_length=1)
    skill_id: str = Field(min_length=1)
    evidence_kind: EvidenceKind
    title: str = Field(min_length=1)
    locator: str = Field(pattern=r"^https://")
    section: str = Field(min_length=1)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    summary: str = Field(min_length=1, max_length=800)


class ProfessionalSkillCurationSourcesV1(ScenarioFirstModel):
    contract_version: Literal["r10.professional_skill_curation_sources.1"] = "r10.professional_skill_curation_sources.1"
    accessed_at: date
    sources: list[ProfessionalSkillCurationSourceV1] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_sources(self) -> "ProfessionalSkillCurationSourcesV1":
        if len({item.source_id for item in self.sources}) != len(self.sources):
            raise ValueError("duplicate_curation_source_id")
        return self


class CuratedProfessionalInstructionV1(ScenarioFirstModel):
    text: str = Field(min_length=20, max_length=500)
    source_ids: list[str] = Field(min_length=1, max_length=3)


class CuratedSkillDraftV1(ScenarioFirstModel):
    skill_id: str
    instructions: list[CuratedProfessionalInstructionV1] = Field(min_length=3, max_length=6)
    trigger_examples: list[str] = Field(min_length=1, max_length=3)
    exclusions: list[str] = Field(min_length=1, max_length=3)


class ProfessionalSkillCurationFindingV1(ScenarioFirstModel):
    skill_id: str
    passed: bool
    reason_codes: list[str] = Field(default_factory=list)


class ProfessionalSkillCurationReportV1(ScenarioFirstModel):
    report_version: Literal["r10.professional_skill_curation_report.1"] = "r10.professional_skill_curation_report.1"
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: Literal["deepseek"] = "deepseek"
    model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro"
    provider_call_count: int = Field(ge=0, le=2)
    provider_retry_count: int = Field(ge=0, le=1)
    response_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decision: CurationDecision
    findings: list[ProfessionalSkillCurationFindingV1] = Field(default_factory=list)
    first_failure: str | None = None
    usage: dict[str, int | None] = Field(default_factory=dict)


class OfficialDeepSeekProfessionalSkillCurator:
    """Use one frozen batch; one format/transport retry is the only retry."""

    def __init__(self, request_executor: Callable[[dict[str, Any], str, int], tuple[int, dict[str, Any]]] | None = None) -> None:
        self.request_executor = request_executor or self._official_request

    def curate(
        self,
        *,
        catalog: ProfessionalSkillCatalogV1,
        sources: ProfessionalSkillCurationSourcesV1,
        api_key: str,
        output_root: Path,
        timeout_seconds: int = 300,
    ) -> tuple[ProfessionalSkillCurationReportV1, list[CuratedSkillDraftV1]]:
        output_root.mkdir(parents=True, exist_ok=False)
        payload = self._input_payload(catalog, sources)
        input_sha = self._sha(payload)
        self._write(output_root / "input_manifest.json", {"input_sha256": input_sha, "provider": "deepseek", "model": "deepseek-v4-pro", "provider_retry_count": 0})
        first_failure: str | None = None
        call_count = 0
        retry_count = 0
        usage: dict[str, int | None] = {}
        for attempt in range(2):
            try:
                call_count += 1
                status, response = self.request_executor(self._request_body(payload), api_key, timeout_seconds)
                content, usage = self._content(response)
                if not 200 <= status < 300:
                    failure = f"provider_http_{status}"
                elif not content or (response.get("choices") or [{}])[0].get("finish_reason") == "length":
                    failure = "empty_provider_content"
                else:
                    response_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    self._write(output_root / f"provider_response_attempt_{attempt + 1}.json", {"response_sha256": response_sha, "content": content})
                    try:
                        raw = json.loads(content)
                        drafts = [CuratedSkillDraftV1.model_validate(item) for item in raw.get("skills", [])]
                    except Exception:
                        failure = "provider_json_or_schema_invalid"
                    else:
                        findings = self._review(catalog, sources, drafts)
                        report = ProfessionalSkillCurationReportV1(
                            input_sha256=input_sha, provider_call_count=call_count,
                            provider_retry_count=retry_count, response_sha256=response_sha,
                            decision="pass" if all(item.passed for item in findings) else "blocked",
                            findings=findings, usage=usage,
                        )
                        self._write(output_root / "professional_skill_curation_report.json", report.model_dump(mode="json"))
                        if report.decision == "pass":
                            self._write(output_root / "curated_skill_drafts.json", {"skills": [item.model_dump(mode="json") for item in drafts]})
                        return report, drafts
            except Exception as exc:
                failure = f"provider_transport_failure:{type(exc).__name__}"
                usage = {}
            if first_failure is None:
                first_failure = failure
            retryable = (
                failure in {"empty_provider_content", "provider_json_or_schema_invalid", "provider_http_408", "provider_http_429"}
                or failure.startswith("provider_http_5")
                or failure.startswith("provider_transport_failure")
            )
            if attempt == 0 and retryable:
                retry_count = 1
                continue
            break
        report = ProfessionalSkillCurationReportV1(
            input_sha256=input_sha, provider_call_count=call_count,
            provider_retry_count=retry_count, decision="incomplete",
            first_failure=first_failure, usage=usage,
        )
        self._write(output_root / "professional_skill_curation_report.json", report.model_dump(mode="json"))
        return report, []

    @staticmethod
    def _review(catalog: ProfessionalSkillCatalogV1, sources: ProfessionalSkillCurationSourcesV1, drafts: list[CuratedSkillDraftV1]) -> list[ProfessionalSkillCurationFindingV1]:
        source_ids = {item.source_id for item in sources.sources}
        source_kinds = {entry.skill_id: {item.evidence_kind for item in sources.sources if item.skill_id == entry.skill_id} for entry in catalog.entries}
        drafts_by_id = {item.skill_id: item for item in drafts}
        findings: list[ProfessionalSkillCurationFindingV1] = []
        for entry in catalog.entries:
            reasons: list[str] = []
            draft = drafts_by_id.get(entry.skill_id)
            if draft is None:
                reasons.append("missing_skill_draft")
            else:
                for instruction in draft.instructions:
                    if not set(instruction.source_ids) <= source_ids:
                        reasons.append("instruction_unknown_source")
                if any("correct treatment" in instruction.text.lower() for instruction in draft.instructions):
                    reasons.append("instruction_contains_teacher_answer_language")
            if source_kinds[entry.skill_id] != {"rule", "practice", "failure_mode"}:
                reasons.append("source_evidence_mix_incomplete")
            findings.append(ProfessionalSkillCurationFindingV1(skill_id=entry.skill_id, passed=not reasons, reason_codes=sorted(set(reasons))))
        if len(drafts_by_id) != len(drafts):
            findings.append(ProfessionalSkillCurationFindingV1(skill_id="__batch__", passed=False, reason_codes=["duplicate_skill_draft"]))
        return findings

    @staticmethod
    def _input_payload(catalog: ProfessionalSkillCatalogV1, sources: ProfessionalSkillCurationSourcesV1) -> dict[str, Any]:
        return {"catalog": catalog.model_dump(mode="json"), "sources": sources.model_dump(mode="json")}

    @staticmethod
    def _request_body(payload: dict[str, Any]) -> dict[str, Any]:
        system = (
            "You curate source-grounded factory-side professional Skills. Return JSON only: "
            '{"skills":[{"skill_id":"...","instructions":[{"text":"...","source_ids":["..."]}],"trigger_examples":["..."],"exclusions":["..."]}]}. '
            "Produce one item per supplied catalog entry. Each instruction must cite supplied source_ids only. "
            "Do not invent facts, companies, amounts, task answers, or generic file-tool advice. "
            "Keep judgment conditional on evidence and do not prescribe a fixed task layout."
        )
        return {"model": "deepseek-v4-pro", "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}, "max_tokens": 6000, "stream": False}

    @staticmethod
    def _official_request(body: dict[str, Any], api_key: str, timeout_seconds: int) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request("https://api.deepseek.com/chat/completions", data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return int(response.status), json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return int(exc.code), {}

    @staticmethod
    def _content(response: dict[str, Any]) -> tuple[str | None, dict[str, int | None]]:
        choice = (response.get("choices") or [{}])[0] if isinstance(response, dict) else {}
        message = choice.get("message") if isinstance(choice, dict) else {}
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        return message.get("content") if isinstance(message, dict) else None, {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"), "total_tokens": usage.get("total_tokens")}

    @staticmethod
    def _sha(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
