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
    RepresentativePilotPackageReadinessCompiler,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bind zero-provider deterministic replays into R8.3 package readiness."
    )
    parser.add_argument("--pilot-manifest", type=Path, required=True)
    parser.add_argument("--generation-result", type=Path, required=True)
    parser.add_argument(
        "--replay",
        action="append",
        required=True,
        help="blind_task_id=absolute_or_relative_package_root",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay_roots = {}
    for value in args.replay:
        blind_task_id, separator, root = value.partition("=")
        if not separator or not blind_task_id or not root:
            raise SystemExit("replay_requires_blind_task_id_equals_path")
        replay_roots[blind_task_id] = root
    result = RepresentativePilotPackageReadinessCompiler().compile(
        pilot_manifest_path=args.pilot_manifest,
        generation_result_path=args.generation_result,
        replay_roots_by_task=replay_roots,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "campaign_id": result.campaign_id,
                "decision": result.decision,
                "package_count": len(result.packages),
                "replay_package_count": sum(
                    item.package_source == "deterministic_false_positive_replay"
                    for item in result.packages
                ),
                "external_provider_calls_made": (
                    result.external_provider_calls_made
                ),
                "training_authorized": result.training_authorized,
                "output_path": str(args.output.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
