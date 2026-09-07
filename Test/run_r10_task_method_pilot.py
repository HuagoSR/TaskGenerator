"""One authorized 24-session method cycle; separate development and frozen validation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "Test")]
import run_r10_process_first_pilot as base
from task_generator.production import task_method_pilot as method
from task_generator.planning.rubric_compiler_v2 import TaskSpecificRubricV2

read, write, sha, tree = base.read, base.write, base.sha, base.tree
HOST, IMAGE, IMAGE_SHA = base.HOST, base.IMAGE, base.IMAGE_SHA
DEPENDENCY_RUN = ROOT / "artifacts/r10/r10_process_first_pilot_20260905"
REMOTE_BASE = "/home/huagosr/taskgenerator-data/r10-task-method"
STAGES = method.STAGES


def now():
    return datetime.now(timezone.utc).isoformat()


def seconds_left(receipt, cap=1800):
    deadline = receipt.get("deadline_epoch")
    left = cap if deadline is None else min(cap, int(deadline - time.time()))
    if left < 1:
        raise RuntimeError("global_budget_exhausted")
    return left


def code_hashes():
    return base.code_hashes()


def public_inputs(destination, spec):
    sources = [ROOT / "data/r10/work_seeds/candidate_work_seeds.json",
               ROOT / "data/r10/work_seeds/professional_rule_sets.json",
               ROOT / "data/r10/professional_skills/curation_sources.json"]
    seed = next(r["seed"] for r in read(sources[0]) if r["status"] == "admitted" and r["seed"]["seed_id"] == spec["seed"])
    rules = next(r for r in read(sources[1]) if r["domain"] == spec["domain"])
    provenance = read(sources[2])
    if isinstance(provenance, dict):
        provenance = provenance["sources"]
    write(destination / "work_seed.json", seed)
    write(destination / "professional_rules.json", rules)
    write(destination / "sources.json", [r for r in provenance if r["skill_id"] == "r10." + spec["skill"]])
    # Preserve the admitted seed; explicitly distinguish its purpose from a verdict.
    write(destination / "public_context.json", {**{k: seed[k] for k in ("role", "trigger_event", "business_goal", "audience")},
          "interpretation": "The business goal is an inquiry, not a required affirmative conclusion; evidence may justify bounded findings and specific follow-up."})
    skill = ROOT / ".agents/skills/r10" / spec["skill"]
    for name in ("SKILL.md", "references/source-map.md"):
        source = skill / name
        sources.append(source)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sources}


def snapshot_code(root, phase):
    hashes = code_hashes()
    for relative in hashes:
        target = root / "execution_code" / phase / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return hashes


def prepare(root, phase, amendment=None, dependency_lock=None, dependency_remote=None):
    if root.parent.resolve() != (ROOT / "artifacts/r10").resolve() or not re.fullmatch(r"[a-zA-Z0-9_-]+", root.name):
        raise ValueError("unsafe_run_root")
    if phase == "development":
        if root.exists():
            raise FileExistsError("run_directory_exists")
        root.mkdir()
        sources = {}
        for spec in method.CASES:
            sources.update(public_inputs(root / "public" / spec["id"], spec))
        shutil.copyfile(base.WORKER, root / "tools.py")
        lock = dependency_lock or DEPENDENCY_RUN / "dependency_lock.json"
        if read(lock).get("pins") != base.PINS:
            raise ValueError("fixed_dependency_pins_required")
        shutil.copyfile(lock, root / "dependency_lock.json")
        dependency_remote = dependency_remote or "/home/huagosr/taskgenerator-data/r10-process-first/r10_process_first_pilot_20260905"
        if not re.fullmatch(r"/home/huagosr/taskgenerator-data/[A-Za-z0-9_/-]+", dependency_remote) or ".." in dependency_remote:
            raise ValueError("unsafe_dependency_location")
        scope = {"created_at": now(), "cases": method.CASES, "stages": list(STAGES),
                 "max_sessions": 24, "max_recoveries": 2, "max_session_seconds": 1800, "total_seconds": 43200,
                 "models": {"generate_compile_solve": "gpt-5.6-sol@chatgpt_codex/high", "mine_review": "deepseek-v4-pro@official_opencode/max"},
                 "source_hashes": sources, "public_hashes": tree(root / "public"), "helper_sha256": sha(root / "tools.py"),
                 "dependency_lock_sha256": sha(root / "dependency_lock.json"),
                 "dependency_remote": dependency_remote,
                 "host": HOST, "image": IMAGE, "image_sha256": IMAGE_SHA,
                 "remote": f"{REMOTE_BASE}/{root.name}", "token_or_money_hard_cap": None,
                 "authorization": "User approved method cycle: 1 development + 4 frozen validation worlds, 20 production sessions, 2 native Sol trials, 2 technical recoveries, 12 hours serial. No grading or ranking.",
                 "isolation": "Each anonymous session reads stage-only readonly inputs; candidate, supervision, hidden records and evidence separate; no GDPval or historical task content.",
                 "independent_case_failure": "retain first result, skip dependent stages, continue next planned case; global auth/isolation/input/budget faults halt"}
        write(root / "scope.json", scope)
        write(root / "initial_git.json", {"status": base._run(["git", "status", "--porcelain"]).stdout,
              "index_sha256": sha(ROOT / ".git/index"), "baseline_files": {p: sha(ROOT / p) for p in sources}})
        write(root / "receipt.json", {"status": "preparing", "sessions": [], "cases": {}, "first_failure": None,
              "recoveries_used": 0, "task_level_manual_edits": 0, "scope_sha256": sha(root / "scope.json")})
    else:
        receipt = read(root / "receipt.json")
        if receipt["status"] != "development_complete" or (root / "methods/validation").exists():
            raise ValueError("validation_requires_closed_development_and_one_freeze")
        verify_master(root)
        if amendment is None or not amendment.is_file():
            raise ValueError("explicit_generic_method_amendment_required")
        seconds_left(receipt)
    method_dir = root / "methods" / phase
    method_dir.mkdir(parents=True)
    clarification = amendment.read_text(encoding="utf-8") if amendment else ""
    for stage, prompt in method.prompts(clarification).items():
        # The two trial sessions use the same candidate-only harness, without development hints.
        if stage == "solve":
            prompt = method.prompts()["solve"]
        (method_dir / f"{stage}.md").write_text(prompt, encoding="utf-8")
    write(method_dir / "freeze.json", {"phase": phase, "created_at": now(),
          "prompt_hashes": tree(method_dir), "code_hashes": snapshot_code(root, phase),
          "amendment": clarification, "development_evidence_hashes": tree(root / "results/dev_01") if phase == "validation" else {},
          "scope_sha256": sha(root / "scope.json")})
    receipt = read(root / "receipt.json")
    receipt.update(status=f"{phase}_prepared")
    receipt.setdefault("freeze_hashes", {})[phase] = sha(method_dir / "freeze.json")
    write(root / "receipt.json", receipt)
    return {"status": receipt["status"], "scope_sha256": receipt["scope_sha256"]}


def verify_master(root):
    receipt, scope = read(root / "receipt.json"), read(root / "scope.json")
    if sha(root / "scope.json") != receipt["scope_sha256"] or scope["cases"] != method.CASES or scope["stages"] != list(STAGES):
        raise RuntimeError("global_scope_changed")
    if (scope["max_sessions"], scope["max_recoveries"], scope["max_session_seconds"], scope["total_seconds"]) != (24, 2, 1800, 43200):
        raise RuntimeError("global_budget_scope_changed")
    if scope["public_hashes"] != tree(root / "public") or any(sha(ROOT / p) != h for p, h in scope["source_hashes"].items()):
        raise RuntimeError("global_public_input_changed")
    if scope["helper_sha256"] != sha(root / "tools.py") or scope["dependency_lock_sha256"] != sha(root / "dependency_lock.json"):
        raise RuntimeError("global_dependency_changed")
    for session in receipt["sessions"]:
        if session.get("output_hashes") and tree(root / session["raw_path"]) != session["output_hashes"]:
            raise RuntimeError("global_prior_output_changed")
        if session.get("derived_hashes") and tree(root / session["derived_path"]) != session["derived_hashes"]:
            raise RuntimeError("global_derived_input_changed")
    return scope


def verify_bindings(root, phase):
    scope = verify_master(root)
    directory = root / "methods" / phase
    receipt, frozen = read(root / "receipt.json"), read(directory / "freeze.json")
    expected_code = frozen["code_hashes"]
    recovery = receipt.get("controller_recovery")
    if recovery and recovery["phase"] == phase:
        if sha(root / recovery["path"]) != recovery["sha256"]:
            raise RuntimeError("global_recovery_binding_changed")
        record = read(root / recovery["path"])
        expected_code = record["code_hashes"]
        if sha(root / record["first_receipt_path"]) != record["first_receipt_sha256"]:
            raise RuntimeError("global_original_failure_receipt_changed")
        if tree(root / record["raw_path"]) != record["raw_hashes"]:
            raise RuntimeError("global_recovered_raw_changed")
    if sha(directory / "freeze.json") != receipt["freeze_hashes"][phase] or expected_code != code_hashes():
        raise RuntimeError("global_frozen_code_changed")
    if any(sha(directory / p) != h for p, h in frozen["prompt_hashes"].items()):
        raise RuntimeError("global_method_changed")
    if phase == "validation" and tree(root / "results/dev_01") != frozen["development_evidence_hashes"]:
        raise RuntimeError("global_development_evidence_changed")
    return scope


def recover_controller(root, phase):
    """Revalidate one returned output; preserve first stop, no repeated model turn."""
    receipt = read(root / "receipt.json")
    if phase != "development" or receipt["status"] != "development_complete" or receipt.get("controller_recovery"):
        raise ValueError("not_the_development_controller_recovery_boundary")
    verify_master(root)
    session = receipt["sessions"][-1]
    if session["status"] != "incomplete" or not session.get("usage", {}).get("completed") or not session.get("raw_path"):
        raise ValueError("no_completed_raw_response_to_revalidate")
    # Closed allowlist: this is a controller-only error, not a semantic redraw.
    if session["stage"] != "mine" or session["first_failure"] != "reference_not_in_stage_allowlist":
        raise ValueError("unsupported_controller_recovery")
    frozen = read(root / "methods" / phase / "freeze.json")
    if any(sha(root / "methods" / phase / p) != h for p, h in frozen["prompt_hashes"].items()):
        raise ValueError("recovery_cannot_change_prompts")
    raw = root / session["raw_path"]
    outcome = validate("mine", raw, root / "staging" / f'{session["ordinal"]:02d}' / "inputs")
    if outcome["status"] != "completed":
        raise ValueError("recovered_task_not_structurally_complete")
    directory = root / "controller_recovery"
    directory.mkdir()
    shutil.copyfile(root / "receipt.json", directory / "first_stop_receipt.json")
    derived = raw.parent / "derived"
    write(derived / "deliverable_contract.json", outcome.pop("contract"))
    (derived / "candidate_task.md").write_text(outcome.pop("candidate_task"), encoding="utf-8")
    record = {"created_at": now(), "phase": phase, "session": session["ordinal"],
              "first_receipt_path": "controller_recovery/first_stop_receipt.json",
              "first_receipt_sha256": sha(directory / "first_stop_receipt.json"),
              "raw_path": session["raw_path"], "raw_hashes": tree(raw), "outcome": outcome,
              "code_hashes": snapshot_code(root, "development_controller_recovery"),
              "model_calls_for_repair": 0, "original_response_modified": False,
              "reason": "Mining may cite its explicitly supplied public role/trigger context; rubric grounding remains candidate-only."}
    write(directory / "recovery.json", record)
    receipt["controller_recovery"] = {"phase": phase, "path": "controller_recovery/recovery.json", "sha256": sha(directory / "recovery.json")}
    session.update(derived_path=derived.relative_to(root).as_posix(), derived_hashes=tree(derived))
    receipt["status"] = "development_prepared"
    write(root / "receipt.json", receipt)
    return {"status": receipt["status"], "revalidated_session": session["ordinal"], "new_model_calls": 0}


def completed_outcome(root, receipt, case_id, stage):
    matches = [s for s in receipt["sessions"] if s["case"] == case_id and s["stage"] == stage]
    if not matches:
        return None
    session = matches[-1]
    if session["status"] == "completed":
        return session["outcome"]
    recovery = receipt.get("controller_recovery")
    if recovery:
        record = read(root / recovery["path"])
        if record["session"] == session["ordinal"]:
            return record["outcome"]
    raise ValueError("cannot_resume_a_started_or_terminal_semantic_session")


def environment(root, receipt):
    scope = read(root / "scope.json")
    remote, deps = scope["remote"], scope["dependency_remote"]
    base._ssh(HOST, f"mkdir -p {shlex.quote(REMOTE_BASE)} && mkdir {shlex.quote(remote)}", timeout=seconds_left(receipt, 60))
    base._run(base._scp_command(str(root / "public/dev_01"), f"{HOST}:{remote}/public"), timeout=seconds_left(receipt, 90))
    identity = base._ssh(HOST, f"docker image inspect --format '{{{{.Id}}}}' {IMAGE}", timeout=seconds_left(receipt, 60)).stdout.strip().removeprefix("sha256:")
    hashes = base._ssh(HOST, f"sha256sum {deps}/deps/lock.json {deps}/tools.py", timeout=seconds_left(receipt, 60)).stdout.splitlines()
    if identity != IMAGE_SHA or [x.split()[0] for x in hashes] != [sha(root / "dependency_lock.json"), sha(root / "tools.py")]:
        raise RuntimeError("global_remote_identity_changed")
    for action, target in (("verify-dependencies", "/deps"), ("smoke", "/tmp/smoke")):
        cmd = base.docker_base(deps) + ["-e", "PYTHONPATH=/deps/site", "-v", f"{deps}/deps:/deps:ro", "-v", f"{deps}/tools.py:/tools.py:ro", "-v", f"{remote}/public:/inputs:ro", "--entrypoint", "python", IMAGE, "/tools.py", action, target]
        result = base._ssh(HOST, shlex.join(cmd), timeout=seconds_left(receipt, 180), check=False)
        (root / f"{action}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("global_environment_check_failed")
    write(root / "environment.json", {"checked_at": now(), "image": identity, "dependencies": "verified", "offline_smoke": "passed", "credentials": "not_read_or_copied"})


def stage_inputs(root, spec, stage, target):
    target.mkdir(parents=True)
    public = root / "public" / spec["id"]
    results = root / "results" / spec["id"]
    if stage == "generate":
        shutil.copytree(public, target, dirs_exist_ok=True)
        return
    shutil.copytree(results / "generate/raw/candidate", target / "reference_files")
    if stage != "solve":
        shutil.copyfile(public / "public_context.json", target / "public_context.json")
    if stage in {"compile", "review"}:
        for name in ("professional_rules.json", "sources.json"):
            shutil.copyfile(public / name, target / name)
    if stage in {"compile", "review", "solve"}:
        for name in ("candidate_task.md", "deliverable_contract.json"):
            shutil.copyfile(results / "mine/derived" / name, target / name)
        if stage != "solve":
            shutil.copyfile(results / "mine/raw/task.json", target / "task.json")
    if stage == "compile":
        write(target / "rubric_schema.json", TaskSpecificRubricV2.model_json_schema())
    if stage == "review":
        for name in ("supervision.json", "new_rubric.json"):
            shutil.copyfile(results / "compile/raw" / name, target / name)


def validate(stage, raw, inputs):
    tree(raw)
    if stage == "generate":
        base.validate_result("generate", raw)
        actual = set(tree(raw / "candidate"))
        records = read(raw / "hidden/manifest.json")["records"]
        if len(records) != len(actual) or {r["path"] for r in records} != actual:
            raise ValueError("manifest_coverage")
        for row in records:
            base.check_reference(raw / "candidate", row["path"])
            if not row.get("producer") or not row.get("business_purpose") or not isinstance(row.get("source_dependencies"), list):
                raise ValueError("manifest_provenance_missing")
        return {"status": "completed"}
    if stage == "mine":
        return method.task_result(raw, inputs)
    if stage == "compile":
        return method.compilation_result(raw, inputs)
    if stage == "review":
        return method.review_result(raw, inputs)
    contract = read(inputs / "deliverable_contract.json")
    expected = {r["relative_path"] for r in contract["deliverables"]}
    actual = set(tree(raw))
    return {"status": "completed", "delivery_status": "valid" if actual == expected else "invalid",
            "missing": sorted(expected - actual), "extra": sorted(actual - expected), "professional_correctness": "not_scored"}


def transport_script(stage):
    return base.agent_script("generate" if stage in {"generate", "compile", "solve"} else "review")


def authentication_failed(returncode, usage, stderr, native):
    # Business records can discuss unauthorized transactions. Only actual failed
    # transport/error events may establish an authentication failure.
    if returncode == 0 and usage.get("completed") and not usage.get("error_events"):
        return False
    errors = [stderr]
    for line in native.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") in {"error", "turn.failed"}:
            errors.append(json.dumps(event))
    return bool(re.search(r'(?i)(?:http[^\n]{0,20}\b(?:401|403)\b|invalid[_ ]api[_ ]key|authentication[_ ](?:failed|error)|unauthorized)', "\n".join(errors)))


def count_session(receipt, case, stage, retry=False):
    existing = [s for s in receipt["sessions"] if s["case"] == case and s["stage"] == stage]
    if len(receipt["sessions"]) >= 24:
        raise RuntimeError("global_session_budget_exhausted")
    if retry:
        if len(existing) != 1 or existing[0].get("status") != "presemantic_transport_failure" or receipt["recoveries_used"] >= 2:
            raise ValueError("recovery_not_authorized")
        receipt["recoveries_used"] += 1
    elif existing:
        raise ValueError("stage_already_started")
    seconds_left(receipt)


def run_session(root, spec, stage, phase, retry=False):
    receipt = read(root / "receipt.json")
    scope = verify_bindings(root, phase)
    count_session(receipt, spec["id"], stage, retry)
    index = len(receipt["sessions"]) + 1
    key = f"{index:02d}"
    workspace = root / "staging" / key
    stage_inputs(root, spec, stage, workspace / "inputs")
    shutil.copyfile(root / "methods" / phase / f"{stage}.md", workspace / "TASK.md")
    shutil.copyfile(root / "tools.py", workspace / "tools.py")
    (workspace / "agent.sh").write_bytes(transport_script(stage).encode())
    hashes = tree(workspace)
    remote = f'{scope["remote"]}/session_{key}'
    deps = scope["dependency_remote"]
    session = {"case": spec["id"], "stage": stage, "phase": phase, "ordinal": index, "retry": retry,
               "status": "staging", "input_hashes": hashes, "remote": remote, "first_failure": None}
    receipt["sessions"].append(session)
    write(root / "receipt.json", receipt)
    evidence_dir = root / "evidence" / key
    evidence_dir.mkdir(parents=True)
    try:
        base._ssh(HOST, f"mkdir {remote} && mkdir {remote}/output", timeout=seconds_left(receipt, 60))
        base._run(base._scp_command(str(workspace), f"{HOST}:{remote}/workspace"), timeout=seconds_left(receipt, 120))
        base.verify_remote_tree(remote + "/workspace", hashes, time.monotonic() + seconds_left(receipt, 120))
        if receipt.get("deadline_epoch") is None:
            receipt.update(started_at=now(), deadline_epoch=time.time() + 43200)
        cap = seconds_left(receipt)
        session.update(status="started", started_at=now(), timeout_seconds=cap)
        write(root / "receipt.json", receipt)
        print(f'{spec["id"]}/{stage}: session {index}/24 started ({cap}s)', flush=True)
        cmd = base.docker_base(deps, network=True) + ["-v", f"{remote}/workspace:/workspace:ro", "-v", f"{remote}/output:/output:rw", "-v", f"{deps}/deps:/deps:ro", "-w", "/workspace"]
        if stage in {"generate", "compile", "solve"}:
            cmd += ["-v", "/home/huagosr/taskgenerator-secrets/codex-auth-current:/run/codex-home:rw"]
        else:
            cmd += ["-v", "/home/huagosr/taskgenerator-secrets/deepseek_api_key:/run/secrets/deepseek_api_key:ro"]
        name = f"{root.name}-{key}"
        cmd[2:2] = ["--name", name, "--stop-timeout", "1"]
        cmd += ["--entrypoint", "/bin/sh", IMAGE, "/workspace/agent.sh"]
        command = f"trap 'timeout 3s docker stop -t 1 {name} >/dev/null 2>&1 || true' EXIT; timeout --signal=TERM --kill-after=1s {max(1, cap - 5)}s " + shlex.join(cmd) + f" > {remote}/agent.jsonl 2> {remote}/stderr.txt"
        start = time.monotonic()
        result = base._ssh(HOST, command, timeout=cap, check=False)
        session.update(returncode=result.returncode, elapsed_seconds=time.monotonic() - start)
        for filename in ("agent.jsonl", "stderr.txt"):
            base._run(base._scp_command(f"{HOST}:{remote}/{filename}", str(evidence_dir / filename)), timeout=seconds_left(receipt, 90))
        session["usage"] = base.usage(evidence_dir / "agent.jsonl")
        error_text = (evidence_dir / "stderr.txt").read_text(encoding="utf-8", errors="replace")
        native = (evidence_dir / "agent.jsonl").read_text(encoding="utf-8", errors="replace")
        if authentication_failed(result.returncode, session["usage"], error_text, native):
            raise RuntimeError("global_authentication_failure")
        if result.returncode or not session["usage"]["completed"] or session["usage"]["error_events"]:
            raise ValueError("agent_session_failed_no_semantic_redraw")
        cmd = base.docker_base(deps) + ["-e", "PYTHONPATH=/deps/site", "-v", f"{deps}/deps:/deps:ro", "-v", f"{deps}/tools.py:/tools.py:ro", "-v", f"{remote}/output:/output:ro", "--entrypoint", "python", IMAGE, "/tools.py", "validate-output", "/output"]
        opened = base._ssh(HOST, shlex.join(cmd), timeout=seconds_left(receipt, 180), check=False)
        (evidence_dir / "file_check.log").write_text(opened.stdout + opened.stderr, encoding="utf-8")
        if opened.returncode:
            if "unsafe_output_path" in opened.stderr or "hardlinked" in opened.stderr:
                raise RuntimeError("global_unsafe_output")
            # Readability failures stay on the server; never bypass the safety check to SCP.
            raise ValueError("necessary_file_not_readable_or_unexpected_output")
        raw = root / "results" / spec["id"] / stage / "raw"
        if raw.exists():
            raise RuntimeError("global_raw_directory_already_exists")
        raw.parent.mkdir(parents=True, exist_ok=True)
        base._run(base._scp_command(f"{HOST}:{remote}/output", str(raw)), timeout=seconds_left(receipt, 120))
        session.update(raw_path=raw.relative_to(root).as_posix(), output_hashes=tree(raw))
        if tree(workspace) != hashes:
            raise RuntimeError("global_staged_input_changed")
        base.verify_remote_tree(remote + "/workspace", hashes, time.monotonic() + seconds_left(receipt, 120))
        outcome = validate(stage, raw, workspace / "inputs")
        if stage == "generate":
            session["process_protocol"] = base.process_protocol(raw, evidence_dir / "agent.jsonl")
            if session["process_protocol"] == "unverified":
                outcome = {"status": "protocol_unverified"}
        if stage == "mine" and outcome["status"] == "completed":
            derived = raw.parent / "derived"
            write(derived / "deliverable_contract.json", outcome.pop("contract"))
            (derived / "candidate_task.md").write_text(outcome.pop("candidate_task"), encoding="utf-8")
            session.update(derived_path=derived.relative_to(root).as_posix(), derived_hashes=tree(derived))
        session.update(status="completed", outcome=outcome, completed_at=now())
    except Exception as exc:
        failure = str(exc)
        session.update(first_failure=failure, status="incomplete", stopped_at=now())
        if session.get("started_at") is None and not failure.startswith("global_"):
            session["status"] = "presemantic_transport_failure"
        receipt["first_failure"] = receipt.get("first_failure") or {"session": index, "reason": failure}
        write(root / "receipt.json", receipt)
        if failure.startswith("global_") or "remote_input_fingerprint_changed" in failure:
            raise RuntimeError(failure)
        outcome = {"status": session["status"], "reason": failure}
    write(root / "receipt.json", receipt)
    print(f'{spec["id"]}/{stage}: {outcome["status"]}', flush=True)
    return outcome


def export_package(root, spec):
    """Internal exchange copy; exact rubric retained, never mounted for Solver."""
    result = root / "results" / spec["id"]
    target = root / "packages" / spec["id"]
    if target.exists():
        raise FileExistsError("package_exists")
    target.mkdir(parents=True)
    shutil.copytree(result / "generate/raw/candidate", target / "reference_files")
    (target / "deliverable_files").mkdir()
    contract = read(result / "mine/derived/deliverable_contract.json")
    prompt = (result / "mine/derived/candidate_task.md").read_text(encoding="utf-8")
    rubric = read(result / "compile/raw/new_rubric.json")
    write(target / "deliverable_contract.json", contract)
    shutil.copyfile(result / "compile/raw/new_rubric.json", target / "rubric_v2.json")
    write(target / "dataset_row.json", {"task_id": spec["id"], "sector": spec["domain"],
          "occupation": read(root / "public" / spec["id"] / "public_context.json")["role"],
          "prompt": prompt, "reference_files": ["reference_files/" + p for p in tree(target / "reference_files")],
          "deliverable_files": [r["relative_path"] for r in contract["deliverables"]],
          "rubric": "Original Rubric V2 criteria retained in rubric_json and rubric_v2.json; provisional LLM-proxy.",
          "rubric_json": json.dumps(rubric["criteria"], ensure_ascii=False),
          "extra": {"internal_research_only": True, "professional_status": "provisional/LLM-proxy", "rubric_version": rubric["rubric_version"], "anonymous_rubric_task_id": rubric["task_id"]}})
    assert json.loads(read(target / "dataset_row.json")["rubric_json"]) == rubric["criteria"]
    return tree(target)


def execute(root, phase):
    receipt = read(root / "receipt.json")
    required = "validation_review_complete" if phase == "trials" else f"{phase}_prepared"
    if receipt["status"] != required:
        raise ValueError("phase_not_fresh_prepared")
    verify_bindings(root, "validation" if phase == "trials" else phase)
    checks = read(root / "readiness.json")
    if checks.get("code_hashes") != code_hashes() or not checks.get("tests_passed") or not checks.get("secret_diff_links_passed"):
        raise ValueError("nonpaid_readiness_checks_required")
    try:
        if phase == "development" and not receipt.get("controller_recovery"):
            environment(root, receipt)
        receipt.update(status=f"{phase}_running")
        write(root / "receipt.json", receipt)
        for spec in (s for s in method.CASES if s["phase"] == phase):
            case = {"status": "running", "quality": "not_reviewed", "stages": {}}
            for stage in STAGES:
                outcome = completed_outcome(root, read(root / "receipt.json"), spec["id"], stage)
                if outcome is None:
                    outcome = run_session(root, spec, stage, phase)
                if outcome["status"] == "presemantic_transport_failure" and read(root / "receipt.json")["recoveries_used"] < 2:
                    outcome = run_session(root, spec, stage, phase, retry=True)
                case["stages"][stage] = outcome
                if outcome["status"] != "completed":
                    case["status"] = outcome["status"]
                    case["skipped"] = list(STAGES[STAGES.index(stage) + 1:])
                    break
                if stage == "review":
                    case.update(status="completed", quality=outcome["quality"])
            receipt = read(root / "receipt.json")
            receipt["cases"][spec["id"]] = case
            write(root / "receipt.json", receipt)
        if phase == "trials":
            receipt = read(root / "receipt.json")
            admission = read(root / "admission_review.json")
            candidates = apply_admission_review(root, receipt, admission)
            receipt["admission_review_sha256"] = sha(root / "admission_review.json")
            selected = method.select_trials(candidates)
            receipt["trial_selection"] = selected
            for spec in method.CASES[1:]:
                receipt["cases"].setdefault(spec["id"], {"status": "not_started"})["effective_quality"] = candidates[spec["id"]]["quality"]
                if candidates[spec["id"]]["quality"] == "pass":
                    receipt["cases"][spec["id"]]["package_hashes"] = export_package(root, spec)
            write(root / "receipt.json", receipt)
            for case_id in selected:
                spec = next(s for s in method.CASES if s["id"] == case_id)
                outcome = run_session(root, spec, "solve", "validation")
                receipt = read(root / "receipt.json")
                receipt.setdefault("trials", {})[case_id] = outcome
                write(root / "receipt.json", receipt)
        receipt = read(root / "receipt.json")
        terminal = {"development": "development_complete", "validation": "validation_review_complete", "trials": "completed"}[phase]
        receipt.update(status=terminal, phase_stopped_at=now())
    except Exception as exc:
        receipt = read(root / "receipt.json")
        receipt.update(status="incomplete", stop_reason=str(exc), stopped_at=now())
    write(root / "receipt.json", receipt)
    return report(root)


def apply_admission_review(root, receipt, admission):
    """A documented disagreement may withhold admission, never promote a failure."""
    expected = {s["id"] for s in method.CASES[1:]}
    if set(admission) != expected:
        raise ValueError("admission_review_must_cover_all_four_positions")
    result = {}
    for case_id in expected:
        row = admission[case_id]
        if row.get("status") not in {"pass", "issue", "uncertain"} or not row.get("findings"):
            raise ValueError("admission_evidence_required")
        for finding in row["findings"]:
            path = finding.get("path", "")
            prefix = f"results/{case_id}/"
            if not path.startswith(prefix) or ".." in Path(path).parts or not (root / path).is_file():
                # A structurally failed/missing case can cite the run receipt.
                if path != "receipt.json":
                    raise ValueError("admission_evidence_outside_case")
            if not finding.get("locator") or not finding.get("observation"):
                raise ValueError("admission_locator_required")
        original = receipt["cases"].get(case_id, {"status": "not_started", "quality": "not_reviewed"})
        result[case_id] = {**original, "quality": original.get("quality", "not_reviewed") if row["status"] == "pass" else row["status"]}
    return result


def report(root):
    receipt = read(root / "receipt.json")
    validation = {s["id"]: receipt["cases"].get(s["id"], {"status": "not_started", "quality": "not_reviewed"}) for s in method.CASES[1:]}
    passed = sum(r.get("status") == "completed" and r.get("effective_quality", r.get("quality")) == "pass" for r in validation.values())
    return {"status": receipt["status"], "validation_first_pass": f"{passed}/4", "validation": validation,
            "sessions_used": len(receipt["sessions"]), "recoveries_used": receipt["recoveries_used"],
            "trials": receipt.get("trials", {}), "first_failure": receipt.get("first_failure"),
            "stop_reason": receipt.get("stop_reason"), "task_level_manual_edits": receipt["task_level_manual_edits"],
            "interpretation": "small-batch preliminary support" if passed == 4 else "method quality not established",
            "professional_status": "provisional/LLM-proxy; no scoring, ranking or expert validation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "execute", "status", "report"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--phase", choices=["development", "validation", "trials"], default="development")
    parser.add_argument("--amendment", type=Path)
    parser.add_argument("--dependency-lock", type=Path)
    parser.add_argument("--dependency-remote")
    parser.add_argument("--recover-controller", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.run_id):
        parser.error("unsafe run ID")
    root = ROOT / "artifacts/r10" / args.run_id
    if args.action == "prepare":
        if args.phase == "trials":
            parser.error("trials use the existing validation freeze; execute after admission review")
        result = recover_controller(root, args.phase) if args.recover_controller else prepare(root, args.phase, args.amendment, args.dependency_lock, args.dependency_remote)
    elif args.action == "execute":
        result = execute(root, args.phase)
    else:
        result = report(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
