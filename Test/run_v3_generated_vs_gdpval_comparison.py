from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_generated_vs_gdpval_comparison import (  # noqa: E402
    GeneratedVsGDPValComparisonBuilder,
    GeneratedVsGDPValComparisonRequest,
)


DEFAULT_PROFILES = (
    ROOT
    / "artifacts"
    / "phase14"
    / "good_task_profiler_observational"
    / "good_task_observational_profiles.jsonl"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "generated_vs_gdpval"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build report-only generated-vs-GDPVal observational comparison reports.")
    parser.add_argument("--observational-profiles-path", default=str(DEFAULT_PROFILES))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    request = GeneratedVsGDPValComparisonRequest(
        observational_profiles_path=args.observational_profiles_path,
        output_dir=args.output_dir,
    )
    report = GeneratedVsGDPValComparisonBuilder().build(request)
    output_dir = Path(args.output_dir).resolve()
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "similarity_report_path": str(output_dir / "generated_vs_gdpval_similarity_report.json"),
                "gap_report_path": str(output_dir / "generated_vs_gdpval_gap_report.json"),
                "quality_matrix_path": str(output_dir / "generated_vs_gdpval_quality_matrix.json"),
                "recommendations_path": str(output_dir / "generated_task_improvement_recommendations.json"),
                "comparison_readiness": report.comparison_readiness,
                "gdpval_clean_eval_count": report.gdpval_clean_eval_count,
                "generated_clean_eval_count": report.generated_clean_eval_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
