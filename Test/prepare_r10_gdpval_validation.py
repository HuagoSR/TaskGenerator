"""Materialize the fixed public GDPval Gold calibration subset.

Run this script with an environment that provides the Hugging Face `datasets`
package.  All downloaded benchmark content is written below ignored artifacts;
it is never imported by TaskGenerator's generation path.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from task_generator.evaluation.r10_gdpval_validation import (
    GDPvalRankingSnapshotV1,
    GDPvalRubricItemV1,
    GDPvalTaskBindingV1,
)
from task_generator.planning.scenario_task_compiler import tree_sha256


TASKS = {
    "development": (
        "83d10b06-26d1-4636-a32c-23f92c57f30b",
        "7d7fc9a7-21a7-4b83-906f-416dea5ad04f",
        "1b1ade2d-f9f6-4a04-baa5-aa15012b53be",
        "24d1e93f-9018-45d4-b522-ad89dfd78079",
        "36d567ba-e205-4313-9756-931c6e4691fe",
        "dfb4e0cd-a0b7-454e-b943-0dd586c2764c",
    ),
    "holdout": (
        "7b08cd4d-df60-41ae-9102-8aaa49306ba2",
        "ee09d943-5a11-430a-b7a2-971b4e9b01b5",
        "15ddd28d-8445-4baa-ac7f-f41372e1344e",
        "05389f78-589a-473c-a4ae-67c61050bfca",
        "7bbfcfe9-132d-4194-82bb-d6f29d001b01",
        "4c18ebae-dfaa-4b76-b10c-61fcdf26734c",
    ),
}
OCCUPATIONS = {
    "Accountants and Auditors", "Buyers and Purchasing Agents", "Compliance Officers"
}


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)


def _name(dataset_path: str) -> str:
    name = PurePosixPath(dataset_path).name
    if not name or name in {".", ".."}:
        raise ValueError("gdpval_dataset_path_invalid")
    return name


def prepare(output_root: Path) -> dict:
    if output_root.exists():
        raise FileExistsError("gdpval_calibration_root_already_exists")
    from datasets import load_dataset

    dataset = load_dataset("openai/gdpval", split="train")
    selected = {task for tasks in TASKS.values() for task in tasks}
    rows = {row["task_id"]: row for row in dataset if row["task_id"] in selected}
    if set(rows) != selected:
        raise ValueError("gdpval_fixed_subset_incomplete")
    output_root.mkdir(parents=True)
    bindings = []
    for split, task_ids in TASKS.items():
        for task_id in task_ids:
            row = rows[task_id]
            if row["occupation"] not in OCCUPATIONS:
                raise ValueError("gdpval_occupation_drift")
            task_root = output_root / "tasks" / task_id
            references = task_root / "reference_files"
            gold = task_root / "human_gold"
            references.mkdir(parents=True)
            gold.mkdir(parents=True)
            for path, url in zip(row["reference_files"], row["reference_file_urls"], strict=True):
                _download(url, references / _name(path))
            for path, url in zip(row["deliverable_files"], row["deliverable_file_urls"], strict=True):
                _download(url, gold / _name(path))
            prompt = row["prompt"]
            (task_root / "prompt.txt").write_text(prompt, encoding="utf-8")
            rubric_raw = json.loads(row["rubric_json"])
            binding = GDPvalTaskBindingV1(
                task_id=task_id, sector=row["sector"], occupation=row["occupation"], split=split,
                prompt_sha256=__import__("hashlib").sha256(prompt.encode()).hexdigest(),
                reference_tree_sha256=tree_sha256(references), gold_tree_sha256=tree_sha256(gold),
                reference_files=sorted(path.name for path in references.iterdir()),
                expected_deliverables=[_name(path) for path in row["deliverable_files"]],
                rubric_items=[GDPvalRubricItemV1(
                    rubric_item_id=item["rubric_item_id"], score=item["score"],
                    criterion=item["criterion"], author_type=item.get("author_type") or "human",
                ) for item in rubric_raw],
            )
            (task_root / "binding.json").write_text(binding.model_dump_json(indent=2) + "\n", encoding="utf-8")
            bindings.append(binding)
    snapshot = GDPvalRankingSnapshotV1(
        source_url="https://artificialanalysis.ai/evaluations/gdpval-aa",
        captured_at=_now(),
        scores={
            "gpt-5.6-sol@chatgpt_codex": 1379,
            "deepseek-v4-pro@official_opencode": 1306,
            "deepseek-v4-flash@official_opencode": 1153,
        },
        reference_order=[
            "gpt-5.6-sol@chatgpt_codex",
            "deepseek-v4-pro@official_opencode",
            "deepseek-v4-flash@official_opencode",
        ],
    )
    (output_root / "ranking_snapshot.json").write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    manifest = {
        "manifest_version": "r10.gdpval_public_subset.1", "created_at": _now(),
        "dataset": "openai/gdpval", "purpose": "eval_calibration_only",
        "splits": {key: list(value) for key, value in TASKS.items()},
        "binding_sha256": {item.task_id: item.canonical_sha256() for item in bindings},
        "ranking_snapshot_sha256": snapshot.canonical_sha256(),
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/r10/r10_10_gdpval_public_20260903")
    args = parser.parse_args()
    print(json.dumps(prepare(args.output_root), indent=2))


if __name__ == "__main__":
    main()
