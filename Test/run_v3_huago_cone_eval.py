from __future__ import annotations

import argparse
import json
from pathlib import Path

from task_generator.v3_huago_cone_eval import R9NativeSolverRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one native R9 solver stack on Huago-cone.")
    parser.add_argument("--action", choices=["probe", "solve"], required=True)
    parser.add_argument("--stack", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--generation-result", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    runner = R9NativeSolverRunner(
        stack_id=args.stack,
        output_root=args.output_root,
        timeout_seconds=args.timeout_seconds,
    )
    if args.action == "probe":
        result = runner.public_probe()
    else:
        if args.generation_result is None:
            parser.error("--generation-result is required for solve")
        result = runner.solve(generation_result_path=args.generation_result)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
