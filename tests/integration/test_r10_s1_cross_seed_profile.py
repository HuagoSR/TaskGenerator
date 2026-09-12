"""Tests for the s1-cross-seed-v1 profile: case selection and packaging semantics."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]
import run_r10_task_factory_harness as batch_runner  # noqa: E402
from task_generator.production import agent_factory as legacy  # noqa: E402


def state():
    return {'attempts': [], 'current': {}, 'sessions': {}, 'checks': [], 'consultations': [],
            'dispositions': [], 'submitted': False, 'calculation_replays': [],
            'compile_stage': 'basis', 'upstream_revisions': 0}


def test_cross_seed_profile_selects_both_procurement_positions(tmp_path, monkeypatch):
    root = tmp_path / 'xs_batch'
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'public.txt').write_text('source', encoding='utf-8')
    readiness = tmp_path / 'readiness.json'
    legacy.write(readiness, {'tests_passed': True, 'commands': ['targeted', 'full']})
    captured = []

    def fake_prepare(child, dependency_lock, dependency_remote, *, spec, source_bundle,
                     batch_id, protocol, harness_options):
        captured.append({'spec': spec, 'harness_options': harness_options})
        child.mkdir(parents=True)
        scope = {'batch_id': batch_id, 'protocol': protocol, 'code_hashes': {}}
        legacy.write(child / 'scope.json', scope)
        legacy.write(child / 'receipt.json', state() | {
            'status': 'prepared', 'task_manual_edits': 0, 'recoveries': 0})
        return scope

    monkeypatch.setattr(batch_runner.runner, 'prepare', fake_prepare)
    result = batch_runner.prepare(
        root, source, tmp_path / 'lock.json', '/remote/deps', readiness,
        profile='s1-cross-seed-v1')
    manifest = json.loads((root / 'batch.json').read_text(encoding='utf-8'))
    assert manifest['profile'] == 's1-cross-seed-v1'
    assert [row['id'] for row in manifest['cases']] == [
        'cross_seed_g1_procurement_price', 'cross_seed_g2_acceptance']
    assert manifest['max_launches'] == 32 and manifest['seconds'] == 28800
    assert len(captured) == 2
    seeds = {c['spec']['seed'] for c in captured}
    assert seeds == {'seed_procurement_price_reasonableness', 'seed_procurement_acceptance_disposition'}
    skills = {c['spec']['skill'] for c in captured}
    assert skills == {'procurement-price-reasonableness', 'procurement-delivery-acceptance'}
    for c in captured:
        opts = c['harness_options']
        assert opts['method_profile'] == 'quality-development-v1'
        assert opts['candidate_edit_version'] == 1
        assert opts['atomic_rubric_version'] == 'r10.atomic_rubric.1'
        assert opts['inherited_world_lineage'] is None
        assert 'quality_diagnostics_version' not in opts
    assert 'no pipeline execution is authorized' in manifest['authorization']
    assert result['launches_used'] == 0


def test_cross_seed_profile_rejects_case_and_world_binding(tmp_path):
    root = tmp_path / 'xs_batch'
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'public.txt').write_text('source', encoding='utf-8')
    readiness = tmp_path / 'readiness.json'
    legacy.write(readiness, {'tests_passed': True, 'commands': ['x']})
    with pytest.raises(ValueError, match='profile_is_mutually_exclusive_with_case_and_parent'):
        batch_runner.prepare(root, source, tmp_path / 'lock.json', '/remote/deps', readiness,
                             profile='s1-cross-seed-v1', case_ids=('cross_seed_g1_procurement_price',))
    with pytest.raises(ValueError, match='quality_world_source_requires_quality_profile'):
        batch_runner.prepare(tmp_path / 'b2', source, tmp_path / 'lock.json', '/remote/deps',
                             readiness, profile='s1-cross-seed-v1', quality_world_from=tmp_path / 'old')
