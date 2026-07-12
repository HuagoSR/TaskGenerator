from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_semantic_review_executor import (  # noqa: E402
    SemanticReviewExecutor,
    deepseek_semantic_config,
    gpt54_semantic_config,
)
from task_generator.v3_semantic_validity import (  # noqa: E402
    SemanticFinding,
    SemanticClaim,
    SemanticDependency,
    SemanticRequirement,
    SemanticReviewPackageBuilder,
    TaskSemanticContract,
    write_semantic_artifact,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate semantic-review provider JSON contracts on public data.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--deepseek-key-path", type=Path, required=True)
    parser.add_argument("--tuzi-env-path", type=Path, required=True)
    parser.add_argument("--allow-external-semantic-review", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--provider", choices=["all", "deepseek", "tuzi_gpt54"], default="all")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not args.allow_external_semantic_review:
        raise SystemExit("Public provider smoke requires explicit --allow-external-semantic-review.")
    fixture = ROOT / "Test" / "v3_semantic_public_fixture"
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    contract = _contract()
    contract_path = output / "task_semantic_contract.json"
    write_semantic_artifact(contract_path, contract)
    blind_package = SemanticReviewPackageBuilder().build_blind_package(
        task_id=contract.task_id,
        prompt=(fixture / "candidate_brief.txt").read_text(encoding="utf-8"),
        deliverable_contract={"reconciliation.xlsx": [contract.requirements[0].prompt_text]},
        reference_files=[fixture / "candidate_brief.txt"],
        output_path=output / "candidate_blind_prompt_package.json",
        semantic_contract=contract,
    )
    providers = {
        "deepseek": SemanticReviewExecutor(deepseek_semantic_config(args.deepseek_key_path, args.timeout_seconds)),
        "tuzi_gpt54": SemanticReviewExecutor(gpt54_semantic_config(args.tuzi_env_path, args.timeout_seconds)),
    }
    if args.provider != "all":
        providers = {args.provider: providers[args.provider]}
    records = []
    for provider_name, executor in providers.items():
        for repeat in (1, 2):
            run_dir = output / provider_name / f"repeat_{repeat}"
            run_dir.mkdir(parents=True, exist_ok=True)
            blind_path = run_dir / "blind_review.json"
            teacher_review_path = run_dir / "teacher_review.json"
            compact_secondary = provider_name == "tuzi_gpt54"
            if args.resume and blind_path.exists():
                if compact_secondary:
                    from task_generator.v3_semantic_validity import SecondarySemanticReview
                    blind = SecondarySemanticReview.model_validate(json.loads(blind_path.read_text(encoding="utf-8")))
                else:
                    from task_generator.v3_semantic_validity import CandidateBlindReview
                    blind = CandidateBlindReview.model_validate(json.loads(blind_path.read_text(encoding="utf-8")))
            elif compact_secondary:
                blind = executor.review_secondary(blind_package, _public_findings(), "candidate_blind")
                write_semantic_artifact(blind_path, blind)
            else:
                from task_generator.v3_semantic_validity import CandidateBlindReview
                blind = executor.review_blind(blind_package)
                write_semantic_artifact(blind_path, blind)
            teacher_package = SemanticReviewPackageBuilder().build_teacher_package(
                contract.task_id,
                blind_path,
                contract_path,
                {"teacher_truth": fixture / "teacher_truth.json", "rubric": fixture / "rubric.json"},
                run_dir / "teacher_prompt_package.json",
            )
            if args.resume and teacher_review_path.exists():
                if compact_secondary:
                    from task_generator.v3_semantic_validity import SecondarySemanticReview
                    teacher = SecondarySemanticReview.model_validate(json.loads(teacher_review_path.read_text(encoding="utf-8")))
                else:
                    from task_generator.v3_semantic_validity import TeacherRubricReview
                    teacher = TeacherRubricReview.model_validate(json.loads(teacher_review_path.read_text(encoding="utf-8")))
            elif compact_secondary:
                teacher = executor.review_secondary(teacher_package, _public_findings(), "teacher_rubric")
                write_semantic_artifact(teacher_review_path, teacher)
            else:
                teacher = executor.review_teacher(teacher_package)
                write_semantic_artifact(teacher_review_path, teacher)
            records.append({
                "provider": provider_name,
                "repeat": repeat,
                "blind_status": blind.status,
                "teacher_status": teacher.status,
                "raw_response_included": False,
            })
    expected_record_count = len(providers) * 2
    decision = "pass" if len(records) == expected_record_count and all(
        item["blind_status"] == "completed" and item["teacher_status"] == "completed" for item in records
    ) else "fail"
    report = {
        "report_version": "v3.semantic_provider_contract_smoke.1",
        "fixture_scope": "tracked_public_synthetic_only",
        "decision": decision,
        "records": records,
        "raw_response_included": False,
    }
    (output / "provider_contract_smoke_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False))


def _contract() -> TaskSemanticContract:
    return TaskSemanticContract(
        contract_version="v3.task_semantic_contract.public_fixture.1",
        task_id="public_synthetic_cash_reconciliation",
        created_at="fixture",
        requirements=[SemanticRequirement(
            requirement_id="req_001",
            prompt_text="Report exact matched and unmatched counts and both period-activity totals.",
            deliverable_file="reconciliation.xlsx",
            deliverable_location="workbook:summary",
            claim_ids=["claim_001"],
        )],
        claims=[SemanticClaim(
            claim_id="claim_001",
            requirement_id="req_001",
            claim_type="matching",
            determinism="exact",
            description="Matching counts and period totals",
            dependency_ids=["dep_001"],
            validator_id="public.synthetic.cash.v1",
            rubric_criterion_ids=["FACT_001"],
        )],
        dependencies=[SemanticDependency(
            dependency_id="dep_001",
            description="Candidate-visible synthetic brief",
            source_kind="candidate_file",
            file_name="candidate_brief.txt",
            locator="document:all",
            candidate_visible=True,
        )],
    )


def _public_findings():
    return [SemanticFinding(
        finding_code="ambiguous_requirement",
        severity="blocking",
        message="Check whether the matching requirement is uniquely answerable.",
        requirement_id="req_001",
        confidence=0.9,
    )]


if __name__ == "__main__":
    main()
