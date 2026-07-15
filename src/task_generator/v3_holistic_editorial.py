from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from task_generator.v3_semantic_review_executor import SemanticReviewExecutionError, tuzi_backup_semantic_config
from task_generator.v3_whole_task_materializer import WholeTaskRevisionBundleV2


class WholeTaskRevisionBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    overall_decision: Literal["revise", "already_valid", "cannot_repair"]
    issue_summary: list[str] = Field(max_length=8)
    revised_prompt: str
    candidate_file_changes: list[Dict[str, Any]] = Field(default_factory=list, max_length=8)
    expected_result: Dict[str, Any]
    calculation_explanation: list[str] = Field(max_length=12)
    rubric: list[Dict[str, Any]] = Field(min_length=3, max_length=10)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=5)


class CandidateSolveReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    answerable: bool
    key_results: Dict[str, Any]
    evidence_used: list[str] = Field(default_factory=list, max_length=12)
    ambiguity_or_hidden_assumptions: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)


class HolisticCostLedger:
    PRICES = {
        "gpt-5.6-terra": {"input": 1.40, "output": 11.20, "cache_read": 0.14, "cache_write": 1.75},
        "gpt-5.6-luna": {"input": 0.56, "output": 4.48, "cache_read": 0.056, "cache_write": 0.70},
    }

    def __init__(self, path: str | Path, budget_rmb: float = 50.0, request_cap: int = 40) -> None:
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {
                "ledger_version": "v3.holistic_editorial_cost.1",
                "key_slot": "backup",
                "budget_rmb": budget_rmb,
                "request_cap": request_cap,
                "pricing_source": "tuzi_/api/pricing_2026-07-13_scaled_from_user_sol_price",
                "spent_rmb": 0.0,
                "remaining_rmb": budget_rmb,
                "requests": [],
            }
            self._write()

    def reserve(self, model: str, input_limit: int, output_limit: int) -> float:
        if len(self.data["requests"]) >= self.data["request_cap"]:
            raise SemanticReviewExecutionError("holistic_provider_request_cap_exhausted")
        price = self.PRICES[model]
        reserve = (input_limit * price["input"] + output_limit * price["output"]) / 1_000_000
        if self.data["spent_rmb"] + reserve > self.data["budget_rmb"]:
            raise SemanticReviewExecutionError("holistic_budget_exhausted")
        return reserve

    def record(self, model: str, role: str, attempt: int, usage: Any, reserve: float, status: str) -> None:
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        price = self.PRICES[model]
        cost = (prompt * price["input"] + completion * price["output"]) / 1_000_000
        self.data["requests"].append({
            "created_at": datetime.now(timezone.utc).isoformat(), "model": model, "role": role,
            "attempt": attempt, "prompt_tokens": prompt, "completion_tokens": completion,
            "reserved_rmb": round(reserve, 6), "actual_cost_rmb": round(cost, 6), "status": status,
        })
        self.data["spent_rmb"] = round(self.data["spent_rmb"] + cost, 6)
        self.data["remaining_rmb"] = round(self.data["budget_rmb"] - self.data["spent_rmb"], 6)
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)


class HolisticEditorialExecutor:
    def __init__(self, env_path: str | Path, ledger: HolisticCostLedger, timeout_seconds: int = 900) -> None:
        self.env_path = Path(env_path)
        self.ledger = ledger
        self.timeout_seconds = timeout_seconds
        self.last_diagnostics: Dict[str, Any] = {}

    def revise(self, payload: Dict[str, Any], attempt: int = 1) -> WholeTaskRevisionBundle:
        system = (
            "You are the senior editor of one complete real-world finance task. Review the task as a whole, not as "
            "isolated schema fields. Preserve its scenario and motif, but directly rewrite everything needed so the "
            "candidate-visible evidence supports a unique answer, teacher truth is independently reproducible, and "
            "at least 60% of rubric weight checks business facts or deliverable correctness. Return a complete revision."
        )
        return self._call("gpt-5.6-terra", "whole_task_editor", system, payload, WholeTaskRevisionBundle, 4000, attempt)

    def revise_v2(self, payload: Dict[str, Any], attempt: int = 1) -> WholeTaskRevisionBundleV2:
        system = (
            "You are the senior editor of one complete real-world finance task. Return the complete target state for "
            "the task after revision. Candidate file operations are restricted to retain, add, and replace. For an "
            "XLSX add/replace, content must map each sheet name to a rectangular array whose first row is the header. "
            "For a DOCX add/replace, content must be either complete plain text or a title/sections object. For JSON, "
            "content must be the complete JSON value. Retained files must omit content. Preserve the motif and source "
            "evidence, remove hidden assumptions and cross-template residue, and make every requested result uniquely "
            "computable from candidate-visible inputs. Expected numbers and rubric suggestions are advisory: a local "
            "deterministic resolver will recompute truth and regenerate the governed rubric."
        )
        return self._call(
            "gpt-5.6-terra", "whole_task_editor_v2", system, payload,
            WholeTaskRevisionBundleV2, 6000, attempt,
        )

    def solve(self, payload: Dict[str, Any], attempt: int = 1) -> CandidateSolveReview:
        system = (
            "Act as an independent candidate. Use only the candidate-visible prompt and reference contents. Determine "
            "whether the task is answerable and independently compute its key results. Do not guess teacher truth. "
            "The ambiguity_or_hidden_assumptions list must contain only unresolved ambiguities or assumptions that are "
            "actually required to answer; do not repeat explicit prompt constraints, stated rules, or prudent caveats."
        )
        return self._call("gpt-5.6-luna", "candidate_blind_solver", system, payload, CandidateSolveReview, 2500, attempt)

    def _call(self, model: str, role: str, system: str, payload: Dict[str, Any], result_type, max_tokens: int, attempt: int):
        from openai import OpenAI
        config = tuzi_backup_semantic_config(self.env_path, model, self.timeout_seconds)
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        estimated = (len(serialized) + 3) // 4
        if estimated > 40_000:
            raise SemanticReviewExecutionError("holistic_prompt_budget_exceeded")
        reserve = self.ledger.reserve(model, 40_000, max_tokens)
        schema = result_type.model_json_schema()
        started = time.monotonic()
        response = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout_seconds).chat.completions.create(
            model=model, temperature=0, max_tokens=max_tokens, response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system + " Return exactly one JSON object matching: " + json.dumps(schema, ensure_ascii=False)},
                {"role": "user", "content": serialized},
            ],
        )
        content = response.choices[0].message.content or ""
        finish = str(response.choices[0].finish_reason or "")
        status = "completed" if content and finish.lower() != "length" else "failed"
        self.ledger.record(model, role, attempt, response.usage, reserve, status)
        self.last_diagnostics = {
            "model": model, "role": role, "key_slot": "backup", "finish_reason": finish,
            "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
            "completion_tokens": getattr(response.usage, "completion_tokens", None),
            "duration_seconds": round(time.monotonic() - started, 3),
            "response_sha256": hashlib.sha256(content.encode()).hexdigest(), "raw_response_included": False,
        }
        if status != "completed":
            raise SemanticReviewExecutionError("holistic_provider_output_incomplete")
        try:
            return result_type.model_validate(json.loads(content))
        except Exception as exc:
            raise SemanticReviewExecutionError(f"holistic_provider_contract_violation:{type(exc).__name__}") from exc
