import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v2_quality_gate import V2SampleQualityGate


DEFAULT_CASE_DIR = ROOT / "Test" / "v2_outputs" / "finance_batch_01" / "TASK_11C0BEA2"
DEFAULT_RW_TASK_DIR = ROOT / "Test" / "v2_outputs" / "rw_task_batch_finance_01" / "TASK_11C0BEA2"
DEFAULT_OUTPUT = ROOT / "Test" / "v2_outputs" / "quality_gate_reports" / "TASK_11C0BEA2_quality_gate.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the V2 sample quality gate on one generated case.")
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--rw-task-case-dir", type=Path, default=DEFAULT_RW_TASK_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    gate = V2SampleQualityGate()
    report = gate.assess_case(args.case_dir, args.rw_task_case_dir)
    gate.write_report(report, args.output)
    print(json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



