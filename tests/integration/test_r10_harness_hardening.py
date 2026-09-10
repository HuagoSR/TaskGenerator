"""New protocol regression through real controller and native-event boundaries."""
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration import test_r10_task_factory_harness as fixtures
from tests.integration import test_r10_agent_factory_pilot as pipeline
import r10_calculation_replay as replay
from task_generator.production import obligation_trace as trace
from task_generator.production import task_method_pilot as method
from task_generator.planning.rubric_compiler_v2 import TaskSpecificAtomicRubricV1, sum_atomic_rubric_points

h, f, tools, runner = fixtures.harness, fixtures.legacy, fixtures.tools, fixtures.runner


def test_atomic_rubric_is_binary_and_has_no_score_boundaries():
    value = TaskSpecificAtomicRubricV1.model_validate({
        'rubric_version': 'r10.atomic_rubric.1', 'task_id': 'anonymous_task',
        'scoring': 'binary_weighted', 'criteria': [{
            'criterion_id': 'price_conclusion', 'decision_id': 'd1',
            'requirement': 'States a supported price conclusion', 'max_points': 3,
            'full_credit_condition': 'Conclusion matches the cited evidence and stated scope.',
            'weight_rationale': 'Core professional judgment',
            'requirement_basis': [{'path': 'candidate_task.md', 'locator': 'Request',
                                   'explanation': 'The task requests this conclusion.'}],
            'evidence_paths': ['reference_files/quotes.xlsx'],
            'applicability': 'Applies to the evaluated purchase.',
            'acceptable_alternatives': 'A bounded conclusion with concrete follow-up is accepted.',
            'tolerance': 'No numeric tolerance applies.',
            'verification': 'Inspect the conclusion, evidence citation, and stated scope.'}]})
    assert value.total_points == 3
    assert 'score_boundaries' not in value.model_dump()['criteria'][0]
    assert sum_atomic_rubric_points(value, {'price_conclusion': 3}) == 1
    with pytest.raises(ValueError, match='zero_or_full'):
        sum_atomic_rubric_points(value, {'price_conclusion': 2})
    with pytest.raises(Exception):
        TaskSpecificAtomicRubricV1.model_validate({**value.model_dump(), 'criteria': [
            {**value.model_dump()['criteria'][0], 'max_points': 0}]})


def test_quality_role_graph_is_versioned():
    old = fixtures.state()
    old['current']['world'] = fixtures.entry('world', 'w', {})
    old['current']['mine'] = fixtures.entry('mine', 'm', {'world': 'w'})
    assert h.expected_parents(old, 'compile') == {'world': 'w', 'mine': 'm'}
    quality = fixtures.state() | {'candidate_edit_version': 1}
    quality['current']['world'] = fixtures.entry('world', 'w', {})
    quality['current']['mine'] = fixtures.entry('mine', 'm', {'world': 'w'})
    assert h.expected_parents(quality, 'edit') == {'world': 'w', 'mine': 'm'}
    quality['current']['edit'] = fixtures.entry('edit', 'e', {'world': 'w', 'mine': 'm'})
    assert h.expected_parents(quality, 'compile') == {'world': 'w', 'mine': 'm', 'edit': 'e'}


def test_atomic_supervision_cannot_hide_scoring_rules(tmp_path):
    inputs, draft = tmp_path / 'inputs', tmp_path / 'draft'
    (inputs / 'reference_files').mkdir(parents=True); draft.mkdir()
    (inputs / 'reference_files/record.txt').write_text('Quoted total: 10')
    (inputs / 'candidate_task.md').write_text('Assess the quoted price.')
    f.write(inputs / 'deliverable_contract.json', {'deliverables': []})
    f.write(inputs / 'task.json', {'requirements': [{'id': 'r1'}]})
    decision = {'decision_id': 'd1', 'requirement_ids': ['r1'],
                'reference_analysis': 'The visible record supports a bounded price assessment.',
                'known_facts': ['Quoted total is 10'], 'uncertainties': [], 'follow_up': [],
                'evidence': [{'path': 'reference_files/record.txt', 'locator': 'line 1',
                              'explanation': 'Shows the quoted total.'}]}
    f.write(draft / 'supervision.json', {'status': 'compiled', 'upstream_issues': [],
                                         'decisions': [decision]})
    f.write(draft / 'new_rubric.json', {
        'rubric_version': 'r10.atomic_rubric.1', 'task_id': 'anonymous_task',
        'scoring': 'binary_weighted', 'criteria': [{
            'criterion_id': 'assessment', 'decision_id': 'd1',
            'requirement': 'Provides a supported price assessment', 'max_points': 3,
            'full_credit_condition': 'States a conclusion and supports it with the quoted total.',
            'weight_rationale': 'Core professional judgment',
            'requirement_basis': [{'path': 'candidate_task.md', 'locator': 'line 1',
                                   'explanation': 'Explicitly requests the assessment.'}],
            'evidence_paths': ['reference_files/record.txt'],
            'applicability': 'Applies to this quoted purchase.',
            'acceptable_alternatives': 'A bounded conclusion with follow-up is acceptable.',
            'tolerance': 'No numeric tolerance applies.',
            'verification': 'Inspect the conclusion and cited quoted total.'}]})
    assert method.atomic_compilation_result(draft, inputs)['scoring'] == 'binary_weighted'
    decision['conditional_completion'] = 'Hidden stricter scoring path'
    f.write(draft / 'supervision.json', {'status': 'compiled', 'upstream_issues': [],
                                         'decisions': [decision]})
    with pytest.raises(ValueError, match='scoring semantics'):
        method.atomic_compilation_result(draft, inputs)


@pytest.mark.parametrize('quality,fault', [('pass', None), ('issue', None), ('uncertain', None),
                                         ('pass', 'timeout'), ('pass', 'after_finish'),
                                         ('pass', 'collection_retry')])
def test_actual_harness_full_lifecycle(tmp_path, monkeypatch, quality, fault):
    pipeline.test_real_controller_roundtrip_with_transport_fixture(
        tmp_path, monkeypatch, quality, fault, harness_protocol=True)


def obligation_fixture(tmp_path):
    draft, inputs = fixtures.make_structured_calculation(tmp_path)
    (inputs / 'candidate_task.md').write_text('Analyze the provided amounts.')
    f.write(draft / 'basis_draft.json', {'requirements': [{
        'requirement_id': 'r1', 'obligation': 'Analyze amounts', 'basis_kind': 'explicit',
        'rubric_ids': ['c1'], 'candidate_obligation_refs': [{
            'path': 'candidate_task.md', 'locator': 'line 1', 'explanation': 'Request',
            'sha256': f.digest(inputs / 'candidate_task.md')}]}]})
    return draft, inputs


def test_trace_actual_diff_cannot_be_hidden_by_empty_declaration(tmp_path):
    draft, inputs = obligation_fixture(tmp_path)
    initial = inputs / 'initial_basis'
    initial.mkdir()
    for name in ('basis_draft.json', 'new_rubric.json', 'calculation_evidence.json'):
        shutil.copyfile(draft / name, initial / name)
    rubric = f.read(draft / 'new_rubric.json')
    rubric['criteria'][0]['requirement'] = 'Also perform additional independent analysis'
    f.write(draft / 'new_rubric.json', rubric)
    f.write(draft / 'comparison.json', {'initial_basis_snapshot': 'initial', 'requirement_changes': []})
    with pytest.raises(ValueError, match='actual change IDs'):
        trace.validate(draft, inputs, True, 'initial')
    changes = trace.actual_changes(initial, draft)
    f.write(draft / 'comparison.json', {'initial_basis_snapshot': 'initial', 'requirement_changes': [
        {'change_id': item['change_id'], 'change_type': item['change_type'], 'description': 'Explain real change',
         'rubric_ids': ['c1']} for item in changes]})
    trace.validate(draft, inputs, True, 'initial')


@pytest.mark.parametrize('kind', trace.KINDS)
def test_classified_obligation_support(tmp_path, kind):
    draft, inputs = obligation_fixture(tmp_path)
    basis = f.read(draft / 'basis_draft.json')
    row = dict(basis['requirements'][0], requirement_id='r2', basis_kind=kind)
    if kind == 'material_instruction':
        row['candidate_obligation_refs'] = [{'path': 'reference_files/amounts.json', 'locator': 'request',
            'explanation': 'Applicability remains professional review', 'sha256': f.digest(inputs / 'reference_files/amounts.json')}]
    if kind == 'necessary_derivation':
        row.update(serves_requirement_id='r1', necessity='Needed to reconcile', alternative_paths='Equivalent summation')
    if kind == 'optional':
        row['rubric_ids'] = []
    basis['requirements'].append(row)
    f.write(draft / 'basis_draft.json', basis)
    trace.validate(draft, inputs, False, None)
    if kind == 'optional':
        row['rubric_ids'] = ['c1']
        f.write(draft / 'basis_draft.json', basis)
        with pytest.raises(ValueError, match='optional analysis'):
            trace.validate(draft, inputs, False, None)


@pytest.mark.parametrize('source', ['task.json', 'design_intent.json', 'initial_basis/basis_draft.json'])
def test_internal_obligation_sources_rejected(tmp_path, source):
    draft, inputs = obligation_fixture(tmp_path)
    basis = f.read(draft / 'basis_draft.json')
    basis['requirements'][0]['candidate_obligation_refs'][0]['path'] = source
    f.write(draft / 'basis_draft.json', basis)
    with pytest.raises(ValueError, match='candidate-visible sources only'):
        trace.validate(draft, inputs, False, None)


def test_explicit_cli_input_never_reads_stdin(tmp_path):
    class OpenPipe(io.StringIO):
        def read(self, *args):
            raise AssertionError('would block')
    assert tools.cli_payload(['tool', 'check', '{}'], OpenPipe()) == {}
    payload = tmp_path / 'request.json'
    payload.write_text('{}')
    assert tools.cli_payload(['tool', 'check', '--input-file', str(payload)], OpenPipe(), (tmp_path,)) == {}
    with pytest.raises(ValueError, match='json_object'):
        tools.cli_payload(['tool', 'check', '[]'], OpenPipe())


@pytest.mark.parametrize('actual,expected', [(True, 1), (False, 0), (1, True), ('1', 1)])
def test_replay_scalar_types_cannot_alias(tmp_path, actual, expected):
    draft, _ = fixtures.make_structured_calculation(tmp_path)
    manifest = f.read(draft / 'calculation_evidence.json')
    manifest['calculations'] = [dict(manifest['calculations'][0], result_pointer='/value', expected={'value': expected, 'tolerance': 0})]
    result = runner.compare_calculation_results(manifest, {'status': 'executed', 'executions': [
        {'execution_id': 'structured', 'output': {'value': actual}}]})
    assert result['status'] == 'mismatch'


def test_canonical_duplicate_script_rejected(tmp_path):
    draft, inputs = fixtures.make_structured_calculation(tmp_path)
    manifest = f.read(draft / 'calculation_evidence.json')
    manifest['executions'].append(dict(manifest['executions'][0], execution_id='alias', script='./structured.py'))
    f.write(draft / 'calculation_evidence.json', manifest)
    with pytest.raises(ValueError, match='duplicate script'):
        h.validate_calculation_bundle(draft, inputs)


@pytest.mark.parametrize('stream', ['stdout', 'stderr'])
def test_output_limit_stops_running_script(stream):
    result = replay.bounded_run([sys.executable, '-c', f'import sys,time;sys.{stream}.write("x"*100000);sys.{stream}.flush();time.sleep(10)'], 2, {}, output_limit=1024)
    assert result.limit_error == 'output_exceeds_1_mib'
    assert len(result.stdout) <= 1024 and len(result.stderr) <= 1024


def test_bounded_script_timeout():
    with pytest.raises(subprocess.TimeoutExpired):
        replay.bounded_run([sys.executable, '-c', 'import time;time.sleep(10)'], .1, {})


def test_replay_preserves_failure_when_script_removes_itself(tmp_path):
    scripts, inputs = tmp_path / 'scripts', tmp_path / 'inputs'
    scripts.mkdir()
    inputs.mkdir()
    script = scripts / 'remove_self.py'
    script.write_text(
        'import json, pathlib\npathlib.Path(__file__).unlink()\nprint(json.dumps({"value": 1}))\n',
        encoding='utf-8',
    )
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'version': 2, 'executions': [{
        'execution_id': 'remove_self', 'script': script.name, 'sources': []}]}), encoding='utf-8')
    output = tmp_path / 'result.json'
    assert replay.main(scripts, inputs, manifest, output, 10) == 1
    result = json.loads(output.read_text(encoding='utf-8'))
    assert result['status'] == 'error'
    assert result['executions'][0]['error'] == 'execution_input_changed'
    assert result['executions'][0]['script_sha256'] is None


def test_record_pages_preserve_long_unicode_values():
    records = [{'cell': 'A1', 'value': '中文' * 1000}, {'cell': 'A2', 'value': 'tail'}]
    offset = fragment = 0
    pieces = []
    page = tools._page_records(iter(records), {'offset': offset}, 100)
    while 'record_json_fragment' in page:
        pieces.append(page['record_json_fragment'])
        assert len(page['record_json_fragment'].encode()) <= 100
        offset, fragment = page['next_offset'], page['next_fragment_offset']
        page = tools._page_records(iter(records), {'offset': offset, 'fragment_offset': fragment}, 100)
    assert json.loads(''.join(pieces)) == records[0]
    assert page['records'] == [records[1]]


def test_programmatic_profile_guard_precedes_preparation(tmp_path):
    with pytest.raises(ValueError, match='mutually_exclusive'):
        fixtures.batch_runner.prepare(tmp_path / 'new', None, None, None, None,
                                      profile='frozen-validation-v1', parent=tmp_path)
    assert not (tmp_path / 'new').exists()


def test_microtest_preparation_uses_real_fingerprint_and_candidate_builder(tmp_path):
    import run_r10_harness_microtest as micro
    readiness = tmp_path / 'readiness.json'
    f.write(readiness, {'tests_passed': True, 'commands': ['synthetic offline readiness']})
    root = tmp_path / 'micro'
    scope = micro.prepare(root, readiness)
    runner.verify(root)
    assert scope['max_launches'] == 3 and scope['seconds'] == 1800
    assert scope['terminal_reserve_seconds'] == 0
    assert 'src/task_generator/production/obligation_trace.py' in scope['runtime_hashes']
    state = f.read(root / 'receipt.json')
    runner.build_inputs(root, state, 'devsolve', tmp_path / 'dev', protocol=scope['protocol'])
    runner.build_inputs(root, state, 'solve', tmp_path / 'blind', protocol=scope['protocol'])
    assert f.files(tmp_path / 'dev') == f.files(tmp_path / 'blind')
    assert 'task.json' not in f.files(tmp_path / 'dev')
    with pytest.raises(ValueError, match='microtest_entry_required'):
        runner.run_turn(root, scope, state, {'role': 'compile'})


def test_microtest_budget_and_action_stop_cannot_expand_production(tmp_path):
    state = fixtures.state() | {'budget_limits': {'max_launches': 3, 'production_launches': 3,
        'seconds': 1800, 'per_launch_seconds': 600, 'terminal_reserve_seconds': 0}}
    assert h.cap(state, 'compile', timestamp=1) == 600
    state['attempts'] = [{'role': 'compile'}, {'role': 'consult'}, {'role': 'compile'}]
    with pytest.raises(ValueError, match='launch_budget'):
        h.cap(state, 'compile', timestamp=1)
    (tmp_path / 'draft').mkdir()
    broker = tools.Broker({'root': str(tmp_path), 'role': 'compile', 'purpose': 'tool_microtest'})
    with pytest.raises(ValueError, match='outside_microtest'):
        broker.handle({'action': 'submit'})


def test_call_events_distinguish_internal_check(tmp_path, monkeypatch):
    cfg = {'event_version': 2}
    calls = []
    original = tools._client
    def fake(action, args):
        if action == 'replay':
            tools.client('check', {})
        return {}
    monkeypatch.setattr(f, 'read', lambda p: cfg)
    monkeypatch.setattr(tools, '_client', fake)
    monkeypatch.setattr(tools, 'broker_call', lambda action, args: calls.append(args['record']))
    tools.client('replay', {})
    assert [r['origin'] for r in calls] == ['internal', 'explicit']
    assert calls[0]['parent_call_id'] == calls[1]['call_id']


def test_resumed_status_matches_real_current_draft_and_invalidates_changes(tmp_path):
    (tmp_path / 'draft').mkdir()
    artifact = tmp_path / 'draft/a.txt'
    artifact.write_text('same')
    broker = tools.Broker({'root': str(tmp_path), 'role': 'compile', 'parents': {'world': 'w'},
        'starting_snapshot': {'id': 'c', 'hashes': f.files(tmp_path / 'draft'), 'parents': {'world': 'w'}},
        'passed_replay_snapshots': ['c'], 'workflow_status': {'legal_next_actions': ['submit']}})
    assert broker.handle({'action': 'status'})['passing_replay_current']
    artifact.write_text('changed')
    result = broker.handle({'action': 'status'})
    assert not result['passing_replay_current'] and 'submit' not in result['legal_next_actions']


@pytest.mark.parametrize('role', ['consult', 'review'])
@pytest.mark.parametrize('citation', ['basis_draft.json', 'calculation_evidence.json', 'calculation_scripts/run.py'])
def test_provided_teacher_evidence_can_be_cited_only_in_new_review_protocol(tmp_path, role, citation):
    draft, inputs = tmp_path / 'draft', tmp_path / 'inputs'
    draft.mkdir(); inputs.mkdir()
    f.write(inputs / citation, {'synthetic': True})
    f.write(inputs / 'task.json', {'requirements': [{'id': 'r1'}]})
    f.write(inputs / 'new_rubric.json', {'criteria': [{'criterion_id': 'c1'}]})
    finding = {'path': citation, 'locator': 'line 1', 'observation': 'Review supplied teacher basis', 'limitation': 'Synthetic'}
    if role == 'consult':
        f.write(draft / 'consultation.json', {'summary': 'Review', 'questions': [], 'findings': [finding]})
    else:
        f.write(draft / 'review.json', {'decision': 'pass', 'checks': [
            {'dimension': d, 'status': 'pass', 'findings': [finding]} for d in runner.previous.method.DIMENSIONS],
            'requirement_coverage': [{'requirement_id': 'r1', 'status': 'pass', 'explanation': 'Fixture'}],
            'rubric_coverage': [{'criterion_id': 'c1', 'status': 'pass', 'explanation': 'Fixture'}]})
    assert tools.check(role, draft, inputs, 'task_factory_harness_v1')['status'] == 'completed'
    with pytest.raises(ValueError):
        tools.check(role, draft, inputs)
    with pytest.raises(ValueError, match='allowlist'):
        runner.previous.method.reference(inputs, citation, candidate_only=True, extra_allowed=[citation])


@pytest.mark.parametrize('citation', ['initial_basis/basis_draft.json', 'development_trial/memo.txt', 'design_intent.json'])
def test_historical_or_trial_material_does_not_become_review_evidence(tmp_path, citation):
    f.write(tmp_path / citation, {'synthetic': True})
    extra = tools.teacher_citation_paths(tmp_path, 'task_factory_harness_v1')
    with pytest.raises(ValueError, match='allowlist'):
        runner.previous.method.reference(tmp_path, citation, extra_allowed=extra)


@pytest.mark.parametrize('artifact', ['supervision', 'consultation'])
def test_missing_native_schema_queries_are_now_discoverable(tmp_path, monkeypatch, artifact):
    read, files = f.read, f.files
    monkeypatch.setattr(f, 'read', lambda p: {'role': 'compile', 'protocol': 'task_factory_harness_v1'}
                        if str(p) == '/workspace/role.json' else read(p))
    monkeypatch.setattr(f, 'files', lambda p: {} if str(p).startswith(('/workspace', '/draft')) else files(p))
    result = tools.client('schema', {'artifact': artifact})
    assert result['contract']['file'] == artifact + '.json'


def test_native_inventory_and_list_path_shapes_are_supported(monkeypatch):
    monkeypatch.setattr(tools, '_inspect_one', lambda area, path, args: {'area': area, 'path': path})
    assert tools.inspect({'area': 'inputs', 'mode': 'inventory'})['path'] == '.'
    result = tools.inspect({'area': 'inputs', 'path': ['a.txt', 'b.txt']})
    assert set(result['items']) == {'a.txt', 'b.txt'}


def test_supervision_error_is_located_and_rubric_subject_preserved(tmp_path):
    f.write(tmp_path / 'supervision.json', {'status': 'complete'})
    with pytest.raises(ValueError) as error:
        runner.previous.method.compilation_result(tmp_path, tmp_path)
    issue = tools.issue_for(error.value)
    assert issue['artifact'] == 'supervision' and issue['path'] == 'supervision.json.status'
    assert issue['code'] == 'invalid_supervision'
    issue = tools.issue_for(ValueError('new_rubric.json.criteria[total].evidence_paths[0]: rubric_basis_not_candidate_visible'))
    assert issue['criterion_id'] == 'total' and issue['artifact'] == 'rubric'
