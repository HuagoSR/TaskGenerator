import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_skill_reviewer import SkillCandidateReviewer  # noqa: E402
from v3_source_schema import ExtractedSkillCandidate, load_skill_candidates  # noqa: E402


DEFAULT_OUTPUT_PATH = ROOT / "SkillRegistry" / "v3_skill_reviewer_calibration_report.json"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_candidates(paths: List[Path]) -> List[tuple[Path, ExtractedSkillCandidate]]:
    loaded: List[tuple[Path, ExtractedSkillCandidate]] = []
    for path in paths:
        for candidate in load_skill_candidates(str(path)):
            loaded.append((path, candidate))
    return loaded


def suspicious_codes(reason_codes: List[str]) -> List[str]:
    interesting = {
        "broad_documentation_deliverable",
        "broad_control_assessment",
        "weak_action_granularity",
        "task_level_overbreadth",
        "source_collection_leakage",
        "low_atomicity",
    }
    return sorted(set(reason_codes) & interesting)


def calibrate(paths: List[Path]) -> Dict[str, object]:
    reviewer = SkillCandidateReviewer()
    loaded = load_candidates(paths)
    records = []
    decision_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    suspicious_accepted = []

    for source_path, candidate in loaded:
        review = reviewer.review(candidate)
        decision_counts.update([review.decision])
        reason_counts.update(review.reason_codes)
        codes = suspicious_codes(review.reason_codes)
        record = {
            "source_path": str(source_path),
            "candidate_id": candidate.candidate_id,
            "proposed_name": candidate.proposed_name,
            "previous_status": candidate.extraction_status,
            "new_decision": review.decision,
            "total_score": review.scores.total_score,
            "reason_codes": review.reason_codes,
            "suggested_abstraction": review.suggested_abstraction,
        }
        records.append(record)
        if review.decision == "accept" and codes:
            suspicious_accepted.append({**record, "suspicious_codes": codes})

    return {
        "calibration_version": "v3.reviewer_calibration.1",
        "candidate_file_count": len(paths),
        "candidate_count": len(loaded),
        "decision_counts": dict(sorted(decision_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "suspicious_accepted_count": len(suspicious_accepted),
        "suspicious_accepted_candidates": suspicious_accepted,
        "records": records,
        "notes": [
            "This is report-only and does not update candidates, registry entries, or extraction outputs.",
            "Use this report to calibrate reviewer thresholds before expanding Pipeline A or sampling for Pipeline B.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic reviewer calibration on existing skill candidate files.")
    parser.add_argument("--candidates", type=Path, action="append", required=True, help="Candidate JSON file. Can be repeated.")
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    report = calibrate(args.candidates)
    write_json(args.output_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
