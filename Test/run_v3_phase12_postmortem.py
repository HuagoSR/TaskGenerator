import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase12_postmortem import Phase12PostmortemBuilder  # noqa: E402


SCRATCH = ROOT / "artifacts" / "pipeline_b" / "scratch"
DEFAULT_DASHBOARD = SCRATCH / "phase12_hardening_phase1234_smoke_v2" / "phase12_global_dashboard" / "phase12_global_dashboard_report.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "historical_phase_runs" / "phase12" / "postmortem"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 12 postmortem report and handoff.")
    parser.add_argument("--dashboard-report", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    report = Phase12PostmortemBuilder().build(
        dashboard_report_path=args.dashboard_report,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "phase12_postmortem_report_path": str(args.output_dir / "phase12_postmortem_report.json"),
                "decision": report.decision,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
