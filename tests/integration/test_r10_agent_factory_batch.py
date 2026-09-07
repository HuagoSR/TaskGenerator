from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'Test'))
import run_r10_agent_factory_pilot as runner
from task_generator.production import agent_factory as f
from task_generator.production import agent_factory_batch as b


def fake_sources(path):
    records = {}
    for identity in b.SOURCE_IDS.values():
        target = path / (identity + '.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('Official source test fixture')
        records[identity] = {'status': 'verified', 'file': target.name, 'sha256': f.digest(target), 'url': 'https://example.invalid'}
    f.write(path / 'verified_sources.json', records)


@pytest.mark.parametrize('index,expected', [(0, 2), (2, 1), (3, 2)])
def test_seed_rules_and_explicit_source_aliases(tmp_path, index, expected):
    bundle = tmp_path / 'bundle'
    fake_sources(bundle)
    dest = tmp_path / 'public'
    b.public_inputs(runner, dest, b.CASES[index], bundle)
    rules = f.read(dest / 'professional_rules.json')['rules']
    assert len(rules) == expected
    seed = f.read(dest / 'work_seed.json')
    original_ids = {s['source_id'] for s in seed['public_sources']}
    assert {s['source_id'] for rule in rules for s in rule['source_refs']} == original_ids
    sources = f.read(dest / 'sources.json')
    assert original_ids <= {s['source_id'] for s in sources}
    assert all(s.get('verification', {}).get('status') == 'verified' for s in sources)
    assert (dest / 'SKILL.md').is_file()


def batch_fixture(tmp_path, monkeypatch):
    root = tmp_path / 'batch'
    root.mkdir()
    cases = []
    for spec in b.CASES:
        child = root / 'cases' / spec['id']
        f.write(child / 'receipt.json', {'status': 'prepared', 'attempts': [], 'consultations': [], 'checks': []})
        cases.append(dict(spec, path=child.relative_to(root).as_posix()))
    manifest = {'cases': cases, 'seconds': 54000}
    f.write(root / 'batch.json', manifest)
    f.write(root / 'receipt.json', {'status': 'prepared', 'position': 0, 'gates': {}, 'first_failure': None, 'interventions': []})
    monkeypatch.setattr(b, 'verify', lambda r, p: (manifest, f.read(p / 'receipt.json')))
    return root, manifest


@pytest.mark.parametrize('failed,category,expected', [(None, None, 5), (0, 'case', 1), (2, 'case', 5), (2, 'global', 3), (2, 'controller', 3)])
def test_batch_order_and_failure_policy(tmp_path, monkeypatch, failed, category, expected):
    root, manifest = batch_fixture(tmp_path, monkeypatch)
    calls = []
    def execute(child, batch_root):
        assert batch_root == root
        i = len(calls)
        calls.append(child.name)
        f.write(child / 'receipt.json', {'status': 'incomplete' if i == failed else 'completed',
                'failure_category': category if i == failed else None, 'stop_reason': 'synthetic',
                'attempts': [{'role': 'world'}]})
        f.write(child / 'researcher_review.json', {'status': 'pass'})
    monkeypatch.setattr(runner, 'execute', execute)
    monkeypatch.setattr(b, 'gate', lambda child, result: 'not_passed' if result['status'] == 'incomplete' else 'pass')
    result = b.execute(runner, root)
    assert calls == [s['id'] for s in b.CASES[:expected]]
    assert result['status'] == ('development_not_passed' if failed == 0 else 'incomplete' if category in ('global', 'controller') else 'completed')
    with pytest.raises(ValueError, match='batch_not_executable'):
        b.execute(runner, root)


def test_global_budget_reserve_clock_and_position(tmp_path, monkeypatch):
    root, manifest = batch_fixture(tmp_path, monkeypatch)
    child = root / manifest['cases'][0]['path']
    (root / 'execution.lock').touch()
    state = f.read(root / 'receipt.json')
    state.update(status='running', deadline_epoch=5000)
    f.write(root / 'receipt.json', state)
    monkeypatch.setattr(b.time, 'time', lambda: 1000)
    assert b.cap(runner, root, child, 'world', started=True) == 400
    assert f.read(root / 'receipt.json')['deadline_epoch'] == 5000
    assert b.cap(runner, root, child, 'review') == 1800
    with pytest.raises(ValueError, match='position_mismatch'):
        b.cap(runner, root, root / manifest['cases'][1]['path'], 'world')
    monkeypatch.setattr(b.time, 'time', lambda: 1401)
    with pytest.raises(ValueError, match='batch_time_budget'):
        b.cap(runner, root, child, 'world')
    assert b.cap(runner, root, child, 'solve') == 1800
    f.write(child / 'receipt.json', {'attempts': [{'role': 'world'}] * 60})
    with pytest.raises(ValueError, match='batch_launch_budget'):
        b.cap(runner, root, child, 'solve')
    (root / 'STOP').touch()
    with pytest.raises(ValueError, match='batch_stop_requested'):
        b.cap(runner, root, child, 'solve')


def test_prepare_and_frozen_method(tmp_path, monkeypatch):
    bundle = tmp_path / 'bundle'
    fake_sources(bundle)
    def prepare(child, *args, **kwargs):
        child.mkdir()
        f.write(child / 'scope.json', {'batch_id': kwargs['batch_id'], 'code_hashes': {}, 'prompt_hashes': {'world': 'fixed'}})
        f.write(child / 'receipt.json', {'status': 'prepared', 'attempts': []})
    monkeypatch.setattr(runner, 'prepare', prepare)
    monkeypatch.setattr(runner, 'verify', lambda child: (f.read(child / 'scope.json'), f.read(child / 'receipt.json')))
    monkeypatch.setattr(runner.base, 'code_hashes', lambda: {})
    root = tmp_path / 'batch'
    b.prepare(runner, root, bundle, None, None)
    b.verify(runner, root)
    with pytest.raises(FileExistsError):
        b.prepare(runner, root, bundle, None, None)
    case = f.read(root / 'batch.json')['cases'][1]
    scope = root / case['path'] / 'scope.json'
    scope.write_text(scope.read_text() + ' ')
    with pytest.raises(ValueError, match='scope_changed'):
        b.verify(runner, root)


def test_atomic_receipt_transient_access_failure(tmp_path, monkeypatch):
    target = tmp_path / 'receipt.json'
    target.write_text('{"first": true}')
    replace = Path.replace
    calls = []
    def transient(path, destination):
        calls.append(path)
        if len(calls) == 1:
            assert f.read(target) == {'first': True}
            raise PermissionError('temporary file access')
        return replace(path, destination)
    monkeypatch.setattr(Path, 'replace', transient)
    f.write(target, {'next': True})
    assert f.read(target) == {'next': True} and len(calls) == 2


def test_gate_binds_receipt_and_evidence(tmp_path, monkeypatch):
    receipt = {'status': 'completed', 'submitted': True, 'review': {'quality': 'pass'}, 'trial': {'delivery_status': 'valid'}}
    monkeypatch.setattr(f, 'assert_submission', lambda state: None)
    f.write(tmp_path / 'receipt.json', receipt)
    f.write(tmp_path / 'scope.json', {})
    assert b.gate(tmp_path, receipt) == 'pending'
    evidence = tmp_path / 'trial.txt'
    evidence.write_text('Actual completion evidence')
    review = {'receipt_sha': f.digest(tmp_path / 'receipt.json'), 'scope_sha': f.digest(tmp_path / 'scope.json'),
              'status': 'pass', 'task_manual_edits': 0, 'findings': [{'path': 'trial.txt', 'sha256': f.digest(evidence),
              'locator': 'line 1', 'observation': 'Actual file checked'}]}
    f.write(tmp_path / 'researcher_review.json', review)
    assert b.gate(tmp_path, receipt) == 'pass'
    evidence.write_text('Changed after inspection')
    with pytest.raises(ValueError, match='gate_evidence'):
        b.gate(tmp_path, receipt)
