from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DocumentationGovernanceTests(unittest.TestCase):
    def test_active_document_set_exists(self) -> None:
        expected = [
            ROOT / "项目概要.md",
            ROOT / "AGENTS.md",
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "architecture" / "system_architecture.md",
            ROOT / "docs" / "architecture" / "global_interface_contracts.md",
            ROOT / "docs" / "architecture" / "production_mvp_definition.md",
            ROOT / "docs" / "archive" / "README.md",
        ]
        missing = [str(path.relative_to(ROOT)) for path in expected if not path.is_file()]
        self.assertEqual(missing, [])

    def test_overview_owns_current_phase_and_roadmap_state(self) -> None:
        overview = (ROOT / "项目概要.md").read_text(encoding="utf-8")
        required = [
            "24 / 24",
            "redesign_again",
            "do_not_promote_default_chain",
            "A. Phase 16 证据收口",
            "B. 文档和项目状态治理",
            "C. 端到端自动化与服务器部署",
            "D. 跨领域泛化验证",
            "下一主线是步骤 C",
        ]
        missing = [token for token in required if token not in overview]
        self.assertEqual(missing, [])

    def test_architecture_directory_contains_only_active_documents(self) -> None:
        architecture_dir = ROOT / "docs" / "architecture"
        actual = {path.name for path in architecture_dir.iterdir() if path.is_file()}
        expected = {
            "system_architecture.md",
            "global_interface_contracts.md",
            "production_mvp_definition.md",
        }
        self.assertEqual(actual, expected)

    def test_agents_is_compact(self) -> None:
        lines = (ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()
        self.assertLessEqual(len(lines), 300)

    def test_historical_runners_do_not_write_active_docs(self) -> None:
        forbidden_forward = "docs" + "/" + "handoffs"
        forbidden_parts = '"docs"' + " / " + '"handoffs"'
        offenders: list[str] = []
        for base in (ROOT / "src" / "task_generator", ROOT / "Test"):
            for path in base.rglob("*.py"):
                if path == Path(__file__).resolve():
                    continue
                text = path.read_text(encoding="utf-8")
                if forbidden_forward in text or forbidden_parts in text:
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])

    def test_active_markdown_links_resolve(self) -> None:
        active_docs = [
            ROOT / "项目概要.md",
            ROOT / "AGENTS.md",
            ROOT / "docs" / "README.md",
            *(ROOT / "docs" / "architecture").glob("*.md"),
        ]
        pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
        broken: list[str] = []
        for path in active_docs:
            for target in pattern.findall(path.read_text(encoding="utf-8")):
                clean = target.split("#", 1)[0].strip()
                if not clean or clean.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (path.parent / clean).resolve()
                if not resolved.exists():
                    broken.append(f"{path.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])

    def test_archive_contains_each_completed_phase(self) -> None:
        phases = ROOT / "docs" / "archive" / "phases"
        missing = [f"phase{number}" for number in range(11, 17) if not (phases / f"phase{number}").is_dir()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
