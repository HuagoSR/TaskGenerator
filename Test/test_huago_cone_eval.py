from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from task_generator.v3_huago_cone_eval import _read_env, _redact


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


if __name__ == "__main__":
    unittest.main()
