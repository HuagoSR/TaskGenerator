from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_route_comparison import (  # noqa: E402
    RouteBlindPackageStager,
    RouteComparisonManifestV1,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Stage already-materialized route exports under route-blind task IDs. "
            "This does not call providers, solvers, graders, or promotion."
        )
    )
    parser.add_argument("--comparison-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = RouteComparisonManifestV1.model_validate_json(
        args.comparison_manifest.read_text(encoding="utf-8")
    )
    report = RouteBlindPackageStager().stage(
        manifest,
        args.output_dir,
    )
    print(
        json.dumps(
            {
                "comparison_id": report.comparison_id,
                "decision": report.decision,
                "package_count": report.package_count,
                "candidate_packages_dir": str(
                    args.output_dir / "candidate_packages"
                ),
                "governance_report": str(
                    args.output_dir
                    / "governance"
                    / "route_blind_staging_report.json"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if report.decision != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
