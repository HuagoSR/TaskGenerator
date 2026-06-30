import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v2_quality_gate import V2SampleQualityGate


DEFAULT_BATCH_DIR = ROOT / "Test" / "v2_outputs" / "finance_batch_01"
DEFAULT_RW_TASK_BATCH_DIR = ROOT / "Test" / "v2_outputs" / "rw_task_batch_finance_01"
DEFAULT_QUALITY_REPORT = DEFAULT_BATCH_DIR / "quality_report.json"
DEFAULT_GATE_REPORT = ROOT / "Test" / "v2_outputs" / "quality_gate_reports" / "finance_batch_01_gate_report.json"
DEFAULT_FUNNEL_REPORT = ROOT / "Test" / "v2_outputs" / "quality_gate_reports" / "finance_batch_01_funnel_report.json"
DEFAULT_FUNNEL_SUMMARY = ROOT / "Test" / "v2_outputs" / "quality_gate_reports" / "finance_batch_01_funnel_summary.md"


def _load_quality_scores(path: Path) -> dict[str, dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["task_id"]): row for row in rows}


def _recommend_next_step(gate_passed: bool, total_score: float | None) -> str:
    if not gate_passed:
        return "fix_pipeline_blockers"
    if total_score is None:
        return "run_static_quality_scoring"
    if total_score >= 82.0:
        return "prioritize_for_rw_task_eval"
    if total_score >= 72.0:
        return "keep_in_training_pool"
    return "revise_before_eval"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run batch-level V2 quality gate and merge it with static quality scoring.")
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--rw-task-batch-dir", type=Path, default=DEFAULT_RW_TASK_BATCH_DIR)
    parser.add_argument("--quality-report", type=Path, default=DEFAULT_QUALITY_REPORT)
    parser.add_argument("--gate-report-out", type=Path, default=DEFAULT_GATE_REPORT)
    parser.add_argument("--funnel-report-out", type=Path, default=DEFAULT_FUNNEL_REPORT)
    parser.add_argument("--funnel-summary-out", type=Path, default=DEFAULT_FUNNEL_SUMMARY)
    args = parser.parse_args()

    gate = V2SampleQualityGate()
    gate_reports = gate.assess_batch(args.batch_dir, args.rw_task_batch_dir)
    gate.write_batch_report(gate_reports, args.gate_report_out)

    quality_by_task = _load_quality_scores(args.quality_report) if args.quality_report.exists() else {}

    funnel_rows = []
    for report in gate_reports:
        quality_row = quality_by_task.get(report.task_id)
        total_score = float(quality_row["total_score"]) if quality_row else None
        recommendation = _recommend_next_step(report.passed, total_score)
        funnel_rows.append(
            {
                "task_id": report.task_id,
                "gate_passed": report.passed,
                "blocking_issue_count": report.blocking_issue_count,
                "warning_count": report.warning_count,
                "static_total_score": total_score,
                "static_recommendation": quality_row.get("recommendation") if quality_row else None,
                "next_step": recommendation,
            }
        )

    funnel_rows.sort(
        key=lambda row: (
            not row["gate_passed"],
            -(row["static_total_score"] if row["static_total_score"] is not None else -1.0),
            row["task_id"],
        )
    )

    args.funnel_report_out.parent.mkdir(parents=True, exist_ok=True)
    args.funnel_report_out.write_text(json.dumps(funnel_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Finance Batch Funnel Summary",
        "",
        f"- batch_dir: `{args.batch_dir}`",
        f"- rw_task_batch_dir: `{args.rw_task_batch_dir}`",
        "",
    ]
    for idx, row in enumerate(funnel_rows, start=1):
        lines.append(f"## {idx}. {row['task_id']}")
        lines.append(f"- gate_passed: {row['gate_passed']}")
        lines.append(f"- blocking_issue_count: {row['blocking_issue_count']}")
        lines.append(f"- warning_count: {row['warning_count']}")
        lines.append(f"- static_total_score: {row['static_total_score']}")
        lines.append(f"- static_recommendation: {row['static_recommendation']}")
        lines.append(f"- next_step: {row['next_step']}")
        lines.append("")

    args.funnel_summary_out.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(funnel_rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



