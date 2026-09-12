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
FROZEN_VALIDATION_V1_CASES = (
    dict(method.CASES[1], id='frozen_procurement_price_01'),
    dict(method.CASES[3], id='frozen_audit_reliability_01'),
    dict(method.CASES[1], id='frozen_procurement_price_02'),
    dict(method.CASES[4], id='frozen_audit_reliability_02'),
)
QUALITY_DEVELOPMENT_V1_CASES = (
    dict(method.CASES[1], id='quality_procurement_price_02'),
    dict(method.CASES[4], id='quality_audit_reliability_02'),
)
MIGRATION_AUDIT_V1_CASES = (
    dict(method.CASES[4], id='development_audit_reliability_03'),
)
S1_CROSS_SEED_V1_CASES = (
    dict(method.CASES[1], id='cross_seed_g1_procurement_price'),
    dict(method.CASES[2], id='cross_seed_g2_acceptance'),
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
                         ('upstream_revisions', 0), ('task_manual_edits', 0),
                         ('initial_basis_snapshot', None)):
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


def _load_continuation_chain(latest):
    chain = []
    seen = set()
    current = latest.resolve()
    artifacts = latest.resolve().parent
    while True:
        if current in seen:
            raise ValueError('continuation_chain_cycle')
        if current.parent != artifacts:
            raise ValueError('continuation_parent_outside_artifacts')
        seen.add(current)
        manifest = io.read(current / 'batch.json')
        receipt = io.read(current / 'receipt.json')
        if receipt.get('manifest_sha256') != io.digest(current / 'batch.json'):
            raise ValueError('continuation_parent_manifest_changed')
        if manifest.get('source_bundle_hashes') != io.files(current / 'source_bundle'):
            raise ValueError('continuation_parent_source_bundle_changed')
        if receipt.get('status') not in ('incomplete', 'stopped', 'completed'):
            raise ValueError('continuation_parent_not_terminal')
        rows = {}
        for row in manifest.get('cases', []):
            child = current / row['path']
            if row.get('scope_sha256') != io.digest(child / 'scope.json'):
                raise ValueError('continuation_parent_case_scope_changed')
            rows[row['id']] = (row, child, io.read(child / 'receipt.json'))
        chain.append((current, manifest, receipt, rows))
        prior = receipt.get('prior_batch') or manifest.get('parent_batch')
        if not prior:
            break
        if not re.fullmatch(r'[A-Za-z0-9_-]+', prior):
            raise ValueError('unsafe_continuation_parent_id')
        current = (ARTIFACTS / prior).resolve()
    chain.reverse()
    expected = [row['id'] for row in FROZEN_VALIDATION_V1_CASES]
    if chain[0][1].get('profile') != 'frozen-validation-v1':
        raise ValueError('continuation_chain_missing_frozen_root')
    if [row['id'] for row in chain[0][1].get('cases', [])] != expected:
        raise ValueError('continuation_parent_case_order_changed')
    root_sources = chain[0][1]['source_bundle_hashes']
    for index, (_, manifest, receipt, rows) in enumerate(chain[1:], 1):
        if manifest.get('profile') != 'frozen-validation-v1-continuation':
            raise ValueError('continuation_chain_profile_changed')
        if manifest.get('source_bundle_hashes') != root_sources:
            raise ValueError('continuation_chain_source_changed')
        prior_root, prior_manifest, prior_receipt, _ = chain[index - 1]
        if (manifest.get('parent_batch') != prior_root.name
                or manifest.get('parent_manifest_sha256') != io.digest(prior_root / 'batch.json')
                or manifest.get('parent_receipt_sha256') != io.digest(prior_root / 'receipt.json')):
            raise ValueError('continuation_chain_parent_binding_changed')
        if receipt.get('prior_batch') != prior_root.name:
            raise ValueError('continuation_chain_receipt_binding_changed')
        if any(case_id not in expected for case_id in rows):
            raise ValueError('continuation_chain_unknown_case')
    return chain


def _case_has_production(child, previous):
    if (previous.get('attempts') or previous.get('sessions') or previous.get('current')
            or previous.get('submitted') or previous.get('development_trial')):
        return True
    for name in ('turns', 'development_trials', 'package'):
        path = child / name
        if path.exists() and any(path.rglob('*')):
            return True
    return False


def _quality_world_source(batch):
    """Bind the accepted procurement-2 world without inheriting STOP or sessions."""
    manifest, receipt = io.read(batch / 'batch.json'), io.read(batch / 'receipt.json')
    if receipt.get('manifest_sha256') != io.digest(batch / 'batch.json'):
        raise ValueError('quality_source_manifest_changed')
    row = next((row for row in manifest.get('cases', [])
                if row['id'] == 'frozen_procurement_price_02'), None)
    if row is None or row.get('scope_sha256') != io.digest(batch / row['path'] / 'scope.json'):
        raise ValueError('quality_source_procurement_position_missing_or_changed')
    child = batch / row['path']
    state = io.read(child / 'receipt.json')
    if set(state.get('current', {})) != {'world'} or state.get('next', {}).get('role') != 'mine':
        raise ValueError('quality_source_must_stop_after_accepted_world')
    world = state['current']['world']
    if io.files(child / world['path']) != world['hashes']:
        raise ValueError('quality_source_world_changed')
    attempts = [row for row in state.get('attempts', []) if harness.attempt_consumes_launch(row)]
    if len(attempts) != 3:
        raise ValueError('quality_source_expected_three_world_launches')
    return manifest, receipt, child, state, world


def _inherit_quality_world(source_child, source_state, source_entry, child, state):
    base = child / 'inherited' / 'world' / source_entry['id']
    snapshot, inputs = base / 'snapshot', base / 'inputs'
    shutil.copytree(source_child / source_entry['path'], snapshot)
    shutil.copytree(source_child / source_entry['inputs'], inputs)
    if io.files(snapshot) != source_entry['hashes']:
        raise ValueError('quality_source_world_changed_during_copy')
    entry = {**source_entry, 'path': snapshot.relative_to(child).as_posix(),
             'inputs': inputs.relative_to(child).as_posix()}
    state.update(current={'world': entry}, sessions={}, attempts=[], next={'role': 'mine'},
                 checks=[row for row in source_state.get('checks', [])
                         if row.get('role') == 'world' and row.get('hashes') == entry['hashes']],
                 consultations=[row for row in source_state.get('consultations', [])
                                if row.get('role') == 'world' and row.get('parents') == entry['parents']],
                 dispositions=[row for row in source_state.get('dispositions', [])
                               if row.get('snapshot') == entry['id']],
                 controller_interventions=[{
                     'kind': 'accepted_world_only_quality_development_inheritance',
                     'source_scope': source_child.name,
                     'world_snapshot': entry['id'],
                     'source_receipt_sha256': io.digest(source_child / 'receipt.json'),
                     'historical_launches_for_world': 3,
                 }])


def prepare(root, source_bundle, dependency_lock, dependency_remote, readiness_record,
            parent=None, case_ids=None, profile=None, continue_unstarted_from=None,
            continuation_budget=None, quality_world_from=None):
    if profile not in (None, 'frozen-validation-v1', 'quality-development-v1', 'migration-audit-v1',
                       's1-cross-seed-v1'):
        raise ValueError('unknown_profile')
    if profile is not None and (parent is not None or case_ids is not None or continue_unstarted_from is not None):
        raise ValueError('profile_is_mutually_exclusive_with_case_and_parent')
    if quality_world_from is not None and profile != 'quality-development-v1':
        raise ValueError('quality_world_source_requires_quality_profile')
    if profile == 'quality-development-v1' and quality_world_from is None:
        raise ValueError('quality_profile_requires_bound_procurement_world')
    if continue_unstarted_from is not None and (parent is not None or case_ids is not None):
        raise ValueError('continuation_is_mutually_exclusive_with_case_and_parent')
    if continuation_budget not in (None, 'new-8h'):
        raise ValueError('unknown_continuation_budget')
    if continuation_budget is not None and continue_unstarted_from is None:
        raise ValueError('continuation_budget_requires_continuation')
    if root.exists():
        raise FileExistsError('batch_exists')
    readiness = io.read(readiness_record)
    if readiness.get('tests_passed') is not True or not readiness.get('commands'):
        raise ValueError('completed_readiness_record_required')
    continuation_manifest = continuation_receipt = None
    quality_source = _quality_world_source(quality_world_from) if quality_world_from is not None else None
    continuation_chain = []
    continuation_rows = {}
    if continue_unstarted_from is not None:
        continuation_chain = _load_continuation_chain(continue_unstarted_from)
        _, continuation_manifest, continuation_receipt, continuation_rows = continuation_chain[-1]
        started_ids = set()
        for _, _, _, rows in continuation_chain:
            for case_id, (_, child, previous) in rows.items():
                if _case_has_production(child, previous):
                    started_ids.add(case_id)
        for case_id, (_, child, previous) in continuation_rows.items():
            if case_id not in started_ids and _case_has_production(child, previous):
                raise ValueError('continuation_position_not_unstarted:' + case_id)
        source_bundle = continue_unstarted_from / 'source_bundle'
        profile = 'frozen-validation-v1-continuation'
    if quality_source is not None:
        source_bundle = quality_world_from / 'source_bundle'
    available = (QUALITY_DEVELOPMENT_V1_CASES if profile == 'quality-development-v1' else S1_CROSS_SEED_V1_CASES
                 if profile == 's1-cross-seed-v1' else MIGRATION_AUDIT_V1_CASES
                 if profile == 'migration-audit-v1' else FROZEN_VALIDATION_V1_CASES
                 if profile in ('frozen-validation-v1', 'frozen-validation-v1-continuation') else CASES)
    selected = tuple((row for row in available if row['id'] not in started_ids)
                     if continue_unstarted_from is not None else
                     (available if case_ids is None else (row for row in available if row['id'] in case_ids)))
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
        prepare_kwargs = {'spec': spec, 'source_bundle': root / 'source_bundle',
                          'batch_id': root.name, 'protocol': PROTOCOL}
        if profile in ('frozen-validation-v1', 'frozen-validation-v1-continuation'):
            prepare_kwargs['harness_options'] = {'obligation_trace_version': 2,
                                                 'method_profile': 'frozen-validation-v1'}
        elif profile == 'quality-development-v1':
            lineage = ({'source_batch': quality_world_from.name,
                        'source_manifest_sha256': io.digest(quality_world_from / 'batch.json'),
                        'source_receipt_sha256': io.digest(quality_world_from / 'receipt.json')}
                       if spec['id'] == 'quality_procurement_price_02' else None)
            prepare_kwargs['harness_options'] = {
                'obligation_trace_version': 2, 'method_profile': 'quality-development-v1',
                'candidate_edit_version': 1, 'atomic_rubric_version': 'r10.atomic_rubric.1',
                'inherited_world_lineage': lineage}
        elif profile == 'migration-audit-v1':
            prepare_kwargs['harness_options'] = {
                'obligation_trace_version': 2, 'method_profile': 'quality-development-v1',
                'candidate_edit_version': 1, 'atomic_rubric_version': 'r10.atomic_rubric.1',
                'inherited_world_lineage': None}
        elif profile == 's1-cross-seed-v1':
            prepare_kwargs['harness_options'] = {
                'obligation_trace_version': 2, 'method_profile': 'quality-development-v1',
                'candidate_edit_version': 1, 'atomic_rubric_version': 'r10.atomic_rubric.1',
                'inherited_world_lineage': None}
        scope = runner.prepare(child, dependency_lock, dependency_remote, **prepare_kwargs)
        if quality_source is not None and spec['id'] == 'quality_procurement_price_02':
            _, _, source_child, source_state, source_entry = quality_source
            state = io.read(child / 'receipt.json')
            _inherit_quality_world(source_child, source_state, source_entry, child, state)
            io.write(child / 'receipt.json', state)
        if continue_unstarted_from is not None:
            _, parent_case, _ = continuation_rows[spec['id']]
            parent_scope = io.read(parent_case / 'scope.json')
            for key in ('seed', 'image', 'image_sha', 'dependency_remote', 'dependency_lock_sha',
                        'public_hashes', 'prompt_hashes', 'models', 'domain', 'case_id',
                        'calculation_contract_version', 'obligation_trace_version', 'method_profile'):
                if scope.get(key) != parent_scope.get(key):
                    raise ValueError('continuation_frozen_input_changed:' + key)
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
    manifest = {'protocol': PROTOCOL, 'profile': profile or 'development-v1',
                'created_at': now(), 'cases': cases,
                'max_launches': 16 * len(cases), 'seconds': 14400 * len(cases), 'per_case_launches': 16,
                'per_case_seconds': 14400, 'order_fixed': True,
                'source_bundle_hashes': io.files(root / 'source_bundle'),
                'authorization': (
                    (
                        'User-approved frozen-validation-v1 with four fixed new worlds; method, tools, prompts, '
                        'occupational inputs, environment and budget freeze before first model launch; independent '
                        'case failures continue, controller/global failures stop the batch; no grading.'
                    )
                    if profile == 'frozen-validation-v1'
                    else (
                        (
                            'User-approved collection-fix continuation of the three unstarted frozen-validation-v1 '
                            'positions, preserving the original batch deadline and per-case budgets; the first position '
                            'is not rerun; controller/global failures stop the continuation; no grading.'
                        )
                        if profile == 'frozen-validation-v1-continuation' and continuation_budget is None
                        else (
                            (
                                'User-approved bound continuation of the two unstarted frozen-validation-v1 positions with '
                                'a new 32-launch / 8-hour aggregate budget; prior 22 launches remain historical and are not '
                                'available to the new positions; controller/global failures stop the continuation; no grading.'
                            )
                            if profile == 'frozen-validation-v1-continuation'
                            else (
                                (
                                    'User-approved quality-development-v1 with the accepted procurement-2 world inherited '
                                    'from a frozen historical receipt and one new audit world; candidate editing and atomic '
                                    'binary rubrics enabled; 32 new launches / 8 hours; no grading.'
                                )
                                if profile == 'quality-development-v1'
                                else (
                                    (
                                        'User-approved single-position generation-side migration check reusing the '
                                        'admitted audit reliability seed with a fresh world; the profile selects the '
                                        'position only and the enabled method is the existing quality-development '
                                        'semantics (candidate editing, atomic binary rubrics, obligation trace 2, no '
                                        'quality diagnostics); 16 launches / 4 hours; in-method consultations, editing '
                                        'and bounded revisions are part of the method; first drafts, revisions and '
                                        'failures preserved; researcher post-generation checks are not part of any '
                                        'generation prompt; no grading.'
                                    )
                                    if profile == 'migration-audit-v1'
                                    else (
                                        (
                                            'User-approved S1 cross-seed exploration: two procurement positions '
                                            '(price reasonableness, acceptance disposition) each generating a fresh world '
                                            'through a single-author session with the complete author contract pack and '
                                            'self-check tooling; inputs packaged with quality-development semantics for '
                                            'schema compatibility but no pipeline execution is authorized from this batch; '
                                            'each position capped at 60 minutes; no grading.'
                                        )
                                        if profile == 's1-cross-seed-v1'
                                        else (
                                            f'{len(cases)} new development world(s): '
                                            + ', '.join(row['id'] for row in cases)
                                            + '; isolated development trial, one upstream revision, final review and '
                                            'admitted final solve; no grading.'
                                        )
                                    )
                                )
                            )
                        )
                    )
                ),
        }
    if quality_source is not None:
        source_manifest, _, _, source_state, _ = quality_source
        manifest.update(
            quality_world_source=quality_world_from.name,
            quality_world_source_manifest_sha256=io.digest(quality_world_from / 'batch.json'),
            quality_world_source_receipt_sha256=io.digest(quality_world_from / 'receipt.json'),
            prior_launches=0,
            historical_launches=source_manifest.get('prior_launches', 22) + sum(
                harness.attempt_consumes_launch(row) for row in source_state.get('attempts', [])),
            max_new_launches=32, max_launches=32, seconds=28800,
            execution_version_changed=True)
    if parent is not None:
        manifest.update(parent_batch=parent.name, parent_manifest_sha256=io.digest(parent / 'batch.json'),
                        parent_receipt_sha256=io.digest(parent / 'receipt.json'),
                        prior_launches=parent_manifest.get('prior_launches', 0) +
                        sum(sum(harness.attempt_consumes_launch(a) for a in value['attempts'])
                            for value in prior_by_case.values()))
    if continue_unstarted_from is not None:
        prior_launches = sum(
            sum(harness.attempt_consumes_launch(a) for a in previous.get('attempts', []))
            for _, _, _, rows in continuation_chain for _, _, previous in rows.values())
        chain_evidence = [{
            'batch_id': chain_root.name,
            'manifest_sha256': io.digest(chain_root / 'batch.json'),
            'receipt_sha256': io.digest(chain_root / 'receipt.json'),
        } for chain_root, _, _, _ in continuation_chain]
        new_budget = continuation_budget == 'new-8h'
        manifest.update(
            parent_batch=continue_unstarted_from.name,
            parent_manifest_sha256=io.digest(continue_unstarted_from / 'batch.json'),
            parent_receipt_sha256=io.digest(continue_unstarted_from / 'receipt.json'),
            continuation_chain=chain_evidence,
            prior_launches=prior_launches,
            max_new_launches=16 * len(cases),
            max_launches=prior_launches + 16 * len(cases),
            seconds=28800 if new_budget else continuation_manifest['seconds'],
            inherited_deadline_epoch=None if new_budget else continuation_receipt['deadline_epoch'],
            continuation_budget='new-8h' if new_budget else 'inherit',
            execution_version_changed=True,
            original_failure=continuation_receipt.get('first_failure'))
    io.write(root / 'batch.json', manifest)
    inherited_receipt = continuation_receipt or parent_receipt
    reset_clock = continue_unstarted_from is not None and continuation_budget == 'new-8h'
    io.write(root / 'receipt.json', {'status': 'prepared', 'manifest_sha256': io.digest(root / 'batch.json'),
                                     'position': 0, 'started_at': None if reset_clock else inherited_receipt.get('started_at') if inherited_receipt else None,
                                     'deadline_epoch': None if reset_clock else inherited_receipt.get('deadline_epoch') if inherited_receipt else None,
                                     'first_failure': None, 'stopped_at': None,
                                     'prior_batch': ((continue_unstarted_from or parent).name
                                                     if continue_unstarted_from or parent else None),
                                     'prior_failure': inherited_receipt.get('first_failure') if inherited_receipt else None,
                                     'controller_interventions': ([{
                                         'kind': 'collection_fix_remaining_positions_continuation',
                                         'parent_batch': continue_unstarted_from.name,
                                         'skipped_started_cases': sorted(started_ids),
                                         'budget_mode': continuation_budget or 'inherit',
                                         'preserved_deadline_epoch': None if reset_clock else continuation_receipt['deadline_epoch'],
                                     }] if continue_unstarted_from else [])})
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
    try:
        receipt['status'] = 'running'
        if receipt.get('started_at') is None:
            receipt['started_at'] = now()
            receipt['deadline_epoch'] = time.time() + manifest['seconds']
        io.write(root / 'receipt.json', receipt)
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
            if state.get('status') != 'completed':
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
    finally:
        receipt['stopped_at'] = now()
        try:
            io.write(root / 'receipt.json', receipt)
        finally:
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
            'historical_launches': manifest.get('historical_launches', manifest.get('prior_launches', 0)),
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
    parser.add_argument('--continue-unstarted-from')
    parser.add_argument('--quality-world-from')
    parser.add_argument('--continuation-budget', choices=('new-8h',))
    parser.add_argument('--case', choices=('all', 'procurement'))
    parser.add_argument('--profile', choices=('frozen-validation-v1', 'quality-development-v1', 'migration-audit-v1', 's1-cross-seed-v1'))
    args = parser.parse_args()
    selectors = [bool(args.profile), bool(args.case), bool(args.parent_batch), bool(args.continue_unstarted_from)]
    if sum(selectors) > 1:
        parser.error('--profile, --case, --parent-batch and --continue-unstarted-from are mutually exclusive')
    root = root_for(args.batch_id)
    if args.action == 'prepare':
        if args.readiness_record is None or (args.source_bundle is None and not args.continue_unstarted_from
                                             and not args.quality_world_from):
            parser.error('prepare requires --readiness-record and a source bundle or bound source batch')
        parent = root_for(args.parent_batch) if args.parent_batch else None
        continuation = root_for(args.continue_unstarted_from) if args.continue_unstarted_from else None
        quality_source = root_for(args.quality_world_from) if args.quality_world_from else None
        case_ids = None if args.case in (None, 'all') else ('development_procurement_price',)
        result = prepare(root, args.source_bundle, args.dependency_lock, args.dependency_remote,
                         args.readiness_record, parent, case_ids, args.profile, continuation,
                         args.continuation_budget, quality_source)
    elif args.action == 'execute':
        result = execute(root)
    elif args.action == 'stop':
        result = stop(root)
    else:
        result = report(root)
    runner.emit_json(result)
