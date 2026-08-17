import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.task_generator.v3_semantic_review_executor import (
    SemanticReviewExecutionError,
    SemanticReviewExecutor,
    claude_semantic_config,
    tuzi_backup_semantic_config,
)
from src.task_generator.v3_semantic_secondary_cost import (
    SecondaryBudgetExceeded,
    SecondaryCostLedgerManager,
)
from src.task_generator.v3_semantic_validity import SecondaryFindingDecision, SecondarySemanticReview
from src.task_generator.v3_skill_extractor import ProviderConfig


class SecondaryReviewGovernanceTests(unittest.TestCase):
    def test_expensive_claude_semantic_config_is_blocked_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text(
                "AGENT_API_KEY=secret\nAGENT_BASE_URL=https://example.invalid/v1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(PermissionError, "project_blocked"):
                claude_semantic_config(env)

    def test_backup_slot_does_not_fall_back_to_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text("OPENAI_API_KEY=primary-only\nOPENAI_BASE_URL=https://example.invalid/v1\n", encoding="utf-8")
            with self.assertRaisesRegex(SemanticReviewExecutionError, "backup"):
                tuzi_backup_semantic_config(env)
            env.write_text("OPENAI_API_KEY=primary\nOPENAI_API_KEY_BACKUP=backup\nOPENAI_BASE_URL=https://example.invalid/v1\n", encoding="utf-8")
            config = tuzi_backup_semantic_config(env)
            self.assertEqual(config.api_key, "backup")
            self.assertEqual(config.model, "gpt-5.6-sol")

    def test_cost_ledger_is_atomic_and_enforces_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            manager = SecondaryCostLedgerManager(path, 0.1)
            reserved = manager.reserve()
            manager.record(scope="candidate_blind", attempt=1, prompt_tokens=12000,
                           completion_tokens=1000, reserved_rmb=reserved, status="completed")
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["key_slot"], "backup")
            self.assertLess(payload["spent_rmb"], 0.1)
            with self.assertRaises(SecondaryBudgetExceeded):
                SecondaryCostLedgerManager(Path(directory) / "tiny.json", 0.01).reserve()

    def test_compact_contract_limits(self):
        with self.assertRaises(ValidationError):
            SecondaryFindingDecision(
                finding_family="candidate_support", material=True, confidence=1,
                evidence_locators=["a", "b", "c", "d", "e"], rationale="ok",
            )
        decisions = [SecondaryFindingDecision(
            finding_family="candidate_support", material=False, confidence=1, rationale="ok"
        ) for _ in range(7)]
        with self.assertRaises(ValidationError):
            SecondarySemanticReview(
                task_id="t", review_scope="candidate_blind", model="m", provider="p",
                created_at="now", decisions=decisions,
            )

    def test_prompt_budget_fails_without_truncation(self):
        executor = SemanticReviewExecutor(
            ProviderConfig(provider_name="test", base_url="https://example.invalid", api_key="x", model="m"),
            input_token_hard_limit=10,
        )
        with self.assertRaisesRegex(SemanticReviewExecutionError, "secondary_prompt_budget_exceeded"):
            executor._enforce_secondary_prompt_budget({"large": "x" * 100})


if __name__ == "__main__":
    unittest.main()
