import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_production_dashboard import ProductionDashboardBuilder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the Phase 13 production dashboard and release-readiness reports."
    )
    parser.add_argument("--manifest-path", type=Path, required=True)
    parser.add_argument("--diversity-report-path", type=Path, required=True)
    parser.add_argument("--qa-gate-report-path", type=Path, required=True)
    parser.add_argument("--release-manifest-path", type=Path, default=None)
    parser.add_argument("--comparison-batch-manifest", type=Path, action="append", default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or (args.manifest_path.parent / "production_dashboard")
    result = ProductionDashboardBuilder().build(
        production_batch_manifest_path=args.manifest_path,
        production_batch_diversity_report_path=args.diversity_report_path,
        production_qa_gate_report_path=args.qa_gate_report_path,
        release_manifest_path=args.release_manifest_path,
        comparison_batch_manifest_paths=args.comparison_batch_manifest or [],
        output_dir=output_dir,
    )
    dashboard = result["production_dashboard_report"]
    readiness = result["release_readiness_report"]
    print(
        json.dumps(
            {
                "production_dashboard_report_path": str(output_dir / "production_dashboard_report.json"),
                "release_readiness_report_path": str(output_dir / "release_readiness_report.json"),
                "case_count": dashboard.summary.case_count,
                "production_ready_count": dashboard.summary.production_ready_count,
                "release_readiness_status": readiness.readiness_status,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
