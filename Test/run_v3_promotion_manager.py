import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_promotion_manager import PromotionManager  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_TYPED_RESOURCE_PATCH_PROPOSALS = (
    SCRATCH / "typed_resource_patch_proposal_smoke" / "typed_resource_patch_proposals.json"
)
DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_OUTPUT_DIR = SCRATCH / "promotion_manager_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build, apply, or rollback typed-resource-first promotion records."
    )
    parser.add_argument(
        "--typed-resource-patch-proposals",
        type=Path,
        default=DEFAULT_TYPED_RESOURCE_PATCH_PROPOSALS,
    )
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--apply-promotion-id", type=str, default=None)
    parser.add_argument("--reviewer", type=str, default=None)
    parser.add_argument("--approval-note", type=str, default=None)
    parser.add_argument("--rollback-record", type=Path, default=None)
    args = parser.parse_args()

    manager = PromotionManager()
    if args.rollback_record is not None:
        artifact = manager.rollback_promotion(
            rollback_record_path=args.rollback_record,
            output_dir=args.output_dir,
        )
    elif args.apply_promotion_id:
        if not args.reviewer or not args.approval_note:
            raise SystemExit("--reviewer and --approval-note are required when --apply-promotion-id is set.")
        artifact = manager.apply_promotion(
            typed_resource_patch_proposals_path=args.typed_resource_patch_proposals,
            registry_path=args.registry_path,
            output_dir=args.output_dir,
            apply_promotion_id=args.apply_promotion_id,
            reviewer=args.reviewer,
            approval_note=args.approval_note,
        )
    else:
        artifact = manager.build_proposals(
            typed_resource_patch_proposals_path=args.typed_resource_patch_proposals,
            registry_path=args.registry_path,
            output_dir=args.output_dir,
        )

    print(
        json.dumps(
            {
                "promotion_proposals_path": str(args.output_dir / "promotion_proposals.json"),
                "promotion_report_path": str(args.output_dir / "promotion_report.json"),
                "rollback_record_path": str(args.output_dir / "rollback_record.json")
                if (args.output_dir / "rollback_record.json").exists()
                else None,
                "promotion_count": artifact.diagnostics.promotion_count,
                "eligible_promotion_count": artifact.diagnostics.eligible_promotion_count,
                "eligible_unreviewed_promotion_count": artifact.diagnostics.eligible_unreviewed_promotion_count,
                "blocked_promotion_count": artifact.diagnostics.blocked_promotion_count,
                "applied_promotion_count": artifact.diagnostics.applied_promotion_count,
                "rolled_back_promotion_count": artifact.diagnostics.rolled_back_promotion_count,
                "no_effective_diff_promotion_count": artifact.diagnostics.no_effective_diff_promotion_count,
                "diff_item_count": artifact.diagnostics.diff_item_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
