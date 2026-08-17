from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from task_generator.v3_huago_cone_eval import R9NativeSolverRunner, _read_env, _redact


class HuagoConeEvalTests(unittest.TestCase):
    def test_crlf_env_is_normalized(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "env"
            path.write_bytes(b"TUZI_API_KEY=secret-value\r\nTUZI_BASE_URL=https://example.test/v1\r\n")
            values = _read_env(path)
            self.assertEqual(values["TUZI_API_KEY"], "secret-value")
            self.assertEqual(values["TUZI_BASE_URL"], "https://example.test/v1")

    def test_secret_redaction(self):
        value = _redact("before secret-value after", ["secret-value"])
        self.assertEqual(value, "before [REDACTED] after")
        self.assertNotIn("secret-value", value)

    def test_public_probe_stages_task_and_delivery_directory(self):
        with tempfile.TemporaryDirectory() as root:
            runner = R9NativeSolverRunner(
                stack_id="deepseek-v4-pro@official_opencode",
                output_root=root,
            )
            captured = {}

            def fake_execute(**kwargs):
                captured.update(kwargs)
                workspace = kwargs["workspace"]
                self.assertTrue((workspace / "TASK.md").is_file())
                self.assertTrue((workspace / "deliverable_files").is_dir())
                raise RuntimeError("stop_after_staging")

            runner._execute = fake_execute
            with self.assertRaisesRegex(RuntimeError, "stop_after_staging"):
                runner.public_probe()
            self.assertIn("public_probe.xlsx", captured["expected"])


if __name__ == "__main__":
    unittest.main()
