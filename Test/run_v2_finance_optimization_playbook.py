import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v2_finance_optimization import FinanceOptimizationPlanner, render_markdown


DEFAULT_QUALITY_REPORT = ROOT / "Test" / "v2_outputs" / "finance_batch_01" / "quality_report.json"
DEFAULT_FUNNEL_REPORT = ROOT / "Test" / "v2_outputs" / "quality_gate_reports" / "finance_batch_01_funnel_report.json"
DEFAULT_OUTPUT_JSON = ROOT / "Test" / "v2_outputs" / "optimization_reports" / "finance_batch_01_optimization_playbook.json"
DEFAULT_OUTPUT_MD = ROOT / "Test" / "v2_outputs" / "optimization_reports" / "finance_batch_01_optimization_playbook.md"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a finance optimization playbook from quality and funnel reports.")
    parser.add_argument("--quality-report", type=Path, default=DEFAULT_QUALITY_REPORT)
    parser.add_argument("--funnel-report", type=Path, default=DEFAULT_FUNNEL_REPORT)
    parser.add_argument("--batch-id", default="finance_batch_01")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    planner = FinanceOptimizationPlanner()
    plan = planner.build_plan(
        quality_report_path=args.quality_report,
        funnel_report_path=args.funnel_report,
        batch_id=args.batch_id,
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(plan.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(render_markdown(plan), encoding="utf-8")

    print(json.dumps(plan.to_json_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



