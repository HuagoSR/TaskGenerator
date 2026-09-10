"""Synthetic regression for versioned quality-diagnostic evidence."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Test'))

from task_generator.production import quality_diagnostics as quality
from task_generator.production import agent_factory as factory
from task_generator.production import agent_factory_tools as tools
from task_generator.production import task_method_pilot as method


def _rubric():
    return {'rubric_version': 'r10.atomic_rubric.1', 'task_id': 'anonymous_task',
            'scoring': 'binary_weighted', 'criteria': [{
                'criterion_id': 'assessment', 'requirement': 'Assess price evidence', 'max_points': 3,
                'full_credit_condition': 'States a supported bounded conclusion.',
                'applicability': 'Applies to this procurement.',
                'acceptable_alternatives': 'A supported affirmative conclusion is accepted when all stated evidence is sufficient.',
                'tolerance': 'No numeric tolerance applies.'}]}


def _basis():
    return {'requirements': [{'requirement_id': 'r1', 'rubric_ids': ['assessment']}]}


def _diagnostic(rubric, basis=None, calculations=None, decision='pass', alternative='pass', candidate_root=None):
    basis = _basis() if basis is None else basis
    calculations = {'calculations': []} if calculations is None else calculations
    view = quality.rubric_view(rubric, basis, calculations, candidate_root)
    criterion = view['criteria'][0]
    return {'version': quality.VERSION, 'rubric_sha256': quality.json_hash(rubric),
            'basis_sha256': quality.json_hash(basis),
            'calculation_evidence_sha256': quality.json_hash(calculations),
            'candidate_input_hashes': view['candidate_input_hashes'], 'decision': decision,
            'criteria': [{'criterion_id': 'assessment', 'criterion_sha256': criterion['criterion_sha256'],
                          'candidate_requirement_ids': ['r1'],
                          'atomicity': 'pass', 'atomicity_rationale': 'One conclusion is independently observable.',
                          'alternative_consistency': alternative,
                          'alternative_consistency_rationale': 'The stated evidence condition explains the alternative.',
                          'overlap': 'pass', 'overlap_rationale': 'No separate criterion repeats this conclusion.',
                          'clause_refs': {
                              'atomicity': ['/criteria/0/full_credit_condition'],
                              'alternative_consistency': ['/criteria/0/acceptable_alternatives'],
                              'overlap': ['/criteria/0/requirement']},
                          'overlap_criterion_ids': []}]}


def test_edit_diagnostic_distinguishes_internal_only_change_and_rejects_prompt_claim():
    source = {'natural_task': True, 'prompt': 'Assess the price.', 'rationale': 'Internal rationale',
              'deliverables': []}
    edited = {**source, 'rationale': 'Changed internal rationale'}
    result = {'candidate_task': 'Assess the price.', 'contract': {'deliverables': []}}
    diagnostic = quality.edit_difference(source, edited, result, result)
    assert diagnostic['effect'] == 'internal_only_change'
    with pytest.raises(ValueError, match='prompt claim'):
        quality.validate_edit_claims({'changes': [{'area': 'prompt', 'actual_change_paths': ['/rationale']}]}, diagnostic)


def test_edit_diagnostic_requires_a_claim_for_actual_candidate_change():
    source, edited = {'prompt': 'Assess.'}, {'prompt': 'Assess and document.'}
    before, after = {'candidate_task': 'Assess.', 'contract': {}}, {'candidate_task': 'Assess and document.', 'contract': {}}
    diagnostic = quality.edit_difference(source, edited, before, after)
    assert diagnostic['effect'] == 'candidate_input_changed'
    with pytest.raises(ValueError, match='lack an edit claim'):
        quality.validate_edit_claims({'changes': []}, diagnostic)
    quality.validate_edit_claims({'changes': [{'area': 'prompt', 'actual_change_paths': ['/prompt']}]}, diagnostic)


def test_editor_result_checks_actual_requirement_locator_when_quality_protocol_is_enabled(tmp_path):
    inputs, draft = tmp_path / 'inputs', tmp_path / 'draft'
    (inputs / 'reference_files').mkdir(parents=True)
    draft.mkdir()
    evidence = inputs / 'reference_files/record.txt'
    evidence.write_text('Price record', encoding='utf-8')
    source = {'natural_task': True, 'rationale': 'Natural downstream use.', 'title': 'Price review',
              'prompt': 'Review the price.', 'deliverables': [{'file_name': 'memo.txt',
                  'relative_path': 'deliverable_files/memo.txt', 'format': 'txt', 'creation_mode': 'create'}], 'requirements': [{
                  'id': 'r1', 'requirement': 'Review price evidence', 'expected_work_product': 'Memo',
                  'basis': [{'path': 'reference_files/record.txt', 'locator': 'line 1', 'explanation': 'Visible record'}]}]}
    changed = {**source, 'requirements': [{**source['requirements'][0], 'expected_work_product': 'Documented memo'}]}
    from task_generator.production import agent_factory as factory
    factory.write(inputs / 'task.json', source)
    record = {'version': 'r10.candidate_edit.1',
              'source_task_sha256': quality.json_hash(source), 'edited_task_sha256': quality.json_hash(changed),
              'changes': [{'change_id': 'r1', 'area': 'requirements', 'original_locator': 'requirements[0]',
                           'actual_change_paths': ['/requirements/0/expected_work_product'],
                           'edit_summary': 'Clarified internal work product.', 'business_reason': 'Keeps assignment traceable.',
                           'preserved_evidence': [{'path': 'reference_files/record.txt', 'locator': 'line 1',
                                                   'explanation': 'Still visible.'}],
                           'returned_judgment': 'Candidate still evaluates the evidence.'}]}
    factory.write(draft / 'task.json', changed)
    factory.write(draft / 'edit_record.json', record)
    assert method.editor_result(draft, inputs, quality_diagnostics_version=1)['edit_diagnostic']['effect'] == 'internal_only_change'
    record['changes'][0]['area'] = 'prompt'
    factory.write(draft / 'edit_record.json', record)
    with pytest.raises(ValueError, match='prompt claim'):
        method.editor_result(draft, inputs, quality_diagnostics_version=1)


def test_rubric_diagnostic_requires_complete_current_mapping_and_closed_issues():
    rubric, basis, calculations = _rubric(), _basis(), {'calculations': []}
    assert quality.validate_rubric_diagnostic(_diagnostic(rubric, basis, calculations), rubric, basis, calculations)['decision'] == 'pass'
    with pytest.raises(ValueError, match='pass requires'):
        quality.validate_rubric_diagnostic(_diagnostic(rubric, basis, calculations, alternative='issue'), rubric, basis, calculations)
    stale = _diagnostic(rubric, basis, calculations)
    stale['criteria'][0]['candidate_requirement_ids'] = []
    with pytest.raises(ValueError, match='basis mapping'):
        quality.validate_rubric_diagnostic(stale, rubric, basis, calculations)


def _relation_record(path, quote, sha, *, timestamp, precision, kind, observation_id):
    return {'observation_id': observation_id, 'path': path, 'locator': 'line 1', 'quote': quote,
            'sha256': sha, 'timestamp': timestamp, 'precision': precision, 'kind': kind}


def test_record_relations_detect_declared_knowledge_time_contradiction(tmp_path):
    root = tmp_path / 'candidate'
    root.mkdir()
    note, approval = root / 'note.md', root / 'approval.md'
    note.write_text('Prepared 2031-04-03T08:10Z and says approval occurred.', encoding='utf-8')
    approval.write_text('Approval timestamp 2031-04-03T09:45:20Z.', encoding='utf-8')
    record = {'version': quality.VERSION, 'observations': [
        _relation_record('note.md', 'Prepared 2031-04-03T08:10Z', quality.factory.digest(note),
                         timestamp='2031-04-03T08:10Z', precision='minute', kind='record_created', observation_id='note'),
        _relation_record('approval.md', 'Approval timestamp 2031-04-03T09:45:20Z', quality.factory.digest(approval),
                         timestamp='2031-04-03T09:45:20Z', precision='second', kind='event', observation_id='approval')],
        'relations': [{'relation_id': 'knowledge', 'subject_id': 'note', 'related_id': 'approval',
                       'constraint': 'subject_not_before_related',
                       'statement': 'A record asserting approval cannot predate that approval.'}]}
    result = quality.validate_record_relations(record, root, candidate_only=False)
    assert result['relations'][0]['status'] == 'issue'


def test_record_relations_preserves_precision_and_requires_timezone(tmp_path):
    root = tmp_path / 'candidate'
    root.mkdir()
    record = root / 'record.md'
    record.write_text('Prepared today', encoding='utf-8')
    value = {'version': quality.VERSION, 'observations': [
        _relation_record('record.md', 'Prepared today', quality.factory.digest(record),
                         timestamp='2026-09-10T10:15', precision='minute', kind='record_created', observation_id='r')],
        'relations': []}
    with pytest.raises(ValueError, match='ISO-8601 precision'):
        quality.validate_record_relations(value, root, candidate_only=False)


def test_rubric_diagnostic_is_bound_to_basis_calculations_and_candidate_files(tmp_path):
    root = tmp_path / 'inputs'
    (root / 'reference_files').mkdir(parents=True)
    (root / 'candidate_task.md').write_text('Assess the record.', encoding='utf-8')
    (root / 'reference_files/record.txt').write_text('Amount 42', encoding='utf-8')
    rubric, basis, calculations = _rubric(), _basis(), {'calculations': []}
    record = _diagnostic(rubric, basis, calculations, candidate_root=root)
    quality.validate_rubric_diagnostic(record, rubric, basis, calculations, root)
    (root / 'reference_files/record.txt').write_text('Amount 43', encoding='utf-8')
    with pytest.raises(ValueError, match='candidate identity'):
        quality.validate_rubric_diagnostic(record, rubric, basis, calculations, root)


def test_edit_claims_cover_internal_changes_and_do_not_double_count_compiled_appendix():
    source = {'prompt': 'Assess.', 'rationale': 'Internal', 'deliverables': []}
    edited = {'prompt': 'Assess.', 'rationale': 'Revised internal note', 'deliverables': [{
        'file_name': 'memo.txt', 'relative_path': 'deliverable_files/memo.txt', 'format': 'txt',
        'creation_mode': 'create'}]}
    before = {'candidate_task': 'Assess.', 'contract': {'deliverables': []}}
    after = {'candidate_task': 'Assess.\nCreate memo.txt.', 'contract': {'deliverables': edited['deliverables']}}
    diagnostic = quality.edit_difference(source, edited, before, after)
    assert diagnostic['candidate_changes'][0]['area'] == 'deliverable_contract'
    quality.validate_edit_claims({'changes': [
        {'area': 'deliverables', 'actual_change_paths': ['/deliverables/0']},
        {'area': 'metadata', 'actual_change_paths': ['/rationale']}],
    }, diagnostic)


@pytest.mark.parametrize(('timestamp', 'precision'), [
    ('2031-04-03T08:10:30Z', 'minute'), ('2031-04-03T08:10Z', 'second')])
def test_record_relations_rejects_fabricated_precision(tmp_path, timestamp, precision):
    root = tmp_path / 'candidate'; root.mkdir()
    path = root / 'record.md'; path.write_text(timestamp, encoding='utf-8')
    record = {'version': quality.VERSION, 'observations': [
        _relation_record('record.md', timestamp, quality.factory.digest(path), timestamp=timestamp,
                         precision=precision, kind='record_created', observation_id='r')], 'relations': []}
    with pytest.raises(ValueError, match='stated ISO-8601 precision'):
        quality.validate_record_relations(record, root, candidate_only=False)


def test_record_relation_locator_must_contain_quote(tmp_path):
    root = tmp_path / 'candidate'; root.mkdir()
    path = root / 'record.md'; path.write_text('first\nPrepared 2031-04-03T08:10Z', encoding='utf-8')
    record = {'version': quality.VERSION, 'observations': [
        _relation_record('record.md', 'Prepared 2031-04-03T08:10Z', quality.factory.digest(path),
                         timestamp='2031-04-03T08:10Z', precision='minute', kind='record_created', observation_id='r')],
        'relations': []}
    with pytest.raises(ValueError, match='cited line'):
        quality.validate_record_relations(record, root, candidate_only=False)


def _write_diagnostic_bundle(draft, inputs, *, decision='pass', alternative='pass'):
    (inputs / 'reference_files').mkdir(parents=True, exist_ok=True)
    (inputs / 'candidate_task.md').write_text('Assess the record.', encoding='utf-8')
    (inputs / 'reference_files/record.txt').write_text('Amount 42', encoding='utf-8')
    rubric, basis, calculations = _rubric(), _basis(), {'version': 2, 'executions': [], 'calculations': []}
    factory.write(draft / 'new_rubric.json', rubric)
    factory.write(draft / 'basis_draft.json', basis)
    factory.write(draft / 'calculation_evidence.json', calculations)
    factory.write(draft / 'rubric_diagnostic.json', _diagnostic(
        rubric, basis, calculations, decision=decision, alternative=alternative, candidate_root=inputs))
    return rubric, basis, calculations


def test_compile_ready_and_status_block_unresolved_diagnostic(tmp_path, monkeypatch):
    inputs, draft = tmp_path / 'workspace/inputs', tmp_path / 'draft'
    draft.mkdir(parents=True)
    _write_diagnostic_bundle(draft, inputs, decision='revision_required', alternative='issue')
    monkeypatch.setattr(method, 'atomic_compilation_result', lambda *_: {'status': 'completed'})
    from task_generator.production import task_factory_harness as harness
    monkeypatch.setattr(harness, 'validate_calculation_bundle', lambda *_: {'version': 2})
    with pytest.raises(Exception, match='unresolved diagnostics'):
        tools.check('compile', draft, inputs, 'task_factory_harness_v1', 'ready', 2,
                    atomic_rubric_version=1, quality_diagnostics_version=1)
    broker = tools.Broker({'root': str(tmp_path), 'role': 'compile', 'parents': {},
                           'quality_diagnostics_version': 1,
                           'workflow_status': {'legal_next_actions': ['submit', 'consult', 'status']}})
    result = broker.handle({'action': 'status'})
    assert result['quality_diagnostics']['rubric_decision'] == 'revision_required'
    assert 'submit' not in result['legal_next_actions']


def test_independent_nonpass_review_can_finish_with_open_diagnostics(tmp_path, monkeypatch):
    inputs, draft = tmp_path / 'inputs', tmp_path / 'draft'
    draft.mkdir(parents=True)
    rubric, basis, calculations = _write_diagnostic_bundle(
        draft, inputs, decision='revision_required', alternative='issue')
    for name in ('new_rubric.json', 'basis_draft.json', 'calculation_evidence.json'):
        factory.write(inputs / name, {'new_rubric.json': rubric, 'basis_draft.json': basis,
                                      'calculation_evidence.json': calculations}[name])
    factory.write(draft / 'review.json', {'checks': []})
    factory.write(draft / 'record_relations.json', {'version': quality.VERSION, 'observations': [],
                                                     'relations': [], 'not_applicable_reason': 'No dated relation in this small fixture.'})
    monkeypatch.setattr(method, 'review_result', lambda *_args, **_kwargs: {'quality': 'issue'})
    result = tools.check('review', draft, inputs, 'task_factory_harness_v1', 'ready',
                         quality_diagnostics_version=1)
    assert result['quality'] == 'issue'


def test_actual_controller_roundtrip_with_quality_protocol(tmp_path, monkeypatch):
    from tests.integration import test_r10_agent_factory_pilot as pipeline
    pipeline.test_real_controller_roundtrip_with_transport_fixture(
        tmp_path, monkeypatch, 'pass', None, harness_protocol=True, quality_diagnostics=True)


def test_documented_update_and_planned_event_are_explicitly_comparable(tmp_path):
    root = tmp_path / 'candidate'; root.mkdir()
    path = root / 'status.md'
    path.write_text('Created 2031-05-04T08:10Z.\nPlanned 2031-05-04T09:30Z.\nUpdated 2031-05-04T10:05Z.\n', encoding='utf-8')
    digest = quality.factory.digest(path)
    observations = [
        _relation_record('status.md', 'Created 2031-05-04T08:10Z', digest, timestamp='2031-05-04T08:10Z',
                         precision='minute', kind='record_created', observation_id='created'),
        _relation_record('status.md', 'Planned 2031-05-04T09:30Z', digest, timestamp='2031-05-04T09:30Z',
                         precision='minute', kind='event', observation_id='planned'),
        _relation_record('status.md', 'Updated 2031-05-04T10:05Z', digest, timestamp='2031-05-04T10:05Z',
                         precision='minute', kind='record_updated', observation_id='updated')]
    for index, row in enumerate(observations, 1):
        row['locator'] = f'line {index}'
    result = quality.validate_record_relations({'version': quality.VERSION, 'observations': observations,
        'relations': [{'relation_id': 'update_after_plan', 'subject_id': 'updated', 'related_id': 'planned',
                       'constraint': 'subject_not_before_related', 'statement': 'The documented update follows the planned event.'}]},
        root, candidate_only=False)
    assert result['relations'][0]['status'] == 'pass'


def test_source_dependency_is_presented_for_agent_review_not_auto_passed(tmp_path):
    root = tmp_path / 'candidate'; root.mkdir()
    source, excerpt = root / 'source.md', root / 'excerpt.md'
    source.write_text('Source at 2031-05-04T08:10Z', encoding='utf-8')
    excerpt.write_text('Excerpt at 2031-05-04T08:20Z', encoding='utf-8')
    observations = [
        _relation_record('source.md', 'Source at 2031-05-04T08:10Z', quality.factory.digest(source),
                         timestamp='2031-05-04T08:10Z', precision='minute', kind='query', observation_id='source'),
        _relation_record('excerpt.md', 'Excerpt at 2031-05-04T08:20Z', quality.factory.digest(excerpt),
                         timestamp='2031-05-04T08:20Z', precision='minute', kind='excerpt', observation_id='excerpt')]
    result = quality.validate_record_relations({'version': quality.VERSION, 'observations': observations,
        'relations': [{'relation_id': 'lineage', 'subject_id': 'excerpt', 'related_id': 'source',
                       'constraint': 'derived_from', 'statement': 'Compare the declared excerpt to its source.'}]},
        root, candidate_only=False)
    assert result['relations'][0]['status'] == 'agent_review_required'


def test_quality_microtest_prepare_keeps_answer_keys_out_of_case_runtime(tmp_path):
    import run_r10_quality_diagnostic_micro as micro
    readiness = tmp_path / 'readiness.json'
    factory.write(readiness, {'tests_passed': True})
    root = tmp_path / 'batch'
    micro.prepare(root, readiness)
    assert len(factory.read(root / 'batch.json')['cases']) == 4
    assert (root / 'answer_keys.json').is_file()
    for row in factory.read(root / 'batch.json')['cases']:
        child = root / row['path']
        assert not any('answer_key' in name for name in factory.files(child))
        runner_scope, _ = __import__('run_r10_agent_factory_pilot').verify(child)
        assert runner_scope['purpose'] == 'quality_diagnostic_microtest'


def _micro_diagnosis(draft, inputs, status='completed'):
    rubric = factory.read(draft / 'new_rubric.json')
    view = quality.rubric_view(rubric, factory.read(draft / 'basis_draft.json'),
                               factory.read(draft / 'calculation_evidence.json'), inputs)
    rows = []
    for item in view['criteria']:
        rows.append({'criterion_id': item['criterion_id'], 'criterion_sha256': item['criterion_sha256'],
                     'candidate_requirement_ids': ['r1'], 'overlap_criterion_ids': [],
                     **{k: 'pass' for k in ('atomicity', 'alternative_consistency', 'overlap')},
                     **{k + '_rationale': 'Synthetic independent observation.' for k in ('atomicity', 'alternative_consistency', 'overlap')},
                     'clause_refs': {k: [item['criterion_pointer'] + '/full_credit_condition']
                                     for k in ('atomicity', 'alternative_consistency', 'overlap')}})
    factory.write(draft / 'rubric_diagnostic.json', {**view, 'criteria': rows, 'decision': 'pass'})
    factory.write(draft / 'diagnostic_result.json', {'version': 1, 'status': status,
                  'reason': 'Synthetic evidence only.', 'candidate_input_hashes': quality.candidate_input_hashes(inputs)})
    context = factory.read(inputs / 'diagnostic_context/edit_versions.json')
    changed = context['before'] != context['after']
    factory.write(draft / 'edit_record.json', {'changes': ([{'area': 'metadata',
                  'actual_change_paths': ['/rationale']}] if changed else [])})


def test_micro_accounting_reads_started_failures_without_mutating_receipts(tmp_path):
    import run_r10_quality_diagnostic_micro as micro
    ready = tmp_path / 'ready.json'
    factory.write(ready, {'tests_passed': True})
    root = tmp_path / 'batch'
    micro.prepare(root, ready)
    for row in factory.read(root / 'batch.json')['cases']:
        path = root / row['path'] / 'receipt.json'
        state = factory.read(path)
        state['attempts'] = [{'status': 'incomplete', 'phase': 'collection_outputs', 'semantic_started': True}]
        factory.write(path, state)
    before = factory.files(root)
    result = micro.report(root)
    assert result['launches'] == 4 and result['recorded_launches'] == 0
    assert result['launch_count_mismatch'] and not result['validation_complete']
    assert before == factory.files(root)


@pytest.mark.parametrize('fault', ['none', 'timeout', 'missing_finish', 'after_finish', 'staging',
    'review_issue', 'review_uncertain', 'conflict', 'time_issue', 'time_control', 'replay_failure',
    'missing_relations', 'old_diagnosis', 'false_edit'])
def test_micro_real_entry_transport_roundtrip(tmp_path, monkeypatch, fault):
    """Real prepare/execute, Broker, input builders and acceptance; fake SSH/SCP only.

    Provider opinions are prescribed, so this tests wiring, not semantic ability.
    """
    import json
    import shutil
    import subprocess
    import run_r10_quality_diagnostic_micro as micro
    import run_r10_agent_factory_pilot as runner
    import r10_calculation_replay as replay
    case_index = 0 if fault in ('conflict', 'false_edit') else 1 if fault in ('time_issue', 'missing_relations') else 3 if fault == 'time_control' else 2
    monkeypatch.setattr(micro, 'CASES', (micro.CASES[case_index],))
    ready = tmp_path / 'ready.json'
    factory.write(ready, {'tests_passed': True})
    root = tmp_path / 'batch'
    micro.prepare(root, ready)
    manifest = factory.read(root / 'batch.json')
    child = root / manifest['cases'][0]['path']
    scope = factory.read(child / 'scope.json')
    remote_root = tmp_path / 'remote'
    def mapped(value):
        value = str(value).removeprefix(runner.HOST + ':')
        return remote_root / value.lstrip('/') if value.startswith('/home/') else Path(value)
    def transfer(args, **kwargs):
        src, dst = map(mapped, args)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copyfile(src, dst)
        return subprocess.CompletedProcess(args, 0, '', '')
    observed = []
    def provider(turn):
        cfg = factory.read(turn / 'broker_config.json')
        cfg['root'] = str(turn)
        broker = tools.Broker(cfg)
        inputs, draft = turn / 'workspace/inputs', turn / 'draft'
        role = cfg['role']
        observed.append(role)
        def client_call(action, args=None):
            original_read, original_files = factory.read, factory.files
            def role_path(value):
                value = str(value).replace('\\', '/')
                for prefix, base in (('/workspace', turn / 'workspace'), ('/draft', draft)):
                    if value == prefix or value.startswith(prefix + '/'):
                        return base / value[len(prefix):].lstrip('/')
                return Path(value)
            with monkeypatch.context() as patch:
                patch.setattr(factory, 'read', lambda p: original_read(role_path(p)))
                patch.setattr(factory, 'files', lambda p: original_files(role_path(p)))
                patch.setattr(tools, 'Path', role_path)
                patch.setattr(quality, 'Path', role_path)
                patch.setattr(tools, 'broker_call', lambda a, payload: broker.handle({'action': a, **payload}))
                return tools.client(action, args or {})
        assert not any('answer_key' in name for name in factory.files(inputs))
        if role == 'compile':
            if fault == 'conflict':
                rubric = factory.read(draft / 'new_rubric.json')
                rubric['criteria'][0]['acceptable_alternatives'] = 'Equivalent calculation with the same scoped total.'
                factory.write(draft / 'new_rubric.json', rubric)
            _micro_diagnosis(draft, inputs, 'upstream_issue' if fault == 'time_issue' else 'completed')
            if fault in ('time_issue', 'time_control'):
                note = inputs / 'reference_files/status_note.md'
                timestamp = '2031-05-04T08:10Z' if fault == 'time_issue' else '2031-05-04T10:05Z'
                other = '2031-05-04T09:30:20Z' if fault == 'time_issue' else '2031-05-04T09:30Z'
                record = {'version': quality.VERSION, 'observations': [
                    _relation_record('reference_files/status_note.md', timestamp, factory.digest(note),
                        timestamp=timestamp, precision='minute', kind='record_created' if fault == 'time_issue' else 'record_updated', observation_id='note'),
                    _relation_record('reference_files/status_note.md', other, factory.digest(note),
                        timestamp=other, precision='second' if fault == 'time_issue' else 'minute', kind='event', observation_id='event')],
                    'relations': [{'relation_id': 'order', 'subject_id': 'note', 'related_id': 'event',
                        'constraint': 'subject_not_before_related', 'statement': 'Knowledge assertion or documented update follows the event.'}]}
                factory.write(draft / 'record_relations.json', record)
            if fault == 'old_diagnosis':
                rubric = factory.read(draft / 'new_rubric.json')
                rubric['criteria'][0]['max_points'] = 3
                factory.write(draft / 'new_rubric.json', rubric)
            if fault == 'false_edit':
                factory.write(draft / 'edit_record.json', {'changes': [{'area': 'prompt', 'actual_change_paths': ['/rationale']}]})
            outcome = quality.micro_result(draft, inputs, cfg)
            assert outcome['status'] == ('upstream_issue' if fault == 'time_issue' else 'completed')
            assert client_call('schema', {'artifact': 'diagnostic_result'})['end_action'] == 'finish'
            assert client_call('diagnose', {'subject': 'edit'})['effect'] in ('no_change', 'internal_only_change')
            assert 'finish' in client_call('status')['legal_next_actions']
            with pytest.raises(ValueError, match='diagnostic_mode_requires_finish'):
                client_call('submit')
        else:
            assert not (inputs / 'diagnostic_context').exists()
            assert not (inputs / 'diagnostic_result.json').exists()
            assert not (inputs / 'edit_record.json').exists()
            # Independent synthetic reviewer writes new diagnostics, never reads self-review.
            view = quality.rubric_view(factory.read(inputs / 'new_rubric.json'),
                factory.read(inputs / 'basis_draft.json'), factory.read(inputs / 'calculation_evidence.json'), inputs)
            item = view['criteria'][0]
            factory.write(draft / 'rubric_diagnostic.json', {**view, 'decision': 'pass', 'criteria': [{
                'criterion_id': 'total', 'criterion_sha256': item['criterion_sha256'], 'candidate_requirement_ids': ['r1'],
                'overlap_criterion_ids': [], **{k: 'pass' for k in ('atomicity', 'alternative_consistency', 'overlap')},
                **{k + '_rationale': 'Independent fixture observation.' for k in ('atomicity', 'alternative_consistency', 'overlap')},
                'clause_refs': {k: ['/criteria/0/full_credit_condition'] for k in ('atomicity', 'alternative_consistency', 'overlap')}}]})
            factory.write(draft / 'record_relations.json', {'version': quality.VERSION, 'observations': [],
                          'relations': [], 'not_applicable_reason': 'No dates in this fixture.'})
            decision = 'issue' if fault in ('review_issue', 'time_issue') else 'uncertain' if fault == 'review_uncertain' else 'pass'
            factory.write(draft / 'review.json', {'decision': decision,
                'checks': [{'dimension': dim, 'status': decision, 'findings': [{'path': 'reference_files/record.json',
                    'locator': '/items', 'observation': 'Synthetic observation.', 'limitation': 'Not expert evidence.'}]}
                    for dim in runner.previous.method.DIMENSIONS],
                'requirement_coverage': [{'requirement_id': 'r1', 'status': decision, 'explanation': 'Checked.'}],
                'rubric_coverage': [{'criterion_id': 'total', 'status': decision, 'explanation': 'Checked.'}]})
            tools.check(role, draft, inputs, 'task_factory_harness_v1', atomic_rubric_version=1, quality_diagnostics_version=1)
        client_call('check')
        if fault != 'missing_finish':
            client_call('finish')
        if fault == 'after_finish':
            (draft / 'late.txt').write_text('Changed after finish')
        (turn / 'agent.jsonl').write_text(json.dumps({'type': 'thread.started', 'thread_id': 'synthetic-session'}) + '\n' +
            json.dumps({'type': 'turn.completed', 'usage': {}}) + '\n', encoding='utf-8')
        for name in ('stderr.txt', 'broker.log'):
            (turn / name).write_text('')
    def ssh(host, command, **kwargs):
        number = len(factory.read(child / 'receipt.json')['attempts'])
        turn = mapped(scope['remote']) / f'turn_{number:02d}'
        if command.startswith('mkdir '):
            if fault == 'staging':
                raise subprocess.TimeoutExpired('staging', 1)
            for part in command.split(' && '):
                mapped(part.split()[-1]).mkdir(parents=True, exist_ok=True)
        elif 'r10_calculation_replay.py' in command:
            code = replay.main(turn / 'replay_request/scripts', turn / 'workspace/inputs',
                               turn / 'replay_request/execution_manifest.json', turn / 'replay_output/result.json')
            if fault == 'replay_failure':
                payload = factory.read(turn / 'replay_output/result.json')
                payload['status'] = 'failed'
                factory.write(turn / 'replay_output/result.json', payload)
            return subprocess.CompletedProcess(command, code, '', '')
        elif '/raw:ro' in command and 'broker.json' in command:
            inventory = {}
            for name in ('draft', 'snapshots', 'processes', 'broker.json'):
                path = turn / name
                if path.is_dir():
                    inventory[name] = {'kind': 'directory', 'hashes': factory.files(path)}
                elif path.is_file():
                    inventory[name] = {'kind': 'file', 'sha256': factory.digest(path)}
            return subprocess.CompletedProcess(command, 0, json.dumps(inventory), '')
        elif 'factory_broker_pid=$!' in command:
            provider(turn)
            return subprocess.CompletedProcess(command, 124 if fault == 'timeout' else 0, '', '')
        elif 'relative_to(r).as_posix()' in command and 'python3' in command:
            return subprocess.CompletedProcess(command, 0, json.dumps(factory.files(turn / 'workspace')), '')
        return subprocess.CompletedProcess(command, 0, '', '')
    monkeypatch.setattr(runner, 'environment', lambda *args: None)
    monkeypatch.setattr(runner.base, '_scp_command', lambda a, b: [a, b])
    monkeypatch.setattr(runner.base, '_run', transfer)
    monkeypatch.setattr(runner.base, '_ssh', ssh)
    monkeypatch.setattr(runner.base, 'verify_remote_tree', lambda *args: None)
    result = micro.execute(root)
    state = factory.read(child / 'receipt.json')
    assert not state.get('submitted') and not (child / 'package').exists()
    completed = ('none', 'review_issue', 'review_uncertain', 'conflict', 'time_control')
    upstream = ('time_issue',)
    assert result['launches'] == (0 if fault == 'staging' else 2 if fault in completed else 1), state.get('stop_reason')
    assert not result['launch_count_mismatch']
    if fault in completed:
        assert observed == ['compile', 'review']
        assert state['status'] == 'diagnostic_review_complete', state.get('stop_reason')
        assert result['validation_complete']
    else:
        assert not result['validation_complete']
        expected = {'timeout': 'started_session_failed_no_redraw',
                    'missing_finish': 'diagnostic_output_not_finished_or_changed',
                    'after_finish': 'diagnostic_output_not_finished_or_changed', 'staging': 'staging',
                    'missing_relations': 'record_relations.json', 'old_diagnosis': 'identity mismatch',
                    'false_edit': 'prompt claim'}
        if fault == 'replay_failure':
            assert state['status'] == 'diagnostic_replay_failed'
        elif fault in upstream:
            assert state['status'] == 'diagnostic_upstream_issue'
        else:
            assert expected[fault] in state['stop_reason']
