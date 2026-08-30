"""Run common-base, agent-review A/B evidence experiment with compiled Skills."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from run_r10_scenario_evidence_ab import IMAGE, SCENARIOS, _image_digest, _now, _probe, _remote_session_script, _run, _ssh, _write
from task_generator.core.scenario_first import ProfessionalRuleSetV1, ScenarioBibleV1, WorkSeedV1
from task_generator.planning.scenario_evidence_experiment import OfficialDeepSeekConditionBlindReviewer, ScenarioEvidenceExperiment, ScenarioEvidenceExperimentPlanV1, ScenarioEvidenceSessionV1, aggregate_experiment
from task_generator.planning.work_seed_admission import WorkSeedCandidateV1
from task_generator.substrate.professional_skill_compiler import sha256_json, tree_sha256
from task_generator.substrate.professional_skills import ProfessionalSkillLoader


def _load(args: argparse.Namespace):
    bibles = {path.stem: ScenarioBibleV1.model_validate_json(path.read_text(encoding="utf-8")) for path in args.bibles_dir.glob("*.json")}
    selected = {key: bibles[key] for key in SCENARIOS}
    rules = {item.rule_set_id: item for item in [ProfessionalRuleSetV1.model_validate(value) for value in json.loads(args.rule_sets.read_text(encoding="utf-8"))]}
    seeds = {item.seed.seed_id: item.seed for item in [WorkSeedCandidateV1.model_validate(value) for value in json.loads(args.work_seeds.read_text(encoding="utf-8"))] if item.status == "admitted"}
    loader, catalog = ProfessionalSkillLoader(), ProfessionalSkillLoader().load_catalog(args.skill_catalog)
    skills = {skill_id: loader.load_skill(next(entry for entry in catalog.entries if entry.skill_id == skill_id), skills_root=args.compiled_skills_root) for skill_id in {item["skill_id"] for item in SCENARIOS.values()}}
    return selected, rules, seeds, skills


def _review_prompt(*, with_skill: bool) -> str:
    skill = "Read teacher/professional_skill/SKILL.md and its source map. Use it only as a professional review lens." if with_skill else "Do not load or infer a professional Skill package; use ordinary realism review only."
    return f"""You are revising a factory-side evidence bundle. Preserve the parent Bible and rules in teacher/; do not alter them. Review candidate/ as a realistic work product, then make limited edits only where they improve natural business provenance, role ownership, plausible incompleteness, and room for the candidate's professional judgment. {skill}

Do not turn candidate material into an analyst workpaper, comparison sheet, answer template, conclusion label, or final disposition. Do not add task prompts, rubrics, solver answers, or generic tool instructions. If you change candidate facts, register them in teacher/scenario_extension.json and keep teacher/evidence_map.json closed over all candidate files. Validate both JSON files before finishing.
"""


def _copy_base(*, base: Path, destination: Path, skill, with_skill: bool) -> None:
    shutil.copytree(base, destination, ignore=shutil.ignore_patterns("codex.jsonl", "stderr.txt", "docker_*.txt", "execution_diagnostics.json", "admission_report.json", ".codex"))
    (destination / "TASK.md").write_text(_review_prompt(with_skill=with_skill), encoding="utf-8")
    if with_skill:
        package = destination / "teacher" / "professional_skill"
        package.mkdir()
        (package / "SKILL.md").write_text(skill.skill_markdown, encoding="utf-8")
        for relative, content in skill.reference_markdown.items():
            target = package / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", default="r10_skill_review_ab_20260830")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/r10/r10_skill_review_ab_20260830")
    parser.add_argument("--bibles-dir", type=Path, default=ROOT / "artifacts/r10/r10_2_scenario_bible_batch_20260829_distribution_repair/bibles")
    parser.add_argument("--rule-sets", type=Path, default=ROOT / "data/r10/work_seeds/professional_rule_sets.json")
    parser.add_argument("--work-seeds", type=Path, default=ROOT / "data/r10/work_seeds/candidate_work_seeds.json")
    parser.add_argument("--skill-catalog", type=Path, default=ROOT / "data/r10/professional_skills/catalog.json")
    parser.add_argument("--compiled-skills-root", type=Path, required=True)
    parser.add_argument("--deepseek-key", type=Path, default=ROOT / "deepseek-key.txt")
    parser.add_argument("--image-sha256", default="02b79e7f6c1b9966918fc986c7624f50c2f45c6e32a5502bc30f65ccd328a722")
    args = parser.parse_args()
    if args.output_root.exists():
        raise FileExistsError("skill_review_ab_output_already_exists")
    selected, rules, seeds, skills = _load(args)
    args.output_root.mkdir(parents=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    compiled_skills_sha256 = tree_sha256(args.compiled_skills_root)
    scope = {
        "scope_version": "r10.skill_review_ab_scope.1",
        "source_commit": commit,
        "compiled_skills_sha256": compiled_skills_sha256,
        "scenarios": sorted(SCENARIOS),
        "generator": {"model": "gpt-5.6-terra", "base_sessions": 2, "review_sessions": 4, "timeout_seconds": 1800},
        "reviewer": {"provider": "deepseek", "model": "deepseek-v4-pro", "pair_review_limit": 2, "format_retry_limit": 1},
        "excluded": ["task_compilation", "solver", "grader", "release", "training", "promotion"],
    }
    _write(args.output_root / "campaign_scope.json", scope)
    _write(args.output_root / "scope_receipt.json", {"scope_sha256": sha256_json(scope), "status": "consumed", "consumed_at": _now()})
    _write(args.output_root / "campaign_manifest.json", {"source_commit": commit, "compiled_skills_sha256": compiled_skills_sha256, "model": "gpt-5.6-terra", "common_base_per_scenario": True, "review_sessions": 4, "pair_review_limit": 2})
    remote_home = _ssh(args.host, 'printf %s "$HOME"', timeout=120).stdout.strip()
    remote_root = f"{remote_home}/taskgenerator-data/r10-skill-review-ab/{args.run_id}"
    _probe(args.host, remote_root, args.output_root)
    if _image_digest(args.host) != args.image_sha256:
        raise RuntimeError("skill_review_remote_image_drift")
    experiment, finals, base_trees = ScenarioEvidenceExperiment(), {}, {}
    sessions: list[ScenarioEvidenceSessionV1] = []
    for scenario_id, config in SCENARIOS.items():
        bible, ruleset, skill = selected[scenario_id], rules[selected[scenario_id].rule_set_id], skills[config["skill_id"]]
        base_session = ScenarioEvidenceSessionV1(session_id=f"{scenario_id}__base", scenario_id=scenario_id, domain=config["domain"], condition="without_skill", bible_sha256=bible.canonical_sha256(), rule_set_sha256=ruleset.canonical_sha256(), image=IMAGE, image_sha256=args.image_sha256)
        base = args.output_root / "base" / scenario_id
        experiment.stage_session(workspace=base, session=base_session, bible=bible, rules=ruleset, skill=None)
        remote = f"{remote_root}/base/{scenario_id}"
        _ssh(args.host, f"mkdir -p '{remote_root}/base'", timeout=120)
        _run(["scp", "-r", str(base), f"{args.host}:{remote}"], timeout=240)
        executed = _ssh(args.host, "sh -s", input_text=_remote_session_script(remote), timeout=1900, check=False)
        downloaded = args.output_root / "base_completed" / scenario_id
        downloaded.mkdir(parents=True)
        _run(["scp", "-r", f"{args.host}:{remote}/.", str(downloaded)], timeout=240)
        base_report = experiment.admit(session=base_session, workspace=downloaded, bible=bible)
        _write(downloaded / "admission_report.json", base_report.model_dump(mode="json"))
        if executed.returncode or base_report.decision != "pass":
            _write(args.output_root / "experiment_result.json", {"decision": "incomplete", "reasons": [f"base_failed:{scenario_id}"]})
            return
        base_trees[scenario_id] = base_report.output_tree_sha256
        for condition in ("without_skill", "with_skill"):
            session = ScenarioEvidenceSessionV1(session_id=f"{scenario_id}__{condition}", scenario_id=scenario_id, domain=config["domain"], condition=condition, bible_sha256=bible.canonical_sha256(), rule_set_sha256=ruleset.canonical_sha256(), image=IMAGE, image_sha256=args.image_sha256, skill_id=skill.entry.skill_id if condition == "with_skill" else None, skill_sha256=experiment.sha256_json(skill.model_dump(mode="json")) if condition == "with_skill" else None)
            workspace = args.output_root / "staged" / session.session_id
            _copy_base(base=downloaded, destination=workspace, skill=skill, with_skill=condition == "with_skill")
            finals[(scenario_id, condition)] = (session, workspace)
            sessions.append(session)
    _write(args.output_root / "common_base_manifest.json", {"base_output_trees": base_trees})
    plan = ScenarioEvidenceExperimentPlanV1(sessions=sessions)
    _write(args.output_root / "experiment_plan.json", plan.model_dump(mode="json"))
    admissions = []
    for session, workspace in finals.values():
        remote = f"{remote_root}/review/{session.session_id}"
        _ssh(args.host, f"mkdir -p '{remote_root}/review'", timeout=120)
        _run(["scp", "-r", str(workspace), f"{args.host}:{remote}"], timeout=240)
        executed = _ssh(args.host, "sh -s", input_text=_remote_session_script(remote), timeout=1900, check=False)
        completed = args.output_root / "completed" / session.session_id
        completed.mkdir(parents=True)
        _run(["scp", "-r", f"{args.host}:{remote}/.", str(completed)], timeout=240)
        report = experiment.admit(session=session, workspace=completed, bible=selected[session.scenario_id])
        if executed.returncode:
            report = report.model_copy(update={"decision": "incomplete", "first_failure": f"codex_or_container_exit:{executed.returncode}"})
        _write(completed / "admission_report.json", report.model_dump(mode="json"))
        admissions.append(report)
    reviews = []
    if all(item.decision == "pass" for item in admissions):
        key = args.deepseek_key.read_text(encoding="utf-8").strip()
        reviewer = OfficialDeepSeekConditionBlindReviewer()
        for scenario_id in SCENARIOS:
            bible = selected[scenario_id]
            order, payload = experiment.blind_payload(seed=seeds[bible.work_seed_id], rules=rules[bible.rule_set_id], workspaces={condition: args.output_root / "completed" / f"{scenario_id}__{condition}" for condition in ("without_skill", "with_skill")}, scenario_id=scenario_id)
            reviews.append(reviewer.review(scenario_id=scenario_id, bundle_order=order, payload=payload, api_key=key, output_root=args.output_root / "blind_reviews" / scenario_id))
    result = aggregate_experiment(plan=plan, admissions=admissions, reviews=reviews)
    _write(args.output_root / "experiment_result.json", result.model_dump(mode="json"))
    print(json.dumps({"decision": result.decision, "reasons": result.reasons, "output_root": str(args.output_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
