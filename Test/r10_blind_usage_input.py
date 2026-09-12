"""Blind-usage input builder for independently verifying S1-generated task packages.

Builds a solver-visible input (dataset_row + reference_files) from a generated
package, mechanically rendering the submission requirements from the AUTHORITATIVE
deliverable contract so the solver receives exact paths, formats, count and the
closed-deliverable rule. Teacher-side artifacts (rubric, calculation evidence,
scripts, author notes) are never copied. The original prompt text is preserved
verbatim; only the mechanically rendered submission section is appended.

Final assembled candidate input (the exact text a solver runner would send) can be
captured with final_candidate_prompt() using the existing bench_standalone
prompt builder — offline, no model call.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]

from task_generator.core import deliverable_contract as dc  # noqa: E402
from task_generator.production import agent_factory as f  # noqa: E402

TEACHER_MARKERS = ('"rubric"', 'rubric_json', 'full_credit_condition', 'anchor',
                   'calculation_evidence', 'observation', 'weight_rationale')


def render_submission_section(contract: dict) -> str:
    """Mechanically render candidate submission requirements from the authoritative contract."""
    validated = dc.DeliverableContractV1.model_validate(contract)
    lines = ['Submission requirements (from the authoritative deliverable contract):',
             f'- Submit exactly {len(validated.deliverables)} file(s), in this order:']
    for d in validated.deliverables:
        lines.append(f'  1. `{d.relative_path}` (format: {d.format}, creation mode: {d.creation_mode})')
    if not validated.allow_unlisted_deliverables:
        lines.append('- No additional deliverables beyond this closed set are permitted.')
    return '\n'.join(lines)


def build_blind_input(package_dir: str, target_dir: str) -> dict:
    """Build the blind solver input from a generated package.

    Returns a report dict. Raises ValueError with locating codes on: missing or
    invalid contract, dataset_row/contract deliverable mismatch, teacher artifacts,
    missing reference files.
    """
    pkg = Path(package_dir)
    target = Path(target_dir)
    contract_path = pkg / 'deliverable_contract.json'
    if not contract_path.is_file():
        raise ValueError('deliverable_contract_missing:' + str(contract_path))
    try:
        contract = json.loads(contract_path.read_text(encoding='utf-8'))
        dc.DeliverableContractV1.model_validate(contract)
    except Exception as error:
        raise ValueError('deliverable_contract_invalid:' + str(error)) from error

    row_path = pkg / 'dataset_row.json'
    if not row_path.is_file():
        raise ValueError('dataset_row_missing:' + str(row_path))
    row = json.loads(row_path.read_text(encoding='utf-8'))
    required = {'task_id', 'title', 'prompt', 'reference_files', 'deliverable_files'}
    missing = required - set(row)
    if missing:
        raise ValueError('dataset_row_missing_keys:' + ','.join(sorted(missing)))
    contract_paths = sorted(d['relative_path'] for d in contract['deliverables'])
    if sorted(row['deliverable_files']) != contract_paths:
        raise ValueError('dataset_row_deliverables_mismatch_contract:' + str(contract_paths))

    if target.exists():
        shutil.rmtree(target)
    (target / 'reference_files').mkdir(parents=True)
    for rel in row['reference_files']:
        src = pkg / rel
        if not src.is_file():
            raise ValueError('reference_file_missing:' + rel)
        (target / rel).write_bytes(src.read_bytes())

    submission = render_submission_section(contract)
    for marker in TEACHER_MARKERS:
        if marker.lower() in submission.lower():
            raise ValueError('teacher_marker_in_submission:' + marker)
    prompt = row['prompt'].rstrip() + '\n\n' + submission + '\n'
    blind_row = {k: row[k] for k in ('task_id', 'title', 'prompt', 'reference_files',
                                     'deliverable_files')}
    blind_row['prompt'] = prompt
    (target / 'dataset_row.json').write_text(
        json.dumps(blind_row, ensure_ascii=False, indent=1), encoding='utf-8')

    return {'status': 'built', 'target': str(target), 'submission_section': submission,
            'reference_files': sorted(
                f.relative_to(target).as_posix() for f in (target / 'reference_files').rglob('*')
                if f.is_file())}


def final_candidate_prompt(dataset_row_path: str) -> str:
    """Capture the FINAL assembled candidate prompt via the actual solver prompt builder."""
    from bench_standalone.prompt import build_task_prompt  # noqa: E402
    from stirrup.constants import FINISH_TOOL_NAME  # noqa: E402
    row = json.loads(Path(dataset_row_path).read_text(encoding='utf-8'))
    refs = row['reference_files']
    sample = {'task_id': row['task_id'], 'prompt': row['prompt'],
              'reference_files': [str(Path(ROOT / 'nonexistent' / r)) for r in refs]}
    return build_task_prompt(sample, finish_tool_name=FINISH_TOOL_NAME)


def main(argv) -> None:
    if len(argv) != 3:
        raise SystemExit('usage: r10_blind_usage_input.py <package_dir> <target_dir>')
    report = build_blind_input(argv[1], argv[2])
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main(sys.argv)
