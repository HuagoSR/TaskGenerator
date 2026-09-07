"""Five-position factory study. No provider client, grader or generic scheduler."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from task_generator.production import agent_factory as f
from task_generator.production.task_method_pilot import CASES

SOURCE_IDS = {
    'procurement_far_13_106_3': 'far_13_106_3',
    'procurement_far_15_404_1_methods': 'far_15_404_1',
    'procurement_dau_igce_workflow': 'dau_igce',
    'procurement_dfars_pgi_insufficient_data': 'dfars_pgi_215_404_1',
    'procurement_far_46_202_1_boundary': 'far_46_202_1',
    'procurement_far_46_407_nonconforming': 'far_46_407',
    'procurement_far_46_501_acceptance': 'far_46_501',
    'procurement_far_46_503_receiving': 'far_46_503',
    'audit_as1105_reliability': 'pcaob_as1105',
    'audit_as1215_workpaper': 'pcaob_as1215',
    'audit_pcaob_remediation_monitoring': 'pcaob_remediation',
}


def public_inputs(runner, destination, spec, bundle):
    original = runner.previous.public_inputs(destination, spec)
    seed = f.read(destination / 'work_seed.json')
    required = {r['source_id'] for r in seed['public_sources']}
    rule_set = f.read(destination / 'professional_rules.json')
    rule_set['rules'] = [r for r in rule_set['rules']
                         if {s['source_id'] for s in r['source_refs']} <= required]
    if not rule_set['rules']:
        raise ValueError('no_seed_linked_rules')
    catalog = f.read(bundle / 'verified_sources.json')
    sources = f.read(destination / 'sources.json')
    mapped = set()
    for row in sources:
        identity = SOURCE_IDS[row['source_id']]
        evidence = catalog[identity]
        path = f.safe_path(bundle, evidence['file'])
        if evidence['status'] != 'verified' or f.digest(path) != evidence['sha256']:
            raise ValueError('public_source_unverified:' + identity)
        row['original_source_id'] = row['source_id']
        row['linked_source_id'] = identity
        row['verification'] = evidence
        row['historical_summary'] = row.pop('summary')
        row['summary'] = evidence.get('verified_summary', row['historical_summary'])
        row['content_sha256'] = evidence['sha256']
        mapped.add(identity)
    if not required <= mapped:
        raise ValueError('seed_source_mapping_missing')
    f.write(destination / 'professional_rules.json', rule_set)
    # Explicit alias records preserve both original namespaces; no fuzzy matching.
    aliases = [{'source_id': identity, 'evidence_kind': 'source_mapping',
                'skill_source_id': next(r['source_id'] for r in sources if r['linked_source_id'] == identity),
                'verification': catalog[identity]} for identity in sorted(required)]
    f.write(destination / 'sources.json', sources + aliases)
    skill = destination / 'SKILL.md'
    skill.write_text(skill.read_text(encoding='utf-8') + '\n\n## Frozen public-source calibration\n'
                     'Read sources.json before relying on this Skill. Its verified summaries and applicability limits '
                     'qualify the historical source descriptions. Public practice is not a legal obligation or evidence '
                     'that a synthetic organization event happened. Unverified historical attributions must not create task obligations.\n', encoding='utf-8')
    return original


def prepare(runner, root, bundle, dependency_lock, dependency_remote):
    if root.exists():
        raise FileExistsError('batch_exists')
    catalog = f.read(bundle / 'verified_sources.json')
    for identity in SOURCE_IDS.values():
        record = catalog[identity]
        if record['status'] != 'verified' or f.digest(f.safe_path(bundle, record['file'])) != record['sha256']:
            raise ValueError('source_bundle_not_verified:' + identity)
    root.mkdir()
    shutil.copytree(bundle, root / 'source_bundle')
    cases = []
    for spec in CASES:
        child = root / 'cases' / (root.name + '_' + spec['id'])
        child.parent.mkdir(exist_ok=True)
        runner.prepare(child, dependency_lock, dependency_remote, spec=spec,
                       source_bundle=root / 'source_bundle', batch_id=root.name)
        cases.append(dict(spec, path=child.relative_to(root).as_posix(), scope_sha=f.digest(child / 'scope.json')))
    first = f.read(root / cases[0]['path'] / 'scope.json')
    manifest = {'version': 'agent_factory_batch.1', 'created_at': runner.now(), 'cases': cases,
                'code_hashes': first['code_hashes'], 'prompt_hashes': first['prompt_hashes'],
                'source_bundle_hashes': f.files(root / 'source_bundle'),
                'max_launches': 60, 'seconds': 54000, 'per_world_seconds': 10800,
                'models': f.MODELS, 'world_max_launches': 12, 'production_launches': 10,
                'per_launch_seconds': 1800, 'terminal_reserve_seconds': 3600,
                'authorization': 'User approved one development world then four conditional frozen validation worlds, 60 launches/15 hours, no grading or expansion.'}
    f.write(root / 'batch.json', manifest)
    f.write(root / 'receipt.json', {'status': 'prepared', 'manifest_sha': f.digest(root / 'batch.json'),
            'position': 0, 'gates': {}, 'first_failure': None, 'interventions': []})
    return manifest


def verify(runner, root):
    manifest, state = f.read(root / 'batch.json'), f.read(root / 'receipt.json')
    if f.digest(root / 'batch.json') != state['manifest_sha']:
        raise ValueError('batch_manifest_changed')
    if manifest['code_hashes'] != runner.base.code_hashes():
        raise ValueError('batch_code_changed')
    if f.files(root / 'source_bundle') != manifest['source_bundle_hashes']:
        raise ValueError('batch_sources_changed')
    for spec in manifest['cases']:
        child = f.safe_path(root, spec['path'])
        if f.digest(child / 'scope.json') != spec['scope_sha']:
            raise ValueError('batch_child_scope_changed')
        scope, _ = runner.verify(child)
        if scope['batch_id'] != root.name or scope['prompt_hashes'] != manifest['prompt_hashes']:
            raise ValueError('batch_method_or_membership_changed')
    for case_id, identity in state['gates'].items():
        spec = next(c for c in manifest['cases'] if c['id'] == case_id)
        if f.digest(root / spec['path'] / 'researcher_review.json') != identity:
            raise ValueError('batch_gate_changed')
    return manifest, state


def cap(runner, root, child, role, *, started=False, appended=False):
    manifest, state = verify(runner, root)
    if not (root / 'execution.lock').exists() or state['status'] != 'running':
        raise ValueError('batch_execution_required')
    if (root / 'STOP').exists():
        raise ValueError('batch_stop_requested')
    spec = manifest['cases'][state['position']]
    if (root / spec['path']).resolve() != child.resolve():
        raise ValueError('batch_position_mismatch')
    count = sum(len(f.read(root / c['path'] / 'receipt.json')['attempts']) for c in manifest['cases'])
    if count > 60 or (not appended and count >= 60):
        raise ValueError('batch_launch_budget_exhausted')
    if started and 'deadline_epoch' not in state:
        state.update(started_at=runner.now(), deadline_epoch=time.time() + manifest['seconds'])
        f.write(root / 'receipt.json', state)
    reserve = 3600 if role not in ('review', 'solve') else (1800 if role == 'review' else 0)
    left = state.get('deadline_epoch', time.time() + manifest['seconds']) - time.time() - reserve
    if left < 1:
        raise ValueError('batch_time_budget_exhausted')
    return min(1800, int(left))


def gate(child, receipt):
    if not (receipt.get('status') == 'completed' and receipt.get('submitted')
            and receipt.get('review', {}).get('quality') == 'pass'
            and receipt.get('trial', {}).get('delivery_status') == 'valid'):
        return 'not_passed'
    f.assert_submission({**receipt, 'submitted': False})
    path = child / 'researcher_review.json'
    if not path.exists():
        return 'pending'
    review = f.read(path)
    if (review['receipt_sha'] != f.digest(child / 'receipt.json')
            or review['scope_sha'] != f.digest(child / 'scope.json')
            or review['status'] not in ('pass', 'issue', 'uncertain')
            or not review.get('findings') or review.get('task_manual_edits') != 0):
        raise ValueError('invalid_researcher_gate')
    for item in review['findings']:
        target = f.safe_path(child, item['path'])
        if not target.is_file() or f.digest(target) != item['sha256'] or not item.get('locator') or not item.get('observation'):
            raise ValueError('researcher_gate_evidence_invalid')
    return review['status']


def execute(runner, root):
    manifest, state = verify(runner, root)
    if state['status'] not in ('prepared', 'awaiting_readonly_review', 'paused'):
        raise ValueError('batch_not_executable')
    if state['status'] == 'paused':
        (root / 'STOP').unlink(missing_ok=True)
    lock = root / 'execution.lock'
    with lock.open('x') as handle:
        handle.write(str(__import__('os').getpid()))
    try:
        state['status'] = 'running'
        f.write(root / 'receipt.json', state)
        while state['position'] < len(manifest['cases']):
            manifest, state = verify(runner, root)
            if (root / 'STOP').exists():
                state['status'] = 'paused'
                break
            if time.time() >= state.get('deadline_epoch', float('inf')):
                raise ValueError('batch_time_budget_exhausted')
            spec = manifest['cases'][state['position']]
            child = root / spec['path']
            receipt = f.read(child / 'receipt.json')
            if receipt['status'] in ('prepared', 'paused'):
                runner.execute(child, batch_root=root)
                # cap() can start the overall clock; never overwrite it with stale state.
                state = f.read(root / 'receipt.json')
                receipt = f.read(child / 'receipt.json')
            if receipt['status'] == 'paused':
                state['status'] = 'paused'
                break
            if receipt.get('failure_category') in ('global', 'controller') or (root / 'STOP').exists():
                raise ValueError('batch_child_global_failure:' + receipt.get('stop_reason', 'stop requested'))
            decision = gate(child, receipt)
            if decision == 'pending':
                state['status'] = 'awaiting_readonly_review'
                break
            if (child / 'researcher_review.json').exists():
                state['gates'][spec['id']] = f.digest(child / 'researcher_review.json')
                state['interventions'].append({'case': spec['id'], 'kind': 'researcher_readonly_closeout', 'decision': decision})
            if decision != 'pass':
                state['first_failure'] = state['first_failure'] or {'case': spec['id'], 'reason': receipt.get('stop_reason', decision)}
                if spec['phase'] == 'development':
                    state.update(status='development_not_passed', stopped_at=runner.now())
                    break
            state['position'] += 1
            f.write(root / 'receipt.json', state)
        if state['position'] == len(manifest['cases']):
            state.update(status='completed', stopped_at=runner.now())
    except (Exception, KeyboardInterrupt) as error:
        # Read the persisted clock even if a child failed before returning.
        persisted = f.read(root / 'receipt.json')
        for key in ('started_at', 'deadline_epoch'):
            if key in persisted:
                state[key] = persisted[key]
        reason = type(error).__name__ + ':' + str(error)
        state.update(status='incomplete', stop_reason=reason, stopped_at=runner.now())
        state['first_failure'] = state['first_failure'] or {'case': manifest['cases'][min(state['position'], 4)]['id'], 'reason': reason}
    finally:
        f.write(root / 'receipt.json', state)
        lock.unlink(missing_ok=True)
    return report(root)


def stop(runner, root):
    (root / 'STOP').touch()
    manifest, state = f.read(root / 'batch.json'), f.read(root / 'receipt.json')
    if state['position'] < len(manifest['cases']):
        runner.stop(root / manifest['cases'][state['position']]['path'])
    return {'stop_requested': True, 'batch': root.name}


def report(root):
    manifest, state = f.read(root / 'batch.json'), f.read(root / 'receipt.json')
    rows = []
    for spec in manifest['cases']:
        child = root / spec['path']
        receipt = f.read(child / 'receipt.json')
        review_path = child / 'researcher_review.json'
        admitted = receipt.get('review', {}).get('quality') == 'pass'
        full = (spec['id'] in state['gates'] and f.read(review_path)['status'] == 'pass')
        rows.append({'case': spec['id'], 'phase': spec['phase'], 'seed': spec['seed'],
                     'status': receipt['status'], 'launches': len(receipt['attempts']),
                     'submitted': receipt.get('submitted', False), 'review_admitted': admitted,
                     'delivery_status': receipt.get('trial', {}).get('delivery_status'), 'full_pass': full,
                     'failure_category': receipt.get('failure_category'), 'stop_reason': receipt.get('stop_reason'),
                     'usage': [a.get('usage') for a in receipt['attempts']],
                     'native_seconds': sum(a.get('elapsed_seconds', 0) for a in receipt['attempts'])})
    validation = [r for r in rows if r['phase'] == 'validation']
    return {'status': state['status'], 'position': state['position'], 'cases': rows,
            'launches_used': sum(r['launches'] for r in rows), 'started_at': state.get('started_at'),
            'deadline_epoch': state.get('deadline_epoch'), 'stop_reason': state.get('stop_reason'),
            'validation_positions': 4, 'validation_admitted': sum(r['review_admitted'] for r in validation),
            'validation_full_pass': sum(r['full_pass'] for r in validation),
            'initial_cross_context_support': all(r['full_pass'] for r in validation),
            'professional_status': 'provisional/LLM-proxy', 'total_cost': None, 'model_request_count': None}
