"""Offline entry points for R10 Scenario-First slices."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from task_generator.core.scenario_first import ProfessionalRuleSetV1
from task_generator.evaluation.r10_behavioral import (
    R10BehavioralResultV1,
    R10ModelTaskResultV1,
    R10PilotTaskBindingV1,
    diagnose_pilot_discrimination,
)
from task_generator.evaluation.r10_evaluator_v2 import profile_from_frozen_supervision
from task_generator.planning.scenario_task_compiler import TaskSpecificRubricV1, tree_sha256
from task_generator.core.scenario_first import TaskDecisionMatrixV1
from task_generator.planning.work_seed_admission import (
    PublicWorkSourceCatalogV1,
    WorkSeedAdmissionValidator,
    WorkSeedCandidateV1,
)
from task_generator.planning.scenario_bible_compiler import OfficialDeepSeekScenarioBibleCompiler
from task_generator.production.r10_world_first import (
    WorldFirstPilotManifestV1,
    resumable_case_ids,
    write_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline R10 Scenario-First admission checks.")
    parser.add_argument(
        "--action",
        choices=[
            "admit-seeds", "compile-bibles", "diagnose-pilot",
            "run-world-pilot", "status-world-pilot", "resume-world-pilot",
            "build-evaluator-profile",
        ],
        required=True,
    )
    parser.add_argument("--source-catalog", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--rule-sets", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--admission-report", type=Path)
    parser.add_argument("--provider-key-file", type=Path)
    parser.add_argument("--records", type=Path)
    parser.add_argument("--behavioral-result", type=Path)
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--world-manifest", type=Path)
    parser.add_argument("--task-root", type=Path)
    parser.add_argument("--evaluator-iteration", choices=["v2.0", "v2.1", "v2.2"], default="v2.0")
    args = parser.parse_args()

    if args.action == "build-evaluator-profile":
        if args.task_root is None:
            parser.error("--task-root is required for build-evaluator-profile")
        task_root = args.task_root.resolve()
        teacher = task_root / "teacher"
        matrix = TaskDecisionMatrixV1.model_validate_json(
            (teacher / "decision_matrix.json").read_text(encoding="utf-8")
        )
        rubric = TaskSpecificRubricV1.model_validate_json(
            (teacher / "task_specific_rubric.json").read_text(encoding="utf-8")
        )
        profile = profile_from_frozen_supervision(
            task_id=task_root.name,
            task_tree_sha256=tree_sha256(task_root),
            teacher_tree_sha256=tree_sha256(teacher),
            matrix=matrix, rubric=rubric,
            iteration=args.evaluator_iteration,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        print(json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    if args.action in {"run-world-pilot", "status-world-pilot", "resume-world-pilot"}:
        if args.world_manifest is None:
            parser.error("--world-manifest is required for World-First actions")
        manifest = WorldFirstPilotManifestV1.model_validate_json(
            args.world_manifest.read_text(encoding="utf-8")
        )
        if args.action == "run-world-pilot":
            if args.output.exists():
                parser.error("world_first_output_already_exists")
            if any(item.stage != "not_started" for item in manifest.cases):
                parser.error("world_first_run_requires_pristine_manifest")
            write_manifest(args.output, manifest)
            payload = manifest.model_dump(mode="json")
        else:
            payload = {
                "campaign_id": manifest.campaign_id,
                "decision": manifest.decision,
                "case_stages": {item.case_id: item.stage for item in manifest.cases},
                "resumable_case_ids": resumable_case_ids(manifest),
            }
            if args.action == "resume-world-pilot" and manifest.decision != "pending":
                parser.error("world_first_terminal_manifest_cannot_resume")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if args.action == "diagnose-pilot":
        if args.records is None or args.behavioral_result is None or args.bindings is None:
            parser.error("--records, --behavioral-result and --bindings are required for diagnose-pilot")
        records = [
            R10ModelTaskResultV1.model_validate(item)
            for item in json.loads(args.records.read_text(encoding="utf-8"))
        ]
        result_payload = json.loads(args.behavioral_result.read_text(encoding="utf-8"))
        aggregate_payload = result_payload.get("aggregate", result_payload)
        behavioral_result = R10BehavioralResultV1.model_validate(aggregate_payload)
        bindings_payload = json.loads(args.bindings.read_text(encoding="utf-8"))
        bindings_items = bindings_payload.get("bindings", bindings_payload)
        bindings = [R10PilotTaskBindingV1.model_validate(item) for item in bindings_items]
        report = diagnose_pilot_discrimination(
            records, behavioral_result=behavioral_result, bindings=bindings,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    if args.source_catalog is None or args.candidates is None or args.rule_sets is None:
        parser.error("--source-catalog, --candidates and --rule-sets are required for this action")
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
