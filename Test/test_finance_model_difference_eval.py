import tempfile
import unittest
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"Test"))
from run_v3_finance_model_difference_eval import ALLOWED_SOLVER_KEYS, jaccard, select_pilot  # noqa:E402


class FinanceModelDifferenceEvalTests(unittest.TestCase):
    def test_panel_and_secrets_are_frozen(self):
        text=(ROOT/"SkillRegistry/v3_finance_model_difference_eval.experimental.json").read_text(encoding="utf-8")
        for model in ("gpt-4o-mini","gemini-3.1-pro-preview","deepseek-v4-pro","claude-sonnet-4-6","gpt-5.4-pro","claude-opus-4-6"):
            self.assertIn(model,text)
        compose=(ROOT/"deploy/docker/compose.yaml").read_text(encoding="utf-8")
        self.assertIn("/run/secrets/eval_tuzi_env:ro",compose); self.assertIn("/run/secrets/e2b_api_key:ro",compose)

    def test_pilot_selection_is_deterministic_and_diverse(self):
        index=[]
        for motif in ("fan_in_reconciliation","cross_check_validation","policy_application"):
            index += [{"task_id":f"{motif}-{i}","global_index":i,"motif":motif,"skills":["a","b"] if i==1 else (["a"] if i==2 else ["x",str(i)])} for i in range(1,5)]
        selected=select_pilot(index)
        self.assertEqual(6,len(selected)); self.assertEqual([1,1,1,3,3,3],[item["global_index"] for item in selected])
        self.assertEqual(0.0,jaccard(["a"],["b"]))

    def test_solver_row_allowlist_excludes_teacher_truth(self):
        self.assertNotIn("rubric",ALLOWED_SOLVER_KEYS); self.assertNotIn("golden_run",ALLOWED_SOLVER_KEYS)

if __name__=="__main__": unittest.main()
