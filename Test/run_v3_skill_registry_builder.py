import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_skill_registry import SkillRegistryBuilder  # noqa: E402
from v3_source_schema import load_skill_candidates  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a first-pass V3 skill registry from extracted or accepted skill candidates.")
    parser.add_argument("--candidates", type=Path, required=True, help="Path to extracted_skill_candidates.json or accepted_skill_candidates.json.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for skill_registry.json and report.")
    args = parser.parse_args()

    candidates = load_skill_candidates(str(args.candidates))
    builder = SkillRegistryBuilder()
    entries = builder.build_entries(candidates)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    registry_payload = {
        "registry_version": "v3.0",
        "entry_count": len(entries),
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }
    report_payload = {
        "candidate_count": len(candidates),
        "entry_count": len(entries),
        "entry_names": [entry.canonical_name for entry in entries],
    }

    with open(args.output_dir / "skill_registry.json", "w", encoding="utf-8") as f:
        json.dump(registry_payload, f, ensure_ascii=False, indent=2)
    with open(args.output_dir / "skill_registry_report.json", "w", encoding="utf-8") as f:
        json.dump(report_payload, f, ensure_ascii=False, indent=2)

    print(json.dumps(report_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
