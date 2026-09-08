from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Test'))
import run_r10_agent_factory_pilot as runner
from task_generator.production import agent_factory as f
from task_generator.production.agent_factory_tools import Broker


def state():
    return {'current': {}, 'sessions': {}, 'attempts': [], 'checks': [], 'consultations': [], 'submitted': False}


def entry(identity, parents=None):
    return {'id': identity, 'parents': parents or {}, 'hashes': {'a.txt': identity}}


def test_version_invalidation_and_submission():
    s = state()
    f.accept_snapshot(s, 'world', entry('w1'))
    f.accept_snapshot(s, 'mine', entry('m1', {'world': 'w1'}))
    f.accept_snapshot(s, 'compile', entry('c1', {'world': 'w1', 'mine': 'm1'}))
    s['checks'] = [{'role': r, 'tool': 'check', 'hashes': s['current'][r]['hashes']} for r in f.AUTHOR_ROLES]
    s['consultations'] = [{'role': 'world', 'parents': {}, 'request_id': 'q1', 'finding_ids': []}]
    f.assert_submission(s)
    s['sessions']['mine'] = {'id': 'old'}
    f.accept_snapshot(s, 'world', entry('w2'))
    assert set(s['current']) == {'world'}
    assert not s['sessions']
    with pytest.raises(ValueError, match='stale'):
        f.accept_snapshot(s, 'mine', entry('old', {'world': 'w1'}))
    f.accept_snapshot(s, 'mine', entry('m2', {'world': 'w2'}))
    f.accept_snapshot(s, 'compile', entry('c2', {'world': 'w2', 'mine': 'm2'}))
    s['checks'] = [{'role': r, 'tool': 'check', 'hashes': s['current'][r]['hashes']} for r in f.AUTHOR_ROLES]
    f.assert_submission(s)
    s['submitted'] = True
    with pytest.raises(ValueError, match='already_submitted'):
        f.invalidate(s, 'world')
    with pytest.raises(ValueError, match='already_submitted'):
        f.assert_submission(s)


def test_budget_reserves_and_no_reused_terminal_slots():
    s = state()
    s['deadline_epoch'] = 4000
    assert f.cap(s, 'world', 0) == 400
    assert f.cap(s, 'review', 0) == 1800
    with pytest.raises(ValueError, match='time_budget'):
        f.cap(s, 'world', 401)
    s['attempts'] = [{'role': 'world'}] * 10
    with pytest.raises(ValueError, match='launch_budget'):
        f.cap(s, 'compile', 0)
    assert f.cap(s, 'review', 0) == 1800
    s['attempts'].append({'role': 'review'})
    with pytest.raises(ValueError, match='already_attempted'):
        f.cap(s, 'review', 0)
    assert f.cap(s, 'solve', 0) == 1800


@pytest.mark.parametrize('path', ['../x', '/etc/passwd', 'a\\b', 'E:/x'])
def test_safe_paths(tmp_path, path):
    with pytest.raises(ValueError):
        f.safe_path(tmp_path, path)


def make_broker(tmp_path, role='world'):
    (tmp_path / 'draft/hidden').mkdir(parents=True)
    (tmp_path / 'draft/hidden/process.md').write_text('Actors and events')
    return Broker({'root': str(tmp_path), 'role': role, 'parents': {}})


def test_broker_snapshot_preserves_first_and_deduplicates(tmp_path):
    broker = make_broker(tmp_path)
    broker.handle({'action': 'save-process'})
    candidate = tmp_path / 'draft/candidate'
    candidate.mkdir()
    (candidate / 'a.txt').write_text('First version')
    snap = broker.handle({'action': 'snapshot', 'reason': 'Initial materials'})
    (candidate / 'a.txt').write_text('Second version')
    assert (tmp_path / 'snapshots' / snap['id'] / 'candidate/a.txt').read_text() == 'First version'
    assert broker.handle({'action': 'diff', 'snapshot': snap['id']})['changed'] == ['candidate/a.txt']
    with pytest.raises(ValueError, match='current_draft'):
        broker.handle({'action': 'consult', 'snapshot': snap['id'], 'reason': 'Check'})
    snap2 = broker.handle({'action': 'snapshot', 'reason': 'Corrected record'})
    request = {'action': 'consult', 'snapshot': snap2['id'], 'reason': 'Read independently'}
    broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'hashes': f.files(broker.draft)}})
    broker.handle(request)
    with pytest.raises(ValueError, match='request_pending'):
        broker.handle(request)
    assert f.read(tmp_path / 'broker.json')['pending']['snapshot'] == snap2['id']


def test_broker_process_order_and_readonly_roles(tmp_path):
    broker = make_broker(tmp_path)
    (tmp_path / 'draft/candidate').mkdir()
    (tmp_path / 'draft/candidate/a.txt').write_text('Premature')
    with pytest.raises(ValueError, match='precedes_process'):
        broker.handle({'action': 'save-process'})
    broker.config['role'] = 'consult'
    with pytest.raises(ValueError, match='read_only_role'):
        broker.handle({'action': 'snapshot', 'reason': 'forbidden'})


def test_explicit_role_session_commands():
    sol = runner.agent_script('world', 'role-session-id')
    assert 'exec resume role-session-id' in sol and '--last' not in sol
    assert '--ephemeral' not in sol and '/state/codex' in sol
    ds = runner.agent_script('mine', 'ses_example')
    assert '--session ses_example' in ds and '--continue' not in ds
    assert 'stirrup' not in sol + ds and 'grader' not in sol + ds
    with pytest.raises(ValueError):
        runner.agent_script('world', 'x;unsafe')


def test_input_isolation(tmp_path, monkeypatch):
    public = tmp_path / 'public'
    public.mkdir()
    for name in ('public_context.json', 'professional_rules.json', 'sources.json'):
        f.write(public / name, {})
    (public / 'SKILL.md').write_text('factory only')
    world = tmp_path / 'world'
    (world / 'candidate').mkdir(parents=True)
    (world / 'hidden').mkdir()
    (world / 'candidate/record.txt').write_text('visible')
    (world / 'hidden/world.md').write_text('hidden')
    mine = tmp_path / 'mine'
    mine.mkdir()
    f.write(mine / 'task.json', {})
    comp = tmp_path / 'compile'
    comp.mkdir()
    for name in ('supervision.json', 'new_rubric.json'):
        f.write(comp / name, {})
    s = state()
    for role, path in [('world', world), ('mine', mine), ('compile', comp)]:
        s['current'][role] = {'path': path.name, 'hashes': f.files(path), 'inputs': 'public'}
    monkeypatch.setattr(runner.previous.method, 'task_result', lambda *a: {'candidate_task': 'visible task', 'contract': {}})
    for role in ('mine', 'compile', 'review', 'solve'):
        target = tmp_path / ('inputs-' + role)
        runner.build_inputs(tmp_path, s, role, target)
        names = f.files(target)
        assert 'reference_files/record.txt' in names
        assert not any('hidden' in name or name == 'SKILL.md' for name in names)
        if role in ('mine', 'solve'):
            assert 'supervision.json' not in names and 'new_rubric.json' not in names
        if role == 'mine':
            assert 'candidate_task.md' not in names
        if role == 'solve':
            assert 'task.json' not in names and 'public_context.json' not in names
    runner.build_inputs(tmp_path, s, 'consult', tmp_path / 'mine-consult', 'mine')
    assert (tmp_path / 'mine-consult/candidate_task.md').exists()


def test_status_does_not_create_run(tmp_path):
    with pytest.raises(FileNotFoundError):
        runner.report(tmp_path / 'absent')
    assert not (tmp_path / 'absent').exists()


def test_prepare_refuses_existing(tmp_path):
    with pytest.raises(FileExistsError):
        runner.prepare(tmp_path)


@pytest.mark.parametrize('author,target', [('world', 'mine'), ('mine', 'compile'), ('compile', 'mine')])
def test_handoff_commentary_never_becomes_downstream_input(author, target):
    s = state()
    s['sessions']['mine'] = {'id': 'old-miner'}
    request = f.handoff_request(s, author, target, 'Hidden intention and compiler interpretation')
    assert request == {'role': target}
    assert f.role_feedback(s, request) is None
    if target == 'mine':
        assert 'mine' not in s['sessions']


@pytest.mark.parametrize('role', ['mine', 'compile', 'consult', 'review', 'solve'])
def test_unbound_feedback_rejected_before_any_launch(tmp_path, role):
    s = state()
    with pytest.raises(ValueError, match='feedback_outside_role_visibility'):
        runner.run_turn(tmp_path, {}, s, {'role': role, 'feedback': {'from_role': 'world', 'reason': 'producer judgment'}})
    assert s['attempts'] == []
    assert not list(tmp_path.iterdir())


def test_only_same_snapshot_consultation_can_return_to_owner():
    s = state()
    s['current']['mine'] = entry('m1')
    request = {'role': 'mine', 'feedback': {'summary': 'Visible-only consultation'},
               'feedback_origin': 'consultation', 'feedback_role': 'mine', 'feedback_snapshot': 'm1'}
    assert f.role_feedback(s, request) == request['feedback']
    request['feedback_snapshot'] = 'old'
    with pytest.raises(ValueError):
        f.role_feedback(s, request)
    upstream = f.handoff_request(s, 'compile', 'world', 'Located material inconsistency')
    assert f.role_feedback(s, upstream)['from_role'] == 'compile'


def test_schema_adapts_output_location_to_current_work_mount(monkeypatch):
    from task_generator.production import agent_factory_tools as tools
    monkeypatch.setattr(f, 'read', lambda p: {'role': 'mine'})
    monkeypatch.setattr(f, 'files', lambda p: {})
    result = tools.client('schema', {})
    assert '/draft/task.json' in result['mine']
    assert '/draft/supervision.json' in result['compile']
    assert '/output' not in result['mine'] + result['compile']


def test_harness_schema_exposes_exact_calculation_contract(monkeypatch):
    from task_generator.production import agent_factory_tools as tools
    monkeypatch.setattr(f, 'read', lambda p: {'role': 'compile', 'protocol': 'task_factory_harness_v1'})
    monkeypatch.setattr(f, 'files', lambda p: {})
    result = tools.client('schema', {})
    contract = result['harness']['calculation_contract']
    assert contract['file'] == 'calculation_evidence.json'
    assert 'rubric_ids' in contract['shape']['calculations'][0]


def test_targeted_calculation_schema_includes_current_ids_and_hashes(tmp_path, monkeypatch):
    from task_generator.production import agent_factory_tools as tools
    draft = tmp_path / 'draft'
    inputs = tmp_path / 'inputs/reference_files'
    draft.mkdir()
    inputs.mkdir(parents=True)
    f.write(draft / 'new_rubric.json', {'criteria': [{'criterion_id': 'c1'}]})
    (inputs / 'a.csv').write_text('value\n1\n', encoding='utf-8')
    original_read, original_files = f.read, f.files
    def fake_read(path):
        if str(path) == '/workspace/role.json':
            return {'role': 'compile', 'protocol': 'task_factory_harness_v1'}
        if str(path) == '/draft/new_rubric.json':
            return original_read(draft / 'new_rubric.json')
        raise AssertionError(path)
    def fake_files(path):
        if str(path) == '/draft':
            return original_files(draft)
        if str(path) == '/workspace/inputs/reference_files':
            return original_files(inputs)
        if str(path) == '/workspace/inputs':
            return original_files(inputs.parent)
        raise AssertionError(path)
    monkeypatch.setattr(f, 'read', fake_read)
    monkeypatch.setattr(f, 'files', fake_files)
    result = tools.client('schema', {'artifact': 'calculation_evidence'})
    assert result['contract']['preferred_version'] == 2
    assert result['current_rubric_ids'] == ['c1']
    assert result['candidate_reference_files'][0]['path'] == 'reference_files/a.csv'


def test_broker_draft_consult_auto_snapshot_and_live_status(tmp_path):
    draft = tmp_path / 'draft'
    draft.mkdir(parents=True)
    (draft / 'basis_draft.json').write_text('{}', encoding='utf-8')
    broker = Broker({'root': str(tmp_path), 'role': 'compile', 'parents': {'world': 'w', 'mine': 'm'}})
    hashes = f.files(draft)
    broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'mode': 'draft', 'hashes': hashes}})
    result = broker.handle({'action': 'consult', 'reason': 'Review the incomplete basis'})
    assert result['status'] == 'queued_end_turn_now'
    assert broker.pending['snapshot_automatic'] == 'created'
    status = broker.handle({'action': 'status'})
    assert status['latest_matching_snapshot'] == broker.pending['snapshot']
    assert status['current_check_modes'] == ['draft']


def test_batch_dispositions_are_atomic_and_snapshot_is_reused(tmp_path):
    draft = tmp_path / 'draft'
    draft.mkdir(parents=True)
    (draft / 'basis_draft.json').write_text('{"basis":"visible"}', encoding='utf-8')
    consultation = {'request_id': 'q1', 'finding_ids': ['1', '2']}
    broker = Broker({'root': str(tmp_path), 'role': 'compile', 'parents': {'world': 'w', 'mine': 'm'},
                     'consultations': [consultation]})
    base = {'decision': 'accept', 'reason': 'Addressed in basis',
            'evidence': [{'area': 'draft', 'path': 'basis_draft.json', 'locator': 'basis'}]}
    with pytest.raises(ValueError, match='every_finding_once'):
        broker.handle({'action': 'record-dispositions', 'request_id': 'q1',
                       'items': [{'finding_id': '1', **base}]})
    assert broker.dispositions == [] and not list((tmp_path / 'snapshots').iterdir())
    result = broker.handle({'action': 'record-dispositions', 'request_id': 'q1',
                            'snapshot_reason': 'Resolved consultation',
                            'items': [{'finding_id': '1', **base}, {'finding_id': '2', **base}]})
    assert result['recorded'] == 2
    broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'mode': 'ready',
                                                     'hashes': f.files(draft)}})
    broker.handle({'action': 'handoff', 'target': 'mine', 'reason': 'Ready'})
    assert broker.pending['snapshot'] == result['snapshot']
    assert broker.pending['snapshot_automatic'] == 'reused'


def test_stop_without_valid_artifact(tmp_path):
    broker = make_broker(tmp_path)
    broker.handle({'action': 'handoff', 'target': 'stop', 'reason': 'No usable records'})
    assert 'snapshot_entry' not in broker.pending


def test_client_contract_error_can_be_fixed_before_yield(tmp_path, monkeypatch):
    from task_generator.production import agent_factory_tools as ft
    draft, inputs = tmp_path / 'draft', tmp_path / 'inputs'
    draft.mkdir()
    (inputs / 'reference_files').mkdir(parents=True)
    (inputs / 'reference_files/a.txt').write_text('Visible work request')
    task = {'natural_task': True, 'rationale': 'Visible work'}
    f.write(draft / 'task.json', task)
    original = ft.check
    monkeypatch.setattr(ft, 'check', lambda *a: original('mine', draft, inputs))
    read, files = f.read, f.files
    monkeypatch.setattr(f, 'read', lambda p: {'role': 'mine'} if str(p) == '/workspace/role.json' else read(p))
    monkeypatch.setattr(f, 'files', lambda p: files(draft) if str(p) == '/draft' else files(p))
    calls = []
    monkeypatch.setattr(ft, 'broker_call', lambda action, args: calls.append(action))
    with pytest.raises(ValueError, match='task_requirements_missing'):
        ft.client('handoff', {'target': 'compile', 'snapshot': 's', 'reason': 'Ready'})
    assert not calls
    task.update(title='Review', prompt='Analyze the visible request.', requirements=[{'id': 'r1', 'requirement': 'Analyze',
        'expected_work_product': 'Analysis', 'basis': [{'path': 'reference_files/a.txt', 'locator': 'line 1', 'explanation': 'Work request'}]}],
        deliverables=[{'file_name': 'memo.docx', 'relative_path': 'deliverable_files/memo.docx', 'format': 'docx'}])
    f.write(draft / 'task.json', task)
    ft.client('handoff', {'target': 'compile', 'snapshot': 's', 'reason': 'Ready'})
    assert calls == ['log-check', 'handoff']


def test_disposition_and_check_follow_exact_revision(tmp_path):
    broker = make_broker(tmp_path)
    broker.handle({'action': 'save-process'})
    (broker.draft / 'candidate').mkdir()
    record = broker.draft / 'candidate/a.txt'
    record.write_text('uncertain source')
    snap = broker.handle({'action': 'snapshot', 'reason': 'Read version'})
    request = {'action': 'handoff', 'snapshot': snap['id'], 'target': 'mine', 'reason': 'Ready'}
    with pytest.raises(ValueError, match='current_version_check'):
        broker.handle(request)
    broker.config['consultations'] = [{'request_id': 'q1', 'finding_ids': ['1']}]
    broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'hashes': f.files(broker.draft)}})
    with pytest.raises(ValueError, match='disposition_required'):
        broker.handle(request)
    disposition = {'action': 'record-disposition', 'request_id': 'q1', 'finding_id': '1', 'snapshot': snap['id'],
                   'decision': 'reject', 'reason': 'Specific uncertainty is intentional work, no source assertion',
                   'evidence': [{'area': 'draft', 'path': 'candidate/a.txt', 'locator': 'line 1'}]}
    broker.handle(disposition)
    record.write_text('revised source')
    revised = broker.handle({'action': 'snapshot', 'reason': 'Revised'})
    request['snapshot'] = revised['id']
    with pytest.raises(ValueError, match='current_version_check'):
        broker.handle(request)
    broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'hashes': f.files(broker.draft)}})
    with pytest.raises(ValueError, match='disposition_required'):
        broker.handle(request)
    disposition['snapshot'] = revised['id']
    broker.handle(disposition)
    broker.handle(request)


@pytest.mark.parametrize('field,value', [('scope', 'other'), ('role', 'mine'), ('parents', {'world': 'old'}), ('normal_end', False)])
def test_wrong_session_refused_before_staging(tmp_path, field, value):
    s = state()
    s['sessions']['world'] = {'scope': tmp_path.name, 'role': 'world', 'parents': {}, 'normal_end': True, field: value}
    with pytest.raises(ValueError, match='session_outside'):
        runner.run_turn(tmp_path, {}, s, {'role': 'world'})
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('review_quality,fault', [('pass', None), ('uncertain', None), ('issue', None),
                                                ('pass', 'staging'), ('pass', 'timeout'), ('pass', 'stop'), ('pass', 'after_finish'),
                                                ('pass', 'batch'), ('issue', 'batch')])
def test_real_controller_roundtrip_with_transport_fixture(tmp_path, monkeypatch, review_quality, fault):
    """Only SSH/SCP and environment/identity checks are replaced; contracts stay real."""
    import json
    import shutil
    import subprocess
    from docx import Document
    from task_generator.production import agent_factory_tools as ft
    root = tmp_path / 'batch/cases/scope' if fault == 'batch' else tmp_path / 'scope'
    root.mkdir(parents=True)
    for name in ('public_context.json', 'professional_rules.json', 'sources.json'):
        f.write(root / 'public' / name, {'role': 'reviewer'})
    for role in f.ROLES:
        p = root / 'prompts' / (role + '.md')
        p.parent.mkdir(exist_ok=True)
        p.write_text(f.prompt(role), encoding='utf-8')
    s = state() | {'status': 'prepared', 'next': {'role': 'world'}, 'recoveries': 0,
                   'task_manual_edits': 0, 'first_failure': None}
    scope = {'remote': '/fixture/scope', 'dependency_remote': '/fixture/deps', 'code_hashes': {}}
    if fault == 'batch':
        from task_generator.production import agent_factory_batch as batch
        batch_root = tmp_path / 'batch'
        scope.update(batch_id='batch', seconds=10800, prompt_hashes={})
        cases = []
        for i, spec in enumerate(batch.CASES):
            child = root if i == 0 else batch_root / 'cases' / spec['id']
            f.write(child / 'scope.json', scope)
            f.write(child / 'receipt.json', s)
            cases.append(dict(spec, path=child.relative_to(batch_root).as_posix(), scope_sha=f.digest(child / 'scope.json')))
        f.write(batch_root / 'batch.json', {'cases': cases, 'seconds': 54000, 'code_hashes': {},
                'prompt_hashes': {}, 'source_bundle_hashes': {}})
        f.write(batch_root / 'receipt.json', {'status': 'prepared', 'position': 0, 'gates': {}, 'interventions': [],
                'first_failure': None, 'manifest_sha': f.digest(batch_root / 'batch.json')})
        monkeypatch.setattr(runner.base, 'code_hashes', lambda: {})
    f.write(root / 'receipt.json', s)
    f.write(root / 'readiness.json', {'tests_passed': True, 'code_hashes': {}})
    monkeypatch.setattr(runner, 'verify', lambda p: (scope, f.read(p / 'receipt.json')))
    monkeypatch.setattr(runner, 'environment', lambda *a: None)
    monkeypatch.setattr(runner.base, 'verify_remote_tree', lambda *a: None)
    monkeypatch.setattr(runner.base, '_scp_command', lambda a, b: [a, b])
    remote_root = tmp_path / 'remote'
    counts = {}
    observations = []

    def mapped(value):
        value = value.removeprefix(runner.HOST + ':')
        return remote_root / value.removeprefix('/fixture/') if value.startswith('/fixture/') else Path(value)

    def transfer(args, **kwargs):
        src, dst = map(mapped, args)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copyfile(src, dst)
        return subprocess.CompletedProcess(args, 0, '', '')

    def provider(turn):
        cfg = f.read(turn / 'broker_config.json')
        cfg['root'] = str(turn)
        role = cfg['role']
        counts[role] = counts.get(role, 0) + 1
        nth = counts[role]
        broker = Broker(cfg)
        draft, inputs = turn / 'draft', turn / 'workspace/inputs'
        names = set(f.files(inputs))
        task_prompt = (turn / 'workspace/TASK.md').read_text(encoding='utf-8')
        observations.append((role, names, task_prompt))
        assert not any('hidden' in name for name in names)
        if role in ('mine', 'review', 'solve'):
            assert not (turn / 'workspace/feedback.json').exists()
            assert 'AUTHOR_INTENT_MARKER' not in task_prompt
        basis = [{'path': 'reference_files/record.txt', 'locator': 'line 1', 'explanation': 'Visible work evidence'}]
        if role == 'world':
            if nth == 1:
                (draft / 'hidden').mkdir()
                (draft / 'hidden/process.md').write_text('Events and record sources')
                broker.handle({'action': 'save-process'})
                (draft / 'candidate').mkdir()
            (draft / 'candidate/record.txt').write_text('Reconcile record version ' + str(nth))
            (draft / 'hidden/world.md').write_text('HIDDEN_MARKER')
            f.write(draft / 'hidden/manifest.json', {'records': [{'path': 'record.txt', 'producer': 'clerk',
                    'business_purpose': 'review', 'source_dependencies': []}]})
        elif role == 'mine':
            f.write(draft / 'task.json', {'natural_task': True, 'rationale': 'Visible request', 'title': 'Review',
                    'prompt': 'Reconcile the record and explain any limitations.',
                    'requirements': [{'id': 'r1', 'requirement': 'Reconcile', 'expected_work_product': 'analysis', 'basis': basis}],
                    'deliverables': [{'file_name': 'memo.docx', 'relative_path': 'deliverable_files/memo.docx', 'format': 'docx'}]})
        elif role == 'compile':
            f.write(draft / 'supervision.json', {'status': 'compiled', 'upstream_issues': [], 'decisions': [{
                'decision_id': 'd1', 'requirement_ids': ['r1'], 'supported_judgment': 'Record allows analysis',
                'conditional_completion': 'Explain any remaining gap', 'gaps': [], 'follow_up': [], 'evidence': basis}]})
            f.write(draft / 'new_rubric.json', {'task_id': 'anonymous_task', 'criteria': [{
                'criterion_id': 'analysis', 'decision_id': 'd1', 'requirement': 'Reconcile the record', 'max_points': 1,
                'score_boundaries': [{'awarded': 0, 'description': 'No supported analysis'}, {'awarded': 1, 'description': 'Supported conditional analysis'}],
                'requirement_basis': [{'path': 'candidate_task.md', 'locator': 'paragraph 1', 'explanation': 'Visible assignment obligation'}],
                'evidence_paths': ['reference_files/record.txt'], 'applicability': 'Always applies',
                'acceptable_alternatives': 'Equivalent supported forms', 'verification': 'Read analysis and trace its sources'}]})
        elif role == 'consult':
            f.write(draft / 'consultation.json', {'summary': 'Check provenance', 'questions': [], 'findings': [{
                'path': 'reference_files/record.txt', 'locator': 'line 1', 'observation': 'Version requires explanation', 'limitation': 'Fixture only'}]})
        elif role == 'review':
            finding = {'path': 'reference_files/record.txt', 'locator': 'line 1', 'observation': 'Visible evidence', 'limitation': 'Fixture only'}
            f.write(draft / 'review.json', {'decision': review_quality,
                'checks': [{'dimension': d, 'status': review_quality, 'findings': [finding]} for d in runner.previous.method.DIMENSIONS],
                'requirement_coverage': [{'requirement_id': 'r1', 'status': review_quality, 'explanation': 'Covered'}],
                'rubric_coverage': [{'criterion_id': 'analysis', 'status': review_quality, 'explanation': 'Covered'}]})
        else:
            (draft / 'deliverable_files').mkdir()
            doc = Document()
            doc.add_paragraph('Analysis of visible record')
            doc.save(draft / 'deliverable_files/memo.docx')
        ft.check(role, draft, inputs)
        broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'role': role, 'hashes': f.files(draft)}})
        if role not in f.AUTHOR_ROLES:
            broker.handle({'action': 'finish'})
            if fault == 'after_finish' and role == 'review':
                with (draft / 'review.json').open('a') as handle:
                    handle.write(' ')
        if role in f.AUTHOR_ROLES:
            snap = broker.handle({'action': 'snapshot', 'reason': 'Actual version'})
            for c in cfg.get('consultations', []):
                for finding in c['finding_ids']:
                    broker.handle({'action': 'record-disposition', 'request_id': c['request_id'], 'finding_id': finding,
                        'snapshot': snap['id'], 'decision': 'accept', 'reason': 'Read and revised the actual record',
                        'evidence': [{'area': 'draft', 'path': 'candidate/record.txt', 'locator': 'line 1'}]})
            if role == 'world' and nth == 1:
                action = {'action': 'consult'}
            elif role == 'compile' and nth == 1:
                action = {'action': 'handoff', 'target': 'world'}
            elif role == 'compile':
                action = {'action': 'submit'}
            else:
                action = {'action': 'handoff', 'target': 'mine' if role == 'world' else 'compile'}
            broker.handle(action | {'snapshot': snap['id'], 'reason': 'AUTHOR_INTENT_MARKER'})
        session = 'world-owner' if role == 'world' else f'{role}-{nth}'
        (turn / 'agent.jsonl').write_text(json.dumps({'type': 'thread.started', 'thread_id': session}) + '\n' +
                                        json.dumps({'type': 'turn.completed', 'usage': {}}) + '\n')
        for name in ('stderr.txt', 'broker.log'):
            (turn / name).write_text('')

    def ssh(host, command, **kwargs):
        if command.startswith('mkdir '):
            if fault == 'staging' and len(f.read(root / 'receipt.json')['attempts']) == 1:
                raise subprocess.TimeoutExpired('synthetic transfer', 1)
            for piece in command.split(' && '):
                mapped(piece.split()[-1]).mkdir(parents=True, exist_ok=True)
        elif command.startswith('test -e '):
            return subprocess.CompletedProcess(command, 0 if mapped(command[8:]).exists() else 1, '', '')
        elif 'factory_broker_pid=$!' in command:
            number = len(f.read(root / 'receipt.json')['attempts'])
            provider(remote_root / 'scope' / f'turn_{number:02d}')
            if fault in ('timeout', 'stop'):
                if fault == 'stop':
                    f.write(root / 'scope.json', scope)
                    runner.stop(root)
                return subprocess.CompletedProcess(command, 124 if fault == 'timeout' else 143, '', '')
        return subprocess.CompletedProcess(command, 0, '', '')

    monkeypatch.setattr(runner.base, '_run', transfer)
    monkeypatch.setattr(runner.base, '_ssh', ssh)
    if fault == 'batch':
        batch_result = batch.execute(runner, batch_root)
    else:
        runner.execute(root)
    result = f.read(root / 'receipt.json')
    if fault == 'after_finish':
        assert result['status'] == 'incomplete'
        assert 'readonly_output_not_finished_or_changed' in result['stop_reason']
        assert result.get('review') is None and not counts.get('solve')
        return
    if fault in ('timeout', 'stop'):
        assert result['status'] == 'incomplete' and len(result['attempts']) == 1
        assert result['attempts'][0]['raw_hashes'] and counts == {'world': 1}
        assert (root / 'STOP').exists() == (fault == 'stop')
        return
    assert result['status'] == ('completed' if review_quality == 'pass' else 'quality_not_passed'), result
    assert counts['world'] == 3 and counts['mine'] == 2 and counts['compile'] == 2
    assert counts.get('solve', 0) == int(review_quality == 'pass')
    miners = [a for a in result['attempts'] if a['role'] == 'mine']
    assert all(a['resumed_session'] is None for a in miners)
    assert miners[0]['session_id'] != miners[1]['session_id']
    assert result['submitted'] and len(result['dispositions']) == 2
    assert (root / 'package/dataset_row.json').exists() == (review_quality == 'pass')
    assert result['attempts'][3 if fault == 'staging' else 2]['resumed_session'] == 'world-owner'
    assert result['recoveries'] == int(fault == 'staging')
    if fault == 'batch':
        assert batch_result['status'] == ('awaiting_readonly_review' if review_quality == 'pass' else 'development_not_passed')
        assert all(row['launches'] == 0 for row in batch_result['cases'][1:])
        assert f.read(batch_root / 'receipt.json')['deadline_epoch'] - result['deadline_epoch'] > 43000
        with pytest.raises(ValueError, match='batch_execution_required'):
            runner.execute(root)
        return
    before = len(result['attempts'])
    with pytest.raises(ValueError, match='scope_not_executable'):
        runner.execute(root)
    assert len(f.read(root / 'receipt.json')['attempts']) == before


@pytest.mark.parametrize('path', ['reference_files/a.txt; task.json', 'reference_files/a', 'reference_files/'])
def test_readonly_finish_reports_precise_path_error_and_allows_same_turn_fix(tmp_path, monkeypatch, path):
    from task_generator.production import agent_factory_tools as ft
    draft, inputs = tmp_path / 'draft', tmp_path / 'workspace/inputs'
    draft.mkdir()
    (inputs / 'reference_files').mkdir(parents=True)
    (inputs / 'reference_files/a.txt').write_text('Visible evidence')
    f.write(inputs / 'task.json', {'requirements': [{'id': 'r1'}]})
    f.write(inputs / 'new_rubric.json', {'criteria': [{'criterion_id': 'c1'}]})
    review = {'decision': 'pass', 'checks': [{'dimension': d, 'status': 'pass', 'findings': [{
        'path': path, 'locator': 'line 1', 'observation': 'Visible record', 'limitation': 'Fixture'}]}
        for d in runner.previous.method.DIMENSIONS],
        'requirement_coverage': [{'requirement_id': 'r1', 'status': 'pass', 'explanation': 'Covered'}],
        'rubric_coverage': [{'criterion_id': 'c1', 'status': 'pass', 'explanation': 'Covered'}]}
    f.write(draft / 'review.json', review)
    broker = Broker({'root': str(tmp_path), 'role': 'review', 'parents': {}})
    check, read, files = ft.check, f.read, f.files
    monkeypatch.setattr(ft, 'check', lambda *a: check('review', draft, inputs))
    monkeypatch.setattr(f, 'read', lambda p: {'role': 'review'} if str(p) == '/workspace/role.json' else read(p))
    monkeypatch.setattr(f, 'files', lambda p: files(draft) if str(p) == '/draft' else files(p))
    monkeypatch.setattr(ft, 'broker_call', lambda action, args: broker.handle({'action': action, **args}))
    with pytest.raises(ValueError, match=r'checks\[0\].findings\[0\].path'):
        ft.client('finish', {})
    assert broker.pending is None
    for row in review['checks']:
        row['findings'][0]['path'] = 'reference_files/a.txt'
    f.write(draft / 'review.json', review)
    assert ft.client('finish', {})['status'] == 'checked_end_turn_now'
    assert broker.pending['hashes'] == files(draft)
    with pytest.raises(ValueError, match='request_pending'):
        ft.client('finish', {})
