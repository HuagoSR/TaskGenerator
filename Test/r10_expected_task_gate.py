"""Launch-identity gate: verify the runner-discovered test case matches the frozen
expected task identity before any solver launch. Minimal wrapper; does not modify
bench_standalone behavior."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_ROW_FILENAME = 'dataset_row.json'


def discover_test_cases(input_path: Path) -> list[Path]:
    """Mirror bench_standalone.stirrup_batch.find_test_cases discovery logic."""
    return sorted(
        d for d in Path(input_path).iterdir()
        if d.is_dir() and (d / DATASET_ROW_FILENAME).exists()
    )


def verify_launch_identity(input_dir: str, expected: dict) -> dict:
    """Verify the discovered test case matches the expected task identity.

    expected: {'task_id': str, 'prompt_sha256': str, 'reference_files': sorted list}
    Raises ValueError with locating detail on any mismatch.
    """
    input_path = Path(input_dir)
    cases = discover_test_cases(input_path)
    if len(cases) != 1:
        raise ValueError(
            f'task_identity_error: expected exactly 1 test case, found {len(cases)}: '
            + str([c.name for c in cases]))
    case = cases[0]
    row_path = case / DATASET_ROW_FILENAME
    row = json.loads(row_path.read_text(encoding='utf-8'))

    if row.get('task_id') != expected.get('task_id'):
        raise ValueError(
            f'task_identity_mismatch: task_id {row.get("task_id")!r} != expected {expected.get("task_id")!r}')

    prompt = row.get('prompt', '')
    prompt_sha = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    if prompt_sha != expected.get('prompt_sha256'):
        raise ValueError(
            f'task_identity_mismatch: prompt sha256 {prompt_sha[:16]} != expected {expected.get("prompt_sha256", "")[:16]}')

    refs = sorted(row.get('reference_files', []))
    expected_refs = sorted(expected.get('reference_files', []))
    if refs != expected_refs:
        raise ValueError(
            f'task_identity_mismatch: reference_files {refs} != expected {expected_refs}')

    for ref in refs:
        ref_path = case / ref
        if not ref_path.is_file():
            raise ValueError(f'task_identity_mismatch: reference file missing: {ref}')

    return {
        'status': 'verified',
        'case_dir': case.name,
        'task_id': row['task_id'],
        'prompt_sha256': prompt_sha,
        'reference_files': refs,
        'deliverable_files': sorted(row.get('deliverable_files', [])),
    }


if __name__ == '__main__':
    input_dir, freeze_path, position_key = sys.argv[1], sys.argv[2], sys.argv[3]
    freeze = json.loads(Path(freeze_path).read_text(encoding='utf-8'))
    row = json.loads(
        next(Path(freeze_path).parent.rglob('*'))
        if False else
        json.loads((Path(freeze_path).parent / 'scope_prompt_sha.json').read_text(encoding='utf-8'))
    ) if False else None
    # CLI: read expected from freeze file's positions or explicit JSON
    print(json.dumps(verify_launch_identity(input_dir, json.loads(sys.argv[4])), ensure_ascii=False, indent=1))
