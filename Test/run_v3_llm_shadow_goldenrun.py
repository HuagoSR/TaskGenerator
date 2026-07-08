import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_llm_shadow_common import LLMShadowBuilder, LLMShadowRequest  # noqa: E402


DEFAULT_RELEASE = ROOT / "artifacts" / "releases" / "finance_audit_mvp_v0_1_pilot8_diversity_final_reviewed_strict" / "release_manifest.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "phase14" / "llm_shadow"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare LLM GoldenRun shadow packages for Phase 14.7.")
    parser.add_argument("--release-manifest-path", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--task-limit", type=int, default=5)
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--model", default="not_run")
    args = parser.parse_args()
    request = LLMShadowRequest(
        release_manifest_path=str(args.release_manifest_path),
        output_dir=str(args.output_dir),
        shadow_kind="goldenrun",
        task_limit=args.task_limit,
        task_ids=args.task_id,
        model=args.model,
    )
    report = LLMShadowBuilder().build(request)
    print(json.dumps({"shadow_kind": report.shadow_kind, "selected_task_count": report.selected_task_count, "prepared_count": report.prepared_count, "awaiting_llm_output_count": report.awaiting_llm_output_count}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
