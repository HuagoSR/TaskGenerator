"""Two-position development harness for isolated trial and calculation evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]
import run_r10_agent_factory_pilot as runner
from task_generator.production import agent_factory as io
from task_generator.production import task_method_pilot as method
from task_generator.production import task_factory_harness as harness

ARTIFACTS = ROOT / 'artifacts/r10'
PROTOCOL = 'task_factory_harness_v1'
CASES = (
    dict(method.CASES[0], id='development_procurement_price'),
    dict(method.CASES[3], id='development_audit_reliability'),
)


def now():
    return datetime.now(timezone.utc).isoformat()


def root_for(batch_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', batch_id):
        raise ValueError('unsafe_batch_id')
    return ARTIFACTS / batch_id


def inherit_case_progress(parent_case, child, previous, state):
    """Carry verified intermediate products across a controller-fix continuation."""
    if previous.get('submitted'):
        raise ValueError('submitted_case_cannot_continue')
    current = previous.get('current') or {}
    if not current:
        return
    inherited_current = {}
    for role, old_entry in current.items():
        entry = dict(old_entry)
        base = child / 'inherited' / role / entry['id']
        snapshot = base / 'snapshot'
        inputs = base / 'inputs'
        shutil.copytree(parent_case / entry['path'], snapshot)
        shutil.copytree(parent_case / entry['inputs'], inputs)
        if io.files(snapshot) != entry['hashes']:
            raise ValueError('parent_snapshot_changed')
        entry.update(path=snapshot.relative_to(child).as_posix(),
                     inputs=inputs.relative_to(child).as_posix())
        inherited_current[role] = entry
    state['current'] = inherited_current
    for key, default in (('checks', []), ('consultations', []), ('dispositions', []),
                         ('calculation_replays', []), ('compile_stage', 'basis'),
                         ('upstream_revisions', 0), ('task_manual_edits', 0)):
        state[key] = previous.get(key, default)
    if previous.get('development_trial'):
        trial = dict(previous['development_trial'])
        source = parent_case / trial['path']
        destination = child / 'inherited' / 'development_trial'
        shutil.copytree(source, destination)
        if io.files(destination) != trial['hashes']:
            raise ValueError('parent_development_trial_changed')
        trial['path'] = destination.relative_to(child).as_posix()
        state['development_trial'] = trial
    request = previous.get('next')
    if (request and request.get('role') == 'mine'
            and request.get('feedback_origin') == 'upstream_issue'
            and request.get('feedback', {}).get('from_role') == 'world'):
        request = {'role': 'mine'}
    state['next'] = request or ({'role': 'mine'} if set(current) == {'world'} else None)
    state['controller_interventions'] = [{
        'kind': 'linked_controller_fix_continuation',
        'parent_scope': parent_case.name,
        'parent_failure': previous.get('stop_reason'),
        'preserved_current_roles': sorted(current),
    }]


def prepare(root, source_bundle, dependency_lock, dependency_remote, readiness_record,
            parent=None, case_ids=None):
    if root.exists():
        raise FileExistsError('batch_exists')
    readiness = io.read(readiness_record)
    if readiness.get('tests_passed') is not True or not readiness.get('commands'):
        raise ValueError('completed_readiness_record_required')
    selected = tuple(CASES if case_ids is None else (row for row in CASES if row['id'] in case_ids))
    if not selected or case_ids is not None and {row['id'] for row in selected} != set(case_ids):
        raise ValueError('unknown_or_empty_case_selection')
    parent_manifest = parent_receipt = None
    prior_by_case = {}
    if parent is not None:
        parent_manifest, parent_receipt = io.read(parent / 'batch.json'), io.read(parent / 'receipt.json')
        if parent_receipt['manifest_sha256'] != io.digest(parent / 'batch.json'):
            raise ValueError('parent_manifest_changed')
        if parent_manifest['source_bundle_hashes'] != io.files(parent / 'source_bundle'):
            raise ValueError('parent_source_bundle_changed')
        if parent_receipt['status'] not in ('completed', 'incomplete', 'stopped'):
            raise ValueError('parent_batch_not_terminal')
        if [row['id'] for row in parent_manifest['cases']] != [row['id'] for row in selected]:
            raise ValueError('continuation_case_selection_changed')
        for row in parent_manifest['cases']:
            if row['scope_sha256'] != io.digest(parent / row['path'] / 'scope.json'):
                raise ValueError('parent_case_scope_changed')
            previous = io.read(parent / row['path'] / 'receipt.json')
            prior_by_case[row['id']] = previous
    root.mkdir(parents=True)
    shutil.copytree(source_bundle, root / 'source_bundle')
    cases = []
    for spec in selected:
        child = root / 'cases' / f'{root.name}_{spec["id"]}'
        child.parent.mkdir(parents=True, exist_ok=True)
        scope = runner.prepare(child, dependency_lock, dependency_remote, spec=spec,
                               source_bundle=root / 'source_bundle', batch_id=root.name,
                               protocol=PROTOCOL)
        if parent is not None:
            state = io.read(child / 'receipt.json')
            previous = prior_by_case[spec['id']]
            parent_case = parent / next(row['path'] for row in parent_manifest['cases'] if row['id'] == spec['id'])
            consumed = [a for a in previous['attempts'] if harness.attempt_consumes_launch(a)]
            state.update(prior_launches=previous.get('prior_launches', 0) + len(consumed),
                         prior_production_launches=previous.get('prior_production_launches', 0) +
                         sum(a['role'] not in ('review', 'solve') for a in consumed),
                         prior_native_elapsed_seconds=previous.get('prior_native_elapsed_seconds', 0) +
                         sum(a.get('elapsed_seconds', 0) for a in consumed),
                         prior_scope=str(parent.name), prior_receipt_sha256=io.digest(
                             parent / next(row['path'] for row in parent_manifest['cases'] if row['id'] == spec['id']) / 'receipt.json'),
                         recoveries=previous.get('recoveries', 0),
                         deadline_epoch=previous.get('deadline_epoch'), started_at=previous.get('started_at'))
            inherit_case_progress(parent_case, child, previous, state)
            io.write(child / 'receipt.json', state)
        io.write(child / 'readiness.json', {'tests_passed': True, 'code_hashes': scope['code_hashes'],
                                            'evidence': readiness, 'recorded_at': now()})
        cases.append({'id': spec['id'], 'path': child.relative_to(root).as_posix(),
                      'scope_sha256': io.digest(child / 'scope.json')})
    manifest = {'protocol': PROTOCOL, 'created_at': now(), 'cases': cases,
                'max_launches': 16 * len(cases), 'seconds': 14400 * len(cases), 'per_case_launches': 16,
                'per_case_seconds': 14400, 'order_fixed': True,
                'source_bundle_hashes': io.files(root / 'source_bundle'),
                'authorization': (f'{len(cases)} new development world(s): '
                                  + ', '.join(row['id'] for row in cases)
                                  + '; isolated development trial, one upstream revision, final review and admitted final solve; no grading.')}
    if parent is not None:
        manifest.update(parent_batch=parent.name, parent_manifest_sha256=io.digest(parent / 'batch.json'),
                        parent_receipt_sha256=io.digest(parent / 'receipt.json'),
                        prior_launches=parent_manifest.get('prior_launches', 0) +
                        sum(sum(harness.attempt_consumes_launch(a) for a in value['attempts'])
                            for value in prior_by_case.values()))
    io.write(root / 'batch.json', manifest)
    io.write(root / 'receipt.json', {'status': 'prepared', 'manifest_sha256': io.digest(root / 'batch.json'),
                                     'position': 0, 'started_at': parent_receipt.get('started_at') if parent_receipt else None,
                                     'deadline_epoch': parent_receipt.get('deadline_epoch') if parent_receipt else None,
                                     'first_failure': None, 'stopped_at': None,
                                     'prior_batch': parent.name if parent else None,
                                     'prior_failure': parent_receipt.get('first_failure') if parent_receipt else None})
    return report(root)


def verify(root):
    manifest, receipt = io.read(root / 'batch.json'), io.read(root / 'receipt.json')
    if receipt['manifest_sha256'] != io.digest(root / 'batch.json'):
        raise ValueError('batch_manifest_changed')
    if manifest['source_bundle_hashes'] != io.files(root / 'source_bundle'):
        raise ValueError('batch_source_bundle_changed')
    for row in manifest['cases']:
        child = root / row['path']
        if row['scope_sha256'] != io.digest(child / 'scope.json'):
            raise ValueError('case_scope_changed')
        runner.verify(child)
    return manifest, receipt


def execute(root):
    manifest, receipt = verify(root)
    if receipt['status'] not in ('prepared', 'paused'):
        raise ValueError('batch_not_executable')
    if receipt['status'] == 'paused':
        (root / 'STOP').unlink(missing_ok=True)
    lock = root / 'execution.lock'
    with lock.open('x') as handle:
        handle.write(str(__import__('os').getpid()))
    receipt['status'] = 'running'
    io.write(root / 'receipt.json', receipt)
    try:
        while receipt['position'] < len(manifest['cases']):
            if (root / 'STOP').exists():
                receipt['status'] = 'paused'
                break
            if receipt.get('deadline_epoch') is not None and time.time() >= receipt['deadline_epoch']:
                raise ValueError('batch_time_budget_exhausted')
            launches = manifest.get('prior_launches', 0) + sum(
                sum(harness.attempt_consumes_launch(a) for a in io.read(
                    root / row['path'] / 'receipt.json')['attempts']) for row in manifest['cases'])
            if launches >= manifest['max_launches']:
                raise ValueError('batch_launch_budget_exhausted')
            row = manifest['cases'][receipt['position']]
            child = root / row['path']
            state = io.read(child / 'receipt.json')
            runner.execute(child, batch_root=root)
            receipt = io.read(root / 'receipt.json')
            state = io.read(child / 'receipt.json')
            if (root / 'STOP').exists():
                receipt['position'] += 1
                receipt['status'] = 'stopped'
                break
            if state.get('failure_category') in ('global', 'controller') or any(token in str(state.get('stop_reason', ''))
                    for token in ('authentication_failed', 'isolation', 'fingerprint', 'code_changed', 'source_changed')):
                raise ValueError('global_case_failure:' + str(state.get('stop_reason')))
            if state.get('status') != 'completed':
                receipt['first_failure'] = receipt.get('first_failure') or {
                    'position': receipt['position'],
                    'case_id': row['id'],
                    'reason': state.get('stop_reason') or state.get('status') or 'case_incomplete',
                }
            receipt['position'] += 1
            io.write(root / 'receipt.json', receipt)
        if receipt['position'] == len(manifest['cases']) and receipt['status'] == 'running':
            receipt['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        receipt['status'] = 'incomplete'
        receipt['first_failure'] = receipt.get('first_failure') or {
            'position': receipt['position'], 'reason': type(error).__name__ + ':' + str(error)}
    receipt['stopped_at'] = now()
    io.write(root / 'receipt.json', receipt)
    lock.unlink(missing_ok=True)
    return report(root)


def stop(root):
    manifest, receipt = verify(root)
    (root / 'STOP').touch()
    if receipt['position'] < len(manifest['cases']):
        runner.stop(root / manifest['cases'][receipt['position']]['path'])
    return {'stop_requested': True, 'batch': root.name}


def report(root):
    manifest = io.read(root / 'batch.json')
    receipt = io.read(root / 'receipt.json')
    rows = []
    for item in manifest['cases']:
        child = root / item['path']
        state = io.read(child / 'receipt.json')
        rows.append({'id': item['id'], **runner.report(child),
                     'upstream_revisions': state.get('upstream_revisions', 0),
                     'development_trial': bool(state.get('development_trial')),
                     'calculation_replays': len(state.get('calculation_replays', []))})
    current_launches = sum(row['launches_used'] for row in rows)
    first_failure = receipt.get('first_failure')
    if first_failure is None:
        for position, row in enumerate(rows):
            if row.get('first_failure') or row.get('status') in (
                    'incomplete', 'quality_not_passed', 'stopped'):
                first_failure = {'position': position, 'case_id': row['id'],
                                 'reason': (row.get('stop_reason') or row.get('status'))}
                break
    return {'status': receipt['status'], 'position': receipt['position'],
            'launches_used': manifest.get('prior_launches', 0) + current_launches,
            'current_scope_launches': current_launches, 'prior_launches': manifest.get('prior_launches', 0),
            'first_failure': first_failure, 'cases': rows,
            'professional_status': 'provisional/LLM-proxy',
            'batch_pass_rate': None, 'stable_scale_claim': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'execute', 'status', 'stop', 'report'))
    parser.add_argument('--batch-id', required=True)
    parser.add_argument('--source-bundle', type=Path)
    parser.add_argument('--dependency-lock', type=Path, default=runner.DEFAULT_LOCK)
    parser.add_argument('--dependency-remote', default=runner.DEFAULT_DEPS)
    parser.add_argument('--readiness-record', type=Path)
    parser.add_argument('--parent-batch')
    parser.add_argument('--case', choices=('all', 'procurement'), default='all')
    args = parser.parse_args()
    root = root_for(args.batch_id)
    if args.action == 'prepare':
        if args.source_bundle is None or args.readiness_record is None:
            parser.error('prepare requires --source-bundle and --readiness-record')
        parent = root_for(args.parent_batch) if args.parent_batch else None
        case_ids = None if args.case == 'all' else ('development_procurement_price',)
        result = prepare(root, args.source_bundle, args.dependency_lock, args.dependency_remote,
                         args.readiness_record, parent, case_ids)
    elif args.action == 'execute':
        result = execute(root)
    elif args.action == 'stop':
        result = stop(root)
    else:
        result = report(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
