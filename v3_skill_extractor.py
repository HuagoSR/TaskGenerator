import hashlib
from dataclasses import dataclass
from typing import Iterable, List

from v3_source_schema import (
    ExtractedSkillCandidate,
    NormalizedSource,
    SemanticContract,
    SkillEvidence,
    SkillExtractionPromptPackage,
    SourceBlock,
)


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class SkillPattern:
    name: str
    keywords: List[str]
    capability_tags: List[str]
    difficulty_tags: List[str]
    requires_semantics: List[str]
    provides_semantics: List[str]
    business_meaning: str
    hidden_difficulty: str
    common_failure_modes: List[str]
    common_deliverables: List[str]
    assembly_hints: List[str]


SKILL_PATTERNS = [
    SkillPattern(
        name="Extract Evidence-Backed Semantic Skill",
        keywords=["source", "evidence", "extract", "skill", "semantic"],
        capability_tags=["skill_extraction", "evidence_grounding"],
        difficulty_tags=["semantic_abstraction", "source_grounding"],
        requires_semantics=["Source:NaturalLanguageMaterial", "Source:EvidenceSpan"],
        provides_semantics=["Skill:SemanticCapability", "Skill:EvidenceReference"],
        business_meaning="Identify reusable task capabilities from source material while preserving evidence references.",
        hidden_difficulty="The extractor must avoid copying one-off task details as if they were reusable skills.",
        common_failure_modes=[
            "overfits a single example into a narrow skill",
            "drops source evidence needed for later review",
            "mixes task assembly details into skill extraction",
        ],
        common_deliverables=["skill registry entry", "skill extraction report"],
        assembly_hints=[
            "Keep extracted skills execution-agnostic.",
            "Attach block-level evidence spans to every candidate skill.",
        ],
    ),
    SkillPattern(
        name="Assemble Skills Into Real-World Task Blueprint",
        keywords=["taskblueprint", "assemble", "scenario", "deliverable", "task"],
        capability_tags=["task_assembly", "scenario_construction"],
        difficulty_tags=["multi_skill_composition", "business_realism"],
        requires_semantics=["Skill:SemanticCapability", "Task:DomainConstraint"],
        provides_semantics=["Task:Blueprint", "Task:CandidatePrompt"],
        business_meaning="Compose reusable skills into a concrete real-world task with a plausible role, evidence package, and deliverable.",
        hidden_difficulty="The assembler must create realistic task dependencies without leaking hidden traps.",
        common_failure_modes=[
            "combines unrelated skills",
            "creates a prompt that reveals the intended trap",
            "creates a scenario without realistic evidence files",
        ],
        common_deliverables=["task blueprint", "candidate prompt"],
        assembly_hints=[
            "Prefer skill combinations with clear dependency order.",
            "Separate candidate-visible instructions from teacher-only hints.",
        ],
    ),
    SkillPattern(
        name="Generate Verifiable Reference Files",
        keywords=["reference file", "spreadsheet", "workbook", "data", "provenance"],
        capability_tags=["reference_generation", "data_provenance"],
        difficulty_tags=["structured_generation", "traceability"],
        requires_semantics=["Task:Blueprint", "Data:SourceSchema"],
        provides_semantics=["Data:ReferenceFile", "Data:ProvenanceMap"],
        business_meaning="Create realistic evidence files whose values can be traced into teacher answers and rubric anchors.",
        hidden_difficulty="Generated data must look realistic without losing deterministic supervision.",
        common_failure_modes=[
            "generates plausible but unverifiable numbers",
            "loses provenance from source values to grading targets",
            "creates files that do not match the blueprint",
        ],
        common_deliverables=["reference spreadsheet", "source manifest", "provenance map"],
        assembly_hints=[
            "Use code-led numeric generation when exact grading is required.",
            "Use LLMs mainly for realistic wording and context variation.",
        ],
    ),
    SkillPattern(
        name="Produce Teacher-Mode GoldenRun",
        keywords=["goldenrun", "teacher", "canonical", "rubric", "grading"],
        capability_tags=["teacher_solution", "rubric_grounding"],
        difficulty_tags=["result_supervision", "intermediate_state_tracking"],
        requires_semantics=["Task:Blueprint", "Data:ReferenceFile", "Teacher:HiddenHint"],
        provides_semantics=["Answer:CanonicalSolution", "Rubric:GradingAnchor"],
        business_meaning="Solve the task in teacher mode and emit canonical intermediate states, final answers, and grading anchors.",
        hidden_difficulty="The teacher can use extra information, but exact grading targets must remain auditable.",
        common_failure_modes=[
            "teacher answer is not reproducible",
            "rubric checks cannot be traced to evidence",
            "teacher-only assumptions leak into candidate-facing grading unfairly",
        ],
        common_deliverables=["golden run package", "grading anchors", "teacher deliverable"],
        assembly_hints=[
            "Record intermediate states, not only final values.",
            "Mark teacher-only supervision separately from candidate-visible evidence.",
        ],
    ),
    SkillPattern(
        name="Filter Generated Tasks Through Quality Funnel",
        keywords=["quality", "funnel", "validation", "accepted", "rejected", "model-separation"],
        capability_tags=["quality_control", "batch_filtering"],
        difficulty_tags=["pipeline_validation", "model_separation"],
        requires_semantics=["Task:GeneratedSample", "Rubric:GradingAnchor"],
        provides_semantics=["Quality:RouteDecision", "Quality:RejectionReason"],
        business_meaning="Route generated tasks through deterministic checks and selective model evaluation before retaining them.",
        hidden_difficulty="The pipeline must distinguish broken samples from valid but low-value samples.",
        common_failure_modes=[
            "runs expensive model evaluation on structurally broken samples",
            "keeps tasks that are valid but fail to separate models",
            "does not record rejection reasons for generator improvement",
        ],
        common_deliverables=["quality report", "batch funnel report", "model separation report"],
        assembly_hints=[
            "Run cheap deterministic gates before expensive model evaluation.",
            "Store rejection reasons as feedback for future generator revisions.",
        ],
    ),
    SkillPattern(
        name="Resolve Incomplete Or Irregular Evidence",
        keywords=["missing", "incomplete", "irregular", "resolve", "trap"],
        capability_tags=["robustness", "evidence_resolution"],
        difficulty_tags=["incomplete_information", "hidden_trap"],
        requires_semantics=["Data:IncompleteEvidence", "Task:BusinessRule"],
        provides_semantics=["Data:ResolvedEvidence", "Reasoning:ResolutionTrace"],
        business_meaning="Detect incomplete or irregular evidence and resolve it through available business rules or support materials.",
        hidden_difficulty="The candidate must handle irregularities without being explicitly told the trap location.",
        common_failure_modes=[
            "silently ignores missing values",
            "uses an unsupported assumption",
            "fails to document the resolution path",
        ],
        common_deliverables=["resolution log", "audit note", "corrected calculation"],
        assembly_hints=[
            "Provide enough visible evidence to make exact grading fair.",
            "Use hidden traps only when the resolution path is auditable.",
        ],
    ),
]


class MockSkillExtractor:
    """Deterministic first-pass extractor for local pipeline testing."""

    def extract(self, package: SkillExtractionPromptPackage, max_candidates: int = 8) -> List[ExtractedSkillCandidate]:
        candidates = []
        for pattern in SKILL_PATTERNS:
            evidence_blocks = self._find_evidence_blocks(package.normalized_sources, pattern)
            if not evidence_blocks:
                continue
            candidates.append(self._build_candidate(pattern, package, evidence_blocks))
            if len(candidates) >= max_candidates:
                break
        return candidates

    def _find_evidence_blocks(
        self,
        sources: Iterable[NormalizedSource],
        pattern: SkillPattern,
    ) -> List[tuple[NormalizedSource, SourceBlock]]:
        matches: List[tuple[NormalizedSource, SourceBlock]] = []
        keywords = [keyword.lower() for keyword in pattern.keywords]
        for source in sources:
            for block in source.blocks:
                lower = block.text.lower()
                if any(keyword in lower for keyword in keywords):
                    matches.append((source, block))
                if len(matches) >= 4:
                    return matches
        return matches

    def _build_candidate(
        self,
        pattern: SkillPattern,
        package: SkillExtractionPromptPackage,
        evidence_blocks: List[tuple[NormalizedSource, SourceBlock]],
    ) -> ExtractedSkillCandidate:
        source_ids = sorted({source.source_id for source, _ in evidence_blocks})
        domain_tags = sorted({tag for source, _ in evidence_blocks for tag in source.domain_tags})
        evidence_id = stable_id(
            "evidence",
            pattern.name + "::" + "::".join(block.block_id for _, block in evidence_blocks),
        )
        evidence = SkillEvidence(
            evidence_id=evidence_id,
            source_id=evidence_blocks[0][0].source_id,
            normalized_source_id=evidence_blocks[0][0].normalized_source_id,
            block_ids=[block.block_id for _, block in evidence_blocks],
            evidence_summary=f"Matched source blocks for reusable capability: {pattern.name}.",
            supporting_spans=[block.source_span for _, block in evidence_blocks],
        )
        candidate_id = stable_id("skill_candidate", package.request_id + "::" + pattern.name)
        return ExtractedSkillCandidate(
            candidate_id=candidate_id,
            source_ids=source_ids,
            proposed_name=pattern.name,
            domain_tags=domain_tags,
            capability_tags=pattern.capability_tags,
            difficulty_tags=pattern.difficulty_tags,
            input_contract=SemanticContract(requires_semantics=pattern.requires_semantics),
            output_contract=SemanticContract(provides_semantics=pattern.provides_semantics),
            business_meaning=pattern.business_meaning,
            hidden_difficulty=pattern.hidden_difficulty,
            common_failure_modes=pattern.common_failure_modes,
            common_deliverables=pattern.common_deliverables,
            assembly_hints=pattern.assembly_hints,
            evidence=[evidence],
            extractor_model="mock_rule_based_v0",
            extraction_trace=[
                "Generated by deterministic keyword matching.",
                "Use this output for pipeline testing, not as final research-quality extraction.",
            ],
        )

