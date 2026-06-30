from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import argparse
import json
import sys
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = Path(__file__).resolve().parent
for path in (ROOT, TEST_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_v3_local_source_to_skill import build_prompt_package, normalize_source  # noqa: E402
from task_generator.v3_source_schema import NormalizedSource, RawSource, dump_json_file, load_raw_source  # noqa: E402


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_raw_sources(collection_dir: Path) -> List[RawSource]:
    raw_dir = collection_dir / "raw_sources"
    if not raw_dir.exists():
        raise RuntimeError(f"Missing raw_sources directory: {raw_dir}")
    paths = sorted(raw_dir.glob("*.json"))
    if not paths:
        raise RuntimeError(f"No RawSource JSON files found in: {raw_dir}")
    return [load_raw_source(str(path)) for path in paths]


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize collected V3 RawSource records and build a skill extraction prompt package.")
    parser.add_argument("--collection-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or (args.collection_dir / "normalized_package")
    norm_dir = output_dir / "normalized_sources"
    norm_dir.mkdir(parents=True, exist_ok=True)

    raw_sources = load_raw_sources(args.collection_dir)
    normalized_sources: List[NormalizedSource] = []
    manifest = []
    for raw_source in raw_sources:
        normalized = normalize_source(raw_source)
        dump_json_file(normalized, str(norm_dir / f"{normalized.normalized_source_id}.json"))
        normalized_sources.append(normalized)
        manifest.append(
            {
                "source_id": raw_source.source_id,
                "normalized_source_id": normalized.normalized_source_id,
                "title": raw_source.title,
                "url_or_path": raw_source.url_or_path,
                "block_count": len(normalized.blocks),
            }
        )

    package = build_prompt_package(normalized_sources)
    dump_json_file(package, str(output_dir / "skill_extraction_prompt_package.json"))
    write_json(
        output_dir / "manifest.json",
        {
            "collection_dir": str(args.collection_dir),
            "source_count": len(raw_sources),
            "normalized_source_count": len(normalized_sources),
            "sources": manifest,
        },
    )
    print(json.dumps({"source_count": len(raw_sources), "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()




