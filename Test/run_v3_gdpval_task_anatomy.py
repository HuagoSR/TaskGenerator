from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_task_anatomy import (  # noqa: E402
    GDPValTaskAnatomyExtractor,
    GDPValTaskAnatomyRequest,
)


DEFAULT_SUBSET_MANIFEST = ROOT / "artifacts" / "phase14" / "gdpval_subset" / "gdpval_finance_audit_subset_manifest.json"
DEFAULT_CLEAN_BASELINE = ROOT / "artifacts" / "phase14" / "gdpval_clean_baseline" / "gdpval_clean_baseline_report.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "gdpval_anatomy"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract deterministic GDPVal task anatomy profiles.")
    parser.add_argument("--subset-manifest-path", default=str(DEFAULT_SUBSET_MANIFEST))
    parser.add_argument("--mirror-manifest-path", default=None)
    parser.add_argument("--clean-baseline-path", default=str(DEFAULT_CLEAN_BASELINE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--task-limit", type=int, default=0)
    parser.add_argument("--task-id", action="append", default=None)
    args = parser.parse_args()

    request = GDPValTaskAnatomyRequest(
        subset_manifest_path=args.subset_manifest_path,
        mirror_manifest_path=args.mirror_manifest_path,
        clean_baseline_path=args.clean_baseline_path,
        output_dir=args.output_dir,
        task_limit=args.task_limit,
        task_ids=args.task_id or [],
    )
    report = GDPValTaskAnatomyExtractor().build(request)
    output_dir = Path(args.output_dir).resolve()
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "summary_report_path": str(output_dir / "gdpval_anatomy_summary_report.json"),
                "profile_jsonl_path": report.profile_jsonl_path,
                "distribution_report_path": report.distribution_report_path,
                "good_task_profiler_input_path": report.good_task_profiler_input_path,
                "task_count": report.task_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
