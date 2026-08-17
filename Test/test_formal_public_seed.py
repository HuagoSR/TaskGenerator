from __future__ import annotations

import unittest
from pathlib import Path

from src.task_generator.v3_formal_public_seed import FormalPublicSeedCompiler


class FormalPublicSeedTests(unittest.TestCase):
    def test_compiler_is_report_only_interface(self):
        compiler = FormalPublicSeedCompiler()
        self.assertTrue(callable(compiler.compile))
        self.assertFalse(
            hasattr(compiler, "apply_registry") or hasattr(compiler, "promote")
        )


if __name__ == "__main__":
    unittest.main()
