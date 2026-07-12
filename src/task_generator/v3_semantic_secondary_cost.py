from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SecondaryBudgetExceeded(RuntimeError):
    pass


class SecondaryPriceContract(BaseModel):
    input_rmb_per_million: float = 2.8
    output_rmb_per_million: float = 22.4
    cache_read_rmb_per_million: float = 0.28
    cache_write_rmb_per_million: float = 3.5


class SecondaryCostLedger(BaseModel):
    ledger_version: str = "v3.secondary_cost_ledger.1"
    model: str = "gpt-5.6-sol"
    key_slot: str = "backup"
    budget_rmb: float = 10.0
    pricing: SecondaryPriceContract = Field(default_factory=SecondaryPriceContract)
    spent_rmb: float = 0.0
    remaining_rmb: float = 10.0
    calls: list[Dict[str, Any]] = Field(default_factory=list)


class SecondaryCostLedgerManager:
    def __init__(self, path: str | Path, budget_rmb: float = 10.0) -> None:
        self.path = Path(path)
        if self.path.exists():
            self.ledger = SecondaryCostLedger.model_validate_json(self.path.read_text(encoding="utf-8"))
        else:
            self.ledger = SecondaryCostLedger(budget_rmb=budget_rmb, remaining_rmb=budget_rmb)
            self._write()

    def reserve(self, input_tokens: int = 20_000, output_tokens: int = 1_200) -> float:
        value = self._cost(input_tokens, output_tokens, 0, 0)
        if self.ledger.spent_rmb + value > self.ledger.budget_rmb:
            raise SecondaryBudgetExceeded("secondary_budget_exhausted")
        return value

    def record(
        self,
        *,
        scope: str,
        attempt: int,
        prompt_tokens: int,
        completion_tokens: int,
        cache_read_tokens: Optional[int] = None,
        cache_write_tokens: Optional[int] = None,
        reserved_rmb: float,
        status: str,
    ) -> Dict[str, Any]:
        cache_read = int(cache_read_tokens or 0)
        cache_write = int(cache_write_tokens or 0)
        normal_input = int(prompt_tokens) if cache_read_tokens is None and cache_write_tokens is None else max(
            int(prompt_tokens) - cache_read - cache_write, 0
        )
        cost = self._cost(normal_input, int(completion_tokens), cache_read, cache_write)
        entry = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model": self.ledger.model,
            "key_slot": self.ledger.key_slot,
            "scope": scope,
            "attempt": attempt,
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "cache_read_tokens": cache_read_tokens,
            "cache_write_tokens": cache_write_tokens,
            "reserved_rmb": round(reserved_rmb, 6),
            "actual_cost_rmb": round(cost, 6),
            "status": status,
        }
        self.ledger.calls.append(entry)
        self.ledger.spent_rmb = round(self.ledger.spent_rmb + cost, 6)
        self.ledger.remaining_rmb = round(self.ledger.budget_rmb - self.ledger.spent_rmb, 6)
        self._write()
        return entry

    def _cost(self, normal_input: int, output: int, cache_read: int, cache_write: int) -> float:
        p = self.ledger.pricing
        return (
            normal_input * p.input_rmb_per_million
            + output * p.output_rmb_per_million
            + cache_read * p.cache_read_rmb_per_million
            + cache_write * p.cache_write_rmb_per_million
        ) / 1_000_000

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(self.ledger.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.path)
