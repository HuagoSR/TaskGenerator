from __future__ import annotations

import hashlib
from pathlib import Path


SNAPSHOT_ROOTS = (
    "src",
    "Test",
    "SkillRegistry",
    "deploy",
    "docs",
    "pyproject.toml",
    "AGENTS.md",
    "项目概要.md",
    "v2_semantic_skills_finance.json",
    "v2_semantic_skills_migrated.json",
)

FORBIDDEN_PARTS = {
    ".env",
    ".git",
    "__pycache__",
    "artifacts",
    "deepseek-key.txt",
    "result",
    "v2_outputs",
}


def iter_governed_snapshot_files(root: str | Path) -> list[Path]:
    base = Path(root).resolve()
    files: list[Path] = []
    for name in SNAPSHOT_ROOTS:
        path = base / name
        if not path.exists():
            continue
        if path.is_file():
            if _allowed(base, path):
                files.append(path)
            continue
        files.extend(
            item
            for item in path.rglob("*")
            if item.is_file() and _allowed(base, item)
        )
    return sorted(set(files), key=lambda item: item.relative_to(base).as_posix())


def governed_source_fingerprint(root: str | Path) -> str:
    base = Path(root).resolve()
    digest = hashlib.sha256()
    for path in iter_governed_snapshot_files(base):
        digest.update(path.relative_to(base).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _allowed(root: Path, path: Path) -> bool:
    return not any(part in FORBIDDEN_PARTS for part in path.relative_to(root).parts)
