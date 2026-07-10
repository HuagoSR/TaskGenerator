import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_source_schema import (  # noqa: E402
    NormalizedSource,
    SkillExtractionPromptPackage,
    SourceBlock,
    SourceSpan,
    dump_json_file,
)


PUBLIC_SOURCE_TEXT = """Public synthetic audit training note.

A regional nonprofit receives donations through two payment processors and a small number of mailed checks. A monthly finance review asks the analyst to reconcile processor exports against the general ledger, identify duplicate donor receipts, and produce a short variance explanation for management.

The source materials include one spreadsheet with processor settlement rows, one spreadsheet with general ledger revenue rows, and a policy note explaining that refunds after month-end should be excluded from current-month donation revenue.

The intended task is not to copy rows into a template. The analyst must create a new workbook with a clean reconciliation summary, a list of exceptions, and a management-ready explanation of unresolved differences.

Common mistakes include double-counting duplicate donor receipts, treating refunded payments as current-month revenue, ignoring processor fees, and producing a polished workbook whose totals do not tie back to the source exports.

Useful evaluation criteria include whether the final revenue total ties to the reconciled source data, whether excluded refunds are documented, whether duplicate receipts are isolated, and whether the final workbook is readable for a finance manager.
"""


def build_public_package(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_id = "public_src_nonprofit_reconciliation"
    normalized_source_id = "public_norm_nonprofit_reconciliation"
    paragraphs = [chunk.strip() for chunk in PUBLIC_SOURCE_TEXT.split("\n\n") if chunk.strip()]
    blocks = []
    cursor = 0
    for idx, paragraph in enumerate(paragraphs, start=1):
        start_char = PUBLIC_SOURCE_TEXT.find(paragraph, cursor)
        end_char = start_char + len(paragraph)
        cursor = end_char
        block_id = f"block_{idx:04d}"
        block_type = "task_prompt" if idx in {2, 4} else "paragraph"
        if "evaluation criteria" in paragraph.lower():
            block_type = "rubric"
        blocks.append(
            SourceBlock(
                block_id=block_id,
                block_type=block_type,
                text=paragraph,
                source_span=SourceSpan(
                    source_id=source_id,
                    block_id=block_id,
                    start_char=start_char,
                    end_char=end_char,
                    quote=paragraph[:500],
                ),
                semantic_tags=["finance", "audit", "reconciliation"],
            )
        )

    normalized = NormalizedSource(
        normalized_source_id=normalized_source_id,
        source_id=source_id,
        title="Public Synthetic Nonprofit Donation Reconciliation",
        domain_tags=["finance", "audit", "public_synthetic"],
        blocks=blocks,
        domain_terms=["donation revenue", "duplicate receipt", "refund exclusion", "reconciliation"],
        candidate_task_patterns=[
            "Reconcile processor exports against general ledger revenue rows.",
            "Create a new workbook with reconciliation summary, exceptions, and management explanation.",
        ],
    )
    package = SkillExtractionPromptPackage(
        request_id="public_skill_extract_nonprofit_reconciliation",
        normalized_sources=[normalized],
        instructions=(
            "Extract reusable semantic skills from this public synthetic audit note. "
            "Return skills that could generalize to other real-world reconciliation tasks."
        ),
        constraints=[
            "Return JSON only.",
            "Use only source_id and block_id values from the provided normalized source.",
            "Do not encode exact file names, row counts, or fixed rubric text.",
        ],
    )

    dump_json_file(normalized, str(output_dir / "public_normalized_source.json"))
    dump_json_file(package, str(output_dir / "skill_extraction_prompt_package.json"))
    with open(output_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(
            "# Public V3 Skill Extraction Smoke Package\n\n"
            "This package is synthetic and intentionally safe to send to external LLM APIs for smoke testing.\n\n"
            "Milestone C uses `public-smoke-offline` and `public-smoke-llm`; mock output is smoke-only, "
            "and external task evaluation remains disabled.\n"
        )
    acceptance_contract = {
            "contract_version": "v3.public_smoke_acceptance.1",
            "fixture_id": "public_skill_extract_nonprofit_reconciliation",
            "offline": {
                "candidate_count": 4,
                "accepted_count": 4,
                "sample_ready_count": 3,
                "generated_case_count": 2,
                "candidate_ready_count": 2,
                "verifier_pass_count": 2,
                "export_compatible_count": 2,
                "prepared_eval_count": 1,
                "executed_eval_count": 0,
            },
            "llm_minimum": {
                "candidate_count": 3,
                "accepted_count": 2,
                "sample_ready_count": 2,
                "candidate_ready_count": 1,
                "verifier_pass_count": 1,
                "export_compatible_count": 1,
                "executed_eval_count": 0,
            },
            "boundaries": {
                "fixture_is_public_synthetic": True,
                "mock_output_is_smoke_only": True,
                "canonical_registry_mutation_allowed": False,
                "external_eval_allowed": False,
            },
        }
    with open(output_dir / "acceptance_contract.json", "w", encoding="utf-8") as f:
        json.dump(acceptance_contract, f, ensure_ascii=False, indent=2)
    print(json.dumps({"output_dir": str(output_dir), "block_count": len(blocks)}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a public synthetic V3 skill-extraction smoke package.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "Test" / "v3_public_smoke_package")
    args = parser.parse_args()
    build_public_package(args.output_dir)


if __name__ == "__main__":
    main()


