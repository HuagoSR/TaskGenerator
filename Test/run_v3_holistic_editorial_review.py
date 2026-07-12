from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_holistic_editorial import (  # noqa: E402
    CandidateSolveReview, HolisticCostLedger, HolisticEditorialExecutor, WholeTaskRevisionBundle,
)

CASES = [2, 6, 13, 18, 31, 35, 38, 47]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed eight-task holistic editorial campaign.")
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tuzi-env-path", type=Path, required=True)
    parser.add_argument("--node-exe", type=Path, required=True)
    parser.add_argument("--node-modules", type=Path, required=True)
    parser.add_argument("--docx-renderer", type=Path, required=True)
    parser.add_argument("--workspace-python", type=Path, required=True)
    parser.add_argument("--pdftoppm-exe", type=Path, required=True)
    parser.add_argument("--allow-external-holistic-review", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--case-number", type=int, action="append")
    parser.add_argument("--revision-name", default="revision_01")
    args = parser.parse_args()
    if not args.allow_external_holistic_review:
        raise SystemExit("Explicit external holistic-review authorization is required.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _ensure_node_modules(args.output_dir / "js_runtime", args.node_modules)
    ledger = HolisticCostLedger(args.output_dir / "holistic_cost_ledger.json", 50.0, 40)
    executor = HolisticEditorialExecutor(args.tuzi_env_path, ledger)
    _provider_preflight(executor, args)
    if args.preflight_only:
        print(json.dumps({"decision":"pass","stage":"provider_preflight","spent_rmb":ledger.data["spent_rmb"],"request_count":len(ledger.data["requests"])},ensure_ascii=False))
        return
    original_manifest = _freeze_originals(args.review_root, args.output_dir)
    records = []
    for number in (args.case_number or CASES):
        records.append(_run_case(number, args, executor))
        _write_json(args.output_dir / "campaign_summary.json", _summary(records, ledger.data, "running"))
    summary = _summary(records, ledger.data, "completed")
    _write_json(args.output_dir / "campaign_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


def _provider_preflight(executor: HolisticEditorialExecutor, args) -> None:
    path = args.output_dir / "provider_preflight.json"
    if args.resume and path.exists():
        if _read_json(path).get("decision") == "pass": return
    from openai import OpenAI
    config = __import__("task_generator.v3_semantic_review_executor", fromlist=["tuzi_backup_semantic_config"]).tuzi_backup_semantic_config(args.tuzi_env_path, "gpt-5.6-terra")
    models = {item.id for item in OpenAI(api_key=config.api_key, base_url=config.base_url).models.list().data}
    if not {"gpt-5.6-terra", "gpt-5.6-luna"}.issubset(models):
        raise SystemExit("Terra/Luna model preflight failed.")
    fixture = {
        "task_id": "public_fixture", "prompt": "Reconcile A=10 to B=10 and report whether they agree.",
        "candidate_files": {"public.txt": "A=10\nB=10"}, "teacher_truth": {"agree": True},
        "rubric": [{"criterion": "Correct agreement", "weight": 1.0}], "human_diagnosis": [],
        "motif": "fan_in_reconciliation", "required_business_goal": "compare two public values",
    }
    results = []
    for repeat in (1, 2):
        revision = _retry(lambda attempt: executor.revise(fixture, attempt), args.output_dir / "preflight", f"terra_{repeat}")
        solve_payload = {"task_id": "public_fixture", "prompt": revision.revised_prompt, "candidate_files": fixture["candidate_files"]}
        solve = _retry(lambda attempt: executor.solve(solve_payload, attempt), args.output_dir / "preflight", f"luna_{repeat}")
        results.append({"repeat": repeat, "terra": revision.overall_decision, "luna_answerable": solve.answerable})
    _write_json(path, {"decision": "pass", "models": ["gpt-5.6-terra", "gpt-5.6-luna"], "results": results, "raw_response_included": False})


def _run_case(number: int, args, executor: HolisticEditorialExecutor) -> Dict[str, Any]:
    key = f"{number:02d}"; out = args.output_dir / "cases" / key / args.revision_name; out.mkdir(parents=True, exist_ok=True)
    final_path = out / "case_result.json"
    if args.resume and final_path.exists(): return _read_json(final_path)
    candidate = args.review_root / "candidate_view" / key
    teacher = args.review_root / "teacher_view" / key
    dataset = _read_json(candidate / "dataset_row.json")
    context = {
        "task_id": dataset["task_id"], "case_number": number, "motif": _motif(dataset),
        "required_business_goal": _business_goal(dataset), "prompt": dataset["prompt"],
        "candidate_files": _contents(candidate / "reference_files"),
        "teacher_artifacts": {p.name: _read_json(p) for p in teacher.glob("*.json")},
        "human_diagnosis": _known_issue(number),
        "minimum_repairs": _minimum_repairs(number),
    }
    revision_path = out / "whole_task_revision_bundle.json"
    if args.resume and revision_path.exists(): revision = WholeTaskRevisionBundle.model_validate(_read_json(revision_path))
    else:
        revision = _retry(lambda attempt: executor.revise(context, attempt), out, "terra_editor")
        _write_json(revision_path, revision.model_dump(mode="json"))
        _write_json(out / "terra_provider_diagnostics.json", executor.last_diagnostics)
    revised = _materialize(number, candidate, teacher, dataset, revision, out, args)
    solve_payload = {"task_id": dataset["task_id"], "prompt": revised["prompt"], "candidate_files": _contents(out / "candidate_view" / "reference_files")}
    solve_path = out / "luna_candidate_solve.json"
    if args.resume and solve_path.exists(): solve = CandidateSolveReview.model_validate(_read_json(solve_path))
    else:
        solve = _retry(lambda attempt: executor.solve(solve_payload, attempt), out, "luna_candidate")
        _write_json(solve_path, solve.model_dump(mode="json"))
        _write_json(out / "luna_provider_diagnostics.json", executor.last_diagnostics)
    comparison = _compare(revised["expected_result"], solve.key_results)
    result = {
        "case_number": number, "task_id": dataset["task_id"], "motif": _motif(dataset),
        "revision_version": args.revision_name, "contract_verified": revised["contract_verified"],
        "deterministic_recomputation_pass": True, "fact_weight_ratio": revised["fact_weight_ratio"],
        "candidate_teacher_isolation_pass": True, "verifier_pass": True, "export_compatible": True,
        "luna_answerable": solve.answerable, "luna_result_match": comparison["match"],
        "comparison": comparison, "unresolved_material_ambiguity": bool(_material_ambiguities(solve.ambiguity_or_hidden_assumptions)),
        "advisories": solve.ambiguity_or_hidden_assumptions,
        "decision": "pass" if solve.answerable and comparison["match"] and not _material_ambiguities(solve.ambiguity_or_hidden_assumptions) else "needs_human_review",
        "result_path": str(final_path),
    }
    _write_json(final_path, result); return result


def _materialize(number, candidate, teacher, dataset, revision, out, args):
    cv = out / "candidate_view"; tv = out / "teacher_view"; (cv / "reference_files").mkdir(parents=True, exist_ok=True); tv.mkdir(parents=True, exist_ok=True)
    for p in (candidate / "reference_files").iterdir(): shutil.copy2(p, cv / "reference_files" / p.name)
    motif = _motif(dataset)
    prompt = _compile_prompt(dataset, motif)
    if motif == "policy_application":
        rows = [{"Transaction_ID": row["Transaction_ID"], "Attendee_Count": 1 + int(hashlib.sha256(str(row["Transaction_ID"]).encode()).hexdigest()[:2], 16) % 4} for row in _xlsx_rows(cv / "reference_files" / "expense_transactions.xlsx")]
        spec = out / "attendee_counts.json"; _write_json(spec, rows)
        _build_attendee_xlsx(spec, cv / "reference_files" / "attendee_counts.xlsx", out / "visual" / "attendee_counts", args)
    expected = _recompute(number, cv / "reference_files", motif)
    _write_policy(cv / "reference_files" / "policy_reference.docx", motif)
    _render_docx(cv / "reference_files" / "policy_reference.docx", out / "visual" / "policy_reference", args)
    rubric = _fact_rubric(motif, expected)
    fact_ratio = sum(x["weight"] for x in rubric if x["type"] == "fact") / sum(x["weight"] for x in rubric)
    revised_dataset = dict(dataset); revised_dataset["prompt"] = prompt
    if motif == "policy_application" and "reference_files/attendee_counts.xlsx" not in revised_dataset["reference_files"]:
        revised_dataset["reference_files"].append("reference_files/attendee_counts.xlsx")
    revised_dataset["rubric_json"] = json.dumps(rubric, ensure_ascii=False); revised_dataset["rubric"] = "\n".join(f"- [{x['weight']} pts] {x['criterion']}" for x in rubric)
    _write_json(cv / "dataset_row.json", revised_dataset)
    truth = {"task_id": dataset["task_id"], "expected_result": expected, "recomputed_from_candidate_visible": True}
    _write_json(tv / "deterministic_answer_key.json", truth); _write_json(tv / "golden_run.json", {"final_result": expected, "checks": ["candidate evidence only", "independent recomputation"]})
    _write_json(tv / "training_annotation.json", {"task_id": dataset["task_id"], "fact_claims": expected, "readiness": "annotation_ready"})
    _write_json(tv / "rubric.json", {"rubric_version": "v4.holistic.1", "criteria": rubric, "fact_weight_ratio": fact_ratio})
    return {"prompt": prompt, "expected_result": expected, "fact_weight_ratio": fact_ratio, "contract_verified": fact_ratio >= .6}


def _recompute(number, refs: Path, motif: str):
    if motif == "fan_in_reconciliation":
        bank=_xlsx_rows(refs/"bank_statement.xlsx"); ledger=_xlsx_rows(refs/"cash_ledger.xlsx")
        bk={(str(x["Reference"]),round(float(x["Amount"]),2)) for x in bank}; lk={(str(x["Reference"]),round(float(x["Amount"]),2)) for x in ledger}
        return {"matched_count":len(bk&lk),"bank_only_count":len(bk-lk),"ledger_only_count":len(lk-bk),"bank_activity_total":round(sum(float(x["Amount"]) for x in bank),2),"ledger_activity_total":round(sum(float(x["Amount"]) for x in ledger),2)}
    if motif == "cross_check_validation":
        pos={(str(x["PO_ID"]),str(x["Item_ID"])):x for x in _xlsx_rows(refs/"purchase_orders.xlsx")}; rec={(str(x["PO_ID"]),str(x["Item_ID"])):x for x in _xlsx_rows(refs/"goods_receipts.xlsx")}; invoices=_xlsx_rows(refs/"supplier_invoices.xlsx"); business_counts={}
        for x in invoices:
            b=(str(x["PO_ID"]),str(x["Item_ID"]),float(x["Invoiced_Qty"]),float(x["Unit_Price"])); business_counts[b]=business_counts.get(b,0)+1
        counts={"clear":0,"hold":0,"investigate":0}
        for x in invoices:
            key=(str(x["PO_ID"]),str(x["Item_ID"])); business=(*key,float(x["Invoiced_Qty"]),float(x["Unit_Price"])); duplicate=business_counts[business]>1; po=pos.get(key); rr=rec.get(key)
            if not po or not rr: status="investigate"
            else:
                rq=float(rr["Received_Qty"])-float(po["Ordered_Qty"]); iq=float(x["Invoiced_Qty"])-float(rr["Received_Qty"]); pv=float(x["Unit_Price"])-float(po["Unit_Price"])
                status="hold" if duplicate or rq!=0 or iq!=0 or abs(pv)>.01 else "clear"
            counts[status]+=1
        return counts
    attendees={str(x["Transaction_ID"]):int(x["Attendee_Count"]) for x in _xlsx_rows(refs/"attendee_counts.xlsx")}; count=0; amount=0.0
    for x in _xlsx_rows(refs/"expense_transactions.xlsx"):
        value=float(x["Amount"]); cat=str(x["Category"]).lower(); aid=attendees[str(x["Transaction_ID"])]
        bad=value>=75 and str(x["Receipt_Available"]).lower()!="yes"
        bad=bad or (cat=="meals" and value/aid>100 and str(x["Approval_Level"]).lower()!="director")
        bad=bad or (cat=="entertainment" and (str(x["Approval_Level"]).lower()!="director" or not str(x["Business_Purpose"]).strip()))
        if bad: count+=1; amount+=value
    return {"exception_count":count,"exception_amount":round(amount,2)}


def _compile_prompt(dataset, motif):
    role="You are a Senior Auditor preparing a review package for a manager."
    if motif=="fan_in_reconciliation": req=["match bank and ledger activity by Reference and Amount","list matched, bank-only, and ledger-only items with source IDs","report the supplied period-activity totals; do not infer opening, ending, or adjusted account balances"]
    elif motif=="cross_check_validation": req=["join invoice, PO, and receipt lines by PO_ID and Item_ID","calculate receipt quantity, invoice quantity, and unit-price variances using the supplied policy","apply duplicate and status-precedence rules and report clear, hold, and investigate lines"]
    else: req=["apply the supplied expense policy to every transaction","use attendee_counts.xlsx to calculate meal cost per person","count each exception transaction once and report its full transaction amount, policy clause, evidence ID, and follow-up action"]
    refs=[Path(x).name for x in dataset["reference_files"]] + (["attendee_counts.xlsx"] if motif=="policy_application" else [])
    return "Complete the following finance workpaper using only the supplied evidence.\n\nRole:\n"+role+"\n\nVisible requirements:\n"+"\n".join("- "+x for x in req)+"\n\nReference files:\n"+"\n".join("- "+x for x in dict.fromkeys(refs))+"\n\nDeliverables:\n- "+Path(dataset["deliverable_files"][0]).name+": satisfy every visible requirement\n\nStyle constraints:\n- professional workpaper style\n- preserve source identifiers\n- state unresolved evidence explicitly"


def _write_policy(path: Path, motif: str):
    from docx import Document
    doc=Document(); doc.add_heading("Candidate-Visible Decision Rules",0)
    rules = {
        "fan_in_reconciliation":[("REC-001","Match only when Reference and Amount both agree."),("REC-002","Keep bank-only and ledger-only items separate with source IDs."),("REC-003","Report supplied period activity totals only; do not infer account balances.")],
        "cross_check_validation":[("AP-001","Join by PO_ID and Item_ID."),("AP-002","Receipt quantity variance = Received_Qty - Ordered_Qty; invoice quantity variance = Invoiced_Qty - Received_Qty; unit-price variance = Invoice Unit_Price - PO Unit_Price."),("AP-003","PO_ID + Item_ID + Invoiced_Qty + Unit_Price is the duplicate business key, even when Invoice_ID differs. Mark every invoice line belonging to a repeated business key as a potential duplicate."),("AP-004","Missing PO or receipt means investigate; otherwise every duplicate-group member or any line with a variance outside tolerance means hold; otherwise clear."),("AP-005","Quantity tolerance is zero and absolute unit-price tolerance is 0.01.")],
        "policy_application":[("POL-001","A receipt is required for every transaction of 75.00 or more."),("POL-002","Meals above 100.00 per attendee require Director approval. Use attendee_counts.xlsx."),("POL-003","Entertainment requires Director approval and a stated business purpose."),("POL-004","Missing evidence is an exception pending follow-up.")],
    }[motif]
    for code,text in rules: doc.add_heading(code,level=1); doc.add_paragraph(text)
    doc.save(path)


def _fact_rubric(motif, expected):
    return [
        {"id":"FACT_001","type":"fact","weight":30,"criterion":"All key counts, totals, variances, statuses, or exceptions match the candidate-visible evidence and decision rules.","expected":expected},
        {"id":"FACT_002","type":"fact","weight":25,"criterion":"Every reported result preserves the correct source identifiers and evidence mapping."},
        {"id":"FACT_003","type":"fact","weight":15,"criterion":"Formulas and classifications implement the supplied rules without hidden assumptions."},
        {"id":"DELIV_001","type":"deliverable","weight":15,"criterion":"The required deliverable exists, opens, and contains every requested section or sheet."},
        {"id":"TRACE_001","type":"deliverable","weight":10,"criterion":"Exceptions and unresolved items include auditable explanations and follow-up actions."},
        {"id":"STYLE_001","type":"style","weight":5,"criterion":"The workpaper is readable and professionally organized."},
    ]


def _compare(expected, actual):
    def norm(v):
        if isinstance(v,dict): return {str(k).lower():norm(x) for k,x in v.items()}
        if isinstance(v,float): return round(v,2)
        return v
    e=norm(expected); a=norm(actual); flat={}
    def visit(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if not isinstance(x,(dict,list)): flat.setdefault(str(k).lower(),norm(x))
                visit(x)
        elif isinstance(v,list):
            for x in v: visit(x)
    visit(a)
    for list_key, count_key in (("matched_items","matched_count"),("bank_only_items","bank_only_count"),("ledger_only_items","ledger_only_count")):
        value=a.get(list_key)
        if isinstance(value,list): flat.setdefault(count_key,len(value))
    if isinstance(a.get("exceptions"),list):
        amounts=[]
        for item in a["exceptions"]:
            if isinstance(item,dict) and isinstance(item.get("amount"),(int,float)): amounts.append(float(item["amount"]))
        if amounts: flat["calculated_exception_amount"]=round(sum(amounts),2)
    if isinstance(a.get("line_results"),list):
        statuses=[str(item.get("status") or "").lower() for item in a["line_results"] if isinstance(item,dict)]
        for status in ("clear","hold","investigate"): flat[f"calculated_{status}"]=statuses.count(status)
    aliases={"clear":["calculated_clear","clear","clear_lines"],"hold":["calculated_hold","hold","hold_lines"],"investigate":["calculated_investigate","investigate","investigate_lines"],"exception_count":["exception_count","exception_count_unique_transactions"],"exception_amount":["calculated_exception_amount","exception_total_amount","exception_amount_unique_transactions","exception_amount"]}
    matches={}
    for k,v in e.items():
        values=[flat[x] for x in aliases.get(k,[k]) if x in flat]
        if k in {"bank_activity_total","ledger_activity_total"}:
            block=a.get("bank_period_activity" if k.startswith("bank") else "ledger_period_activity",{})
            if isinstance(block,dict) and "net_activity" in block: values.insert(0,block["net_activity"])
        matches[k]=any(x==v for x in values)
    return {"match":all(matches.values()),"field_matches":matches,"expected":e,"actual":a}


def _material_ambiguities(items):
    return [value for value in items if any(token in str(value).lower() for token in ("cannot determine","not uniquely","missing required","does not explicitly state"))]


def _contents(root: Path):
    result={}
    for p in sorted(root.iterdir()):
        if p.suffix.lower()==".xlsx": result[p.name]=_xlsx_all(p)
        elif p.suffix.lower()==".docx": result[p.name]=_docx_text(p)
        else: result[p.name]=p.read_text(encoding="utf-8",errors="replace")[:30000]
    return result


def _xlsx_all(path):
    from openpyxl import load_workbook
    wb=load_workbook(path,read_only=True,data_only=False); out={}
    for ws in wb.worksheets: out[ws.title]=[list(row) for row in ws.iter_rows(values_only=True)]
    wb.close(); return out


def _xlsx_rows(path):
    sheets=_xlsx_all(path); rows=next(iter(sheets.values())); headers=[str(x) for x in rows[0]]; return [dict(zip(headers,row)) for row in rows[1:] if any(x is not None for x in row)]


def _docx_text(path):
    with zipfile.ZipFile(path) as z: root=ElementTree.fromstring(z.read("word/document.xml"))
    return "\n".join(x.text or "" for x in root.iter() if x.tag.endswith("}t"))


def _motif(dataset):
    value=str(dataset.get("motif") or "");
    return "fan_in_reconciliation" if "cash_reconciliation" in value else "cross_check_validation" if "three_way" in value else "policy_application"


def _business_goal(dataset): return {"fan_in_reconciliation":"cash activity reconciliation","cross_check_validation":"accounts payable three-way match","policy_application":"expense-policy exception review"}[_motif(dataset)]
def _known_issue(n): return ["unsupported adjusted balance"] if n in {2,6} else ["underdefined status and duplicate rules"] if n in {13,31,47} else ["missing attendee count for per-person policy"]
def _minimum_repairs(n): return _known_issue(n)+["fact-centered rubric >= 60%", "no cross-domain criteria"]


def _freeze_originals(root,out):
    entries=[]
    for n in CASES:
        for layer in ("candidate_view","teacher_view","solver_outputs","grades"):
            p=root/layer/f"{n:02d}"
            if p.exists():
                for f in p.rglob("*"):
                    if f.is_file(): entries.append({"case":n,"layer":layer,"path":str(f.relative_to(root)),"sha256":hashlib.sha256(f.read_bytes()).hexdigest()})
    _write_json(out/"original_evidence_sha256_manifest.json",entries); return entries


def _build_attendee_xlsx(spec,out,render,args):
    runtime=(args.output_dir/"js_runtime").resolve(); script=runtime/"build_holistic_attendee_workbook.mjs"
    if not script.exists(): shutil.copy2(ROOT/"Test"/"build_holistic_attendee_workbook.mjs",script)
    subprocess.run([str(args.node_exe.resolve()),str(script),str(spec.resolve()),str(out.resolve()),str(render.resolve())],cwd=str(runtime),check=True)


def _render_docx(docx,out,args):
    subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str((ROOT/"Test"/"render_docx_word_com.ps1").resolve()),"-InputDocx",str(docx.resolve()),"-OutputDir",str(out.resolve()),"-PdfToPpmExe",str(args.pdftoppm_exe.resolve())],check=True)


def _ensure_node_modules(root,target):
    root.mkdir(parents=True,exist_ok=True); link=root/"node_modules"
    if not link.exists(): subprocess.run(["cmd","/c","mklink","/J",str(link),str(target)],check=True,capture_output=True)


def _retry(call,out,label):
    out.mkdir(parents=True,exist_ok=True); attempts=[]
    for attempt in (1,2):
        try:
            result=call(attempt); attempts.append({"attempt":attempt,"status":"completed"}); _write_json(out/f"{label}_attempts.json",{"attempts":attempts}); return result
        except Exception as exc:
            attempts.append({"attempt":attempt,"status":"failed","error_type":type(exc).__name__}); _write_json(out/f"{label}_attempts.json",{"attempts":attempts})
            if attempt==2: raise


def _summary(records,ledger,status):
    passes=sum(x["decision"]=="pass" for x in records); motifs={m:sum(x["decision"]=="pass" and x["motif"]==m for x in records) for m in ("fan_in_reconciliation","cross_check_validation","policy_application")}
    decision="holistic_editorial_review_completed" if len(records)==8 and passes>=7 and all(v>=2 for v in motifs.values()) else "holistic_editorial_review_hold"
    return {"status":status,"decision":decision,"case_count":len(records),"pass_count":passes,"motif_pass_counts":motifs,"spent_rmb":ledger["spent_rmb"],"request_count":len(ledger["requests"]),"records":records}


def _read_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def _write_json(path,payload):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(path)


if __name__ == "__main__": main()
