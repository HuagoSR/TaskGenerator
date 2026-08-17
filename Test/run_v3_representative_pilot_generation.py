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
    RepresentativePilotGenerationRunner,
)
from task_generator.v3_skill_extractor import build_tuzi_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute the fixed R8.3 24-assignment provider generation stage."
    )
    parser.add_argument("--pilot-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()

    config = build_tuzi_config(args.env_file, "gpt-5.6-sol", 900)
    if config is None:
        raise SystemExit("tuzi_configuration_missing")
    result = RepresentativePilotGenerationRunner().execute(
        pilot_manifest_path=args.pilot_manifest,
        output_root=args.output_root,
        provider_config=config,
    )
    print(
        json.dumps(
            {
                "campaign_id": result.campaign_id,
                "decision": result.decision,
                "provider_call_count": result.provider_call_count,
                "materialized_count": sum(
                    item.status == "materialized" for item in result.cases
                ),
                "blocked_count": sum(
                    item.status == "blocked" for item in result.cases
                ),
                "infrastructure_failed_count": sum(
                    item.status == "infrastructure_failed"
                    for item in result.cases
                ),
                "training_authorized": result.training_authorized,
                "registry_mutation_authorized": (
                    result.registry_mutation_authorized
                ),
                "result_path": str(
                    (args.output_root / "generation_result.json").resolve()
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
