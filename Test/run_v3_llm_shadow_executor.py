from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_llm_shadow_executor import LLMShadowExecuteRequest, LLMShadowExecutor  # noqa: E402


DEFAULT_SHADOW_DIR = ROOT / "artifacts" / "phase14" / "llm_shadow"
DEFAULT_ENV = ROOT.parent / "rw-task" / ".env"


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute Phase 14 LLM shadow packages with an approved external model.")
    parser.add_argument("--llm-shadow-dir", type=Path, default=DEFAULT_SHADOW_DIR)
    parser.add_argument("--shadow-kind", default="all", choices=["all", "goldenrun", "rubric", "realism_critic", "reference_narrative"])
    parser.add_argument("--model", default="gemini-3-pro-preview")
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--max-tokens", type=int, default=3000)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--task-limit", type=int, default=0)
    parser.add_argument("--overwrite-completed", action="store_true")
    args = parser.parse_args()

    request = LLMShadowExecuteRequest(
        llm_shadow_dir=str(args.llm_shadow_dir),
        shadow_kind=args.shadow_kind,
        model=args.model,
        env_path=str(args.env_path),
        timeout_seconds=args.timeout_seconds,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        task_limit=args.task_limit,
        overwrite_completed=args.overwrite_completed,
    )
    report = LLMShadowExecutor().run(request)
    print(
        json.dumps(
            {
                "attempted_count": report.attempted_count,
                "completed_count": report.completed_count,
                "failed_count": report.failed_count,
                "report_path": str(Path(args.llm_shadow_dir) / "llm_shadow_execute_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
