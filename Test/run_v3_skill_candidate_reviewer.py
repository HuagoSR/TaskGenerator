import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_skill_reviewer import SkillCandidateReviewer  # noqa: E402
from v3_source_schema import load_skill_candidates  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Review V3 extracted skill candidates before registry insertion.")
    parser.add_argument("--candidates", type=Path, required=True, help="Path to extracted_skill_candidates.json.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for review outputs.")
    args = parser.parse_args()

    candidates = load_skill_candidates(str(args.candidates))
    reviewer = SkillCandidateReviewer()
    reviews = reviewer.review_many(candidates)
    accepted = reviewer.accepted_candidates(candidates, reviews)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    reviewed_payload = {
        "candidate_count": len(candidates),
        "accepted_count": len(accepted),
        "reviews": [review.model_dump(mode="json") for review in reviews],
    }
    accepted_payload = {
        "candidate_count": len(candidates),
        "accepted_count": len(accepted),
        "accepted_candidates": [candidate.model_dump(mode="json") for candidate in accepted],
    }
    report_payload = {
        "candidate_count": len(candidates),
        "accepted_count": len(accepted),
        "revise_count": sum(1 for review in reviews if review.decision == "revise"),
        "rejected_count": sum(1 for review in reviews if review.decision == "reject"),
        "decisions": [
            {
                "candidate_id": review.candidate_id,
                "proposed_name": review.proposed_name,
                "decision": review.decision,
                "total_score": review.scores.total_score,
                "reason_codes": review.reason_codes,
            }
            for review in reviews
        ],
    }

    with open(args.output_dir / "reviewed_skill_candidates.json", "w", encoding="utf-8") as f:
        json.dump(reviewed_payload, f, ensure_ascii=False, indent=2)
    with open(args.output_dir / "accepted_skill_candidates.json", "w", encoding="utf-8") as f:
        json.dump(accepted_payload, f, ensure_ascii=False, indent=2)
    with open(args.output_dir / "skill_candidate_review_report.json", "w", encoding="utf-8") as f:
        json.dump(report_payload, f, ensure_ascii=False, indent=2)

    print(json.dumps(report_payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

