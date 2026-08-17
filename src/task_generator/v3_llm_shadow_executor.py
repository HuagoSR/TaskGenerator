from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_llm_shadow_common import KIND_CONFIG, ShadowKind
from task_generator.v3_skill_extractor import ProviderConfig, build_tuzi_config, load_env_file
from task_generator.v3_external_model_policy import enforce_external_model_policy


class LLMShadowExecuteRequest(BaseModel):
    llm_shadow_dir: str
    shadow_kind: str = "all"
    model: str = "gemini-3-pro-preview"
    env_path: str
    timeout_seconds: int = 240
    max_tokens: int = 3000
    temperature: float = 0.2
    task_limit: int = 0
    overwrite_completed: bool = False


class LLMShadowExecuteRecord(BaseModel):
    shadow_kind: str
    task_id: str
    status: str
    shadow_report_path: str
    comparison_report_path: str
    model: str
    metric_status: str = "not_available"
    metrics: Dict[str, Any] = Field(default_factory=dict)
    failure_reasons: List[str] = Field(default_factory=list)


class LLMShadowExecuteReport(BaseModel):
    report_version: str = "v3.llm_shadow_execute.1"
    created_at: str
    request: LLMShadowExecuteRequest
    diagnostic_only: bool = True
    not_release_artifact: bool = True
    attempted_count: int
    completed_count: int
    failed_count: int
    records: List[LLMShadowExecuteRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class LLMShadowExecutor:
    def run(self, request: LLMShadowExecuteRequest) -> LLMShadowExecuteReport:
        shadow_root = Path(request.llm_shadow_dir)
        config = self._build_config(request)
        if config is None:
            raise RuntimeError("No OpenAI-compatible model config found in env_path/environment.")
        config.max_tokens = request.max_tokens
        config.temperature = request.temperature

        records: List[LLMShadowExecuteRecord] = []
        for kind in self._selected_kinds(request.shadow_kind):
            records.extend(self._run_kind(shadow_root, kind, request, config))

        report = LLMShadowExecuteReport(
            created_at=self._now(),
            request=request,
            attempted_count=len(records),
            completed_count=sum(1 for record in records if record.status == "completed"),
            failed_count=sum(1 for record in records if record.status != "completed"),
            records=records,
            notes=[
                "This executor writes Phase 14 LLM shadow diagnostics only.",
                "It does not overwrite deterministic GoldenRun, rubric, QA, registry, or release artifacts.",
                "Metrics are first-pass diagnostics for adoption decisions, not proof of LLM quality.",
            ],
        )
        self._write_json(shadow_root / "llm_shadow_execute_report.json", report.model_dump(mode="json"))
        return report

    def _build_config(self, request: LLMShadowExecuteRequest) -> Optional[ProviderConfig]:
        config = build_tuzi_config(request.env_path, request.model, request.timeout_seconds)
        if config is not None:
            return config
        env = load_env_file(request.env_path)
        api_key = env.get("AGENT_API_KEY") or env.get("GRADER_API_KEY")
        base_url = env.get("AGENT_BASE_URL") or env.get("GRADER_BASE_URL")
        model = request.model or env.get("AGENT_MODEL") or env.get("GRADER_MODEL")
        if not api_key or not base_url or not model:
            return None
        enforce_external_model_policy("openai_compatible_env", model)
        return ProviderConfig(
            provider_name="openai_compatible_env",
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=request.timeout_seconds,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    def _run_kind(
        self,
        shadow_root: Path,
        kind: ShadowKind,
        request: LLMShadowExecuteRequest,
        config: ProviderConfig,
    ) -> List[LLMShadowExecuteRecord]:
        batch_path = shadow_root / f"{KIND_CONFIG[kind]['dir']}_batch_report.json"
        if not batch_path.exists():
            return []
        batch = self._read_json(batch_path)
        records: List[Dict[str, Any]] = list(batch.get("records") or [])
        if request.task_limit > 0:
            records = records[: request.task_limit]
        out_records = []
        for record in records:
            out_records.append(self._run_record(kind, record, request, config))
        self._update_batch_report(batch_path, batch, out_records)
        return out_records

    def _run_record(
        self,
        kind: ShadowKind,
        record: Dict[str, Any],
        request: LLMShadowExecuteRequest,
        config: ProviderConfig,
    ) -> LLMShadowExecuteRecord:
        shadow_path = Path(str(record.get("shadow_report_path") or ""))
        comparison_path = Path(str(record.get("comparison_report_path") or ""))
        package_path = Path(str(record.get("prompt_package_path") or ""))
        task_id = str(record.get("task_id") or "")
        if not package_path.exists():
            return self._failed(kind, task_id, shadow_path, comparison_path, config.model, ["prompt_package_missing"])
        if shadow_path.exists() and not request.overwrite_completed:
            existing = self._read_json(shadow_path)
            if existing.get("status") == "completed":
                comparison = self._read_json(comparison_path) if comparison_path.exists() else {}
                return LLMShadowExecuteRecord(
                    shadow_kind=kind,
                    task_id=task_id,
                    status="completed",
                    shadow_report_path=str(shadow_path),
                    comparison_report_path=str(comparison_path),
                    model=str(existing.get("model") or config.model),
                    metric_status=str(comparison.get("metric_status") or "computed"),
                    metrics=dict(comparison.get("metrics") or {}),
                )

        package = self._read_json(package_path)
        try:
            llm_payload = self._call_model(kind, package, config)
            metrics = self._metrics(kind, package, llm_payload)
            shadow = {
                "shadow_version": f"v3.llm_{kind}_shadow.1",
                "created_at": self._now(),
                "task_id": task_id,
                "shadow_kind": kind,
                "model": config.model,
                "status": "completed",
                "diagnostic_only": True,
                "not_release_artifact": True,
                "prompt_package_path": str(package_path),
                "llm_output": llm_payload,
                "notes": [
                    "Generated by approved external LLM shadow execution.",
                    "This output is diagnostic-only and must not be promoted into release artifacts without a later review gate.",
                ],
            }
            comparison = {
                "comparison_version": f"v3.llm_{kind}_comparison.1",
                "created_at": self._now(),
                "task_id": task_id,
                "shadow_kind": kind,
                "status": "completed",
                "metric_status": "computed",
                "diagnostic_only": True,
                "not_release_artifact": True,
                "prompt_package_path": str(package_path),
                "shadow_report_path": str(shadow_path),
                "metrics": metrics,
                "blocking_reasons": [],
            }
            self._write_json(shadow_path, shadow)
            self._write_json(comparison_path, comparison)
            return LLMShadowExecuteRecord(
                shadow_kind=kind,
                task_id=task_id,
                status="completed",
                shadow_report_path=str(shadow_path),
                comparison_report_path=str(comparison_path),
                model=config.model,
                metric_status="computed",
                metrics=metrics,
            )
        except Exception as exc:
            failure = [f"{type(exc).__name__}: {str(exc)[:500]}"]
            return self._failed(kind, task_id, shadow_path, comparison_path, config.model, failure)

    def _call_model(self, kind: ShadowKind, package: Dict[str, Any], config: ProviderConfig) -> Dict[str, Any]:
        enforce_external_model_policy(config.provider_name, config.model)
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"OpenAI SDK is unavailable: {exc}") from exc

        client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout_seconds)
        response = client.chat.completions.create(
            model=config.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You produce diagnostic-only LLM shadow artifacts for a task-generation research pipeline. "
                        "Return valid JSON only. Do not claim access to files beyond the prompt package."
                    ),
                },
                {"role": "user", "content": self._prompt(kind, package)},
            ],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content.")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = {"raw_text": content}
        if not isinstance(payload, dict):
            payload = {"raw_value": payload}
        return payload

    def _prompt(self, kind: ShadowKind, package: Dict[str, Any]) -> str:
        compact = {
            "task_id": package.get("task_id"),
            "shadow_kind": kind,
            "motif": package.get("motif"),
            "prompt": str(package.get("prompt") or "")[:6000],
            "reference_files": package.get("reference_files"),
            "deliverable_files": package.get("deliverable_files"),
            "rubric_excerpt": str(package.get("rubric_excerpt") or "")[:3000],
            "instructions": package.get("instructions"),
            "forbidden_actions": package.get("forbidden_actions"),
        }
        schema = {
            "summary": "short diagnostic summary",
            "strengths": ["supported strength"],
            "risks": ["risk or caveat"],
            "evidence_refs": ["candidate-visible evidence id if present"],
            "shadow_suggestions": ["diagnostic-only suggestion"],
            "hidden_info_or_mutation_risks": ["risk if any"],
        }
        return (
            "Create a diagnostic-only LLM shadow artifact for this package. "
            "Do not rewrite release files. Do not invent hidden ground truth. "
            "Return JSON matching this shape: "
            + json.dumps(schema, ensure_ascii=False)
            + "\n\nPACKAGE:\n"
            + json.dumps(compact, ensure_ascii=False, indent=2)
        )

    def _metrics(self, kind: ShadowKind, package: Dict[str, Any], llm_payload: Dict[str, Any]) -> Dict[str, Any]:
        text = json.dumps(llm_payload, ensure_ascii=False)
        prompt = str(package.get("prompt") or "")
        visible_refs = set(re.findall(r"\bEVID-\d+\b", prompt))
        used_refs = set(re.findall(r"\bEVID-\d+\b", text))
        invalid_refs = sorted(used_refs - visible_refs)
        valid_rate = (len(used_refs - set(invalid_refs)) / len(used_refs)) if used_refs else None
        hidden_mentions = len(re.findall(r"\bhidden|ground truth|teacher-only\b", text, flags=re.IGNORECASE))
        mutation_terms = len(re.findall(r"\boverwrite|modify reference|change reference|promote\b", text, flags=re.IGNORECASE))
        base = {
            "output_nonempty": bool(text.strip()),
            "visible_evidence_ref_count": len(visible_refs),
            "used_evidence_ref_count": len(used_refs),
            "invalid_evidence_ref_count": len(invalid_refs),
            "valid_evidence_ref_rate": valid_rate,
            "hidden_info_violation_count": hidden_mentions,
            "ground_truth_mutation_count": mutation_terms,
        }
        if kind == "goldenrun":
            base["unsupported_claim_rate"] = 0.0 if used_refs or not visible_refs else 0.5
            base["missing_step_candidates"] = len(llm_payload.get("risks") or [])
        elif kind == "rubric":
            base["format_noise_delta"] = 0
            base["added_capability_criteria"] = len(llm_payload.get("shadow_suggestions") or [])
        elif kind == "realism_critic":
            base["realism_critique_alignment"] = "diagnostic_output_present"
            base["friction_signal_count"] = len(llm_payload.get("risks") or [])
            base["workflow_realism_notes"] = llm_payload.get("strengths") or []
        else:
            base["evidence_id_mutation_count"] = len(invalid_refs)
            base["narrative_improvement_candidates"] = len(llm_payload.get("shadow_suggestions") or [])
        return base

    def _update_batch_report(
        self,
        batch_path: Path,
        batch: Dict[str, Any],
        execution_records: List[LLMShadowExecuteRecord],
    ) -> None:
        by_task = {(record.shadow_kind, record.task_id): record for record in execution_records}
        updated_records = []
        for record in batch.get("records") or []:
            key = (str(batch.get("shadow_kind") or ""), str(record.get("task_id") or ""))
            execution = by_task.get(key)
            if execution and execution.status == "completed":
                record["shadow_status"] = "completed"
                record["metric_status"] = "computed"
                metrics = execution.metrics
                for metric_name, value in metrics.items():
                    if metric_name in record or metric_name in {
                        "unsupported_claim_rate",
                        "valid_evidence_ref_rate",
                        "hidden_info_violation_count",
                        "ground_truth_mutation_count",
                    }:
                        record[metric_name] = value
            updated_records.append(record)
        batch["records"] = updated_records
        batch["awaiting_llm_output_count"] = sum(1 for record in updated_records if record.get("shadow_status") == "awaiting_llm_output")
        batch["completed_metric_count"] = sum(1 for record in updated_records if record.get("metric_status") == "computed")
        batch["created_at"] = self._now()
        self._write_json(batch_path, batch)

    def _selected_kinds(self, value: str) -> List[ShadowKind]:
        if value == "all":
            return list(KIND_CONFIG.keys())
        if value not in KIND_CONFIG:
            raise ValueError(f"Unknown shadow kind: {value}")
        return [value]  # type: ignore[list-item]

    def _failed(
        self,
        kind: str,
        task_id: str,
        shadow_path: Path,
        comparison_path: Path,
        model: str,
        reasons: List[str],
    ) -> LLMShadowExecuteRecord:
        return LLMShadowExecuteRecord(
            shadow_kind=kind,
            task_id=task_id,
            status="failed",
            shadow_report_path=str(shadow_path),
            comparison_report_path=str(comparison_path),
            model=model,
            failure_reasons=reasons,
        )

    def _read_json(self, path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
