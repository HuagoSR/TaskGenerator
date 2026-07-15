from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "SkillRegistry" / "v3_finance_model_difference_eval.experimental.json"
F4_2_SPEC = ROOT / "SkillRegistry" / "v3_finance_f4_2_model_eval.experimental.json"
ALLOWED_SOLVER_KEYS = {"task_id", "sector", "occupation", "motif", "prompt", "reference_files", "deliverable_files"}
FORBIDDEN_NAMES = {"golden_run.json", "rubric.json", "training_annotation.json", "deterministic_answer_key.json"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def tree_sha256(root: Path) -> str:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            entries.append((path.relative_to(root).as_posix(), sha256(path)))
    return json_sha256(entries)


def _f4_2_package(source_campaign_root: Path, slot: dict) -> Path:
    evidence = Path(slot["holistic_evidence_dir"])
    if evidence.is_absolute() and not evidence.exists():
        evidence = source_campaign_root.parent / Path(*evidence.parts[3:])
    package = evidence / "final_package"
    if not package.is_dir():
        raise RuntimeError(f"missing F4.2 final package for slot {slot.get('slot')}: {package}")
    return package


def build_f4_2_index(source_campaign_root: Path) -> list[dict]:
    manifest = load_json(source_campaign_root / "campaign_manifest.json")
    if manifest.get("decision") != "f4_from_scratch_validation_passed":
        raise RuntimeError("F4.2 source campaign is not a passed immutable cohort")
    records = []
    for slot in manifest.get("slots", []):
        if slot.get("state") != "passed":
            raise RuntimeError(f"F4.2 slot is not passed: {slot.get('slot')}")
        package = _f4_2_package(source_campaign_root, slot)
        row_path = package / "rw_task_export" / "dataset_row.json"
        reference_dir = package / "rw_task_export" / "reference_files"
        row = load_json(row_path)
        records.append({
            "slot": int(slot["slot"]),
            "task_id": row["task_id"],
            "global_index": int(slot["slot"]),
            "motif": slot["motif"],
            "skills": [],
            "case_dir": str(package),
            "dataset_row_path": str(row_path),
            "reference_dir": str(reference_dir),
            "task_sha256": sha256(row_path),
            "prompt_sha256": json_sha256(row.get("prompt")),
            "subgraph_sha256": None,
            "reference_bundle_sha256": tree_sha256(reference_dir),
            "package_sha256": tree_sha256(package),
            "assistant_review_sha256": slot.get("assistant_review_sha256"),
            "experimental_motif": bool(slot.get("experimental_motif")),
            "default_promotion_allowed": slot.get("default_promotion_allowed"),
        })
    if len(records) != 8 or {item["motif"] for item in records} != {
        "fan_in_reconciliation", "cross_check_validation", "policy_application", "evidence_to_deliverable"
    }:
        raise RuntimeError("F4.2 cohort must contain exactly eight tasks across four motifs")
    return sorted(records, key=lambda item: item["slot"])


def task_roots(production_root: Path) -> list[Path]:
    return sorted(path for path in production_root.glob("**/batch/pipeline_b_batch_*") if path.is_dir())


def build_index(production_root: Path) -> list[dict]:
    by_index = {}
    for case in task_roots(production_root):
        blueprint = load_json(case / "prototype" / "draft_task_blueprint.json")
        if not str(blueprint.get("template_family") or "").startswith("finance_"):
            continue
        row_path = case / "rw_task_export" / "dataset_row.json"
        row = load_json(row_path)
        digits = "".join(ch for ch in case.name.split("_")[3] if ch.isdigit())
        motif = {"finance_cash_reconciliation_v1":"fan_in_reconciliation","finance_three_way_match_v1":"cross_check_validation","finance_expense_policy_review_v1":"policy_application"}[blueprint["template_family"]]
        subgraphs = sorted((case / "prototype").glob("*subgraph*.json"))
        subgraph_sha = sha256(subgraphs[0]) if subgraphs else json_sha256(blueprint.get("task_subgraph") or {})
        reference_dir = case / "rw_task_export" / "reference_files"
        record = {
            "task_id": row["task_id"], "global_index": int(digits), "motif": motif,
            "skills": sorted(blueprint.get("selected_skills") or []), "case_dir": str(case),
            "dataset_row_path": str(row_path), "reference_dir": str(reference_dir),
            "task_sha256": sha256(row_path),
            "prompt_sha256": json_sha256(row.get("prompt")),
            "subgraph_sha256": subgraph_sha,
            "reference_bundle_sha256": tree_sha256(reference_dir),
        }
        current = by_index.get(record["global_index"])
        if current is None or record["case_dir"] > current["case_dir"]:
            by_index[record["global_index"]] = record
    return sorted(by_index.values(), key=lambda item: item["global_index"])


def jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    return len(a & b) / len(a | b) if a | b else 1.0


def select_pilot(index: list[dict]) -> list[dict]:
    selected = []
    for motif in ("fan_in_reconciliation", "cross_check_validation", "policy_application"):
        candidates = [item for item in index if item["motif"] == motif]
        first = candidates[0]
        second = min(candidates[1:], key=lambda item: (jaccard(first["skills"], item["skills"]), item["global_index"]))
        selected.extend([first, second])
    return sorted(selected, key=lambda item: item["global_index"])


def _is_exact_duplicate(item: dict, selected: list[dict]) -> bool:
    for existing in selected:
        if item.get("task_sha256") and item.get("task_sha256") == existing.get("task_sha256"):
            return True
        bundle_keys = ("prompt_sha256", "subgraph_sha256", "reference_bundle_sha256")
        if all(item.get(key) and item.get(key) == existing.get(key) for key in bundle_keys):
            return True
    return False


def select_extended(index: list[dict], tasks_per_motif: int = 10) -> list[dict]:
    pilot = select_pilot(index)
    selected = list(pilot)
    for motif in ("fan_in_reconciliation", "cross_check_validation", "policy_application"):
        motif_selected = [item for item in selected if item["motif"] == motif]
        candidates = [item for item in index if item["motif"] == motif and item not in motif_selected]
        while len(motif_selected) < tasks_per_motif:
            eligible = [item for item in candidates if not _is_exact_duplicate(item, selected)]
            if not eligible:
                raise RuntimeError(f"not enough non-duplicate tasks for {motif}")
            chosen = min(
                eligible,
                key=lambda item: (
                    max(jaccard(item["skills"], existing["skills"]) for existing in motif_selected),
                    item["global_index"],
                ),
            )
            chosen["selection_max_skill_jaccard"] = max(
                jaccard(chosen["skills"], existing["skills"]) for existing in motif_selected
            )
            motif_selected.append(chosen)
            selected.append(chosen)
            candidates.remove(chosen)
    return sorted(selected, key=lambda item: item["global_index"])


def _task_file_hashes(solver_root: Path, task_id: str) -> dict[str, str]:
    root = solver_root / task_id
    return {
        str(path.relative_to(solver_root)).replace("\\", "/"): sha256(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _verify_and_import_pilot(campaign_root: Path, pilot_root: Path, selection: dict) -> list[dict]:
    pilot_selection = load_json(pilot_root / "pilot_selection.json")
    pilot_manifest = load_json(pilot_root / "pilot_manifest.json")
    expected_ids = {item["task_id"] for item in selection["tasks"] if item["is_pilot"]}
    actual_ids = {item["task_id"] for item in pilot_selection["tasks"]}
    if actual_ids != expected_ids:
        raise RuntimeError(f"pilot task cohort mismatch: expected={sorted(expected_ids)} actual={sorted(actual_ids)}")
    current_hashes = selection["solver_input_sha256"]
    for relative, old_hash in pilot_selection["solver_input_sha256"].items():
        normalized = relative.replace("\\", "/")
        if current_hashes.get(normalized) != old_hash:
            raise RuntimeError(f"pilot solver-input fingerprint mismatch: {normalized}")
    imported = []
    for record in pilot_manifest.get("records", []):
        if record.get("task_id") not in expected_ids:
            continue
        if record.get("status") != "completed" or record.get("primary_grade", {}).get("score") is None or record.get("audit_grade", {}).get("score") is None:
            raise RuntimeError(f"pilot evidence incomplete: {record.get('task_id')} / {record.get('model')}")
        copied = json.loads(json.dumps(record))
        copied.update(imported=True, evidence_origin=str(pilot_root))
        imported.append(copied)
    if len(imported) != 24:
        raise RuntimeError(f"expected 24 imported pilot records, found {len(imported)}")
    return imported


def prepare(production_root: Path, campaign_root: Path, spec: dict, pilot_root: Path,
            source_campaign_root: Path | None = None) -> dict:
    scope = spec.get("scope", "pilot_6")
    if scope == "f4_2_eight_task":
        if source_campaign_root is None:
            raise RuntimeError("F4.2 scope requires source_campaign_root")
        selected = build_f4_2_index(source_campaign_root)
        index = selected
    else:
        index = build_index(production_root)
        if len(index) != 60:
            raise RuntimeError(f"expected 60 tasks, found {len(index)}")
    if scope in {"pilot_only", "pilot_6"}:
        selected = select_pilot(index)
    elif scope == "extended_30":
        selected = select_extended(index, int(spec.get("tasks_per_motif", 10)))
    elif scope == "f4_2_eight_task":
        selected = index
    else:
        raise RuntimeError(f"unsupported eval scope: {scope}")
    pilot_ids = {item["task_id"] for item in select_pilot(index)} if scope != "f4_2_eight_task" else set()
    solver_root = campaign_root / "solver_inputs"
    contracts = campaign_root / "grading_contracts"
    for item in selected:
        source_row = load_json(Path(item["dataset_row_path"]))
        target = solver_root / item["task_id"]
        target.mkdir(parents=True, exist_ok=True)
        solver_row = {key: value for key, value in source_row.items() if key in ALLOWED_SOLVER_KEYS}
        atomic_json(target / "dataset_row.json", solver_row)
        refs = target / "reference_files"
        if refs.exists():
            shutil.rmtree(refs)
        shutil.copytree(item["reference_dir"], refs)
        atomic_json(contracts / f"{item['task_id']}.json", {
            "task_id": item["task_id"], "rubric": source_row.get("rubric"), "rubric_json": source_row.get("rubric_json"),
            "source_task_sha256": item["task_sha256"], "source_package_sha256": item.get("package_sha256"),
        })
        forbidden = [str(path) for path in target.rglob("*") if path.name in FORBIDDEN_NAMES]
        if forbidden or set(solver_row) - ALLOWED_SOLVER_KEYS:
            raise RuntimeError(f"teacher-only truth leaked for {item['task_id']}")
    tasks = []
    for item in selected:
        copied = dict(item)
        copied["is_pilot"] = item["task_id"] in pilot_ids
        tasks.append(copied)
    payload = {"version": "v3.finance_model_difference_selection.3", "created_at": now(), "scope": scope,
               "task_count": len(selected), "tasks": tasks, "solver_input_root": str(solver_root),
               "solver_input_sha256": {
                   str(path.relative_to(solver_root)).replace("\\", "/"): sha256(path)
                   for path in sorted(solver_root.rglob("*")) if path.is_file()
               }}
    payload["selection_sha256"] = json_sha256({key: value for key, value in payload.items() if key != "created_at"})
    selection_path = campaign_root / "selection_manifest.json"
    if selection_path.exists():
        existing = load_json(selection_path)
        if existing.get("selection_sha256") != payload["selection_sha256"]:
            raise RuntimeError("immutable 30-task selection manifest conflict")
        payload = existing
    else:
        atomic_json(selection_path, payload)
    # Keep the historical pilot filename for the pilot scope only.
    if scope in {"pilot_only", "pilot_6"}:
        atomic_json(campaign_root / "pilot_selection.json", payload)
    if scope == "extended_30":
        imported = _verify_and_import_pilot(campaign_root, pilot_root, payload)
        manifest_path = campaign_root / "eval_manifest.json"
        if not manifest_path.exists():
            atomic_json(manifest_path, {"version":"v3.finance_model_difference_eval.2","created_at":now(),
                                       "status":"prepared","scope":scope,"records":imported,
                                       "imported_pilot_record_count":len(imported)})
    if scope == "f4_2_eight_task" and not (campaign_root / "eval_manifest.json").exists():
        atomic_json(campaign_root / "eval_manifest.json", {
            "version": "v3.finance_f4_2_model_eval.1", "created_at": now(), "status": "prepared",
            "scope": scope, "records": [], "source_campaign_root": str(source_campaign_root),
            "canonical_registry_sha256_before": load_json(source_campaign_root / "campaign_manifest.json").get("canonical_registry_sha256_after"),
        })
    return payload


def env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1); values[key.strip()] = value.strip()
    return values


def _cost_ledger_path(campaign_root: Path) -> Path:
    return campaign_root / "tuzi_cost_ledger.json"


def reserve_tuzi_call(campaign_root: Path, spec: dict, role: str, model: str) -> dict:
    path = _cost_ledger_path(campaign_root)
    ledger = load_json(path) if path.exists() else {
        "version": "v3.finance_f4_2_tuzi_budget.1", "key_slot": "backup",
        "budget_rmb": float(spec.get("tuzi_budget_rmb", 50)), "request_cap": int(spec.get("tuzi_request_cap", 96)),
        "reserved_spend_rmb": 0.0, "requests": [],
    }
    reservation = float(spec.get("reservation_rmb", {}).get(f"{role}:{model}", spec.get("reservation_rmb", {}).get(role, .5)))
    if len(ledger["requests"]) >= ledger["request_cap"]:
        raise RuntimeError("tuzi_request_cap_exhausted")
    if float(ledger["reserved_spend_rmb"]) + reservation > float(ledger["budget_rmb"]):
        raise RuntimeError("tuzi_budget_exhausted")
    entry = {"created_at": now(), "role": role, "model": model, "reserved_rmb": reservation, "status": "reserved"}
    ledger["requests"].append(entry)
    ledger["reserved_spend_rmb"] = round(float(ledger["reserved_spend_rmb"]) + reservation, 6)
    ledger["remaining_reserved_budget_rmb"] = round(float(ledger["budget_rmb"]) - float(ledger["reserved_spend_rmb"]), 6)
    atomic_json(path, ledger)
    return entry


def finalize_tuzi_call(campaign_root: Path, entry: dict, status: str) -> None:
    path = _cost_ledger_path(campaign_root)
    ledger = load_json(path)
    for candidate in reversed(ledger["requests"]):
        if candidate["created_at"] == entry["created_at"] and candidate["model"] == entry["model"]:
            candidate["status"] = status
            candidate["finished_at"] = now()
            break
    atomic_json(path, ledger)


def freeze_tuzi_pricing(campaign_root: Path, spec: dict, tuzi_base_url: str) -> dict:
    root = tuzi_base_url.split("/v1", 1)[0].rstrip("/")
    url = root + "/api/pricing?page=1&page_size=1000"
    with urllib.request.urlopen(url, timeout=30) as response:
        raw = response.read()
    payload = json.loads(raw)
    wanted = {item["model"] for item in spec["solver_models"] if item["provider"] == "tuzi"}
    wanted |= {spec["primary_grader"], spec["audit_grader"]}
    rows = {item.get("model_name"): item for item in payload.get("data", []) if item.get("model_name") in wanted}
    if set(rows) != wanted:
        raise RuntimeError(f"tuzi_pricing_missing_models:{sorted(wanted-set(rows))}")
    frozen = {
        "version": "v3.finance_f4_2_pricing.1", "created_at": now(), "source_url": url,
        "pricing_version": payload.get("pricing_version"), "response_sha256": hashlib.sha256(raw).hexdigest(),
        "models": {name: {key: row.get(key) for key in (
            "model_name", "quota_type", "model_ratio", "completion_ratio", "cache_ratio", "create_cache_ratio",
            "enable_groups", "supported_endpoint_types"
        )} for name, row in sorted(rows.items())},
    }
    atomic_json(campaign_root / "tuzi_pricing_snapshot.json", frozen)
    return frozen


def _chat_preflight(url: str, key: str, model: str) -> dict:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Public synthetic preflight. Return only JSON: {\"ok\":true}."}],
        "max_tokens": 64,
        "temperature": 0,
    }).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
    payload = json.loads(raw)
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    structured = "ok" in content.lower() and "true" in content.lower()
    if not structured:
        raise RuntimeError(f"provider_preflight_contract_failed:{model}")
    return {
        "model": model, "status": "completed", "response_sha256": hashlib.sha256(raw).hexdigest(),
        "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
        "usage": payload.get("usage") or {}, "structured_contract_pass": True,
    }


def provider_preflight(campaign_root: Path, spec: dict, tuzi_env: Path, deepseek_key: Path) -> dict:
    campaign_root.mkdir(parents=True, exist_ok=True)
    tuzi = env_file(tuzi_env)
    key = tuzi.get("TUZI_API_KEY") or tuzi.get("AGENT_API_KEY") or tuzi.get("OPENAI_API_KEY")
    url = tuzi.get("TUZI_BASE_URL") or tuzi.get("AGENT_BASE_URL") or tuzi.get("OPENAI_BASE_URL")
    deepseek = deepseek_key.read_text(encoding="utf-8").strip()
    if not key or not url or not deepseek:
        raise RuntimeError("provider_preflight_secrets_missing")
    pricing = freeze_tuzi_pricing(campaign_root, spec, url)
    reports = []
    for model_spec in spec["solver_models"] + [
        {"model": spec["primary_grader"], "provider": "tuzi"},
        {"model": spec["audit_grader"], "provider": "tuzi"},
    ]:
        model = model_spec["model"]
        if model_spec["provider"] == "tuzi":
            reservation = reserve_tuzi_call(campaign_root, spec, "preflight", model)
            try:
                report = _chat_preflight(url, key, model)
                finalize_tuzi_call(campaign_root, reservation, "completed")
            except Exception:
                finalize_tuzi_call(campaign_root, reservation, "failed")
                raise
        else:
            report = _chat_preflight("https://api.deepseek.com", deepseek, model)
        reports.append(report)
    payload = {
        "version": "v3.finance_f4_2_provider_preflight.1", "created_at": now(),
        "public_fixture_only": True, "task_package_uploaded": False,
        "pricing_response_sha256": pricing["response_sha256"], "models": reports, "decision": "pass",
    }
    atomic_json(campaign_root / "provider_preflight_report.json", payload)
    return payload


def run_command(command: list[str], env: dict[str, str], timeout: int, stdout_path: Path, stderr_path: Path) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=os.getenv("TASKGEN_RW_TASK_ROOT") or None, env=env, text=True,
                                encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)
        status, code, out, err = ("completed" if result.returncode == 0 else "failed"), result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        status, code, out, err = "timeout", None, str(exc.stdout or ""), str(exc.stderr or "")
    stdout_path.parent.mkdir(parents=True, exist_ok=True); stdout_path.write_text(out, encoding="utf-8")
    stderr_path.write_text(err, encoding="utf-8")
    return {"status": status, "returncode": code, "duration_seconds": round(time.monotonic()-started, 2),
            "stdout_path": str(stdout_path), "stderr_path": str(stderr_path)}


def selection_path(campaign_root: Path) -> Path:
    current = campaign_root / "selection_manifest.json"
    return current if current.exists() else campaign_root / "pilot_selection.json"


def manifest_path(campaign_root: Path) -> Path:
    current = campaign_root / "eval_manifest.json"
    return current if current.exists() else campaign_root / "pilot_manifest.json"


def execute(campaign_root: Path, spec: dict, tuzi_env: Path, deepseek_key: Path, e2b_key: Path) -> dict:
    selection = load_json(selection_path(campaign_root))
    if selection.get("scope") == "f4_2_eight_task":
        preflight_path = campaign_root / "provider_preflight_report.json"
        if not preflight_path.exists() or load_json(preflight_path).get("decision") != "pass":
            raise RuntimeError("F4.2 provider preflight has not passed")
    tuzi = env_file(tuzi_env); base = dict(os.environ)
    tuzi_key = tuzi.get("TUZI_API_KEY") or tuzi.get("AGENT_API_KEY") or tuzi.get("OPENAI_API_KEY")
    tuzi_url = tuzi.get("TUZI_BASE_URL") or tuzi.get("AGENT_BASE_URL") or tuzi.get("OPENAI_BASE_URL")
    e2b = e2b_key.read_text(encoding="utf-8").strip(); deepseek = deepseek_key.read_text(encoding="utf-8").strip()
    if not all((tuzi_key, tuzi_url, e2b, deepseek)): raise RuntimeError("required eval secrets are missing")
    if shutil.disk_usage(campaign_root.parent).free < int(spec.get("minimum_free_disk_bytes", 0)):
        raise RuntimeError("insufficient_free_disk_space")
    target_manifest = manifest_path(campaign_root)
    manifest = load_json(target_manifest) if target_manifest.exists() else {"version":"v3.finance_model_difference_eval.1","created_at":now(),"status":"running","records":[]}
    keyed = {(r["task_id"], r["model"]): r for r in manifest["records"]}
    for task in selection["tasks"]:
        for model_spec in spec["solver_models"]:
            key = (task["task_id"], model_spec["model"])
            if keyed.get(key, {}).get("status") == "completed": continue
            record = {"slot":task.get("slot"),"task_id":key[0],"model":key[1],"provider":model_spec["provider"],
                      "task_sha256":task.get("task_sha256"),"package_sha256":task.get("package_sha256"),
                      "status":"running","started_at":now(),"attempts":[]}
            keyed[key] = record; manifest["records"] = list(keyed.values()); manifest["heartbeat_at"] = now(); atomic_json(target_manifest, manifest)
            for attempt in (1, 2):
                env = dict(base); env["E2B_API_KEY"] = e2b
                if model_spec["provider"] == "deepseek_official": env.update(AGENT_API_KEY=deepseek, AGENT_BASE_URL="https://api.deepseek.com")
                else: env.update(AGENT_API_KEY=tuzi_key, AGENT_BASE_URL=tuzi_url)
                input_root = campaign_root / "single_inputs" / task["task_id"]
                case_target = input_root / task["task_id"]
                if not case_target.exists(): case_target.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(Path(selection["solver_input_root"])/task["task_id"], case_target)
                output = campaign_root / "solver_outputs" / model_spec["model"] / task["task_id"]
                command = [sys.executable,"-m","task_generator.v3_rw_task_eval_stirrup_wrapper",str(input_root),"--output",str(output),"-w","1","--model",model_spec["model"],"--max-tokens","16384" if model_spec["model"]=="gpt-4o-mini" else "64000"]
                reservation = reserve_tuzi_call(campaign_root, spec, "solver", model_spec["model"]) if model_spec["provider"] == "tuzi" else None
                attempt_result = run_command(command, env, spec["solve_timeout_seconds"], campaign_root/"logs"/f"{task['task_id']}__{model_spec['model']}__{attempt}.out", campaign_root/"logs"/f"{task['task_id']}__{model_spec['model']}__{attempt}.err")
                if reservation:
                    finalize_tuzi_call(campaign_root, reservation, attempt_result["status"])
                record["attempts"].append(attempt_result)
                if attempt_result["status"] == "completed": break
            record["status"] = record["attempts"][-1]["status"]; record["finished_at"] = now(); manifest["records"] = list(keyed.values()); manifest["heartbeat_at"] = now(); atomic_json(target_manifest, manifest)
    manifest["status"] = (
        "solver_f4_2_completed" if selection.get("scope") == "f4_2_eight_task"
        else "solver_extended_completed" if selection.get("scope") == "extended_30" else "solver_pilot_completed"
    )
    atomic_json(target_manifest, manifest); return manifest


def status(campaign_root: Path) -> dict:
    path = manifest_path(campaign_root)
    if not path.exists(): return {"status":"not_started"}
    manifest = load_json(path); records=manifest.get("records",[])
    return {"status":manifest.get("status"),"heartbeat_at":manifest.get("heartbeat_at"),"record_count":len(records),
            "completed":sum(r.get("status")=="completed" for r in records),"failed":sum(r.get("status") in {"failed","timeout"} for r in records)}


def fixed_audit_assignments(selection: dict, models: list[str]) -> dict[str, str]:
    assignments = {}
    if selection.get("scope") == "f4_2_eight_task":
        tasks = sorted(selection["tasks"], key=lambda item: item.get("slot", item["global_index"]))
        return {task["task_id"]: models[index % len(models)] for index, task in enumerate(tasks)}
    for motif in ("fan_in_reconciliation", "cross_check_validation", "policy_application"):
        tasks = sorted(
            (item for item in selection["tasks"] if item["motif"] == motif and not item.get("is_pilot")),
            key=lambda item: item["global_index"],
        )
        for index, task in enumerate(tasks):
            assignments[task["task_id"]] = models[index % len(models)]
    return assignments


def _grade_one(campaign_root: Path, manifest: dict, target_manifest: Path, record: dict,
               grader_key: str, grader_model: str, key: str, url: str, timeout: int, spec: dict) -> None:
    if record.get(grader_key, {}).get("status") == "completed" and record[grader_key].get("score") is not None:
        return
    output = campaign_root / "solver_outputs" / record["model"] / record["task_id"]
    rows = list(output.rglob("dataset_row.json"))
    if not rows:
        record["status"] = "non_delivery"
        return
    contract = load_json(campaign_root / "grading_contracts" / f"{record['task_id']}.json")
    stage = campaign_root / "grading_staging" / grader_model / record["model"] / record["task_id"]
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(rows[0].parent, stage)
    row = load_json(stage / "dataset_row.json"); row.update(contract); atomic_json(stage / "dataset_row.json", row)
    out = campaign_root / "grades" / grader_model / record["model"] / record["task_id"]
    env = dict(os.environ); env.update(GRADER_API_KEY=key, GRADER_BASE_URL=url, GRADER_MODEL=grader_model)
    command = [sys.executable, "-m", "bench_standalone.grade_deliverables", str(stage), "--out-dir", str(out)]
    attempts = []
    for attempt in (1, 2):
        reservation = reserve_tuzi_call(campaign_root, spec, "grader", grader_model)
        result = run_command(
            command, env, timeout,
            campaign_root / "logs" / f"grade__{grader_model}__{record['task_id']}__{record['model']}__{attempt}.out",
            campaign_root / "logs" / f"grade__{grader_model}__{record['task_id']}__{record['model']}__{attempt}.err",
        )
        finalize_tuzi_call(campaign_root, reservation, result["status"])
        attempts.append(result)
        if result["status"] == "completed":
            break
    grade_files = sorted(out.glob("eval_*.json")); score = None
    if attempts[-1]["status"] == "completed" and grade_files:
        sample = load_json(grade_files[-1]).get("samples", [{}])[0]
        grading = sample.get("grading") or {}
        maximum = float(grading.get("max_possible_score") or 0)
        total = float(grading.get("total_score") or 0)
        score = total / maximum if maximum else None
    record[grader_key] = {**attempts[-1], "grader": grader_model, "score": score, "attempts": attempts}
    manifest["heartbeat_at"] = now(); atomic_json(target_manifest, manifest)


def _audit_disagrees(record: dict, spec: dict) -> bool:
    primary = record.get("primary_grade", {}).get("score")
    audit = record.get("audit_grade", {}).get("score")
    if primary is None or audit is None:
        return False
    difference = float(spec.get("audit_absolute_difference_threshold", .20))
    threshold = float(spec.get("audit_pass_threshold", .60))
    return abs(primary - audit) > difference or ((primary >= threshold) != (audit >= threshold))


def grade(campaign_root: Path, spec: dict, tuzi_env: Path) -> dict:
    target_manifest = manifest_path(campaign_root); manifest = load_json(target_manifest); tuzi = env_file(tuzi_env)
    selection = load_json(selection_path(campaign_root))
    key = tuzi.get("TUZI_API_KEY") or tuzi.get("AGENT_API_KEY") or tuzi.get("OPENAI_API_KEY")
    url = tuzi.get("TUZI_BASE_URL") or tuzi.get("AGENT_BASE_URL") or tuzi.get("OPENAI_BASE_URL")
    if not key or not url:
        raise RuntimeError("Tuzi grader secret missing")
    records = [record for record in manifest["records"] if record.get("status") == "completed" and not record.get("imported")]
    for record in records:
        _grade_one(campaign_root, manifest, target_manifest, record, "primary_grade", spec["primary_grader"], key, url, spec["grade_timeout_seconds"], spec)
    models = [item["model"] for item in spec["solver_models"]]
    assignments = fixed_audit_assignments(selection, models)
    by_task = {}
    for record in records:
        by_task.setdefault(record["task_id"], {})[record["model"]] = record
    for task_id, assigned_model in list(assignments.items()):
        assigned = by_task.get(task_id, {}).get(assigned_model)
        if assigned and assigned.get("primary_grade", {}).get("score") is not None:
            continue
        start = models.index(assigned_model)
        replacement = next((model for model in models[start + 1:] + models[:start]
                            if by_task.get(task_id, {}).get(model, {}).get("primary_grade", {}).get("score") is not None), None)
        if replacement:
            assignments[task_id] = replacement
    manifest["fixed_audit_assignments"] = assignments
    for record in records:
        if assignments.get(record["task_id"]) == record["model"]:
            record["audit_reason"] = "fixed_sample"
            _grade_one(campaign_root, manifest, target_manifest, record, "audit_grade", spec["audit_grader"], key, url, spec["grade_timeout_seconds"], spec)
    anomalous_tasks = {
        record["task_id"] for record in records
        if record.get("audit_reason") == "fixed_sample" and _audit_disagrees(record, spec)
    }
    for record in records:
        if record["task_id"] in anomalous_tasks:
            record["audit_reason"] = record.get("audit_reason") or "anomaly_expansion"
            _grade_one(campaign_root, manifest, target_manifest, record, "audit_grade", spec["audit_grader"], key, url, spec["grade_timeout_seconds"], spec)
    manifest["anomaly_expanded_task_ids"] = sorted(anomalous_tasks)
    primary_count = sum(r.get("primary_grade", {}).get("score") is not None for r in manifest["records"])
    manifest["status"] = (
        "f4_2_eval_completed_awaiting_interpretation"
        if selection.get("scope") == "f4_2_eight_task" and len(manifest["records"]) == 32 and primary_count >= 30
        else "thirty_task_eval_completed_awaiting_research_interpretation"
        if selection.get("scope") == "extended_30" and len(manifest["records"]) == 120 and primary_count >= 114
        else "pilot_completed_awaiting_cost_decision" if selection.get("scope") != "extended_30"
        else "thirty_task_eval_blocked"
    )
    atomic_json(target_manifest, manifest)
    return summarize(campaign_root)


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values); cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[cursor]]:
            end += 1
        rank = (cursor + end - 1) / 2
        for position in range(cursor, end):
            ranks[ordered[position]] = rank
        cursor = end
    return ranks


def _spearman(values: list[float]) -> float | None:
    if len(values) < 2 or len(set(values)) == 1:
        return None
    left = list(range(len(values))); right = _average_ranks(values)
    lm, rm = statistics.mean(left), statistics.mean(right)
    numerator = sum((a-lm)*(b-rm) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a-lm)**2 for a in left) * sum((b-rm)**2 for b in right))
    return numerator / denominator if denominator else None


def summarize(campaign_root: Path) -> dict:
    manifest = load_json(manifest_path(campaign_root)); records = manifest["records"]
    selection = load_json(selection_path(campaign_root)); task_meta = {item["task_id"]: item for item in selection["tasks"]}
    models = []
    for record in records:
        if record["model"] not in models:
            models.append(record["model"])
    task_rows = []
    for task_id in sorted({r["task_id"] for r in records}, key=lambda value: task_meta.get(value, {}).get("global_index", 10**9)):
        task_records = [r for r in records if r["task_id"] == task_id]
        by_model = {r["model"]: r.get("primary_grade", {}).get("score") for r in task_records}
        scores = [by_model.get(model) for model in models]; complete = all(score is not None for score in scores)
        spread = max(scores)-min(scores) if complete else None; label = None
        if complete:
            label = "mixed_signal"
            if min(scores) >= .75: label = "too_easy"
            elif max(scores) <= .40: label = "too_hard"
            elif spread >= .20 and max(scores) >= .65 and min(scores) <= .55: label = "informative"
            elif spread < .15: label = "compressed"
        audited = [r for r in task_records if r.get("audit_grade", {}).get("score") is not None]
        unstable = any(_audit_disagrees(r, {"audit_absolute_difference_threshold":.20,"audit_pass_threshold":.60}) for r in audited)
        audit_status = "grader_unstable" if unstable else "fully_dual_graded" if len(audited) == 4 else "sample_audit_stable" if audited else "awaiting_manual_review"
        valid_delivery_count = sum(score is not None for score in scores)
        externally_executable = valid_delivery_count >= 3 and any(score is not None and score >= .60 for score in scores)
        task_rows.append({"task_id":task_id,"global_index":task_meta.get(task_id,{}).get("global_index"),
                          "motif":task_meta.get(task_id,{}).get("motif"),"is_pilot":task_meta.get(task_id,{}).get("is_pilot",False),
                          "scores":by_model,"spread":spread,"standard_deviation":statistics.pstdev(scores) if complete else None,
                          "spearman_expected_order":_spearman(scores) if complete else None,"rank_inversion":(_spearman(scores) or 0) < 0 if complete else None,
                          "label":label,"grader_unstable":unstable,"audit_status":audit_status,"audited_output_count":len(audited),
                          "valid_delivery_count":valid_delivery_count,"externally_executable":externally_executable,
                          "common_task_failure":False,"task_quality_diagnosis":"pending_manual_diagnostic"})
    durations = [a["duration_seconds"] for r in records if not r.get("imported") for a in r.get("attempts",[]) if a.get("status")=="completed"]
    model_summary = {}
    for model in models:
        scores = [r.get("primary_grade",{}).get("score") for r in records if r["model"]==model]
        scores = [score for score in scores if score is not None]
        model_summary[model] = {"graded":len(scores),"mean":statistics.mean(scores) if scores else None,
                                "median":statistics.median(scores) if scores else None}
    pairwise = {}
    for left_index, left in enumerate(models):
        for right in models[left_index+1:]:
            comparable = [(row["scores"].get(left),row["scores"].get(right)) for row in task_rows]
            comparable = [(a,b) for a,b in comparable if a is not None and b is not None]
            pairwise[f"{left}__vs__{right}"] = {"left_wins":sum(a>b for a,b in comparable),"ties":sum(a==b for a,b in comparable),"right_wins":sum(a<b for a,b in comparable)}
    process_completed = sum(
        bool(r.get("imported")) or any(attempt.get("status") == "completed" for attempt in r.get("attempts", []))
        for r in records
    )
    supportive = (
        selection.get("scope") == "f4_2_eight_task"
        and sum(row["externally_executable"] for row in task_rows) >= 7
        and all(any(row["externally_executable"] for row in task_rows if row["motif"] == motif)
                for motif in {row["motif"] for row in task_rows})
        and sum((row["spread"] or 0) >= .15 for row in task_rows) >= 4
        and sum(row["grader_unstable"] for row in task_rows) <= 2
    )
    preliminary_decision = "f4_2_eval_supportive" if supportive else "f4_2_eval_mixed" if selection.get("scope") == "f4_2_eight_task" else None
    payload = {"version":"v3.finance_model_difference_summary.3","status":manifest.get("status"),"task_count":len(task_rows),
               "record_count":len(records),"solver_attempted":len(records),"solver_process_completed":process_completed,
               "valid_deliveries":sum(r.get("status")=="completed" for r in records),
               "non_delivery":sum(r.get("status")=="non_delivery" for r in records),
               "solver_completed":sum(r.get("status")=="completed" for r in records),
               "primary_graded":sum(r.get("primary_grade",{}).get("score") is not None for r in records),
               "audit_graded":sum(r.get("audit_grade",{}).get("score") is not None for r in records),
               "imported_pilot_records":sum(bool(r.get("imported")) for r in records),
               "new_solver_wall_time_seconds_sum":sum(durations),"median_solver_seconds":statistics.median(durations) if durations else None,
               "p90_solver_seconds":sorted(durations)[max(0,math.ceil(.9*len(durations))-1)] if durations else None,
               "model_summary":model_summary,"pairwise_wins":pairwise,"tasks":task_rows,
               "preliminary_decision":preliminary_decision,
               "decision_requires_manual_failure_diagnosis":selection.get("scope") == "f4_2_eight_task",
               "call_ledger":{"deepseek_solver_estimated_rmb":3.52 if selection.get("scope") != "f4_2_eight_task" else None,
                              "deepseek_actual_rmb":None,"tuzi_actual_cost":"pending_provider_reconciliation",
                              "tuzi_reserved_spend_rmb":load_json(_cost_ledger_path(campaign_root)).get("reserved_spend_rmb") if _cost_ledger_path(campaign_root).exists() else 0,
                              "new_tuzi_solver_calls":sum(r.get("provider")=="tuzi" and not r.get("imported") for r in records),
                              "new_primary_grade_calls":sum(not r.get("imported") and r.get("primary_grade",{}).get("score") is not None for r in records),
                              "new_audit_grade_calls":sum(not r.get("imported") and r.get("audit_grade",{}).get("score") is not None for r in records)},
               "cost_note":"Provider token usage and account debit must be reconciled from provider logs; unavailable values remain explicit."}
    summary_name = "f4_2_eight_task_summary.json" if selection.get("scope") == "f4_2_eight_task" else "extended_30_summary.json" if selection.get("scope")=="extended_30" else "pilot_summary.json"
    atomic_json(campaign_root / summary_name, payload)
    return payload


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--action",choices=["preflight","prepare","run","resume","grade","report","status"],required=True)
    parser.add_argument("--production-root",type=Path,default=Path("/data/runs/finance_audit_production_01")); parser.add_argument("--campaign-root",type=Path,default=Path("/data/runs/finance_model_difference_eval_30_01"))
    parser.add_argument("--pilot-campaign-root",type=Path,default=Path("/data/runs/finance_model_difference_eval_01"))
    parser.add_argument("--source-campaign-root",type=Path,default=Path("/data/runs/finance_f4_from_scratch_validation_02"))
    parser.add_argument("--spec",type=Path,default=SPEC); parser.add_argument("--tuzi-env",type=Path,default=Path("/run/secrets/eval_tuzi_env")); parser.add_argument("--deepseek-key",type=Path,default=Path("/run/secrets/deepseek_api_key")); parser.add_argument("--e2b-key",type=Path,default=Path("/run/secrets/e2b_api_key"))
    args=parser.parse_args(); spec=load_json(args.spec)
    if args.action=="preflight": payload=provider_preflight(args.campaign_root,spec,args.tuzi_env,args.deepseek_key)
    elif args.action=="prepare": payload=prepare(args.production_root,args.campaign_root,spec,args.pilot_campaign_root,args.source_campaign_root)
    elif args.action=="status": payload=status(args.campaign_root)
    elif args.action=="grade": payload=grade(args.campaign_root,spec,args.tuzi_env)
    elif args.action=="report": payload=summarize(args.campaign_root)
    else: payload=execute(args.campaign_root,spec,args.tuzi_env,args.deepseek_key,args.e2b_key)
    print(json.dumps(payload if args.action!="run" and args.action!="resume" else status(args.campaign_root),ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
