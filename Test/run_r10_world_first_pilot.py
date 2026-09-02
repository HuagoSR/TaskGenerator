"""Run the bounded R10.9 World-First / Task-Mining experiment.

This is deliberately a campaign harness rather than a reusable agent
framework.  Semantic outputs live under ignored artifacts; the reusable code
is limited to contracts, state transitions and hard isolation checks.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from task_generator.core.deliverable_contract import DeliverableContractV1, DeliverableSpecV1
from task_generator.core.scenario_first import ProfessionalRuleSetV1, WorkSeedV1
from task_generator.evaluation.r10_behavioral import binding_from_task, inspect_delivery, sha256_file, sha256_json
from task_generator.planning.scenario_task_compiler import (
    TaskCompilationOutputV1,
    TaskSpecificRubricV1,
    productive_workload_rubric_errors,
    tree_sha256,
)
from task_generator.production.campaign import atomic_json
from task_generator.production.r10_world_first import (
    PairedJudgeReviewV1,
    ProfessionDifficultyPlanV1,
    WorldFirstCaseStateV1,
    WorldFirstPilotManifestV1,
    judge_calibration_errors,
    paired_task_discrimination,
    recompute_paired_review,
    validate_world_candidate_tree,
    write_manifest,
)
from run_r10_behavioral_pilot import (
    CHATGPT_CODEX_STACK,
    DEEPSEEK_OPENCODE_STACK,
    _codex_turn_completed,
    _execute_solver,
    _is_codex_stack,
    _run_remote,
)


IMAGE = "taskgenerator-eval:milestone-r9-huago-cone-a2d8a5e35099"
IMAGE_SHA256 = "3c6c76324780a911ff7b47bf52629280b4f2a49f26248540de049a61b9129363"
CODEX_AUTH_DIR = "/home/huagosr/taskgenerator-secrets/codex-auth-current"
REMOTE_HOME = "/home/huagosr"
STACKS = (CHATGPT_CODEX_STACK, DEEPSEEK_OPENCODE_STACK)
SEED_IDS = {
    "audit_compliance": "seed_audit_company_information_reliability",
    "procurement_operations": "seed_procurement_price_reasonableness",
}
RULE_SET_IDS = {
    "audit_compliance": "r10_rules_audit_evidence_and_deficiency",
    "procurement_operations": "r10_rules_procurement_award_and_acceptance",
}
SKILLS = {
    "audit_compliance": "audit-evidence-reliability",
    "procurement_operations": "procurement-price-reasonableness",
}
FORMATS = {"audit_compliance": "xlsx", "procurement_operations": "docx"}
CASE_IDS = {
    ("audit_compliance", "baseline"): "r10_9_audit_reliability_baseline",
    ("audit_compliance", "adversarial"): "r10_9_audit_reliability_adversarial",
    ("procurement_operations", "baseline"): "r10_9_procurement_price_baseline",
    ("procurement_operations", "adversarial"): "r10_9_procurement_price_adversarial",
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    atomic_json(path, payload)


def _copy(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        capture_output=True, check=True,
    ).stdout.strip()


def _canonical(value: Any) -> str:
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return sha256_json(payload)


def _load_inputs() -> dict[str, dict[str, Any]]:
    seed_rows = json.loads((ROOT / "data/r10/work_seeds/candidate_work_seeds.json").read_text(encoding="utf-8"))
    rules_rows = json.loads((ROOT / "data/r10/work_seeds/professional_rule_sets.json").read_text(encoding="utf-8"))
    seeds = {
        row["seed"]["domain"]: WorkSeedV1.model_validate(row["seed"])
        for row in seed_rows if row.get("status") == "admitted" and row["seed"]["seed_id"] in set(SEED_IDS.values())
    }
    rules = {
        row["domain"]: ProfessionalRuleSetV1.model_validate(row)
        for row in rules_rows if row["rule_set_id"] in set(RULE_SET_IDS.values())
    }
    if set(seeds) != set(SEED_IDS) or set(rules) != set(RULE_SET_IDS):
        raise ValueError("world_first_public_inputs_incomplete")
    result: dict[str, dict[str, Any]] = {}
    for domain in SEED_IDS:
        skill_root = ROOT / ".agents/skills/r10" / SKILLS[domain]
        skill = skill_root / "SKILL.md"
        source_map = skill_root / "references/source-map.md"
        if not (skill.is_file() and source_map.is_file()):
            raise ValueError("world_first_skill_package_incomplete")
        source_ids = sorted(set(re.findall(r"`([a-z][a-z0-9_]+)`", source_map.read_text(encoding="utf-8"))))
        source_ids.extend(
            ref.source_id for rule in rules[domain].rules for ref in rule.source_refs
            if ref.source_id not in source_ids
        )
        result[domain] = {
            "seed": seeds[domain], "rules": rules[domain], "skill": skill,
            "source_map": source_map, "source_ids": sorted(set(source_ids)),
        }
    return result


def _initial_manifest(run_id: str, inputs: dict[str, dict[str, Any]]) -> WorldFirstPilotManifestV1:
    cases: list[WorldFirstCaseStateV1] = []
    for domain in SEED_IDS:
        for variant in ("baseline", "adversarial"):
            cases.append(WorldFirstCaseStateV1(
                case_id=CASE_IDS[(domain, variant)], pair_id=f"r10_9_{domain}_pair",
                domain=domain, variant=variant, deliverable_format=FORMATS[domain],
                seed_sha256=_canonical(inputs[domain]["seed"]),
                rules_sha256=_canonical(inputs[domain]["rules"]),
                skill_sha256=sha256_file(inputs[domain]["skill"]),
            ))
    return WorldFirstPilotManifestV1(
        campaign_id=run_id, source_commit=_git_head(), image=IMAGE,
        image_sha256=IMAGE_SHA256, cases=cases,
    )


def _scope(run_id: str, inputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    manifest = _initial_manifest(run_id, inputs)
    return {
        "scope_version": "r10.world_first_scope.1", "campaign_id": run_id,
        "source_commit": manifest.source_commit, "image": IMAGE,
        "image_sha256": IMAGE_SHA256, "codex_version": "0.149.1",
        "opencode_version": "1.17.13", "sol_model": "gpt-5.6-sol",
        "deepseek_model": "deepseek-v4-pro", "cases": [item.model_dump(mode="json") for item in manifest.cases],
        "authorized_uploads": ["public_seed", "professional_rules", "professional_skill", "campaign_generated_private_artifacts"],
        "excluded_actions": ["historical_task_reuse", "gdpval_content_generation_input", "training", "public_release", "registry_mutation"],
        "session_retry_policy": "one semantic attempt; one identical-input repair only for transport or invalid structure",
    }


def _persist_stage(
    run_root: Path, manifest: WorldFirstPilotManifestV1, *, stage: str,
    plans: dict[str, ProfessionDifficultyPlanV1] | None = None,
    worlds: dict[str, Path] | None = None, packages: dict[str, Path] | None = None,
    calibration: bool = False, decision: str | None = None,
) -> WorldFirstPilotManifestV1:
    cases: list[WorldFirstCaseStateV1] = []
    for item in manifest.cases:
        updates: dict[str, Any] = {"stage": stage}
        if plans and item.variant == "adversarial":
            updates["difficulty_plan_sha256"] = _canonical(plans[item.domain])
        if worlds:
            world = worlds[item.case_id]
            updates.update({
                "world_tree_sha256": tree_sha256(world),
                "candidate_tree_sha256": tree_sha256(world / "candidate"),
            })
        if packages:
            package = packages[item.case_id]
            updates.update({
                "task_tree_sha256": tree_sha256(package),
                "teacher_tree_sha256": tree_sha256(package / "teacher"),
            })
        if calibration:
            updates["calibration_tree_sha256"] = tree_sha256(run_root / "calibration")
        cases.append(item.model_copy(update=updates))
    result = manifest.model_copy(update={
        "cases": cases, **({"decision": decision} if decision else {}),
    })
    write_manifest(run_root / "manifest.json", result)
    return result


def _remote_root(run_id: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", run_id):
        raise ValueError("world_first_run_id_invalid")
    return f"{REMOTE_HOME}/taskgenerator-data/r10-world-first/{run_id}"


def _session(
    *, run_root: Path, run_id: str, assignment_id: str, stack: str,
    prompt: str, stage_inputs: Callable[[Path], None], timeout_seconds: int = 1800,
) -> Path:
    session_root = run_root / "sessions" / assignment_id
    if session_root.exists():
        state_path = session_root / "state.json"
        state = _json(state_path) if state_path.is_file() else {}
        output = session_root / "workspace/deliverable_files"
        if state.get("status") == "completed" and output.is_dir():
            return output
        raise FileExistsError(f"world_first_session_started_but_not_reusable:{assignment_id}")
    workspace = session_root / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "deliverable_files").mkdir()
    stage_inputs(workspace)
    (workspace / "TASK.md").write_text(prompt, encoding="utf-8")
    _write(session_root / "state.json", {
        "assignment_id": assignment_id, "status": "running", "stack": stack,
        "started_at": _now(), "input_tree_sha256": tree_sha256(workspace),
    })
    started = time.monotonic()
    code, stdout, stderr = _run_remote(
        host="huago-cone", remote=f"{_remote_root(run_id)}/{assignment_id}",
        local=workspace, stack=stack, image=IMAGE, codex_auth_dir=CODEX_AUTH_DIR,
        timeout_seconds=timeout_seconds,
    )
    completed = _codex_turn_completed(workspace / "agent.jsonl") if _is_codex_stack(stack) else code == 0
    state = {
        "assignment_id": assignment_id, "status": "completed" if code == 0 and completed else "incomplete",
        "stack": stack, "returncode": code, "turn_completed": completed,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": stdout[-2000:], "stderr_tail": stderr[-3000:], "finished_at": _now(),
    }
    _write(session_root / "state.json", state)
    if state["status"] != "completed":
        raise RuntimeError(f"world_first_agent_incomplete:{assignment_id}:{code}")
    output = workspace / "deliverable_files"
    if not output.is_dir() or not any(path.is_file() for path in output.rglob("*")):
        raise RuntimeError(f"world_first_agent_output_missing:{assignment_id}")
    return output


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_relative_path(value: object) -> str:
    path = str(value or "").replace("\\", "/").removeprefix("./")
    for prefix in ("inputs/candidate/", "candidate/", "reference_files/"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def _stage_public_inputs(workspace: Path, domain_input: dict[str, Any]) -> None:
    target = workspace / "inputs"
    target.mkdir()
    _write(target / "work_seed.json", domain_input["seed"])
    _write(target / "professional_rules.json", domain_input["rules"])
    _copy(domain_input["skill"], target / "current_skill.md")
    _copy(domain_input["source_map"], target / "source_map.md")


def _run_debate(run_root: Path, run_id: str, inputs: dict[str, dict[str, Any]]) -> dict[str, ProfessionDifficultyPlanV1]:
    plans: dict[str, ProfessionDifficultyPlanV1] = {}
    for domain, item in inputs.items():
        prefix = "audit" if domain == "audit_compliance" else "procurement"
        author = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{prefix}_skill_author",
            stack=CHATGPT_CODEX_STACK, stage_inputs=lambda workspace, item=item: _stage_public_inputs(workspace, item),
            prompt="""Act as an occupational Skill author. Read inputs/. Strengthen the professional Skill as a concise workplace-review guide grounded only in the supplied public sources. Focus on roles, naturally produced evidence, judgment boundaries, and serious shortcuts. Do not invent a company, case, task answer, file template, fixed field list, puzzle, or generic office-tool instructions. You may consult only official PCAOB or Acquisition.gov/DAU pages when a locator needs verification. Write deliverable_files/skill_draft.md and deliverable_files/author_notes.json. The notes must list source IDs and explain what changed. Do not create a task, answer, rubric, or scenario.""",
        )
        challenger = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{prefix}_difficulty_challenger",
            stack=DEEPSEEK_OPENCODE_STACK,
            stage_inputs=lambda workspace, item=item, author=author: (
                _stage_public_inputs(workspace, item), _copy(author / "skill_draft.md", workspace / "inputs/skill_draft.md")
            ),
            prompt="""Act as a professional difficulty challenger. Read inputs/. Propose 3–5 source-grounded difficulties that arise naturally in this job and could expose model shortcuts. Each must describe professional cause, business event, candidate-evidence effect, targeted shortcut, source IDs, fairness, and solvability. Reject label leakage, hidden passwords, broken formats, guessing, and arbitrary traps. Write only deliverable_files/challenge.json. Do not create a case, task, answer, rubric, or files.""",
        )
        defender = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{prefix}_realism_defender",
            stack=CHATGPT_CODEX_STACK,
            stage_inputs=lambda workspace, item=item, author=author, challenger=challenger: (
                _stage_public_inputs(workspace, item),
                _copy(author / "skill_draft.md", workspace / "inputs/skill_draft.md"),
                _copy(challenger / "challenge.json", workspace / "inputs/challenge.json"),
            ),
            prompt="""Act as realism and solvability defender. Review every proposed difficulty against the Work Seed, Rules, Skill and public source map. Keep only occupationally natural changes with visible evidence and a defensible uncertain conclusion when evidence is incomplete. Remove exam tricks, unsupported facts, answer labels and mutually incompatible changes. Write deliverable_files/defense.json with accepted/rejected items and file-level reasoning. Do not generate a scenario or task.""",
        )
        schema = ProfessionDifficultyPlanV1.model_json_schema()
        owner = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{prefix}_task_owner",
            stack=DEEPSEEK_OPENCODE_STACK,
            stage_inputs=lambda workspace, item=item, author=author, challenger=challenger, defender=defender: (
                _stage_public_inputs(workspace, item),
                _copy(author / "skill_draft.md", workspace / "inputs/skill_draft.md"),
                _copy(challenger / "challenge.json", workspace / "inputs/challenge.json"),
                _copy(defender / "defense.json", workspace / "inputs/defense.json"),
                _write(workspace / "inputs/difficulty_schema.json", schema),
            ),
            prompt=f"""Act as Task Owner. Select at most two mutually compatible, source-grounded difficulties from inputs/defense.json. Preserve the job's ordinary workflow and make the strengthened world harder through business facts and evidence relations, never formatting friction. Write exactly deliverable_files/difficulty_plan.json matching inputs/difficulty_schema.json. Use domain {domain}, seed_id {item['seed'].seed_id}, skill_id r10.{SKILLS[domain]}, and only these available_source_ids: {json.dumps(item['source_ids'])}. Do not create a scenario, task, answer or rubric.""",
        )
        plan = ProfessionDifficultyPlanV1.model_validate(_json(owner / "difficulty_plan.json"))
        plans[domain] = plan
        _write(run_root / "difficulty" / f"{domain}.json", plan)
        shutil.copy2(author / "skill_draft.md", run_root / "difficulty" / f"{domain}_skill_draft.md")
    return plans


def _world_prompt(*, domain: str, variant: str, case_id: str) -> str:
    format_hint = "The professional deliverable later will be an XLSX audit workpaper." if domain == "audit_compliance" else "The professional deliverable later will be a DOCX price-analysis memorandum."
    variant_hint = (
        "Create the ordinary baseline world from the public seed, rules and draft Skill."
        if variant == "baseline" else
        "Copy the supplied baseline world faithfully, then apply only the selected difficulty mutations through plausible business events and changed raw records. Preserve organization, role, core trigger and later deliverable type."
    )
    return f"""Act as a workplace evidence author. {variant_hint} {format_hint}

At this stage there is no question, expected answer, rubric or deliverable contract. Generate a complete work world made of records that different people or systems would naturally produce before a professional analyses them. Include normal volume, redundant and irrelevant-but-plausible information, provenance/time/version clues, and at least two cross-file evidence relationships. Do not make every record relevant. Do not summarize the hidden issues in candidate files. Do not use labels such as Questionable, Exception, Requires Follow-Up, correct treatment, red flag or answer.

Create only:
- deliverable_files/world/candidate/ with natural XLSX/DOCX/PDF/CSV/TXT business records;
- deliverable_files/world/teacher/world_ledger.md describing the authoritative facts, chronology and unresolved limits;
- deliverable_files/world/world_manifest.json with case_id `{case_id}`, an `artifacts` list (path, producer, system, purpose), and at least two `cross_file_relationships` (paths plus relationship).

Do not create TASK.md, a prompt, answer, rubric, decision matrix or delivery file. Reopen every office file before finishing."""


def _validate_world(root: Path, *, case_id: str) -> None:
    candidate = root / "candidate"
    errors = validate_world_candidate_tree(candidate)
    ledger = root / "teacher/world_ledger.md"
    manifest_path = root / "world_manifest.json"
    if not ledger.is_file() or ledger.stat().st_size < 200:
        errors.append("world_ledger_missing_or_thin")
    if not manifest_path.is_file():
        errors.append("world_manifest_missing")
    else:
        value = _json(manifest_path)
        if value.get("case_id") != case_id:
            errors.append("world_manifest_case_mismatch")
        def candidate_relative(value: object) -> str | None:
            path = str(value or "").replace("\\", "/").removeprefix("./")
            if path.startswith("candidate/"):
                path = path[len("candidate/"):]
            if path.startswith("teacher/") or path == "teacher":
                return None
            return path

        actual = {path.relative_to(candidate).as_posix() for path in candidate.rglob("*") if path.is_file()}
        declared = {
            normalized for item in value.get("artifacts", [])
            if (normalized := candidate_relative(item.get("path"))) is not None
        }
        if actual != declared:
            errors.append("world_manifest_candidate_coverage_invalid")
        relationships = value.get("cross_file_relationships", [])
        if len(relationships) < 2 or any(len(set(item.get("paths", []))) < 2 for item in relationships):
            errors.append("world_cross_file_relationships_insufficient")
        normalized_relationships = [
            {normalized for path in item.get("paths", []) if (normalized := candidate_relative(path)) is not None}
            for item in relationships
        ]
        if any(len(paths) < 2 or not paths <= actual for paths in normalized_relationships):
            errors.append("world_relationship_path_unknown")
    if errors:
        raise ValueError(";".join(sorted(set(errors))))


def _run_worlds(
    run_root: Path, run_id: str, inputs: dict[str, dict[str, Any]],
    plans: dict[str, ProfessionDifficultyPlanV1],
) -> dict[str, Path]:
    worlds: dict[str, Path] = {}
    for domain, item in inputs.items():
        prefix = "audit" if domain == "audit_compliance" else "procurement"
        baseline_id = CASE_IDS[(domain, "baseline")]
        baseline = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{prefix}_baseline_world",
            stack=CHATGPT_CODEX_STACK,
            stage_inputs=lambda workspace, item=item: _stage_public_inputs(workspace, item),
            prompt=_world_prompt(domain=domain, variant="baseline", case_id=baseline_id),
        ) / "world"
        _validate_world(baseline, case_id=baseline_id)
        worlds[baseline_id] = baseline
        adversarial_id = CASE_IDS[(domain, "adversarial")]
        adversarial = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{prefix}_adversarial_world",
            stack=CHATGPT_CODEX_STACK,
            stage_inputs=lambda workspace, item=item, baseline=baseline, plan=plans[domain]: (
                _stage_public_inputs(workspace, item), _copy(baseline, workspace / "inputs/baseline_world"),
                _write(workspace / "inputs/difficulty_plan.json", plan),
            ),
            prompt=_world_prompt(domain=domain, variant="adversarial", case_id=adversarial_id),
        ) / "world"
        _validate_world(adversarial, case_id=adversarial_id)
        worlds[adversarial_id] = adversarial
    return worlds


def _mine_tasks(
    run_root: Path, run_id: str, inputs: dict[str, dict[str, Any]], worlds: dict[str, Path],
) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for (domain, variant), case_id in CASE_IDS.items():
        seed = inputs[domain]["seed"]
        output = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{case_id}_task_miner",
            stack=DEEPSEEK_OPENCODE_STACK,
            stage_inputs=lambda workspace, seed=seed, world=worlds[case_id]: (
                _write(workspace / "inputs/public_context.json", {
                    "role": seed.role, "trigger_event": seed.trigger_event,
                    "business_goal": seed.business_goal, "audience": seed.audience,
                }),
                _copy(world / "candidate", workspace / "inputs/candidate"),
            ),
            prompt=f"""Act as an independent Task Miner. You can see only raw candidate business records and a public role/trigger context. Do not infer hidden condition identities or invent a predetermined answer. Decide whether a real {seed.role} would naturally receive one substantial task now. If not, write task.json with natural=false and explain why. If yes, write deliverable_files/task.json with: natural=true, task_id=`{case_id}_task`, title, role, trigger, audience, business_use, base_prompt, deliverable_format=`{FORMATS[domain]}`, deliverable_file_name, evidence_paths, and natural_task_rationale. The prompt must request a workplace product, not enumerate hidden anomalies or rubric points. It must refer only to visible candidate files. Do not read or produce teacher truth, a rubric or answer.""",
        )
        value = _json(output / "task.json")
        if value.get("natural") is not True:
            raise ValueError(f"world_first_task_not_natural:{case_id}")
        if value.get("deliverable_format") != FORMATS[domain]:
            raise ValueError(f"world_first_task_format_invalid:{case_id}")
        actual = {path.relative_to(worlds[case_id] / "candidate").as_posix() for path in (worlds[case_id] / "candidate").rglob("*") if path.is_file()}
        normalized_evidence = [_candidate_relative_path(path) for path in value.get("evidence_paths", [])]
        if not set(normalized_evidence) <= actual:
            raise ValueError(f"world_first_task_evidence_path_unknown:{case_id}")
        value["evidence_paths"] = normalized_evidence
        value["base_prompt"] = str(value["base_prompt"]).replace("inputs/candidate/", "reference_files/")
        tasks[case_id] = value
        _write(run_root / "mined_tasks" / f"{case_id}.json", value)
    return tasks


def _truth_prompt(case_id: str, task: dict[str, Any], skill_id: str) -> str:
    return f"""Act as an independent professional Truth Reconstructor. Read the frozen candidate records, mined_task.json, public Professional Rules and Skill. You cannot see a hidden world ledger or difficulty identity. Reconstruct only conclusions supportable from candidate-visible evidence, preserving conditional or unresolved conclusions where evidence is insufficient.

Write deliverable_files/compilation_output.json matching compilation_schema.json. It must contain the exact base_prompt from mined_task.json, 3–5 aligned teacher_truth points, decision_matrix points and task_specific_rubric criteria. In decision_matrix evidence_refs, use artifact_id as the exact candidate-relative path, record_id as a visible record/section locator, and field_names as visible fields. Use rule IDs from professional_rules.json and skill ID `{skill_id}`. Every rubric description must explicitly define `Met:`, `Partial:`, and `Not met:`. A major error must be specific and professional; presentation quality cannot offset it. Do not add facts that candidate files cannot support.

Also write deliverable_files/reconstructed_facts.json as a JSON object mapping each fact_id used in teacher_truth to a concise candidate-supported statement and its evidence_paths. Task ID is `{case_id}_task`. Do not write a candidate answer."""


def _make_contract(case_id: str, task: dict[str, Any]) -> DeliverableContractV1:
    suffix = ".xlsx" if task["deliverable_format"] == "xlsx" else ".docx"
    name = Path(str(task.get("deliverable_file_name", ""))).name
    if Path(name).suffix.casefold() != suffix:
        name = "audit_workpaper.xlsx" if suffix == ".xlsx" else "price_analysis_memo.docx"
    return DeliverableContractV1(
        case_id=f"{case_id}_task",
        deliverables=[DeliverableSpecV1(
            file_name=name, relative_path=f"deliverable_files/{name}",
            format=task["deliverable_format"], creation_mode="create",
        )],
    )


def _compile_tasks(
    run_root: Path, run_id: str, inputs: dict[str, dict[str, Any]],
    worlds: dict[str, Path], tasks: dict[str, dict[str, Any]],
) -> dict[str, Path]:
    packages: dict[str, Path] = {}
    for (domain, _variant), case_id in CASE_IDS.items():
        item = inputs[domain]
        schema = TaskCompilationOutputV1.model_json_schema()
        output = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{case_id}_truth_reconstructor",
            stack=CHATGPT_CODEX_STACK,
            stage_inputs=lambda workspace, item=item, world=worlds[case_id], task=tasks[case_id]: (
                _copy(world / "candidate", workspace / "inputs/candidate"),
                _write(workspace / "inputs/mined_task.json", task),
                _write(workspace / "inputs/professional_rules.json", item["rules"]),
                _copy(item["skill"], workspace / "inputs/professional_skill.md"),
                _write(workspace / "inputs/compilation_schema.json", schema),
            ),
            prompt=_truth_prompt(case_id, tasks[case_id], f"r10.{SKILLS[domain]}"),
        )
        compilation = TaskCompilationOutputV1.model_validate(_json(output / "compilation_output.json"))
        if compilation.base_prompt.strip() != str(tasks[case_id]["base_prompt"]).strip():
            raise ValueError(f"world_first_prompt_drift:{case_id}")
        rubric_errors = productive_workload_rubric_errors(compilation)
        if rubric_errors:
            raise ValueError(f"world_first_rubric_boundary_invalid:{case_id}:{rubric_errors}")
        facts = _json(output / "reconstructed_facts.json")
        used_facts = {fact for point in compilation.teacher_truth for fact in point.fact_ids}
        if set(facts) != used_facts:
            raise ValueError(f"world_first_reconstructed_fact_closure_invalid:{case_id}")
        candidate_paths = {path.relative_to(worlds[case_id] / "candidate").as_posix() for path in (worlds[case_id] / "candidate").rglob("*") if path.is_file()}
        evidence_paths = {path for point in compilation.teacher_truth for path in point.evidence_paths}
        artifact_ids = {ref.artifact_id for point in compilation.decision_matrix.decision_points for ref in point.evidence_refs}
        if not evidence_paths <= candidate_paths or not artifact_ids <= candidate_paths:
            raise ValueError(f"world_first_teacher_evidence_path_unknown:{case_id}")
        contract = _make_contract(case_id, tasks[case_id])
        expected = contract.deliverables[0].relative_path
        prompt = compilation.base_prompt.rstrip() + f"\n\nSubmit exactly one final deliverable at `{expected}`.\n"
        package = run_root / "tasks" / f"{case_id}_task"
        package.mkdir(parents=True)
        (package / "TASK.md").write_text(prompt, encoding="utf-8")
        _write(package / "deliverable_contract.json", contract)
        shutil.copytree(worlds[case_id] / "candidate", package / "reference_files")
        teacher = package / "teacher"
        teacher.mkdir()
        _write(teacher / "teacher_truth.json", compilation.teacher_truth)
        _write(teacher / "decision_matrix.json", compilation.decision_matrix)
        _write(teacher / "task_specific_rubric.json", compilation.task_specific_rubric)
        _write(teacher / "reconstructed_facts.json", facts)
        _write(package / "task_manifest.json", {
            "task_id": f"{case_id}_task", "case_id": case_id,
            "variant": next(variant for (_domain, variant), cid in CASE_IDS.items() if cid == case_id),
            "candidate_tree_sha256": tree_sha256(package / "reference_files"),
            "task_compilation_sha256": _canonical(compilation),
            "source_commit": _git_head(),
        })
        packages[case_id] = package
    return packages


def _truth_audit(
    run_root: Path, run_id: str, worlds: dict[str, Path], packages: dict[str, Path],
) -> None:
    def stage(workspace: Path) -> None:
        for case_id in CASE_IDS.values():
            target = workspace / "inputs/cases" / case_id
            _copy(worlds[case_id] / "teacher/world_ledger.md", target / "world_ledger.md")
            _copy(worlds[case_id] / "candidate", target / "candidate")
            _copy(packages[case_id] / "TASK.md", target / "TASK.md")
            _copy(packages[case_id] / "teacher", target / "teacher")
    output = _session(
        run_root=run_root, run_id=run_id, assignment_id="independent_truth_audit",
        stack=DEEPSEEK_OPENCODE_STACK, stage_inputs=stage,
        prompt="""Independently audit all four cases in inputs/cases. Compare each reconstructed teacher truth and decision matrix with its hidden world ledger and candidate-visible evidence. Fail any preset-answer dependence, unsupported definite fact, missing visible evidence, answer leakage, contradictory truth, or task that cannot be solved with an appropriately conditional conclusion. Write deliverable_files/truth_audit.json with `cases`, each containing case_id, decision (`pass` or `blocked`), and concrete findings. This is an audit, not a rewrite; do not modify any input.""",
    )
    value = _json(output / "truth_audit.json")
    decisions = {item.get("case_id"): item.get("decision") for item in value.get("cases", [])}
    if decisions != {case_id: "pass" for case_id in CASE_IDS.values()}:
        raise ValueError(f"world_first_truth_audit_failed:{decisions}")
    _write(run_root / "truth_audit.json", value)


def _delivery_name(package: Path) -> str:
    contract = DeliverableContractV1.model_validate_json((package / "deliverable_contract.json").read_text(encoding="utf-8"))
    return contract.deliverables[0].relative_path


def _calibration_prompt(task_id: str, expected: str) -> str:
    suffix = Path(expected).suffix
    return f"""Act as a factory-side calibration author, not a solver under evaluation. Read the task and teacher materials. Create three complete, openable anonymous work products of type {suffix}:
1. deliverable_files/controls/reference_quality{suffix}: covers every decision with no major error.
2. deliverable_files/controls/plausible_incomplete{suffix}: professionally plausible but omits exactly one important judgment or evidence limitation.
3. deliverable_files/controls/shortcut_critical_error{suffix}: follows a tempting shortcut targeted by the task and contains one explicit major professional error without announcing it as an error.
Also write deliverable_files/controls/control_intent.json identifying omitted_decision_id, shortcut_decision_id, and the intended shortcut. Do not alter task inputs or teacher truth. Reopen all three files. Task is {task_id}."""


def _calibration_judge_prompt(task_id: str) -> str:
    return f"""Blindly grade three anonymous calibration work products for task {task_id}. Read task, contract, decision matrix, teacher truth, rubric and all files in controls/. For every tier and every decision, give rating met/partial/not_met, major_error, evidence_paths and rationale. Compute a provisional 0–1 weighted_score, state major_defect, and provide ranking best_to_worst. Write deliverable_files/calibration_review.json as {{"task_id":...,"judge_id":...,"tiers":{{"reference_quality":{{"assessments":[],"weighted_score":...,"major_defect":...}},"plausible_incomplete":...,"shortcut_critical_error":...}},"ranking":[]}}. Do not infer how the files were generated."""


def _score_tier(value: dict[str, Any], rubric: TaskSpecificRubricV1) -> dict[str, Any]:
    weights = {item.decision_id: item.weight for item in rubric.criteria}
    ratings = {"met": 1.0, "partial": 0.5, "not_met": 0.0}
    assessments = value.get("assessments", [])
    if {item.get("decision_id") for item in assessments} != set(weights):
        return value
    value["weighted_score"] = round(sum(weights[item["decision_id"]] * ratings[item["rating"]] for item in assessments), 6)
    value["major_defect"] = any(bool(item.get("major_error")) for item in assessments)
    return value


def _calibrate(
    run_root: Path, run_id: str, packages: dict[str, Path],
) -> dict[str, Path]:
    controls: dict[str, Path] = {}
    for case_id, package in packages.items():
        task_id = f"{case_id}_task"
        generated = _session(
            run_root=run_root, run_id=run_id, assignment_id=f"{case_id}_calibration_author",
            stack=CHATGPT_CODEX_STACK,
            stage_inputs=lambda workspace, package=package: _copy(package, workspace / "inputs/task"),
            prompt=_calibration_prompt(task_id, _delivery_name(package)),
        ) / "controls"
        suffix = Path(_delivery_name(package)).suffix
        for name in ("reference_quality", "plausible_incomplete", "shortcut_critical_error"):
            path = generated / f"{name}{suffix}"
            report = inspect_delivery(generated.parent, expected=f"controls/{name}{suffix}", input_hashes=set(), verify_docx_with_office=False)
            if not path.is_file() or not report.valid:
                raise ValueError(f"world_first_calibration_delivery_invalid:{case_id}:{name}:{report.first_failure}")
        controls[case_id] = generated
        rubric = TaskSpecificRubricV1.model_validate_json((package / "teacher/task_specific_rubric.json").read_text(encoding="utf-8"))
        reviews: list[dict[str, Any]] = []
        for judge in STACKS:
            judge_name = "gpt" if judge == CHATGPT_CODEX_STACK else "deepseek"
            output = _session(
                run_root=run_root, run_id=run_id, assignment_id=f"{case_id}_calibration_{judge_name}",
                stack=judge,
                stage_inputs=lambda workspace, package=package, generated=generated: (
                    _copy(package / "TASK.md", workspace / "inputs/task.md"),
                    _copy(package / "deliverable_contract.json", workspace / "inputs/deliverable_contract.json"),
                    _copy(package / "teacher", workspace / "inputs/teacher"),
                    _copy(generated, workspace / "inputs/controls"),
                ),
                prompt=_calibration_judge_prompt(task_id),
            )
            review = _json(output / "calibration_review.json")
            review["judge_id"] = judge
            for tier in review.get("tiers", {}).values():
                _score_tier(tier, rubric)
            reviews.append(review)
        errors = judge_calibration_errors(reviews, decision_ids={item.decision_id for item in rubric.criteria})
        _write(run_root / "calibration" / f"{case_id}.json", {"reviews": reviews, "errors": errors})
        if errors:
            raise ValueError(f"world_first_judge_calibration_failed:{case_id}:{errors}")
    return controls


def _paired_judge_prompt(task_id: str, judge: str) -> str:
    return f"""Blindly compare two anonymous solver work products for task {task_id}. Read task, contract, teacher truth, decision matrix, rubric, bundle_1 and bundle_2. Inspect actual files. Write deliverable_files/paired_review.json matching paired_schema.json, with judge_id `{judge}`. Include every decision exactly once. Prefer bundle_1, bundle_2 or tie based only on professional correctness; do not infer solver identity. Evidence paths must point to visible content in each anonymous bundle. Scores are provisional and will be recomputed by the controller."""


def _run_behavior(
    run_root: Path, run_id: str, packages: dict[str, Path], plans: dict[str, ProfessionDifficultyPlanV1],
) -> tuple[dict[str, Any], str]:
    outcomes: dict[str, dict[str, Any]] = {}
    deliveries: dict[tuple[str, str], Path] = {}
    for stack in STACKS:
        for case_id, package in packages.items():
            binding = binding_from_task(package, domain=next(domain for (domain, _), cid in CASE_IDS.items() if cid == case_id))
            outcome = _execute_solver(
                host="huago-cone", remote_root=_remote_root(run_id), output_root=run_root,
                binding=binding, stack=stack, image=IMAGE, codex_auth_dir=CODEX_AUTH_DIR,
            )
            outcomes[f"{case_id}:{stack}"] = outcome.model_dump(mode="json")
            if outcome.delivery.valid:
                deliveries[(case_id, stack)] = run_root / "solvers" / stack / binding.task_id / "workspace" / binding.expected_delivery
    _write(run_root / "solver_outcomes.json", outcomes)
    results: dict[str, Any] = {}
    for case_id, package in packages.items():
        if any((case_id, stack) not in deliveries for stack in STACKS):
            results[case_id] = {"classification": "incomplete", "reason": "solver_delivery_missing"}
            continue
        rubric = TaskSpecificRubricV1.model_validate_json((package / "teacher/task_specific_rubric.json").read_text(encoding="utf-8"))
        reviews: list[PairedJudgeReviewV1] = []
        for judge in STACKS:
            judge_name = "gpt" if judge == CHATGPT_CODEX_STACK else "deepseek"
            output = _session(
                run_root=run_root, run_id=run_id, assignment_id=f"{case_id}_paired_{judge_name}",
                stack=judge,
                stage_inputs=lambda workspace, package=package, case_id=case_id: (
                    _copy(package / "TASK.md", workspace / "inputs/task.md"),
                    _copy(package / "deliverable_contract.json", workspace / "inputs/deliverable_contract.json"),
                    _copy(package / "teacher", workspace / "inputs/teacher"),
                    _copy(deliveries[(case_id, CHATGPT_CODEX_STACK)], workspace / f"inputs/bundle_1{deliveries[(case_id, CHATGPT_CODEX_STACK)].suffix}"),
                    _copy(deliveries[(case_id, DEEPSEEK_OPENCODE_STACK)], workspace / f"inputs/bundle_2{deliveries[(case_id, DEEPSEEK_OPENCODE_STACK)].suffix}"),
                    _write(workspace / "inputs/paired_schema.json", PairedJudgeReviewV1.model_json_schema()),
                ),
                prompt=_paired_judge_prompt(f"{case_id}_task", judge),
            )
            review = PairedJudgeReviewV1.model_validate(_json(output / "paired_review.json"))
            reviews.append(recompute_paired_review(review, rubric=rubric))
        result = paired_task_discrimination(
            reviews, bundle_1_solver=CHATGPT_CODEX_STACK,
            bundle_2_solver=DEEPSEEK_OPENCODE_STACK,
        )
        result["reviews"] = [item.model_dump(mode="json") for item in reviews]
        results[case_id] = result
    _write(run_root / "paired_results.json", results)

    domain_support: dict[str, bool] = {}
    for domain in SEED_IDS:
        baseline = results[CASE_IDS[(domain, "baseline")]]
        hard = results[CASE_IDS[(domain, "adversarial")]]
        baseline_gap = float(baseline.get("absolute_gap", 0))
        hard_gap = float(hard.get("absolute_gap", 0))
        hard_scores = [float(hard.get("bundle_1_composite", 0)), float(hard.get("bundle_2_composite", 0))]
        direct_major = hard.get("major_defect_pair") in ([True, False], [False, True])
        related_major = direct_major and any(
            mutation.targeted_shortcut.casefold() in json.dumps(hard, ensure_ascii=False).casefold()
            for mutation in plans[domain].mutations if mutation.mutation_id in plans[domain].selected_mutation_ids
        )
        domain_support[domain] = (
            hard.get("classification") == "cleanly_discriminative"
            and max(hard_scores) >= 0.70
            and (hard_gap >= baseline_gap + 0.05 or related_major)
        )
    if all(domain_support.values()):
        decision = "world_first_adversarial_supported"
    elif any(domain_support.values()):
        decision = "world_first_adversarial_mixed"
    else:
        decision = "world_first_adversarial_not_supported"
    return results, decision


def run(run_root: Path, run_id: str) -> None:
    inputs = _load_inputs()
    if run_root.exists():
        raise FileExistsError("world_first_run_root_already_exists")
    run_root.mkdir(parents=True)
    scope = _scope(run_id, inputs)
    _write(run_root / "scope.json", scope)
    _write(run_root / "receipt.json", {"scope_sha256": _canonical(scope), "consumed_at": _now()})
    manifest = _initial_manifest(run_id, inputs)
    write_manifest(run_root / "manifest.json", manifest)
    try:
        plans = _run_debate(run_root, run_id, inputs)
        manifest = _persist_stage(run_root, manifest, stage="skill_deliberated", plans=plans)
        worlds = _run_worlds(run_root, run_id, inputs, plans)
        manifest = _persist_stage(run_root, manifest, stage="world_frozen", plans=plans, worlds=worlds)
        tasks = _mine_tasks(run_root, run_id, inputs, worlds)
        manifest = _persist_stage(run_root, manifest, stage="task_mined", plans=plans, worlds=worlds)
        packages = _compile_tasks(run_root, run_id, inputs, worlds, tasks)
        manifest = _persist_stage(run_root, manifest, stage="truth_reconstructed", plans=plans, worlds=worlds, packages=packages)
        _truth_audit(run_root, run_id, worlds, packages)
        manifest = _persist_stage(run_root, manifest, stage="statically_admitted", plans=plans, worlds=worlds, packages=packages)
        _calibrate(run_root, run_id, packages)
        manifest = _persist_stage(run_root, manifest, stage="judge_calibrated", plans=plans, worlds=worlds, packages=packages, calibration=True)
        results, decision = _run_behavior(run_root, run_id, packages, plans)
        manifest = _persist_stage(
            run_root, manifest, stage="judged", plans=plans, worlds=worlds,
            packages=packages, calibration=True, decision=decision,
        )
        _write(run_root / "result.json", {
            "decision": decision, "professional_validity": "provisional",
            "task_results": results, "finished_at": _now(),
        })
    except Exception as exc:
        current = WorldFirstPilotManifestV1.model_validate_json((run_root / "manifest.json").read_text(encoding="utf-8"))
        write_manifest(run_root / "manifest.json", current.model_copy(update={
            "decision": "incomplete", "first_failure": f"{type(exc).__name__}:{exc}",
        }))
        _write(run_root / "result.json", {
            "decision": "incomplete", "professional_validity": "provisional",
            "first_failure": f"{type(exc).__name__}:{exc}", "finished_at": _now(),
        })
        raise


def resume(run_root: Path, run_id: str) -> None:
    """Continue only missing sessions after a controller-only repair.

    Completed provider sessions are reused byte-for-byte.  A started or failed
    provider session remains terminal and is never silently rerun.
    """

    if not run_root.is_dir():
        raise FileNotFoundError("world_first_resume_root_missing")
    scope = _json(run_root / "scope.json")
    if scope.get("campaign_id") != run_id or scope.get("image_sha256") != IMAGE_SHA256:
        raise ValueError("world_first_resume_scope_drift")
    completed = {}
    for state_path in sorted((run_root / "sessions").glob("*/state.json")):
        state = _json(state_path)
        if state.get("status") != "completed":
            raise ValueError(f"world_first_resume_nonterminal_session:{state_path.parent.name}")
        output = state_path.parent / "workspace/deliverable_files"
        completed[state_path.parent.name] = tree_sha256(output)
    if (run_root / "result.json").is_file() and not (run_root / "initial_incomplete_result.json").exists():
        shutil.copy2(run_root / "result.json", run_root / "initial_incomplete_result.json")
    repair_commit = _git_head()
    _write(run_root / "repair_receipts" / f"{repair_commit}.json", {
        "receipt_version": "r10.world_first_repair_receipt.1",
        "parent_scope_sha256": _canonical(scope), "repair_source_commit": repair_commit,
        "completed_session_output_sha256": completed,
        "repair_boundary": "candidate path-prefix normalization only; no semantic session rerun",
        "consumed_at": _now(),
    })
    manifest = WorldFirstPilotManifestV1.model_validate_json((run_root / "manifest.json").read_text(encoding="utf-8"))
    write_manifest(run_root / "manifest.json", manifest.model_copy(update={"decision": "pending", "first_failure": None}))
    inputs = _load_inputs()
    try:
        plans = _run_debate(run_root, run_id, inputs)
        manifest = _persist_stage(run_root, manifest.model_copy(update={"decision": "pending", "first_failure": None}), stage="skill_deliberated", plans=plans)
        worlds = _run_worlds(run_root, run_id, inputs, plans)
        manifest = _persist_stage(run_root, manifest, stage="world_frozen", plans=plans, worlds=worlds)
        tasks = _mine_tasks(run_root, run_id, inputs, worlds)
        manifest = _persist_stage(run_root, manifest, stage="task_mined", plans=plans, worlds=worlds)
        packages = _compile_tasks(run_root, run_id, inputs, worlds, tasks)
        manifest = _persist_stage(run_root, manifest, stage="truth_reconstructed", plans=plans, worlds=worlds, packages=packages)
        _truth_audit(run_root, run_id, worlds, packages)
        manifest = _persist_stage(run_root, manifest, stage="statically_admitted", plans=plans, worlds=worlds, packages=packages)
        _calibrate(run_root, run_id, packages)
        manifest = _persist_stage(run_root, manifest, stage="judge_calibrated", plans=plans, worlds=worlds, packages=packages, calibration=True)
        results, decision = _run_behavior(run_root, run_id, packages, plans)
        _persist_stage(run_root, manifest, stage="judged", plans=plans, worlds=worlds, packages=packages, calibration=True, decision=decision)
        _write(run_root / "result.json", {"decision": decision, "professional_validity": "provisional", "task_results": results, "finished_at": _now()})
    except Exception as exc:
        current = WorldFirstPilotManifestV1.model_validate_json((run_root / "manifest.json").read_text(encoding="utf-8"))
        write_manifest(run_root / "manifest.json", current.model_copy(update={"decision": "incomplete", "first_failure": f"{type(exc).__name__}:{exc}"}))
        _write(run_root / "result.json", {"decision": "incomplete", "professional_validity": "provisional", "first_failure": f"{type(exc).__name__}:{exc}", "finished_at": _now()})
        raise


def status(run_root: Path) -> dict[str, Any]:
    if not run_root.is_dir():
        return {"status": "not_started"}
    result = _json(run_root / "result.json") if (run_root / "result.json").is_file() else None
    sessions = {}
    for path in sorted((run_root / "sessions").glob("*/state.json")) if (run_root / "sessions").is_dir() else []:
        sessions[path.parent.name] = _json(path).get("status")
    return {"status": "completed" if result else "running_or_interrupted", "result": result, "sessions": sessions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["scope", "run", "status", "resume"])
    parser.add_argument("--run-id", default="r10_9_world_first_pilot_20260902")
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = args.output_root or ROOT / "artifacts/r10" / args.run_id
    if args.action == "scope":
        value = _scope(args.run_id, _load_inputs())
        print(json.dumps({"scope_sha256": _canonical(value), "scope": value}, ensure_ascii=False, indent=2))
    elif args.action == "status":
        print(json.dumps(status(output), ensure_ascii=False, indent=2))
    elif args.action == "resume":
        current = status(output)
        if current["status"] == "not_started":
            run(output, args.run_id)
        elif current["status"] in {"running_or_interrupted", "completed"} and current.get("result", {}).get("decision") == "incomplete":
            resume(output, args.run_id)
        else:
            raise RuntimeError("world_first_resume_refuses_started_or_terminal_sessions")
    else:
        run(output, args.run_id)


if __name__ == "__main__":
    main()
