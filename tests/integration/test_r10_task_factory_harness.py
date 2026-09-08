import json
import io
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]
import run_r10_agent_factory_pilot as runner
import run_r10_task_factory_harness as batch_runner
from task_generator.production import agent_factory as legacy
from task_generator.production import agent_factory_tools as tools
from task_generator.production import task_factory_harness as harness


def entry(role, identity, parents, hashes=None):
    return {'id': identity, 'role': role, 'parents': parents, 'hashes': hashes or {'x': identity}}


def state():
    return {'attempts': [], 'current': {}, 'sessions': {}, 'checks': [], 'consultations': [],
            'dispositions': [], 'submitted': False, 'calculation_replays': [],
            'compile_stage': 'basis', 'upstream_revisions': 0}


def test_harness_budget_reserves_terminal_roles():
    receipt = state()
    receipt['deadline_epoch'] = 10_000
    receipt['attempts'] = [{'role': 'world'}] * 14
    with pytest.raises(ValueError, match='launch_budget'):
        harness.cap(receipt, 'compile', timestamp=1)
    assert harness.cap(receipt, 'review', timestamp=1) == 1800
    receipt['attempts'].append({'role': 'review'})
    assert harness.cap(receipt, 'solve', timestamp=1) == 1800


def test_continuation_budget_counts_prior_launches():
    receipt = state() | {'prior_launches': 2, 'prior_production_launches': 2,
                         'deadline_epoch': 10_000}
    receipt['attempts'] = [{'role': 'world'}] * 12
    with pytest.raises(ValueError, match='launch_budget'):
        harness.cap(receipt, 'compile', timestamp=1)
    assert harness.cap(receipt, 'review', timestamp=1) == 1800


def test_budget_status_uses_prior_and_current_attempts_consistently():
    receipt = state() | {'prior_launches': 11, 'prior_production_launches': 11,
                         'deadline_epoch': 10_000}
    receipt['attempts'] = [{'role': 'world'}, {'role': 'consult'}, {'role': 'compile'}]
    budget = harness.budget_state(receipt, timestamp=1)
    assert budget['launches_used'] == 14
    assert budget['launches_remaining'] == 2
    assert budget['production_launches_used'] == 14
    assert budget['production_launches_remaining'] == 0
    with pytest.raises(ValueError, match='launch_budget'):
        harness.cap(receipt, 'compile', timestamp=1)
    assert harness.cap(receipt, 'review', timestamp=1) == 1800
    receipt['attempts'].append({'role': 'review'})
    assert harness.cap(receipt, 'solve', timestamp=1) == 1800


def test_workflow_status_and_broker_expose_the_same_budget(tmp_path):
    draft = tmp_path / 'draft'
    draft.mkdir()
    value = state() | {'prior_launches': 11, 'prior_production_launches': 11,
                       'deadline_epoch': 10_000}
    value['attempts'] = [{'role': 'world'}, {'role': 'mine'}]
    status = harness.workflow_status(value, 'world', timestamp=1)
    broker = tools.Broker({'root': str(tmp_path), 'role': 'world',
                           'protocol': 'task_factory_harness_v1',
                           'workflow_status': status})
    assert broker.handle({'action': 'status'})['budget'] == status['budget']
    assert status['budget']['production_remaining_after_current'] == 0


def test_one_upstream_revision_invalidates_trial_and_downstream():
    value = state()
    value['current']['world'] = entry('world', 'w1', {})
    value['current']['mine'] = entry('mine', 'm1', {'world': 'w1'})
    value['current']['compile'] = entry('compile', 'c1', {'world': 'w1', 'mine': 'm1'})
    value['current']['devsolve'] = entry('devsolve', 'd1', {})
    value['development_trial'] = {'path': 'trial', 'hashes': {}}
    request = harness.handoff_request(value, 'compile', 'world', 'visible issue')
    assert request['feedback']['from_role'] == 'compile'
    assert value['upstream_revisions'] == 1
    harness.accept_snapshot(value, 'world', entry('world', 'w2', {}))
    assert set(value['current']) == {'world'}
    assert 'development_trial' not in value
    with pytest.raises(ValueError, match='revision_budget'):
        harness.handoff_request(value, 'compile', 'world', 'second issue')


def test_teacher_only_compile_revision_preserves_candidate_trial():
    value = state()
    value['current']['world'] = entry('world', 'w1', {})
    value['current']['mine'] = entry('mine', 'm1', {'world': 'w1'})
    value['current']['compile'] = entry('compile', 'c1', {'world': 'w1', 'mine': 'm1'})
    value['development_trial'] = {'path': 'trial', 'hashes': {},
                                  'candidate_parents': {'world': 'w1', 'mine': 'm1'}}
    harness.accept_snapshot(value, 'compile', entry(
        'compile', 'c2', {'world': 'w1', 'mine': 'm1'}, {'teacher': 'changed'}))
    assert harness.trial_is_current(value)
    assert value['development_trial']['candidate_parents'] == {'world': 'w1', 'mine': 'm1'}


def test_downstream_handoff_does_not_leak_author_reason():
    value = state()
    value['sessions']['mine'] = {'id': 'old'}
    request = harness.handoff_request(value, 'world', 'mine', 'hidden design intent')
    assert request == {'role': 'mine'}
    assert harness.role_feedback(value, request) is None
    assert 'mine' not in value['sessions']


def test_continuation_preserves_intermediate_snapshot_without_session(tmp_path):
    parent_case = tmp_path / 'parent_case'
    child = tmp_path / 'child'
    snapshot = parent_case / 'turns/03/raw/snapshots/w1'
    inputs = parent_case / 'turns/03/workspace/inputs'
    snapshot.mkdir(parents=True)
    inputs.mkdir(parents=True)
    trial = parent_case / 'development_trials/06'
    trial.mkdir(parents=True)
    (snapshot / 'candidate.txt').write_text('frozen', encoding='utf-8')
    (inputs / 'public.json').write_text('{}', encoding='utf-8')
    (trial / 'diagnostic.json').write_text('{}', encoding='utf-8')
    previous = state() | {
        'current': {'world': entry('world', 'w1', {}, legacy.files(snapshot)) | {
            'path': snapshot.relative_to(parent_case).as_posix(),
            'inputs': inputs.relative_to(parent_case).as_posix(),
        }},
        'next': {'role': 'mine', 'feedback_origin': 'upstream_issue',
                 'feedback': {'from_role': 'world', 'reason': 'private intent'}},
        'development_trial': {'path': trial.relative_to(parent_case).as_posix(),
                              'hashes': legacy.files(trial)},
        'stop_reason': 'ValueError:feedback_outside_role_visibility',
    }
    next_state = state()
    batch_runner.inherit_case_progress(parent_case, child, previous, next_state)
    assert next_state['next'] == {'role': 'mine'}
    assert next_state['sessions'] == {}
    inherited = next_state['current']['world']
    assert legacy.files(child / inherited['path']) == inherited['hashes']
    inherited_trial = next_state['development_trial']
    assert legacy.files(child / inherited_trial['path']) == inherited_trial['hashes']


def test_compile_consultation_can_precede_current_snapshot_replay(tmp_path, monkeypatch):
    root = tmp_path / 'scope'
    for directory in ('world/candidate', 'mine', 'compiler/calculation_scripts', 'public'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / 'world/candidate/source.txt').write_text('visible', encoding='utf-8')
    legacy.write(root / 'mine/task.json', {})
    for name in ('supervision.json', 'new_rubric.json', 'basis_draft.json',
                 'calculation_evidence.json'):
        legacy.write(root / 'compiler' / name, {})
    for name in ('public_context.json', 'professional_rules.json', 'sources.json'):
        legacy.write(root / 'public' / name, {})
    monkeypatch.setattr(runner.previous.method, 'task_result', lambda *_: {
        'candidate_task': 'Analyze the records.',
        'contract': {'deliverables': []},
    })
    value = state()
    value['current'] = {
        'world': entry('world', 'w1', {}, legacy.files(root / 'world')) |
                 {'path': 'world', 'inputs': 'public'},
        'mine': entry('mine', 'm1', {'world': 'w1'}, legacy.files(root / 'mine')) |
                {'path': 'mine', 'inputs': 'public'},
        'compile': entry('compile', 'c2', {'world': 'w1', 'mine': 'm1'},
                         legacy.files(root / 'compiler')) | {
            'path': 'compiler', 'inputs': 'public'},
    }
    target = tmp_path / 'target'
    runner.build_inputs(root, value, 'consult', target, 'compile', 'task_factory_harness_v1')
    assert (target / 'calculation_evidence.json').is_file()
    assert not (target / 'replay_results.json').exists()


def test_second_development_trial_is_rejected_in_same_turn(tmp_path):
    draft = tmp_path / 'draft'
    store = tmp_path / 'snapshots'
    draft.mkdir()
    store.mkdir()
    (draft / 'basis_draft.json').write_text('{}', encoding='utf-8')
    config = {'root': str(tmp_path), 'role': 'compile', 'parents': {}, 'consultations': [],
              'protocol': 'task_factory_harness_v1', 'passed_replay_snapshots': [],
              'development_trial_current': True,
              'workflow_status': {'development_trial_current': True,
                                  'budget': {'production_remaining_after_current': 1,
                                             'launches_remaining_after_current': 2}}}
    broker = tools.Broker(config)
    snapshot = broker.handle({'action': 'snapshot', 'reason': 'teacher-only refinement'})
    broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'arguments': {},
                                                     'ok': True, 'hashes': snapshot['hashes'],
                                                     'role': 'compile'}})
    with pytest.raises(ValueError, match='development_trial_already_completed'):
        broker.handle({'action': 'request-development-trial', 'snapshot': snapshot['id'],
                       'reason': 'repeat'})


def test_replay_pass_is_bound_to_exact_snapshot(tmp_path):
    draft = tmp_path / 'draft'
    draft.mkdir()
    (draft / 'basis_draft.json').write_text('{}', encoding='utf-8')
    status = {'development_trial_current': False,
              'budget': {'production_remaining_after_current': 1,
                         'launches_remaining_after_current': 2}}
    broker = tools.Broker({'root': str(tmp_path), 'role': 'compile', 'parents': {},
                           'consultations': [], 'protocol': 'task_factory_harness_v1',
                           'passed_replay_snapshots': ['old-snapshot'],
                           'development_trial_current': False, 'workflow_status': status})
    snapshot = broker.handle({'action': 'snapshot', 'reason': 'changed teacher files'})
    broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'hashes': snapshot['hashes']}})
    with pytest.raises(ValueError, match='current_calculation_replay'):
        broker.handle({'action': 'request-development-trial', 'snapshot': snapshot['id'],
                       'reason': 'must not use old replay'})


def make_calculation(tmp_path):
    inputs = tmp_path / 'inputs'
    draft = tmp_path / 'draft'
    (inputs / 'reference_files').mkdir(parents=True)
    (draft / 'calculation_scripts').mkdir(parents=True)
    source = inputs / 'reference_files/amounts.json'
    source.write_text('[10, 15, 20]', encoding='utf-8')
    script = draft / 'calculation_scripts/total.py'
    script.write_text("""import argparse,json,pathlib
p=argparse.ArgumentParser(); p.add_argument('--inputs'); a=p.parse_args()
v=json.loads((pathlib.Path(a.inputs)/'reference_files/amounts.json').read_text())
print(json.dumps({'value':sum(v)}))
""", encoding='utf-8')
    legacy.write(draft / 'new_rubric.json', {'criteria': [{'criterion_id': 'c1'}]})
    legacy.write(draft / 'calculation_evidence.json', {'version': '1', 'calculations': [{
        'calculation_id': 'total', 'rubric_ids': ['c1'], 'script': 'total.py',
        'sources': [{'path': 'reference_files/amounts.json', 'locator': 'all values',
                     'sha256': legacy.digest(source)}], 'unit': 'USD', 'scope': 'all rows',
        'method': 'sum', 'assumptions': [], 'expected': {'value': 45, 'tolerance': 0},
        'alternatives': []}]})
    return draft, inputs


def test_calculation_contract_and_offline_replay(tmp_path):
    draft, inputs = make_calculation(tmp_path)
    harness.validate_calculation_bundle(draft, inputs)
    output = tmp_path / 'result.json'
    execution = tmp_path / 'execution.json'
    legacy.write(execution, {'calculations': [{'calculation_id': 'total', 'script': 'total.py'}]})
    result = subprocess.run([sys.executable, str(ROOT / 'Test/r10_calculation_replay.py'),
                             '--scripts', str(draft / 'calculation_scripts'), '--inputs', str(inputs),
                             '--manifest', str(execution), '--output', str(output)])
    assert result.returncode == 0
    assert legacy.read(output)['calculations'][0]['value'] == 45
    compared = runner.compare_calculation_results(legacy.read(draft / 'calculation_evidence.json'), legacy.read(output))
    assert compared['status'] == 'passed'
    source = inputs / 'reference_files/amounts.json'
    source.write_text('[10]', encoding='utf-8')
    with pytest.raises(ValueError, match='exact sha256'):
        harness.validate_calculation_bundle(draft, inputs)


def test_calculation_contract_is_queryable_and_accepts_numeric_version(tmp_path):
    draft, inputs = make_calculation(tmp_path)
    evidence = legacy.read(draft / 'calculation_evidence.json')
    evidence['version'] = 1
    legacy.write(draft / 'calculation_evidence.json', evidence)
    harness.validate_calculation_bundle(draft, inputs)
    schema = harness.calculation_contract_schema()
    row = schema['shape']['calculations'][0]
    assert row['script'].startswith('filename.py relative')
    assert set(row) == {'calculation_id', 'rubric_ids', 'script', 'sources', 'unit',
                        'scope', 'method', 'assumptions', 'expected', 'alternatives'}


def test_calculation_contract_error_locates_missing_fields(tmp_path):
    draft, inputs = make_calculation(tmp_path)
    evidence = legacy.read(draft / 'calculation_evidence.json')
    del evidence['calculations'][0]['method']
    legacy.write(draft / 'calculation_evidence.json', evidence)
    with pytest.raises(ValueError, match=r'calculations\[0\].*method'):
        harness.validate_calculation_bundle(draft, inputs)


@pytest.mark.parametrize('tolerance', [-1, float('inf'), float('nan'), True])
def test_calculation_contract_rejects_invalid_tolerance(tmp_path, tolerance):
    draft, inputs = make_calculation(tmp_path)
    evidence = legacy.read(draft / 'calculation_evidence.json')
    evidence['calculations'][0]['expected']['tolerance'] = tolerance
    legacy.write(draft / 'calculation_evidence.json', evidence)
    with pytest.raises(ValueError, match='expected.tolerance'):
        harness.validate_calculation_bundle(draft, inputs)


def make_structured_calculation(tmp_path):
    draft, inputs = make_calculation(tmp_path)
    script = draft / 'calculation_scripts/structured.py'
    script.write_text(
        'import argparse,json\np=argparse.ArgumentParser(); p.add_argument("--inputs"); p.parse_args()\n'
        'print(json.dumps({"totals":{"quote":45,"valid":True},"lines":[10,35]}))\n',
        encoding='utf-8')
    source = inputs / 'reference_files/amounts.json'
    legacy.write(draft / 'calculation_evidence.json', {
        'version': 2,
        'executions': [{'execution_id': 'structured', 'script': 'structured.py',
                        'sources': [{'path': 'reference_files/amounts.json', 'locator': 'all values',
                                     'sha256': legacy.digest(source)}]}],
        'calculations': [
            {'calculation_id': 'total', 'execution_id': 'structured', 'result_pointer': '/totals/quote',
             'rubric_ids': ['c1'], 'unit': 'USD', 'scope': 'all rows', 'method': 'sum',
             'assumptions': [], 'expected': {'value': 45, 'tolerance': 0}, 'alternatives': []},
            {'calculation_id': 'valid', 'execution_id': 'structured', 'result_pointer': '/totals/valid',
             'rubric_ids': ['c1'], 'unit': 'boolean', 'scope': 'all rows', 'method': 'verify',
             'assumptions': [], 'expected': {'value': True, 'tolerance': 0}, 'alternatives': []},
        ]})
    return draft, inputs


def test_structured_calculation_executes_once_and_selects_multiple_values(tmp_path):
    draft, inputs = make_structured_calculation(tmp_path)
    manifest = harness.validate_calculation_bundle(draft, inputs)
    execution_manifest = tmp_path / 'execution.json'
    legacy.write(execution_manifest, {'version': 2, 'executions': [
        {'execution_id': 'structured', 'script': 'structured.py'}]})
    output = tmp_path / 'result.json'
    result = subprocess.run([sys.executable, str(ROOT / 'Test/r10_calculation_replay.py'),
                             '--scripts', str(draft / 'calculation_scripts'), '--inputs', str(inputs),
                             '--manifest', str(execution_manifest), '--output', str(output)], check=False)
    assert result.returncode == 0
    execution = legacy.read(output)
    assert len(execution['executions']) == 1
    compared = runner.compare_calculation_results(manifest, execution)
    assert compared['status'] == 'passed'
    assert [row['value'] for row in compared['calculations']] == [45, True]


def test_structured_calculation_rejects_bad_pointer_and_unused_execution(tmp_path):
    draft, inputs = make_structured_calculation(tmp_path)
    evidence = legacy.read(draft / 'calculation_evidence.json')
    evidence['calculations'][0]['result_pointer'] = 'totals/quote'
    legacy.write(draft / 'calculation_evidence.json', evidence)
    with pytest.raises(ValueError, match='RFC 6901'):
        harness.validate_calculation_bundle(draft, inputs)
    evidence['calculations'][0]['result_pointer'] = '/totals/quote'
    evidence['executions'].append({**evidence['executions'][0], 'execution_id': 'unused'})
    legacy.write(draft / 'calculation_evidence.json', evidence)
    with pytest.raises(ValueError, match='every execution'):
        harness.validate_calculation_bundle(draft, inputs)


def test_json_pointer_supports_escaped_members_and_requires_scalar():
    value = {'a/b': {'~key': [4]}}
    assert harness.resolve_json_pointer(value, '/a~1b/~0key/0') == 4
    with pytest.raises(ValueError, match='scalar'):
        harness.resolve_json_pointer(value, '/a~1b')


def test_calculation_executor_uses_one_shared_timeout_and_preserves_progress(tmp_path):
    scripts = tmp_path / 'scripts'
    inputs = tmp_path / 'inputs'
    scripts.mkdir()
    inputs.mkdir()
    for name in ('first', 'second'):
        (scripts / f'{name}.py').write_text(
            "import argparse,json,time\np=argparse.ArgumentParser();p.add_argument('--inputs');p.parse_args()\n"
            "time.sleep(0.7)\nprint(json.dumps({'value': 1}))\n", encoding='utf-8')
    manifest = tmp_path / 'execution.json'
    legacy.write(manifest, {'calculations': [
        {'calculation_id': 'first', 'script': 'first.py'},
        {'calculation_id': 'second', 'script': 'second.py'}]})
    output = tmp_path / 'result.json'
    result = subprocess.run([sys.executable, str(ROOT / 'Test/r10_calculation_replay.py'),
                             '--scripts', str(scripts), '--inputs', str(inputs),
                             '--manifest', str(manifest), '--output', str(output),
                             '--timeout-seconds', '1'])
    payload = legacy.read(output)
    assert result.returncode == 124
    assert payload['status'] == 'timeout'
    assert payload['calculations'][0]['status'] == 'executed'
    assert payload['calculations'][1]['status'] == 'timeout'


def test_replay_container_exposes_no_expected_answers_and_has_separate_output(tmp_path, monkeypatch):
    root = tmp_path / 'scope'
    snapshot, inputs = make_calculation(tmp_path)
    stored = root / 'versions/compile'
    stored.parent.mkdir(parents=True)
    snapshot.rename(stored)
    entry_value = {'id': 'compile1', 'path': 'versions/compile', 'hashes': legacy.files(stored)}
    state_value = state() | {'deadline_epoch': __import__('time').time() + 5000}
    attempt = {'ordinal': 3}
    commands = []

    def fake_ssh(host, command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=1 if command.startswith('test -e ') else 0,
                               stdout='', stderr='')

    monkeypatch.setattr(runner.base, '_ssh', fake_ssh)
    monkeypatch.setattr(runner.base, '_run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(runner.base, '_scp_command', lambda *args: ['scp'])
    result = runner.run_calculation_replay(
        root, {'dependency_remote': '/deps', 'remote': '/scope',
               'terminal_reserve_seconds': 3600}, state_value, attempt, entry_value, '/turn')
    docker_command = next(command for command in commands if 'docker run' in command)
    assert 'calculation_evidence.json' not in docker_command
    assert 'new_rubric.json' not in docker_command
    assert '/workspace/inputs/reference_files:/inputs/reference_files:ro' in docker_command
    assert '/replay_output:/result:rw' in docker_command
    assert '/turn:/result:rw' not in docker_command
    assert result['status'] == 'error'


def test_development_trial_is_candidate_only_and_compile_gets_it_later(tmp_path):
    root = tmp_path / 'scope'
    public = root / 'public'
    public.mkdir(parents=True)
    for name, value in [('public_context.json', {'role': 'analyst'}),
                        ('professional_rules.json', {}), ('sources.json', [])]:
        legacy.write(public / name, value)
    world = root / 'versions/world'
    (world / 'candidate').mkdir(parents=True)
    (world / 'candidate/record.txt').write_text('visible', encoding='utf-8')
    mine = root / 'versions/mine'
    mine.mkdir(parents=True)
    basis = [{'path': 'reference_files/record.txt', 'locator': 'line 1', 'explanation': 'visible'}]
    legacy.write(mine / 'task.json', {'natural_task': True, 'rationale': 'work', 'title': 'Analyze',
        'prompt': 'Analyze the record.', 'requirements': [{'id': 'r1', 'requirement': 'Analyze',
        'expected_work_product': 'memo', 'basis': basis}], 'deliverables': [{'file_name': 'memo.txt',
        'relative_path': 'deliverable_files/memo.txt', 'format': 'txt'}]})
    legacy.write(mine / 'design_intent.json', {'occupational_use': 'decision', 'analysis_points': ['x'],
        'likely_difficulties': ['y'], 'evidence': [{'path': 'reference_files/record.txt', 'locator': 'line 1'}]})
    value = state()
    value['current']['world'] = entry('world', 'w1', {}, legacy.files(world)) | {'path': 'versions/world'}
    original_inputs = root / 'mine_inputs'
    (original_inputs / 'reference_files').mkdir(parents=True)
    (original_inputs / 'reference_files/record.txt').write_text('visible', encoding='utf-8')
    legacy.write(original_inputs / 'public_context.json', {'role': 'analyst'})
    value['current']['mine'] = entry('mine', 'm1', {'world': 'w1'}, legacy.files(mine)) | {
        'path': 'versions/mine', 'inputs': 'mine_inputs'}
    trial_inputs = root / 'trial_inputs'
    runner.build_inputs(root, value, 'devsolve', trial_inputs, protocol='task_factory_harness_v1')
    names = legacy.files(trial_inputs)
    assert 'candidate_task.md' in names and 'public_context.json' in names
    assert 'task.json' in names and 'design_intent.json' not in names
    assert not any('rubric' in name or 'supervision' in name or 'hidden' in name for name in names)
    trial = root / 'trials/1'
    (trial / 'deliverable_files').mkdir(parents=True)
    (trial / 'deliverable_files/memo.txt').write_text('answer', encoding='utf-8')
    legacy.write(trial / 'diagnostic.json', {'evidence_used': [], 'calculations': [], 'ambiguities': [], 'barriers': []})
    value['development_trial'] = {'path': 'trials/1', 'hashes': legacy.files(trial),
                                  'candidate_parents': {'world': 'w1', 'mine': 'm1'}}
    compile_inputs = root / 'compile_inputs'
    runner.build_inputs(root, value, 'compile', compile_inputs, protocol='task_factory_harness_v1')
    assert 'design_intent.json' in legacy.files(compile_inputs)
    assert 'development_trial/diagnostic.json' in legacy.files(compile_inputs)


def test_broker_requires_replay_before_development_trial(tmp_path):
    draft, inputs = make_calculation(tmp_path)
    legacy.write(draft / 'basis_draft.json', {'requirements': [{'id': 'r1'}]})
    broker = tools.Broker({'root': str(tmp_path), 'role': 'compile', 'parents': {},
                           'protocol': 'task_factory_harness_v1', 'replay_passed_for_snapshot': False})
    snap = broker.handle({'action': 'snapshot', 'reason': 'basis'})
    broker.handle({'action': 'log-check', 'result': {'tool': 'check', 'hashes': harness.files(draft)}})
    with pytest.raises(ValueError, match='current_calculation_replay'):
        broker.handle({'action': 'request-development-trial', 'snapshot': snap['id'], 'reason': 'try'})


def test_two_case_manifest_is_development_not_validation():
    assert [row['id'] for row in batch_runner.CASES] == [
        'development_procurement_price', 'development_audit_reliability']
    assert batch_runner.PROTOCOL == 'task_factory_harness_v1'


def test_single_procurement_prepare_binds_scope_and_budget(tmp_path, monkeypatch):
    root = tmp_path / 'new_batch'
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'public.txt').write_text('source', encoding='utf-8')
    readiness = tmp_path / 'readiness.json'
    legacy.write(readiness, {'tests_passed': True, 'commands': ['targeted', 'full']})

    def fake_prepare(child, dependency_lock, dependency_remote, *, spec, source_bundle,
                     batch_id, protocol):
        child.mkdir(parents=True)
        scope = {'batch_id': batch_id, 'protocol': protocol, 'code_hashes': {}}
        legacy.write(child / 'scope.json', scope)
        legacy.write(child / 'receipt.json', state() | {
            'status': 'prepared', 'task_manual_edits': 0, 'recoveries': 0})
        return scope

    monkeypatch.setattr(batch_runner.runner, 'prepare', fake_prepare)
    result = batch_runner.prepare(
        root, source, tmp_path / 'lock.json', '/remote/deps', readiness,
        case_ids=('development_procurement_price',))
    manifest = legacy.read(root / 'batch.json')
    child = root / manifest['cases'][0]['path']
    assert result['launches_used'] == 0
    assert result['first_failure'] is None
    assert len(manifest['cases']) == 1
    assert manifest['max_launches'] == 16 and manifest['seconds'] == 14400
    assert legacy.read(child / 'scope.json')['batch_id'] == root.name


def test_harness_batch_clock_starts_only_at_first_semantic_launch(tmp_path):
    root = tmp_path / 'batch'
    child = root / 'cases/case'
    child.mkdir(parents=True)
    legacy.write(child / 'receipt.json', {'attempts': []})
    legacy.write(root / 'batch.json', {'cases': [{'path': 'cases/case'}],
        'max_launches': 16, 'seconds': 14400})
    legacy.write(root / 'receipt.json', {'status': 'running', 'position': 0,
                                         'started_at': None, 'deadline_epoch': None})
    (root / 'execution.lock').write_text('test', encoding='utf-8')
    assert harness.batch_cap(root, child, 'world', started=False) == 1800
    before = legacy.read(root / 'receipt.json')
    assert before['started_at'] is None and before['deadline_epoch'] is None
    state_value = legacy.read(child / 'receipt.json')
    state_value['attempts'].append({'role': 'world'})
    legacy.write(child / 'receipt.json', state_value)
    assert harness.batch_cap(root, child, 'world', started=True, appended=True) == 1800
    after = legacy.read(root / 'receipt.json')
    assert after['started_at'] and after['deadline_epoch']


def test_presemantic_controller_operation_does_not_consume_launch_budget():
    value = state() | {'deadline_epoch': None}
    value['attempts'].append({
        'ordinal': 1, 'role': 'world', 'status': 'incomplete',
        'reason': "TypeError:unsupported operand type(s) for -: 'NoneType' and 'float'"})
    budget = harness.budget_state(value, 'world', timestamp=1000)
    assert budget['launches_used'] == 0
    assert budget['production_launches_used'] == 0
    assert harness.cap(value, 'world', timestamp=1000) == 1800

    value['attempts'][0]['phase'] = 'collection'
    budget = harness.budget_state(value, 'world', timestamp=1000)
    assert budget['launches_used'] == 1


def test_batch_bound_scope_cannot_execute_directly(tmp_path, monkeypatch):
    root = tmp_path / 'case'
    root.mkdir()
    scope = {'batch_id': 'bound-batch'}
    receipt = state() | {'status': 'prepared', 'task_manual_edits': 0}
    monkeypatch.setattr(runner, 'verify', lambda value: (scope, receipt))
    with pytest.raises(ValueError, match='batch_execution_required'):
        runner.execute(root)


def test_controller_acceptance_failure_does_not_relabel_native_completion(tmp_path):
    value = state()
    value['attempts'] = [{'ordinal': 1, 'role': 'compile', 'status': 'native_completed',
                          'phase': 'output_check'}]
    runner.record_execution_failure(tmp_path, value, ValueError('current_calculation_replay_required'))
    assert value['attempts'][0]['status'] == 'native_completed'
    assert value['attempts'][0]['acceptance_status'] == 'failed'
    assert value['failure_category'] == 'case'


def test_harness_prompt_uses_absolute_tool_path():
    prompt = harness.prompt('world')
    assert '`/workspace/bin/factory-tools help`' in prompt


def test_factory_tool_accepts_json_argument_or_stdin():
    expected = {'area': 'inputs', 'path': 'SKILL.md'}
    assert tools.cli_payload(['factory-tools', 'inspect', json.dumps(expected)], io.StringIO('')) == expected
    assert tools.cli_payload(['factory-tools', 'inspect'], io.StringIO(json.dumps(expected))) == expected


def test_batch_stop_is_not_overwritten_by_completion(tmp_path, monkeypatch):
    root = tmp_path / 'batch'
    child = root / 'cases/case'
    child.mkdir(parents=True)
    legacy.write(child / 'scope.json', {'code_hashes': {}})
    legacy.write(child / 'receipt.json', {'status': 'prepared', 'attempts': [], 'task_manual_edits': 0,
        'current': {}, 'consultations': [], 'dispositions': [], 'submitted': False})
    legacy.write(root / 'batch.json', {'protocol': harness.__name__, 'seconds': 100, 'max_launches': 2,
        'per_case_seconds': 50, 'source_bundle_hashes': {}, 'cases': [{'id': 'case', 'path': 'cases/case',
        'scope_sha256': legacy.digest(child / 'scope.json')}]})
    (root / 'source_bundle').mkdir()
    legacy.write(root / 'receipt.json', {'status': 'prepared', 'manifest_sha256': legacy.digest(root / 'batch.json'),
        'position': 0, 'started_at': None, 'deadline_epoch': None, 'first_failure': None})
    monkeypatch.setattr(batch_runner, 'verify', lambda value: (legacy.read(root / 'batch.json'), legacy.read(root / 'receipt.json')))
    def stopped(value, **kwargs):
        assert (root / 'execution.lock').is_file()
        state = legacy.read(child / 'receipt.json')
        state['status'] = 'incomplete'
        legacy.write(child / 'receipt.json', state)
        (root / 'STOP').touch()
    monkeypatch.setattr(batch_runner.runner, 'execute', stopped)
    monkeypatch.setattr(batch_runner.runner, 'report', lambda value: {'launches_used': 0})
    result = batch_runner.execute(root)
    assert result['status'] == 'stopped'


def test_batch_records_terminal_case_failure_while_finishing_fixed_schedule(tmp_path, monkeypatch):
    root = tmp_path / 'batch'
    child = root / 'cases/case'
    child.mkdir(parents=True)
    legacy.write(root / 'batch.json', {'cases': [{'id': 'case', 'path': 'cases/case'}],
        'max_launches': 16, 'seconds': 14400, 'prior_launches': 0})
    legacy.write(root / 'receipt.json', {'status': 'prepared', 'position': 0,
        'deadline_epoch': None, 'first_failure': None})
    legacy.write(child / 'receipt.json', state() | {'status': 'prepared'})
    monkeypatch.setattr(batch_runner, 'verify', lambda value: (
        legacy.read(root / 'batch.json'), legacy.read(root / 'receipt.json')))

    def fake_execute(value, *, batch_root):
        current = legacy.read(child / 'receipt.json')
        current.update(status='incomplete', stop_reason='started_session_failed_no_redraw',
                       failure_category='case')
        legacy.write(child / 'receipt.json', current)

    monkeypatch.setattr(batch_runner.runner, 'execute', fake_execute)
    monkeypatch.setattr(batch_runner.runner, 'report', lambda value: {
        'status': 'incomplete', 'launches_used': 0, 'stop_reason': 'started_session_failed_no_redraw'})
    result = batch_runner.execute(root)
    assert result['status'] == 'completed'
    assert result['first_failure']['case_id'] == 'case'
