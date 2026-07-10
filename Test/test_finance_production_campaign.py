import argparse
import json
import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from Test.run_v3_finance_production_campaign import (  # noqa: E402
    build_command,
    load_json,
    occurrence_offsets,
    topic_payload,
    wave_motifs,
)
from Test.run_v3_server_reproduction import _env_value, production_container_name  # noqa: E402
from task_generator.v3_direct_source_collector import DirectWebSourceCollector  # noqa: E402
from task_generator.v3_skill_extractor import LLMSkillExtractor, ProviderConfig  # noqa: E402


class FinanceProductionCampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec_path = ROOT / "SkillRegistry" / "v3_finance_production_campaign.experimental.json"
        self.spec = load_json(self.spec_path)

    def test_campaign_contract_totals_and_excludes_phase16_motif(self) -> None:
        motifs = [motif for wave in range(1, 5) for motif in wave_motifs(self.spec, wave)]
        self.assertEqual(60, len(motifs))
        self.assertEqual(20, motifs.count("fan_in_reconciliation"))
        self.assertEqual(20, motifs.count("cross_check_validation"))
        self.assertEqual(20, motifs.count("policy_application"))
        self.assertNotIn("evidence_to_deliverable", motifs)

    def test_topics_are_split_five_and_five_with_two_queries(self) -> None:
        for wave in (1, 2):
            topics, queries = topic_payload(self.spec, wave)
            self.assertEqual(5, len(topics))
            self.assertTrue(all(len(queries[topic]) == 2 for topic in topics))
        self.assertEqual(([], {}), topic_payload(self.spec, 3))

    def test_offsets_continue_across_waves(self) -> None:
        self.assertEqual(
            {"fan_in_reconciliation": 2, "cross_check_validation": 2, "policy_application": 1},
            occurrence_offsets(self.spec, 2),
        )
        self.assertEqual(20, sum(occurrence_offsets(self.spec, 3).values()))

    def test_wave_command_stops_before_eval_and_uses_minimal_secret_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            args = argparse.Namespace(
                wave=1,
                pipeline_action="run",
                rw_task_root="/opt/rw-task",
                timeout_seconds=7200,
                env_path="/run/secrets/provider_env",
                deepseek_key_path="/run/secrets/deepseek_api_key",
            )
            command = build_command(args, self.spec, Path(temporary))
            joined = " ".join(command)
            self.assertIn("--stage production_review", joined)
            self.assertNotIn("rw_task_eval", joined)
            self.assertNotIn("--allow-external-eval", joined)
            self.assertIn("bounded_production", joined)

    def test_bounded_production_prompt_is_compact_and_explicit(self) -> None:
        config = ProviderConfig(provider_name="test", api_key="x", base_url="https://example.com", model="model", output_profile="bounded_production")
        extractor = LLMSkillExtractor(config)
        prompt = extractor._build_prompt(  # pylint: disable=protected-access
            type("Package", (), {"normalized_sources": [], "instructions": "", "constraints": []})(),
            6,
        )
        self.assertIn("Bounded production output budget", prompt)
        self.assertIn("no more than 6 candidates", prompt)

    def test_private_and_local_urls_are_rejected(self) -> None:
        collector = DirectWebSourceCollector(api_key="x")
        with self.assertRaises(RuntimeError):
            collector._validate_public_url("http://127.0.0.1/private")  # pylint: disable=protected-access
        with self.assertRaises(RuntimeError):
            collector._validate_public_url("http://localhost/private")  # pylint: disable=protected-access

    def test_minimal_env_reader_selects_only_requested_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("SERPER_API_KEY=search-only\nOPENAI_API_KEY=must-not-copy\n", encoding="utf-8")
            self.assertEqual("search-only", _env_value(path, "SERPER_API_KEY"))

    def test_compose_mounts_provider_secret_only_for_online_service(self) -> None:
        compose = (ROOT / "deploy" / "docker" / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn("TASKGEN_PROVIDER_ENV_FILE", compose)
        self.assertIn("/run/secrets/provider_env:ro", compose)
        self.assertNotIn("ports:", compose)
        self.assertEqual("taskgenerator-finance_audit_production_01-wave-01", production_container_name("finance_audit_production_01", 1))


if __name__ == "__main__":
    unittest.main()
