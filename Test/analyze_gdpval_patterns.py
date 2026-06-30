import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

from datasets import load_dataset


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "v2_outputs" / "gdpval_analysis"
SUMMARY_JSON = OUTPUT_DIR / "summary.json"
SUMMARY_MD = OUTPUT_DIR / "summary.md"


def _ext(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return suffix or "<no_ext>"


def _safe_prompt_excerpt(text: str, limit: int = 900) -> str:
    compact = " ".join(text.split())
    return compact[:limit]


def _contains_new_document_signal(prompt: str) -> bool:
    lowered = prompt.lower()
    markers = [
        "create a new excel document",
        "create a new spreadsheet",
        "create a new workbook",
        "prepare a structured excel",
        "prepare a structured",
        "create a new",
    ]
    return any(marker in lowered for marker in markers)


def _load_rows() -> List[Dict[str, object]]:
    os.environ.setdefault("HF_HOME", "D:/huggingface_cache")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    ds = load_dataset("openai/gdpval", split="train")
    return [dict(row) for row in ds]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = _load_rows()
    total = len(rows)

    reference_count_dist = Counter(len(row["reference_files"]) for row in rows)
    deliverable_count_dist = Counter(len(row["deliverable_files"]) for row in rows)
    reference_ext_dist = Counter()
    deliverable_ext_dist = Counter()
    occupation_dist = Counter()
    sector_dist = Counter()

    for row in rows:
        occupation_dist[row["occupation"]] += 1
        sector_dist[row["sector"]] += 1
        for file_path in row["reference_files"]:
            reference_ext_dist[_ext(file_path)] += 1
        for file_path in row["deliverable_files"]:
            deliverable_ext_dist[_ext(file_path)] += 1

    accountant_rows = [row for row in rows if row["occupation"] == "Accountants and Auditors"]
    finance_rows = [
        row
        for row in rows
        if row["occupation"] == "Accountants and Auditors"
        or "finance" in str(row["occupation"]).lower()
        or "audit" in str(row["occupation"]).lower()
        or "account" in str(row["occupation"]).lower()
    ]

    accountant_patterns = {
        "row_count": len(accountant_rows),
        "reference_count_dist": dict(Counter(len(row["reference_files"]) for row in accountant_rows)),
        "deliverable_count_dist": dict(Counter(len(row["deliverable_files"]) for row in accountant_rows)),
        "reference_ext_dist": dict(
            Counter(_ext(path) for row in accountant_rows for path in row["reference_files"])
        ),
        "deliverable_ext_dist": dict(
            Counter(_ext(path) for row in accountant_rows for path in row["deliverable_files"])
        ),
        "new_document_prompt_count": sum(
            1 for row in accountant_rows if _contains_new_document_signal(row["prompt"])
        ),
    }

    finance_examples = []
    target_ids = {
        "7b08cd4d-df60-41ae-9102-8aaa49306ba2",
        "83d10b06-26d1-4636-a32c-23f92c57f30b",
    }
    for row in finance_rows:
        if row["task_id"] in target_ids or len(finance_examples) < 5:
            finance_examples.append(
                {
                    "task_id": row["task_id"],
                    "sector": row["sector"],
                    "occupation": row["occupation"],
                    "reference_files": row["reference_files"],
                    "deliverable_files": row["deliverable_files"],
                    "new_document_signal": _contains_new_document_signal(row["prompt"]),
                    "prompt_excerpt": _safe_prompt_excerpt(str(row["prompt"])),
                }
            )
        if len(finance_examples) >= 5 and target_ids.issubset({item["task_id"] for item in finance_examples}):
            break

    same_name_pairs = 0
    extension_pairs = defaultdict(int)
    for row in rows:
        ref_names = {Path(path).name.lower() for path in row["reference_files"]}
        del_names = {Path(path).name.lower() for path in row["deliverable_files"]}
        if ref_names & del_names:
            same_name_pairs += 1
        for ref_path in row["reference_files"]:
            for del_path in row["deliverable_files"]:
                extension_pairs[f"{_ext(ref_path)}->{_ext(del_path)}"] += 1

    summary = {
        "total_rows": total,
        "reference_count_distribution": dict(reference_count_dist),
        "deliverable_count_distribution": dict(deliverable_count_dist),
        "reference_extension_distribution": dict(reference_ext_dist),
        "deliverable_extension_distribution": dict(deliverable_ext_dist),
        "top_occupations": occupation_dist.most_common(12),
        "top_sectors": sector_dist.most_common(12),
        "accountant_and_auditor_patterns": accountant_patterns,
        "same_filename_overlap_rows": same_name_pairs,
        "reference_to_deliverable_extension_pairs": dict(sorted(extension_pairs.items())),
        "finance_examples": finance_examples,
    }

    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# GDPVal Pattern Analysis",
        "",
        f"- total_rows: {total}",
        f"- reference_count_distribution: {dict(reference_count_dist)}",
        f"- deliverable_count_distribution: {dict(deliverable_count_dist)}",
        f"- reference_extension_distribution: {dict(reference_ext_dist)}",
        f"- deliverable_extension_distribution: {dict(deliverable_ext_dist)}",
        f"- same_filename_overlap_rows: {same_name_pairs}",
        "",
        "## Accountants And Auditors",
        "",
        f"- row_count: {accountant_patterns['row_count']}",
        f"- reference_count_dist: {accountant_patterns['reference_count_dist']}",
        f"- deliverable_count_dist: {accountant_patterns['deliverable_count_dist']}",
        f"- reference_ext_dist: {accountant_patterns['reference_ext_dist']}",
        f"- deliverable_ext_dist: {accountant_patterns['deliverable_ext_dist']}",
        f"- new_document_prompt_count: {accountant_patterns['new_document_prompt_count']}",
        "",
        "## Finance Examples",
        "",
    ]

    for item in finance_examples:
        lines.extend(
            [
                f"### {item['task_id']}",
                f"- occupation: {item['occupation']}",
                f"- reference_files: {item['reference_files']}",
                f"- deliverable_files: {item['deliverable_files']}",
                f"- new_document_signal: {item['new_document_signal']}",
                f"- prompt_excerpt: {item['prompt_excerpt']}",
                "",
            ]
        )

    SUMMARY_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote GDPVal analysis to {SUMMARY_JSON}")
    print(f"Wrote GDPVal analysis summary to {SUMMARY_MD}")


if __name__ == "__main__":
    main()



