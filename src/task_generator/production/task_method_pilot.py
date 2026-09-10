"""Bounded method research: reusable prompts and evidence checks, not a grader."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from task_generator.core.deliverable_contract import DeliverableContractCompiler, DeliverableContractV1, DeliverableSpecV1
from task_generator.planning.rubric_compiler_v2 import (
    TaskSpecificAtomicRubricV1, TaskSpecificRubricV2, validate_rubric,
)

CASES = [
    {"id": "dev_01", "phase": "development", "seed": "seed_procurement_price_reasonableness", "skill": "procurement-price-reasonableness", "domain": "procurement_operations"},
    {"id": "val_01", "phase": "validation", "seed": "seed_procurement_price_reasonableness", "skill": "procurement-price-reasonableness", "domain": "procurement_operations"},
    {"id": "val_02", "phase": "validation", "seed": "seed_procurement_acceptance_disposition", "skill": "procurement-delivery-acceptance", "domain": "procurement_operations"},
    {"id": "val_03", "phase": "validation", "seed": "seed_audit_company_information_reliability", "skill": "audit-evidence-reliability", "domain": "audit_compliance"},
    {"id": "val_04", "phase": "validation", "seed": "seed_audit_company_information_reliability", "skill": "audit-evidence-reliability", "domain": "audit_compliance"},
]
STAGES = ("generate", "mine", "compile", "review")
DIMENSIONS = ("factual_consistency", "business_provenance", "requirements_and_fairness", "solvability", "professional_complexity")
FORMATS = {"docx", "xlsx", "pdf", "csv", "txt", "json"}

COMMON = """Work exclusively on the supplied inputs under /workspace/inputs.
Do not browse, access other workspaces or authentication, install packages, call
another model, use subagents, or launch background jobs. Use existing Python
openpyxl, python-docx, pypdf, reportlab, Pillow, LibreOffice and Poppler.
Inputs and system root are read-only. Write only /output and /tmp.
Use English for business records and candidate instructions. JSON explanations
may use Chinese. Frozen public sources describe professional methods; they do
not assert that current live regulations have been checked. Do not import any
historical organization, task, answer, score or benchmark content.
No file, row, anomaly, decision or rubric item quotas. Quantity is not quality.
Each session is independent. Do not infer hidden intended answers.
Keep candidate material, teacher supervision and execution evidence separate.
Use exact input-relative file paths for citations (reference_files/name.ext,
candidate_task.md, deliverable_contract.json). Include a page/paragraph, sheet/cell
or line locator and explain what the evidence supports and what it does not.
Write final required artifacts, not just a promise in the final message.
"""

GENERATION = """Construct a new occupational world using the public seed, rules and Skill.
Before creating ANY candidate business record, use one separate tool step to
write /output/hidden/process.md (participants, events, times, record producers,
purposes and source dependencies; no task, rubric or solution). In that step run
python /workspace/tools.py freeze-process /output and wait for PROCESS_FROZEN
before a later tool step creates /output/candidate/. Never revise that process.
Materialize useful business records in /output/candidate/. Do not write a task or
candidate solution. Keep answer labels and factory commentary out of records.
Record real work purposes, versions, dates and dependencies. Shared underlying
sources remain shared even if several documents quote them. Distinguish receipt
from approval, estimates from commitments and stated conditions from proof.
Leave genuine uncertainty when reasonable; do not fabricate missing confirmation
to force a positive decision. Provide enough substantive evidence for analysis
and consequential follow-up, not merely a generic 'insufficient information'.
Make complexity arise from necessary cross-record analysis and professional
judgment. Do not preselect organizations, products, amounts, conflicts or outcomes.
Write hidden/world.md and hidden/manifest.json with records: [{path (relative to
candidate/), producer, business_purpose, source_dependencies: [strings]}]. Every
candidate file must appear once. Read back and check the actual files yourself.
Use /tmp for scripts and scratch files; do not leave scripts in /output.
"""

MINING = """Independently mine one natural task from reference_files/ and public_context.json.
Do not solve it or invent new business facts. A public business goal is a work
purpose, not a mandatory affirmative outcome. A defensible bounded conclusion
may complete the work, but must include analysis and specific useful next steps.
Write /output/task.json with natural_task (boolean), rationale (string).
If false, do not invent a replacement or other required outputs.
If true include title, prompt (work request naming downstream user and purpose),
deliverables ([{file_name, relative_path: 'deliverable_files/<same basename>',
format, creation_mode: 'create'}]), and requirements ([{id, requirement,
basis: [{path, locator, explanation}], expected_work_product}]).
Use docx/xlsx/pdf/csv/txt/json only, choosing outputs by actual work needs.
Do not overprescribe layout, list hidden discrepancies or dictate conclusions.
Make clear that unsupported affirmative conclusions are not required and what
consequential analysis/follow-up a bounded conclusion must contain. Do not claim
the file is complete or all vendors/records comply without visible support.
The controller will compile authoritative submission paths from your deliverables.
The business record paths in citations and prompt start with reference_files/.
"""

COMPILATION = """Reconstruct teacher supervision independently from the frozen task, contract,
reference_files/ and public rules. No hidden world is available. Do not edit inputs
or create a full candidate deliverable. Write /output/supervision.json:
{status: 'compiled' or 'upstream_issue', upstream_issues: [strings],
decisions: [{decision_id, requirement_ids: [task requirement IDs],
supported_judgment, conditional_completion, gaps: [strings],
follow_up: [strings], evidence: [{path, locator, explanation}]}]}.
Ground decisions in candidate-visible evidence. Conditions must say what is
known, what cannot yet be concluded, and the concrete evidence/action needed.
If the upstream task cannot support fair supervision, report upstream_issue and
do not create a rubric. Otherwise also write /output/new_rubric.json matching
rubric_schema.json. Use task_id 'anonymous_task'. Every decision_id must be
covered; optional 'deliverable_structure' is reserved for explicit contract work.
Reuse TaskSpecificRubricV2 semantics: each item has criterion_id, decision_id,
requirement, positive integer max_points, score_boundaries covering EVERY integer
from zero through max_points, requirement_basis [{path,locator,explanation}],
evidence_paths [paths], applicability, acceptable_alternatives and verification.
Each item checks an independently observable result. Shared evidence is allowed;
duplicate credit or repeated penalties for the same result are not. Supportable
conditional completion must have a full-credit path through both judgment and
recommendation; a vague refusal to analyze is not full credit. Specify partial
correct combinations, equivalents and scope without imposing hidden preferences.
All requirement_basis references must be candidate_task.md, the contract or
reference_files/, never public factory rules or teacher supervision. No item quota.
Schema is in inputs/rubric_schema.json. Read it before writing JSON.
"""

REVIEW = """Independently review the actual candidate files, task, supervision and rubric.
This is quality review, NOT grading a Solver. Do not create scores or rewrite
artifacts. Independently check quantities/calculations and scope against the
records. A valid citation or source agreement does not prove professional truth.
Distinguish explicitly specified calculations from judgmental assumptions. Check
what each dated record asserts at its own time and authority level; a condition,
request or intention is not proof of fulfillment. Distinguish uncertainty from
proved defects and explain the evidence needed to resolve disputed claims.
Write /output/review.json:
{decision: 'pass' or 'issue' or 'uncertain', checks: [{dimension, status (same three
values), findings: [{observation, path, locator, limitation}]}],
requirement_coverage: [{requirement_id, status, explanation}],
rubric_coverage: [{criterion_id, status, explanation}], summary: string}.
Include exactly these five dimensions: factual_consistency, business_provenance,
requirements_and_fairness, solvability, professional_complexity. Each has evidence.
Cover every task requirement and rubric item exactly once. For fairness check
candidate-visible basis, overlap, partial credit, conditional full-credit paths,
equivalence, verification scope and supervision consistency. 'pass' overall is
allowed only if all dimensions and coverage rows pass. Professional uncertainty
is allowed within a task, but uncertainty about its quality stays uncertain.
Reference citations use exact input-relative paths, including supervision.json
and new_rubric.json when discussing them. Cite candidate evidence for real facts.
Assess meaningful downstream work and cross-file judgment, not document count.
Do not use a generic conditional conclusion to excuse an empty or broken task.
All professional findings are provisional LLM-proxy, not expert validation.
"""

SOLVE = """Complete the work requested in inputs/candidate_task.md using only the candidate
materials under inputs/reference_files/ and its visible instructions. Do not seek
teacher material or other task results. Produce actual usable files matching the
contract, under /output/deliverable_files/. Verify them with available file tools.
Do not substitute a completion message for files. Do not change the assignment.
"""


def prompts(amendment: str = "") -> dict[str, str]:
    return {stage: COMMON + text + ("\nMethod clarification:\n" + amendment if amendment else "")
            for stage, text in zip((*STAGES, "solve"), (GENERATION, MINING, COMPILATION, REVIEW, SOLVE))}


def reference(root: Path, value: str, *, candidate_only: bool = False, extra_allowed=()) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("unsafe_reference")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("unsafe_reference")
    allowed = {"candidate_task.md", "deliverable_contract.json"} if candidate_only else {
        "candidate_task.md", "deliverable_contract.json", "task.json", "public_context.json",
        "professional_rules.json", "sources.json", "supervision.json", "new_rubric.json"}
    if not candidate_only:
        allowed.update(extra_allowed)
    if not value.startswith("reference_files/") and value not in allowed:
        raise ValueError("reference_not_in_stage_allowlist")
    target = root / value
    if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("reference_missing_or_linked")
    return target


def evidence(root, rows, candidate_only=False):
    if not isinstance(rows, list) or not rows:
        raise ValueError("evidence_required")
    for row in rows:
        reference(root, row["path"], candidate_only=candidate_only)
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in ("locator", "explanation")):
            raise ValueError("evidence_locator_or_explanation_missing")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def task_result(raw: Path, inputs: Path) -> dict:
    task = load(raw / "task.json")
    if type(task.get("natural_task")) is not bool or not isinstance(task.get("rationale"), str):
        raise ValueError("invalid_task_result")
    if not task["natural_task"]:
        return {"status": "no_natural_task"}
    if not task.get("title") or not task.get("prompt") or not task.get("requirements"):
        raise ValueError("task_requirements_missing")
    ids = [r["id"] for r in task["requirements"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_requirement")
    for row in task["requirements"]:
        if not row.get("requirement") or not row.get("expected_work_product"):
            raise ValueError("requirement_product_missing")
        # Mining derives a new assignment from visible business records AND the
        # explicitly supplied public role/trigger. This is not rubric grounding:
        # rubric obligations still require the resulting candidate-visible task.
        for basis in row["basis"]:
            evidence(inputs, [basis], basis.get("path") != "public_context.json")
    specs = [DeliverableSpecV1.model_validate(x) for x in task["deliverables"]]
    if any(s.format not in FORMATS or s.creation_mode != "create" for s in specs):
        raise ValueError("unsupported_deliverable")
    contract = DeliverableContractCompiler().build("anonymous_task", [s.model_dump() for s in specs])
    return {"status": "completed", "contract": contract.model_dump(mode="json"),
            "candidate_task": DeliverableContractCompiler().compile_prompt(task["prompt"], contract)}


def editor_result(raw: Path, inputs: Path, *, quality_diagnostics_version=None) -> dict:
    """Validate an edited candidate task without granting access to teacher data."""
    result = task_result(raw, inputs)
    if result["status"] != "completed":
        raise ValueError("editor_cannot_remove_natural_task")
    source = load(inputs / "task.json")
    edited = load(raw / "task.json")
    record = load(raw / "edit_record.json")
    import hashlib
    canonical = lambda value: hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    if record.get("version") != "r10.candidate_edit.1":
        raise ValueError("edit_record.json.version: expected r10.candidate_edit.1")
    if record.get("source_task_sha256") != canonical(source):
        raise ValueError("edit_record.json.source_task_sha256: source task identity mismatch")
    if record.get("edited_task_sha256") != canonical(edited):
        raise ValueError("edit_record.json.edited_task_sha256: edited task identity mismatch")
    changes = record.get("changes")
    if not isinstance(changes, list):
        raise ValueError("edit_record.json.changes: expected an array")
    changed = canonical(source) != canonical(edited)
    if changed != bool(changes):
        raise ValueError("edit_record.json.changes: must match the actual task change")
    if not changed and not str(record.get("no_change_reason", "")).strip():
        raise ValueError("edit_record.json.no_change_reason: required when task is unchanged")
    seen = set()
    for index, row in enumerate(changes):
        location = f"edit_record.json.changes[{index}]"
        required = ("change_id", "area", "original_locator", "edit_summary",
                    "business_reason", "preserved_evidence", "returned_judgment")
        if not isinstance(row, dict) or any(not row.get(key) for key in required):
            raise ValueError(location + ": incomplete edit record")
        if row["change_id"] in seen or row["area"] not in {"prompt", "requirements", "deliverables", "metadata"}:
            raise ValueError(location + ": duplicate ID or invalid area")
        seen.add(row["change_id"])
        evidence(inputs, row["preserved_evidence"], True)
    outcome = {**result, "edited": changed, "change_count": len(changes)}
    if quality_diagnostics_version is not None:
        if str(quality_diagnostics_version) != "1":
            raise ValueError("unsupported_quality_diagnostics_version")
        unexpected = {path.relative_to(raw).as_posix() for path in raw.rglob("*") if path.is_file()} - {
            "task.json", "edit_record.json"}
        if unexpected:
            raise ValueError("candidate_editor_cannot_modify_materials_or_add_outputs:" + ",".join(sorted(unexpected)))
        from task_generator.production.quality_diagnostics import edit_difference, validate_edit_claims
        source_result = task_result(inputs, inputs)
        diagnostic = edit_difference(source, edited, source_result, result)
        validate_edit_claims(record, diagnostic)
        outcome["edit_diagnostic"] = diagnostic
    return outcome


def compilation_result(raw: Path, inputs: Path) -> dict:
    supervision = load(raw / "supervision.json")
    if supervision.get("status") == "upstream_issue" and supervision.get("upstream_issues"):
        return {"status": "upstream_issue", "issues": supervision["upstream_issues"]}
    if supervision.get("status") != "compiled":
        raise ValueError("supervision.json.status: invalid_supervision; expected compiled, or upstream_issue with nonempty upstream_issues")
    if supervision.get("upstream_issues"):
        raise ValueError("supervision.json.upstream_issues: invalid_supervision; expected empty issues when compiled")
    if not supervision.get("decisions"):
        raise ValueError("supervision.json.decisions: invalid_supervision; expected nonempty decisions when compiled")
    decisions = supervision["decisions"]
    ids = [r["decision_id"] for r in decisions]
    requirements = {r["id"] for r in load(inputs / "task.json")["requirements"]}
    if len(ids) != len(set(ids)) or set().union(*(set(r["requirement_ids"]) for r in decisions)) != requirements:
        raise ValueError("supervision_requirement_coverage")
    for row in decisions:
        if not row.get("supported_judgment") or not row.get("conditional_completion") or not isinstance(row.get("gaps"), list) or not isinstance(row.get("follow_up"), list):
            raise ValueError("supervision_completion_missing")
        evidence(inputs, row["evidence"], True)
    rubric = TaskSpecificRubricV2.model_validate(load(raw / "new_rubric.json"))
    if rubric.task_id != "anonymous_task":
        raise ValueError("rubric_task_identity")
    # The existing validator needs decision identifiers, not historical quantity limits.
    matrix = SimpleNamespace(decision_points=[SimpleNamespace(decision_id=x) for x in ids])
    validate_rubric(rubric, matrix, inputs)
    return {"status": "completed", "total_rubric_points": rubric.total_points}


def atomic_compilation_result(raw: Path, inputs: Path) -> dict:
    """Validate reference supervision and the sole, binary atomic rubric."""
    supervision = load(raw / "supervision.json")
    if supervision.get("status") == "upstream_issue" and supervision.get("upstream_issues"):
        return {"status": "upstream_issue", "issues": supervision["upstream_issues"]}
    if supervision.get("status") != "compiled" or supervision.get("upstream_issues"):
        raise ValueError("supervision.json.status: invalid atomic supervision")
    decisions = supervision.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ValueError("supervision.json.decisions: expected nonempty decisions")
    ids = [row.get("decision_id") for row in decisions]
    requirements = {row["id"] for row in load(inputs / "task.json")["requirements"]}
    covered = set()
    for index, row in enumerate(decisions):
        required = ("decision_id", "requirement_ids", "reference_analysis", "known_facts",
                    "uncertainties", "follow_up", "evidence")
        if any(key not in row for key in required):
            raise ValueError(f"supervision.json.decisions[{index}]: reference fields missing")
        if "conditional_completion" in row or "score_boundaries" in row:
            raise ValueError(f"supervision.json.decisions[{index}]: scoring semantics belong only in new_rubric.json")
        if not row["reference_analysis"] or not isinstance(row["known_facts"], list) \
                or not isinstance(row["uncertainties"], list) or not isinstance(row["follow_up"], list):
            raise ValueError(f"supervision.json.decisions[{index}]: invalid reference analysis")
        if not isinstance(row["requirement_ids"], list):
            raise ValueError(f"supervision.json.decisions[{index}].requirement_ids: expected array")
        unknown = set(row["requirement_ids"]) - requirements
        if unknown:
            raise ValueError(f"supervision.json.decisions[{index}].requirement_ids: unknown IDs {sorted(unknown)}")
        covered.update(row["requirement_ids"])
        evidence(inputs, row["evidence"], True)
    if len(ids) != len(set(ids)) or covered != requirements:
        raise ValueError("supervision_requirement_coverage")
    rubric = TaskSpecificAtomicRubricV1.model_validate(load(raw / "new_rubric.json"))
    if rubric.task_id != "anonymous_task":
        raise ValueError("rubric_task_identity")
    matrix = SimpleNamespace(decision_points=[SimpleNamespace(decision_id=value) for value in ids])
    validate_rubric(rubric, matrix, inputs)
    return {"status": "completed", "total_rubric_points": rubric.total_points,
            "scoring": "binary_weighted"}


def review_result(raw: Path, inputs: Path, *, extra_allowed=()) -> dict:
    review = load(raw / "review.json")
    if sorted(r["dimension"] for r in review["checks"]) != sorted(DIMENSIONS):
        raise ValueError("review_dimensions")
    states = []
    for row in review["checks"]:
        states.append(row["status"])
        if not row.get("findings"):
            raise ValueError("review_evidence_missing")
        for f in row["findings"]:
            reference(inputs, f["path"], extra_allowed=extra_allowed)
            if not all(isinstance(f.get(k), str) and f[k].strip() for k in ("observation", "locator", "limitation")):
                raise ValueError("review_evidence_incomplete")
    for key, expected, field in (
        ("requirement_coverage", {r["id"] for r in load(inputs / "task.json")["requirements"]}, "requirement_id"),
        ("rubric_coverage", {r["criterion_id"] for r in load(inputs / "new_rubric.json")["criteria"]}, "criterion_id"),
    ):
        ids = [r[field] for r in review[key]]
        if len(ids) != len(set(ids)) or set(ids) != expected:
            raise ValueError("review_coverage_incomplete")
        states.extend(r["status"] for r in review[key])
        if any(not r.get("explanation") for r in review[key]):
            raise ValueError("review_coverage_explanation_missing")
    if any(s not in {"pass", "issue", "uncertain"} for s in states) or review.get("decision") not in {"pass", "issue", "uncertain"}:
        raise ValueError("review_state_invalid")
    if (review["decision"] == "pass") != all(s == "pass" for s in states):
        raise ValueError("review_decision_mismatch")
    return {"status": "completed", "quality": review["decision"], "professional_status": "provisional/LLM-proxy"}


def select_trials(cases):
    selected = []
    for domain in ("procurement_operations", "audit_compliance"):
        for spec in CASES[1:]:
            result = cases.get(spec["id"], {})
            if spec["domain"] == domain and result.get("quality") == "pass" and result.get("status") == "completed":
                selected.append(spec["id"])
                break
    return selected
