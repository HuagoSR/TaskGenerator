"""Lightweight discovery and safe, progressive loading for R10 professional Skills."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CATALOG_VERSION = "r10.professional_skill_catalog.1"
ENTRY_VERSION = "r10.professional_skill_catalog_entry.1"
Domain = Literal["audit_compliance", "procurement_operations"]
SkillStatus = Literal["draft", "curated"]


class ProfessionalSkillCatalogError(ValueError):
    """Raised when a catalog entry cannot safely resolve to a Skill package."""


class ProfessionalSkillCatalogEntryV1(BaseModel):
    """Thin metadata used to discover a factory-side professional Skill."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[ENTRY_VERSION]
    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    domain: Domain
    relative_path: str = Field(min_length=1)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: SkillStatus


class ProfessionalSkillCatalogV1(BaseModel):
    """Catalog metadata only; package prose remains unloaded until selection."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[CATALOG_VERSION]
    entries: list[ProfessionalSkillCatalogEntryV1] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_identifiers(self) -> "ProfessionalSkillCatalogV1":
        skill_ids = [entry.skill_id for entry in self.entries]
        paths = [entry.relative_path for entry in self.entries]
        if len(skill_ids) != len(set(skill_ids)):
            raise ValueError("professional Skill catalog contains duplicate skill_id")
        if len(paths) != len(set(paths)):
            raise ValueError("professional Skill catalog contains duplicate relative_path")
        return self


class LoadedProfessionalSkillV1(BaseModel):
    """Selected package content, deliberately separate from catalog discovery."""

    model_config = ConfigDict(extra="forbid")

    entry: ProfessionalSkillCatalogEntryV1
    skill_markdown: str = Field(min_length=1)
    reference_markdown: dict[str, str]


class ProfessionalSkillLoader:
    """Read catalog metadata first and package prose only after explicit selection."""

    def load_catalog(self, catalog_path: Path) -> ProfessionalSkillCatalogV1:
        try:
            raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProfessionalSkillCatalogError(
                f"cannot load professional Skill catalog: {catalog_path}"
            ) from exc
        return ProfessionalSkillCatalogV1.model_validate(raw)

    def search(
        self,
        catalog: ProfessionalSkillCatalogV1,
        *,
        query: str = "",
        domain: Domain | None = None,
        limit: int = 4,
    ) -> list[ProfessionalSkillCatalogEntryV1]:
        """Return at most four metadata matches without reading a Skill package."""
        if not 1 <= limit <= 4:
            raise ValueError("professional Skill search limit must be between 1 and 4")

        query_terms = set(_search_terms(query))
        matches: list[ProfessionalSkillCatalogEntryV1] = []
        for entry in catalog.entries:
            if domain is not None and entry.domain != domain:
                continue
            searchable = set(_search_terms(f"{entry.name} {entry.description}"))
            if query_terms and not query_terms.intersection(searchable):
                continue
            matches.append(entry)
        return matches[:limit]

    def load_skill(
        self,
        entry: ProfessionalSkillCatalogEntryV1,
        *,
        skills_root: Path,
    ) -> LoadedProfessionalSkillV1:
        """Resolve one selected package, validate its frontmatter, then read references."""
        package_path = _resolve_package_path(skills_root, entry.relative_path)
        skill_path = package_path / "SKILL.md"
        if not skill_path.is_file():
            raise ProfessionalSkillCatalogError(
                f"professional Skill package is missing SKILL.md: {entry.relative_path}"
            )

        try:
            skill_markdown = skill_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProfessionalSkillCatalogError(
                f"cannot read professional Skill package: {entry.relative_path}"
            ) from exc

        frontmatter = _parse_frontmatter(skill_markdown)
        if frontmatter.get("name") != entry.name:
            raise ProfessionalSkillCatalogError(
                f"professional Skill frontmatter name does not match catalog: {entry.relative_path}"
            )
        if frontmatter.get("description") != entry.description:
            raise ProfessionalSkillCatalogError(
                f"professional Skill frontmatter description does not match catalog: {entry.relative_path}"
            )

        references_path = package_path / "references"
        references: dict[str, str] = {}
        if references_path.exists():
            if not references_path.is_dir():
                raise ProfessionalSkillCatalogError(
                    f"professional Skill references path is not a directory: {entry.relative_path}"
                )
            for reference in sorted(references_path.rglob("*.md")):
                if not reference.is_file():
                    continue
                references[str(reference.relative_to(package_path)).replace("\\", "/")] = (
                    reference.read_text(encoding="utf-8")
                )

        return LoadedProfessionalSkillV1(
            entry=entry,
            skill_markdown=skill_markdown,
            reference_markdown=references,
        )


def _search_terms(value: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) >= 3]


def _resolve_package_path(skills_root: Path, relative_path: str) -> Path:
    candidate = PurePosixPath(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ProfessionalSkillCatalogError("professional Skill relative_path escapes the skills root")

    root = skills_root.resolve()
    package_path = (root / Path(*candidate.parts)).resolve()
    try:
        package_path.relative_to(root)
    except ValueError as exc:
        raise ProfessionalSkillCatalogError(
            "professional Skill relative_path escapes the skills root"
        ) from exc
    return package_path


def _parse_frontmatter(markdown: str) -> dict[str, str]:
    lines = markdown.splitlines()
    if not lines or lines[0] != "---":
        raise ProfessionalSkillCatalogError("professional Skill is missing YAML frontmatter")
    try:
        closing_index = lines.index("---", 1)
    except ValueError as exc:
        raise ProfessionalSkillCatalogError("professional Skill frontmatter is not closed") from exc

    values: dict[str, str] = {}
    for line in lines[1:closing_index]:
        key, separator, value = line.partition(":")
        if not separator:
            raise ProfessionalSkillCatalogError("professional Skill frontmatter is malformed")
        values[key.strip()] = value.strip().strip('"').strip("'")
    if not values.get("name") or not values.get("description"):
        raise ProfessionalSkillCatalogError("professional Skill frontmatter requires name and description")
    return values
