import json
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from v3_source_schema import (
    ExtractedSkillCandidate,
    NormalizedSource,
    SemanticContract,
    SemanticResource,
    SkillEvidence,
    SkillExtractionPromptPackage,
    SkillMotifHint,
    SkillTraceEdge,
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


class BaseSkillExtractor:
    last_trace_edges: List[SkillTraceEdge] = []
    last_motif_hints: List[SkillMotifHint] = []

    def extract(self, package: SkillExtractionPromptPackage, max_candidates: int = 8) -> List[ExtractedSkillCandidate]:
        raise NotImplementedError


class MockSkillExtractor(BaseSkillExtractor):
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
        self.last_trace_edges = self._build_trace_edges(candidates)
        self.last_motif_hints = self._build_motif_hints(candidates)
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
            input_contract=SemanticContract(
                requires_semantics=pattern.requires_semantics,
                required_resources=[
                    self._semantic_resource(item, "required", evidence_id, domain_tags)
                    for item in pattern.requires_semantics
                ],
            ),
            output_contract=SemanticContract(
                provides_semantics=pattern.provides_semantics,
                provided_resources=[
                    self._semantic_resource(item, "provided", evidence_id, domain_tags)
                    for item in pattern.provides_semantics
                ],
            ),
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

    def _semantic_resource(
        self,
        semantic_name: str,
        role: str,
        evidence_id: str,
        domain_tags: List[str],
    ) -> SemanticResource:
        if ":" in semantic_name:
            resource_type, subtype = semantic_name.split(":", 1)
        else:
            resource_type, subtype = semantic_name, ""
        return SemanticResource(
            resource_type=resource_type,
            subtype=subtype,
            attributes={"role": role},
            domain=domain_tags[0] if domain_tags else "",
            evidence_refs=[evidence_id],
        )

    def _build_trace_edges(self, candidates: List[ExtractedSkillCandidate]) -> List[SkillTraceEdge]:
        edges = []
        for left, right in zip(candidates, candidates[1:]):
            edge_id_blocks = sorted(
                {
                    block_id
                    for candidate in (left, right)
                    for evidence in candidate.evidence
                    for block_id in evidence.block_ids
                }
            )
            edges.append(
                SkillTraceEdge(
                    from_candidate_id=left.candidate_id,
                    to_candidate_id=right.candidate_id,
                    relation_type="local_order",
                    evidence_block_ids=edge_id_blocks,
                    reason_codes=["mock_local_candidate_order"],
                    weight_hint=0.5,
                )
            )
        return edges

    def _build_motif_hints(self, candidates: List[ExtractedSkillCandidate]) -> List[SkillMotifHint]:
        if len(candidates) < 2:
            return []
        names = " ".join(candidate.proposed_name.lower() for candidate in candidates)
        motif_type = "evidence_to_deliverable"
        if "reconcile" in names or "reference" in names:
            motif_type = "fan_in_reconciliation"
        elif "quality" in names or "validation" in names:
            motif_type = "cross_check_validation"
        return [
            SkillMotifHint(
                motif_type=motif_type,
                candidate_ids=[candidate.candidate_id for candidate in candidates[:4]],
                evidence_block_ids=sorted(
                    {
                        block_id
                        for candidate in candidates[:4]
                        for evidence in candidate.evidence
                        for block_id in evidence.block_ids
                    }
                ),
                confidence=0.35,
                reason_codes=["mock_batch_motif_hint"],
                summary="Deterministic mock motif hint based on extracted candidate order.",
            )
        ]


@dataclass
class ProviderConfig:
    provider_name: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 180
    temperature: float = 0.2
    max_tokens: int = 6000


@dataclass
class ProviderAttempt:
    provider_name: str
    model: str
    success: bool
    candidate_count: int = 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    def to_report(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "provider_name": self.provider_name,
            "model": self.model,
            "success": self.success,
            "candidate_count": self.candidate_count,
        }
        if self.error_type:
            payload["error_type"] = self.error_type
        if self.error_message:
            payload["error_message"] = self.error_message[:1000]
        return payload


class SkillExtractionError(RuntimeError):
    pass


class LLMSkillExtractor(BaseSkillExtractor):
    def __init__(self, config: ProviderConfig, prompt_block_limit: int = 80, prompt_char_limit: int = 24000):
        self.config = config
        self.prompt_block_limit = prompt_block_limit
        self.prompt_char_limit = prompt_char_limit
        self.last_trace_edges: List[SkillTraceEdge] = []
        self.last_motif_hints: List[SkillMotifHint] = []

    def extract(self, package: SkillExtractionPromptPackage, max_candidates: int = 8) -> List[ExtractedSkillCandidate]:
        response_text = self._call_model(package, max_candidates)
        payload = self._parse_json_object(response_text)
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list):
            raise SkillExtractionError("LLM response JSON must contain a top-level candidates array.")

        valid_source_ids, valid_block_ids = self._valid_evidence_ids(package)
        candidates = []
        for raw_candidate in raw_candidates[:max_candidates]:
            if not isinstance(raw_candidate, dict):
                raise SkillExtractionError("Each candidate must be a JSON object.")
            candidate = ExtractedSkillCandidate.model_validate(raw_candidate)
            self._validate_evidence(candidate, valid_source_ids, valid_block_ids)
            candidates.append(candidate)
        if not candidates:
            raise SkillExtractionError("LLM returned zero valid candidates.")
        self.last_trace_edges = self._parse_trace_edges(payload, candidates, valid_block_ids)
        self.last_motif_hints = self._parse_motif_hints(payload, candidates, valid_block_ids)
        return candidates

    def _parse_trace_edges(
        self,
        payload: Dict[str, Any],
        candidates: List[ExtractedSkillCandidate],
        valid_block_ids: set[tuple[str, str]],
    ) -> List[SkillTraceEdge]:
        raw_edges = payload.get("trace_edges", [])
        if raw_edges is None:
            raw_edges = []
        if not isinstance(raw_edges, list):
            raise SkillExtractionError("trace_edges must be an array when provided.")
        valid_candidate_ids = {candidate.candidate_id for candidate in candidates}
        valid_block_names = {block_id for _, block_id in valid_block_ids}
        edges = []
        for raw_edge in raw_edges:
            edge = SkillTraceEdge.model_validate(raw_edge)
            if edge.from_candidate_id not in valid_candidate_ids or edge.to_candidate_id not in valid_candidate_ids:
                raise SkillExtractionError("trace_edges must reference candidate IDs returned in candidates.")
            unknown_blocks = [block_id for block_id in edge.evidence_block_ids if block_id not in valid_block_names]
            if unknown_blocks:
                raise SkillExtractionError(f"trace_edges reference unknown block IDs: {unknown_blocks[:5]}")
            edges.append(edge)
        return edges

    def _parse_motif_hints(
        self,
        payload: Dict[str, Any],
        candidates: List[ExtractedSkillCandidate],
        valid_block_ids: set[tuple[str, str]],
    ) -> List[SkillMotifHint]:
        raw_hints = payload.get("motif_hints", [])
        if raw_hints is None:
            raw_hints = []
        if not isinstance(raw_hints, list):
            raise SkillExtractionError("motif_hints must be an array when provided.")
        valid_candidate_ids = {candidate.candidate_id for candidate in candidates}
        valid_block_names = {block_id for _, block_id in valid_block_ids}
        hints = []
        for raw_hint in raw_hints:
            hint = SkillMotifHint.model_validate(raw_hint)
            unknown_candidates = [candidate_id for candidate_id in hint.candidate_ids if candidate_id not in valid_candidate_ids]
            if unknown_candidates:
                raise SkillExtractionError(f"motif_hints reference unknown candidate IDs: {unknown_candidates[:5]}")
            unknown_blocks = [block_id for block_id in hint.evidence_block_ids if block_id not in valid_block_names]
            if unknown_blocks:
                raise SkillExtractionError(f"motif_hints reference unknown block IDs: {unknown_blocks[:5]}")
            hints.append(hint)
        return hints

    def _call_model(self, package: SkillExtractionPromptPackage, max_candidates: int) -> str:
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - environment-specific
            raise SkillExtractionError(f"OpenAI SDK is unavailable: {exc}") from exc

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout_seconds,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You extract reusable semantic skills for real-world-task dataset generation. "
                    "You must output valid JSON only."
                ),
            },
            {
                "role": "user",
                "content": self._build_prompt(package, max_candidates),
            },
        ]
        response = client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise SkillExtractionError("LLM returned empty content.")
        return content

    def _build_prompt(self, package: SkillExtractionPromptPackage, max_candidates: int) -> str:
        compact_sources = self._compact_sources(package)
        resource_hint = {
            "resource_type": "MonetaryAmount",
            "subtype": "NetProfit",
            "attributes": {"currency": "unknown_or_explicit", "period": "required", "entity": "required"},
            "domain": "finance",
            "evidence_refs": ["evidence_short_unique_id"],
        }
        schema_hint = {
            "candidates": [
                {
                    "candidate_id": "skill_candidate_short_unique_id",
                    "source_ids": ["source_id"],
                    "proposed_name": "Reusable Semantic Skill Name",
                    "domain_tags": ["finance"],
                    "capability_tags": ["capability_name"],
                    "difficulty_tags": ["difficulty_name"],
                    "input_contract": {
                        "requires_semantics": ["Domain:InputSemantic"],
                        "optional_semantics": [],
                        "provides_semantics": [],
                        "required_resources": [resource_hint],
                        "optional_resources": [],
                        "provided_resources": [],
                    },
                    "output_contract": {
                        "requires_semantics": [],
                        "optional_semantics": [],
                        "provides_semantics": ["Domain:OutputSemantic"],
                        "required_resources": [],
                        "optional_resources": [],
                        "provided_resources": [resource_hint],
                    },
                    "business_meaning": "What reusable business capability this skill represents.",
                    "hidden_difficulty": "What makes the task non-trivial.",
                    "common_failure_modes": ["failure mode"],
                    "common_deliverables": ["deliverable type"],
                    "assembly_hints": ["task assembly hint"],
                    "evidence": [
                        {
                            "evidence_id": "evidence_short_unique_id",
                            "source_id": "source_id",
                            "normalized_source_id": "normalized_source_id",
                            "block_ids": ["block_0001"],
                            "evidence_summary": "Why this evidence supports the skill.",
                            "supporting_spans": [
                                {
                                    "source_id": "source_id",
                                    "block_id": "block_0001",
                                    "start_char": 0,
                                    "end_char": 10,
                                    "quote": "short quote from provided source",
                                    "note": "",
                                }
                            ],
                        }
                    ],
                    "extraction_status": "candidate",
                    "extractor_model": self.config.model,
                    "extraction_trace": ["Extracted by LLM from evidence-backed source blocks."],
                }
            ],
            "trace_edges": [
                {
                    "from_candidate_id": "skill_candidate_a",
                    "to_candidate_id": "skill_candidate_b",
                    "relation_type": "local_order",
                    "evidence_block_ids": ["block_0001", "block_0002"],
                    "reason_codes": ["same_source_order", "resource_compatible"],
                    "weight_hint": 0.8,
                }
            ],
            "motif_hints": [
                {
                    "motif_type": "fan_in_reconciliation",
                    "candidate_ids": ["skill_candidate_a", "skill_candidate_b"],
                    "evidence_block_ids": ["block_0001"],
                    "confidence": 0.7,
                    "reason_codes": ["source_implies_reconciliation_workflow"],
                    "summary": "Short explanation of the task graph pattern observed in the source.",
                }
            ],
        }
        return (
            "Return JSON only. The top-level JSON object must be {\"candidates\": [...], \"trace_edges\": [...], \"motif_hints\": [...]}.\n"
            "trace_edges and motif_hints are allowed to be empty only when there is exactly one candidate or no source-supported local relationship.\n"
            "If you return two or more candidates from the same source or block, strongly prefer at least one trace_edge unless the candidates are truly unrelated.\n"
            f"Return at most {max_candidates} ExtractedSkillCandidate objects.\n\n"
            "Project context:\n"
            "- This project previously used a multi-agent skill extraction pipeline with semantic ports, business intents, data-profile-like context, and evaluation dimensions.\n"
            "- Preserve that useful abstraction style, but do not bring back operator-heavy generation details.\n"
            "- Treat input_contract.requires_semantics and output_contract.provides_semantics as the V3 equivalent of old ports.requires/provides.\n"
            "- Also fill typed semantic resources in required_resources, optional_resources, and provided_resources.\n"
            "- Use resource_type values from a small vocabulary when possible: SourceDocument, StructuredTable, FinancialMetric, MonetaryAmount, TimePeriod, Entity, Jurisdiction, PolicyRule, ComplianceRequirement, ControlEvidence, AuditSample, ExceptionRecord, AuditFinding, ReconciliationDifference, DeliverableSection.\n"
            "- Use subtype for specific but reusable concepts such as NetProfit, SourceCurrency, ControlOwner, ExceptionSeverity, or SupportingDocument.\n"
            "- Use attributes for required semantic qualifiers such as currency, period, entity, jurisdiction, source_system, or evidence_strength.\n"
            "- Put reusable business context and task-family hints in business_meaning, common_deliverables, and assembly_hints.\n"
            "- Use Fact, Reasoning, Robustness, and Compliance ideas as capability or difficulty tags when they are relevant.\n\n"
            "Atomicity requirement:\n"
            "- Decompose each GDPVal-style prompt into multiple atomic skills when the evidence supports it; do not summarize one prompt into one broad skill.\n"
            "- A task-level skill names a whole deliverable or job, such as \"Prepare Form 1040\", \"Profit and Loss Report Preparation\", or \"Create an Audit Workbook\". These are usually too broad for the registry.\n"
            "- An atomic skill names one reusable capability that can be combined with other skills, such as \"map tax document fields to filing inputs\", \"detect missing supporting schedules\", \"reconcile source totals to report line items\", \"compute period allocation\", or \"validate jurisdiction-specific compliance evidence\".\n"
            "- Prefer skills that can transfer across different task prompts, files, jurisdictions, and deliverable layouts.\n"
            "- If a source prompt mentions a specific form, jurisdiction, or report, extract the reusable action behind it rather than copying the specific artifact as the skill name.\n\n"
            "Hard constraints:\n"
            "- Every candidate must cite at least one evidence object.\n"
            "- Every evidence object must reference source_id and block_id values that appear in the provided sources.\n"
            "- Do not encode exact file names, row counts, generated values, or fixed rubric text as the skill definition.\n"
            "- Extract reusable semantic capabilities, not one-off task instances.\n"
            "- Prefer diverse skills that cover different reusable capabilities, not near-duplicates of the same prompt detail.\n"
            "- Prefer reusable skills that could appear in many future tasks with different domains, files, and data values.\n"
            "- Do not output operator_class, data_params, generator_type, exact spreadsheet operators, or implementation-specific pipeline nodes.\n"
            "- After writing candidates, inspect them pairwise within the same source/block and output local trace_edges for source-supported order, dependency, fan-in, fan-out, validation, or cross-check relationships.\n"
            "- For a sequential workflow, output adjacent edges such as A->B and B->C with relation_type='local_order'.\n"
            "- For validation or cross-check relationships, use relation_type='validation' or 'cross_check' and explain with reason_codes.\n"
            "- Every trace_edge must reference candidate_id values that appear in candidates and block IDs that appear in the normalized sources.\n"
            "- If the source suggests a task graph pattern, output motif_hints using one of: fan_in_reconciliation, policy_application, exception_escalation, cross_check_validation, evidence_to_deliverable.\n"
            "- Motif hints should cover the relevant candidate subset for that pattern, not just one isolated pair. When a motif describes a local workflow, include every candidate_id participating in that workflow.\n"
            "- If trace_edges cover most candidates but motif_hints cover only a small subset, add a broader source-supported motif hint for the shared pattern.\n"
            "- Do not infer global successors across the whole registry. Only report local source-supported trace edges and motif hints.\n"
            "- Use concise English identifiers and tags.\n"
            "- Include the word json in your reasoning only internally; output JSON only.\n\n"
            f"Expected JSON shape:\n{json.dumps(schema_hint, ensure_ascii=False, indent=2)}\n\n"
            f"Extraction instructions:\n{package.instructions}\n\n"
            f"Constraints from package:\n{json.dumps(package.constraints, ensure_ascii=False, indent=2)}\n\n"
            f"Normalized sources:\n{json.dumps(compact_sources, ensure_ascii=False, indent=2)}"
        )

    def _compact_sources(self, package: SkillExtractionPromptPackage) -> List[Dict[str, object]]:
        compact = []
        remaining_chars = self.prompt_char_limit
        for source in package.normalized_sources:
            blocks = []
            for block in source.blocks[: self.prompt_block_limit]:
                if remaining_chars <= 0:
                    break
                text = block.text[:1200]
                remaining_chars -= len(text)
                blocks.append(
                    {
                        "block_id": block.block_id,
                        "block_type": block.block_type,
                        "semantic_tags": block.semantic_tags,
                        "text": text,
                        "start_char": block.source_span.start_char,
                        "end_char": block.source_span.end_char,
                    }
                )
            compact.append(
                {
                    "source_id": source.source_id,
                    "normalized_source_id": source.normalized_source_id,
                    "title": source.title,
                    "domain_tags": source.domain_tags,
                    "domain_terms": source.domain_terms[:50],
                    "blocks": blocks,
                }
            )
        return compact

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SkillExtractionError(f"LLM response was not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise SkillExtractionError("LLM response must be a JSON object.")
        return payload

    def _valid_evidence_ids(self, package: SkillExtractionPromptPackage) -> tuple[set[str], set[tuple[str, str]]]:
        source_ids = set()
        block_ids = set()
        for source in package.normalized_sources:
            source_ids.add(source.source_id)
            for block in source.blocks:
                block_ids.add((source.source_id, block.block_id))
        return source_ids, block_ids

    def _validate_evidence(
        self,
        candidate: ExtractedSkillCandidate,
        valid_source_ids: set[str],
        valid_block_ids: set[tuple[str, str]],
    ) -> None:
        if not candidate.evidence:
            raise SkillExtractionError(f"Candidate {candidate.candidate_id} has no evidence.")
        for evidence in candidate.evidence:
            if evidence.source_id not in valid_source_ids:
                raise SkillExtractionError(f"Evidence {evidence.evidence_id} references unknown source_id {evidence.source_id}.")
            for block_id in evidence.block_ids:
                if (evidence.source_id, block_id) not in valid_block_ids:
                    raise SkillExtractionError(
                        f"Evidence {evidence.evidence_id} references unknown block_id {block_id} for source {evidence.source_id}."
                    )


class FallbackSkillExtractor(BaseSkillExtractor):
    def __init__(self, extractors: List[tuple[str, BaseSkillExtractor]], allow_mock_fallback: bool = True):
        self.extractors = extractors
        self.allow_mock_fallback = allow_mock_fallback
        self.attempts: List[ProviderAttempt] = []
        self.last_trace_edges: List[SkillTraceEdge] = []
        self.last_motif_hints: List[SkillMotifHint] = []

    def extract(self, package: SkillExtractionPromptPackage, max_candidates: int = 8) -> List[ExtractedSkillCandidate]:
        self.attempts = []
        last_error: Optional[Exception] = None
        for provider_name, extractor in self.extractors:
            if isinstance(extractor, MockSkillExtractor) and not self.allow_mock_fallback:
                continue
            model = self._extractor_model(extractor)
            try:
                candidates = extractor.extract(package, max_candidates=max_candidates)
                self.attempts.append(
                    ProviderAttempt(
                        provider_name=provider_name,
                        model=model,
                        success=True,
                        candidate_count=len(candidates),
                    )
                )
                self.last_trace_edges = list(getattr(extractor, "last_trace_edges", []))
                self.last_motif_hints = list(getattr(extractor, "last_motif_hints", []))
                return candidates
            except Exception as exc:
                last_error = exc
                self.attempts.append(
                    ProviderAttempt(
                        provider_name=provider_name,
                        model=model,
                        success=False,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
                )
        raise SkillExtractionError(f"All extraction providers failed. Last error: {last_error}")

    def _extractor_model(self, extractor: BaseSkillExtractor) -> str:
        config = getattr(extractor, "config", None)
        if config is not None:
            return str(getattr(config, "model", "unknown"))
        if isinstance(extractor, MockSkillExtractor):
            return "mock_rule_based_v0"
        return "unknown"


def load_env_file(path: str | Path) -> Dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values = {}
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def build_tuzi_config(env_path: str | Path, model_override: Optional[str], timeout_seconds: int) -> Optional[ProviderConfig]:
    env_values = load_env_file(env_path)
    api_key = env_values.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = env_values.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    model = model_override or env_values.get("OPENAI_MODEL") or os.environ.get("OPENAI_MODEL")
    if not api_key or not base_url or not model:
        return None
    return ProviderConfig(
        provider_name="tuzi",
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )


def build_deepseek_config(key_path: str | Path, model: str, timeout_seconds: int) -> Optional[ProviderConfig]:
    path = Path(key_path)
    if not path.exists():
        return None
    api_key = path.read_text(encoding="utf-8", errors="replace").strip()
    if not api_key:
        return None
    return ProviderConfig(
        provider_name="deepseek",
        base_url="https://api.deepseek.com",
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )
