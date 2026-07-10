import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_gdpval_contamination import (  # noqa: E402
    ProtectedGDPValIndex,
    aggregate_domain_feasibility,
    audit_generation,
    build_protected_index,
)


def load_rows(arrow_path: Path):
    from datasets import Dataset

    return [dict(row) for row in Dataset.from_file(str(arrow_path))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GDPVal aggregate feasibility or isolated contamination evidence.")
    parser.add_argument("--action", choices=["feasibility", "protected-index", "audit"], required=True)
    parser.add_argument("--arrow-path", type=Path)
    parser.add_argument("--protected-index-path", type=Path)
    parser.add_argument("--source-manifest-path", type=Path)
    parser.add_argument("--generation-root", type=Path)
    parser.add_argument("--output-path", type=Path, required=True)
    args = parser.parse_args()

    if args.action in {"feasibility", "protected-index"} and not args.arrow_path:
        parser.error("--arrow-path is required")
    if args.action == "feasibility":
        payload = aggregate_domain_feasibility(load_rows(args.arrow_path))
    elif args.action == "protected-index":
        payload = build_protected_index(load_rows(args.arrow_path)).model_dump(mode="json")
    else:
        if not args.protected_index_path or not args.source_manifest_path or not args.generation_root:
            parser.error("audit requires --protected-index-path, --source-manifest-path, and --generation-root")
        protected = ProtectedGDPValIndex.model_validate_json(args.protected_index_path.read_text(encoding="utf-8"))
        payload = audit_generation(args.source_manifest_path, args.generation_root, protected).model_dump(mode="json")
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_path": str(args.output_path), "action": args.action}, ensure_ascii=False))


if __name__ == "__main__":
    main()
