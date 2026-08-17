import tempfile
import unittest
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"Test"))
from run_v3_finance_model_difference_eval import (  # noqa:E402
    ALLOWED_SOLVER_KEYS,
    _audit_disagrees,
    _delivered_files,
    atomic_json,
    build_f4_2_index,
    fixed_audit_assignments,
    jaccard,
    select_extended,
    select_pilot,
    reserve_tuzi_call,
    tuzi_credentials,
)


class FinanceModelDifferenceEvalTests(unittest.TestCase):
    def test_panel_and_secrets_are_frozen(self):
        text=(ROOT/"SkillRegistry/v3_finance_model_difference_eval.experimental.json").read_text(encoding="utf-8")
        for model in ("gpt-4o-mini","gemini-3.1-pro-preview","deepseek-v4-pro","claude-sonnet-4-6","gpt-5.4-pro","claude-opus-4-6"):
            self.assertIn(model,text)
        compose=(ROOT/"deploy/docker/compose.yaml").read_text(encoding="utf-8")
        self.assertIn("/run/secrets/eval_tuzi_env:ro",compose); self.assertIn("/run/secrets/e2b_api_key:ro",compose)

    def test_f4_2_panel_and_low_cost_graders_are_frozen(self):
        payload=json.loads((ROOT/"SkillRegistry/v3_finance_f4_2_model_eval.experimental.json").read_text(encoding="utf-8"))
        self.assertEqual("f4_2_eight_task",payload["scope"])
        self.assertEqual(["gpt-5.6-sol","claude-sonnet-4-6","deepseek-v4-pro","deepseek-v4-flash"],
                         [item["model"] for item in payload["solver_models"]])
        self.assertEqual("gpt-5.6-luna",payload["primary_grader"])
        self.assertEqual("claude-opus-4-7",payload["audit_grader"])
        self.assertEqual(50.0,payload["tuzi_budget_rmb"])

    def test_f4_2_fixed_audit_rotates_every_model_twice(self):
        models=["sol","sonnet","pro","flash"]
        selection={"scope":"f4_2_eight_task","tasks":[
            {"task_id":f"task-{slot}","slot":slot,"global_index":slot,"motif":"m"} for slot in range(1,9)
        ]}
        assignments=fixed_audit_assignments(selection,models)
        self.assertEqual({model:2 for model in models},{model:list(assignments.values()).count(model) for model in models})

    def test_tuzi_budget_is_atomic_and_blocks_overrun(self):
        spec={"tuzi_budget_rmb":1.0,"tuzi_request_cap":2,"reservation_rmb":{"grader:test":.6}}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            reserve_tuzi_call(root,spec,"grader","test")
            with self.assertRaisesRegex(RuntimeError,"tuzi_budget_exhausted"):
                reserve_tuzi_call(root,spec,"grader","test")

    def test_f4_2_backup_key_does_not_fall_back_to_primary(self):
        values={"OPENAI_API_KEY":"teacher","OPENAI_API_KEY_BACKUP":"personal","OPENAI_BASE_URL":"https://example.invalid/v1"}
        self.assertEqual(("personal","https://example.invalid/v1"),tuzi_credentials(values,backup_only=True))
        self.assertEqual(("teacher","https://example.invalid/v1"),tuzi_credentials(values,backup_only=False))
        self.assertEqual((None,"https://example.invalid/v1"),tuzi_credentials({"OPENAI_API_KEY":"teacher","OPENAI_BASE_URL":"https://example.invalid/v1"},backup_only=True))

    def test_pilot_selection_is_deterministic_and_diverse(self):
        index=[]
        for motif in ("fan_in_reconciliation","cross_check_validation","policy_application"):
            index += [{"task_id":f"{motif}-{i}","global_index":i,"motif":motif,"skills":["a","b"] if i==1 else (["a"] if i==2 else ["x",str(i)])} for i in range(1,5)]
        selected=select_pilot(index)
        self.assertEqual(6,len(selected)); self.assertEqual([1,1,1,3,3,3],[item["global_index"] for item in selected])
        self.assertEqual(0.0,jaccard(["a"],["b"]))

    def test_solver_row_allowlist_excludes_teacher_truth(self):
        self.assertNotIn("rubric",ALLOWED_SOLVER_KEYS); self.assertNotIn("golden_run",ALLOWED_SOLVER_KEYS)

    def test_extended_selection_is_balanced_and_deterministic(self):
        index=[]
        global_index=1
        for motif in ("fan_in_reconciliation","cross_check_validation","policy_application"):
            for occurrence in range(12):
                index.append({"task_id":f"{motif}-{occurrence}","global_index":global_index,"motif":motif,
                              "skills":[motif,str(occurrence)],"prompt_sha256":f"p-{motif}-{occurrence}",
                              "subgraph_sha256":f"s-{motif}-{occurrence}","reference_bundle_sha256":f"r-{motif}-{occurrence}"})
                global_index += 1
        first=select_extended(index,10); second=select_extended(index,10)
        self.assertEqual([item["task_id"] for item in first],[item["task_id"] for item in second])
        self.assertEqual(30,len(first))
        self.assertEqual({motif:10 for motif in ("fan_in_reconciliation","cross_check_validation","policy_application")},
                         {motif:sum(item["motif"]==motif for item in first) for motif in {item["motif"] for item in first}})

    def test_reused_subgraph_template_is_not_a_whole_task_duplicate(self):
        index=[]
        for occurrence in range(10):
            index.append({"task_id":f"task-{occurrence}","global_index":occurrence,"motif":"fan_in_reconciliation",
                          "skills":[str(occurrence)],"task_sha256":f"task-{occurrence}","prompt_sha256":f"prompt-{occurrence}",
                          "subgraph_sha256":"shared-template","reference_bundle_sha256":f"reference-{occurrence}"})
        from run_v3_finance_model_difference_eval import _is_exact_duplicate
        self.assertFalse(_is_exact_duplicate(index[1],[index[0]]))

    def test_fixed_audit_is_two_per_model_per_motif(self):
        models=["weak","medium","strong","best"]
        tasks=[]
        for motif in ("fan_in_reconciliation","cross_check_validation","policy_application"):
            tasks += [{"task_id":f"{motif}-{index}","motif":motif,"global_index":index,"is_pilot":False} for index in range(8)]
            tasks += [{"task_id":f"{motif}-pilot-{index}","motif":motif,"global_index":100+index,"is_pilot":True} for index in range(2)]
        assignments=fixed_audit_assignments({"tasks":tasks},models)
        self.assertEqual(24,len(assignments))
        for motif in ("fan_in_reconciliation","cross_check_validation","policy_application"):
            assigned=[model for task_id,model in assignments.items() if task_id.startswith(motif+"-")]
            self.assertEqual({model:2 for model in models},{model:assigned.count(model) for model in models})

    def test_audit_expansion_thresholds(self):
        spec={"audit_absolute_difference_threshold":.20,"audit_pass_threshold":.60}
        self.assertTrue(_audit_disagrees({"primary_grade":{"score":.70},"audit_grade":{"score":.49}},spec))
        self.assertTrue(_audit_disagrees({"primary_grade":{"score":.61},"audit_grade":{"score":.59}},spec))
        self.assertFalse(_audit_disagrees({"primary_grade":{"score":.55},"audit_grade":{"score":.50}},spec))

    def test_summary_contract_distinguishes_non_delivery(self):
        source=(ROOT/"Test/run_v3_finance_model_difference_eval.py").read_text(encoding="utf-8")
        for field in ("solver_attempted","solver_process_completed","valid_deliveries","non_delivery"):
            self.assertIn(f'"{field}"',source)

    def test_delivery_requires_a_file_in_deliverable_directory(self):
        record={"model":"model","task_id":"task"}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            case=root/"single_inputs/task/task"
            case.mkdir(parents=True)
            atomic_json(case/"dataset_row.json",{
                "task_id":"task",
                "reference_files":[],
                "deliverable_files":["deliverable_files/output.xlsx"],
                "extra":{},
            })
            run=root/"solver_outputs/model/task/run_task"
            (run/"reference_files").mkdir(parents=True)
            (run/"reference_files/input.xlsx").write_bytes(b"input")
            self.assertEqual([],_delivered_files(root,record))
            (run/"deliverable_files").mkdir()
            from openpyxl import Workbook
            workbook=Workbook(); workbook.active.append(["value"]); workbook.save(run/"deliverable_files/output.xlsx")
            self.assertEqual([run/"deliverable_files/output.xlsx"],_delivered_files(root,record))

    def test_delivery_rejects_wrong_name_even_when_a_file_exists(self):
        record={"model":"model","task_id":"task"}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            case=root/"single_inputs/task/task"
            case.mkdir(parents=True)
            atomic_json(case/"dataset_row.json",{
                "task_id":"task",
                "reference_files":[],
                "deliverable_files":["deliverable_files/output.xlsx"],
                "extra":{},
            })
            run=root/"solver_outputs/model/task/run_task/deliverable_files"
            run.mkdir(parents=True)
            from openpyxl import Workbook
            workbook=Workbook(); workbook.active.append(["value"]); workbook.save(run/"wrong.xlsx")
            self.assertEqual([],_delivered_files(root,record))

if __name__=="__main__": unittest.main()
