"""Tests for the launch-identity gate: correct case passes, wrong identity rejected."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]
import r10_expected_task_gate as gate  # noqa: E402


def make_input(tmp_path: Path, *, task_id='anonymous_task', prompt='Solve the task.',
               refs=None, n_cases=1):
    input_dir = tmp_path / 'input'
    input_dir.mkdir(exist_ok=True)
    for i in range(n_cases):
        case = input_dir / f'Task_{i}'
        case.mkdir(exist_ok=True)
        row = {'task_id': task_id, 'title': 'T', 'prompt': prompt,
               'reference_files': refs or [], 'deliverable_files': []}
        (case / 'dataset_row.json').write_text(json.dumps(row, indent=1), encoding='utf-8')
        for r in (refs or []):
            (case / r).parent.mkdir(parents=True, exist_ok=True)
            (case / r).write_text('data', encoding='utf-8')
    return input_dir


def make_expected(task_id='anonymous_task', prompt='Solve the task.', refs=None):
    return {'task_id': task_id,
            'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
            'reference_files': sorted(refs or [])}


def test_correct_case_passes(tmp_path):
    input_dir = make_input(tmp_path)
    result = gate.verify_launch_identity(str(input_dir), make_expected())
    assert result['status'] == 'verified'
    assert result['task_id'] == 'anonymous_task'


def test_wrong_task_id_rejected(tmp_path):
    input_dir = make_input(tmp_path, task_id='wrong_task')
    with pytest.raises(ValueError, match='task_identity_mismatch'):
        gate.verify_launch_identity(str(input_dir), make_expected())


def test_wrong_prompt_rejected(tmp_path):
    input_dir = make_input(tmp_path, prompt='Different prompt entirely.')
    with pytest.raises(ValueError, match='task_identity_mismatch'):
        gate.verify_launch_identity(str(input_dir), make_expected())


def test_zero_cases_rejected(tmp_path):
    input_dir = tmp_path / 'empty'
    input_dir.mkdir()
    with pytest.raises(ValueError, match='expected exactly 1 test case, found 0'):
        gate.verify_launch_identity(str(input_dir), make_expected())


def test_multiple_cases_rejected(tmp_path):
    input_dir = make_input(tmp_path, n_cases=2)
    with pytest.raises(ValueError, match='expected exactly 1 test case, found 2'):
        gate.verify_launch_identity(str(input_dir), make_expected())
