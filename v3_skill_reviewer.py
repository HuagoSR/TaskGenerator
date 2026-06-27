import re
from typing import Dict, List, Literal

from pydantic import BaseModel, Field

from v3_source_schema import ExtractedSkillCandidate


ReviewDecision = Literal["accept", "revise", "reject"]


class SkillReviewScores(BaseModel):
    reusability_score: float
    diversity_score: float
    semantic_clarity_score: float
    evidence_grounding_score: float
    assembly_usefulness_score: float
    atomicity_score: float
    operator_leakage_penalty: float
    single_instance_overfit_penalty: float
    task_level_overbreadth_penalty: float
    total_score: float


class SkillReviewResult(BaseModel):
    candidate_id: str
    proposed_name: str
    decision: ReviewDecision
    scores: SkillReviewScores
    reason_codes: List[str] = Field(default_factory=list)
    reviewer_notes: List[str] = Field(default_factory=list)
    suggested_abstraction: str = ""


class SkillCandidateReviewer:
    """Deterministic first-pass reviewer prioritizing diversity and reusability."""

    operator_terms = {
        "operator",
        "operator_class",
        "data_params",
        "generator_type",
        "uniform",
        "categorical",
        "cellperturbation",
        "filteroperator",
    }
    file_pattern = re.compile(r"\b[\w\-]+\.(xlsx|csv|pdf|docx|pptx|txt)\b", re.IGNORECASE)
    numeric_overfit_pattern = re.compile(r"\b(row\s*\d+|\d+\s*rows?|q[1-4]\s*20\d{2}|20\d{2})\b", re.IGNORECASE)
    instance_terms = {
        "this task",
        "the provided file",
        "the given spreadsheet",
        "the attached document",
        "exactly as requested",
    }
    atomic_action_terms = {
        "map",
        "detect",
        "classify",
        "reconcile",
        "compute",
        "validate",
        "apply",
        "extract",
        "normalize",
        "identify",
        "allocate",
        "match",
        "compare",
        "convert",
        "resolve",
        "tie",
    }
    task_level_terms = {
        "preparation",
        "report preparation",
        "return preparation",
        "statement preparation",
        "schedule preparation",
        "workbook preparation",
        "document generation",
        "report generation",
        "presentation generation",
        "question construction",
        "questionnaire construction",
        "narrative drafting",
        "prepare report",
        "prepare return",
        "prepare form",
        "complete report",
        "create report",
        "create workbook",
        "create spreadsheet",
        "presentation slides",
        "slide deck",
    }
    task_level_name_terms = {
        "preparation",
        "report preparation",
        "return preparation",
        "statement preparation",
        "schedule preparation",
        "workbook preparation",
        "document generation",
        "report generation",
        "presentation generation",
        "question construction",
        "questionnaire construction",
        "narrative drafting",
    }
    form_specific_pattern = re.compile(
        r"\b(form\s*\d+|1040|1099|w-?2|schedule\s+(?:[a-z]\b|\d+\b)|irs|tax return|jurisdiction-specific|country-specific)\b",
        re.IGNORECASE,
    )
    broad_deliverable_pattern = re.compile(
        r"\b(build|create|prepare|produce|generate|structure|construct|write|compile|draft)\b.{0,60}\b(report|workbook|spreadsheet|statement|return|deliverable|document|presentation|slides?|deck|questions?|questionnaire|narrative|profiles?|visualizations?)\b",
        re.IGNORECASE,
    )
    source_collection_pattern = re.compile(
        r"\b(open\s+web|web\s+search|retrieve\s+and\s+normalize|external\s+data\s+retrieval|sourcecollector|collect\s+source)\b",
        re.IGNORECASE,
    )

    def review_many(self, candidates: List[ExtractedSkillCandidate]) -> List[SkillReviewResult]:
        return [self.review(candidate) for candidate in candidates]

    def accepted_candidates(self, candidates: List[ExtractedSkillCandidate], reviews: List[SkillReviewResult]) -> List[ExtractedSkillCandidate]:
        review_by_id = {review.candidate_id: review for review in reviews}
        accepted = []
        for candidate in candidates:
            review = review_by_id.get(candidate.candidate_id)
            if review and review.decision == "accept":
                accepted.append(candidate.model_copy(update={"extraction_status": "accepted"}))
        return accepted

    def review(self, candidate: ExtractedSkillCandidate) -> SkillReviewResult:
        text = self._candidate_text(candidate)
        reason_codes: List[str] = []
        notes: List[str] = []

        reusability = self._score_reusability(candidate, text, reason_codes)
        diversity = self._score_diversity(candidate, reason_codes)
        semantic_clarity = self._score_semantic_clarity(candidate, reason_codes)
        evidence_grounding = self._score_evidence(candidate, reason_codes)
        assembly_usefulness = self._score_assembly(candidate, reason_codes)
        atomicity = self._score_atomicity(candidate, text, reason_codes)
        operator_penalty = self._operator_leakage_penalty(text, reason_codes)
        overfit_penalty = self._single_instance_overfit_penalty(text, reason_codes)
        task_level_penalty = self._task_level_overbreadth_penalty(candidate, text, reason_codes)

        total = round(
            (
                0.18 * reusability
                + 0.14 * diversity
                + 0.16 * semantic_clarity
                + 0.18 * evidence_grounding
                + 0.14 * assembly_usefulness
                + 0.20 * atomicity
            )
            - operator_penalty
            - overfit_penalty
            - task_level_penalty,
            4,
        )
        decision = self._decision(total, reason_codes)
        suggested_abstraction = self._suggest_abstraction(candidate, reason_codes)
        if decision == "accept":
            notes.append("Candidate is reusable, evidence-backed, atomic enough, and useful for downstream task assembly.")
        elif decision == "revise":
            notes.append("Candidate is potentially useful but should be revised before registry insertion.")
            if suggested_abstraction:
                notes.append(f"Suggested abstraction: {suggested_abstraction}.")
        else:
            notes.append("Candidate should not enter the registry in its current form.")

        return SkillReviewResult(
            candidate_id=candidate.candidate_id,
            proposed_name=candidate.proposed_name,
            decision=decision,
            scores=SkillReviewScores(
                reusability_score=reusability,
                diversity_score=diversity,
                semantic_clarity_score=semantic_clarity,
                evidence_grounding_score=evidence_grounding,
                assembly_usefulness_score=assembly_usefulness,
                atomicity_score=atomicity,
                operator_leakage_penalty=operator_penalty,
                single_instance_overfit_penalty=overfit_penalty,
                task_level_overbreadth_penalty=task_level_penalty,
                total_score=total,
            ),
            reason_codes=reason_codes,
            reviewer_notes=notes,
            suggested_abstraction=suggested_abstraction,
        )

    def _candidate_text(self, candidate: ExtractedSkillCandidate) -> str:
        parts = [
            candidate.proposed_name,
            " ".join(candidate.domain_tags),
            " ".join(candidate.capability_tags),
            " ".join(candidate.difficulty_tags),
            candidate.business_meaning,
            candidate.hidden_difficulty,
            " ".join(candidate.common_failure_modes),
            " ".join(candidate.common_deliverables),
            " ".join(candidate.assembly_hints),
        ]
        return " ".join(parts).lower()

    def _score_reusability(self, candidate: ExtractedSkillCandidate, text: str, reason_codes: List[str]) -> float:
        score = 0.35
        if candidate.capability_tags:
            score += 0.2
        if candidate.common_deliverables:
            score += 0.15
        if candidate.assembly_hints:
            score += 0.15
        if any(term in text for term in ["reusable", "general", "across", "task", "workflow", "reconciliation", "analysis"]):
            score += 0.15
        if score < 0.65:
            reason_codes.append("low_reusability")
        return min(round(score, 4), 1.0)

    def _score_diversity(self, candidate: ExtractedSkillCandidate, reason_codes: List[str]) -> float:
        tag_count = len(set(candidate.capability_tags + candidate.difficulty_tags + candidate.domain_tags))
        score = min(1.0, 0.25 + tag_count * 0.08)
        if len(candidate.capability_tags) >= 2 and len(candidate.difficulty_tags) >= 1:
            score += 0.15
        score = min(round(score, 4), 1.0)
        if score < 0.55:
            reason_codes.append("low_diversity")
        return score

    def _score_semantic_clarity(self, candidate: ExtractedSkillCandidate, reason_codes: List[str]) -> float:
        score = 0.0
        if len(candidate.proposed_name.strip()) >= 8:
            score += 0.18
        if len(candidate.business_meaning.strip()) >= 40:
            score += 0.24
        if len(candidate.hidden_difficulty.strip()) >= 30:
            score += 0.2
        if candidate.input_contract.requires_semantics or candidate.input_contract.optional_semantics:
            score += 0.18
        if candidate.output_contract.provides_semantics:
            score += 0.2
        score = min(round(score, 4), 1.0)
        if score < 0.7:
            reason_codes.append("weak_semantic_contract")
        return score

    def _score_evidence(self, candidate: ExtractedSkillCandidate, reason_codes: List[str]) -> float:
        if not candidate.evidence:
            reason_codes.append("missing_evidence")
            return 0.0
        score = 0.35
        for evidence in candidate.evidence:
            if evidence.source_id and evidence.block_ids:
                score += 0.2
            if evidence.supporting_spans:
                score += 0.15
            if len(evidence.evidence_summary.strip()) >= 30:
                score += 0.1
        score = min(round(score, 4), 1.0)
        if score < 0.75:
            reason_codes.append("weak_evidence_grounding")
        return score

    def _score_assembly(self, candidate: ExtractedSkillCandidate, reason_codes: List[str]) -> float:
        score = 0.3
        if candidate.assembly_hints:
            score += 0.25
        if candidate.common_failure_modes:
            score += 0.15
        if candidate.common_deliverables:
            score += 0.15
        if candidate.capability_tags:
            score += 0.15
        score = min(round(score, 4), 1.0)
        if score < 0.65:
            reason_codes.append("weak_assembly_usefulness")
        return score

    def _score_atomicity(self, candidate: ExtractedSkillCandidate, text: str, reason_codes: List[str]) -> float:
        score = 0.25
        name = candidate.proposed_name.lower()
        contract_text = " ".join(
            candidate.input_contract.requires_semantics
            + candidate.input_contract.optional_semantics
            + candidate.output_contract.provides_semantics
        ).lower()
        action_text = f"{name} {contract_text} {' '.join(candidate.assembly_hints).lower()}"

        if any(term in action_text for term in self.atomic_action_terms):
            score += 0.2
        if 1 <= len(candidate.output_contract.provides_semantics) <= 2:
            score += 0.18
        if 1 <= len(candidate.input_contract.requires_semantics) <= 4:
            score += 0.12
        if candidate.hidden_difficulty and len(candidate.hidden_difficulty.split()) <= 32:
            score += 0.12
        if candidate.common_failure_modes:
            score += 0.1
        if candidate.assembly_hints and not any(term in " ".join(candidate.assembly_hints).lower() for term in self.task_level_terms):
            score += 0.13

        name_is_task_level = any(term in name for term in self.task_level_name_terms) or bool(self.broad_deliverable_pattern.search(name))
        if name_is_task_level:
            score -= 0.22
        if self.form_specific_pattern.search(text):
            score -= 0.12
        if self.source_collection_pattern.search(text):
            score -= 0.18

        score = max(0.0, min(round(score, 4), 1.0))
        if score < 0.65:
            reason_codes.append("low_atomicity")
        return score

    def _operator_leakage_penalty(self, text: str, reason_codes: List[str]) -> float:
        if any(term in text for term in self.operator_terms):
            reason_codes.append("operator_leakage")
            return 0.25
        return 0.0

    def _single_instance_overfit_penalty(self, text: str, reason_codes: List[str]) -> float:
        penalty = 0.0
        if self.file_pattern.search(text):
            penalty += 0.15
            reason_codes.append("file_name_overfit")
        if self.numeric_overfit_pattern.search(text):
            penalty += 0.1
            reason_codes.append("specific_value_overfit")
        if any(term in text for term in self.instance_terms):
            penalty += 0.1
            reason_codes.append("single_instance_language")
        return min(round(penalty, 4), 0.3)

    def _task_level_overbreadth_penalty(self, candidate: ExtractedSkillCandidate, text: str, reason_codes: List[str]) -> float:
        penalty = 0.0
        name = candidate.proposed_name.lower()
        contract_text = " ".join(
            candidate.input_contract.requires_semantics + candidate.output_contract.provides_semantics
        ).lower()
        appears_atomic = (
            any(term in f"{name} {contract_text}" for term in self.atomic_action_terms)
            and 1 <= len(candidate.output_contract.provides_semantics) <= 2
        )

        if (
            any(term in name for term in self.task_level_name_terms)
            or any(term in text for term in self.task_level_terms)
            or bool(self.broad_deliverable_pattern.search(name))
        ):
            penalty += 0.18
            reason_codes.append("task_level_overbreadth")
        if self.form_specific_pattern.search(text):
            penalty += 0.14
            reason_codes.append("form_or_jurisdiction_specific")
        if self.source_collection_pattern.search(text):
            penalty += 0.16
            reason_codes.append("source_collection_leakage")
        if appears_atomic and penalty:
            penalty *= 0.5
            reason_codes.append("task_level_penalty_reduced_by_atomic_contract")
        return min(round(penalty, 4), 0.32)

    def _decision(self, total_score: float, reason_codes: List[str]) -> ReviewDecision:
        blocking = {"missing_evidence", "operator_leakage"}
        if blocking & set(reason_codes):
            return "reject"
        revise_only = {"task_level_overbreadth", "form_or_jurisdiction_specific", "low_atomicity", "source_collection_leakage"}
        if revise_only & set(reason_codes):
            if total_score >= 0.48:
                return "revise"
            return "reject"
        if total_score >= 0.74:
            return "accept"
        if total_score >= 0.5:
            return "revise"
        return "reject"

    def _suggest_abstraction(self, candidate: ExtractedSkillCandidate, reason_codes: List[str]) -> str:
        text = self._candidate_text(candidate)
        name = candidate.proposed_name.lower()
        reason_set = set(reason_codes)
        if "form_or_jurisdiction_specific" in reason_set and any(term in text for term in ["1040", "tax return", "irs", "form"]):
            return "Structured Statutory Filing Input Mapping or Jurisdiction-Specific Compliance Schedule Selection"
        if "source_collection_leakage" in reason_set:
            return "Source Evidence Normalization From Candidate-Visible Materials"
        if "task_level_overbreadth" in reason_set and any(term in name for term in ["report", "statement", "workbook"]):
            return "Source-to-Report Metric Mapping or Financial Statement Component Assembly"
        if "task_level_overbreadth" in reason_set and any(term in name for term in ["presentation", "slide", "deck"]):
            return "Evidence-to-Executive-Insight Structuring"
        if "task_level_overbreadth" in reason_set and any(term in name for term in ["question", "questionnaire"]):
            return "Compliance Criterion Mapping or Risk-Control Coverage Selection"
        if "task_level_overbreadth" in reason_set and "schedule" in name:
            return "Periodic Allocation Schedule Calculation"
        if "low_atomicity" in reason_set:
            return "A single reusable action such as mapping, reconciling, validating, resolving, or allocating one semantic input-output pair"
        return ""
