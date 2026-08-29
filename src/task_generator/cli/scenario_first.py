"""Offline entry points for R10 Scenario-First slices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from task_generator.core.scenario_first import ProfessionalRuleSetV1
from task_generator.planning.work_seed_admission import (
    PublicWorkSourceCatalogV1,
    WorkSeedAdmissionValidator,
    WorkSeedCandidateV1,
)
from task_generator.planning.scenario_bible_compiler import OfficialDeepSeekScenarioBibleCompiler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline R10 Scenario-First admission checks.")
    parser.add_argument("--action", choices=["admit-seeds", "compile-bibles"], required=True)
    parser.add_argument("--source-catalog", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--rule-sets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--admission-report", type=Path)
    parser.add_argument("--provider-key-file", type=Path)
    args = parser.parse_args()

    catalog = PublicWorkSourceCatalogV1.model_validate_json(
        args.source_catalog.read_text(encoding="utf-8")
    )
    candidates = [
        WorkSeedCandidateV1.model_validate(item)
        for item in json.loads(args.candidates.read_text(encoding="utf-8"))
    ]
    rules = [
        ProfessionalRuleSetV1.model_validate(item)
        for item in json.loads(args.rule_sets.read_text(encoding="utf-8"))
    ]
    if args.action == "admit-seeds":
        report = WorkSeedAdmissionValidator().evaluate(
            catalog=catalog, candidates=candidates, rule_sets=rules,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    else:
        if args.admission_report is None or args.provider_key_file is None:
            parser.error("--admission-report and --provider-key-file are required for compile-bibles")
        admission = json.loads(args.admission_report.read_text(encoding="utf-8"))
        if admission.get("decision") != "pass":
            parser.error("scenario_bible_requires_passing_seed_admission")
        admitted_ids = set(admission.get("admitted_seed_ids", []))
        seeds = [item.seed for item in candidates if item.seed.seed_id in admitted_ids]
        if len(seeds) != 4:
            parser.error("scenario_bible_requires_exactly_four_admitted_seeds")
        key = args.provider_key_file.read_text(encoding="utf-8", errors="replace").strip()
        if not key:
            parser.error("scenario_bible_provider_key_missing")
        report = OfficialDeepSeekScenarioBibleCompiler().compile(
            seeds=seeds, rule_sets=rules, api_key=key, output_root=args.output,
        )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
