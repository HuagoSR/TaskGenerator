"""Run the R10 Codex Skill Compiler and independent DeepSeek content review."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from task_generator.core.scenario_first import ProfessionalRuleSetV1
from task_generator.planning.work_seed_admission import WorkSeedCandidateV1
from task_generator.substrate.professional_skill_compiler import OfficialDeepSeekSkillContentReviewer, SkillCompilerManifestV1, admit_compiled_skill, sha256_json, tree_sha256
from task_generator.substrate.professional_skills import ProfessionalSkillLoader

IMAGE = "taskgenerator-eval:milestone-r9-huago-cone-746ff9b55f1b"


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run(command: list[str], *, input_text: str | None = None, timeout: int = 1900, check: bool = True):
    raw = subprocess.run(command, input=input_text.encode("utf-8") if input_text else None, capture_output=True, timeout=timeout)
    result = subprocess.CompletedProcess(command, raw.returncode, raw.stdout.decode("utf-8", "replace"), raw.stderr.decode("utf-8", "replace"))
    if check and result.returncode:
        raise RuntimeError(f"command_failed:{result.returncode}:{result.stderr[-800:]}")
    return result


def _ssh(host: str, command: str, *, input_text: str | None = None, timeout: int = 1900, check: bool = True):
    return _run(["ssh", "-o", "BatchMode=yes", host, command], input_text=input_text, timeout=timeout, check=check)


def _remote_script(workspace: str) -> str:
    lines = [
        "set -eu", f"workspace='{workspace}'", 'auth_file="$HOME/.codex/auth.json"', 'test -r "$auth_file"', 'cd "$workspace"',
        'timeout --preserve-status 1800 docker run -i --rm --init --read-only --cap-drop ALL --security-opt no-new-privileges:true --user 1000:1000 --memory 3g --cpus 2 --pids-limit 256 --tmpfs /tmp:rw,nosuid,nodev,size=512m --tmpfs /home/taskgenerator/.cache:rw,nosuid,nodev,size=512m --tmpfs /home/taskgenerator/.local:rw,nosuid,nodev,size=512m --tmpfs /home/taskgenerator/.config:rw,nosuid,nodev,size=256m -v "$workspace:/workspace:rw" -v "$auth_file:/run/codex-auth/auth.json:ro" -w /workspace --entrypoint /bin/sh ' + IMAGE + " -s > docker_stdout.txt 2> docker_stderr.txt <<'INNER'",
        'set -eu', 'mkdir -p .codex', 'ln -sf /run/codex-auth/auth.json .codex/auth.json', "trap 'rm -rf /workspace/.codex' EXIT", 'export CODEX_HOME=/workspace/.codex',
        'codex --ask-for-approval never --model gpt-5.6-sol exec -c project_doc_max_bytes=0 -c agents.enabled=false --disable plugins --disable apps --disable multi_agent --disable skill_search --json --ephemeral --ignore-user-config --ignore-rules --sandbox danger-full-access --skip-git-repo-check -C /workspace - < TASK.md > codex.jsonl 2> stderr.txt', 'INNER',
    ]
    return "\n".join(lines) + "\n"


def _stage(args: argparse.Namespace) -> tuple[dict, dict]:
    loader = ProfessionalSkillLoader()
    catalog = loader.load_catalog(args.skill_catalog)
    sources = json.loads(args.curation_sources.read_text(encoding="utf-8"))
    seeds = [item for item in json.loads(args.work_seeds.read_text(encoding="utf-8")) if item["status"] == "admitted"]
    rules = [ProfessionalRuleSetV1.model_validate(item).model_dump(mode="json") for item in json.loads(args.rule_sets.read_text(encoding="utf-8"))]
    feedback = json.loads(args.feedback.read_text(encoding="utf-8"))
    selected_entries = [entry for entry in catalog.entries if not args.skill_ids or entry.skill_id in args.skill_ids]
    if not selected_entries:
        raise ValueError("requested_skill_ids_not_in_catalog")
    selected_ids = {entry.skill_id for entry in selected_entries}
    selected_catalog = catalog.model_copy(update={"entries": selected_entries})
    selected_sources = [source for source in sources if source["skill_id"] in selected_ids]
    root = args.output_root / "compiler"
    inputs = root / "inputs"
    inputs.mkdir(parents=True)
    for name, value in {"catalog.json": selected_catalog.model_dump(mode="json"), "public_sources.json": {"sources": selected_sources}, "work_seeds.json": {"seeds": seeds}, "professional_rules.json": {"rules": rules}, "previous_blind_feedback.json": {"blind_reviews": feedback.get("blind_reviews", [])}}.items():
        _write(inputs / name, value)
    for entry in selected_entries:
        try:
            loaded = loader.load_skill(entry, skills_root=args.skills_root)
        except Exception:
            if entry.status != "draft":
                raise
            continue
        package = inputs / "current_skills" / entry.relative_path
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(loaded.skill_markdown, encoding="utf-8")
        for relative, content in loaded.reference_markdown.items():
            target = package / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    (root / "TASK.md").write_text("You are a Skill Compiler Agent. Read inputs/ and create factory-side Skill packages in compiled_skills/, one directory per selected catalog relative_path, each containing SKILL.md and references/source-map.md. Preserve catalog name and description exactly. You may consult official PCAOB, Acquisition.gov, or DAU material. Write concise occupational-situation review guidance: roles, trigger, natural source-system materials, plausible gaps, and what must remain for the candidate to decide. Do not prescribe candidate/teacher paths, fixed file layouts, answer labels, company facts, amounts, task answers, or generic file-tool procedures. Source maps must cite official URLs and explain how each source constrains the guidance. Previous blind feedback is diagnosis only; do not recreate old files. Do not alter inputs/.\n", encoding="utf-8")
    return {entry.skill_id: entry for entry in selected_entries}, {"catalog": selected_catalog.model_dump(mode="json"), "sources": selected_sources, "seeds": seeds, "rules": rules, "feedback": feedback.get("blind_reviews", [])}


def _public_probe(args: argparse.Namespace) -> None:
    probe = args.output_root / "public_probe"
    probe.mkdir(parents=True)
    (probe / "TASK.md").write_text("Create compiled_skills/probe.txt containing the words 'public compiler probe'. Do not access any private input.\n", encoding="utf-8")
    home = _ssh(args.host, 'printf %s "$HOME"', timeout=120).stdout.strip()
    remote = f"{home}/taskgenerator-data/r10-skill-compiler/{args.run_id}/public_probe"
    _ssh(args.host, f"mkdir -p '{remote.rsplit('/', 1)[0]}' && rm -rf '{remote}'", timeout=120)
    _run(["scp", "-r", str(probe), f"{args.host}:{remote}"], timeout=180)
    executed = _ssh(args.host, "sh -s", input_text=_remote_script(remote), timeout=1900, check=False)
    completed = probe / "completed"
    completed.mkdir()
    _run(["scp", "-r", f"{args.host}:{remote}/.", str(completed)], timeout=180)
    _write(probe / "diagnostics.json", {"exit_code": executed.returncode, "stdout": executed.stdout[-4000:], "stderr": executed.stderr[-4000:]})
    if executed.returncode or not (completed / "compiled_skills" / "probe.txt").is_file():
        raise RuntimeError("public_skill_compiler_probe_failed")
    _write(args.output_root / "public_probe.json", {"decision": "pass"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", default="r10_skill_compiler_20260830")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/r10/r10_skill_compiler_20260830")
    parser.add_argument("--skill-catalog", type=Path, default=ROOT / "data/r10/professional_skills/catalog.json")
    parser.add_argument("--curation-sources", type=Path, default=ROOT / "data/r10/professional_skills/curation_sources.json")
    parser.add_argument("--work-seeds", type=Path, default=ROOT / "data/r10/work_seeds/candidate_work_seeds.json")
    parser.add_argument("--rule-sets", type=Path, default=ROOT / "data/r10/work_seeds/professional_rule_sets.json")
    parser.add_argument("--skills-root", type=Path, default=ROOT / ".agents/skills/r10")
    parser.add_argument("--feedback", type=Path, default=ROOT / "artifacts/r10/r10_5_skill_evidence_ab_restart2_execute1/experiment_result.json")
    parser.add_argument("--deepseek-key", type=Path, default=ROOT / "deepseek-key.txt")
    parser.add_argument("--public-probe", action="store_true")
    parser.add_argument("--review-compiled-root", type=Path)
    parser.add_argument("--only-skill-id")
    parser.add_argument("--skill-id", dest="skill_ids", action="append", default=[])
    args = parser.parse_args()
    if args.output_root.exists():
        raise FileExistsError("skill_compiler_output_already_exists")
    if args.public_probe:
        _public_probe(args)
        print(json.dumps({"decision": "pass", "output_root": str(args.output_root)}, ensure_ascii=False))
        return
    if args.review_compiled_root:
        args.output_root.mkdir(parents=True)
        loader = ProfessionalSkillLoader()
        catalog = loader.load_catalog(args.skill_catalog)
        selected_ids = set(args.skill_ids)
        if args.only_skill_id:
            selected_ids.add(args.only_skill_id)
        entries = [entry for entry in catalog.entries if not selected_ids or entry.skill_id in selected_ids]
        if not entries:
            raise ValueError("requested_skill_id_not_in_catalog")
        key = args.deepseek_key.read_text(encoding="utf-8").strip()
        reviews = [OfficialDeepSeekSkillContentReviewer().review(entry=entry, package_root=args.review_compiled_root / entry.relative_path, api_key=key) for entry in entries]
        _write(args.output_root / "content_reviews.json", {"reviews": [item.model_dump(mode="json") for item in reviews]})
        decision = "pass" if all(item.decision == "pass" for item in reviews) else ("incomplete" if any(item.decision == "incomplete" for item in reviews) else "blocked")
        print(json.dumps({"decision": decision, "output_root": str(args.output_root)}, ensure_ascii=False))
        return
    entries, payload = _stage(args)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    manifest = SkillCompilerManifestV1(source_commit=commit, input_sha256=sha256_json(payload), decision="incomplete")
    _write(args.output_root / "compiler_manifest.json", manifest.model_dump(mode="json"))
    scope = {"scope_version": "r10.skill_compiler_campaign_scope.1", "source_commit": commit, "input_sha256": manifest.input_sha256, "compiler_model": "gpt-5.6-sol", "content_reviewer": "deepseek-v4-pro", "compiler_call_limit": 1, "review_call_limit": 2, "excluded_actions": ["task_compilation", "solver", "grader", "production_release"]}
    _write(args.output_root / "campaign_scope.json", scope)
    _write(args.output_root / "scope_receipt.json", {"scope_sha256": sha256_json(scope), "consumed_at": datetime.now(UTC).isoformat()})
    home = _ssh(args.host, 'printf %s "$HOME"', timeout=120).stdout.strip()
    remote = f"{home}/taskgenerator-data/r10-skill-compiler/{args.run_id}/compiler"
    _ssh(args.host, f"mkdir -p '{remote.rsplit('/', 1)[0]}' && rm -rf '{remote}'", timeout=120)
    _run(["scp", "-r", str(args.output_root / "compiler"), f"{args.host}:{remote}"], timeout=240)
    executed = _ssh(args.host, "sh -s", input_text=_remote_script(remote), timeout=1900, check=False)
    completed = args.output_root / "completed"
    completed.mkdir()
    _run(["scp", "-r", f"{args.host}:{remote}/.", str(completed)], timeout=240)
    _write(completed / "execution_diagnostics.json", {"exit_code": executed.returncode, "stdout": executed.stdout[-4000:], "stderr": executed.stderr[-4000:]})
    compiled = completed / "compiled_skills"
    forbidden = {"heliotrack", "harborview", "correct treatment", "scenario_audit", "scenario_procurement"}
    errors = {skill_id: admit_compiled_skill(entry=entry, package_root=compiled / entry.relative_path, forbidden_terms=forbidden) for skill_id, entry in entries.items()} if executed.returncode == 0 and compiled.is_dir() else {skill_id: ["compiler_agent_or_output_failure"] for skill_id in entries}
    _write(args.output_root / "compiler_admission.json", {"errors": errors})
    if any(errors.values()):
        _write(args.output_root / "compiler_manifest.json", manifest.model_copy(update={"decision": "blocked", "first_failure": "compiled_skill_admission_failed"}).model_dump(mode="json"))
        print(json.dumps({"decision": "blocked", "errors": errors}, ensure_ascii=False))
        return
    key = args.deepseek_key.read_text(encoding="utf-8").strip()
    reviews = [OfficialDeepSeekSkillContentReviewer().review(entry=entry, package_root=compiled / entry.relative_path, api_key=key) for entry in entries.values()]
    _write(args.output_root / "content_reviews.json", {"reviews": [item.model_dump(mode="json") for item in reviews]})
    decision = "pass" if all(item.decision == "pass" for item in reviews) else ("incomplete" if any(item.decision == "incomplete" for item in reviews) else "blocked")
    _write(args.output_root / "compiler_manifest.json", manifest.model_copy(update={"decision": decision, "output_sha256": tree_sha256(compiled)}).model_dump(mode="json"))
    print(json.dumps({"decision": decision, "output_root": str(args.output_root)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
