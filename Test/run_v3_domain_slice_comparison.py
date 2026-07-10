import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_domain_profile import DEFAULT_DOMAIN_PROFILE_PATH, load_domain_profile  # noqa: E402
from task_generator.v3_domain_slice_comparison import build_domain_slice_comparison  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare finance control and warehouse inventory vertical-slice runs.")
    parser.add_argument("--finance-run-root", type=Path, required=True)
    parser.add_argument("--warehouse-run-root", type=Path, required=True)
    parser.add_argument("--contamination-ledger-path", type=Path, required=True)
    parser.add_argument("--domain-profile-path", type=Path, default=DEFAULT_DOMAIN_PROFILE_PATH)
    parser.add_argument("--output-path", type=Path, required=True)
    args = parser.parse_args()
    report = build_domain_slice_comparison(
        args.finance_run_root,
        args.warehouse_run_root,
        load_domain_profile("warehouse_inventory", args.domain_profile_path),
        args.contamination_ledger_path,
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_path": str(args.output_path), "decision": report["decision"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
