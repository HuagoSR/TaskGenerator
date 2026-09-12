"""Shared final-package acceptance checker for the P/S method comparison.

One acceptance gate for BOTH the multi-stage pipeline package (P: rubric exported
as atomic_rubric_v1.json with dataset_row rubric/rubric_json mirrors) and the
single-author baseline package (S: new_rubric.json, minimal dataset_row).
Composes existing validators only; weakens no production rule.

Usage: python r10_baseline_package_check.py <package_dir>
Prints a JSON report; exit 0 = passed, exit 1 = rejected (code locates the issue).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]

from task_generator.production import agent_factory as f  # noqa: E402
from task_generator.production import task_method_pilot as m  # noqa: E402

ALLOWED = {'.docx', '.xlsx', '.pdf', '.csv', '.txt', '.md', '.json', '.sha256', '.py', '.sql'}
FORBIDDEN_DIRS = ('hidden', 'supervision', 'basis', 'drafts', 'snapshots')
FORBIDDEN_FILES = ('edit_record.json', 'consultation.json', 'basis_draft.json',
                   'supervision.json', 'design_intent.json', 'review.json')
REQUIRED_TOP = ('dataset_row.json', 'deliverable_contract.json', 'calculation_evidence.json')
RUBRIC_ALIASES = ('new_rubric.json', 'atomic_rubric_v1.json')
REQUIRED_DIRS = ('reference_files', 'calculation_scripts')


def fail(code, detail):
    print(json.dumps({'status': 'rejected', 'code': code, 'detail': str(detail)[:400]},
                     ensure_ascii=False))
    raise SystemExit(1)


def check_package(package_dir: str) -> dict:
    pkg = Path(package_dir)
    if not pkg.is_dir():
        fail('package_missing', str(pkg))

    # 1) file gate (same extension/empty rules as the production draft gate)
    for path in sorted(pkg.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(pkg).as_posix()
        if path.suffix.lower() not in ALLOWED:
            fail('unsupported_output_type:' + rel, rel)
        if not path.stat().st_size:
            fail('empty_output:' + rel, rel)
        if path.suffix.lower() == '.docx':
            from docx import Document
            Document(path)
        elif path.suffix.lower() == '.xlsx':
            import openpyxl
            openpyxl.load_workbook(path).close()
        elif path.suffix.lower() == '.sql':
            try:
                path.read_bytes().decode('utf-8-sig')
            except UnicodeDecodeError as error:
                fail('invalid_text_encoding:' + rel, str(error))
        else:
            path.read_text(encoding='utf-8')

    # 2) required layout with rubric alias
    for name in REQUIRED_TOP:
        if not (pkg / name).is_file():
            fail('missing_required_file:' + name, name)
    for name in REQUIRED_DIRS:
        if not (pkg / name).is_dir():
            fail('missing_required_dir:' + name, name)
    rubric_files = [name for name in RUBRIC_ALIASES if (pkg / name).is_file()]
    if len(rubric_files) != 1:
        fail('rubric_file_missing_or_ambiguous', rubric_files)
    rubric_name = rubric_files[0]

    # 3) isolation: no teacher-side artifacts anywhere
    for path in sorted(pkg.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(pkg).as_posix()
        parts = PurePosixPath(rel).parts
        if any(part in FORBIDDEN_DIRS for part in parts):
            fail('teacher_artifact_present:' + rel, rel)
        if rel in FORBIDDEN_FILES:
            fail('teacher_artifact_present:' + rel, rel)

    # 4) dataset_row: required keys; rubric mirrors allowed only if identical to the rubric file
    row = json.loads((pkg / 'dataset_row.json').read_text(encoding='utf-8'))
    required_keys = {'task_id', 'title', 'prompt', 'reference_files', 'deliverable_files'}
    missing_keys = required_keys - set(row)
    if missing_keys:
        fail('dataset_row_missing_keys', sorted(missing_keys))
    rubric_content = json.loads((pkg / rubric_name).read_text(encoding='utf-8'))
    if 'rubric_json' in row:
        try:
            mirrored = json.loads(row['rubric_json']) if isinstance(row['rubric_json'], str) \
                else row['rubric_json']
        except json.JSONDecodeError as error:
            fail('dataset_row_rubric_json_unparseable', str(error))
        if mirrored != rubric_content:
            fail('dataset_row_rubric_json_mismatch', rubric_name)
    if 'rubric' in row and row['rubric'] != rubric_content:
        fail('dataset_row_rubric_mismatch', rubric_name)
    for rel in row['reference_files']:
        if not PurePosixPath(rel).parts or PurePosixPath(rel).parts[0] != 'reference_files':
            fail('dataset_row_reference_not_in_reference_files:' + rel, rel)
        if not (pkg / rel).is_file():
            fail('dataset_row_reference_missing:' + rel, rel)

    # 5) atomic rubric schema (existing validator) on the aliased file
    m.TaskSpecificAtomicRubricV1.model_validate(rubric_content)

    # 6) deliverable contract schema (existing validator) + dataset_row consistency
    from task_generator.core import deliverable_contract as dc
    contract = json.loads((pkg / 'deliverable_contract.json').read_text(encoding='utf-8'))
    dc.DeliverableContractV1.model_validate(contract)
    contract_paths = sorted(d['relative_path'] for d in contract['deliverables'])
    if sorted(row['deliverable_files']) != contract_paths:
        fail('dataset_row_deliverables_mismatch_contract', contract_paths)

    # 7) rubric requirement_basis paths must resolve inside the package
    package_files = set(f.files(pkg))
    for index, criterion in enumerate(rubric_content['criteria']):
        for basis in criterion.get('requirement_basis', []):
            path = basis.get('path', '')
            ok = path in package_files or (path == 'candidate_task.md' and row.get('prompt'))
            if not ok:
                fail(f'rubric_basis_unresolved[{criterion["criterion_id"]}:{index}]', path)

    return {'status': 'passed', 'rubric_file': rubric_name, 'files': sorted(package_files)}


if __name__ == '__main__':
    print(json.dumps(check_package(sys.argv[1]), ensure_ascii=False, indent=1))
