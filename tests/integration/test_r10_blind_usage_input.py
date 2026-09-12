"""Fixture tests for the blind-usage input builder (delivery-requirements rendering)."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]
import r10_blind_usage_input as builder  # noqa: E402


def make_package(tmp_path: Path, *, with_contract=True, contract_mutate=None,
                 row_mutate=None, drop_ref=None):
    pkg = tmp_path / 'pkg'
    (pkg / 'reference_files').mkdir(parents=True)
    (pkg / 'reference_files/ticket_fees.csv').write_text('Ticket_ID,Fee\nAB-1,10000\n', encoding='utf-8')
    (pkg / 'reference_files/rate_note.md').write_text('# Rate note\n', encoding='utf-8')
    row = {'task_id': 'anonymous_task', 'title': 'T',
           'prompt': 'Recompute the amounts. Cite the files. Preserve uncertainty.',
           'reference_files': ['reference_files/ticket_fees.csv', 'reference_files/rate_note.md'],
           'deliverable_files': ['deliverable_files/summary.docx',
                                 'deliverable_files/recalc.xlsx']}
    contract = {'contract_version': 'v3.deliverable_contract.1', 'case_id': 'c1',
                'deliverables': [
                    {'file_name': 'summary.docx', 'relative_path': 'deliverable_files/summary.docx',
                     'format': 'docx'},
                    {'file_name': 'recalc.xlsx', 'relative_path': 'deliverable_files/recalc.xlsx',
                     'format': 'xlsx'}],
                'allow_unlisted_deliverables': False}
    if contract_mutate:
        contract_mutate(contract)
    if with_contract:
        (pkg / 'deliverable_contract.json').write_text(json.dumps(contract, indent=1), encoding='utf-8')
    if row_mutate:
        row_mutate(row)
    (pkg / 'dataset_row.json').write_text(json.dumps(row, indent=1), encoding='utf-8')
    if drop_ref:
        (pkg / row['reference_files'][0]).unlink() if False else (pkg / 'reference_files/ticket_fees.csv').unlink()
    return pkg, row, contract


def test_build_blind_input_renders_contract_requirements(tmp_path):
    pkg, row, contract = make_package(tmp_path)
    target = tmp_path / 'blind'
    report = builder.build_blind_input(str(pkg), str(target))
    built = json.loads((target / 'dataset_row.json').read_text(encoding='utf-8'))
    assert set(built) == {'task_id', 'title', 'prompt', 'reference_files', 'deliverable_files'}
    assert built['prompt'].startswith(row['prompt'].rstrip())  # original prompt verbatim prefix
    for rel in ('deliverable_files/summary.docx', 'deliverable_files/recalc.xlsx'):
        assert f'`{rel}`' in built['prompt']
    assert 'exactly 2 file(s)' in built['prompt']
    assert 'No additional deliverables' in built['prompt']
    assert built['prompt'].index(row['prompt'].rstrip()) < built['prompt'].index('Submission requirements')
    assert report['status'] == 'built'


def test_final_candidate_prompt_captures_rendered_requirements(tmp_path):
    pytest.importorskip('bench_standalone')  # solver-assembly env (real-world-task); skip elsewhere
    pkg, row, contract = make_package(tmp_path)
    target = tmp_path / 'blind'
    builder.build_blind_input(str(pkg), str(target))
    final = builder.final_candidate_prompt(str(target / 'dataset_row.json'))
    assert 'deliverable_files/summary.docx' in final
    assert 'exactly 2 file(s)' in final
    assert 'No additional deliverables' in final
    assert 'ticket_fees.csv' in final  # reference basename rendered by the runner


def test_missing_contract_rejected(tmp_path):
    pkg, _, _ = make_package(tmp_path, with_contract=False)
    with pytest.raises(ValueError, match='deliverable_contract_missing'):
        builder.build_blind_input(str(pkg), str(tmp_path / 'blind'))


def test_invalid_contract_rejected(tmp_path):
    pkg, _, _ = make_package(tmp_path, contract_mutate=lambda c: c.update(
        {'deliverables': [{'file_name': 'x.txt', 'relative_path': 'wrong/x.txt', 'format': 'txt'}]}))
    with pytest.raises(ValueError, match='deliverable_contract_invalid'):
        builder.build_blind_input(str(pkg), str(tmp_path / 'blind'))


def test_row_contract_mismatch_rejected(tmp_path):
    pkg, _, _ = make_package(tmp_path, row_mutate=lambda r: r.update(
        {'deliverable_files': ['deliverable_files/other.docx']}))
    with pytest.raises(ValueError, match='dataset_row_deliverables_mismatch_contract'):
        builder.build_blind_input(str(pkg), str(tmp_path / 'blind'))


def test_missing_reference_rejected(tmp_path):
    pkg, _, _ = make_package(tmp_path)
    (pkg / 'reference_files/ticket_fees.csv').unlink()
    with pytest.raises(ValueError, match='reference_file_missing'):
        builder.build_blind_input(str(pkg), str(tmp_path / 'blind'))
