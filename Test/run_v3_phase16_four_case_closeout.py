import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_four_case_closeout import (  # noqa: E402
    Phase16FourCaseCloseoutRequest,
    build_phase16_four_case_closeout,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the final Phase 16 four-case closeout reports.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts" / "phase16")
    parser.add_argument("--results", type=Path, default=ROOT / "artifacts" / "phase16" / "e4" / "phase16_four_case_external_eval_results.sanitized.json")
    parser.add_argument("--gate-report", type=Path, default=ROOT / "artifacts" / "phase16" / "clean_eval_gate" / "phase16_four_case_clean_eval_import_report.json")
    parser.add_argument("--production-report", type=Path, default=ROOT / "artifacts" / "phase16" / "e4" / "phase16_production_experiment_report.json")
    parser.add_argument("--retry-records", type=Path, default=ROOT / "artifacts" / "phase16" / "e4" / "retry_records")
    args = parser.parse_args()
    report = build_phase16_four_case_closeout(Phase16FourCaseCloseoutRequest(
        sanitized_results_path=str(args.results),
        gate_report_path=str(args.gate_report),
        production_experiment_report_path=str(args.production_report),
        output_root=str(args.output_root),
        retry_records_dir=str(args.retry_records),
    ))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
