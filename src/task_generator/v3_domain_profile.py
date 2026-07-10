from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field, model_validator


DEFAULT_DOMAIN_PROFILE_PATH = Path(__file__).resolve().parents[2] / "SkillRegistry" / "v3_domain_profiles.experimental.json"


class DomainReferenceSchema(BaseModel):
    source_file_name: str
    source_sheet_name: str
    source_columns: List[str]
    control_file_name: str
    control_sheet_name: str
    control_columns: List[str]
    policy_file_name: str = "policy_reference.docx"


class DomainMotifHint(BaseModel):
    template_family: str
    deliverable_name: str
    scenario_goal: str
    deliverable_requirements: List[str] = Field(default_factory=list)


class DomainProfile(BaseModel):
    profile_id: str
    profile_version: str
    domain_scope: str
    domain_tags: List[str]
    target_domains: List[str]
    allowed_motifs: List[str]
    allowed_input_file_types: List[str]
    allowed_output_file_types: List[str]
    occupation: str
    actor_role: str
    business_context: str
    resource_aliases: Dict[str, str] = Field(default_factory=dict)
    typed_resources: List[str] = Field(default_factory=list)
    forbidden_terms: List[str] = Field(default_factory=list)
    reference_schema: DomainReferenceSchema
    motif_hints: Dict[str, DomainMotifHint] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_contract(self) -> "DomainProfile":
        if not self.domain_tags or not self.target_domains:
            raise ValueError("domain profile requires domain_tags and target_domains")
        missing = set(self.allowed_motifs) - set(self.motif_hints)
        if missing:
            raise ValueError(f"domain profile is missing motif hints: {sorted(missing)}")
        if not set(self.allowed_output_file_types) <= {"xlsx", "docx"} and self.profile_id == "warehouse_inventory":
            raise ValueError("warehouse_inventory outputs must remain xlsx/docx only")
        return self


class DomainProfileRegistry(BaseModel):
    domain_profile_registry_version: str
    profiles: List[DomainProfile]


def load_domain_profile(
    profile_id: str = "finance_audit",
    path: str | Path = DEFAULT_DOMAIN_PROFILE_PATH,
) -> DomainProfile:
    profile_path = Path(path)
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    registry = DomainProfileRegistry.model_validate(payload)
    for profile in registry.profiles:
        if profile.profile_id == profile_id:
            return profile
    raise ValueError(f"Unknown domain profile: {profile_id}")


def domain_profile_sha256(path: str | Path = DEFAULT_DOMAIN_PROFILE_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
