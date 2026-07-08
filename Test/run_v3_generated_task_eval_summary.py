import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_generated_task_eval_summary import (  # noqa: E402
    GeneratedTaskEvalSummaryBuilder,
    GeneratedTaskEvalSummaryRequest,
)


DEFAULT_EVAL_REPORT = (
    ROOT
    / "artifacts"
    / "phase14"
    / "generated_task_comparison_eval"
    / "generated_task_comparison_eval_report.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "generated_task_comparison_eval_summary"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize generated TaskGenerator rw-task eval outputs into clean-pair gap records."
    )
    parser.add_argument("--eval-report-path", type=Path, action="append")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strong-model", default="gpt-5.4-pro")
    parser.add_argument("--weak-model", default="gpt-4o-mini")
    args = parser.parse_args()
    eval_report_paths = args.eval_report_path or [DEFAULT_EVAL_REPORT]

    request = GeneratedTaskEvalSummaryRequest(
        eval_report_path=str(eval_report_paths[0]),
        eval_report_paths=[str(path) for path in eval_report_paths],
        output_dir=str(args.output_dir),
        strong_model=args.strong_model,
        weak_model=args.weak_model,
    )
    report = GeneratedTaskEvalSummaryBuilder().build(request)
    print(
        json.dumps(
            {
                "task_count": report.task_count,
                "model_score_count": report.model_score_count,
                "completed_model_score_count": report.completed_model_score_count,
                "clean_pair_count": report.clean_pair_count,
                "blocked_pair_count": report.blocked_pair_count,
                "report_path": str(Path(args.output_dir) / "generated_task_eval_summary_report.json"),
                "gap_profile_path": str(Path(args.output_dir) / "generated_task_gap_profile.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
