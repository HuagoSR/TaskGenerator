import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_source_schema import (  # noqa: E402
    NormalizedSource,
    RawSource,
    SkillExtractionPromptPackage,
    SourceBlock,
    SourceSpan,
    dump_json_file,
)


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def split_blocks(text: str, source_id: str) -> List[SourceBlock]:
    blocks: List[SourceBlock] = []
    for idx, match in enumerate(re.finditer(r"\S(?:.*?)(?:\n\s*\n|$)", text, flags=re.DOTALL), start=1):
        block_text = match.group(0).strip()
        if not block_text:
            continue
        block_type = infer_block_type(block_text)
        block_id = f"block_{idx:04d}"
        blocks.append(
            SourceBlock(
                block_id=block_id,
                block_type=block_type,
                text=block_text,
                source_span=SourceSpan(
                    source_id=source_id,
                    block_id=block_id,
                    start_char=match.start(),
                    end_char=match.end(),
                    quote=block_text[:500],
                ),
                semantic_tags=infer_semantic_tags(block_text),
            )
        )
    return blocks


def infer_block_type(text: str) -> str:
    lower = text.lower()
    if "rubric" in lower or "评分" in text or "criterion" in lower:
        return "rubric"
    if "task" in lower or "assignment" in lower or "deliverable" in lower or "题目" in text:
        return "task_prompt"
    if "|" in text and text.count("|") >= 4:
        return "table"
    if any(token in text for token in ["=", "公式", "calculate", "compute"]):
        return "formula"
    if len(text) < 120 and (":" in text or "：" in text):
        return "domain_term"
    return "paragraph"


def infer_semantic_tags(text: str) -> List[str]:
    tags = []
    lower = text.lower()
    tag_patterns = {
        "finance": ["audit", "revenue", "expense", "tax", "withholding", "p&l", "财务", "审计"],
        "spreadsheet": ["excel", "spreadsheet", "workbook", "sheet", "xlsx", "表格"],
        "rubric": ["rubric", "criterion", "score", "评分"],
        "task": ["task", "assignment", "deliverable", "题目", "任务"],
        "reasoning": ["infer", "reconcile", "resolve", "compare", "推理", "核对"],
        "robustness": ["missing", "incomplete", "irregular", "trap", "缺失", "异常"],
    }
    for tag, patterns in tag_patterns.items():
        if any(pattern in lower or pattern in text for pattern in patterns):
            tags.append(tag)
    return tags


def extract_domain_terms(blocks: List[SourceBlock]) -> List[str]:
    terms = set()
    for block in blocks:
        for tag in block.semantic_tags:
            terms.add(tag)
        for match in re.finditer(r"`([^`]{3,80})`", block.text):
            terms.add(match.group(1))
    return sorted(terms)


def extract_candidate_task_patterns(blocks: List[SourceBlock]) -> List[str]:
    patterns = []
    for block in blocks:
        if block.block_type in {"task_prompt", "rubric", "formula"}:
            patterns.append(block.text[:240])
    return patterns[:12]


def build_raw_source(path: Path, domain_tags: List[str]) -> RawSource:
    text = read_text(path)
    source_id = stable_id("src", f"{path.resolve()}::{text[:1000]}")
    return RawSource(
        source_id=source_id,
        source_type="text_note",
        domain_tags=domain_tags,
        url_or_path=str(path.resolve()),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        title=path.stem,
        raw_text_path=str(path.resolve()),
        collection_trace=["loaded from local text file"],
        metadata={"file_size": path.stat().st_size},
    )


def normalize_source(raw_source: RawSource) -> NormalizedSource:
    if not raw_source.raw_text_path:
        raise ValueError(f"Raw source has no raw_text_path: {raw_source.source_id}")
    text = read_text(Path(raw_source.raw_text_path))
    blocks = split_blocks(text, raw_source.source_id)
    return NormalizedSource(
        normalized_source_id=stable_id("norm", raw_source.source_id),
        source_id=raw_source.source_id,
        title=raw_source.title,
        domain_tags=raw_source.domain_tags,
        blocks=blocks,
        domain_terms=extract_domain_terms(blocks),
        candidate_task_patterns=extract_candidate_task_patterns(blocks),
    )


def build_prompt_package(normalized_sources: List[NormalizedSource]) -> SkillExtractionPromptPackage:
    source_ids = ",".join(source.source_id for source in normalized_sources)
    return SkillExtractionPromptPackage(
        request_id=stable_id("skill_extract_req", source_ids),
        normalized_sources=normalized_sources,
        instructions=(
            "Extract reusable semantic skills from the normalized sources. "
            "Do not encode exact file names, row counts, generated values, or fixed rubric text. "
            "Each skill should describe capability meaning, input/output semantics, hidden difficulty, "
            "failure modes, common deliverables, assembly hints, and evidence spans."
        ),
        constraints=[
            "Return JSON only.",
            "Return an array of ExtractedSkillCandidate objects.",
            "Every candidate must cite at least one evidence span.",
            "Prefer reusable capability abstractions over one-off task details.",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize local text sources and build a V3 skill-extraction prompt package.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory containing .txt or .md source files.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for RawSource, NormalizedSource, and prompt package JSON.")
    parser.add_argument("--domain-tag", action="append", default=[], help="Domain tag to attach to every source. Can be repeated.")
    args = parser.parse_args()

    source_paths = sorted([*args.input_dir.glob("*.txt"), *args.input_dir.glob("*.md")])
    if not source_paths:
        raise RuntimeError(f"No .txt or .md files found in {args.input_dir}")

    raw_dir = args.output_dir / "raw_sources"
    norm_dir = args.output_dir / "normalized_sources"
    raw_dir.mkdir(parents=True, exist_ok=True)
    norm_dir.mkdir(parents=True, exist_ok=True)

    normalized_sources = []
    manifest = []
    for path in source_paths:
        raw_source = build_raw_source(path, args.domain_tag)
        normalized = normalize_source(raw_source)
        dump_json_file(raw_source, str(raw_dir / f"{raw_source.source_id}.json"))
        dump_json_file(normalized, str(norm_dir / f"{normalized.normalized_source_id}.json"))
        normalized_sources.append(normalized)
        manifest.append(
            {
                "source_path": str(path.resolve()),
                "source_id": raw_source.source_id,
                "normalized_source_id": normalized.normalized_source_id,
                "block_count": len(normalized.blocks),
            }
        )

    prompt_package = build_prompt_package(normalized_sources)
    dump_json_file(prompt_package, str(args.output_dir / "skill_extraction_prompt_package.json"))
    with open(args.output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({"sources": manifest}, f, ensure_ascii=False, indent=2)

    print(json.dumps({"source_count": len(source_paths), "output_dir": str(args.output_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

