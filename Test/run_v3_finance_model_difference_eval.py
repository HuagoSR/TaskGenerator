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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "SkillRegistry" / "v3_finance_model_difference_eval.experimental.json"
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
        record = {
            "task_id": row["task_id"], "global_index": int(digits), "motif": motif,
            "skills": sorted(blueprint.get("selected_skills") or []), "case_dir": str(case),
            "dataset_row_path": str(row_path), "reference_dir": str(case / "rw_task_export" / "reference_files"),
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


def prepare(production_root: Path, campaign_root: Path) -> dict:
    index = build_index(production_root)
    if len(index) != 60:
        raise RuntimeError(f"expected 60 tasks, found {len(index)}")
    selected = select_pilot(index)
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
        })
        forbidden = [str(path) for path in target.rglob("*") if path.name in FORBIDDEN_NAMES]
        if forbidden or set(solver_row) - ALLOWED_SOLVER_KEYS:
            raise RuntimeError(f"teacher-only truth leaked for {item['task_id']}")
    payload = {"version": "v3.finance_model_difference_pilot.1", "created_at": now(), "task_count": len(selected),
               "tasks": selected, "solver_input_root": str(solver_root), "solver_input_sha256": {
                   str(path.relative_to(solver_root)): sha256(path) for path in sorted(solver_root.rglob("*")) if path.is_file()
               }}
    atomic_json(campaign_root / "pilot_selection.json", payload)
    return payload


def env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1); values[key.strip()] = value.strip()
    return values


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


def execute(campaign_root: Path, spec: dict, tuzi_env: Path, deepseek_key: Path, e2b_key: Path) -> dict:
    selection = load_json(campaign_root / "pilot_selection.json")
    tuzi = env_file(tuzi_env); base = dict(os.environ)
    tuzi_key = tuzi.get("TUZI_API_KEY") or tuzi.get("AGENT_API_KEY") or tuzi.get("OPENAI_API_KEY")
    tuzi_url = tuzi.get("TUZI_BASE_URL") or tuzi.get("AGENT_BASE_URL") or tuzi.get("OPENAI_BASE_URL")
    e2b = e2b_key.read_text(encoding="utf-8").strip(); deepseek = deepseek_key.read_text(encoding="utf-8").strip()
    if not all((tuzi_key, tuzi_url, e2b, deepseek)): raise RuntimeError("required eval secrets are missing")
    manifest_path = campaign_root / "pilot_manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {"version":"v3.finance_model_difference_eval.1","created_at":now(),"status":"running","records":[]}
    keyed = {(r["task_id"], r["model"]): r for r in manifest["records"]}
    for task in selection["tasks"]:
        for model_spec in spec["solver_models"]:
            key = (task["task_id"], model_spec["model"])
            if keyed.get(key, {}).get("status") == "completed": continue
            record = {"task_id":key[0],"model":key[1],"provider":model_spec["provider"],"status":"running","started_at":now(),"attempts":[]}
            keyed[key] = record; manifest["records"] = list(keyed.values()); manifest["heartbeat_at"] = now(); atomic_json(manifest_path, manifest)
            for attempt in (1, 2):
                env = dict(base); env["E2B_API_KEY"] = e2b
                if model_spec["provider"] == "deepseek_official": env.update(AGENT_API_KEY=deepseek, AGENT_BASE_URL="https://api.deepseek.com")
                else: env.update(AGENT_API_KEY=tuzi_key, AGENT_BASE_URL=tuzi_url)
                input_root = campaign_root / "single_inputs" / task["task_id"]
                case_target = input_root / task["task_id"]
                if not case_target.exists(): case_target.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(Path(selection["solver_input_root"])/task["task_id"], case_target)
                output = campaign_root / "solver_outputs" / model_spec["model"] / task["task_id"]
                command = [sys.executable,"-m","task_generator.v3_rw_task_eval_stirrup_wrapper",str(input_root),"--output",str(output),"-w","1","--model",model_spec["model"],"--max-tokens","16384" if model_spec["model"]=="gpt-4o-mini" else "64000"]
                attempt_result = run_command(command, env, spec["solve_timeout_seconds"], campaign_root/"logs"/f"{task['task_id']}__{model_spec['model']}__{attempt}.out", campaign_root/"logs"/f"{task['task_id']}__{model_spec['model']}__{attempt}.err")
                record["attempts"].append(attempt_result)
                if attempt_result["status"] == "completed": break
            record["status"] = record["attempts"][-1]["status"]; record["finished_at"] = now(); manifest["records"] = list(keyed.values()); manifest["heartbeat_at"] = now(); atomic_json(manifest_path, manifest)
    manifest["status"] = "solver_pilot_completed"; atomic_json(manifest_path, manifest); return manifest


def status(campaign_root: Path) -> dict:
    path = campaign_root / "pilot_manifest.json"
    if not path.exists(): return {"status":"not_started"}
    manifest = load_json(path); records=manifest.get("records",[])
    return {"status":manifest.get("status"),"heartbeat_at":manifest.get("heartbeat_at"),"record_count":len(records),
            "completed":sum(r.get("status")=="completed" for r in records),"failed":sum(r.get("status") in {"failed","timeout"} for r in records)}


def grade(campaign_root: Path, spec: dict, tuzi_env: Path) -> dict:
    manifest_path=campaign_root/"pilot_manifest.json"; manifest=load_json(manifest_path); tuzi=env_file(tuzi_env)
    key=tuzi.get("TUZI_API_KEY") or tuzi.get("AGENT_API_KEY") or tuzi.get("OPENAI_API_KEY"); url=tuzi.get("TUZI_BASE_URL") or tuzi.get("AGENT_BASE_URL") or tuzi.get("OPENAI_BASE_URL")
    if not key or not url: raise RuntimeError("Tuzi grader secret missing")
    for record in manifest["records"]:
        if record.get("status")!="completed": continue
        output=campaign_root/"solver_outputs"/record["model"]/record["task_id"]
        rows=list(output.rglob("dataset_row.json")); contract=load_json(campaign_root/"grading_contracts"/f"{record['task_id']}.json")
        if not rows: record["status"]="non_delivery"; continue
        for grader_key,grader_model in (("primary_grade",spec["primary_grader"]),("audit_grade",spec["audit_grader"])):
            if record.get(grader_key,{}).get("status")=="completed": continue
            stage=campaign_root/"grading_staging"/grader_model/record["model"]/record["task_id"]
            if stage.exists(): shutil.rmtree(stage)
            shutil.copytree(rows[0].parent,stage)
            row=load_json(stage/"dataset_row.json"); row.update(contract); atomic_json(stage/"dataset_row.json",row)
            out=campaign_root/"grades"/grader_model/record["model"]/record["task_id"]
            env=dict(os.environ); env.update(GRADER_API_KEY=key,GRADER_BASE_URL=url,GRADER_MODEL=grader_model)
            command=[sys.executable,"-m","bench_standalone.grade_deliverables",str(stage),"--out-dir",str(out)]
            result=run_command(command,env,spec["grade_timeout_seconds"],campaign_root/"logs"/f"grade__{grader_model}__{record['task_id']}__{record['model']}.out",campaign_root/"logs"/f"grade__{grader_model}__{record['task_id']}__{record['model']}.err")
            grade_files=sorted(out.glob("eval_*.json")); score=None
            if result["status"]=="completed" and grade_files:
                sample=load_json(grade_files[-1]).get("samples",[{}])[0]; grading=sample.get("grading") or {}; maximum=float(grading.get("max_possible_score") or 0); total=float(grading.get("total_score") or 0); score=total/maximum if maximum else None
            record[grader_key]={**result,"grader":grader_model,"score":score}
            manifest["heartbeat_at"]=now(); atomic_json(manifest_path,manifest)
    manifest["status"]="pilot_completed_awaiting_cost_decision"; atomic_json(manifest_path,manifest); return summarize(campaign_root)


def summarize(campaign_root: Path) -> dict:
    manifest=load_json(campaign_root/"pilot_manifest.json"); records=manifest["records"]; task_rows=[]
    for task_id in sorted({r["task_id"] for r in records}):
        task_records=[r for r in records if r["task_id"]==task_id]; scores=[r.get("primary_grade",{}).get("score") for r in task_records]; scores=[s for s in scores if s is not None]
        spread=max(scores)-min(scores) if scores else None
        label="mixed_signal"
        if len(scores)==4:
            if min(scores)>=.75: label="too_easy"
            elif max(scores)<=.40: label="too_hard"
            elif spread>=.20 and max(scores)>=.65 and min(scores)<=.55: label="informative"
            elif spread<.15: label="compressed"
        task_rows.append({"task_id":task_id,"scores":{r["model"]:r.get("primary_grade",{}).get("score") for r in task_records},"spread":spread,"label":label,
                          "grader_unstable":any(abs((r.get("primary_grade",{}).get("score") or 0)-(r.get("audit_grade",{}).get("score") or 0))>.20 for r in task_records if r.get("primary_grade",{}).get("score") is not None and r.get("audit_grade",{}).get("score") is not None)})
    durations=[a["duration_seconds"] for r in records for a in r.get("attempts",[]) if a.get("status")=="completed"]
    payload={"version":"v3.finance_model_difference_summary.1","status":manifest.get("status"),"record_count":len(records),"solver_completed":sum(r.get("status")=="completed" for r in records),"primary_graded":sum(r.get("primary_grade",{}).get("score") is not None for r in records),"audit_graded":sum(r.get("audit_grade",{}).get("score") is not None for r in records),"wall_time_seconds_sum":sum(durations),"median_solver_seconds":statistics.median(durations) if durations else None,"p90_solver_seconds":sorted(durations)[max(0,math.ceil(.9*len(durations))-1)] if durations else None,"tasks":task_rows,"cost_note":"Provider token usage and account debit must be reconciled from provider logs; unavailable values remain explicit."}
    atomic_json(campaign_root/"pilot_summary.json",payload); return payload


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--action",choices=["prepare","run","resume","grade","report","status"],required=True)
    parser.add_argument("--production-root",type=Path,default=Path("/data/runs/finance_audit_production_01")); parser.add_argument("--campaign-root",type=Path,default=Path("/data/runs/finance_model_difference_eval_01"))
    parser.add_argument("--spec",type=Path,default=SPEC); parser.add_argument("--tuzi-env",type=Path,default=Path("/run/secrets/eval_tuzi_env")); parser.add_argument("--deepseek-key",type=Path,default=Path("/run/secrets/deepseek_api_key")); parser.add_argument("--e2b-key",type=Path,default=Path("/run/secrets/e2b_api_key"))
    args=parser.parse_args(); spec=load_json(args.spec)
    if args.action=="prepare": payload=prepare(args.production_root,args.campaign_root)
    elif args.action=="status": payload=status(args.campaign_root)
    elif args.action=="grade": payload=grade(args.campaign_root,spec,args.tuzi_env)
    elif args.action=="report": payload=summarize(args.campaign_root)
    else: payload=execute(args.campaign_root,spec,args.tuzi_env,args.deepseek_key,args.e2b_key)
    print(json.dumps(payload if args.action!="run" and args.action!="resume" else status(args.campaign_root),ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
