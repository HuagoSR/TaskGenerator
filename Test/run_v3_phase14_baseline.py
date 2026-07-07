import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase14_baseline import (  # noqa: E402
    DEFAULT_RELEASE_MANIFEST,
    Phase14BaselineBuilder,
)


DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "phase14"
DEFAULT_SCOPE_DOC = ROOT / "docs" / "architecture" / "phase_14_scope.md"
DEFAULT_HANDOFF_DOC = ROOT / "docs" / "handoffs" / "PHASE_14_BASELINE_2026-07-07.md"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase 14 baseline, GDPVal mirror, and initial subset.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--release-manifest", action="append", default=[str(DEFAULT_RELEASE_MANIFEST)])
    parser.add_argument("--target-subset-count", type=int, default=10)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--mirror-limit", type=int, default=0)
    parser.add_argument("--exclude-rubrics", action="store_true")
    parser.add_argument("--scope-doc-path", type=Path, default=DEFAULT_SCOPE_DOC)
    parser.add_argument("--handoff-path", type=Path, default=DEFAULT_HANDOFF_DOC)
    args = parser.parse_args()

    artifact = Phase14BaselineBuilder().build(
        output_root=args.output_root,
        release_manifest_paths=[Path(path) for path in args.release_manifest],
        target_subset_count=args.target_subset_count,
        allow_network=args.allow_network,
        mirror_limit=args.mirror_limit,
        include_rubrics=not args.exclude_rubrics,
        docs_scope_path=args.scope_doc_path,
        handoff_path=args.handoff_path,
    )
    print(
        json.dumps(
            {
                "baseline_manifest_path": artifact.baseline_manifest_path,
                "scope_doc_path": artifact.scope_doc_path,
                "handoff_path": artifact.handoff_path,
                "mirror_task_count": artifact.mirror_manifest.task_count,
                "subset_selected_count": artifact.subset_manifest.selected_count,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
