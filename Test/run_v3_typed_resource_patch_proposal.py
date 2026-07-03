import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_typed_resource_patch_proposal import (  # noqa: E402
    TypedResourcePatchProposalBuilder,
)


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_SUBSTRATE_AUDIT_REPORT = (
    SCRATCH / "pipeline_a_substrate_audit_smoke" / "pipeline_a_substrate_audit_report.json"
)
DEFAULT_OUTPUT_DIR = SCRATCH / "typed_resource_patch_proposal_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build reviewed typed-resource patch proposals from a Pipeline A substrate audit."
    )
    parser.add_argument(
        "--substrate-audit-report",
        type=Path,
        default=DEFAULT_SUBSTRATE_AUDIT_REPORT,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--drop-low-confidence",
        action="store_true",
        help="Omit low-confidence proposals from the output. Default keeps them visible for review.",
    )
    args = parser.parse_args()

    builder = TypedResourcePatchProposalBuilder()
    report = builder.build(
        substrate_audit_report_path=args.substrate_audit_report,
        output_dir=args.output_dir,
        include_low_confidence=not args.drop_low_confidence,
    )
    print(
        json.dumps(
            {
                "typed_resource_patch_proposals_path": str(
                    args.output_dir / "typed_resource_patch_proposals.json"
                ),
                "typed_resource_patch_proposal_report_path": str(
                    args.output_dir / "typed_resource_patch_proposal_report.json"
                ),
                "proposal_skill_count": report.diagnostics.proposal_skill_count,
                "proposed_resource_count": report.diagnostics.proposed_resource_count,
                "proposed_required_resource_count": report.diagnostics.proposed_required_resource_count,
                "proposed_optional_resource_count": report.diagnostics.proposed_optional_resource_count,
                "proposed_provided_resource_count": report.diagnostics.proposed_provided_resource_count,
                "low_confidence_resource_count": report.diagnostics.low_confidence_resource_count,
                "unknown_resource_type_count": report.diagnostics.unknown_resource_type_count,
                "needs_source_evidence_skill_count": report.diagnostics.needs_source_evidence_skill_count,
                "status_counts": report.diagnostics.status_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
