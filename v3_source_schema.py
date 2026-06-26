import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


SourceType = Literal[
    "web_page",
    "pdf",
    "doc",
    "spreadsheet",
    "benchmark_task",
    "text_note",
    "unknown",
]
SourceBlockType = Literal[
    "paragraph",
    "table",
    "task_prompt",
    "rubric",
    "example",
    "formula",
    "domain_term",
    "metadata",
]
ExtractionStatus = Literal["candidate", "accepted", "rejected", "merged"]


class SourceArtifact(BaseModel):
    artifact_id: str
    artifact_type: SourceType = "unknown"
    path: str
    description: str = ""


class RawSource(BaseModel):
    source_id: str
    source_type: SourceType = "unknown"
    domain_tags: List[str] = Field(default_factory=list)
    url_or_path: str
    retrieved_at: str
    title: str
    raw_text_path: Optional[str] = None
    raw_file_paths: List[str] = Field(default_factory=list)
    collector_model: Optional[str] = None
    collection_trace: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SourceSpan(BaseModel):
    source_id: str
    block_id: Optional[str] = None
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    quote: str = ""
    note: str = ""


class SourceBlock(BaseModel):
    block_id: str
    block_type: SourceBlockType
    text: str
    source_span: SourceSpan
    semantic_tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NormalizedSource(BaseModel):
    normalized_source_id: str
    source_id: str
    title: str
    domain_tags: List[str] = Field(default_factory=list)
    blocks: List[SourceBlock] = Field(default_factory=list)
    domain_terms: List[str] = Field(default_factory=list)
    detected_artifacts: List[SourceArtifact] = Field(default_factory=list)
    candidate_task_patterns: List[str] = Field(default_factory=list)
    normalizer_version: str = "v3.0"


class SkillEvidence(BaseModel):
    evidence_id: str
    source_id: str
    normalized_source_id: Optional[str] = None
    block_ids: List[str] = Field(default_factory=list)
    evidence_summary: str
    supporting_spans: List[SourceSpan] = Field(default_factory=list)


class SemanticContract(BaseModel):
    requires_semantics: List[str] = Field(default_factory=list)
    optional_semantics: List[str] = Field(default_factory=list)
    provides_semantics: List[str] = Field(default_factory=list)


class ExtractedSkillCandidate(BaseModel):
    candidate_id: str
    source_ids: List[str] = Field(default_factory=list)
    proposed_name: str
    domain_tags: List[str] = Field(default_factory=list)
    capability_tags: List[str] = Field(default_factory=list)
    difficulty_tags: List[str] = Field(default_factory=list)
    input_contract: SemanticContract = Field(default_factory=SemanticContract)
    output_contract: SemanticContract = Field(default_factory=SemanticContract)
    business_meaning: str
    hidden_difficulty: str
    common_failure_modes: List[str] = Field(default_factory=list)
    common_deliverables: List[str] = Field(default_factory=list)
    assembly_hints: List[str] = Field(default_factory=list)
    evidence: List[SkillEvidence] = Field(default_factory=list)
    extraction_status: ExtractionStatus = "candidate"
    extractor_model: Optional[str] = None
    extraction_trace: List[str] = Field(default_factory=list)


class SkillRegistryStats(BaseModel):
    usage_count: int = 0
    accepted_task_count: int = 0
    rejected_task_count: int = 0
    model_separation_stats: Dict[str, Any] = Field(default_factory=dict)


class SkillRegistryEntry(BaseModel):
    skill_id: str
    canonical_name: str
    version: str = "3.0"
    domain_tags: List[str] = Field(default_factory=list)
    capability_tags: List[str] = Field(default_factory=list)
    difficulty_tags: List[str] = Field(default_factory=list)
    input_contract: SemanticContract = Field(default_factory=SemanticContract)
    output_contract: SemanticContract = Field(default_factory=SemanticContract)
    business_meaning: str
    hidden_difficulty: str
    failure_modes: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    assembly_hints: List[str] = Field(default_factory=list)
    stats: SkillRegistryStats = Field(default_factory=SkillRegistryStats)
    source_candidate_ids: List[str] = Field(default_factory=list)


class SkillExtractionPromptPackage(BaseModel):
    request_id: str
    normalized_sources: List[NormalizedSource] = Field(default_factory=list)
    instructions: str
    expected_schema: str = "ExtractedSkillCandidate[]"
    constraints: List[str] = Field(default_factory=list)


def dump_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def dump_json_file(model: BaseModel, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump_json(model))


def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_raw_source(path: str) -> RawSource:
    return RawSource.model_validate(load_json_file(path))


def load_normalized_source(path: str) -> NormalizedSource:
    return NormalizedSource.model_validate(load_json_file(path))


def load_skill_candidates(path: str) -> List[ExtractedSkillCandidate]:
    payload = load_json_file(path)
    if isinstance(payload, dict) and "candidates" in payload:
        payload = payload["candidates"]
    return [ExtractedSkillCandidate.model_validate(item) for item in payload]

