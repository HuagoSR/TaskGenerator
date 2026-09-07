"""One procurement materials comparison; no Solver, grading, retry or resumption."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "Test")]
from run_r10_skill_compiler import _ssh, _run
from run_r10_behavioral_pilot import _remote_script, _scp_command
from task_generator.core.deliverable_contract import DeliverableContractCompiler, DeliverableContractV1, DeliverableSpecV1

IMAGE = "taskgenerator-eval:milestone-r9-huago-cone-a2d8a5e35099"
IMAGE_SHA = "3c6c76324780a911ff7b47bf52629280b4f2a49f26248540de049a61b9129363"
HOST = "huago-cone"
REMOTE_BASE = "/home/huagosr/taskgenerator-data/r10-process-first"
PINS = ["python-docx==1.2.0", "pypdf==6.10.0", "reportlab==4.4.9", "Pillow==12.3.0"]
STAGES = [("generate", "A"), ("generate", "B"), ("mine", "A"), ("mine", "B"), ("review", "A"), ("review", "B")]
ANON = {"A": "case_731", "B": "case_284"}
WORKER = ROOT / "Test/r10_process_first_tools.py"


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path):
    result = {}
    for p in sorted(path.rglob("*")):
        if p.is_symlink() or getattr(p, "is_junction", lambda: False)():
            raise ValueError("linked_path")
        if p.is_file():
            result[p.relative_to(path).as_posix()] = sha(p)
    return result


def code_hashes():
    # Bind imported project code as well as the controller and remote helper.
    paths = list((ROOT / "src").rglob("*.py")) + list((ROOT / "Test").glob("*.py"))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def remaining(deadline, cap=1800):
    seconds = min(cap, int(deadline - time.monotonic()))
    if seconds < 1:
        raise TimeoutError("scope_time_budget_exhausted")
    return seconds


COMMON = """Work only on the frozen public occupational seed and sources in inputs/.
Invent a new procurement situation, not a historical task. Do not browse, access
other workspaces, inspect authentication, install packages, call another model,
or use background/subagents. Do not preselect a supplier, amount, conflict or
conclusion to satisfy an experiment hypothesis. There are no file/record/anomaly
quotas. Use naturally useful XLSX, DOCX, PDF, CSV, TXT or Markdown records.
Available: Python with openpyxl, python-docx, pypdf, reportlab, Pillow; LibreOffice
and Poppler. /workspace and inputs are read-only. Write only /output or /tmp.
Candidate-visible facts, hidden factory records and run evidence must stay separate.
Frozen sources are methodology, not a representation that live regulations were checked.
"""


def prompt(stage, arm):
    if stage == "generate":
        method = (
            "Directly construct the business materials. Write hidden/world.md explaining "
            "the underlying events, record provenance and dependencies separately."
            if arm == "A" else
            "Before materializing ANY candidate file, use a separate tool step to write "
            "/output/hidden/process.md (participants, events, times, record origins and "
            "purposes; no task or rubric). In that tool step run: "
            "python /workspace/tools.py freeze-process /output . Wait for its successful "
            "PROCESS_FROZEN output before a subsequent tool call creates candidate files. "
            "Do not revise the frozen process. Then materialize records and write hidden/world.md."
        )
        return COMMON + method + """
Put candidate business records in /output/candidate/. They must support a natural
occupational work trigger, but do not write a candidate task, solution, or rubric.
Do not expose hidden strategy, world ledger, intended answer or experiment arm in
candidate files. Write /output/hidden/manifest.json with a records array containing
path (relative to candidate/), producer, business_purpose, and source_dependencies.
Preserve genuine uncertainty instead of silently inventing missing corroboration.
"""
    if stage == "mine":
        return COMMON + """
You are independently mining a task from one anonymous candidate material set.
Read inputs/candidate/ and inputs/public_context.json only. Do not infer hidden
author intent. Write /output/task.json: natural_task (boolean), rationale (string).
If false, stop; do not fabricate a replacement. If true also include title,
prompt (candidate-visible work request, with explicit downstream purpose),
evidence_paths (paths relative to inputs/candidate/), and deliverable_file_name
(one DOCX memorandum basename). Requirements must follow visible obligations.
Do not solve the task, supply answer labels or compile a rubric.
"""
    return COMMON + """
Independently reconstruct the judgments supported by this anonymous task and its
candidate evidence. Read inputs/candidate_task.md, inputs/deliverable_contract.json,
inputs/task.json, inputs/candidate/ and public rules.
Do not write a complete candidate answer or new rubric. Write /output/review.json
with requirements (array), supportable_judgments (array), conditional_conclusions
(array), gaps (array), and checks (array of four objects). Each check has dimension
(one of consistency, business_causes, downstream_requirements, solvability),
findings (array of objects with observation, evidence_path relative to candidate/,
locator such as sheet/cell, page/paragraph or line, and limitation).
Task and public-rule evidence may use ../candidate_task.md, ../task.json,
../deliverable_contract.json, ../professional_rules.json, ../sources.json or
../public_context.json, all within your supplied inputs. No other parent paths.
Cover dates, amounts, scope and versions; causes of differences and source dependence; explicit
downstream use and visible requirements; feasible completion or specific conditions
and follow-up. Preserve semantic defects. Your findings are provisional LLM-proxy
opinions, not expert validation, scoring or method superiority.
"""


def public_inputs(destination):
    source_files = [ROOT / "data/r10/work_seeds/candidate_work_seeds.json",
                    ROOT / "data/r10/work_seeds/professional_rule_sets.json",
                    ROOT / "data/r10/professional_skills/curation_sources.json"]
    seed = next(x["seed"] for x in read(source_files[0]) if x["status"] == "admitted" and x["seed"]["seed_id"] == "seed_procurement_price_reasonableness")
    rules = next(x for x in read(source_files[1]) if x["rule_set_id"] == "r10_rules_procurement_award_and_acceptance")
    sources = read(source_files[2])
    if isinstance(sources, dict):
        sources = sources["sources"]
    write(destination / "work_seed.json", seed)
    write(destination / "professional_rules.json", rules)
    write(destination / "sources.json", [x for x in sources if x["skill_id"] == "r10.procurement-price-reasonableness"])
    write(destination / "public_context.json", {k: seed[k] for k in ("role", "trigger_event", "business_goal", "audience")})
    skill = ROOT / ".agents/skills/r10/procurement-price-reasonableness"
    for relative in ("SKILL.md", "references/source-map.md"):
        p = skill / relative
        source_files.append(p)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, target)
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in source_files}


def docker_base(remote, *, network=False):
    return ["docker", "run", "--rm", "--init", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--user", "1000:1000",
            "--memory", "3g", "--cpus", "2", "--pids-limit", "256",
            *([] if network else ["--network", "none"]),
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=512m",
            "--tmpfs", "/home/taskgenerator/.cache:rw,nosuid,nodev,size=512m",
            "--tmpfs", "/home/taskgenerator/.local:rw,nosuid,nodev,size=512m",
            "--tmpfs", "/home/taskgenerator/.config:rw,nosuid,nodev,size=256m"]


def prepare(root):
    if root.exists():
        raise FileExistsError("pilot_directory_already_exists")
    if root.parent.resolve() != (ROOT / "artifacts/r10").resolve() or not re.fullmatch(r"[a-zA-Z0-9_-]+", root.name):
        raise ValueError("pilot_path_must_be_fresh_artifacts_r10_child")
    root.mkdir()
    receipt = {"status": "preparing", "created_at": now(), "sessions": [], "first_failure": None}
    write(root / "receipt.json", receipt)
    try:
        source_hashes = public_inputs(root / "public")
        prompts = root / "prompts"
        prompts.mkdir()
        for stage, arm in STAGES:
            (prompts / f"{stage}_{arm}.md").write_text(prompt(stage, arm), encoding="utf-8")
        shutil.copyfile(WORKER, root / "tools.py")
        remote = f"{REMOTE_BASE}/{root.name}"
        scope = {"created_at": now(), "remote": remote, "host": HOST, "image": IMAGE,
                 "image_sha256": IMAGE_SHA, "source_hashes": source_hashes,
                 "public_hashes": tree(root / "public"), "prompt_hashes": tree(prompts),
                 "code_hashes": code_hashes(), "tool_sha256": sha(root / "tools.py"),
                 "dependency_pins": PINS, "order": STAGES, "anonymous_ids": ANON,
                 "generation": {"model": "gpt-5.6-sol", "reasoning": "high", "route": "chatgpt_codex"},
                 "mining_review": {"model": "deepseek-v4-pro", "reasoning": "max", "route": "official_opencode"},
                 "max_sessions": 6, "session_seconds": 1800, "total_execution_seconds": 10800,
                 "token_and_cost_hard_limit": None, "no_retry": True, "no_solver_or_grading": True,
                 "isolation": "readonly stage inputs; candidate-only anonymous mining; no hidden records in review",
                 "authorization": "User approved procurement process-first plan, Sol + official DeepSeek, six serial sessions/three hours"}
        write(root / "scope.json", scope)
        write(root / "initial_git.json", {"status": _run(["git", "status", "--porcelain"]).stdout,
              "index_sha256": sha(ROOT / ".git/index")})
        _ssh(HOST, f"mkdir -p {shlex.quote(REMOTE_BASE)} && mkdir {shlex.quote(remote)} && mkdir {shlex.quote(remote + '/deps')}", timeout=60)
        _run(_scp_command(str(root / "tools.py"), f"{HOST}:{remote}/tools.py"), timeout=60)
        _run(_scp_command(str(root / "public"), f"{HOST}:{remote}/public"), timeout=60)
        identity = _ssh(HOST, f"docker image inspect --format '{{{{.Id}}}}' {IMAGE}", timeout=60).stdout.strip().removeprefix("sha256:")
        if identity != IMAGE_SHA:
            raise ValueError("image_fingerprint_changed")
        cmd = docker_base(remote, network=True) + ["-v", f"{remote}/deps:/deps:rw", "-v", f"{remote}/tools.py:/tools.py:ro", "--entrypoint", "python", IMAGE, "/tools.py", "dependencies", "/deps"]
        result = _ssh(HOST, shlex.join(cmd), timeout=1200, check=False)
        (root / "dependency_setup.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("fixed_dependency_preparation_failed")
        _run(_scp_command(f"{HOST}:{remote}/deps/lock.json", str(root / "dependency_lock.json")), timeout=60)
        cmd = docker_base(remote) + ["-e", "PYTHONPATH=/deps/site", "-v", f"{remote}/public:/inputs:ro", "-v", f"{remote}/deps:/deps:ro", "-v", f"{remote}/tools.py:/tools.py:ro", "--entrypoint", "python", IMAGE, "/tools.py", "smoke", "/tmp/smoke"]
        result = _ssh(HOST, shlex.join(cmd), timeout=180, check=False)
        (root / "offline_smoke.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("offline_document_smoke_failed")
        write(root / "ready.json", {"scope_sha256": sha(root / "scope.json"), "dependency_lock_sha256": sha(root / "dependency_lock.json"), "ready_at": now()})
        receipt["status"] = "ready"
    except Exception as exc:
        receipt.update(status="incomplete", first_failure=str(exc), stopped_at=now())
    write(root / "receipt.json", receipt)
    return receipt


def stage_inputs(root, stage, arm, destination):
    destination.mkdir(parents=True)
    public = root / "public"
    if stage == "generate":
        shutil.copytree(public, destination, dirs_exist_ok=True)
    else:
        shutil.copyfile(public / "public_context.json", destination / "public_context.json")
        candidate = root / "results" / f"generate_{arm}" / "candidate"
        tree(candidate)
        shutil.copytree(candidate, destination / "candidate")
        if stage == "review":
            for name in ("professional_rules.json", "sources.json"):
                shutil.copyfile(public / name, destination / name)
            for name in ("task.json", "candidate_task.md", "deliverable_contract.json"):
                shutil.copyfile(root / "results" / f"mine_{arm}" / name, destination / name)


def agent_script(stage):
    stack = "gpt-5.6-sol@chatgpt_codex" if stage == "generate" else "deepseek-v4-pro@official_opencode"
    script = _remote_script("/workspace", stack=stack, codex_reasoning_effort="high", opencode_variant="max")
    script = script.split("rm -rf /workspace/.docx_office_check;")[0]
    script = script.replace("/tmp/r10-pylibs", "/deps/site")
    # Docker's host stdout/stderr become evidence inaccessible to the Agent.
    script = script.replace(" > agent.jsonl 2> stderr.txt", "")
    return script + "\n"


def check_bindings(root):
    scope, ready = read(root / "scope.json"), read(root / "ready.json")
    if sha(root / "scope.json") != ready["scope_sha256"] or sha(root / "dependency_lock.json") != ready["dependency_lock_sha256"]:
        raise ValueError("scope_or_dependency_lock_changed")
    if scope["code_hashes"] != code_hashes() or scope["public_hashes"] != tree(root / "public") or scope["prompt_hashes"] != tree(root / "prompts") or scope["tool_sha256"] != sha(root / "tools.py"):
        raise ValueError("code_or_inputs_changed")
    if any(sha(ROOT / p) != h for p, h in scope["source_hashes"].items()):
        raise ValueError("public_source_changed")
    for relative, expected in scope.get("inherited_files", {}).items():
        if sha(root / relative) != expected:
            raise ValueError("inherited_material_changed")
    for relative, expected in scope.get("parent_files", {}).items():
        if sha(ROOT / relative) != expected:
            raise ValueError("parent_evidence_changed")
    return scope


def execution_order(scope):
    order = [tuple(item) for item in scope["order"]]
    expected = [("review", "B")] if scope.get("continuation") == "frozen_review_B" else STAGES
    if order != expected or scope["max_sessions"] != len(expected):
        raise ValueError("pilot_stage_scope_invalid")
    return order


def prepare_continuation(root, parent):
    """New authorization: preserve the closed run and finish its unstarted review."""
    if root.exists():
        raise FileExistsError("pilot_directory_already_exists")
    if root.parent.resolve() != (ROOT / "artifacts/r10").resolve() or parent.parent.resolve() != root.parent.resolve():
        raise ValueError("continuation_must_stay_in_artifacts_r10")
    old = read(parent / "scope.json")
    receipt = read(parent / "receipt.json")
    closed = read(parent / "closeout.json")
    if sha(parent / "scope.json") != closed["scope_sha256"] or sha(parent / "receipt.json") != closed["receipt_sha256"] or tree(parent / "results/review_A") != closed["review_A_raw_hashes_at_closeout"]:
        raise ValueError("parent_closeout_binding_changed")
    expected = [("generate", "A"), ("generate", "B"), ("mine", "A"), ("mine", "B"), ("review", "A")]
    if receipt["status"] != "incomplete" or [(x["stage"], x["arm"]) for x in receipt["sessions"]] != expected:
        raise ValueError("not_the_unstarted_review_B_boundary")
    for session in receipt["sessions"][:4]:
        if session["status"] != "completed" or tree(parent / "results" / f'{session["stage"]}_{session["arm"]}') != session["output_hashes"]:
            raise ValueError("parent_completed_result_changed")
    if not receipt["sessions"][4]["usage"]["completed"]:
        raise ValueError("review_A_did_not_return")
    validate_result("review", parent / "results/review_A")
    check_evidence(parent, "review", "A")
    elapsed = (datetime.fromisoformat(receipt["stopped_at"]) - datetime.fromisoformat(receipt["started_at"])).total_seconds()
    budget = int(old["total_execution_seconds"] - elapsed)
    if budget < 1:
        raise ValueError("original_execution_budget_exhausted")
    root.mkdir()
    shutil.copytree(parent / "public", root / "public")
    shutil.copytree(parent / "prompts", root / "prompts")
    for key in ("generate_B", "mine_B"):
        source = parent / "results" / key
        if key == "generate_B":
            shutil.copytree(source / "candidate", root / "results" / key / "candidate")
        else:
            shutil.copytree(source, root / "results" / key)
    shutil.copyfile(WORKER, root / "tools.py")
    shutil.copyfile(parent / "dependency_lock.json", root / "dependency_lock.json")
    bound = [parent / name for name in ("scope.json", "receipt.json", "closeout.json", "dependency_lock.json", "results/review_A/review.json")]
    scope = dict(old)
    scope.update(created_at=now(), remote=f"{REMOTE_BASE}/{root.name}", dependency_remote=old["remote"],
                 continuation="frozen_review_B", order=[("review", "B")], max_sessions=1,
                 total_execution_seconds=budget, prior_execution_seconds=elapsed,
                 code_hashes=code_hashes(), tool_sha256=sha(root / "tools.py"),
                 inherited_files={"results/" + k: v for k, v in tree(root / "results").items()},
                 parent_files={p.relative_to(ROOT).as_posix(): sha(p) for p in bound},
                 authorization="User explicitly authorized continuing, autonomous diagnosis/repair/resumption under the existing material-comparison plan. Finish the unstarted B review; preserve prior five sessions and six-session/three-hour total budget.")
    write(root / "scope.json", scope)
    write(root / "ready.json", {"scope_sha256": sha(root / "scope.json"), "dependency_lock_sha256": sha(root / "dependency_lock.json"), "ready_at": now(), "reused_offline_smoke": str(parent / "offline_smoke.log")})
    write(root / "receipt.json", {"status": "ready", "created_at": now(), "sessions": [], "first_failure": None, "review_A_offline_revalidation": "passed_without_new_model_session"})
    return read(root / "receipt.json")


def validate_result(stage, path):
    tree(path)
    if stage == "generate":
        if not tree(path / "candidate") or not (path / "hidden/world.md").is_file():
            raise ValueError("materials_or_world_missing")
        records = read(path / "hidden/manifest.json")["records"]
        if not isinstance(records, list):
            raise ValueError("manifest_records_invalid")
    elif stage == "mine":
        task = read(path / "task.json")
        if type(task.get("natural_task")) is not bool or not isinstance(task.get("rationale"), str):
            raise ValueError("task_structure_invalid")
        if task["natural_task"]:
            name = task["deliverable_file_name"]
            contract = DeliverableContractV1(case_id="anonymous_task", deliverables=[DeliverableSpecV1(file_name=name, relative_path=f"deliverable_files/{name}", format="docx")])
            contract = DeliverableContractCompiler().build(case_id=contract.case_id, deliverable_specs=[s.model_dump() for s in contract.deliverables])
            write(path / "deliverable_contract.json", contract.model_dump(mode="json"))
            if not task.get("prompt") or not task.get("evidence_paths"):
                raise ValueError("task_requirements_missing")
    else:
        review = read(path / "review.json")
        for key in ("requirements", "supportable_judgments", "conditional_conclusions", "gaps", "checks"):
            if not isinstance(review.get(key), list):
                raise ValueError("review_structure_invalid")
        if sorted(c["dimension"] for c in review["checks"]) != sorted(["consistency", "business_causes", "downstream_requirements", "solvability"]):
            raise ValueError("review_dimensions_invalid")


def check_reference(candidate, relative):
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise ValueError("unsafe_evidence_path")
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or not relative or not (candidate / relative).is_file():
        raise ValueError("missing_or_unsafe_evidence_path")


def check_evidence(root, stage, arm):
    candidate = root / "results" / f"generate_{arm}" / "candidate"
    output = root / "results" / f"{stage}_{arm}"
    if stage == "generate":
        for record in read(output / "hidden/manifest.json")["records"]:
            check_reference(candidate, record["path"])
    elif stage == "mine":
        task = read(output / "task.json")
        if task["natural_task"]:
            for reference in task["evidence_paths"]:
                check_reference(candidate, reference)
            contract = read(output / "deliverable_contract.json")
            compiled = DeliverableContractCompiler().compile_prompt(task["prompt"], DeliverableContractV1.model_validate(contract))
            (output / "candidate_task.md").write_text(compiled, encoding="utf-8")
    else:
        for check in read(output / "review.json")["checks"]:
            if not isinstance(check.get("findings"), list) or not check["findings"]:
                raise ValueError("review_evidence_missing")
            for finding in check["findings"]:
                check_review_reference(root / "staging" / f"review_{arm}" / "inputs", finding["evidence_path"])
                if not all(isinstance(finding.get(key), str) and finding[key].strip() for key in ("observation", "locator", "limitation")):
                    raise ValueError("review_locator_missing")


def check_review_reference(inputs, relative):
    """Review requirements can cite the task/contract as well as business records."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative or PurePosixPath(relative).is_absolute():
        raise ValueError("unsafe_review_evidence_path")
    tree(inputs)  # Refuse linked inputs before resolving any relative references.
    target = (inputs / "candidate" / relative).resolve()
    allowed = {p.resolve() for p in (inputs / "candidate").rglob("*") if p.is_file()}
    context_names = ("candidate_task.md", "task.json", "deliverable_contract.json", "professional_rules.json", "sources.json", "public_context.json")
    allowed.update((inputs / name).resolve() for name in context_names if (inputs / name).is_file())
    matches = {target} if target in allowed else set()
    # Native readers also cite these exact supplied context basenames. Resolve
    # only the closed list; do not guess missing filenames or fuzzy-match paths.
    if relative in context_names and (inputs / relative).is_file():
        matches.add((inputs / relative).resolve())
    if len(matches) > 1:
        raise ValueError("ambiguous_review_evidence_path")
    if not matches:
        raise ValueError("missing_or_unsafe_review_evidence_path")


def verify_remote_tree(remote_path, expected, deadline):
    # Host-side stdlib inspection; no model, auth or package imports.
    code = "import hashlib,json,pathlib,sys; r=pathlib.Path(sys.argv[1]); print(json.dumps({p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob('*')) if p.is_file()}))"
    result = _ssh(HOST, shlex.join(["python3", "-c", code, remote_path]), timeout=remaining(deadline, 60))
    if json.loads(result.stdout) != expected:
        raise ValueError("remote_input_fingerprint_changed")


def execute(root):
    receipt = read(root / "receipt.json")
    if receipt["status"] != "ready" or receipt["sessions"]:
        raise ValueError("scope_not_fresh_ready_no_resume")
    receipt.update(status="running", started_at=now())
    write(root / "receipt.json", receipt)
    deadline = time.monotonic() + 10800
    try:
        scope = check_bindings(root)
        order = execution_order(scope)
        deadline = deadline - 10800 + min(10800, scope["total_execution_seconds"])
        remote = scope["remote"]
        stage_base = remote
        remote = scope.get("dependency_remote", remote)
        if scope.get("continuation"):
            _ssh(HOST, f"mkdir {shlex.quote(stage_base)}", timeout=remaining(deadline, 60))
        lock_digest = _ssh(HOST, f"sha256sum {remote}/deps/lock.json {remote}/tools.py", timeout=remaining(deadline, 60)).stdout.splitlines()
        if [line.split()[0] for line in lock_digest] != [sha(root / "dependency_lock.json"), sha(root / "tools.py")]:
            raise ValueError("remote_dependency_or_helper_changed")
        cmd = docker_base(remote) + ["-v", f"{remote}/deps:/deps:ro", "-v", f"{remote}/tools.py:/tools.py:ro", "--entrypoint", "python", IMAGE, "/tools.py", "verify-dependencies", "/deps"]
        _ssh(HOST, f"test $(docker image inspect --format '{{{{.Id}}}}' {IMAGE}) = sha256:{IMAGE_SHA} && " + shlex.join(cmd), timeout=remaining(deadline, 120))
        for index, (stage, arm) in enumerate(order, 1):
            if stage == "review" and not read(root / "results" / f"mine_{arm}" / "task.json")["natural_task"]:
                receipt.setdefault("skipped", []).append({"stage": stage, "arm": arm, "reason": "no_natural_task"})
                continue
            check_bindings(root)
            key = f"{stage}_{arm}"
            workspace = root / "staging" / key
            stage_inputs(root, stage, arm, workspace / "inputs")
            shutil.copyfile(root / "prompts" / f"{key}.md", workspace / "TASK.md")
            shutil.copyfile(root / "tools.py", workspace / "tools.py")
            (workspace / "agent.sh").write_bytes(agent_script(stage).encode())
            inputs_hashes = tree(workspace)
            stage_remote = f"{stage_base}/{index:02d}_{ANON[arm]}"
            session = {"stage": stage, "arm": arm, "anonymous_id": ANON[arm], "status": "staging", "input_hashes": inputs_hashes}
            receipt["sessions"].append(session)
            write(root / "receipt.json", receipt)
            _ssh(HOST, f"mkdir {stage_remote} && mkdir {stage_remote}/output", timeout=remaining(deadline, 60))
            _run(_scp_command(str(workspace), f"{HOST}:{stage_remote}/workspace"), timeout=remaining(deadline, 120))
            verify_remote_tree(stage_remote + "/workspace", inputs_hashes, deadline)
            cap = remaining(deadline)
            session.update(status="started", started_at=now(), timeout_seconds=cap)
            write(root / "receipt.json", receipt)
            print(f"{key}: started, limit {cap}s", flush=True)
            cmd = docker_base(remote, network=True) + ["-v", f"{stage_remote}/workspace:/workspace:ro", "-v", f"{stage_remote}/output:/output:rw", "-v", f"{remote}/deps:/deps:ro", "-w", "/workspace"]
            if stage == "generate":
                cmd += ["-v", "/home/huagosr/taskgenerator-secrets/codex-auth-current:/run/codex-home:rw"]
            else:
                cmd += ["-v", "/home/huagosr/taskgenerator-secrets/deepseek_api_key:/run/secrets/deepseek_api_key:ro"]
            cmd += ["--entrypoint", "/bin/sh", IMAGE, "/workspace/agent.sh"]
            # GNU timeout also bounds remote execution if the SSH connection is lost.
            container_name = f"{root.name}-{index:02d}"
            cmd[2:2] = ["--name", container_name, "--stop-timeout", "1"]
            command = f"trap 'timeout 3s docker stop -t 1 {container_name} >/dev/null 2>&1 || true' EXIT; timeout --signal=TERM --kill-after=1s {max(1, cap - 5)}s " + shlex.join(cmd) + f" > {stage_remote}/agent.jsonl 2> {stage_remote}/stderr.txt"
            start = time.monotonic()
            result = _ssh(HOST, command, timeout=cap, check=False)
            session.update(returncode=result.returncode, elapsed_seconds=time.monotonic() - start)
            evidence = root / "evidence" / key
            evidence.mkdir(parents=True)
            for name in ("agent.jsonl", "stderr.txt"):
                _run(_scp_command(f"{HOST}:{stage_remote}/{name}", str(evidence / name)), timeout=remaining(deadline, 60))
            session["usage"] = usage(evidence / "agent.jsonl")
            if result.returncode or not session["usage"]["completed"] or session["usage"]["error_events"]:
                raise RuntimeError(f"{key}:agent_or_authentication_failed")
            # Validate actual remote output before SCP, never follow Agent-created links.
            cmd = docker_base(remote) + ["-e", "PYTHONPATH=/deps/site", "-v", f"{remote}/deps:/deps:ro", "-v", f"{remote}/tools.py:/tools.py:ro", "-v", f"{stage_remote}/output:/output:ro", "--entrypoint", "python", IMAGE, "/tools.py", "validate-output", "/output"]
            _ssh(HOST, shlex.join(cmd), timeout=remaining(deadline, 120))
            destination = root / "results" / key
            destination.parent.mkdir(exist_ok=True)
            _run(_scp_command(f"{HOST}:{stage_remote}/output", str(destination)), timeout=remaining(deadline, 120))
            if inputs_hashes != tree(workspace):
                raise ValueError("staged_input_changed")
            verify_remote_tree(stage_remote + "/workspace", inputs_hashes, deadline)
            validate_result(stage, destination)
            check_evidence(root, stage, arm)
            session.update(status="completed", output_hashes=tree(destination), completed_at=now())
            if key == "generate_B":
                session["process_protocol"] = process_protocol(destination, evidence / "agent.jsonl")
            write(root / "receipt.json", receipt)
            remaining(deadline)
            print(f"{key}: completed", flush=True)
        receipt.update(status="completed", stopped_at=now(), interpretation="provisional LLM-proxy; no method superiority or difficulty inference")
    except Exception as exc:
        receipt.update(status="incomplete", first_failure=receipt.get("first_failure") or str(exc), stopped_at=now())
        if receipt["sessions"] and receipt["sessions"][-1]["status"] != "completed":
            receipt["sessions"][-1]["status"] = "incomplete"
    write(root / "receipt.json", receipt)
    return receipt


def usage(path):
    events, errors, completed = [], 0, False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get("type", "")
        part = event.get("part", {})
        errors += int(kind in ("error", "turn.failed"))
        if kind == "turn.completed":
            completed = True
            events.append({"usage": event.get("usage")})
        if kind == "step_finish":
            completed |= part.get("reason") == "stop"
            events.append({"tokens": part.get("tokens"), "cost": part.get("cost")})
    return {"completed": completed, "error_events": errors, "reported_usage_events": events,
            "model_request_count": None, "request_count_note": "native logs may not expose all backend requests; session count is not request count"}


def process_protocol(output, log):
    proof = output / "hidden/process.sha256"
    process = output / "hidden/process.md"
    if not proof.is_file() or not process.is_file() or proof.read_text().strip() != sha(process):
        return "unverified"
    # A successful dedicated tool event must freeze the record before later tools.
    frozen = False
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line).get("item", {})
        except ValueError:
            continue
        if item.get("type") == "command_execution" and item.get("status") == "completed":
            command = item.get("command", "")
            if "freeze-process" in command and "PROCESS_FROZEN " + sha(process) in item.get("aggregated_output", "") and "candidate/" not in command:
                frozen = True
            elif frozen and "candidate" in command:
                return "trajectory_supported_not_tamperproof"
    return "unverified"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "prepare-continuation", "execute", "status"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--parent-run-id")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.run_id):
        parser.error("unsafe run id")
    root = ROOT / "artifacts/r10" / args.run_id
    if args.action == "prepare-continuation":
        if not args.parent_run_id or not re.fullmatch(r"[a-zA-Z0-9_-]+", args.parent_run_id):
            parser.error("safe parent run id required")
        result = prepare_continuation(root, ROOT / "artifacts/r10" / args.parent_run_id)
    else:
        result = read(root / "receipt.json") if args.action == "status" else (prepare(root) if args.action == "prepare" else execute(root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "incomplete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
