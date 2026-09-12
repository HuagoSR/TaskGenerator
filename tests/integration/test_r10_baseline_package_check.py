"""Fixture tests for the shared P/S package acceptance checker.

Covers both package shapes and the rejection cases; runs the existing offline
replayer on the P-shaped fixture. Pure local; no model calls.
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]
import r10_baseline_package_check as checker  # noqa: E402

REPLAY = ROOT / 'Test' / 'r10_calculation_replay.py'


def build_package(target: Path, shape: str, *, total_declared: int = 900) -> None:
    if target.exists():
        shutil.rmtree(target)
    (target / 'reference_files').mkdir(parents=True)
    (target / 'calculation_scripts').mkdir(parents=True)
    (target / 'reference_files/service_credits_q4.csv').write_text(
        'Ticket_ID,Monthly_Fee_USD\nSC-101,10000\nSC-102,8000\n', encoding='utf-8')
    (target / 'reference_files/rate_memo.md').write_text(
        '# Rate memo\nStandard credit rate: 5.00% of monthly fee.\n', encoding='utf-8')
    row = {
        'task_id': 'anonymous_task',
        'title': 'Verify the Q4 service-credit recalculation',
        'prompt': ('Recompute the proposed credits from the rate memo and the ticket table; '
                   'state what the visible inputs support and what remains unsupported.'),
        'reference_files': ['reference_files/service_credits_q4.csv',
                            'reference_files/rate_memo.md'],
        'deliverable_files': ['deliverable_files/credit_memo.docx',
                              'deliverable_files/recalc.xlsx'],
    }
    rubric = {'rubric_version': 'r10.atomic_rubric.1', 'task_id': 'anonymous_task', 'criteria': [
        {'criterion_id': 'independent_recalculation', 'decision_id': 'recalc', 'max_points': 2,
         'requirement': 'Recompute the credit total from the visible inputs.',
         'full_credit_condition': f'The workpaper shows each fee times the 5.00% rate and a total of {total_declared}, with the limitation that arithmetic agreement does not establish population completeness.',
         'weight_rationale': 'Substantive analytical result.',
         'requirement_basis': [{'path': 'reference_files/service_credits_q4.csv',
                                'locator': 'rows 2-3', 'explanation': 'Fees used.'}],
         'evidence_paths': ['reference_files/service_credits_q4.csv'],
         'applicability': 'Applies to the listed tickets.',
         'acceptable_alternatives': 'Equivalent layouts acceptable.',
         'tolerance': 'Monetary results within 0.01.',
         'verification': 'Recompute from the CSV and compare.'}]}
    contract = {'case_id': 'synthetic_case', 'deliverables': [
        {'file_name': 'credit_memo.docx', 'relative_path': 'deliverable_files/credit_memo.docx',
         'format': 'docx'},
        {'file_name': 'recalc.xlsx', 'relative_path': 'deliverable_files/recalc.xlsx',
         'format': 'xlsx'}]}
    if shape == 'P':
        row['rubric'] = rubric
        row['rubric_json'] = json.dumps(rubric, ensure_ascii=False)
    (target / 'dataset_row.json').write_text(json.dumps(row, indent=1), encoding='utf-8')
    (target / 'deliverable_contract.json').write_text(json.dumps(contract, indent=1), encoding='utf-8')
    rubric_name = 'atomic_rubric_v1.json' if shape == 'P' else 'new_rubric.json'
    (target / rubric_name).write_text(json.dumps(rubric, indent=1), encoding='utf-8')
    evidence = {'version': 2, 'executions': [
        {'execution_id': 'recalc_exec', 'script': 'recalc.py',
         'sources': [{'path': 'reference_files/service_credits_q4.csv',
                      'sha256': hashlib.sha256(
                          (target / 'reference_files/service_credits_q4.csv').read_bytes()).hexdigest()}],
         'anchors': [{'anchor_id': 'credit_total', 'value': total_declared}]}]}
    (target / 'calculation_evidence.json').write_text(json.dumps(evidence, indent=1), encoding='utf-8')
    (target / 'calculation_scripts/recalc.py').write_text(
        "import csv,json,argparse\np=argparse.ArgumentParser();p.add_argument('--inputs',required=True);a=p.parse_args()\n"
        "rows=list(csv.DictReader(open(a.inputs + '/reference_files/service_credits_q4.csv',encoding='utf-8')))\n"
        "total=sum(int(r['Monthly_Fee_USD']) for r in rows)*5//100\n"
        "print(json.dumps({'anchors': [{'anchor_id': 'credit_total', 'value': %d}]}))\n"
        % total_declared, encoding='utf-8')


@pytest.mark.parametrize('shape', ['P', 'S'])
def test_valid_package_passes_both_shapes(tmp_path, shape):
    pkg = tmp_path / f'pkg_{shape}'
    build_package(pkg, shape)
    outcome = checker.check_package(str(pkg))
    assert outcome['status'] == 'passed'
    assert outcome['rubric_file'] == ('atomic_rubric_v1.json' if shape == 'P' else 'new_rubric.json')


def test_rubric_mirror_mismatch_rejected(tmp_path):
    pkg = tmp_path / 'pkg_P'
    build_package(pkg, 'P')
    row = json.loads((pkg / 'dataset_row.json').read_text(encoding='utf-8'))
    row['rubric_json'] = json.dumps({**row['rubric'], 'criteria': []})
    (pkg / 'dataset_row.json').write_text(json.dumps(row, indent=1), encoding='utf-8')
    with pytest.raises(SystemExit):
        checker.check_package(str(pkg))


def test_replay_runs_on_p_shape_and_exposes_anchor_mismatch(tmp_path):
    pkg = tmp_path / 'pkg_P'
    build_package(pkg, 'P')
    run = subprocess.run([sys.executable, str(REPLAY), '--scripts', str(pkg / 'calculation_scripts'),
                          '--inputs', str(pkg), '--manifest', str(pkg / 'calculation_evidence.json'),
                          '--output', str(tmp_path / 'replay_out.json'), '--timeout-seconds', '30'],
                         capture_output=True, text=True)
    assert run.returncode == 0
    out = json.loads((tmp_path / 'replay_out.json').read_text(encoding='utf-8'))
    assert out['status'] in ('completed', 'executed')
    assert json.dumps(out).count('900') >= 1
    # anchor mismatch variant: declared 900, script computes 999
    build_package(pkg, 'P', total_declared=999)
    run = subprocess.run([sys.executable, str(REPLAY), '--scripts', str(pkg / 'calculation_scripts'),
                          '--inputs', str(pkg), '--manifest', str(pkg / 'calculation_evidence.json'),
                          '--output', str(tmp_path / 'replay_bad.json'), '--timeout-seconds', '30'],
                         capture_output=True, text=True)
    bad = json.loads((tmp_path / 'replay_bad.json').read_text(encoding='utf-8'))
    produced = json.dumps(bad)
    assert '999' in produced


@pytest.mark.parametrize('mutation,code', [
    (lambda p: (p / 'reference_files/query.sqlx').write_text('SELECT 1;', encoding='utf-8'),
     'unsupported_output_type'),
    (lambda p: (p / 'reference_files/empty.md').write_text('', encoding='utf-8'), 'empty_output'),
    (lambda p: (p / 'hidden').mkdir() or (p / 'hidden/process.md').write_text('x', encoding='utf-8'),
     'teacher_artifact_present'),
    (lambda p: (p / 'deliverable_contract.json').unlink(), 'missing_required_file'),
    (lambda p: (p / 'reference_files/rate_memo.md').unlink(), 'dataset_row_reference_missing'),
])
def test_rejections_locate_issues(tmp_path, mutation, code):
    pkg = tmp_path / 'pkg_S'
    build_package(pkg, 'S')
    mutation(pkg)
    with pytest.raises(SystemExit):
        checker.check_package(str(pkg))


def test_rejection_message_contains_code(tmp_path):
    pkg = tmp_path / 'pkg_S'
    build_package(pkg, 'S')
    (pkg / 'reference_files/query.sqlx').write_text('SELECT 1;', encoding='utf-8')
    import io
    import contextlib
    buf = io.StringIO()
    with pytest.raises(SystemExit), contextlib.redirect_stdout(buf):
        checker.check_package(str(pkg))
    assert 'unsupported_output_type:reference_files/query.sqlx' in buf.getvalue()
