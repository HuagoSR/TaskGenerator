from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_representative_production_pilot import (  # noqa: E402
    RepresentativeProductionPilotCompiler,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile and formally admit the fixed R8.3 12-brief pilot cohort."
    )
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--audit-brief", action="append", type=Path, required=True)
    parser.add_argument("--audit-ledger", type=Path, required=True)
    parser.add_argument("--procurement-candidates", type=Path, required=True)
    parser.add_argument(
        "--procurement-raw-source", action="append", type=Path, required=True
    )
    args = parser.parse_args()

    manifest = RepresentativeProductionPilotCompiler().compile(
        campaign_id=args.campaign_id,
        output_root=args.output_root,
        audit_brief_paths=args.audit_brief,
        audit_ledger_path=args.audit_ledger,
        procurement_candidate_path=args.procurement_candidates,
        procurement_raw_source_paths=args.procurement_raw_source,
    )
    print(
        json.dumps(
            {
                "campaign_id": manifest.campaign_id,
                "brief_count": len(manifest.briefs),
                "assignment_count": len(manifest.assignments),
                "admission_report_sha256": manifest.admission_report_sha256,
                "training_authorized": manifest.training_authorized,
                "registry_mutation_authorized": (
                    manifest.registry_mutation_authorized
                ),
                "manifest_path": str(
                    (args.output_root / "pilot_manifest.json").resolve()
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
