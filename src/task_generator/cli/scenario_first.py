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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline R10 Scenario-First admission checks.")
    parser.add_argument("--action", choices=["admit-seeds"], required=True)
    parser.add_argument("--source-catalog", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--rule-sets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
    report = WorkSeedAdmissionValidator().evaluate(
        catalog=catalog, candidates=candidates, rule_sets=rules,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
