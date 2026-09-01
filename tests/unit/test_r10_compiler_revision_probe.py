from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "Test" / "run_r10_compiler_revision.py"
SPEC = importlib.util.spec_from_file_location("r10_compiler_revision_probe", RUNNER_PATH)
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class R10CompilerRevisionProbeTests(unittest.TestCase):
    def test_accepts_content_when_read_only_dimensions_are_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "probe.xlsx"
            book = Workbook(write_only=True)
            sheet = book.create_sheet("Probe")
            sheet.append(["record", "value"])
            sheet.append(["A-01", 1])
            book.save(path)
            self.assertTrue(RUNNER._xlsx_has_visible_content(path))

    def test_rejects_a_workbook_without_cells(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "empty.xlsx"
            book = Workbook()
            book.save(path)
            self.assertFalse(RUNNER._xlsx_has_visible_content(path))

    def test_codex_execution_normalizes_a_relative_workspace(self):
        class Process:
            returncode = 0

            def communicate(self, _prompt, timeout):
                return "", ""

        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "relative" / "workspace"
            captured: list[Path] = []
            with (
                patch.object(RUNNER, "_codex_command", side_effect=lambda *, workspace: captured.append(workspace) or ["codex"]),
                patch.object(RUNNER, "local_codex_version", return_value="codex-cli 0.149.1"),
                patch.object(RUNNER.subprocess, "Popen", return_value=Process()),
            ):
                RUNNER._run_codex(workspace=workspace, prompt="public probe")
        self.assertEqual(captured, [workspace.resolve()])


if __name__ == "__main__":
    unittest.main()
