from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_generator.evaluation.r10_gdpval_calibration import build_r10_gdpval_calibration_report


class R10GDPvalCalibrationTests(unittest.TestCase):
    def _task(self, root: Path, name: str) -> Path:
        task = root / name
        (task / "reference_files").mkdir(parents=True)
        (task / "reference_files" / "record.csv").write_text("id,value\n1,10\n", encoding="utf-8")
        (task / "teacher").mkdir()
        (task / "TASK.md").write_text("Prepare a usable work product.", encoding="utf-8")
        (task / "teacher" / "decision_matrix.json").write_text(json.dumps({"decision_points": [{"decision_id": "d1"}]}), encoding="utf-8")
        (task / "teacher" / "task_specific_rubric.json").write_text(json.dumps({"criteria": [{"criterion_id": "c1"}]}), encoding="utf-8")
        (task / "deliverable_contract.json").write_text(json.dumps({"deliverables": [{"format": "xlsx"}]}), encoding="utf-8")
        return task

    def test_report_uses_aggregate_gdpval_data_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tasks = [self._task(root, f"task_{index}") for index in range(4)]
            distribution = root / "distribution.json"
            discrimination = root / "diagnosis.json"
            distribution.write_text(json.dumps({"task_count": 10, "reference_file_extension_counts": {".xlsx": 7}, "reasoning_requirement_counts": {"reconciliation": 3}, "evidence_density_counts": {"high": 6}, "ambiguity_level_counts": {"medium": 7}}), encoding="utf-8")
            discrimination.write_text(json.dumps({"task_diagnoses": [{"task_id": "task_0", "classification": "saturated", "compiler_signals": ["score_saturation"]}]}), encoding="utf-8")
            report = build_r10_gdpval_calibration_report(task_roots=tasks, gdpval_distribution_path=distribution, discrimination_path=discrimination)
        self.assertTrue(report["generation_safe"])
        self.assertEqual(report["gdpval_aggregate"]["task_count"], 10)
        self.assertEqual(report["r10_frozen_task_shapes"][0]["pilot_classification"], "saturated")
        self.assertIn("GDPval task prompts", report["prohibited_generation_inputs"])

    def test_requires_the_complete_frozen_pilot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            distribution = root / "distribution.json"
            discrimination = root / "diagnosis.json"
            distribution.write_text("{}", encoding="utf-8")
            discrimination.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_r10_gdpval_calibration_report(task_roots=[], gdpval_distribution_path=distribution, discrimination_path=discrimination)


if __name__ == "__main__":
    unittest.main()
