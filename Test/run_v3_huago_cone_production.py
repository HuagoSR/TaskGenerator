from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_huago_cone_production import (  # noqa: E402
    FreshProductionBriefCompiler,
    ModelTaskEvaluationV1,
    ProductionSourceRecordV1,
    ProductionTaskCohortCompiler,
    ProductionTaskGenerationRunner,
    aggregate_production_model_comparison,
    atomic_json,
    collect_production_sources,
)
from task_generator.v3_skill_extractor import build_tuzi_config  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Operate the fixed Huago-cone ten-task R9 campaign.")
    parser.add_argument("--action", choices=["collect", "compile-briefs", "compile", "generate", "aggregate"], required=True)
    parser.add_argument("--campaign-id", default="r9_huago_cone_first_production_10")
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--brief-specs", type=Path)
    parser.add_argument("--audit-candidates", type=Path)
    parser.add_argument("--procurement-candidates", type=Path)
    parser.add_argument("--cohort-manifest", type=Path)
    parser.add_argument("--evaluation-records", type=Path)
    parser.add_argument("--env-file", type=Path, default=Path("/run/secrets/provider_env"))
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    if args.action == "collect":
        result = {"sources": [item.model_dump(mode="json") for item in collect_production_sources(args.output_root / "raw_sources")]}
    elif args.action == "compile-briefs":
        _require(args.source_manifest, parser, "--source-manifest")
        _require(args.audit_candidates, parser, "--audit-candidates")
        _require(args.procurement_candidates, parser, "--procurement-candidates")
        sources = [ProductionSourceRecordV1.model_validate(item) for item in _json(args.source_manifest)["sources"]]
        result = {
            "briefs": FreshProductionBriefCompiler().compile(
                campaign_id=args.campaign_id,
                sources=sources,
                accepted_candidate_paths={
                    "audit_compliance": args.audit_candidates,
                    "procurement_operations": args.procurement_candidates,
                },
                output_root=args.output_root / "capability_briefs",
            )
        }
    elif args.action == "compile":
        _require(args.source_manifest, parser, "--source-manifest")
        _require(args.brief_specs, parser, "--brief-specs")
        sources = [
            ProductionSourceRecordV1.model_validate(item)
            for item in _json(args.source_manifest)["sources"]
        ]
        result = ProductionTaskCohortCompiler().compile(
            campaign_id=args.campaign_id,
            sources=sources,
            brief_specs=_json(args.brief_specs)["briefs"],
            output_path=args.output_root / "production_task_cohort.json",
        )
    elif args.action == "generate":
        _require(args.cohort_manifest, parser, "--cohort-manifest")
        config = build_tuzi_config(args.env_file, "gpt-5.6-sol", 900)
        if config is None:
            raise SystemExit("tuzi_configuration_missing")
        result = ProductionTaskGenerationRunner().execute(
            cohort_manifest_path=args.cohort_manifest,
            output_root=args.output_root,
            provider_config=config,
        )
    else:
        _require(args.evaluation_records, parser, "--evaluation-records")
        records = [
            ModelTaskEvaluationV1.model_validate(item)
            for item in _json(args.evaluation_records)["records"]
        ]
        result = aggregate_production_model_comparison(records)
        atomic_json(args.output_root / "production_model_comparison_result.json", result)
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _require(value, parser, flag):
    if value is None:
        parser.error(f"{flag} is required")
    return value


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
