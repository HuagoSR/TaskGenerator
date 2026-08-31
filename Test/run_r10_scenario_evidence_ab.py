"""Run the four-session R10 professional-Skill evidence A/B experiment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from task_generator.core.scenario_first import ProfessionalRuleSetV1, ScenarioBibleV1, WorkSeedV1
from task_generator.planning.scenario_evidence_experiment import (
    OfficialDeepSeekConditionBlindReviewer,
    ScenarioEvidenceExperiment,
    ScenarioEvidenceExperimentPlanV1,
    ScenarioEvidenceSessionV1,
    aggregate_experiment,
    compile_campaign_scope,
)
from task_generator.planning.work_seed_admission import WorkSeedCandidateV1
from task_generator.substrate.professional_skills import ProfessionalSkillLoader

IMAGE = "taskgenerator-eval:milestone-r9-huago-cone-746ff9b55f1b"
SCENARIOS = {
    "scenario_audit_company_information_reliability": {"domain": "audit_compliance", "skill_id": "r10.audit-evidence-reliability"},
    "scenario_procurement_price_reasonableness": {"domain": "procurement_operations", "skill_id": "r10.procurement-price-reasonableness"},
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run(command: list[str], *, input_text: str | None = None, timeout: int = 1900, check: bool = True) -> subprocess.CompletedProcess[str]:
    if input_text is None:
        result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)
    else:
        # Windows text pipes translate LF to CRLF.  POSIX ``sh -s`` then treats
        # the carriage return as part of a ``set -eu`` option, so stream exact
        # UTF-8 bytes for the remote heredoc.
        raw = subprocess.run(command, input=input_text.encode("utf-8"), capture_output=True, timeout=timeout)
        result = subprocess.CompletedProcess(command, raw.returncode, raw.stdout.decode("utf-8", errors="replace"), raw.stderr.decode("utf-8", errors="replace"))
    if check and result.returncode:
        raise RuntimeError(f"command_failed:{result.returncode}:{' '.join(command[:3])}:{result.stderr[-800:]}")
    return result


def _ssh(host: str, command: str, *, input_text: str | None = None, timeout: int = 1900, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["ssh", "-o", "BatchMode=yes", host, command], input_text=input_text, timeout=timeout, check=check)


def _image_digest(host: str) -> str:
    result = _ssh(host, f"docker image inspect --format '{{{{.Id}}}}' {IMAGE}", timeout=120)
    digest = result.stdout.strip().removeprefix("sha256:")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise RuntimeError("invalid_remote_eval_image_digest")
    return digest


def _remote_session_script(workspace: str) -> str:
    return f"""set -eu
workspace='{workspace}'
auth_file=\"$HOME/.codex/auth.json\"
test -r \"$auth_file\"
cd \"$workspace\"
timeout --preserve-status 1800 docker run -i --rm --init --read-only --cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000 --memory 3g --cpus 2 --pids-limit 256 \\
  --tmpfs /tmp:rw,nosuid,nodev,size=512m --tmpfs /home/taskgenerator/.cache:rw,nosuid,nodev,size=512m --tmpfs /home/taskgenerator/.local:rw,nosuid,nodev,size=512m --tmpfs /home/taskgenerator/.config:rw,nosuid,nodev,size=256m \\
  -v \"$workspace:/workspace:rw\" -v \"$auth_file:/run/codex-auth/auth.json:ro\" -w /workspace --entrypoint /bin/sh \\
  {IMAGE} -s > docker_stdout.txt 2> docker_stderr.txt <<'CONTAINER_SCRIPT'
set -eu
mkdir -p .codex
ln -sf /run/codex-auth/auth.json .codex/auth.json
trap 'rm -rf /workspace/.codex' EXIT
export CODEX_HOME=/workspace/.codex
codex exec --dangerously-bypass-approvals-and-sandbox --model gpt-5.6-terra -c project_doc_max_bytes=0 -c agents.enabled=false --disable plugins --disable apps --disable multi_agent --disable skill_search --json --ephemeral --ignore-user-config --ignore-rules --skip-git-repo-check -C /workspace - < TASK.md > codex.jsonl 2> stderr.txt
CONTAINER_SCRIPT
"""


def _probe(host: str, remote_root: str, output_root: Path) -> None:
    probe = output_root / "public_probe"
    (probe / "candidate").mkdir(parents=True)
    (probe / "teacher").mkdir()
    (probe / "TASK.md").write_text("Create candidate/public_probe.xlsx with a non-empty worksheet and candidate/public_note.txt. Do not write teacher files.\n", encoding="utf-8")
    remote = f"{remote_root}/public_probe"
    _ssh(host, f"mkdir -p '{remote_root}' && rm -rf '{remote}'", timeout=120)
    _run(["scp", "-r", str(probe), f"{host}:{remote}"], timeout=180)
    result = _ssh(host, "sh -s", input_text=_remote_session_script(remote), timeout=1900, check=False)
    _write(probe / "diagnostics.json", {"exit_code": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
    if result.returncode:
        raise RuntimeError(f"public_codex_probe_failed:{result.returncode}")
    downloads = probe / "downloads"
    downloads.mkdir()
    _run(["scp", "-r", f"{host}:{remote}/.", str(downloads)], timeout=180)
    candidate = downloads / "candidate"
    if not (candidate / "public_probe.xlsx").is_file() or not (candidate / "public_note.txt").is_file():
        raise RuntimeError("public_codex_probe_missing_delivery")


def _load(args: argparse.Namespace) -> tuple[dict[str, ScenarioBibleV1], dict[str, ProfessionalRuleSetV1], dict[str, WorkSeedV1], dict[str, Any], dict[str, list[str]]]:
    bibles = {path.stem: ScenarioBibleV1.model_validate_json(path.read_text(encoding="utf-8")) for path in args.bibles_dir.glob("*.json")}
    selected = {key: bibles[key] for key in SCENARIOS}
    rule_sets = {item.rule_set_id: item for item in [ProfessionalRuleSetV1.model_validate(value) for value in json.loads(args.rule_sets.read_text(encoding="utf-8"))]}
    seeds = {item.seed.seed_id: item.seed for item in [WorkSeedCandidateV1.model_validate(value) for value in json.loads(args.work_seeds.read_text(encoding="utf-8"))] if item.status == "admitted"}
    loader = ProfessionalSkillLoader()
    catalog = loader.load_catalog(args.skill_catalog)
    skills = {}
    for skill_id in {item["skill_id"] for item in SCENARIOS.values()}:
        skills[skill_id] = loader.load_skill(next(item for item in catalog.entries if item.skill_id == skill_id), skills_root=args.skills_root)
    sources = json.loads(args.curation_sources.read_text(encoding="utf-8"))["sources"]
    source_ids = {skill_id: sorted(item["source_id"] for item in sources if item["skill_id"] == skill_id) for skill_id in skills}
    if any(not ids for ids in source_ids.values()):
        raise ValueError("curated_skill_has_no_source_map")
    return selected, rule_sets, seeds, skills, source_ids


def _build_plan(*, selected: dict[str, ScenarioBibleV1], rules: dict[str, ProfessionalRuleSetV1], skills: dict[str, Any], source_ids: dict[str, list[str]], image_sha: str) -> ScenarioEvidenceExperimentPlanV1:
    experiment, sessions = ScenarioEvidenceExperiment(), []
    for scenario_id, config in SCENARIOS.items():
        bible, rule_set, skill = selected[scenario_id], rules[selected[scenario_id].rule_set_id], skills[config["skill_id"]]
        for condition in ("without_skill", "with_skill"):
            sessions.append(ScenarioEvidenceSessionV1(session_id=f"{scenario_id}__{condition}", scenario_id=scenario_id, domain=config["domain"], condition=condition, bible_sha256=bible.canonical_sha256(), rule_set_sha256=rule_set.canonical_sha256(), image=IMAGE, image_sha256=image_sha, skill_id=skill.entry.skill_id if condition == "with_skill" else None, skill_sha256=experiment.sha256_json(skill.model_dump(mode="json")) if condition == "with_skill" else None, skill_source_ids=source_ids[skill.entry.skill_id] if condition == "with_skill" else []))
    return ScenarioEvidenceExperimentPlanV1(sessions=sessions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", default="r10_5_skill_evidence_ab_20260830")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts" / "r10" / "r10_5_skill_evidence_ab_20260830")
    parser.add_argument("--bibles-dir", type=Path, default=ROOT / "artifacts" / "r10" / "r10_2_scenario_bible_batch_20260829_distribution_repair" / "bibles")
    parser.add_argument("--rule-sets", type=Path, default=ROOT / "data" / "r10" / "work_seeds" / "professional_rule_sets.json")
    parser.add_argument("--work-seeds", type=Path, default=ROOT / "data" / "r10" / "work_seeds" / "candidate_work_seeds.json")
    parser.add_argument("--skill-catalog", type=Path, default=ROOT / "data" / "r10" / "professional_skills" / "catalog.json")
    parser.add_argument("--curation-sources", type=Path, default=ROOT / "data" / "r10" / "professional_skills" / "curation_sources.json")
    parser.add_argument("--skills-root", type=Path, default=ROOT / ".agents" / "skills" / "r10")
    parser.add_argument("--deepseek-key", type=Path, default=ROOT / "deepseek-key.txt")
    parser.add_argument("--campaign-id", default="r10_5_skill_evidence_ab_restart1")
    parser.add_argument("--source-commit")
    parser.add_argument("--scope-only", action="store_true")
    parser.add_argument("--image-sha256", default="02b79e7f6c1b9966918fc986c7624f50c2f45c6e32a5502bc30f65ccd328a722")
    parser.add_argument("--authorized-scope-sha256")
    args = parser.parse_args()
    if args.output_root.exists():
        raise FileExistsError("r10_evidence_experiment_output_already_exists")
    selected, rules, seeds, skills, source_ids = _load(args)
    args.output_root.mkdir(parents=True)
    source_commit = args.source_commit or subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=True).stdout.strip()
    authorized_plan = _build_plan(selected=selected, rules=rules, skills=skills, source_ids=source_ids, image_sha=args.image_sha256)
    scope = compile_campaign_scope(campaign_id=args.campaign_id, source_commit=source_commit, plan=authorized_plan)
    if args.scope_only:
        _write(args.output_root / "campaign_scope.json", scope.model_dump(mode="json"))
        print(json.dumps({"scope_sha256": scope.canonical_sha256(), "output_root": str(args.output_root), "decision": "awaiting_private_upload_authorization"}, ensure_ascii=False))
        return
    if args.authorized_scope_sha256 != scope.canonical_sha256():
        raise PermissionError("scenario_evidence_scope_authorization_mismatch")
    _write(args.output_root / "campaign_scope.json", scope.model_dump(mode="json"))
    _write(args.output_root / "scope_receipt.json", {"scope_sha256": scope.canonical_sha256(), "campaign_id": scope.campaign_id, "consumed_at": _now()})
    remote_home = _ssh(args.host, "printf %s \"$HOME\"", timeout=120).stdout.strip()
    remote_root = f"{remote_home}/taskgenerator-data/r10-evidence-ab/{args.run_id}"
    _probe(args.host, remote_root, args.output_root)
    _write(args.output_root / "public_probe.json", {"decision": "pass", "created_at": _now()})
    image_sha = _image_digest(args.host)
    if image_sha != args.image_sha256:
        raise RuntimeError("scenario_evidence_remote_image_drift")
    experiment, staged = ScenarioEvidenceExperiment(), {}
    plan = authorized_plan
    sessions = plan.sessions
    for session in sessions:
        workspace = args.output_root / "staged" / session.session_id
        skill = skills[SCENARIOS[session.scenario_id]["skill_id"]]
        experiment.stage_session(workspace=workspace, session=session, bible=selected[session.scenario_id], rules=rules[selected[session.scenario_id].rule_set_id], skill=skill if session.condition == "with_skill" else None)
        staged[(session.scenario_id, session.condition)] = workspace
    _write(args.output_root / "experiment_plan.json", plan.model_dump(mode="json"))
    admissions = []
    for session in sessions:
        remote = f"{remote_root}/{session.session_id}"
        local = staged[(session.scenario_id, session.condition)]
        _run(["scp", "-r", str(local), f"{args.host}:{remote}"], timeout=240)
        executed = _ssh(args.host, "sh -s", input_text=_remote_session_script(remote), timeout=1900, check=False)
        completed = args.output_root / "completed" / session.session_id
        completed.mkdir(parents=True)
        _run(["scp", "-r", f"{args.host}:{remote}/.", str(completed)], timeout=240)
        _write(completed / "execution_diagnostics.json", {"finished_at": _now(), "exit_code": executed.returncode, "stdout": executed.stdout[-4000:], "stderr": executed.stderr[-4000:]})
        report = experiment.admit(session=session, workspace=completed, bible=selected[session.scenario_id])
        if executed.returncode:
            report = report.model_copy(update={"decision": "incomplete", "first_failure": f"codex_or_container_exit:{executed.returncode}"})
        _write(completed / "admission_report.json", report.model_dump(mode="json"))
        admissions.append(report)
    reviews = []
    if all(report.decision == "pass" for report in admissions):
        api_key = args.deepseek_key.read_text(encoding="utf-8").strip()
        if not api_key:
            raise ValueError("deepseek_key_missing")
        reviewer = OfficialDeepSeekConditionBlindReviewer()
        for scenario_id in SCENARIOS:
            bible = selected[scenario_id]
            order, payload = experiment.blind_payload(seed=seeds[bible.work_seed_id], rules=rules[bible.rule_set_id], workspaces={condition: args.output_root / "completed" / f"{scenario_id}__{condition}" for condition in ("without_skill", "with_skill")}, scenario_id=scenario_id)
            reviews.append(reviewer.review(scenario_id=scenario_id, bundle_order=order, payload=payload, api_key=api_key, output_root=args.output_root / "blind_reviews" / scenario_id))
    result = aggregate_experiment(plan=plan, admissions=admissions, reviews=reviews)
    _write(args.output_root / "experiment_result.json", result.model_dump(mode="json"))
    print(json.dumps({"decision": result.decision, "reasons": result.reasons, "output_root": str(args.output_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
