import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase16_clean_eval_gate import build_phase16_clean_eval_gate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or validate the Phase 16.7 two-case clean eval gate.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts" / "phase16")
    parser.add_argument("--external-eval-results", type=Path, default=None)
    parser.add_argument("--scope-id", default="two_case")
    parser.add_argument("--case-ids", nargs="+", default=None)
    args = parser.parse_args()

    result = build_phase16_clean_eval_gate(
        output_root=args.output_root,
        external_eval_results_path=str(args.external_eval_results) if args.external_eval_results else None,
        scope_id=args.scope_id,
        case_ids=args.case_ids,
    )
    acceptance = result["import_report"].get("clean_eval_acceptance") or {}
    print(
        json.dumps(
            {
                "runbook": next(value for key, value in result["outputs"].items() if key.endswith("_runbook")),
                "import_report": next(value for key, value in result["outputs"].items() if key.endswith("_import_report")),
                "clean_eval_proven": acceptance.get("clean_eval_proven"),
                "blocking_reasons": acceptance.get("blocking_reasons"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
