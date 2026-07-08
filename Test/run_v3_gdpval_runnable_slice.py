from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_runnable_slice import (  # noqa: E402
    DEFAULT_MODELS,
    GDPValRunnableSliceBuilder,
    RunnableSliceRequest,
)


DEFAULT_CLEAN_BASELINE = ROOT / "artifacts" / "phase14" / "gdpval_clean_baseline" / "gdpval_clean_baseline_report.json"
DEFAULT_ANATOMY_JSONL = ROOT / "artifacts" / "phase14" / "gdpval_anatomy" / "gdpval_task_anatomy.jsonl"
DEFAULT_GAP_AUTOPSY = ROOT / "artifacts" / "phase14" / "gdpval_gap_autopsy" / "gdpval_gap_autopsy_report.json"
DEFAULT_HYPOTHESIS_LEDGER = ROOT / "artifacts" / "phase14" / "gdpval_gap_autopsy" / "gdpval_gap_hypothesis_ledger.json"
DEFAULT_SUBSET_MANIFEST = ROOT / "artifacts" / "phase14" / "gdpval_subset" / "gdpval_finance_audit_subset_manifest.json"
DEFAULT_RELEASE_MANIFEST = (
    ROOT
    / "artifacts"
    / "releases"
    / "finance_audit_mvp_v0_1_pilot8_diversity_final_reviewed_strict"
    / "release_manifest.json"
)
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 14.4B stratified runnable slice plan.")
    parser.add_argument("--clean-baseline-path", default=str(DEFAULT_CLEAN_BASELINE))
    parser.add_argument("--anatomy-jsonl-path", default=str(DEFAULT_ANATOMY_JSONL))
    parser.add_argument("--gap-autopsy-report-path", default=str(DEFAULT_GAP_AUTOPSY))
    parser.add_argument("--hypothesis-ledger-path", default=str(DEFAULT_HYPOTHESIS_LEDGER))
    parser.add_argument("--subset-manifest-path", default=str(DEFAULT_SUBSET_MANIFEST))
    parser.add_argument("--release-manifest-path", default=str(DEFAULT_RELEASE_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--target-gdpval-clean-pairs", type=int, default=8)
    parser.add_argument("--target-taskgenerator-pairs", type=int, default=4)
    parser.add_argument("--model", action="append", default=None)
    args = parser.parse_args()

    request = RunnableSliceRequest(
        clean_baseline_path=args.clean_baseline_path,
        anatomy_jsonl_path=args.anatomy_jsonl_path,
        gap_autopsy_report_path=args.gap_autopsy_report_path,
        hypothesis_ledger_path=args.hypothesis_ledger_path,
        subset_manifest_path=args.subset_manifest_path,
        release_manifest_path=args.release_manifest_path,
        output_dir=args.output_dir,
        target_gdpval_clean_pairs=args.target_gdpval_clean_pairs,
        target_taskgenerator_pairs=args.target_taskgenerator_pairs,
        models=args.model if args.model else list(DEFAULT_MODELS),
    )
    manifest = GDPValRunnableSliceBuilder().build(request)
    output_dir = Path(args.output_dir).resolve()
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "runnable_slice_manifest_path": str(output_dir / "gdpval_runnable_slice_v2_manifest.json"),
                "gdpval_next_eval_queue_path": str(output_dir / "gdpval_next_eval_queue.json"),
                "taskgenerator_comparison_eval_plan_path": str(output_dir / "taskgenerator_comparison_eval_plan.json"),
                "current_gdpval_clean_seed_count": manifest.current_gdpval_clean_seed_count,
                "gdpval_holdout_count": manifest.gdpval_holdout_count,
                "next_gdpval_eval_count": manifest.next_gdpval_eval_count,
                "taskgenerator_comparison_count": manifest.taskgenerator_comparison_count,
                "target_total_clean_pairs": manifest.target_total_clean_pairs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
