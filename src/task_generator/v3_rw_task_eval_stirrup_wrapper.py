from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from pathlib import Path


MODEL_MAX_TOKENS_OVERRIDES: dict[str, int] = {
    "gpt-4o-mini": 16384,
}

DEFAULT_MAX_TOKENS = 64000


def resolve_stirrup_max_tokens(model: str) -> int:
    return MODEL_MAX_TOKENS_OVERRIDES.get(model, DEFAULT_MAX_TOKENS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for rw-task bench_standalone.stirrup_batch with model-aware max token overrides."
    )
    parser.add_argument("input_path")
    parser.add_argument("--output", required=True)
    parser.add_argument("-w", "--workers", type=int, default=1)
    parser.add_argument("--model", required=True)
    parser.add_argument("--e2b-template", default="rw-task-sandbox:stable")
    parser.add_argument("--max-tokens", type=int, default=None)
    args = parser.parse_args()

    rw_task_root = Path(r"E:\THU\2026Spring\SRT\rw-task")
    if str(rw_task_root) not in sys.path:
        sys.path.insert(0, str(rw_task_root))

    from bench_standalone import stirrup_batch as stirrup_batch_module

    stirrup_batch_module.MAX_TOKENS = args.max_tokens or resolve_stirrup_max_tokens(args.model)
    input_path = Path(args.input_path).resolve()
    output_batch_dir = Path(args.output).resolve()
    output_batch_dir.mkdir(parents=True, exist_ok=True)
    log_dir = output_batch_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    test_cases = stirrup_batch_module.find_test_cases(input_path)
    if not test_cases:
        raise SystemExit(f"Error: no test cases found in {input_path}")

    print(f"[Wrapper] Output directory : {output_batch_dir}")
    print(f"Input directory  : {input_path}")
    print(f"Test cases found : {len(test_cases)}")
    print(f"Workers          : {args.workers}")
    print(f"Model            : {args.model}")
    print(f"E2B template     : {args.e2b_template}")
    print()

    succeeded = 0
    failed = 0
    skipped = 0
    for case_dir in test_cases:
        with open(case_dir / stirrup_batch_module.DATASET_ROW_FILENAME, encoding="utf-8") as f:
            task_id = json.load(f)["task_id"]
        safe = stirrup_batch_module._safe_name(case_dir.name)
        output_run_dir = output_batch_dir / f"run_{safe}"
        log_file = log_dir / f"{safe}.txt"
        if stirrup_batch_module.is_completed(output_run_dir):
            print(f"  [SKIP] {task_id}  ({case_dir.name})")
            skipped += 1
            continue
        ok = _run_single_case(
            stirrup_batch_module=stirrup_batch_module,
            case_dir=case_dir,
            output_run_dir=output_run_dir,
            log_file=log_file,
            model=args.model,
            e2b_template=args.e2b_template,
        )
        if ok:
            succeeded += 1
            print(f"  [OK  ] {task_id}")
        else:
            failed += 1
            print(f"  [FAIL] {task_id}  (see logs/{log_file.name})")

    print()
    print("=== Batch Run Complete ===")
    print(f"Total    : {len(test_cases)}")
    print(f"Skipped  : {skipped}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed   : {failed}")
    print(f"Output   : {output_batch_dir}")
    print(f"Logs     : {log_dir}")


def _run_single_case(
    stirrup_batch_module,
    case_dir: Path,
    output_run_dir: Path,
    log_file: Path,
    model: str,
    e2b_template: str,
) -> bool:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w", encoding="utf-8", buffering=1) as log:
        original_stdout, original_stderr = sys.stdout, sys.stderr
        sys.stdout = log
        sys.stderr = log
        try:
            asyncio.run(stirrup_batch_module._run_async(case_dir, output_run_dir, model, e2b_template))
            return True
        except Exception as exc:
            print(f"\n[ERROR] {exc}")
            traceback.print_exc()
            return False
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


if __name__ == "__main__":
    main()
