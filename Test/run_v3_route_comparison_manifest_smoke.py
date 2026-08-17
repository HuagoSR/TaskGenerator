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
    RouteComparisonManifestBuilder,
)
from task_generator.v3_task_design_frontend import CapabilityBriefV1  # noqa: E402


FIXTURE = (
    ROOT
    / "Test"
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
    / "capability_brief.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "artifacts"
    / "pipeline_reconstruction"
    / "route_comparison"
    / "offline_manifest_smoke"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze an offline 4-brief x 3-route comparison manifest. "
            "No provider, solver, grader, or promotion action is performed."
        )
    )
    parser.add_argument("--comparison-id", default="r6_offline_manifest_v1")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    briefs = []
    for index, motif in enumerate(
        [
            "cross_document_reconciliation",
            "exception_analysis",
            "validation_workpaper",
            "review_memo",
        ],
        start=1,
    ):
        payload = json.loads(json.dumps(base))
        payload["brief_id"] = f"frozen_brief_{index}"
        payload["case_id"] = f"frozen_case_{index}"
        payload["motif"] = motif
        briefs.append(CapabilityBriefV1.model_validate(payload))

    routes = RouteComparisonManifestBuilder.ROUTES
    package_roots = {
        brief.brief_id: {
            route: str(args.output_dir / "packages" / brief.brief_id / route)
            for route in routes
        }
        for brief in briefs
    }
    manifest = RouteComparisonManifestBuilder().build(
        comparison_id=args.comparison_id,
        briefs=briefs,
        source_snapshot_sha256="offline-fixture-source-snapshot",
        package_roots=package_roots,
        code_fingerprint="working-tree-offline-smoke",
        environment_contract_id="local-plus-fixed-docker-pending",
        solver_preflight_contract_path=(
            "governance/solver_tool_preflight_report.json"
        ),
        grader_calibration_contract_path=(
            "governance/evaluation_calibration_contract.json"
        ),
        timeout_seconds=1800,
        maximum_provider_cost_usd=100.0,
    )
    output_path = args.output_dir / "route_comparison_manifest.json"
    RouteComparisonManifestBuilder.write(manifest, output_path)
    print(
        json.dumps(
            {
                "comparison_id": manifest.comparison_id,
                "brief_count": len(manifest.briefs),
                "route_count": len(manifest.routes),
                "assignment_count": len(manifest.assignments),
                "thresholds_frozen_before_results": (
                    manifest.thresholds.frozen_before_results
                ),
                "comparison_status": manifest.comparison_status,
                "manifest_path": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
