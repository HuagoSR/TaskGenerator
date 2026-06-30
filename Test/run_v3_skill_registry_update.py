import argparse
import json
import sys
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_skill_registry import SkillRegistryBuilder  # noqa: E402
from task_generator.v3_source_schema import ExtractedSkillCandidate, load_skill_candidates  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"


def load_all_candidates(paths: List[Path]) -> List[ExtractedSkillCandidate]:
    candidates: List[ExtractedSkillCandidate] = []
    for path in paths:
        candidates.extend(load_skill_candidates(str(path)))
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Update the persistent V3 atomic skill registry from reviewed skill candidates.")
    parser.add_argument("--candidates", type=Path, nargs="+", required=True, help="One or more accepted/extracted skill candidate JSON files.")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH, help="Persistent registry JSON path.")
    parser.add_argument("--report-path", type=Path, default=None, help="Update report JSON path. Defaults next to the registry.")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print the update report without writing the registry.")
    args = parser.parse_args()

    report_path = args.report_path or args.registry_path.with_name("v3_skill_registry_update_report.json")
    builder = SkillRegistryBuilder()
    existing_entries = builder.load_registry(args.registry_path)
    candidates = load_all_candidates(args.candidates)
    updated_entries, report = builder.update_registry(existing_entries, candidates)
    report["registry_path"] = str(args.registry_path)
    report["candidate_paths"] = [str(path) for path in args.candidates]
    report["dry_run"] = args.dry_run

    if not args.dry_run:
        builder.write_registry(args.registry_path, updated_entries)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



