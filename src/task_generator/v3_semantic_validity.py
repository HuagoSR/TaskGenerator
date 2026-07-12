from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, model_validator


ClaimType = Literal["amount", "quantity", "matching", "classification", "status", "judgment"]
Determinism = Literal["exact", "tolerance", "acceptable_set", "judgmental"]
Answerability = Literal["supported", "ambiguous", "unsupported"]
FindingSeverity = Literal["info", "warning", "blocking"]
SemanticDecision = Literal[
    "pass",
    "pass_with_advisories",
    "revise",
    "blocked",
    "needs_secondary_review",
    "needs_human_review",
]
SemanticMode = Literal["disabled", "prepare", "diagnostic", "blocking"]
FindingCode = Literal[
    "missing_candidate_input",
    "underdefined_decision_rule",
    "ambiguous_requirement",
    "hidden_assumption_required",
    "teacher_truth_conflict",
    "goldenrun_requirement_gap",
    "rubric_missing_fact_coverage",
    "irrelevant_rubric_criterion",
    "rubric_weight_imbalance",
    "deliverable_contract_mismatch",
]

FINDING_CODES = {
    "missing_candidate_input",
    "underdefined_decision_rule",
    "ambiguous_requirement",
    "hidden_assumption_required",
    "teacher_truth_conflict",
    "goldenrun_requirement_gap",
    "rubric_missing_fact_coverage",
    "irrelevant_rubric_criterion",
    "rubric_weight_imbalance",
    "deliverable_contract_mismatch",
}


class SemanticDependency(BaseModel):
    dependency_id: str
    description: str
    source_kind: Literal["candidate_file", "candidate_rule", "prompt", "teacher_only"]
    file_name: Optional[str] = None
    locator: Optional[str] = None
    field_names: List[str] = Field(default_factory=list)
    candidate_visible: bool = True


class SemanticRequirement(BaseModel):
    requirement_id: str
    prompt_text: str
    deliverable_file: str
    deliverable_location: str = ""
    claim_ids: List[str] = Field(default_factory=list)


class SemanticClaim(BaseModel):
    claim_id: str
    requirement_id: str
    claim_type: ClaimType
    determinism: Determinism
    description: str
    dependency_ids: List[str] = Field(default_factory=list)
    expected_value: Any = None
    acceptable_values: List[Any] = Field(default_factory=list)
    tolerance: Optional[float] = None
    explicit_assumptions: List[str] = Field(default_factory=list)
    prohibited_hidden_assumptions: List[str] = Field(default_factory=list)
    validator_id: Optional[str] = None
    rubric_criterion_ids: List[str] = Field(default_factory=list)


class TaskSemanticContract(BaseModel):
    contract_version: str = "v3.task_semantic_contract.1"
    task_id: str
    created_at: str
    requirements: List[SemanticRequirement]
    claims: List[SemanticClaim]
    dependencies: List[SemanticDependency]
    notes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_links(self) -> "TaskSemanticContract":
        requirement_ids = {item.requirement_id for item in self.requirements}
        claim_ids = {item.claim_id for item in self.claims}
        dependency_ids = {item.dependency_id for item in self.dependencies}
        if len(requirement_ids) != len(self.requirements):
            raise ValueError("Duplicate semantic requirement ids.")
        if len(claim_ids) != len(self.claims):
            raise ValueError("Duplicate semantic claim ids.")
        if len(dependency_ids) != len(self.dependencies):
            raise ValueError("Duplicate semantic dependency ids.")
        for requirement in self.requirements:
            if not requirement.claim_ids:
                raise ValueError(f"Requirement {requirement.requirement_id} has no claim mapping.")
            if not set(requirement.claim_ids).issubset(claim_ids):
                raise ValueError(f"Requirement {requirement.requirement_id} references an unknown claim.")
        for claim in self.claims:
            if claim.requirement_id not in requirement_ids:
                raise ValueError(f"Claim {claim.claim_id} references an unknown requirement.")
            if not set(claim.dependency_ids).issubset(dependency_ids):
                raise ValueError(f"Claim {claim.claim_id} references an unknown dependency.")
            if claim.determinism in {"exact", "tolerance", "acceptable_set"} and not claim.dependency_ids:
                raise ValueError(f"Deterministic claim {claim.claim_id} has no dependency.")
        return self


class SemanticFinding(BaseModel):
    finding_code: FindingCode
    severity: FindingSeverity
    message: str
    requirement_id: Optional[str] = None
    claim_id: Optional[str] = None
    evidence_locators: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    alternative_interpretations: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    deterministic_corroboration: bool = False

class BlindRequirementReview(BaseModel):
    requirement_id: str
    answerability: Answerability
    required_inputs: List[str] = Field(default_factory=list)
    visible_support: List[str] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)
    alternative_interpretations: List[str] = Field(default_factory=list)
    independent_result: Any = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    findings: List[SemanticFinding] = Field(default_factory=list)


class CandidateBlindReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_version: str = "v3.candidate_blind_semantic_review.1"
    task_id: str
    model: str
    provider: str
    created_at: str
    prompt_package_sha256: str
    status: Literal["completed", "failed"] = "completed"
    requirement_reviews: List[BlindRequirementReview] = Field(min_length=1)
    findings: List[SemanticFinding] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class TeacherRubricReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_version: str = "v3.teacher_rubric_semantic_review.1"
    task_id: str
    model: str
    provider: str
    created_at: str
    blind_review_sha256: str
    status: Literal["completed", "failed"] = "completed"
    teacher_truth_consistent: bool
    goldenrun_covers_requirements: bool
    rubric_fact_weight_ratio: float = Field(ge=0.0, le=1.0)
    findings: List[SemanticFinding] = Field(default_factory=list)
    repair_proposals: List[Dict[str, Any]] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class SemanticValidityGateReport(BaseModel):
    gate_version: str = "v3.semantic_validity_gate.1"
    task_id: str
    created_at: str
    mode: SemanticMode
    decision: SemanticDecision
    semantic_gate_pass: bool = False
    secondary_review_required: bool = False
    needs_human_review: bool = False
    repair_iteration: int = 0
    findings: List[SemanticFinding] = Field(default_factory=list)
    reason_codes: List[str] = Field(default_factory=list)
    artifact_sha256: Dict[str, str] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)


class SemanticContractValidator:
    def validate(self, contract: TaskSemanticContract) -> List[SemanticFinding]:
        findings: List[SemanticFinding] = []
        dependencies = {item.dependency_id: item for item in contract.dependencies}
        claims = {item.claim_id: item for item in contract.claims}
        for requirement in contract.requirements:
            if not requirement.deliverable_file:
                findings.append(self._finding("deliverable_contract_mismatch", "blocking", "Requirement has no deliverable file.", requirement.requirement_id))
            for claim_id in requirement.claim_ids:
                claim = claims[claim_id]
                for dependency_id in claim.dependency_ids:
                    dependency = dependencies[dependency_id]
                    if dependency.source_kind == "teacher_only" or not dependency.candidate_visible:
                        findings.append(
                            self._finding(
                                "hidden_assumption_required",
                                "blocking",
                                "A deterministic claim depends on teacher-only information.",
                                requirement.requirement_id,
                                claim.claim_id,
                                [dependency_id],
                            )
                        )
                    if dependency.source_kind in {"candidate_file", "candidate_rule"} and (
                        not dependency.file_name or not dependency.locator
                    ):
                        findings.append(
                            self._finding(
                                "missing_candidate_input",
                                "blocking",
                                "A candidate dependency lacks a file or locator.",
                                requirement.requirement_id,
                                claim.claim_id,
                                [dependency_id],
                            )
                        )
                if claim.claim_type in {"classification", "status"} and claim.determinism != "judgmental":
                    has_rule = any(dependencies[item].source_kind == "candidate_rule" for item in claim.dependency_ids)
                    if not has_rule:
                        findings.append(
                            self._finding(
                                "underdefined_decision_rule",
                                "blocking",
                                "A deterministic classification/status claim has no candidate-visible decision rule.",
                                requirement.requirement_id,
                                claim.claim_id,
                            )
                        )
                if claim.determinism in {"exact", "tolerance", "acceptable_set"} and not claim.rubric_criterion_ids:
                    findings.append(
                        self._finding(
                            "rubric_missing_fact_coverage",
                            "blocking",
                            "A deterministic claim has no linked rubric criterion.",
                            requirement.requirement_id,
                            claim.claim_id,
                        )
                    )
        return findings

    def _finding(
        self,
        code: str,
        severity: FindingSeverity,
        message: str,
        requirement_id: Optional[str] = None,
        claim_id: Optional[str] = None,
        missing_inputs: Optional[List[str]] = None,
    ) -> SemanticFinding:
        return SemanticFinding(
            finding_code=code,
            severity=severity,
            message=message,
            requirement_id=requirement_id,
            claim_id=claim_id,
            missing_inputs=missing_inputs or [],
            deterministic_corroboration=True,
        )


class SemanticContractDraftBuilder:
    """Build a generic contract draft from generator-owned blueprint structure.

    The draft is intentionally conservative. It provides stable requirement and dependency
    identifiers; the candidate-blind critic must still challenge semantic sufficiency.
    """

    def build(self, task_id: str, blueprint: Dict[str, Any], rubric: Optional[Dict[str, Any]] = None) -> TaskSemanticContract:
        dependencies: List[SemanticDependency] = []
        for item in ((blueprint.get("data_spec") or {}).get("reference_files") or []):
            file_name = str(item.get("file_name") or "")
            if not file_name:
                continue
            is_rule = "policy" in file_name.lower() or str(item.get("file_role") or "") in {"policy", "decision_rule"}
            fields = [
                str(column.get("name") or "")
                for sheet in item.get("sheet_specs") or []
                for column in sheet.get("columns") or []
                if column.get("name")
            ]
            dependencies.append(
                SemanticDependency(
                    dependency_id=f"dep_{len(dependencies) + 1:03d}",
                    description=f"Candidate-visible source {file_name}",
                    source_kind="candidate_rule" if is_rule else "candidate_file",
                    file_name=file_name,
                    locator="document:all" if Path(file_name).suffix.lower() != ".xlsx" else "workbook:all_sheets",
                    field_names=fields,
                )
            )
        if not dependencies:
            dependencies.append(
                SemanticDependency(
                    dependency_id="dep_001",
                    description="Candidate-visible prompt context",
                    source_kind="prompt",
                    locator="prompt:all",
                )
            )

        rubric_items = self._rubric_items(rubric or {})
        requirements: List[SemanticRequirement] = []
        claims: List[SemanticClaim] = []
        for deliverable in blueprint.get("deliverable_spec") or []:
            file_name = str(deliverable.get("file_name") or "")
            for text in deliverable.get("requirements") or []:
                requirement_id = f"req_{len(requirements) + 1:03d}"
                claim_id = f"claim_{len(claims) + 1:03d}"
                claim_type = self._claim_type(str(text))
                determinism: Determinism = "judgmental" if claim_type == "judgment" else "exact"
                linked_criteria = self._matching_rubric_ids(str(text), rubric_items)
                requirements.append(
                    SemanticRequirement(
                        requirement_id=requirement_id,
                        prompt_text=str(text),
                        deliverable_file=file_name,
                        deliverable_location="deliverable:any",
                        claim_ids=[claim_id],
                    )
                )
                claims.append(
                    SemanticClaim(
                        claim_id=claim_id,
                        requirement_id=requirement_id,
                        claim_type=claim_type,
                        determinism=determinism,
                        description=str(text),
                        dependency_ids=[item.dependency_id for item in dependencies],
                        rubric_criterion_ids=linked_criteria,
                        prohibited_hidden_assumptions=["Do not use facts unavailable in candidate-visible prompt or reference files."],
                    )
                )
        if not requirements:
            raise ValueError("Blueprint has no deliverable requirements for semantic contract construction.")
        return TaskSemanticContract(
            task_id=task_id,
            created_at=_now(),
            requirements=requirements,
            claims=claims,
            dependencies=dependencies,
            notes=[
                "Drafted from generator-owned blueprint structure.",
                "Semantic sufficiency still requires candidate-blind review.",
            ],
        )

    def build_from_legacy_dataset(
        self,
        dataset: Dict[str, Any],
        reference_files: List[str | Path],
    ) -> TaskSemanticContract:
        """Create a conservative migration contract without treating legacy teacher truth as valid."""
        task_id = str(dataset.get("task_id") or "legacy_task")
        prompt = str(dataset.get("prompt") or "")
        visible_requirements = self._prompt_requirements(prompt)
        deliverables = [Path(str(value).replace("\\", "/")).name for value in dataset.get("deliverable_files") or []]
        deliverable = deliverables[0] if deliverables else "required_deliverable"
        dependencies: List[SemanticDependency] = []
        for index, value in enumerate(reference_files, start=1):
            path = Path(value)
            is_rule = "policy" in path.name.lower() or "rule" in path.name.lower()
            dependencies.append(
                SemanticDependency(
                    dependency_id=f"dep_{index:03d}",
                    description=f"Legacy candidate-visible reference {path.name}",
                    source_kind="candidate_rule" if is_rule else "candidate_file",
                    file_name=path.name,
                    locator="document:all" if path.suffix.lower() != ".xlsx" else "workbook:all_sheets",
                )
            )
        requirements = []
        claims = []
        for index, text in enumerate(visible_requirements or ["Complete the requested deliverable using only candidate-visible evidence."], start=1):
            requirement_id = f"req_{index:03d}"
            claim_id = f"claim_{index:03d}"
            requirements.append(
                SemanticRequirement(
                    requirement_id=requirement_id,
                    prompt_text=text,
                    deliverable_file=deliverable,
                    deliverable_location="deliverable:any",
                    claim_ids=[claim_id],
                )
            )
            claims.append(
                SemanticClaim(
                    claim_id=claim_id,
                    requirement_id=requirement_id,
                    claim_type=self._claim_type(text),
                    determinism="judgmental",
                    description=text,
                    dependency_ids=[item.dependency_id for item in dependencies],
                    prohibited_hidden_assumptions=["Do not use facts unavailable in candidate-visible prompt or reference files."],
                )
            )
        return TaskSemanticContract(
            task_id=task_id,
            created_at=_now(),
            requirements=requirements,
            claims=claims,
            dependencies=dependencies,
            notes=[
                "Legacy migration contract; it does not certify teacher truth or answer determinism.",
                "Candidate-blind and teacher/rubric reviews must determine semantic validity.",
            ],
        )

    def _rubric_items(self, rubric: Dict[str, Any]) -> List[Dict[str, str]]:
        items = []
        for section in rubric.get("sections") or []:
            for criterion in section.get("criteria") or []:
                items.append(
                    {
                        "id": str(criterion.get("criterion_id") or ""),
                        "text": " ".join(
                            [str(criterion.get("description") or ""), str(criterion.get("pass_condition") or "")]
                        ),
                    }
                )
        return items

    def _matching_rubric_ids(self, requirement: str, items: List[Dict[str, str]]) -> List[str]:
        tokens = self._tokens(requirement)
        matches = []
        for item in items:
            if len(tokens.intersection(self._tokens(item["text"]))) >= 2 and item["id"]:
                matches.append(item["id"])
        return matches[:5]

    def _claim_type(self, text: str) -> ClaimType:
        lowered = text.lower()
        if any(token in lowered for token in ["amount", "balance", "total", "value"]):
            return "amount"
        if any(token in lowered for token in ["quantity", "count", "number"]):
            return "quantity"
        if any(token in lowered for token in ["match", "reconcile", "tie out"]):
            return "matching"
        if any(token in lowered for token in ["classify", "category", "exception"]):
            return "classification"
        if any(token in lowered for token in ["status", "hold", "approve", "reject"]):
            return "status"
        return "judgment"

    def _tokens(self, text: str) -> Set[str]:
        return {token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(token) > 2}

    def _prompt_requirements(self, prompt: str) -> List[str]:
        lines = prompt.splitlines()
        requirements: List[str] = []
        in_visible = False
        for raw in lines:
            line = raw.strip()
            lowered = line.lower()
            if lowered in {"visible requirements:", "requirements:"}:
                in_visible = True
                continue
            if in_visible and lowered in {"reference files:", "deliverables:", "style constraints:"}:
                break
            if in_visible and line.startswith("- "):
                requirements.append(line[2:].strip())
        return requirements[:40]


class SemanticValidityGate:
    SECONDARY_CONFIDENCE_THRESHOLD = 0.80
    MIN_FACT_WEIGHT_RATIO = 0.60

    def build(
        self,
        contract: TaskSemanticContract,
        blind_review: Optional[CandidateBlindReview],
        teacher_review: Optional[TeacherRubricReview],
        mode: SemanticMode,
        repair_iteration: int = 0,
        force_secondary_audit: bool = False,
        secondary_blind_review: Optional[CandidateBlindReview] = None,
        secondary_teacher_review: Optional[TeacherRubricReview] = None,
        deterministic_findings: Optional[List[SemanticFinding]] = None,
    ) -> SemanticValidityGateReport:
        contract_findings = SemanticContractValidator().validate(contract)
        contract_findings.extend(deterministic_findings or [])
        for item in contract_findings:
            item.deterministic_corroboration = True
        findings = list(contract_findings)
        primary_findings: List[SemanticFinding] = []
        if blind_review:
            primary_findings.extend(blind_review.findings)
            for review in blind_review.requirement_reviews:
                primary_findings.extend(review.findings)
                if review.answerability != "supported" and not review.findings:
                    primary_findings.append(
                        SemanticFinding(
                            finding_code="ambiguous_requirement" if review.answerability == "ambiguous" else "missing_candidate_input",
                            severity="blocking",
                            message=f"Requirement is {review.answerability} in candidate-blind review.",
                            requirement_id=review.requirement_id,
                            missing_inputs=review.missing_inputs,
                            alternative_interpretations=review.alternative_interpretations,
                            confidence=review.confidence,
                        )
                    )
        if teacher_review:
            primary_findings.extend(teacher_review.findings)
            if not teacher_review.teacher_truth_consistent:
                primary_findings.append(SemanticFinding(finding_code="teacher_truth_conflict", severity="blocking", message="Teacher truth conflicts with the independent candidate-blind review."))
            if not teacher_review.goldenrun_covers_requirements:
                primary_findings.append(SemanticFinding(finding_code="goldenrun_requirement_gap", severity="blocking", message="GoldenRun does not cover every candidate requirement."))
            if teacher_review.rubric_fact_weight_ratio < self.MIN_FACT_WEIGHT_RATIO:
                primary_findings.append(
                    SemanticFinding(
                        finding_code="rubric_weight_imbalance",
                        severity="blocking",
                        message=f"Rubric fact/deliverable weight ratio {teacher_review.rubric_fact_weight_ratio:.3f} is below {self.MIN_FACT_WEIGHT_RATIO:.2f}.",
                        deterministic_corroboration=False,
                    )
                )
        for item in primary_findings:
            item.deterministic_corroboration = False
        findings.extend(primary_findings)

        secondary_findings: List[SemanticFinding] = []
        if secondary_blind_review:
            secondary_findings.extend(secondary_blind_review.findings)
            for review in secondary_blind_review.requirement_reviews:
                secondary_findings.extend(review.findings)
        if secondary_teacher_review:
            secondary_findings.extend(secondary_teacher_review.findings)
        findings.extend(secondary_findings)

        findings = self._deduplicate(findings)
        low_confidence = any(item.confidence < self.SECONDARY_CONFIDENCE_THRESHOLD for item in primary_findings)
        primary_blocker_keys = self._material_keys(primary_findings)
        uncorroborated_blocker = bool(primary_blocker_keys)
        has_secondary = secondary_blind_review is not None and secondary_teacher_review is not None
        secondary_required = (force_secondary_audit or low_confidence or uncorroborated_blocker) and not has_secondary
        needs_human = False
        confirmed_llm_blocker = False
        if has_secondary:
            secondary_blocker_keys = self._material_keys(secondary_findings)
            confirmed_llm_blocker = bool(primary_blocker_keys.intersection(secondary_blocker_keys))
            needs_human = bool(primary_blocker_keys.symmetric_difference(secondary_blocker_keys))
        deterministic_blocking = any(item.severity == "blocking" for item in contract_findings)
        blocking = deterministic_blocking or confirmed_llm_blocker
        advisories = any(item.severity in {"info", "warning"} for item in findings)

        if mode == "disabled":
            decision: SemanticDecision = "pass"
            passed = True
        elif blind_review is None or teacher_review is None:
            decision = "revise" if mode == "prepare" else "blocked"
            passed = False
        elif needs_human:
            decision = "needs_human_review"
            passed = False
        elif secondary_required:
            decision = "needs_secondary_review"
            passed = False
        elif blocking:
            decision = "blocked" if repair_iteration >= 2 else "revise"
            passed = False
        elif advisories:
            decision = "pass_with_advisories"
            passed = True
        else:
            decision = "pass"
            passed = True

        return SemanticValidityGateReport(
            task_id=contract.task_id,
            created_at=_now(),
            mode=mode,
            decision=decision,
            semantic_gate_pass=passed,
            secondary_review_required=secondary_required,
            needs_human_review=needs_human,
            repair_iteration=repair_iteration,
            findings=findings,
            reason_codes=sorted({item.finding_code for item in findings}),
            notes=[
                "LLM findings are diagnostic evidence, not self-authenticating truth.",
                "Only candidate-visible dependencies may support deterministic claims.",
                "The gate never edits task artifacts in place.",
            ],
        )

    def _deduplicate(self, findings: List[SemanticFinding]) -> List[SemanticFinding]:
        unique: Dict[str, SemanticFinding] = {}
        for item in findings:
            key = "|".join([item.finding_code, item.requirement_id or "", item.claim_id or "", item.message])
            unique[key] = item
        return list(unique.values())

    def _material_keys(self, findings: List[SemanticFinding]) -> Set[str]:
        return {
            "|".join([item.requirement_id or "global", self._finding_family(item.finding_code)])
            for item in findings
            if item.severity == "blocking"
        }

    def _finding_family(self, code: str) -> str:
        if code in {"missing_candidate_input", "hidden_assumption_required"}:
            return "candidate_support"
        if code in {"underdefined_decision_rule", "ambiguous_requirement"}:
            return "decision_ambiguity"
        if code in {"teacher_truth_conflict", "goldenrun_requirement_gap"}:
            return "teacher_alignment"
        if code in {"rubric_missing_fact_coverage", "irrelevant_rubric_criterion", "rubric_weight_imbalance"}:
            return "rubric_alignment"
        return code


class SemanticReviewPackageBuilder:
    FORBIDDEN_BLIND_NAMES = {
        "golden_run.json",
        "deterministic_answer_key.json",
        "training_annotation.json",
        "rubric.json",
    }

    def build_blind_package(
        self,
        task_id: str,
        prompt: str,
        deliverable_contract: Dict[str, Any],
        reference_files: List[str | Path],
        output_path: str | Path,
        semantic_contract: Optional[TaskSemanticContract] = None,
    ) -> Dict[str, Any]:
        references = []
        for value in reference_files:
            path = Path(value)
            if path.name in self.FORBIDDEN_BLIND_NAMES:
                raise ValueError(f"Teacher-only artifact cannot enter blind package: {path.name}")
            references.append({"file_name": path.name, "sha256": _sha256_file(path), "path": str(path)})
        payload = {
            "package_version": "v3.semantic_blind_package.1",
            "task_id": task_id,
            "prompt": prompt,
            "deliverable_contract": deliverable_contract,
            "semantic_requirements": [
                {"requirement_id": item.requirement_id, "prompt_text": item.prompt_text}
                for item in (semantic_contract.requirements if semantic_contract else [])
            ],
            "reference_files": references,
            "forbidden_teacher_artifacts": sorted(self.FORBIDDEN_BLIND_NAMES),
        }
        self._write_json(output_path, payload)
        return payload

    def build_teacher_package(
        self,
        task_id: str,
        blind_review_path: str | Path,
        contract_path: str | Path,
        teacher_artifact_paths: Dict[str, str | Path],
        output_path: str | Path,
    ) -> Dict[str, Any]:
        blind_path = Path(blind_review_path)
        payload = {
            "package_version": "v3.semantic_teacher_package.1",
            "task_id": task_id,
            "blind_review": {"path": str(blind_path), "sha256": _sha256_file(blind_path)},
            "semantic_contract": {"path": str(contract_path), "sha256": _sha256_file(Path(contract_path))},
            "teacher_artifacts": {
                name: {"path": str(path), "sha256": _sha256_file(Path(path))}
                for name, path in teacher_artifact_paths.items()
            },
        }
        self._write_json(output_path, payload)
        return payload

    def _write_json(self, path: str | Path, payload: Dict[str, Any]) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_semantic_artifact(path: str | Path, model: BaseModel) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(target)


class SemanticRevisionController:
    MAX_REPAIR_ITERATIONS = 2
    INVALIDATION_MAP = {
        "missing_candidate_input": ["reference_files", "teacher_truth", "training_annotation", "rubric", "verifier", "production_qa"],
        "underdefined_decision_rule": ["reference_files", "task_contract", "teacher_truth", "training_annotation", "rubric", "verifier", "production_qa"],
        "ambiguous_requirement": ["task_contract", "teacher_truth", "training_annotation", "rubric", "verifier", "production_qa"],
        "hidden_assumption_required": ["reference_files", "task_contract", "teacher_truth", "training_annotation", "rubric", "verifier", "production_qa"],
        "teacher_truth_conflict": ["teacher_truth", "training_annotation", "rubric", "verifier", "production_qa"],
        "goldenrun_requirement_gap": ["teacher_truth", "training_annotation", "rubric", "verifier", "production_qa"],
        "rubric_missing_fact_coverage": ["rubric", "verifier", "production_qa"],
        "irrelevant_rubric_criterion": ["rubric", "verifier", "production_qa"],
        "rubric_weight_imbalance": ["rubric", "verifier", "production_qa"],
        "deliverable_contract_mismatch": ["task_contract", "teacher_truth", "training_annotation", "rubric", "verifier", "production_qa"],
    }

    def plan_revision(
        self,
        task_root: str | Path,
        current_iteration: int,
        findings: List[SemanticFinding],
    ) -> Dict[str, Any]:
        if current_iteration >= self.MAX_REPAIR_ITERATIONS:
            return {
                "decision": "blocked",
                "reason": "maximum_semantic_repair_iterations_reached",
                "current_iteration": current_iteration,
                "next_revision_dir": None,
                "invalidated_artifacts": [],
            }
        invalidated: Set[str] = set()
        for finding in findings:
            invalidated.update(self.INVALIDATION_MAP.get(finding.finding_code, []))
        next_iteration = current_iteration + 1
        return {
            "decision": "revision_required",
            "current_iteration": current_iteration,
            "next_iteration": next_iteration,
            "next_revision_dir": str(Path(task_root) / f"revision_{next_iteration:02d}"),
            "invalidated_artifacts": sorted(invalidated),
            "finding_codes": sorted({item.finding_code for item in findings}),
            "in_place_edit_allowed": False,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
