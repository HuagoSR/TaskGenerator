"""Versioned protocol for development solving and reproducible rubric evidence.

Professional conclusions remain Agent judgments.  This module owns only the
role graph, immutable version dependencies, budgets, and machine-checkable
teacher-side evidence contracts.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from task_generator.production import agent_factory as legacy

ROLES = ('world', 'mine', 'edit', 'compile', 'devsolve', 'consult', 'review', 'solve')
AUTHOR_ROLES = ('world', 'mine', 'edit', 'compile')
TERMINAL_ROLES = ('review', 'solve')


def attempt_consumes_launch(attempt):
    """Return whether an operation crossed the provider-launch accounting boundary."""
    # Historical receipts and small offline fixtures predate explicit lifecycle
    # fields; their presence in attempts meant that a launch had occurred.
    if 'status' not in attempt and 'phase' not in attempt:
        return True
    phase = str(attempt.get('phase', ''))
    return (phase in ('native', 'output_check') or phase.startswith('collection')
            or attempt.get('status') in ('started', 'native_completed', 'completed',
                                         'presemantic_transport_failure'))
SOL_ROLES = ('world', 'edit', 'compile', 'devsolve', 'solve')
MODELS = {role: ('gpt-5.6-sol/high' if role in SOL_ROLES else 'deepseek-v4-pro/max') for role in ROLES}


class ContractIssues(ValueError):
    def __init__(self, messages):
        self.messages = list(messages)
        super().__init__('; '.join(self.messages))


def read(path):
    return legacy.read(path)


def write(path, value):
    return legacy.write(path, value)


def digest(path):
    return legacy.digest(path)


def files(root):
    return legacy.files(root)


def fingerprint(value):
    return legacy.fingerprint(value)


def safe_path(root, relative):
    return legacy.safe_path(root, relative)


def expected_parents(state, role):
    dependencies = {
        'world': (),
        'mine': ('world',),
        'edit': ('world', 'mine'),
        'compile': ('world', 'mine', 'edit') if state.get('candidate_edit_version') else ('world', 'mine'),
    }
    return {key: state['current'][key]['id'] for key in dependencies[role]}


def active_author_roles(state):
    return AUTHOR_ROLES if state.get('candidate_edit_version') else ('world', 'mine', 'compile')


def invalidate(state, role):
    if state.get('submitted'):
        raise ValueError('already_submitted')
    downstream = {'world': ('mine', 'edit', 'compile', 'devsolve'),
                  'mine': ('edit', 'compile', 'devsolve'),
                  'edit': ('compile', 'devsolve'), 'compile': ('devsolve',)}[role]
    for item in downstream:
        state['current'].pop(item, None)
        state.setdefault('sessions', {}).pop(item, None)
    if role in ('world', 'mine', 'edit'):
        state.pop('development_trial', None)
        state.pop('initial_basis_snapshot', None)
        state['compile_stage'] = 'basis'


def accept_snapshot(state, role, entry):
    if entry['parents'] != expected_parents(state, role):
        raise ValueError('stale_snapshot_parents')
    previous = state['current'].get(role)
    if previous is None or previous['hashes'] != entry['hashes']:
        invalidate(state, role)
    state['current'][role] = entry


def validate_session(state, role, scope_id):
    session = state.get('sessions', {}).get(role)
    if session and (session.get('scope') != scope_id or session.get('role') != role
                    or session.get('parents') != expected_parents(state, role)
                    or session.get('normal_end') is not True):
        raise ValueError('session_outside_role_scope_or_version')
    return session


def budget_state(receipt, role=None, timestamp=None):
    timestamp = time.time() if timestamp is None else timestamp
    attempts = [row for row in receipt['attempts'] if attempt_consumes_launch(row)]
    used = receipt.get('prior_launches', 0) + len(attempts)
    production = receipt.get('prior_production_launches', 0) + sum(
        row['role'] not in TERMINAL_ROLES for row in attempts)
    deadline = receipt.get('deadline_epoch')
    remaining_seconds = None if deadline is None else max(0, int(deadline - timestamp))
    limits = receipt.get('budget_limits', {})
    return {
        'launches_used': used,
        'launches_remaining': max(0, min(16, limits.get('max_launches', 16)) - used),
        'production_launches_used': production,
        'production_launches_remaining': max(0, min(14, limits.get('production_launches', 14)) - production),
        'review_attempted': any(row['role'] == 'review' for row in attempts),
        'solve_attempted': any(row['role'] == 'solve' for row in attempts),
        'case_seconds_remaining': remaining_seconds,
        'requested_role': role,
    }


def cap(receipt, role, timestamp=None):
    timestamp = time.time() if timestamp is None else timestamp
    budget = budget_state(receipt, role, timestamp)
    if budget['launches_remaining'] < 1 or (
            role not in TERMINAL_ROLES and budget['production_launches_remaining'] < 1):
        raise ValueError('launch_budget_exhausted')
    if role == 'review' and budget['review_attempted'] or role == 'solve' and budget['solve_attempted']:
        raise ValueError('terminal_role_already_attempted')
    limits = receipt.get('budget_limits', {})
    reserve = limits.get('terminal_reserve_seconds', 3600) if role not in TERMINAL_ROLES else (1800 if role == 'review' else 0)
    deadline = receipt.get('deadline_epoch')
    if deadline is None:
        deadline = timestamp + min(14400, limits.get('seconds', 14400))
    remaining = deadline - timestamp - reserve
    if remaining < 1:
        raise ValueError('time_budget_exhausted')
    return min(1800, limits.get('per_launch_seconds', 1800), int(remaining))


def relevant_consultations(state, role):
    parents = expected_parents(state, role)
    return [row for row in state.get('consultations', [])
            if row['role'] == role and row.get('parents') == parents]


def require_dispositions(state, role, snapshot_id):
    for consultation in relevant_consultations(state, role):
        for finding in consultation['finding_ids']:
            if not any(row['request_id'] == consultation['request_id']
                       and row['finding_id'] == finding and row['snapshot'] == snapshot_id
                       for row in state.get('dispositions', [])):
                raise ValueError('disposition_required:' + consultation['request_id'] + ':' + finding)


def assert_submission(state):
    for role in active_author_roles(state):
        entry = state['current'][role]
        if entry['parents'] != expected_parents(state, role):
            raise ValueError('stale_submission')
        if not any(row.get('role') == role and row.get('hashes') == entry['hashes']
                   and row.get('tool') == 'check' and row.get('mode', 'ready') == 'ready'
                   for row in state.get('checks', [])):
            raise ValueError('current_version_check_required:' + role)
        require_dispositions(state, role, entry['id'])
    if not state.get('consultations'):
        raise ValueError('independent_consultation_required')
    if not state.get('development_trial'):
        raise ValueError('development_trial_required')
    if state['development_trial'].get('candidate_parents') != expected_parents(state, 'compile'):
        raise ValueError('development_trial_outside_current_candidate')
    if not state.get('calculation_replays'):
        raise ValueError('calculation_replay_required')
    current = state['current']['compile']['id']
    if not any(row.get('compile_snapshot') == current and row.get('status') == 'passed'
               for row in state['calculation_replays']):
        raise ValueError('current_calculation_replay_required')


def submission_base_missing(state):
    missing = []
    for role in (('world', 'mine', 'edit') if state.get('candidate_edit_version') else ('world', 'mine')):
        entry = state.get('current', {}).get(role)
        if not entry:
            missing.append('current_' + role)
            continue
        if not any(row.get('role') == role and row.get('hashes') == entry['hashes']
                   and row.get('tool') == 'check' and row.get('mode', 'ready') == 'ready'
                   for row in state.get('checks', [])):
            missing.append('current_version_check:' + role)
        try:
            require_dispositions(state, role, entry['id'])
        except ValueError:
            missing.append('consultation_dispositions:' + role)
    if not state.get('consultations'):
        missing.append('independent_consultation')
    if 'compile' not in state.get('current', {}) or not trial_is_current(state):
        missing.append('development_trial_for_current_candidate')
    return missing


def snapshot(draft, store, role, parents, reason, process=None):
    return legacy.snapshot(draft, store, role, parents, reason, process)


def role_feedback(state, request):
    feedback = request.get('feedback')
    if feedback is None:
        return None
    role = request['role']
    origin = request.get('feedback_origin')
    if origin in ('consultation', 'replay', 'development_trial'):
        entry = state['current'].get(role)
        if role in active_author_roles(state) and request.get('feedback_role') == role and entry \
                and request.get('feedback_snapshot') == entry['id']:
            return feedback
    if origin == 'upstream_issue' and role in ('world', 'mine', 'edit'):
        allowed = ({'world': ('mine', 'edit', 'compile'), 'mine': ('edit', 'compile'),
                    'edit': ('compile',)}[role])
        if feedback.get('from_role') in allowed:
            return feedback
    raise ValueError('feedback_outside_role_visibility')


def handoff_request(state, author, target, reason):
    upstream = ((author == 'compile' and target in ('world', 'mine', 'edit'))
                or (author == 'edit' and target in ('world', 'mine'))
                or (author == 'mine' and target == 'world'))
    if upstream:
        if state.get('upstream_revisions', 0) >= 1:
            raise ValueError('upstream_revision_budget_exhausted')
        state['upstream_revisions'] = state.get('upstream_revisions', 0) + 1
    if target in ('mine', 'edit'):
        state['sessions'].pop(target, None)
    if upstream:
        return {'role': target, 'feedback_origin': 'upstream_issue',
                'feedback': {'from_role': author, 'reason': reason}}
    return {'role': target}


def _calculation_id(value, location, seen):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value)
            or value in seen):
        raise ValueError(f'{location}: expected a unique letters/digits/_/- identifier')
    seen.add(value)


def _calculation_sources(rows, inputs, location):
    if not isinstance(rows, list) or not rows:
        raise ValueError(f'{location}: expected a nonempty list')
    for index, source in enumerate(rows):
        item = f'{location}[{index}]'
        if not isinstance(source, dict) or not isinstance(source.get('path'), str) \
                or not source['path'].startswith('reference_files/'):
            raise ValueError(f'{item}.path: expected one exact reference_files/ path')
        path = safe_path(inputs, source.get('path', ''))
        if not path.is_file() or source.get('sha256') != digest(path) or not source.get('locator'):
            raise ValueError(f'{item}: file, exact sha256 and nonempty locator must match the current candidate input')


def _calculation_expected(expected, location):
    if not isinstance(expected, dict) or set(expected) != {'value', 'tolerance'}:
        raise ValueError(f'{location}: expected exactly {{value: JSON scalar, tolerance: finite nonnegative number}}')
    tolerance = expected['tolerance']
    if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance) or tolerance < 0):
        raise ValueError(f'{location}.tolerance: expected finite nonnegative number, got {tolerance!r}')
    value = expected['value']
    if isinstance(value, (list, dict)):
        raise ValueError(f'{location}.value: expected a JSON scalar, got list/object')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f'{location}.value: numeric values must be finite')
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        if tolerance != 0:
            raise ValueError(f'{location}.tolerance: nonnumeric expected values require zero tolerance')


def json_pointer_tokens(pointer):
    """Parse an RFC 6901 JSON pointer without accepting ambiguous shorthand."""
    if not isinstance(pointer, str) or not pointer.startswith('/'):
        raise ValueError('expected an RFC 6901 JSON Pointer beginning with /')
    tokens = []
    for raw in pointer[1:].split('/'):
        index = 0
        while index < len(raw):
            if raw[index] == '~' and (index + 1 >= len(raw) or raw[index + 1] not in '01'):
                raise ValueError('invalid JSON Pointer escape; use ~0 for ~ and ~1 for /')
            index += 2 if raw[index] == '~' else 1
        tokens.append(raw.replace('~1', '/').replace('~0', '~'))
    return tokens


def resolve_json_pointer(value, pointer):
    current = value
    for token in json_pointer_tokens(pointer):
        if isinstance(current, list):
            if not token.isdigit() or token != str(int(token)) or int(token) >= len(current):
                raise ValueError(f'JSON Pointer list index not found: {token!r}')
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise ValueError(f'JSON Pointer member not found: {token!r}')
    if isinstance(current, (dict, list)):
        raise ValueError('JSON Pointer must resolve to a scalar')
    if isinstance(current, float) and not math.isfinite(current):
        raise ValueError('JSON Pointer resolved to a non-finite number')
    return current


def validate_calculation_bundle(draft, inputs):
    manifest_path = Path(draft) / 'calculation_evidence.json'
    script_root = Path(draft) / 'calculation_scripts'
    manifest = read(manifest_path)
    calculations = manifest.get('calculations')
    version = str(manifest.get('version'))
    preflight = []
    if version not in ('1', '2'):
        raise ValueError(f'calculation_evidence.json.version: expected 1 or 2, got {manifest.get("version")!r}')
    if not isinstance(calculations, list) or not calculations:
        raise ValueError('calculation_evidence.json.calculations: expected a nonempty list')
    required_calculation = (('calculation_id', 'rubric_ids', 'script', 'sources', 'unit',
                             'scope', 'method', 'assumptions', 'expected', 'alternatives')
                            if version == '1' else
                            ('calculation_id', 'execution_id', 'result_pointer', 'rubric_ids', 'unit',
                             'scope', 'method', 'assumptions', 'expected', 'alternatives'))
    calculation_ids, result_refs = set(), set()
    for index, row in enumerate(calculations):
        location = f'calculation_evidence.json.calculations[{index}]'
        if not isinstance(row, dict):
            preflight.append(f'{location}: expected an object')
            continue
        missing = [key for key in required_calculation if key not in row]
        if missing:
            preflight.append(f'{location}: missing fields {missing}')
        identity = row.get('calculation_id')
        if identity in calculation_ids:
            preflight.append(f'{location}.calculation_id: duplicate identifier {identity!r}')
        elif isinstance(identity, str):
            calculation_ids.add(identity)
        if version == '2' and isinstance(row.get('execution_id'), str) and isinstance(row.get('result_pointer'), str):
            result_ref = (row['execution_id'], row['result_pointer'])
            if result_ref in result_refs:
                preflight.append(f'{location}.result_pointer: duplicate result reference; associate one calculation with multiple rubric_ids')
            result_refs.add(result_ref)
        if version == '1' and ('execution_id' in row or 'result_pointer' in row):
            preflight.append(f'{location}: version 1 cannot contain version 2 execution fields')
        if version == '2' and ('script' in row or 'sources' in row):
            preflight.append(f'{location}: version 2 script and sources belong in executions')
    if version == '2' and isinstance(manifest.get('executions'), list):
        execution_ids, scripts = set(), set()
        for index, row in enumerate(manifest['executions']):
            location = f'calculation_evidence.json.executions[{index}]'
            if not isinstance(row, dict):
                preflight.append(f'{location}: expected an object')
                continue
            missing = [key for key in ('execution_id', 'script', 'sources') if key not in row]
            if missing:
                preflight.append(f'{location}: missing fields {missing}')
            identity, script = row.get('execution_id'), row.get('script')
            if isinstance(script, str):
                script = safe_path(script_root, script).resolve().as_posix()
            if identity in execution_ids:
                preflight.append(f'{location}.execution_id: duplicate identifier {identity!r}')
            elif isinstance(identity, str):
                execution_ids.add(identity)
            if script in scripts:
                preflight.append(f'{location}.script: duplicate script; combine outputs under one execution_id')
            elif isinstance(script, str):
                scripts.add(script)
    if preflight:
        raise ContractIssues(preflight)
    seen = set()
    rubric_ids = {row['criterion_id'] for row in read(Path(draft) / 'new_rubric.json')['criteria']}
    executions = {}
    if version == '2':
        rows = manifest.get('executions')
        if not isinstance(rows, list) or not rows:
            raise ValueError('calculation_evidence.json.executions: expected a nonempty list')
        execution_ids = set()
        execution_scripts = set()
        for index, execution in enumerate(rows):
            location = f'calculation_evidence.json.executions[{index}]'
            if not isinstance(execution, dict):
                raise ValueError(f'{location}: expected an object')
            missing = [key for key in ('execution_id', 'script', 'sources') if key not in execution]
            if missing:
                raise ValueError(f'{location}: missing fields {missing}')
            _calculation_id(execution['execution_id'], location + '.execution_id', execution_ids)
            if execution['script'] in execution_scripts:
                raise ValueError(f'{location}.script: duplicate script; combine its outputs under one execution_id')
            execution_scripts.add(execution['script'])
            script = safe_path(script_root, execution['script'])
            if script.suffix != '.py' or not script.is_file():
                raise ValueError(f'{location}.script: expected an existing .py file relative to calculation_scripts/')
            _calculation_sources(execution['sources'], inputs, location + '.sources')
            executions[execution['execution_id']] = execution
    used_executions = set()
    used_results = set()
    for index, row in enumerate(calculations):
        required = required_calculation
        missing = [key for key in required if key not in row]
        if missing:
            raise ValueError(
                f'calculation_evidence.json.calculations[{index}]: missing fields {missing}')
        _calculation_id(row['calculation_id'],
                        f'calculation_evidence.json.calculations[{index}].calculation_id', seen)
        if not row['rubric_ids'] or not set(row['rubric_ids']).issubset(rubric_ids):
            raise ValueError(
                f'calculation_evidence.json.calculations[{index}].rubric_ids: '
                f'expected nonempty subset of {sorted(rubric_ids)}')
        if version == '1':
            if 'execution_id' in row or 'result_pointer' in row or 'executions' in manifest:
                raise ValueError(f'calculation_evidence.json.calculations[{index}]: version 1 cannot contain version 2 execution fields')
            script = safe_path(script_root, row['script'])
            if script.suffix != '.py' or not script.is_file():
                raise ValueError(f'calculation_evidence.json.calculations[{index}].script: expected an existing .py file relative to calculation_scripts/')
            _calculation_sources(row['sources'], inputs,
                                 f'calculation_evidence.json.calculations[{index}].sources')
        else:
            if 'script' in row or 'sources' in row:
                raise ValueError(f'calculation_evidence.json.calculations[{index}]: version 2 script and sources belong in executions')
            if row['execution_id'] not in executions:
                raise ValueError(f'calculation_evidence.json.calculations[{index}].execution_id: unknown execution')
            used_executions.add(row['execution_id'])
            try:
                json_pointer_tokens(row['result_pointer'])
            except ValueError as error:
                raise ValueError(f'calculation_evidence.json.calculations[{index}].result_pointer: {error}') from error
            result_identity = (row['execution_id'], row['result_pointer'])
            if result_identity in used_results:
                raise ValueError(f'calculation_evidence.json.calculations[{index}].result_pointer: duplicate result reference; associate one calculation with multiple rubric_ids')
            used_results.add(result_identity)
        _calculation_expected(row['expected'],
                              f'calculation_evidence.json.calculations[{index}].expected')
    if version == '2' and used_executions != set(executions):
        raise ValueError('calculation_evidence.json.executions: every execution must be used by at least one calculation')
    return manifest


def _candidate_obligation_ref(ref, inputs, location):
    if not isinstance(ref, dict) or not all(isinstance(ref.get(key), str) and ref[key].strip()
                                            for key in ('path', 'locator', 'explanation')):
        raise ValueError(f'{location}: expected path, locator and explanation strings')
    allowed = {'candidate_task.md', 'deliverable_contract.json'}
    if ref['path'] not in allowed:
        raise ValueError(f'{location}.path: expected one of {sorted(allowed)}; evidence files support analysis but do not create candidate obligations')
    path = safe_path(inputs, ref['path'])
    if not path.is_file():
        raise ValueError(f'{location}.path: candidate-visible obligation source is missing')


def validate_obligation_trace(draft, inputs, *, require_comparison=False,
                              initial_basis_snapshot=None, version=1):
    """Check candidate-visible obligation to rubric linkage for new scopes only."""
    if str(version) == '2':
        from .obligation_trace import validate
        return validate(draft, inputs, require_comparison, initial_basis_snapshot)
    if str(version) != '1':
        raise ValueError('unsupported_obligation_trace_version')
    basis = read(Path(draft) / 'basis_draft.json')
    requirements = basis.get('requirements')
    if not isinstance(requirements, list) or not requirements:
        raise ValueError('basis_draft.json.requirements: expected a nonempty list of obligation mappings')
    rubric = read(Path(draft) / 'new_rubric.json')
    criteria = {row['criterion_id']: row for row in rubric['criteria']}
    mapped = set()
    requirement_ids = set()
    for index, row in enumerate(requirements):
        location = f'basis_draft.json.requirements[{index}]'
        if not isinstance(row, dict):
            raise ValueError(f'{location}: expected an object')
        missing = [key for key in ('requirement_id', 'obligation', 'candidate_obligation_refs', 'rubric_ids')
                   if key not in row]
        if missing:
            raise ValueError(f'{location}: missing fields {missing}')
        _calculation_id(row['requirement_id'], location + '.requirement_id', requirement_ids)
        if not isinstance(row['obligation'], str) or not row['obligation'].strip():
            raise ValueError(f'{location}.obligation: expected a nonempty string')
        refs = row['candidate_obligation_refs']
        if not isinstance(refs, list) or not refs:
            raise ValueError(f'{location}.candidate_obligation_refs: expected a nonempty list')
        for ref_index, ref in enumerate(refs):
            _candidate_obligation_ref(ref, inputs, f'{location}.candidate_obligation_refs[{ref_index}]')
        rubric_ids = row['rubric_ids']
        if not isinstance(rubric_ids, list) or not rubric_ids or len(rubric_ids) != len(set(rubric_ids)):
            raise ValueError(f'{location}.rubric_ids: expected unique criterion IDs')
        unknown = set(rubric_ids) - set(criteria)
        if unknown:
            raise ValueError(f'{location}.rubric_ids: unknown criteria {sorted(unknown)}')
        mapped.update(rubric_ids)
    required = {criterion_id for criterion_id, row in criteria.items()
                if row.get('decision_id') != 'deliverable_structure'}
    missing = required - mapped
    if missing:
        raise ValueError('basis_draft.json.requirements: rubric criteria lack candidate obligation mappings: '
                         + ','.join(sorted(missing)))
    if not require_comparison:
        return basis
    comparison = read(Path(draft) / 'comparison.json')
    if comparison.get('initial_basis_snapshot') != initial_basis_snapshot:
        raise ValueError('comparison.json.initial_basis_snapshot: expected immutable pre-trial basis snapshot identity')
    changes = comparison.get('requirement_changes')
    if not isinstance(changes, list):
        raise ValueError('comparison.json.requirement_changes: expected a list, empty when no scoring obligations changed')
    for index, row in enumerate(changes):
        location = f'comparison.json.requirement_changes[{index}]'
        if not isinstance(row, dict) or row.get('change_type') not in ('clarify', 'add', 'remove'):
            raise ValueError(f'{location}.change_type: expected clarify, add or remove')
        if not isinstance(row.get('description'), str) or not row['description'].strip():
            raise ValueError(f'{location}.description: expected a nonempty string')
        if not isinstance(row.get('rubric_ids'), list):
            raise ValueError(f'{location}.rubric_ids: expected a list')
        for ref_index, ref in enumerate(row.get('candidate_obligation_refs', [])):
            _candidate_obligation_ref(ref, inputs, f'{location}.candidate_obligation_refs[{ref_index}]')
        if row['change_type'] == 'add' and not row.get('candidate_obligation_refs'):
            raise ValueError(f'{location}.candidate_obligation_refs: a new scoring obligation needs candidate-visible support or upstream revision')
    return basis


def calculation_contract_schema():
    """Agent-queryable calculation evidence contract; code remains authoritative."""
    result = {
        'file': 'calculation_evidence.json',
        'preferred_version': 2,
        'version_2': {
            'version': '2 (string or integer)',
            'executions': [{
                'execution_id': 'unique letters/digits/_/- identifier',
                'script': 'filename.py relative to calculation_scripts/',
                'sources': [{'path': 'reference_files/exact_candidate_file',
                             'locator': 'specific row/cell/record locator',
                             'sha256': 'exact current input hash'}],
            }],
            'calculations': [{
                'calculation_id': 'unique letters/digits/_/- identifier',
                'execution_id': 'existing execution_id',
                'result_pointer': 'RFC 6901 pointer resolving to a JSON scalar, for example /totals/quoted_total',
                'rubric_ids': ['existing criterion_id'],
                'unit': 'result unit',
                'scope': 'time/range/filter/deduplication/rounding scope',
                'method': 'formula and calculation method',
                'assumptions': ['explicit assumption or empty list'],
                'expected': {'value': 'finite JSON scalar', 'tolerance': 'finite nonnegative number'},
                'alternatives': ['reasonable alternative method or empty list'],
            }],
        },
        'version_1_legacy_shape': {
            'version': '1 (string or integer)',
            'calculations': [{
                'calculation_id': 'unique letters/digits/_/- identifier',
                'rubric_ids': ['existing criterion_id'],
                'script': 'filename.py relative to calculation_scripts/ (no calculation_scripts/ prefix)',
                'sources': [{
                    'path': 'reference_files/exact_candidate_file',
                    'locator': 'specific row/cell/record locator',
                    'sha256': 'exact current input hash',
                }],
                'unit': 'result unit',
                'scope': 'time/range/filter/deduplication/rounding scope',
                'method': 'formula and calculation method',
                'assumptions': ['explicit assumption or empty list'],
                'expected': {'value': 'JSON scalar; numeric values must be finite',
                             'tolerance': 'finite nonnegative number'},
                'alternatives': ['reasonable alternative method or empty list'],
            }],
        },
        'script_io': ('Version 2 scripts receive --inputs <read-only root> and write one JSON object '
                      'of at most 1 MiB to stdout. Calculations select scalar leaves using result_pointer. '
                      'Version 1 scripts retain the legacy {"value": scalar} contract.'),
    }
    # Historical callers use ``shape`` for the version-1 contract.
    result['shape'] = result['version_1_legacy_shape']
    return result


def trial_is_current(state):
    trial = state.get('development_trial')
    return bool(trial and trial.get('candidate_parents') == expected_parents(state, 'compile'))


def replay_is_current(state, snapshot_id=None):
    snapshot_id = snapshot_id or state.get('current', {}).get('compile', {}).get('id')
    return any(row.get('compile_snapshot') == snapshot_id and row.get('status') == 'passed'
               for row in state.get('calculation_replays', []))


def workflow_status(state, role, timestamp=None, current_launch_included=False):
    budget = budget_state(state, role, timestamp)
    consumes_production = role not in TERMINAL_ROLES
    budget['production_remaining_after_current'] = max(0, budget['production_launches_remaining'] - (
        0 if current_launch_included else int(consumes_production)))
    budget['launches_remaining_after_current'] = max(
        0, budget['launches_remaining'] - (0 if current_launch_included else 1))
    current = {name: entry['id'] for name, entry in state.get('current', {}).items()}
    missing = []
    if role == 'compile':
        if not trial_is_current(state):
            missing.append('development_trial_for_current_candidate')
        if not replay_is_current(state):
            missing.append('passing_replay_for_current_compile_snapshot')
        missing += submission_base_missing(state)
    legal = ['status', 'inspect', 'render', 'check']
    if role in AUTHOR_ROLES:
        legal += ['snapshot', 'diff', 'handoff:stop']
        if budget['production_remaining_after_current']:
            legal += ['consult']
            if role == 'world':
                legal += ['handoff:mine']
            elif role == 'mine':
                legal += ['handoff:world', 'handoff:edit' if state.get('candidate_edit_version') else 'handoff:compile']
            elif role == 'edit':
                legal += ['handoff:world', 'handoff:mine', 'handoff:compile']
            else:
                legal += ['handoff:world', 'handoff:mine']
                if state.get('candidate_edit_version'):
                    legal += ['handoff:edit']
                legal += ['replay:return']
                if not trial_is_current(state):
                    legal += ['request-development-trial', 'replay:development_trial']
        if role == 'compile' and budget['launches_remaining_after_current'] and not submission_base_missing(state):
            legal += ['replay:submit']
            if replay_is_current(state):
                legal += ['submit']
    else:
        legal += ['finish']
    return {
        'role': role,
        'current_versions': current,
        'compile_stage': state.get('compile_stage'),
        'development_trial_current': trial_is_current(state) if 'compile' in current else False,
        'passing_replay_current': replay_is_current(state) if 'compile' in current else False,
        'submitted': bool(state.get('submitted')),
        'review_completed': bool(state.get('review')),
        'final_solve_completed': bool(state.get('trial')),
        'missing_prerequisites': missing,
        'submission_base_missing': submission_base_missing(state) if role == 'compile' else [],
        'legal_next_actions': legal,
        'budget': budget,
    }


def validate_next_action(status, role, action, request):
    budget = status['budget']
    next_action = request.get('next_action', 'return') if action == 'replay' else None
    needs_production = (action in ('consult', 'request-development-trial', 'handoff')
                        or action == 'replay' and next_action in ('return', 'development_trial'))
    if needs_production and budget['production_remaining_after_current'] < 1:
        raise ValueError('next_production_launch_budget_unavailable')
    if action == 'submit' or action == 'replay' and next_action == 'submit':
        if budget['launches_remaining_after_current'] < 1:
            raise ValueError('final_review_launch_budget_unavailable')
    if action == 'request-development-trial' and status['development_trial_current']:
        raise ValueError('development_trial_already_completed')
    if action == 'replay' and next_action == 'development_trial' and status['development_trial_current']:
        raise ValueError('development_trial_already_completed')
    return True


def batch_cap(root, child, role, *, started=False, appended=False):
    root, child = Path(root), Path(child)
    manifest, receipt = read(root / 'batch.json'), read(root / 'receipt.json')
    if not (root / 'execution.lock').exists() or receipt['status'] != 'running':
        raise ValueError('batch_execution_required')
    if (root / 'STOP').exists():
        raise ValueError('batch_stop_requested')
    row = manifest['cases'][receipt['position']]
    if (root / row['path']).resolve() != child.resolve():
        raise ValueError('batch_position_mismatch')
    count = manifest.get('prior_launches', 0) + sum(
        sum(attempt_consumes_launch(row) for row in read(
            root / item['path'] / 'receipt.json')['attempts'])
        for item in manifest['cases'])
    if count > manifest['max_launches'] or (not appended and count >= manifest['max_launches']):
        raise ValueError('batch_launch_budget_exhausted')
    if started and receipt.get('deadline_epoch') is None:
        receipt.update(started_at=datetime.now(timezone.utc).isoformat(),
                       deadline_epoch=time.time() + manifest['seconds'])
        write(root / 'receipt.json', receipt)
    reserve = 3600 if role not in TERMINAL_ROLES else (1800 if role == 'review' else 0)
    deadline = receipt.get('deadline_epoch') or (time.time() + manifest['seconds'])
    remaining = deadline - time.time() - reserve
    if remaining < 1:
        raise ValueError('batch_time_budget_exhausted')
    return min(1800, int(remaining))


COMMON = '''You are working in a bounded occupational task factory. Use only
/workspace/inputs and your own /draft. Public sources constrain professional
methods; they do not prove fictional facts. Do not browse, install packages,
inspect credentials, call providers directly, or start background agents. Run
`/workspace/bin/factory-tools help` first and always invoke the tool by that
absolute path because the native Agent may rebuild PATH. Commands accept one JSON
object either as their second argument or on stdin; consult `help` examples. Use
inspect/check/render on actual files. Writable
business outputs belong in /draft and scratch belongs in /tmp. No quotas for
files, anomalies, calculations, or rubric items. Preserve meaningful uncertainty.
'''

AUTHOR_FLOW = '''Consultation is advice. For every returned finding, investigate
and record a disposition tied to the resulting snapshot and located evidence.
Use record-dispositions to bind all findings from one consultation to one current
snapshot. Stage actions create or reuse an immutable snapshot when snapshot is
omitted. End promptly after a queued request; the controller acts only after a
normal end. Explicit session resumes consume the same production budget.
'''

READONLY_FLOW = '''Query schema, create only the requested output, run check, then
call finish. After finish succeeds, do not modify files. Do not consult, handoff,
submit or invoke another Agent.
'''

ROLE_PROMPTS = {
    'world': legacy.ROLE_PROMPTS['world'],
    'mine': '''Read only candidate-visible materials and public background. Discover
a natural downstream task and write task.json. Also write design_intent.json with
occupational_use, analysis_points, likely_difficulties, and evidence references.
It is production evidence, never candidate input or a source of truth. Do not
solve the task. Consult when useful; handoff to world for a located material issue
or the candidate editor when that role is enabled, otherwise compile when ready.''',
    'edit': '''Act as the independent candidate-task editor. Read the mined task,
contract, candidate records, public occupational rules and Skill. Do not read or
infer the hidden world, design intent, teacher basis, answers, historical cases or
scores. Preserve the role, business purpose, authority, evidence scope, delivery
responsibility and real work instructions. Remove only producer-added teaching
hints that reveal anomaly identity, evidence weight or expected conclusions, and
clarify task wording when needed. Natural colleague analysis with a real source
and business purpose remains evidence for the candidate to test. Never alter raw
amounts, dates, record identities, data rows, system/query logic or business
conditions, and never create random missing values. You may remove a genuinely
redundant deliverable only by updating the task and its deliverable list together.
Write edited task.json plus edit_record.json matching schema artifact task_edit.
Every edit must locate its source, explain the business reason, cite preserved
candidate evidence, and state the judgment returned to the candidate. An explicit
no-change result is valid. Consult when useful and handoff to compile when ready.''',
    'compile': '''Independently reconstruct the candidate-visible obligations before
seeing any trial or design intent. Write basis_draft.json, supervision.json,
new_rubric.json, calculation_evidence.json and executable Python files under
calculation_scripts/. Each calculation cites exact input hashes and links rubric
items; judgmental items must describe evidence and conditional paths rather than
invent numeric precision. For the initial evidence snapshot, request replay with
next_action development_trial so a passing replay starts the trial without a
relay turn.
Query schema with artifact calculation_evidence before authoring it. Use version
2: one execution may emit a structured JSON object, and calculations select its
scalar results with JSON Pointers. Do not duplicate a script merely to expose
several related anchors.
In basis_draft.json, make every requirements entry an object with requirement_id,
obligation, candidate_obligation_refs and rubric_ids. Query schema artifact basis
for this scope's provenance version, source classifications and hash requirements.
Facts alone do not create scoring obligations; producer intent and trial answers
are never obligation sources. deliverable_structure remains the declared contract exception and needs
no fabricated professional supervision decision.
After the controller supplies both blind trial evidence and design intent, record
comparison.json distinguishing trial errors, compiler omissions, alternatives,
and upstream defects. Also record initial_basis_snapshot and requirement_changes.
A new scoring requirement needs candidate-visible support; otherwise keep it optional
or use the single upstream revision. Design intent, trial answers, supervision and
calculation outputs are diagnostic inputs, never candidate obligations. You may revise
teacher files, consult, or use the single
upstream revision. When ready, request replay with next_action submit for the
final snapshot; a passing replay submits without a relay turn. Query status when
uncertain and do not request another trial for unchanged candidate inputs.
No hidden world facts.''',
    'devsolve': '''Act as a fresh candidate. Read only the candidate task, contract,
public background required by the task, and reference files. Produce exactly the
contract deliverables under deliverable_files/. Separately write diagnostic.json
with evidence locations, calculation method, ambiguities and completion barriers.
Do not infer teacher intent.''',
    'consult': legacy.ROLE_PROMPTS['consult'],
}


def prompt(role, options=None):
    options = options or {}
    atomic = bool(options.get('atomic_rubric_version'))
    if role in ('review', 'solve'):
        from task_generator.production import task_method_pilot
        body = task_method_pilot.REVIEW if role == 'review' else task_method_pilot.SOLVE
        if role == 'review':
            body += '''\nIndependently inspect calculation_evidence.json and replay_results.json.
Check source identity, professional scope, alternatives, rubric linkage, and that
numeric boundaries are reproducible where appropriate. A replay pass proves only
execution consistency, not professional correctness. Independently verify that every
professional rubric criterion is supported by a candidate-visible obligation in
basis_draft.json. Design intent, trial answers, teacher supervision and calculations
cannot create candidate obligations. deliverable_structure is the declared contract
exception and does not need a fabricated supervision decision.\n'''
            if atomic:
                body += '''Review new_rubric.json as the sole scoring authority.
Each criterion must be one independently observable binary result, scored only
zero or max_points. Check overlap, weight rationale, complete numeric anchors,
tolerance, applicability and reasonable alternatives. supervision.json may
explain calculations and uncertainty but may not add, narrow or override any
scoring condition. Also assess whether editing left substantive professional
judgment for the candidate instead of exposing anomaly identities or conclusions.\n'''
        return COMMON + READONLY_FLOW + body.replace('/output', '/draft')
    body = ROLE_PROMPTS[role]
    if role == 'world' and atomic:
        body += '''\nFor each record that claims a query, sort, filter, subtotal,
unit conversion or date relationship, run a targeted check on the actual file
and retain located check evidence. A file described as a direct system export
must match its stated query; if a record is an excerpt or transformation, its
producer, time, purpose and source dependency must explain that transformation.
During material consultation distinguish a real business conflict from a
generation contradiction by checking author identity, knowledge time, authority,
record purpose and shared sources. Missing evidence may support a bounded
analysis and next action; it never proves that the underlying event did not occur.
Write hidden/material_checks.json with checks [{path, locator, assertion,
method, result, limitation}] for the targeted checks you actually performed.\n'''
    if role == 'compile' and atomic:
        body += '''\nThis scope uses r10.atomic_rubric.1. Query schema artifacts
supervision and rubric. supervision.json is reference analysis only: use
reference_analysis, known_facts, uncertainties, follow_up and evidence; never
write conditional_completion, score boundaries or any scoring rule there.
new_rubric.json is the complete and sole scoring authority. Each criterion has
one independently observable result, a positive integer max_points, one complete
full_credit_condition, weight_rationale, candidate-visible requirement_basis,
evidence_paths, applicability, acceptable_alternatives, tolerance and verification.
It is scored only 0 or max_points. Use weight 3 for a core professional judgment,
2 for a substantive analytical result and 1 for a necessary record/delivery
result unless a located reason justifies another positive integer. Do not split
units or harmless presentation details into artificial criteria, and do not
repeat one fact to amplify its weight. Every scoring condition and alternative
must appear in the rubric, never only in supervision or calculation evidence.\n'''
    return COMMON + (AUTHOR_FLOW if role in AUTHOR_ROLES else READONLY_FLOW) + body
