"""Compile and validate teacher-only R10 Scenario Bibles from admitted work seeds."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import Field

from task_generator.core.scenario_first import (
    ProfessionalRuleSetV1,
    ScenarioBibleV1,
    ScenarioFirstModel,
    WorkSeedV1,
)


BibleDecision = Literal["pass", "blocked", "incomplete"]


class ScenarioBibleFindingV1(ScenarioFirstModel):
    scenario_id: str
    passed: bool
    reason_codes: list[str] = Field(default_factory=list)


class ScenarioBibleBatchReportV1(ScenarioFirstModel):
    report_version: Literal["r10.scenario_bible_batch_report.1"] = "r10.scenario_bible_batch_report.1"
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str
    model: str
    provider_call_count: int = Field(ge=0, le=1)
    provider_retry_count: Literal[0] = 0
    provider_http_status: int | None = Field(default=None, ge=100, le=599)
    response_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    finish_reason: str | None = None
    usage: dict[str, int | None] = Field(default_factory=dict)
    decision: BibleDecision
    findings: list[ScenarioBibleFindingV1] = Field(default_factory=list)
    first_failure: str | None = None
    validation_error_paths: list[str] = Field(default_factory=list)


class ScenarioBibleStaticValidator:
    """Checks a Bible before any evidence projection is allowed."""

    def evaluate(
        self,
        bible: ScenarioBibleV1,
        *,
        seed: WorkSeedV1,
        rule_set: ProfessionalRuleSetV1,
    ) -> ScenarioBibleFindingV1:
        reasons: list[str] = []
        if bible.work_seed_id != seed.seed_id or bible.rule_set_id != rule_set.rule_set_id:
            reasons.append("seed_or_rule_set_binding_mismatch")
        if not any(role.title.casefold() == seed.role.casefold() for role in bible.roles):
            reasons.append("seed_role_missing_from_bible")
        fact_kinds = [item.kind for item in bible.facts]
        if len(bible.facts) < 12 or len(bible.facts) > 30:
            reasons.append("fact_count_outside_r10_bible_range")
        if fact_kinds.count("normal_background") < 6:
            reasons.append("normal_background_insufficient")
        if not 1 <= fact_kinds.count("anomaly") <= 3:
            reasons.append("anomaly_count_invalid")
        if not 1 <= fact_kinds.count("open_issue") <= 2:
            reasons.append("open_issue_count_invalid")
        if fact_kinds.count("consequence") < 1 or fact_kinds.count("treatment") < 1:
            reasons.append("missing_consequence_or_treatment")
        rule_ids = {item.rule_id for item in rule_set.rules}
        if not any(item.kind == "policy_application" and item.rule_ids for item in bible.facts):
            reasons.append("policy_application_fact_missing")
        if any(not set(item.rule_ids) <= rule_ids for item in bible.facts):
            reasons.append("unknown_rule_reference")
        normalized_statements = [self._normalize(item.statement) for item in bible.facts]
        if len(normalized_statements) != len(set(normalized_statements)):
            reasons.append("duplicate_bible_fact_statement")
        normal_times = [item.occurred_at for item in bible.facts if item.kind == "normal_background"]
        anomaly_times = [item.occurred_at for item in bible.facts if item.kind == "anomaly"]
        treatment_times = [item.occurred_at for item in bible.facts if item.kind == "treatment"]
        if normal_times and anomaly_times and min(anomaly_times) < min(normal_times):
            reasons.append("anomaly_precedes_business_background")
        if anomaly_times and treatment_times and min(treatment_times) < max(anomaly_times):
            reasons.append("treatment_precedes_anomaly")
        return ScenarioBibleFindingV1(
            scenario_id=bible.scenario_id, passed=not reasons, reason_codes=sorted(set(reasons)),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().casefold()


class OfficialDeepSeekScenarioBibleCompiler:
    """One-call, no-retry semantic proposal batch for public R10 seeds."""

    def __init__(
        self,
        request_executor: Callable[[dict[str, Any], str, int], tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.request_executor = request_executor or self._official_request

    def compile(
        self,
        *,
        seeds: list[WorkSeedV1],
        rule_sets: list[ProfessionalRuleSetV1],
        api_key: str,
        output_root: str | Path,
        model: Literal["deepseek-v4-pro"] = "deepseek-v4-pro",
        timeout_seconds: int = 300,
    ) -> ScenarioBibleBatchReportV1:
        output = Path(output_root)
        output.mkdir(parents=True, exist_ok=False)
        input_payload = self._input_payload(seeds, rule_sets)
        input_sha = self._sha256(input_payload)
        self._write_json(output / "input_manifest.json", {
            "input_sha256": input_sha,
            "provider": "deepseek",
            "model": model,
            "seed_ids": [item.seed_id for item in seeds],
            "rule_set_ids": [item.rule_set_id for item in rule_sets],
            "provider_retry_count": 0,
        })
        try:
            status, response = self.request_executor(
                self._request_body(model, input_payload), api_key, timeout_seconds,
            )
            if not 200 <= status < 300:
                return self._failure(output, input_sha, model, f"provider_http_{status}", provider_http_status=status, provider_call_count=1)
            choices = response.get("choices") if isinstance(response, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            content = message.get("content")
            finish_reason = choice.get("finish_reason")
            usage = self._usage(response)
            if not content or finish_reason == "length":
                return self._failure(output, input_sha, model, "empty_or_truncated_provider_content", finish_reason, usage, provider_http_status=status, provider_call_count=1)
            response_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
            self._write_json(output / "provider_response_content.json", {
                "response_sha256": response_sha,
                "content": content,
            })
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                return self._failure(output, input_sha, model, "provider_json_invalid", finish_reason, usage, response_sha, status, provider_call_count=1)
            raw_bibles = payload.get("bibles") if isinstance(payload, dict) else None
            if not isinstance(raw_bibles, list) or len(raw_bibles) != len(seeds):
                return self._failure(output, input_sha, model, "scenario_bible_batch_schema_invalid", finish_reason, usage, response_sha, status, provider_call_count=1)
            try:
                bibles = [ScenarioBibleV1.model_validate(item) for item in raw_bibles]
            except Exception as exc:
                return self._failure(
                    output, input_sha, model, f"scenario_bible_schema_invalid:{type(exc).__name__}",
                    finish_reason, usage, response_sha, status, provider_call_count=1,
                    validation_error_paths=self._validation_error_paths(exc),
                )
        except Exception as exc:
            return self._failure(
                output, input_sha, model, f"provider_or_schema_failure:{type(exc).__name__}",
                provider_call_count=1,
            )

        seeds_by_id = {item.seed_id: item for item in seeds}
        rules_by_id = {item.rule_set_id: item for item in rule_sets}
        findings: list[ScenarioBibleFindingV1] = []
        seen_seed_ids: set[str] = set()
        for bible in bibles:
            seed = seeds_by_id.get(bible.work_seed_id)
            rules = rules_by_id.get(bible.rule_set_id)
            if seed is None or rules is None:
                findings.append(ScenarioBibleFindingV1(
                    scenario_id=bible.scenario_id, passed=False, reason_codes=["unknown_seed_or_rule_set"],
                ))
            else:
                findings.append(ScenarioBibleStaticValidator().evaluate(bible, seed=seed, rule_set=rules))
                seen_seed_ids.add(seed.seed_id)
        if seen_seed_ids != set(seeds_by_id):
            findings.append(ScenarioBibleFindingV1(
                scenario_id="__batch__", passed=False, reason_codes=["seed_coverage_incomplete"],
            ))
        decision: BibleDecision = "pass" if all(item.passed for item in findings) else "blocked"
        for bible in bibles:
            self._write_json(output / "bibles" / f"{bible.scenario_id}.json", bible.model_dump(mode="json"))
        report = ScenarioBibleBatchReportV1(
            input_sha256=input_sha, provider="deepseek", model=model, provider_call_count=1,
            response_sha256=response_sha, finish_reason=finish_reason, usage=usage, provider_http_status=status,
            decision=decision, findings=findings,
        )
        self._write_json(output / "scenario_bible_report.json", report.model_dump(mode="json"))
        return report

    def _failure(self, output: Path, input_sha: str, model: str, failure: str,
                 finish_reason: str | None = None, usage: dict[str, int | None] | None = None,
                 response_sha: str | None = None, provider_http_status: int | None = None,
                 provider_call_count: int = 0, validation_error_paths: list[str] | None = None) -> ScenarioBibleBatchReportV1:
        report = ScenarioBibleBatchReportV1(
            input_sha256=input_sha, provider="deepseek", model=model, provider_call_count=provider_call_count,
            response_sha256=response_sha, finish_reason=finish_reason, usage=usage or {},
            provider_http_status=provider_http_status, decision="incomplete", first_failure=failure,
            validation_error_paths=validation_error_paths or [],
        )
        self._write_json(output / "scenario_bible_report.json", report.model_dump(mode="json"))
        return report

    @staticmethod
    def _input_payload(seeds: list[WorkSeedV1], rule_sets: list[ProfessionalRuleSetV1]) -> dict[str, Any]:
        return {"seeds": [item.model_dump(mode="json") for item in seeds], "rule_sets": [item.model_dump(mode="json") for item in rule_sets]}

    @staticmethod
    def _messages(payload: dict[str, Any]) -> list[dict[str, str]]:
        system = """You are compiling teacher-only professional Scenario Bibles. Return JSON only with exactly {\"bibles\":[...]}. Do not create candidate files, prompts, task packages, answer labels, or hidden reasoning.\n\nEach bibles item MUST be exactly this object shape (no aliases and no additional top-level keys):\n{\"contract_version\":\"r10.scenario_bible.1\",\"scenario_id\":\"string\",\"work_seed_id\":\"one supplied seed_id\",\"rule_set_id\":\"one supplied rule_set_id\",\"organization_name\":\"fictional name\",\"roles\":[{\"role_id\":\"string\",\"title\":\"string\",\"authorities\":[\"string\"]}],\"facts\":[{\"fact_id\":\"string\",\"kind\":\"organization|role|transaction|timeline|policy_application|normal_background|anomaly|open_issue|consequence|treatment\",\"statement\":\"string\",\"occurred_at\":0,\"actor_role_id\":\"role_id or null\",\"authority_required\":\"string or null\",\"knowledge\":\"confirmed|unresolved\",\"rule_ids\":[\"supplied rule id\"]}],\"correct_treatments\":[\"string\"]}\n\nRoles must be objects, not strings. policy_application, consequence, and treatment are fact.kind values inside facts, never top-level fields. Use kind, never type. Each Bible must bind one supplied seed and rule set; include 2-5 roles, 12-30 unique facts, at least six normal_background facts, 1-3 anomaly facts, 1-2 open_issue facts, policy_application, consequence, treatment, and correct_treatments. Use integer occurred_at sequence values. Facts must be fictional but operationally plausible and must not claim that a public source supplied organization-specific facts."""
        return [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]

    @staticmethod
    def _request_body(model: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": model, "messages": OfficialDeepSeekScenarioBibleCompiler._messages(payload),
            "response_format": {"type": "json_object"},
            "thinking": {"type": "enabled"}, "reasoning_effort": "high",
            "max_tokens": 16000, "stream": False,
        }

    @staticmethod
    def _official_request(body: dict[str, Any], api_key: str, timeout_seconds: int) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return int(response.status), json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # The status is diagnostically useful; the body can contain provider details and is not persisted.
            return int(exc.code), {}

    @staticmethod
    def _usage(response: dict[str, Any]) -> dict[str, int | None]:
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        return {"prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"), "total_tokens": usage.get("total_tokens")}

    @staticmethod
    def _validation_error_paths(exc: Exception) -> list[str]:
        errors = getattr(exc, "errors", None)
        if not callable(errors):
            return []
        try:
            return [".".join(str(part) for part in item.get("loc", ())) + ":" + str(item.get("type", "invalid")) for item in errors()[:20]]
        except Exception:
            return []

    @staticmethod
    def _sha256(payload: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
