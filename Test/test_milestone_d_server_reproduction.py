from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_end_to_end_pipeline import EndToEndPipeline, EndToEndRequest  # noqa: E402
from task_generator.v3_environment_equivalence import (  # noqa: E402
    EXPECTED_OFFLINE_FINGERPRINT,
    EXPECTED_OFFLINE_METRICS,
    EXPECTED_STAGE_ORDER,
    compare_environments,
)


class MilestoneDServerReproductionTests(unittest.TestCase):
    def test_deepseek_key_path_is_frozen_but_not_a_secret_value(self) -> None:
        request = EndToEndRequest(
            run_id="container",
            selected_stages=list(EXPECTED_STAGE_ORDER),
            profile="public-smoke-llm",
            source_mode="public_fixture",
            registry_mode="fresh_scratch",
            extractor_mode="llm",
            allow_external_source_upload=True,
            deepseek_key_path="/run/secrets/deepseek_api_key",
        )
        payload = request.model_dump(mode="json")
        self.assertEqual(payload["deepseek_key_path"], "/run/secrets/deepseek_api_key")
        self.assertNotIn("secret-value", json.dumps(payload))

    def test_runtime_summary_contains_only_non_secret_container_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = EndToEndPipeline(Path(tmp))
            summary = pipeline._runtime_summary(Path(tmp) / "runs")
            text = json.dumps(summary)
            self.assertIn("container", summary)
            self.assertNotIn("api_key", text.lower())
            self.assertNotIn("bearer", text.lower())

    def test_content_fingerprint_uses_legacy_cross_platform_deliverable_separator(self) -> None:
        source = (ROOT / "src" / "task_generator" / "v3_end_to_end_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('str(item).replace("/", "\\\\")', source)

    def test_compose_is_private_and_resource_bounded(self) -> None:
        text = (ROOT / "deploy" / "docker" / "compose.yaml").read_text(encoding="utf-8")
        self.assertNotIn("ports:", text)
        self.assertNotIn("privileged:", text)
        self.assertIn("network_mode: none", text)
        self.assertIn("mem_limit: 2560m", text)
        self.assertIn("cpus: 1.5", text)
        self.assertIn('pids_limit: 256', text)
        self.assertIn('cap_drop: ["ALL"]', text)

    def test_docker_context_ignore_excludes_secret_and_outputs(self) -> None:
        text = (ROOT / "deploy" / "docker" / ".dockerignore").read_text(encoding="utf-8")
        for required in ("**/.env", "**/deepseek-key.txt", "**/artifacts", "**/result"):
            self.assertIn(required, text)

    def test_equivalence_accepts_expected_cross_platform_difference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            remote = root / "remote"
            local.mkdir()
            remote.mkdir()
            stages = {stage: {"state": "completed"} for stage in EXPECTED_STAGE_ORDER}
            common = {
                "end_to_end_manifest_version": "v3.end_to_end_pipeline.2",
                "git_commit": "abc123",
                "request": {"profile": "public-smoke-offline"},
                "stages": stages,
                "input_fingerprints": {"fixture": "f00"},
            }
            (local / "end_to_end_run_manifest.json").write_text(
                json.dumps({**common, "run_id": "local", "runtime_summary": {"platform": "Windows"}}), encoding="utf-8"
            )
            (remote / "end_to_end_run_manifest.json").write_text(
                json.dumps({**common, "run_id": "remote", "runtime_summary": {"platform": "Linux", "container": {"image_id": "sha256:image"}}}), encoding="utf-8"
            )
            acceptance = {
                "metrics": EXPECTED_OFFLINE_METRICS,
                "content_fingerprint": EXPECTED_OFFLINE_FINGERPRINT,
                "external_effects": {
                    "web_collection": False,
                    "external_source_upload": False,
                    "llm_extraction": False,
                    "eval_preparation": True,
                    "external_eval": False,
                },
                "canonical_registry_before_sha256": "same",
                "canonical_registry_after_sha256": "same",
            }
            for directory in (local, remote):
                (directory / "acceptance_report.json").write_text(json.dumps(acceptance), encoding="utf-8")
            report = compare_environments(
                local / "end_to_end_run_manifest.json",
                remote / "end_to_end_run_manifest.json",
                expected_image_id="sha256:image",
            )
            self.assertEqual(report.decision, "equivalent")

    def test_equivalence_rejects_metric_drift_and_windows_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            remote = root / "remote"
            local.mkdir()
            remote.mkdir()
            manifest = {
                "end_to_end_manifest_version": "v3.end_to_end_pipeline.2",
                "git_commit": "abc",
                "request": {"profile": "public-smoke-offline"},
                "stages": {stage: {} for stage in EXPECTED_STAGE_ORDER},
                "input_fingerprints": {},
            }
            for directory in (local, remote):
                (directory / "end_to_end_run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            local_acceptance = {"metrics": EXPECTED_OFFLINE_METRICS, "content_fingerprint": EXPECTED_OFFLINE_FINGERPRINT, "external_effects": {}, "canonical_registry_before_sha256": "x", "canonical_registry_after_sha256": "x"}
            remote_acceptance = {**local_acceptance, "metrics": {**EXPECTED_OFFLINE_METRICS, "candidate_count": 3}, "bad_path": "E:\\private"}
            (local / "acceptance_report.json").write_text(json.dumps(local_acceptance), encoding="utf-8")
            (remote / "acceptance_report.json").write_text(json.dumps(remote_acceptance), encoding="utf-8")
            report = compare_environments(local / "end_to_end_run_manifest.json", remote / "end_to_end_run_manifest.json")
            self.assertEqual(report.decision, "not_equivalent")
            self.assertTrue(report.secret_or_windows_path_findings)


if __name__ == "__main__":
    unittest.main()
