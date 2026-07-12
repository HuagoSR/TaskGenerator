from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SELECTED = {"02":"revision_01","06":"revision_01","13":"revision_02","18":"revision_01","31":"revision_02","35":"revision_01","38":"revision_01","47":"revision_02"}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--campaign-root",type=Path,required=True); parser.add_argument("--review-root",type=Path,required=True); args=parser.parse_args()
    records=[]; visual=[]
    for case,revision in SELECTED.items():
        root=args.campaign_root/"cases"/case/revision
        record=json.loads((root/"case_result.json").read_text(encoding="utf-8")); records.append(record)
        visual.extend(str(p) for p in (root/"visual").rglob("*.png") if "policy_test" not in str(p))
    frozen=json.loads((args.campaign_root/"original_evidence_sha256_manifest.json").read_text(encoding="utf-8")); mismatches=[]
    for item in frozen:
        path=args.review_root/item["path"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]: mismatches.append(item["path"])
    ledger=json.loads((args.campaign_root/"holistic_cost_ledger.json").read_text(encoding="utf-8"))
    pass_count=sum(x["decision"]=="pass" for x in records); motifs={m:sum(x["decision"]=="pass" and x["motif"]==m for x in records) for m in ("fan_in_reconciliation","cross_check_validation","policy_application")}
    decision="holistic_editorial_review_completed" if pass_count>=7 and all(v>=2 for v in motifs.values()) and not mismatches else "holistic_editorial_review_hold"
    summary={"report_version":"v3.holistic_editorial_closure.1","decision":decision,"selected_revisions":SELECTED,"case_count":8,"pass_count":pass_count,"motif_pass_counts":motifs,"contract_verified_count":sum(x["contract_verified"] for x in records),"deterministic_recomputation_pass_count":sum(x["deterministic_recomputation_pass"] for x in records),"fact_centered_rubric_count":sum(x["fact_weight_ratio"]>=.6 for x in records),"candidate_teacher_isolation_pass_count":sum(x["candidate_teacher_isolation_pass"] for x in records),"luna_answerable_count":sum(x["luna_answerable"] for x in records),"luna_result_match_count":sum(x["luna_result_match"] for x in records),"unresolved_material_ambiguity_count":sum(x["unresolved_material_ambiguity"] for x in records),"original_hash_mismatch_count":len(mismatches),"visual_artifact_count":len(visual),"tuzi_request_count":len(ledger["requests"]),"spent_rmb":ledger["spent_rmb"],"remaining_rmb":ledger["remaining_rmb"],"records":records,"visual_artifacts":visual,"scope_boundaries":{"four_model_rerun":False,"rl_or_sft":False,"financial_expert_certification":False}}
    write(args.campaign_root/"final_closure_summary.json",summary)
    case18=next(x for x in records if x["case_number"]==18)
    write(args.campaign_root/"case_18_lifecycle_index.json",{"case_number":18,"before":"finance_30_human_review_01/candidate_view/18","diagnosis":"missing attendee count for per-person policy","terra_revision":str(args.campaign_root/"cases/18/revision_01/whole_task_revision_bundle.json"),"candidate_revision":str(args.campaign_root/"cases/18/revision_01/candidate_view"),"deterministic_truth":case18["comparison"]["expected"],"luna_independent_result":case18["comparison"]["actual"],"decision":case18["decision"]})
    print(json.dumps({k:summary[k] for k in ("decision","pass_count","motif_pass_counts","spent_rmb","tuzi_request_count","original_hash_mismatch_count","visual_artifact_count")},ensure_ascii=False))


def write(path,payload):
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(path)


if __name__=="__main__": main()
