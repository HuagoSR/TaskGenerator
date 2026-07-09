import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_phase15_permitted_eval_bundle import (  # noqa: E402
    Phase15PermittedEvalBundleBuilder,
    Phase15PermittedEvalBundleRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_OUTPUT = PHASE15 / "permitted_eval_bundle"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a portable Phase 15 first-pair eval bundle for a permitted environment.")
    parser.add_argument("--runbook-path", type=Path, default=PHASE15 / "external_eval_runbook" / "phase15_external_eval_runbook.json")
    parser.add_argument("--results-template-path", type=Path, default=PHASE15 / "external_eval_import" / "phase15_external_eval_results_template.json")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bundle-name", default="phase15_first_pair_gpt4omini_permitted_eval_bundle")
    parser.add_argument("--python-executable-hint", default="D:\\miniconda3\\envs\\real-world-task\\python.exe")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()

    request = Phase15PermittedEvalBundleRequest(
        runbook_path=str(args.runbook_path),
        results_template_path=str(args.results_template_path),
        output_dir=str(args.output_dir),
        bundle_name=args.bundle_name,
        python_executable_hint=args.python_executable_hint,
        create_zip=not args.no_zip,
    )
    report = Phase15PermittedEvalBundleBuilder().build(request)
    print(
        json.dumps(
            {
                "bundle_status": report.bundle_status,
                "item_count": report.item_count,
                "bundle_dir": report.bundle_dir,
                "zip_path": report.zip_path,
                "blocking_reasons": report.blocking_reasons,
                "report_path": str(Path(args.output_dir) / "phase15_permitted_eval_bundle_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
