"""One bounded, versioned Agent factory. No scoring or business ontology."""
from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

ROLES = ('world', 'mine', 'compile', 'consult', 'review', 'solve')
AUTHOR_ROLES = ('world', 'mine', 'compile')
MODELS = {r: ('gpt-5.6-sol/high' if r in ('world', 'compile', 'solve') else 'deepseek-v4-pro/max') for r in ROLES}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for attempt in range(5):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(root):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('linked_root')
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or getattr(p, 'is_junction', lambda: False)():
            raise ValueError('linked_file')
        if p.is_file():
            if p.stat().st_nlink != 1:
                raise ValueError('hardlinked_file')
            if p.name.lower() in ('auth.json', '.env', 'deepseek-key.txt'):
                raise ValueError('credential_filename')
            result[p.relative_to(root).as_posix()] = digest(p)
        elif not p.is_dir():
            raise ValueError('special_file')
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def cap(receipt, role, timestamp=None):
    timestamp = time.time() if timestamp is None else timestamp
    attempts = receipt['attempts']
    production = sum(a['role'] not in ('review', 'solve') for a in attempts)
    if len(attempts) >= 12 or (role not in ('review', 'solve') and production >= 10):
        raise ValueError('launch_budget_exhausted')
    if role in ('review', 'solve') and any(a['role'] == role for a in attempts):
        raise ValueError('terminal_role_already_attempted')
    reserve = 3600 if role not in ('review', 'solve') else (1800 if role == 'review' else 0)
    remaining = receipt.get('deadline_epoch', timestamp + 21600) - timestamp - reserve
    if remaining < 1:
        raise ValueError('time_budget_exhausted')
    return min(1800, int(remaining))


def invalidate(state, role):
    if state.get('submitted'):
        raise ValueError('already_submitted')
    for downstream in {'world': ('mine', 'compile'), 'mine': ('compile',), 'compile': ()}[role]:
        state['current'].pop(downstream, None)
        state.setdefault('sessions', {}).pop(downstream, None)


def expected_parents(state, role):
    return {k: state['current'][k]['id'] for k in
            {'world': (), 'mine': ('world',), 'compile': ('world', 'mine')}[role]}


def accept_snapshot(state, role, entry):
    if entry['parents'] != expected_parents(state, role):
        raise ValueError('stale_snapshot_parents')
    old = state['current'].get(role)
    if old is None or old['hashes'] != entry['hashes']:
        invalidate(state, role)
    state['current'][role] = entry


def assert_submission(state):
    if state.get('submitted'):
        raise ValueError('already_submitted')
    for role in AUTHOR_ROLES:
        entry = state['current'][role]
        if entry['parents'] != expected_parents(state, role):
            raise ValueError('stale_submission')
    if not state.get('consultations') or not state.get('checks'):
        raise ValueError('consultation_and_file_check_required')
    for role in AUTHOR_ROLES:
        if not any(c.get('role') == role and c.get('hashes') == state['current'][role]['hashes']
                   and c.get('tool') == 'check' for c in state['checks']):
            raise ValueError('current_version_check_required:' + role)
        require_dispositions(state, role, state['current'][role]['id'])


def relevant_consultations(state, role):
    parents = expected_parents(state, role)
    return [c for c in state.get('consultations', []) if c['role'] == role and c.get('parents') == parents]


def require_dispositions(state, role, snapshot_id):
    for consultation in relevant_consultations(state, role):
        for finding in consultation['finding_ids']:
            if not any(d['request_id'] == consultation['request_id'] and d['finding_id'] == finding
                       and d['snapshot'] == snapshot_id for d in state.get('dispositions', [])):
                raise ValueError('disposition_required:' + consultation['request_id'] + ':' + finding)


def validate_session(state, role, scope_id):
    session = state.get('sessions', {}).get(role)
    if session and (session.get('scope') != scope_id or session.get('role') != role
                    or session.get('parents') != expected_parents(state, role)
                    or session.get('normal_end') is not True):
        raise ValueError('session_outside_role_scope_or_version')
    return session


def handoff_request(state, author, target, reason):
    """Author commentary is evidence, never a downstream role's input."""
    if target == 'mine':
        # A compiler's return must not resume a miner that could accumulate
        # supervision-derived editorial advice. Re-mine the visible snapshot.
        state['sessions'].pop('mine', None)
    if target == 'world':
        return {'role': target, 'feedback_origin': 'upstream_issue',
                'feedback': {'from_role': author, 'reason': reason}}
    return {'role': target}


def role_feedback(state, request):
    """Validate the complete message boundary, including out-of-band feedback."""
    feedback = request.get('feedback')
    if feedback is None:
        return None
    role = request['role']
    if request.get('feedback_origin') == 'consultation':
        entry = state['current'].get(role)
        if (role in AUTHOR_ROLES and request.get('feedback_role') == role and entry
                and request.get('feedback_snapshot') == entry['id']):
            return feedback
    if (request.get('feedback_origin') == 'upstream_issue' and role == 'world'
            and feedback.get('from_role') in ('mine', 'compile')):
        return feedback
    raise ValueError('feedback_outside_role_visibility')


def safe_path(root, relative):
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('invalid_relative_path')
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('invalid_relative_path')
    target = Path(root) / p
    if not target.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('path_escape')
    return target


def snapshot(draft, store, role, parents, reason, process=None):
    if not reason.strip():
        raise ValueError('snapshot_reason_required')
    hashes = files(draft)
    if not hashes:
        raise ValueError('empty_snapshot')
    if role == 'world':
        if process is None or hashes.get('hidden/process.md') != process['hash']:
            raise ValueError('save_process_before_materialization')
        if not any(p.startswith('candidate/') for p in hashes):
            raise ValueError('candidate_files_required')
    identity = fingerprint({'hashes': hashes, 'parents': parents, 'role': role})
    destination = Path(store) / identity
    if destination.exists():
        raise FileExistsError('snapshot_already_saved')
    shutil.copytree(draft, destination)
    if files(draft) != hashes or files(destination) != hashes:
        raise ValueError('draft_changed_during_snapshot')
    return {'id': identity, 'role': role, 'hashes': hashes, 'parents': parents,
            'reason': reason, 'process': process, 'saved_at': time.time()}


COMMON = '''You are working in a bounded occupational task factory, not answering a benchmark.
Use /workspace/inputs and your own /draft only. Public sources describe methods,
not organization facts or a claim of current legal verification. No browsing,
package installation, credential inspection, direct provider calls or background
agents. To request another Agent use factory-tools. Do not read other histories.
Use the existing Python/file tools and professional judgment. No file, anomaly,
record or rubric-item quotas. Preserve meaningful uncertainty and actual work.
Do not invent facts just to obtain a positive conclusion.
Run `factory-tools help` first. Tools accept a JSON object on stdin and return JSON.
Writable business artifacts belong in /draft; scripts and render scratch in /tmp.
'''

AUTHOR_FLOW = '''
Consultation is advice, not truth: investigate it and record evidence for your
disposition using record-disposition for each finding on your resulting snapshot.
You may accept, partially accept or reject with located evidence; consult help
for request/finding IDs.
To yield, call consult or handoff (or submit), then end your response promptly.
The controller performs that request only after this turn ends normally. Do not
poll. Each resumed turn consumes one of the same ten production launches.
Use inspect/check tools before handoff. Snapshot final files and supply its ID
when requesting consultation/handoff. Saved versions are outside your write mount.
If no useful task can be formed, handoff to stop with a factual explanation.
'''

READONLY_FLOW = '''
Query schema for the current output contract and exact citation_inputs. Produce
only this role's requested result. Call factory-tools finish before ending your
response; it checks the real output and reports correctable contract errors in
this same turn. After finish succeeds, do not change files and end normally.
Do not call consult, handoff, submit, or another Agent.
'''

ROLE_PROMPTS = {
    'world': '''Build a new occupational business world from the supplied seed and Skill.
Write hidden/process.md describing actors, events, knowledge times, producers,
record purposes and dependencies, not a task or solution. Call save-process in a
separate step BEFORE materializing candidate/ files. For a process revision save
the revised process first, then reconcile existing/new materials to that version.
Keep hidden/world.md and hidden/manifest.json separate from candidate/ records.
Manifest records have path relative to candidate/, producer, business_purpose,
source_dependencies. Read back actual files, investigate their own declarations
and calculations using tools. You may revise this same world, not redraw another.
Use consult to obtain a blind material reading, then assess its findings. When
ready handoff to mine. Do not write a task, rubric or candidate answer.''',
    'mine': '''Read only visible materials and public background. Independently discover
a natural downstream task. Write task.json; query schema for its contract. Work
requirements need visible support and must allow specific conditional conclusions.
Select deliverables by work purpose, not a DOCX template. Do not solve the task.
You can consult about the visible task or request world revision for a located
material problem. When ready handoff to compile. No hidden world is available.''',
    'compile': '''Using visible task/materials/rules, reconstruct supervision.json and
new_rubric.json. Query schema for exact existing contracts. No hidden world facts.
Rubric obligations derive from candidate-visible task/contract/materials, not the
teacher. Cover independently observable partial combinations and full conditional
credit without duplicate penalties. You may consult, revise your files or request
an upstream world/mine revision with located evidence. On upstream_issue request
revision or stop, not submit. After checks and consultation disposition, submit
the final snapshot. Submission is terminal; final review will not return to you.''',
    'consult': '''Independently inspect the supplied visible snapshot. Do not rewrite it
or produce a full candidate answer. Address the supplied question, locate evidence,
distinguish real defects from business uncertainty and report unverified areas.
Write consultation.json: {summary, findings:[{path,locator,observation,limitation}],
questions:[strings]}. No additional Agent calls. You are not grading.''',
}


def prompt(role):
    if role in ('review', 'solve'):
        from task_generator.production import task_method_pilot as previous
        return COMMON + READONLY_FLOW + (
            previous.REVIEW if role == 'review' else previous.SOLVE).replace('/output', '/draft')
    return COMMON + (AUTHOR_FLOW if role in AUTHOR_ROLES else READONLY_FLOW) + ROLE_PROMPTS[role]
