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

ROLES = ('world', 'mine', 'compile', 'devsolve', 'consult', 'review', 'solve')
AUTHOR_ROLES = ('world', 'mine', 'compile')
TERMINAL_ROLES = ('review', 'solve')


def attempt_consumes_launch(attempt):
    """Return whether an operation crossed the provider-launch accounting boundary."""
    # Historical receipts and small offline fixtures predate explicit lifecycle
    # fields; their presence in attempts meant that a launch had occurred.
    if 'status' not in attempt and 'phase' not in attempt:
        return True
    return (attempt.get('phase') in ('native', 'collection', 'output_check')
            or attempt.get('status') in ('started', 'native_completed', 'completed',
                                         'presemantic_transport_failure'))
SOL_ROLES = ('world', 'compile', 'devsolve', 'solve')
MODELS = {role: ('gpt-5.6-sol/high' if role in SOL_ROLES else 'deepseek-v4-pro/max') for role in ROLES}


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
        'compile': ('world', 'mine'),
    }
    return {key: state['current'][key]['id'] for key in dependencies[role]}


def invalidate(state, role):
    if state.get('submitted'):
        raise ValueError('already_submitted')
    downstream = {'world': ('mine', 'compile', 'devsolve'),
                  'mine': ('compile', 'devsolve'), 'compile': ('devsolve',)}[role]
    for item in downstream:
        state['current'].pop(item, None)
        state.setdefault('sessions', {}).pop(item, None)
    if role in ('world', 'mine'):
        state.pop('development_trial', None)
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
    return {
        'launches_used': used,
        'launches_remaining': max(0, 16 - used),
        'production_launches_used': production,
        'production_launches_remaining': max(0, 14 - production),
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
    reserve = 3600 if role not in TERMINAL_ROLES else (1800 if role == 'review' else 0)
    deadline = receipt.get('deadline_epoch')
    if deadline is None:
        deadline = timestamp + 14400
    remaining = deadline - timestamp - reserve
    if remaining < 1:
        raise ValueError('time_budget_exhausted')
    return min(1800, int(remaining))


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
    for role in AUTHOR_ROLES:
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
    for role in ('world', 'mine'):
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
        if role in AUTHOR_ROLES and request.get('feedback_role') == role and entry \
                and request.get('feedback_snapshot') == entry['id']:
            return feedback
    if origin == 'upstream_issue' and role in ('world', 'mine'):
        allowed = ('mine', 'compile') if role == 'world' else ('compile',)
        if feedback.get('from_role') in allowed:
            return feedback
    raise ValueError('feedback_outside_role_visibility')


def handoff_request(state, author, target, reason):
    upstream = ((author == 'compile' and target in ('world', 'mine'))
                or (author == 'mine' and target == 'world'))
    if upstream:
        if state.get('upstream_revisions', 0) >= 1:
            raise ValueError('upstream_revision_budget_exhausted')
        state['upstream_revisions'] = state.get('upstream_revisions', 0) + 1
    if target == 'mine':
        state['sessions'].pop('mine', None)
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
    if version not in ('1', '2'):
        raise ValueError(f'calculation_evidence.json.version: expected 1 or 2, got {manifest.get("version")!r}')
    if not isinstance(calculations, list) or not calculations:
        raise ValueError('calculation_evidence.json.calculations: expected a nonempty list')
    seen = set()
    rubric_ids = {row['criterion_id'] for row in read(Path(draft) / 'new_rubric.json')['criteria']}
    executions = {}
    if version == '2':
        rows = manifest.get('executions')
        if not isinstance(rows, list) or not rows:
            raise ValueError('calculation_evidence.json.executions: expected a nonempty list')
        execution_ids = set()
        for index, execution in enumerate(rows):
            location = f'calculation_evidence.json.executions[{index}]'
            if not isinstance(execution, dict):
                raise ValueError(f'{location}: expected an object')
            missing = [key for key in ('execution_id', 'script', 'sources') if key not in execution]
            if missing:
                raise ValueError(f'{location}: missing fields {missing}')
            _calculation_id(execution['execution_id'], location + '.execution_id', execution_ids)
            script = safe_path(script_root, execution['script'])
            if script.suffix != '.py' or not script.is_file():
                raise ValueError(f'{location}.script: expected an existing .py file relative to calculation_scripts/')
            _calculation_sources(execution['sources'], inputs, location + '.sources')
            executions[execution['execution_id']] = execution
    used_executions = set()
    for index, row in enumerate(calculations):
        required = (('calculation_id', 'rubric_ids', 'script', 'sources', 'unit',
                     'scope', 'method', 'assumptions', 'expected', 'alternatives') if version == '1' else
                    ('calculation_id', 'execution_id', 'result_pointer', 'rubric_ids', 'unit',
                     'scope', 'method', 'assumptions', 'expected', 'alternatives'))
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
            script = safe_path(script_root, row['script'])
            if script.suffix != '.py' or not script.is_file():
                raise ValueError(f'calculation_evidence.json.calculations[{index}].script: expected an existing .py file relative to calculation_scripts/')
            _calculation_sources(row['sources'], inputs,
                                 f'calculation_evidence.json.calculations[{index}].sources')
        else:
            if row['execution_id'] not in executions:
                raise ValueError(f'calculation_evidence.json.calculations[{index}].execution_id: unknown execution')
            used_executions.add(row['execution_id'])
            try:
                json_pointer_tokens(row['result_pointer'])
            except ValueError as error:
                raise ValueError(f'calculation_evidence.json.calculations[{index}].result_pointer: {error}') from error
        _calculation_expected(row['expected'],
                              f'calculation_evidence.json.calculations[{index}].expected')
    if version == '2' and used_executions != set(executions):
        raise ValueError('calculation_evidence.json.executions: every execution must be used by at least one calculation')
    return manifest


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
                legal += ['handoff:world', 'handoff:compile']
            else:
                legal += ['handoff:world', 'handoff:mine', 'replay:return']
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
or compile when ready.''',
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
After the controller supplies both blind trial evidence and design intent, record
comparison.json distinguishing trial errors, compiler omissions, alternatives,
and upstream defects. You may revise teacher files, consult, or use the single
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


def prompt(role):
    if role in ('review', 'solve'):
        from task_generator.production import task_method_pilot
        body = task_method_pilot.REVIEW if role == 'review' else task_method_pilot.SOLVE
        if role == 'review':
            body += '''\nIndependently inspect calculation_evidence.json and replay_results.json.
Check source identity, professional scope, alternatives, rubric linkage, and that
numeric boundaries are reproducible where appropriate. A replay pass proves only
execution consistency, not professional correctness.\n'''
        return COMMON + READONLY_FLOW + body.replace('/output', '/draft')
    return COMMON + (AUTHOR_FLOW if role in AUTHOR_ROLES else READONLY_FLOW) + ROLE_PROMPTS[role]
