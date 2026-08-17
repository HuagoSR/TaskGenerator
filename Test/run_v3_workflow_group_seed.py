from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_workflow_group_seed import WorkflowGroupSeedCompiler  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile a report-only single-workflow Pipeline B seed."
    )
    parser.add_argument("--registry-path", type=Path, required=True)
    parser.add_argument("--readiness-report", type=Path, required=True)
    parser.add_argument("--provenance-ledger", type=Path, required=True)
    parser.add_argument("--source-group-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    report = WorkflowGroupSeedCompiler().compile(
        registry_path=args.registry_path,
        readiness_report_path=args.readiness_report,
        provenance_ledger_path=args.provenance_ledger,
        source_group_id=args.source_group_id,
        output_dir=args.output_dir,
    )
    report_path = args.output_dir / "workflow_group_seed_compile_report.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": report.decision,
                "source_group_id": report.source_group_id,
                "admitted_skill_count": len(report.admitted_skill_ids),
                "seed_report_path": report.seed_report_path,
                "report_path": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
