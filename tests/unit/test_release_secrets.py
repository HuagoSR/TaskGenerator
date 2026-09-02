from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from task_generator.cli import release


class ReleaseSecretTests(unittest.TestCase):
    def test_secret_staging_uses_lf_on_windows_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider_env = root / "provider.env"
            deepseek_key = root / "deepseek-key.txt"
            provider_env.write_bytes(
                b"OPENAI_API_KEY=tuzi-token\r\nOPENAI_BASE_URL=https://example.test/v1\r\nSERPER_API_KEY=serper-token\r\n"
            )
            deepseek_key.write_bytes(b"deepseek-token\r\n")
            staged: dict[str, bytes] = {}

            def fake_run(command, **_kwargs):
                local = Path(command[1])
                staged[local.name] = local.read_bytes()

            with patch.object(release, "ssh") as ssh, patch.object(release, "run", side_effect=fake_run):
                ssh.return_value.stdout = "/remote\n"
                release.install_secrets(host="fixture", provider_env=provider_env, deepseek_key=deepseek_key)

        self.assertEqual(staged["eval_tuzi.env"], b"TUZI_API_KEY=tuzi-token\nTUZI_BASE_URL=https://example.test/v1\n")
        self.assertTrue(all(b"\r\n" not in content for content in staged.values()))

