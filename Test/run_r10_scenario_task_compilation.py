"""Compile two R10 Scenario-First task/truth pilot packages on huago-cone."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from run_r10_skill_compiler import IMAGE, _remote_script, _run, _ssh
from task_generator.core.deliverable_contract import DeliverableContractCompiler
from task_generator.core.scenario_first import ProfessionalRuleSetV1, ScenarioBibleV1
from task_generator.planning.scenario_task_compiler import (
    ScenarioTaskAdmissionValidator,
    ScenarioTaskCompilationPlanV1,
    ScenarioTaskSpecV1,
    TaskCompilationOutputV1,
    compile_scope,
    compiler_prompt,
    sha256_json,
    tree_sha256,
)
from task_generator.substrate.professional_skills import ProfessionalSkillLoader


FINAL_BUNDLE_ROOT = ROOT / "artifacts" / "r10" / "r10_skill_review_ab_20260830_execute3" / "completed"
BIBLES = ROOT / "artifacts" / "r10" / "r10_2_scenario_bible_batch_20260829_distribution_repair" / "bibles"
RULE_SETS = ROOT / "data" / "r10" / "work_seeds" / "professional_rule_sets.json"
SKILL_CATALOG = ROOT / "data" / "r10" / "professional_skills" / "catalog.json"
SKILLS_ROOT = ROOT / ".agents" / "skills" / "r10"
IMAGE_SHA256 = "02b79e7f6c1b9966918fc986c7624f50c2f45c6e32a5502bc30f65ccd328a722"

TASKS = {
    "r10_audit_revenue_evidence_reliability": {
        "scenario_id": "scenario_audit_company_information_reliability",
        "domain": "audit_compliance",
        "skill_id": "r10.audit-evidence-reliability",
        "bundle": "scenario_audit_company_information_reliability__with_skill",
        "deliverable": {"file_name": "audit_evidence_workpaper.xlsx", "format": "xlsx", "creation_mode": "create"},
    },
    "r10_procurement_price_reasonableness": {
        "scenario_id": "scenario_procurement_price_reasonableness",
        "domain": "procurement_operations",
        "skill_id": "r10.procurement-price-reasonableness",
        "bundle": "scenario_procurement_price_reasonableness__with_skill",
        "deliverable": {"file_name": "price_reasonableness_memo.docx", "format": "docx", "creation_mode": "create"},
    },
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_bibles_and_rules() -> tuple[dict[str, ScenarioBibleV1], dict[str, ProfessionalRuleSetV1]]:
    bibles = {item.stem: ScenarioBibleV1.model_validate_json(item.read_text(encoding="utf-8")) for item in BIBLES.glob("*.json")}
    rules = {item.rule_set_id: item for item in (ProfessionalRuleSetV1.model_validate(value) for value in json.loads(RULE_SETS.read_text(encoding="utf-8")))}
    return bibles, rules


def build_plan() -> ScenarioTaskCompilationPlanV1:
    specs = []
    for task_id, config in TASKS.items():
        bundle = FINAL_BUNDLE_ROOT / config["bundle"]
        candidate = bundle / "candidate"
        contract = DeliverableContractCompiler().build(case_id=task_id, deliverable_specs=[config["deliverable"]])
        specs.append(ScenarioTaskSpecV1(
            task_id=task_id, scenario_id=config["scenario_id"], domain=config["domain"], skill_id=config["skill_id"],
            parent_bundle_sha256=tree_sha256(bundle), candidate_tree_sha256=tree_sha256(candidate), deliverable_contract=contract,
        ))
    return ScenarioTaskCompilationPlanV1(tasks=specs)


def _stage_task(*, workspace: Path, spec: ScenarioTaskSpecV1, bible: ScenarioBibleV1, rules: ProfessionalRuleSetV1) -> None:
    config = TASKS[spec.task_id]
    bundle = FINAL_BUNDLE_ROOT / config["bundle"]
    candidate = bundle / "candidate"
    reference = workspace / "reference_files"
    frozen = workspace / "_frozen_candidate"
    shutil.copytree(candidate, reference)
    shutil.copytree(candidate, frozen)
    teacher = workspace / "teacher"
    teacher.mkdir()
    _write(teacher / "scenario_bible.json", bible.model_dump(mode="json"))
    _write(teacher / "professional_rules.json", rules.model_dump(mode="json"))
    _write(teacher / "evidence_map.json", json.loads((bundle / "teacher" / "evidence_map.json").read_text(encoding="utf-8")))
    _write(teacher / "scenario_extension.json", json.loads((bundle / "teacher" / "scenario_extension.json").read_text(encoding="utf-8")))
    loader = ProfessionalSkillLoader()
    catalog = loader.load_catalog(SKILL_CATALOG)
    entry = next(item for item in catalog.entries if item.skill_id == spec.skill_id)
    skill = loader.load_skill(entry, skills_root=SKILLS_ROOT)
    (teacher / "professional_skill").mkdir()
    (teacher / "professional_skill" / "SKILL.md").write_text(skill.skill_markdown, encoding="utf-8")
    for relative, content in skill.reference_markdown.items():
        target = teacher / "professional_skill" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _write(workspace / "deliverable_contract.json", spec.deliverable_contract.model_dump(mode="json"))
    (workspace / "TASK.md").write_text(compiler_prompt(spec=spec), encoding="utf-8")


def _parse_output(path: Path) -> TaskCompilationOutputV1:
    return TaskCompilationOutputV1.model_validate_json(path.read_text(encoding="utf-8"))


def _materialize_package(*, workspace: Path, spec: ScenarioTaskSpecV1, output: TaskCompilationOutputV1) -> None:
    prompt = DeliverableContractCompiler().compile_prompt(output.base_prompt, spec.deliverable_contract)
    (workspace / "TASK.md").write_text(prompt, encoding="utf-8")
    _write(workspace / "teacher" / "teacher_truth.json", {"truth": [item.model_dump(mode="json") for item in output.teacher_truth]})
    _write(workspace / "teacher" / "decision_matrix.json", output.decision_matrix.model_dump(mode="json"))
    _write(workspace / "teacher" / "task_specific_rubric.json", output.task_specific_rubric.model_dump(mode="json"))
    _write(workspace / "teacher" / "task_compilation.json", output.model_dump(mode="json"))
    _write(workspace / "task_manifest.json", {
        "manifest_version": "r10.scenario_task_manifest.1", "task_id": spec.task_id, "scenario_id": spec.scenario_id,
        "parent_bundle_sha256": spec.parent_bundle_sha256, "candidate_tree_sha256": spec.candidate_tree_sha256,
        "task_compilation_sha256": output.canonical_sha256(), "deliverable_contract_sha256": sha256_json(spec.deliverable_contract.model_dump(mode="json")),
    })


def _write_user_review_pack(*, workspace: Path, target: Path, spec: ScenarioTaskSpecV1, output: TaskCompilationOutputV1) -> None:
    """Create a compact, explicitly teacher-visible inspection copy for the user."""
    if target.exists():
        shutil.rmtree(target)
    candidate = target / "candidate_task"
    candidate.mkdir(parents=True)
    shutil.copy2(workspace / "TASK.md", candidate / "TASK.md")
    shutil.copy2(workspace / "deliverable_contract.json", candidate / "deliverable_contract.json")
    shutil.copytree(workspace / "reference_files", candidate / "reference_files")
    lines = [f"# {spec.task_id} — Teacher Truth 摘要", "", "以下内容仅供项目审题，不属于 candidate task package。", ""]
    for item in output.teacher_truth:
        lines.extend([f"## {item.decision_id}", "", item.conclusion, "", "后续行动："])
        lines.extend(f"- {action}" for action in item.required_follow_up_actions)
        lines.append("")
    (target / "teacher_truth_summary.md").write_text("\n".join(lines), encoding="utf-8")


def _execute_remote(*, host: str, remote: str, workspace: Path) -> subprocess.CompletedProcess[str]:
    _ssh(host, f"mkdir -p '{remote.rsplit('/', 1)[0]}' && rm -rf '{remote}'", timeout=120)
    _run(["scp", "-r", str(workspace), f"{host}:{remote}"], timeout=240)
    result = _ssh(host, "sh -s", input_text=_remote_script(remote), timeout=1900, check=False)
    _run(["scp", "-r", f"{host}:{remote}/.", str(workspace)], timeout=240)
    _write(workspace / "execution_diagnostics.json", {"finished_at": _now(), "exit_code": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
    return result


def _compile_one(*, host: str, remote_root: str, output_root: Path, spec: ScenarioTaskSpecV1, bible: ScenarioBibleV1, rules: ProfessionalRuleSetV1) -> dict[str, Any]:
    workspace = output_root / "tasks" / spec.task_id
    _stage_task(workspace=workspace, spec=spec, bible=bible, rules=rules)
    executed = _execute_remote(host=host, remote=f"{remote_root}/{spec.task_id}", workspace=workspace)
    output_path = workspace / "teacher" / "task_compilation.json"
    first_failure: str | None = None
    output: TaskCompilationOutputV1 | None = None
    if executed.returncode == 0:
        try:
            output = _parse_output(output_path)
        except Exception as exc:
            first_failure = f"task_compilation_json_or_schema_invalid:{type(exc).__name__}"
    else:
        first_failure = f"codex_or_container_exit:{executed.returncode}"
    # A second call is deliberately reserved for invalid/missing structured output.
    if output is None and first_failure and first_failure.startswith("task_compilation_json_or_schema_invalid"):
        (workspace / "TASK.md").write_text(compiler_prompt(spec=spec) + "\nYour prior output was missing or invalid. Replace only teacher/task_compilation.json with schema-valid JSON; do not edit any other file.\n", encoding="utf-8")
        retry = _execute_remote(host=host, remote=f"{remote_root}/{spec.task_id}_format_retry", workspace=workspace)
        if retry.returncode == 0:
            try:
                output = _parse_output(output_path)
            except Exception:
                pass
    if output is None:
        report = {"task_id": spec.task_id, "decision": "incomplete", "first_failure": first_failure}
        _write(workspace / "admission_report.json", report)
        return report
    _materialize_package(workspace=workspace, spec=spec, output=output)
    report = ScenarioTaskAdmissionValidator().validate(spec=spec, package_root=workspace, bible=bible, rules=rules, output=output)
    report = report.model_copy(update={"first_failure": first_failure})
    _write(workspace / "admission_report.json", report.model_dump(mode="json"))
    if report.decision == "pass":
        _write_user_review_pack(workspace=workspace, target=output_root / "user_review" / spec.task_id, spec=spec, output=output)
    return report.model_dump(mode="json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", default="r10_6_task_compilation_20260831_execute1")
    parser.add_argument("--campaign-id", default="r10_6_task_compilation_20260831_execute1")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts" / "r10" / "r10_6_task_compilation_20260831_execute1")
    parser.add_argument("--scope-only", action="store_true")
    parser.add_argument("--review-only", action="store_true", help="Rebuild the local user review pack from an already admitted run; no provider call.")
    args = parser.parse_args()
    if args.scope_only and args.review_only:
        parser.error("scope_only_and_review_only_are_mutually_exclusive")
    if args.review_only:
        if not args.output_root.is_dir():
            raise FileNotFoundError("r10_task_compilation_review_root_missing")
        plan = build_plan()
        for spec in plan.tasks:
            workspace = args.output_root / "tasks" / spec.task_id
            report = json.loads((workspace / "admission_report.json").read_text(encoding="utf-8"))
            if report.get("decision") != "pass":
                raise RuntimeError("user_review_requires_admitted_task")
            _write_user_review_pack(workspace=workspace, target=args.output_root / "user_review" / spec.task_id, spec=spec, output=_parse_output(workspace / "teacher" / "task_compilation.json"))
        print(json.dumps({"decision": "user_review_pack_ready", "output_root": str(args.output_root / "user_review")}, ensure_ascii=False))
        return
    if args.output_root.exists():
        raise FileExistsError("r10_task_compilation_output_already_exists")
    bibles, rules = _load_bibles_and_rules()
    plan = build_plan()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=True).stdout.strip()
    scope = compile_scope(campaign_id=args.campaign_id, source_commit=commit, plan=plan, image=IMAGE, image_sha256=IMAGE_SHA256)
    args.output_root.mkdir(parents=True)
    _write(args.output_root / "campaign_scope.json", scope.model_dump(mode="json"))
    _write(args.output_root / "compilation_plan.json", plan.model_dump(mode="json"))
    if args.scope_only:
        print(json.dumps({"decision": "awaiting_execution", "scope_sha256": scope.canonical_sha256()}, ensure_ascii=False))
        return
    _write(args.output_root / "scope_receipt.json", {"scope_sha256": scope.canonical_sha256(), "campaign_id": args.campaign_id, "status": "consumed", "consumed_at": _now()})
    remote_home = _ssh(args.host, 'printf %s "$HOME"', timeout=120).stdout.strip()
    remote_root = f"{remote_home}/taskgenerator-data/r10-task-compilation/{args.run_id}"
    reports = []
    for spec in plan.tasks:
        reports.append(_compile_one(host=args.host, remote_root=remote_root, output_root=args.output_root, spec=spec, bible=bibles[spec.scenario_id], rules=rules[bibles[spec.scenario_id].rule_set_id]))
    decision = "compiled_for_user_review" if all(item.get("decision") == "pass" for item in reports) else "incomplete"
    _write(args.output_root / "compilation_result.json", {"result_version": "r10.scenario_task_compilation_result.1", "plan_sha256": plan.canonical_sha256(), "decision": decision, "reports": reports})
    print(json.dumps({"decision": decision, "output_root": str(args.output_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
