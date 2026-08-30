"""Generate one frozen, with-Skill evidence bundle per remaining R10 scenario."""

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

from run_r10_scenario_evidence_ab import IMAGE, _image_digest, _probe, _remote_session_script, _run, _ssh
from task_generator.core.scenario_first import ProfessionalRuleSetV1, ScenarioBibleV1
from task_generator.planning.scenario_evidence_experiment import ScenarioEvidenceExperiment, ScenarioEvidenceSessionV1
from task_generator.substrate.professional_skills import ProfessionalSkillLoader


SCENARIOS = {
    "scenario_audit_control_deficiency_aggregation": {
        "domain": "audit_compliance", "skill_id": "r10.audit-control-deficiency-evaluation",
    },
    "scenario_procurement_acceptance_disposition": {
        "domain": "procurement_operations", "skill_id": "r10.procurement-delivery-acceptance",
    },
}
BIBLES = ROOT / "artifacts" / "r10" / "r10_2_scenario_bible_batch_20260829_distribution_repair" / "bibles"
RULE_SETS = ROOT / "data" / "r10" / "work_seeds" / "professional_rule_sets.json"
CATALOG = ROOT / "data" / "r10" / "professional_skills" / "catalog.json"
SKILLS = ROOT / ".agents" / "skills" / "r10"
IMAGE_SHA256 = "02b79e7f6c1b9966918fc986c7624f50c2f45c6e32a5502bc30f65ccd328a722"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", default="r10_7a_evidence_generation")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts" / "r10" / "r10_7a_evidence_generation")
    parser.add_argument("--image-sha256", default=IMAGE_SHA256)
    args = parser.parse_args()
    if args.output_root.exists():
        raise FileExistsError("r10_7a_evidence_output_already_exists")

    bibles = {path.stem: ScenarioBibleV1.model_validate_json(path.read_text(encoding="utf-8")) for path in BIBLES.glob("*.json")}
    rules = {item.rule_set_id: item for item in (ProfessionalRuleSetV1.model_validate(value) for value in json.loads(RULE_SETS.read_text(encoding="utf-8")))}
    loader = ProfessionalSkillLoader()
    catalog = loader.load_catalog(CATALOG)
    experiment, sessions, staged = ScenarioEvidenceExperiment(), [], {}
    selected: dict[str, tuple[ScenarioBibleV1, Any]] = {}
    for scenario_id, config in SCENARIOS.items():
        bible = bibles[scenario_id]
        entry = next(item for item in catalog.entries if item.skill_id == config["skill_id"] and item.status == "curated")
        selected[scenario_id] = (bible, loader.load_skill(entry, skills_root=SKILLS))
    image_sha = _image_digest(args.host)
    if image_sha != args.image_sha256:
        raise RuntimeError("scenario_evidence_remote_image_drift")
    for scenario_id, (bible, skill) in selected.items():
        rule_set = rules[bible.rule_set_id]
        session = ScenarioEvidenceSessionV1(
            session_id=f"{scenario_id}__with_skill", scenario_id=scenario_id,
            domain=SCENARIOS[scenario_id]["domain"], condition="with_skill",
            bible_sha256=bible.canonical_sha256(), rule_set_sha256=rule_set.canonical_sha256(),
            skill_id=skill.entry.skill_id, skill_sha256=experiment.sha256_json(skill.model_dump(mode="json")),
            image=IMAGE, image_sha256=image_sha,
        )
        sessions.append(session)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=True).stdout.strip()
    scope = {"scope_version": "r10.7a_evidence_generation_scope.1", "campaign_id": args.run_id, "source_commit": commit, "sessions": [item.model_dump(mode="json") for item in sessions], "codex_session_limit": 2, "excluded_actions": ["task_compilation", "solver", "grader", "release", "training"]}
    args.output_root.mkdir(parents=True)
    _write(args.output_root / "campaign_scope.json", scope)
    _write(args.output_root / "scope_receipt.json", {"scope_sha256": experiment.sha256_json(scope), "status": "consumed", "consumed_at": _now()})
    home = _ssh(args.host, 'printf %s "$HOME"', timeout=120).stdout.strip()
    remote_root = f"{home}/taskgenerator-data/r10-evidence-generation/{args.run_id}"
    _probe(args.host, remote_root, args.output_root)
    _write(args.output_root / "public_probe.json", {"decision": "pass", "created_at": _now()})
    reports = []
    for session in sessions:
        bible, skill = selected[session.scenario_id]
        local = args.output_root / "staged" / session.session_id
        experiment.stage_session(workspace=local, session=session, bible=bible, rules=rules[bible.rule_set_id], skill=skill)
        remote = f"{remote_root}/{session.session_id}"
        _run(["scp", "-r", str(local), f"{args.host}:{remote}"], timeout=240)
        result = _ssh(args.host, "sh -s", input_text=_remote_session_script(remote), timeout=1900, check=False)
        completed = args.output_root / "completed" / session.session_id
        completed.mkdir(parents=True)
        _run(["scp", "-r", f"{args.host}:{remote}/.", str(completed)], timeout=240)
        _write(completed / "execution_diagnostics.json", {"exit_code": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]})
        report = experiment.admit(session=session, workspace=completed, bible=bible)
        if result.returncode:
            report = report.model_copy(update={"decision": "incomplete", "first_failure": f"codex_or_container_exit:{result.returncode}"})
        _write(completed / "admission_report.json", report.model_dump(mode="json"))
        reports.append(report.model_dump(mode="json"))
    decision = "pass" if all(item["decision"] == "pass" for item in reports) else "incomplete"
    _write(args.output_root / "generation_result.json", {"result_version": "r10.7a_evidence_generation_result.1", "decision": decision, "reports": reports})
    print(json.dumps({"decision": decision, "output_root": str(args.output_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
