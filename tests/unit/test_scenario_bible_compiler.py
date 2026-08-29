from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_generator.core.scenario_first import ProfessionalRuleSetV1, ScenarioBibleV1, WorkSeedV1
from task_generator.planning.scenario_bible_compiler import OfficialDeepSeekScenarioBibleCompiler
from task_generator.planning.work_seed_admission import WorkSeedCandidateV1


_ROOT = Path(__file__).parents[2] / "data" / "r10" / "work_seeds"


def _inputs():
    candidates = [WorkSeedCandidateV1.model_validate(item) for item in json.loads((_ROOT / "candidate_work_seeds.json").read_text(encoding="utf-8"))]
    seeds = [item.seed for item in candidates if item.status == "admitted"]
    rules = [ProfessionalRuleSetV1.model_validate(item) for item in json.loads((_ROOT / "professional_rule_sets.json").read_text(encoding="utf-8"))]
    return seeds, rules


def _bible(seed: WorkSeedV1, rule_set: ProfessionalRuleSetV1) -> dict:
    rule_id = rule_set.rules[0].rule_id
    facts = [
        {"fact_id": f"normal_{index}", "kind": "normal_background", "statement": f"Normal operating fact {index} for {seed.seed_id}.", "occurred_at": index, "actor_role_id": "role_primary"}
        for index in range(1, 7)
    ]
    facts += [
        {"fact_id": "anomaly_1", "kind": "anomaly", "statement": "A record relationship does not agree across operational sources.", "occurred_at": 7, "actor_role_id": "role_primary", "rule_ids": [rule_id]},
        {"fact_id": "open_1", "kind": "open_issue", "statement": "A supporting record has not yet been supplied.", "occurred_at": 8, "actor_role_id": "role_primary", "knowledge": "unresolved", "rule_ids": [rule_id]},
        {"fact_id": "policy_1", "kind": "policy_application", "statement": "The professional rule applies to the pending decision.", "occurred_at": 9, "actor_role_id": "role_primary", "rule_ids": [rule_id]},
        {"fact_id": "consequence_1", "kind": "consequence", "statement": "An unsupported conclusion could delay the business decision.", "occurred_at": 10, "actor_role_id": "role_manager"},
        {"fact_id": "treatment_1", "kind": "treatment", "statement": "The reviewer documents a supported disposition and requests missing evidence.", "occurred_at": 11, "actor_role_id": "role_primary", "rule_ids": [rule_id]},
        {"fact_id": "transaction_1", "kind": "transaction", "statement": "The reviewed business item has a unique operational identifier.", "occurred_at": 4, "actor_role_id": "role_primary"},
    ]
    return {
        "scenario_id": "scenario_" + seed.seed_id.removeprefix("seed_"),
        "work_seed_id": seed.seed_id,
        "rule_set_id": rule_set.rule_set_id,
        "organization_name": "Fictional Operations Group",
        "roles": [
            {"role_id": "role_primary", "title": seed.role, "authorities": ["review evidence", "document disposition"]},
            {"role_id": "role_manager", "title": "Review manager", "authorities": ["approve escalation"]},
        ],
        "facts": facts,
        "correct_treatments": ["Document only the disposition supported by the available evidence and request missing support."],
    }


class ScenarioBibleCompilerTests(unittest.TestCase):
    def test_compiles_single_frozen_deepseek_batch_without_key_persistence(self):
        seeds, rules = _inputs()
        rules_by_domain = {item.domain: item for item in rules}
        content = json.dumps({"bibles": [_bible(seed, rules_by_domain[seed.domain]) for seed in seeds]})
        holder = {}
        def executor(body, api_key, timeout):
            holder.update(body=body, api_key=api_key, timeout=timeout)
            return 200, {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300}}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            report = OfficialDeepSeekScenarioBibleCompiler(executor).compile(
                seeds=seeds, rule_sets=rules, api_key="deepseek-secret-marker", output_root=output,
            )
            persisted = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file())
            saved_response = (output / "provider_response_content.json").is_file()
        self.assertEqual(report.decision, "pass")
        self.assertEqual(holder["body"]["response_format"], {"type": "json_object"})
        self.assertEqual(holder["body"]["thinking"], {"type": "disabled"})
        self.assertIn('"work_seed_id"', holder["body"]["messages"][0]["content"])
        self.assertIn("Use kind, never type", holder["body"]["messages"][0]["content"])
        self.assertIn("produce exactly 14 facts", holder["body"]["messages"][0]["content"])
        self.assertEqual(holder["api_key"], "deepseek-secret-marker")
        self.assertNotIn("deepseek-secret-marker", persisted)
        self.assertTrue(saved_response)

    def test_invalid_batch_is_frozen_incomplete_without_retry(self):
        seeds, rules = _inputs()
        holder = {}
        def executor(*args):
            holder["calls"] = holder.get("calls", 0) + 1
            return 200, {"choices": [{"message": {"content": "{\"bibles\": []}"}, "finish_reason": "stop"}], "usage": {}}
        with tempfile.TemporaryDirectory() as directory:
            report = OfficialDeepSeekScenarioBibleCompiler(executor).compile(
                seeds=seeds, rule_sets=rules, api_key="secret", output_root=Path(directory) / "batch",
            )
        self.assertEqual(report.decision, "incomplete")
        self.assertEqual(report.provider_call_count, 1)
        self.assertEqual(holder["calls"], 1)

    def test_schema_failure_preserves_response_content_and_sha(self):
        seeds, rules = _inputs()
        content = json.dumps({"bibles": [{"scenario_id": "missing_required_fields"}] * 4})
        def executor(*args):
            return 200, {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {}}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            report = OfficialDeepSeekScenarioBibleCompiler(executor).compile(
                seeds=seeds, rule_sets=rules, api_key="secret", output_root=output,
            )
            payload = json.loads((output / "provider_response_content.json").read_text(encoding="utf-8"))
        self.assertEqual(report.decision, "incomplete")
        self.assertTrue(report.response_sha256)
        self.assertEqual(payload["response_sha256"], report.response_sha256)
        self.assertTrue(report.validation_error_paths)

    def test_http_failure_is_frozen_without_response_or_retry(self):
        seeds, rules = _inputs()
        calls = 0
        def executor(*args):
            nonlocal calls
            calls += 1
            return 429, {}
        with tempfile.TemporaryDirectory() as directory:
            report = OfficialDeepSeekScenarioBibleCompiler(executor).compile(
                seeds=seeds, rule_sets=rules, api_key="secret", output_root=Path(directory) / "batch",
            )
        self.assertEqual(calls, 1)
        self.assertEqual(report.decision, "incomplete")
        self.assertEqual(report.first_failure, "provider_http_429")
        self.assertEqual(report.provider_http_status, 429)
        self.assertIsNone(report.response_sha256)

    def test_truncated_content_is_preserved_without_retry(self):
        seeds, rules = _inputs()
        content = '{"bibles": ['
        def executor(*args):
            return 200, {"choices": [{"message": {"content": content}, "finish_reason": "length"}], "usage": {}}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "batch"
            report = OfficialDeepSeekScenarioBibleCompiler(executor).compile(
                seeds=seeds, rule_sets=rules, api_key="secret", output_root=output,
            )
            persisted = json.loads((output / "provider_response_content.json").read_text(encoding="utf-8"))
        self.assertEqual(report.first_failure, "empty_or_truncated_provider_content")
        self.assertEqual(persisted["response_sha256"], report.response_sha256)

    def test_static_validator_blocks_incomplete_world(self):
        seeds, rules = _inputs()
        payload = _bible(seeds[0], next(item for item in rules if item.domain == seeds[0].domain))
        payload["facts"] = payload["facts"][:5]
        def executor(*args):
            return 200, {"choices": [{"message": {"content": json.dumps({"bibles": [payload] * 4})}, "finish_reason": "stop"}], "usage": {}}
        with tempfile.TemporaryDirectory() as directory:
            report = OfficialDeepSeekScenarioBibleCompiler(executor).compile(
                seeds=seeds, rule_sets=rules, api_key="secret", output_root=Path(directory) / "batch",
            )
        self.assertEqual(report.decision, "blocked")


if __name__ == "__main__":
    unittest.main()
