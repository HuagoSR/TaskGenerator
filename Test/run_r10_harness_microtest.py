"""Three authorized native turns on synthetic inputs; never a production world."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import time

import run_r10_agent_factory_pilot as runner
from task_generator.production import agent_factory as f


def prepare(root, readiness):
    if root.exists():
        raise FileExistsError('microtest_exists')
    record = f.read(readiness)
    if record.get('tests_passed') is not True or not record.get('commands'):
        raise ValueError('offline_readiness_required')
    from openpyxl import Workbook
    public = root.parent / (root.name + '_synthetic_inputs')
    public.mkdir()
    f.write(public / 'public_context.json', {'kind': 'synthetic_tool_fixture', 'role': 'analyst',
                                            'instruction': 'Use supplied fixture only; no occupational validity claim.'})
    f.write(public / 'professional_rules.json', {'rules': []})
    f.write(public / 'sources.json', {'kind': 'synthetic_not_public_occupational_sources'})
    candidate = public / 'fixture_candidate'
    candidate.mkdir()
    book = Workbook()
    sheet = book.active
    sheet.title = 'Items'
    for row in [('item', 'quantity', 'unit_price'), ('A', 2, 10), ('B', 3, 5)]:
        sheet.append(row)
    book.save(candidate / 'items.xlsx')
    (candidate / 'instructions.txt').write_text(
        'Synthetic fixture: report the sum of quantity times unit_price across all Items rows. '
        'State the calculation and unit (fictional units); submit memo.txt. No other analysis is required.\n', encoding='utf-8')
    scope = runner.prepare(root, protocol='task_factory_harness_v1', synthetic_public=public,
                           spec={'id': 'synthetic', 'seed': 'synthetic_tool_fixture', 'domain': 'synthetic'},
                           harness_options={'purpose': 'tool_microtest', 'max_launches': 3,
                               'production_launches': 3, 'seconds': 1800, 'per_launch_seconds': 600,
                               'terminal_reserve_seconds': 0,
                               'authorization': 'Three native tool microtest turns, 30 minutes total, no production or grading.'})
    world = root / 'fixture/world'
    shutil.copytree(candidate, world / 'candidate')
    state = f.read(root / 'receipt.json')
    state['current']['world'] = {'id': f.fingerprint(f.files(world)), 'role': 'world', 'parents': {},
                                 'path': 'fixture/world', 'hashes': f.files(world), 'synthetic_preseed': True}
    inputs = root / 'fixture/mine_inputs'
    runner.build_inputs(root, state, 'mine', inputs, protocol=scope['protocol'])
    mine = root / 'fixture/mine'
    basis = [{'path': 'reference_files/instructions.txt', 'locator': 'line 1', 'explanation': 'Synthetic visible assignment'}]
    f.write(mine / 'task.json', {'natural_task': True, 'rationale': 'Synthetic transport fixture; not research production',
        'title': 'Synthetic arithmetic fixture', 'prompt': (candidate / 'instructions.txt').read_text(encoding='utf-8'),
        'requirements': [{'id': 'r1', 'requirement': 'Report and explain total', 'expected_work_product': 'memo', 'basis': basis}],
        'deliverables': [{'file_name': 'memo.txt', 'relative_path': 'deliverable_files/memo.txt', 'format': 'txt'}]})
    f.write(mine / 'design_intent.json', {'occupational_use': 'Synthetic fixture only', 'analysis_points': ['Arithmetic'],
        'likely_difficulties': ['Tool contracts'], 'evidence': basis})
    state['current']['mine'] = {'id': f.fingerprint(f.files(mine)), 'role': 'mine',
        'parents': {'world': state['current']['world']['id']}, 'path': 'fixture/mine',
        'inputs': 'fixture/mine_inputs', 'hashes': f.files(mine), 'synthetic_preseed': True}
    prompt = '''This is a bounded synthetic tool microtest, not occupational task generation.
Use only /workspace/inputs and /draft. Do not browse, install dependencies, read credentials or call providers.
Run /workspace/bin/factory-tools help, schema (basis, rubric, calculation_evidence), and inspect on actual inputs.
Use /tmp/factory-requests for JSON --input-file requests. Produce the minimal valid compiler artifacts:
basis_draft.json, supervision.json, new_rubric.json, calculation_evidence.json and calculation_scripts/.
Obligations come only from the candidate fixture. Read schema for exact contracts; use calculation version 2.
On your first turn, check the actual draft and request independent consult, then end normally.
When resumed with consultation feedback, check each finding and record dispositions with file evidence,
making corrections only if needed. Then run replay with next_action "stop" and end normally.
This scope permits stop after replay solely to end the microtest; do not request trial, handoff, or submit.
There is no development trial, no final review and no blind solve in this microtest.
'''
    (root / 'prompts/compile.md').write_text(prompt, encoding='utf-8')
    scope.update(prompt_hashes=f.files(root / 'prompts'), fixture_hashes=f.files(root / 'fixture'),
                 readiness_sha256=f.digest(readiness), frozen_at=runner.now())
    f.write(root / 'scope.json', scope)
    state.update(scope_sha=f.digest(root / 'scope.json'), next={'role': 'compile'},
                 microtest_execution=False, status='prepared')
    f.write(root / 'receipt.json', state)
    shutil.copyfile(readiness, root / 'readiness.json')
    return scope


def execute(root):
    scope, state = runner.verify(root)
    if scope.get('purpose') != 'tool_microtest' or state['status'] != 'prepared' or state['attempts']:
        raise ValueError('fresh_microtest_required')
    if scope['fixture_hashes'] != f.files(root / 'fixture'):
        raise ValueError('fixture_changed')
    with (root / 'execution.lock').open('x') as handle:
        handle.write('microtest')
    try:
        runner.environment(root, scope)
        state.update(status='running', microtest_execution=True)
        for role in ('compile', 'consult', 'compile'):
            runner.verify(root)
            if (root / 'STOP').exists():
                raise ValueError('user_stopped')
            if state.get('next', {}).get('role') != role:
                raise ValueError('microtest_sequence_not_satisfied')
            if len(state['attempts']) >= 3:
                raise ValueError('microtest_launch_budget_exhausted')
            if state.get('deadline_epoch') is not None and time.time() >= state['deadline_epoch']:
                raise ValueError('microtest_time_budget_exhausted')
            runner.run_turn(root, scope, state, state['next'])
        if state.get('next') is not None or state['status'] != 'microtest_completed':
            raise ValueError('microtest_replay_stop_required')
    except (Exception, KeyboardInterrupt) as error:
        runner.record_execution_failure(root, state, error)
    finally:
        state.update(microtest_execution=False, stopped_at=runner.now())
        f.write(root / 'receipt.json', state)
        (root / 'execution.lock').unlink(missing_ok=True)
        f.write(root / 'microtest_report.json', runner.report(root) | {
            'claim': 'Native tool interaction only; synthetic preseed is not autonomous production.',
            'remaining_calls_transferable': False})
    return runner.report(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'execute', 'status', 'stop', 'report'))
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--readiness', type=Path)
    args = parser.parse_args()
    root = runner.safe_root(args.run_id)
    result = prepare(root, args.readiness) if args.action == 'prepare' else (
        execute(root) if args.action == 'execute' else runner.stop(root) if args.action == 'stop' else runner.report(root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
