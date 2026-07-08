import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_generated_task_gap_autopsy import (  # noqa: E402
    GeneratedTaskGapAutopsyBuilder,
    GeneratedTaskGapAutopsyRequest,
)


PHASE14 = ROOT / "artifacts" / "phase14"
PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_EVAL_SUMMARY = PHASE14 / "generated_task_comparison_eval_summary" / "generated_task_eval_summary_report.json"
DEFAULT_GAP_REPORT = PHASE14 / "generated_vs_gdpval" / "generated_vs_gdpval_gap_report.json"
DEFAULT_QUALITY_MATRIX = PHASE14 / "generated_vs_gdpval" / "generated_vs_gdpval_quality_matrix.json"
DEFAULT_OUTPUT = PHASE15 / "gap_autopsy"


def main() -> None:
    parser = argparse.ArgumentParser(description="Autopsy generated-task clean-pair gaps for Phase 15 reform planning.")
    parser.add_argument("--generated-task-eval-summary-path", type=Path, default=DEFAULT_EVAL_SUMMARY)
    parser.add_argument("--generated-vs-gdpval-gap-path", type=Path, default=DEFAULT_GAP_REPORT)
    parser.add_argument("--generated-vs-gdpval-quality-matrix-path", type=Path, default=DEFAULT_QUALITY_MATRIX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    request = GeneratedTaskGapAutopsyRequest(
        generated_task_eval_summary_path=str(args.generated_task_eval_summary_path),
        generated_vs_gdpval_gap_path=str(args.generated_vs_gdpval_gap_path),
        generated_vs_gdpval_quality_matrix_path=str(args.generated_vs_gdpval_quality_matrix_path),
        output_dir=str(args.output_dir),
    )
    report = GeneratedTaskGapAutopsyBuilder().build(request)
    print(
        json.dumps(
            {
                "case_count": report.case_count,
                "gap_band_counts": report.gap_band_counts,
                "low_gap_motifs": report.low_gap_motifs,
                "high_gap_motifs": report.high_gap_motifs,
                "recommended_first_reform_target": report.recommended_first_reform_target,
                "report_path": str(Path(args.output_dir) / "generated_task_gap_autopsy_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
