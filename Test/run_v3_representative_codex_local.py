from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_codex_local_solver import (  # noqa: E402
    CodexLocalRunner,
    CodexLocalTooling,
    compile_standing_receipt,
)
from task_generator.v3_representative_codex_local import (  # noqa: E402
    compile_representative_codex_scope,
)


DEFAULT_TOOLING_ROOT = (
    ROOT
    / "artifacts"
    / "pipeline_reconstruction"
    / "codex_local_tooling"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the 24-task representative pilot with local Codex."
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=("freeze-cli", "compile-scope", "compile-receipt", "execute"),
    )
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--tooling-root", type=Path, default=DEFAULT_TOOLING_ROOT)
    parser.add_argument("--package-readiness", type=Path)
    parser.add_argument("--reality-scope", type=Path)
    parser.add_argument("--reality-result", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--codex-home", type=Path, default=Path.home() / ".codex")
    parser.add_argument(
        "--python-executable",
        type=Path,
        default=Path(sys.executable),
    )
    args = parser.parse_args()
    tooling = CodexLocalTooling(args.tooling_root)

    if args.action == "freeze-cli":
        result = tooling.freeze_identity()
    elif args.action == "compile-scope":
        if not all(
            (
                args.package_readiness,
                args.reality_scope,
                args.reality_result,
                args.parity_report,
            )
        ):
            parser.error(
                "compile-scope requires package-readiness, reality-scope, "
                "reality-result and parity-report"
            )
        scope, path, digest = compile_representative_codex_scope(
            campaign_root=args.campaign_root,
            package_readiness_path=args.package_readiness,
            reality_scope_path=args.reality_scope,
            reality_result_path=args.reality_result,
            parity_report_path=args.parity_report,
            cli_identity=tooling.freeze_identity(),
            repository_root=ROOT,
            output_root=args.output_root,
        )
        result = {
            "scope": scope.model_dump(mode="json"),
            "scope_path": str(path),
            "scope_sha256": digest,
            "external_model_calls_made": False,
        }
    elif args.action == "compile-receipt":
        if not args.scope:
            parser.error("compile-receipt requires --scope")
        receipt, path = compile_standing_receipt(
            scope_path=args.scope,
            output_root=args.output_root,
        )
        result = {
            "receipt": receipt.model_dump(mode="json"),
            "receipt_path": str(path),
            "external_model_calls_made": False,
        }
    else:
        if not args.scope or not args.receipt:
            parser.error("execute requires --scope and --receipt")
        manifest, path = CodexLocalRunner(
            scope_path=args.scope,
            receipt_path=args.receipt,
            campaign_root=args.campaign_root,
            output_root=args.output_root / "execution",
            codex_home=args.codex_home,
            python_executable=args.python_executable,
        ).run_solver()
        result = {
            "status": manifest.status,
            "manifest_path": str(path),
            "first_failure": manifest.first_failure,
        }
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
