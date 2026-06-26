import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List

from datasets import Dataset, DownloadConfig, load_dataset


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_source_schema import (  # noqa: E402
    NormalizedSource,
    SkillExtractionPromptPackage,
    SourceBlock,
    SourceSpan,
    dump_json_file,
)


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "gdpval_prompt"


DEFAULT_GDPVAL_ARROW = Path(
    r"C:\Users\ysyys\.cache\huggingface\datasets\openai___gdpval\default\0.0.0\11e7900cdcac61bc4daf59e65feb238acda98fbf\gdpval-train.arrow"
)


def load_gdpval_rows(local_files_only: bool, cache_arrow: Path) -> List[Dict[str, object]]:
    if cache_arrow.exists():
        dataset = Dataset.from_file(str(cache_arrow))
        return [dict(row) for row in dataset]
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    download_config = DownloadConfig(local_files_only=local_files_only)
    dataset = load_dataset("openai/gdpval", split="train", download_config=download_config)
    return [dict(row) for row in dataset]


def row_matches(row: Dict[str, object], args: argparse.Namespace) -> bool:
    if args.task_id and str(row.get("task_id")) not in set(args.task_id):
        return False
    if args.occupation_filter:
        occupation = str(row.get("occupation", "")).lower()
        if not any(term.lower() in occupation for term in args.occupation_filter):
            return False
    if args.sector_filter:
        sector = str(row.get("sector", "")).lower()
        if not any(term.lower() in sector for term in args.sector_filter):
            return False
    return True


def infer_domain_tags(row: Dict[str, object]) -> List[str]:
    tags = ["gdpval", "prompt_only"]
    sector = str(row.get("sector", "")).lower()
    occupation = str(row.get("occupation", "")).lower()
    combined = f"{sector} {occupation}"
    if any(term in combined for term in ["account", "audit", "finance", "tax"]):
        tags.append("finance")
        tags.append("audit")
    if "software" in combined or "developer" in combined:
        tags.append("software")
    if "legal" in combined or "law" in combined:
        tags.append("legal")
    return sorted(set(tags))


def build_normalized_source(row: Dict[str, object]) -> NormalizedSource:
    task_id = str(row["task_id"])
    prompt = str(row["prompt"])
    source_id = f"gdpval_prompt_{slugify(task_id)}"
    normalized_source_id = stable_id("gdpval_norm", f"{task_id}:{prompt[:1000]}")
    block = SourceBlock(
        block_id="block_0001",
        block_type="task_prompt",
        text=prompt,
        source_span=SourceSpan(
            source_id=source_id,
            block_id="block_0001",
            start_char=0,
            end_char=len(prompt),
            quote=prompt[:500],
            note="GDPVal prompt text only; no rubric, files, or answers included.",
        ),
        semantic_tags=infer_domain_tags(row),
        metadata={
            "task_id": task_id,
            "sector": str(row.get("sector", "")),
            "occupation": str(row.get("occupation", "")),
        },
    )
    return NormalizedSource(
        normalized_source_id=normalized_source_id,
        source_id=source_id,
        title=f"GDPVal Prompt {task_id}",
        domain_tags=infer_domain_tags(row),
        blocks=[block],
        domain_terms=[str(row.get("sector", "")), str(row.get("occupation", ""))],
        candidate_task_patterns=[prompt[:300]],
    )


def build_prompt_package(sources: Iterable[NormalizedSource], include_public_upload_note: bool) -> SkillExtractionPromptPackage:
    source_list = list(sources)
    constraints = [
        "Return JSON only.",
        "Extract reusable semantic skills from GDPVal prompt text only.",
        "Do not infer from GDPVal rubrics, reference files, deliverable files, answers, or hidden metadata.",
        "Optimize for reusable and diverse skills, not one prompt-specific task detail.",
        "Preserve evidence references to GDPVal prompt blocks.",
    ]
    if include_public_upload_note:
        constraints.append("The prompt text is treated as public benchmark text approved for external LLM extraction.")
    return SkillExtractionPromptPackage(
        request_id=stable_id("gdpval_prompt_extract", ",".join(source.source_id for source in source_list)),
        normalized_sources=source_list,
        instructions=(
            "Extract reusable semantic skills from GDPVal task prompts. "
            "Use the old pipeline's strengths: semantic ports, reusable business intents, data-profile-like context, "
            "and Fact/Reasoning/Robustness/Compliance dimensions. "
            "Do not output operators, data_params, row counts, file names, or fixed rubric text."
        ),
        constraints=constraints,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GDPVal prompt-only sources for V3 source-to-skill extraction.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--occupation-filter", action="append", default=[])
    parser.add_argument("--sector-filter", action="append", default=[])
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--include-public-upload-note", action="store_true")
    parser.add_argument("--allow-network", action="store_true", help="Allow HuggingFace network access instead of using local cache only.")
    parser.add_argument("--cache-arrow", type=Path, default=DEFAULT_GDPVAL_ARROW, help="Path to cached gdpval-train.arrow.")
    args = parser.parse_args()

    rows = [
        row
        for row in load_gdpval_rows(local_files_only=not args.allow_network, cache_arrow=args.cache_arrow)
        if row_matches(row, args)
    ]
    selected = rows[: args.limit] if args.limit > 0 else rows
    if not selected:
        raise RuntimeError("No GDPVal rows matched the requested filters.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    norm_dir = args.output_dir / "normalized_sources"
    norm_dir.mkdir(parents=True, exist_ok=True)

    normalized_sources = [build_normalized_source(row) for row in selected]
    for source in normalized_sources:
        dump_json_file(source, str(norm_dir / f"{source.normalized_source_id}.json"))

    package = build_prompt_package(normalized_sources, include_public_upload_note=args.include_public_upload_note)
    dump_json_file(package, str(args.output_dir / "skill_extraction_prompt_package.json"))

    manifest = {
        "source": "openai/gdpval",
        "split": "train",
        "prompt_only": True,
        "excludes": ["rubric", "reference_files", "deliverable_files", "answers", "data_file_contents"],
        "row_count": len(selected),
        "rows": [
            {
                "task_id": str(row.get("task_id", "")),
                "sector": str(row.get("sector", "")),
                "occupation": str(row.get("occupation", "")),
                "source_id": source.source_id,
                "normalized_source_id": source.normalized_source_id,
                "prompt_char_count": len(str(row.get("prompt", ""))),
            }
            for row, source in zip(selected, normalized_sources)
        ],
    }
    with open(args.output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    readme = (
        "# GDPVal Prompt-Only Source Package\n\n"
        "This package contains GDPVal task prompt text and task metadata only.\n\n"
        "It intentionally excludes rubrics, reference file lists, deliverable file lists, answer traces, and file contents.\n"
    )
    (args.output_dir / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps({"output_dir": str(args.output_dir), "row_count": len(selected)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
