"""A single authorized Agent factory world, with bounded cooperative handoffs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import sys
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'Test')]
import run_r10_process_first_pilot as base
import run_r10_task_method_pilot as previous
from task_generator.production import agent_factory as f
from task_generator.production import agent_factory_tools as ft

HOST, IMAGE, IMAGE_SHA = base.HOST, base.IMAGE, base.IMAGE_SHA
DEFAULT_DEPS = '/home/huagosr/taskgenerator-data/r10-process-first/r10_process_first_pilot_20260905'
DEFAULT_LOCK = ROOT / 'artifacts/r10/r10_process_first_pilot_20260905/dependency_lock.json'
REMOTE_BASE = '/home/huagosr/taskgenerator-data/r10-agent-factory'
RUNTIME_FILES = ['src/task_generator/' + p for p in (
    '__init__.py', 'core/__init__.py', 'core/deliverable_contract.py', 'core/scenario_first.py',
    'planning/__init__.py', 'planning/rubric_compiler_v2.py', 'production/__init__.py',
    'production/task_method_pilot.py', 'production/agent_factory.py', 'production/agent_factory_tools.py'
)] + ['Test/r10_process_first_tools.py']


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_root(run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
        raise ValueError('unsafe_run_id')
    return ROOT / 'artifacts/r10' / run_id


def prepare(root, dependency_lock=DEFAULT_LOCK, dependency_remote=DEFAULT_DEPS, *, spec=None, source_bundle=None, batch_id=None):
    if root.exists():
        raise FileExistsError('run_exists')
    if not re.fullmatch(r'/home/huagosr/taskgenerator-data/[A-Za-z0-9_/-]+', dependency_remote) or '..' in dependency_remote:
        raise ValueError('unsafe_dependency_path')
    if f.read(dependency_lock)['pins'] != base.PINS:
        raise ValueError('dependency_pins_changed')
    root.mkdir()
    spec = spec or previous.method.CASES[0]
    if source_bundle is not None:
        from task_generator.production import agent_factory_batch as batch
        sources = batch.public_inputs(sys.modules[__name__], root / 'public', spec, source_bundle)
    else:
        sources = previous.public_inputs(root / 'public', spec)
    hashes = base.code_hashes()
    for path in hashes:
        target = root / 'code' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    shutil.copyfile(dependency_lock, root / 'dependency_lock.json')
    for path in RUNTIME_FILES:
        target = root / 'runtime' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    for role in f.ROLES:
        p = root / 'prompts' / (role + '.md')
        p.parent.mkdir(exist_ok=True)
        p.write_text(f.prompt(role), encoding='utf-8')
    scope = {'created_at': now(), 'seed': spec['seed'], 'host': HOST, 'image': IMAGE, 'image_sha': IMAGE_SHA,
             'remote': REMOTE_BASE + '/' + root.name, 'dependency_remote': dependency_remote,
             'dependency_lock_sha': f.digest(root / 'dependency_lock.json'), 'public_hashes': f.files(root / 'public'),
             'source_hashes': sources, 'code_hashes': hashes, 'runtime_hashes': f.files(root / 'runtime'), 'prompt_hashes': f.files(root / 'prompts'),
             'models': f.MODELS, 'max_launches': 12, 'production_launches': 10, 'seconds': 21600,
             'per_launch_seconds': 1800, 'terminal_reserve_seconds': 3600, 'world_count': 1,
             'authorization': 'User approved one new procurement Agent development world, autonomous versioned revision, independent consultation, final review once and admitted trial once. No grading.',
             'cost_cap': None, 'no_automatic_expansion': True, 'domain': spec['domain']}
    if batch_id:
        scope.update(batch_id=batch_id, case_id=spec['id'], seconds=10800,
                     authorization='One fixed position within the user-approved 60-launch/15-hour Agent factory batch. No independent execution.')
    f.write(root / 'scope.json', scope)
    f.write(root / 'initial_git.json', {'index_sha256': f.digest(ROOT / '.git/index'),
            'status': base._run(['git', 'status', '--porcelain']).stdout})
    f.write(root / 'receipt.json', {'status': 'prepared', 'scope_sha': f.digest(root / 'scope.json'),
            'attempts': [], 'current': {}, 'sessions': {}, 'checks': [], 'consultations': [], 'dispositions': [],
            'next': {'role': 'world'}, 'submitted': False, 'recoveries': 0,
            'task_manual_edits': 0, 'controller_interventions': [], 'first_failure': None})
    return scope


def verify(root):
    scope, state = f.read(root / 'scope.json'), f.read(root / 'receipt.json')
    assert state['scope_sha'] == f.digest(root / 'scope.json'), 'scope_changed'
    assert scope['code_hashes'] == base.code_hashes(), 'code_changed'
    assert scope['code_hashes'] == f.files(root / 'code'), 'code_snapshot_changed'
    assert scope['runtime_hashes'] == f.files(root / 'runtime'), 'runtime_changed'
    assert scope['public_hashes'] == f.files(root / 'public'), 'public_changed'
    assert scope['prompt_hashes'] == f.files(root / 'prompts'), 'prompts_changed'
    assert scope['dependency_lock_sha'] == f.digest(root / 'dependency_lock.json'), 'dependency_changed'
    for relative, value in scope['source_hashes'].items():
        assert f.digest(ROOT / relative) == value, 'source_changed'
    for a in state['attempts']:
        if a.get('raw_hashes'):
            assert f.files(root / a['raw_path']) == a['raw_hashes'], 'raw_changed'
    return scope, state


def environment(root, scope):
    remote, deps = scope['remote'], scope['dependency_remote']
    identity = base._ssh(HOST, f"docker image inspect --format '{{{{.Id}}}}' {IMAGE}", timeout=60).stdout.strip().removeprefix('sha256:')
    if identity != IMAGE_SHA:
        raise ValueError('image_changed')
    lock = base._ssh(HOST, f'sha256sum {deps}/deps/lock.json', timeout=60).stdout.split()[0]
    if lock != scope['dependency_lock_sha']:
        raise ValueError('remote_dependencies_changed')
    if not (root / 'environment.json').exists():
        base._ssh(HOST, f'mkdir -p {REMOTE_BASE} && mkdir {remote}', timeout=60)
        for name in ('public', 'runtime'):
            base._run(base._scp_command(str(root / name), f'{HOST}:{remote}/{name}'), timeout=180)
        for action, target in [('verify-dependencies', '/deps'), ('smoke', '/tmp/factory-smoke')]:
            cmd = base.docker_base(deps) + ['-e', 'PYTHONPATH=/deps/site', '-v', f'{deps}/deps:/deps:ro',
                    '-v', f'{remote}/runtime/Test/r10_process_first_tools.py:/tools.py:ro', '-v', f'{remote}/public:/inputs:ro',
                    '--entrypoint', 'python', IMAGE, '/tools.py', action, target]
            result = base._ssh(HOST, shlex.join(cmd), timeout=180)
            (root / (action + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
        f.write(root / 'environment.json', {'checked_at': now(), 'image': identity, 'dependency_lock': lock,
                'offline_smoke': 'passed', 'credentials': 'not_read_or_copied'})
    base.verify_remote_tree(remote + '/runtime', scope['runtime_hashes'], time.monotonic() + 120)


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def version_path(root, entry):
    p = root / entry['path']
    if f.files(p) != entry['hashes']:
        raise ValueError('version_changed')
    return p


def build_inputs(root, state, role, target, consult_role=None):
    target.mkdir(parents=True)
    public = root / 'public'
    if role == 'world':
        shutil.copytree(public, target, dirs_exist_ok=True)
        return
    world = version_path(root, state['current']['world'])
    shutil.copytree(world / 'candidate', target / 'reference_files')
    effective = consult_role if role == 'consult' else role
    if role != 'solve':
        copy_file(public / 'public_context.json', target / 'public_context.json')
    if effective in ('compile', 'review') or role == 'consult':
        for name in ('professional_rules.json', 'sources.json'):
            copy_file(public / name, target / name)
    if effective == 'world' or (effective == 'mine' and role != 'consult'):
        return
    mine = state['current']['mine']
    task = version_path(root, mine) / 'task.json'
    parsed = previous.method.task_result(task.parent, root / mine['inputs'])
    (target / 'candidate_task.md').write_text(parsed['candidate_task'], encoding='utf-8')
    f.write(target / 'deliverable_contract.json', parsed['contract'])
    if role != 'solve':
        copy_file(task, target / 'task.json')
    if role == 'review' or (role == 'consult' and consult_role == 'compile'):
        compiler = version_path(root, state['current']['compile'])
        for name in ('supervision.json', 'new_rubric.json'):
            copy_file(compiler / name, target / name)


def agent_script(role, session_id=None):
    if session_id and not re.fullmatch(r'[A-Za-z0-9_-]+', session_id):
        raise ValueError('unsafe_session_id')
    lines = ['#!/bin/sh', 'set -eu', 'export HOME=/tmp',
             'export PYTHONPATH=/code/src:/code/Test:/deps/site', 'export PYTHONDONTWRITEBYTECODE=1',
             'export PATH=/workspace/bin:$PATH', 'export PIP_NO_INDEX=1']
    if role in ('world', 'compile', 'solve'):
        lines += ['export CODEX_HOME=/state/codex', 'mkdir -p "$CODEX_HOME"',
                  'ln -sfn /run/codex-home/auth.json "$CODEX_HOME/auth.json"']
        cmd = ['codex', 'exec'] + (['resume', session_id] if session_id else [])
        cmd += ['--dangerously-bypass-approvals-and-sandbox', '--model', 'gpt-5.6-sol', '-c', 'model_reasoning_effort="high"',
                '-c', 'project_doc_max_bytes=0', '--disable', 'plugins', '--disable', 'apps', '--disable', 'multi_agent',
                '--disable', 'skill_search', '--ignore-user-config', '--ignore-rules', '--skip-git-repo-check', '--json', '-']
        lines.append(shlex.join(cmd) + ' < /workspace/TASK.md')
    else:
        lines += ['export XDG_DATA_HOME=/state/data', 'export XDG_CONFIG_HOME=/tmp/opencode-config',
                  'export DEEPSEEK_API_KEY="$(cat /run/secrets/deepseek_api_key)"']
        cmd = ['opencode', 'run', '--pure', '--format', 'json', '--model', 'deepseek/deepseek-v4-pro', '--variant', 'max', '--auto', '--dir', '/workspace']
        if session_id:
            cmd += ['--session', session_id]
        lines.append(shlex.join(cmd) + ' "$(cat /workspace/TASK.md)"')
    return '\n'.join(lines) + '\n'


def session_identity(path, role):
    ids = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        e = json.loads(line)
        if e.get('type') == 'thread.started' and e.get('thread_id'):
            ids.add(e['thread_id'])
        if e.get('sessionID'):
            ids.add(e['sessionID'])
    if len(ids) != 1:
        raise ValueError('session_identity_not_unique')
    return ids.pop()


def run_turn(root, scope, state, request, batch_root=None):
    role = request['role']
    feedback = f.role_feedback(state, request)
    session = f.validate_session(state, role, root.name) if role in f.AUTHOR_ROLES else None
    if session and not re.fullmatch(re.escape(scope['remote']) + r'/state_\d{2}', session['storage']):
        raise ValueError('session_storage_outside_scope')
    if role == 'consult' and (request.get('snapshot') != state['current'][request['consult_role']]['id']
                             or request.get('parents') != f.expected_parents(state, request['consult_role'])):
        raise ValueError('consultation_outside_current_version')
    limit = f.cap(state, role)
    if batch_root is not None:
        from task_generator.production import agent_factory_batch as batch
        limit = min(limit, batch.cap(sys.modules[__name__], batch_root, root, role))
    ordinal = len(state['attempts']) + 1
    name = f'{root.name}-{ordinal:02d}'
    remote = f'{scope["remote"]}/turn_{ordinal:02d}'
    local = root / 'turns' / f'{ordinal:02d}'
    workspace = local / 'workspace'
    workspace.mkdir(parents=True)
    build_inputs(root, state, role, workspace / 'inputs', request.get('consult_role'))
    if feedback is not None:
        f.write(workspace / 'feedback.json', feedback)
    task = (root / 'prompts' / (role + '.md')).read_text(encoding='utf-8')
    if feedback is not None:
        task += '\nRead /workspace/feedback.json as feedback, investigate it rather than blindly accepting it.\n'
    if role == 'consult':
        task += '\nQuestion: ' + request['question']
    task += f'\nProduction launches remaining including this one: {10 - sum(a["role"] not in ("review", "solve") for a in state["attempts"])}.\n'
    (workspace / 'TASK.md').write_text(task, encoding='utf-8')
    parents = f.expected_parents(state, role) if role in f.AUTHOR_ROLES else {}
    consultations = f.relevant_consultations(state, role) if role in f.AUTHOR_ROLES else []
    f.write(workspace / 'role.json', {'role': role, 'parents': parents, 'remaining_production_launches': 10 - len(state['attempts']),
                                    'consultations': consultations})
    session_id = session['id'] if session else None
    storage = session['storage'] if session else f'{scope["remote"]}/state_{ordinal:02d}'
    (workspace / 'agent.sh').write_text(agent_script(role, session_id), encoding='utf-8', newline='\n')
    (workspace / 'bin').mkdir()
    (workspace / 'bin/factory-tools').write_text('#!/bin/sh\nexec python -m task_generator.production.agent_factory_tools "$@"\n', encoding='utf-8', newline='\n')
    draft = local / 'draft'
    if role in state['current'] and role in f.AUTHOR_ROLES:
        shutil.copytree(version_path(root, state['current'][role]), draft)
    else:
        draft.mkdir()
    process = state['current'].get('world', {}).get('process') if role == 'world' else None
    dispositions = [d for d in state.get('dispositions', []) if d['request_id'] in {c['request_id'] for c in consultations}]
    f.write(local / 'broker_config.json', {'root': remote, 'role': role, 'parents': parents, 'process': process,
                                         'consultations': consultations, 'dispositions': dispositions})
    attempt = {'ordinal': ordinal, 'role': role, 'status': 'staging', 'started_at': now(), 'remote': remote,
               'container': name, 'timeout_seconds': limit, 'resumed_session': session_id,
               'input_hashes': f.files(workspace), 'inputs': (workspace / 'inputs').relative_to(root).as_posix()}
    state['attempts'].append(attempt)
    f.write(root / 'receipt.json', state)
    base._ssh(HOST, f'mkdir {remote} && mkdir -p {storage}', timeout=60)
    for p in ('workspace', 'draft', 'broker_config.json'):
        base._run(base._scp_command(str(local / p), f'{HOST}:{remote}/{p}'), timeout=180)
    base._ssh(HOST, f'chmod +x {remote}/workspace/bin/factory-tools', timeout=30)
    base.verify_remote_tree(remote + '/workspace', attempt['input_hashes'], time.monotonic() + 60)
    if (root / 'STOP').exists():
        raise ValueError('user_stopped_before_semantic_start')
    if 'deadline_epoch' not in state:
        state.update(started_at=now(), deadline_epoch=time.time() + scope.get('seconds', 21600))
    if batch_root is not None:
        limit = min(limit, batch.cap(sys.modules[__name__], batch_root, root, role, started=True, appended=True))
    reserve = 3600 if role not in ('review', 'solve') else (1800 if role == 'review' else 0)
    limit = min(limit, int(state['deadline_epoch'] - time.time() - reserve))
    if limit < 1:
        raise ValueError('time_budget_exhausted_before_semantic_start')
    attempt.update(status='started', started_at=now(), timeout_seconds=limit, phase='native')
    f.write(root / 'receipt.json', state)
    deps = scope['dependency_remote']
    cmd = base.docker_base(deps, network=True)
    cmd[2:2] = ['--name', name, '--stop-timeout', '1']
    cmd += ['-v', f'{scope["remote"]}/runtime:/code:ro', '-v', f'{deps}/deps:/deps:ro',
            '-v', f'{remote}/workspace:/workspace:ro', '-v', f'{remote}/draft:/draft:rw',
            '-v', f'{remote}/socket:/run/factory:ro', '-v', f'{storage}:/state:rw', '-w', '/workspace']
    cmd += (['-v', '/home/huagosr/taskgenerator-secrets/codex-auth-current:/run/codex-home:rw'] if role in ('world', 'compile', 'solve')
            else ['-v', '/home/huagosr/taskgenerator-secrets/deepseek_api_key:/run/secrets/deepseek_api_key:ro'])
    cmd += ['--entrypoint', '/bin/sh', IMAGE, '/workspace/agent.sh']
    command = f'''set -eu
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH={scope['remote']}/runtime/src
python3 -m task_generator.production.agent_factory_tools serve {remote}/broker_config.json > {remote}/broker.log 2>&1 &
factory_broker_pid=$!
trap 'timeout 5s docker stop -t 1 {name} >/dev/null 2>&1 || true; kill "$factory_broker_pid" 2>/dev/null || true' EXIT
for factory_wait in $(seq 1 100); do [ -S {remote}/socket/tool.sock ] && break; sleep 0.1; done
test -S {remote}/socket/tool.sock
timeout --signal=TERM --kill-after=2s {max(1, limit-5)}s {shlex.join(cmd)} > {remote}/agent.jsonl 2> {remote}/stderr.txt
'''
    print(f'{role}: launch {ordinal}/12' + (' resume' if session_id else ' fresh'), flush=True)
    start = time.monotonic()
    result = base._ssh(HOST, command, timeout=limit, check=False)
    attempt.update(returncode=result.returncode, elapsed_seconds=time.monotonic() - start)
    attempt['phase'] = 'collection'
    for p in ('agent.jsonl', 'stderr.txt', 'broker.log'):
        base._run(base._scp_command(f'{HOST}:{remote}/{p}', str(local / p)), timeout=90)
    attempt['usage'] = base.usage(local / 'agent.jsonl')
    # Preserve safe original drafts, snapshots and broker evidence even on semantic failure.
    safe_cmd = base.docker_base(deps) + ['-e', 'PYTHONPATH=/code/src:/code/Test:/deps/site', '-v', f'{scope["remote"]}/runtime:/code:ro',
             '-v', f'{remote}:/raw:ro', '--entrypoint', 'python', IMAGE, '-c',
             'from task_generator.production.agent_factory import files; files("/raw/draft"); files("/raw/snapshots"); files("/raw/processes"); print("SAFE")']
    base._ssh(HOST, shlex.join(safe_cmd), timeout=120)
    raw = local / 'raw'
    raw.mkdir()
    for p in ('draft', 'snapshots', 'processes', 'broker.json'):
        exists = base._ssh(HOST, f'test -e {remote}/{p}', timeout=30, check=False).returncode == 0
        if exists:
            base._run(base._scp_command(f'{HOST}:{remote}/{p}', str(raw / p)), timeout=120)
    attempt.update(raw_path=raw.relative_to(root).as_posix(), raw_hashes=f.files(raw))
    f.write(root / 'receipt.json', state)
    native, stderr = (local / 'agent.jsonl').read_text(encoding='utf-8'), (local / 'stderr.txt').read_text(encoding='utf-8')
    if previous.authentication_failed(result.returncode, attempt['usage'], stderr, native):
        raise ValueError('authentication_failed')
    if result.returncode or not attempt['usage']['completed'] or attempt['usage']['error_events']:
        raise ValueError('started_session_failed_no_redraw')
    actual_id = session_identity(local / 'agent.jsonl', role)
    if session_id and actual_id != session_id:
        raise ValueError('resumed_identity_changed')
    attempt['session_id'] = actual_id
    if role in f.AUTHOR_ROLES:
        state['sessions'][role] = {'id': actual_id, 'storage': storage, 'scope': root.name, 'role': role,
                                   'parents': parents, 'normal_end': True}
    base.verify_remote_tree(remote + '/workspace', attempt['input_hashes'], time.monotonic() + 90)
    journal = f.read(raw / 'broker.json') if (raw / 'broker.json').exists() else {'events': [], 'pending': None}
    for event in journal['events']:
        if event['action'] == 'log-check':
            state['checks'].append({'launch': ordinal, **event['result']['recorded']})
    for disposition in journal.get('dispositions', []):
        if disposition not in state.setdefault('dispositions', []):
            state['dispositions'].append(disposition)
    attempt.update(status='completed', completed_at=now())
    attempt['phase'] = 'output_check'
    if role in f.AUTHOR_ROLES:
        pending = journal['pending']
        if not pending:
            raise ValueError('normal_turn_without_explicit_next_action')
        if pending['action'] == 'handoff' and pending.get('target') == 'stop':
            state.update(status='incomplete', stop_reason=pending['reason'], next=None)
            f.write(root / 'receipt.json', state)
            return
        entry = pending['snapshot_entry']
        entry.update(path=(raw / 'snapshots' / entry['id']).relative_to(root).as_posix(), inputs=attempt['inputs'])
        if f.files(raw / 'draft') != entry['hashes']:
            raise ValueError('draft_changed_after_yield')
        outcome = ft.check(role, version_path(root, entry), workspace / 'inputs')
        attempt['outcome'] = outcome
        f.accept_snapshot(state, role, entry)
        action = pending['action']
        if action == 'consult':
            question = ('Independently read these business records. Locate material contradictions, provenance and knowledge-time problems, useful work and concrete information gaps. Ask clarifying questions when evidence is insufficient.' if role == 'world' else pending['reason'])
            state['next'] = {'role': 'consult', 'consult_role': role, 'question': question,
                             'request_id': pending['request_id'], 'snapshot': entry['id'], 'parents': parents}
        elif action == 'submit':
            if outcome['status'] != 'completed':
                raise ValueError('cannot_submit_upstream_issue')
            f.assert_submission(state)
            state.update(submitted=True, submitted_at=now(), next={'role': 'review'})
        elif pending['target'] == 'stop':
            state.update(status='incomplete', stop_reason=pending['reason'], next=None)
        else:
            state['next'] = f.handoff_request(state, role, pending['target'], pending['reason'])
    else:
        pending = journal.get('pending') or {}
        if pending.get('action') != 'finish' or pending.get('hashes') != f.files(raw / 'draft'):
            raise ValueError('readonly_output_not_finished_or_changed')
        outcome = ft.check(role, raw / 'draft', workspace / 'inputs')
        attempt['outcome'] = outcome
        if role == 'consult':
            feedback = f.read(raw / 'draft/consultation.json')
            if request['snapshot'] != state['current'][request['consult_role']]['id']:
                raise ValueError('stale_consultation_result')
            state['consultations'].append({'launch': ordinal, 'role': request['consult_role'], 'snapshot': request['snapshot'],
                                          'parents': request['parents'], 'request_id': request['request_id'],
                                          'finding_ids': [str(i) for i in range(1, len(feedback['findings']) + 1)]})
            feedback = {**feedback, 'request_id': request['request_id'],
                        'findings': [{'finding_id': str(i), **item} for i, item in enumerate(feedback['findings'], 1)]}
            owner = request['consult_role']
            state['next'] = {'role': owner, 'feedback': feedback, 'feedback_origin': 'consultation',
                             'feedback_role': owner, 'feedback_snapshot': state['current'][owner]['id']}
        elif role == 'review':
            state['review'] = outcome
            if outcome['quality'] == 'pass':
                export_package(root, state, workspace / 'inputs')
                state['next'] = {'role': 'solve'}
            else:
                state.update(status='quality_not_passed', next=None)
        else:
            state.update(trial=outcome, status='completed', next=None)
    f.write(root / 'receipt.json', state)


def export_package(root, state, inputs):
    package = root / 'package'
    package.mkdir()
    shutil.copytree(inputs / 'reference_files', package / 'reference_files')
    (package / 'deliverable_files').mkdir()
    rubric = f.read(inputs / 'new_rubric.json')
    task = f.read(inputs / 'task.json')
    f.write(package / 'dataset_row.json', {'task_id': 'anonymous_task', 'title': task['title'],
            'sector': f.read(root / 'scope.json').get('domain', 'procurement_operations') if (root / 'scope.json').exists() else 'procurement_operations',
            'occupation': f.read(root / 'public/public_context.json')['role'],
            'prompt': (inputs / 'candidate_task.md').read_text(encoding='utf-8'),
            'reference_files': ['reference_files/' + p for p in f.files(package / 'reference_files')],
            'deliverable_files': [r['relative_path'] for r in f.read(inputs / 'deliverable_contract.json')['deliverables']],
            'rubric': 'Original Rubric V2 criteria retained; provisional LLM-proxy.',
            'rubric_json': json.dumps(rubric['criteria'], ensure_ascii=False),
            'extra': {'internal_research_only': True, 'professional_status': 'provisional/LLM-proxy'}})
    copy_file(inputs / 'new_rubric.json', package / 'rubric_v2.json')
    copy_file(inputs / 'deliverable_contract.json', package / 'deliverable_contract.json')
    state['package_hashes'] = f.files(package)


def execute(root, *, batch_root=None):
    scope, state = verify(root)
    if scope.get('batch_id'):
        if batch_root is None or batch_root.name != scope['batch_id'] or root.parent.parent.resolve() != batch_root.resolve():
            raise ValueError('batch_execution_required')
    elif batch_root is not None:
        raise ValueError('not_a_batch_scope')
    if state['status'] not in ('prepared', 'paused'):
        raise ValueError('scope_not_executable')
    if state['status'] == 'paused':
        (root / 'STOP').unlink(missing_ok=True)
    ready = f.read(root / 'readiness.json')
    if not ready.get('tests_passed') or ready.get('code_hashes') != scope['code_hashes']:
        raise ValueError('readiness_required')
    lock = root / 'execution.lock'
    with lock.open('x') as handle:
        handle.write(str(__import__('os').getpid()))
    try:
        environment(root, scope)
        state['status'] = 'running'
        f.write(root / 'receipt.json', state)
        while state.get('next'):
            if (root / 'STOP').exists():
                state.update(status='paused', paused_at=now())
                break
            verify(root)
            try:
                if batch_root is None:
                    run_turn(root, scope, state, state['next'])
                else:
                    run_turn(root, scope, state, state['next'], batch_root=batch_root)
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
                attempt = state['attempts'][-1]
                recoverable = (attempt['status'] == 'staging' and attempt['role'] not in ('review', 'solve')
                               and state['recoveries'] == 0
                               and (isinstance(error, subprocess.TimeoutExpired) or error.returncode == 255))
                if not recoverable:
                    raise
                attempt.update(status='presemantic_transport_failure', reason=type(error).__name__)
                state['first_failure'] = state.get('first_failure') or {'launch': attempt['ordinal'], 'reason': attempt['reason']}
                state['recoveries'] += 1
                f.write(root / 'receipt.json', state)
        state['stopped_at'] = now()
    except (Exception, KeyboardInterrupt) as error:
        reason = type(error).__name__ + ':' + str(error)
        # A started abnormal session is terminal, including user interruption.
        if state['attempts'] and state['attempts'][-1]['status'] in ('started', 'staging', 'completed'):
            state['attempts'][-1].update(status='incomplete', reason=reason)
        state.update(status='incomplete', stop_reason=reason, stopped_at=now())
        critical = ('authentication_failed', 'batch_', 'feedback_outside', 'session_outside', 'session_storage',
                    'resumed_identity', 'consultation_outside', 'stale_consultation', 'source_changed', 'code_changed',
                    'raw_changed', 'runtime_changed', 'scope_changed', 'version_changed', 'public_changed',
                    'prompts_changed', 'dependencies_changed', 'path_escape', 'linked_', 'hardlinked_',
                    'session_identity_not_unique', 'already_submitted', 'draft_changed', 'readonly_output_not_finished_or_changed')
        last = state['attempts'][-1] if state['attempts'] else {}
        if any(token in reason for token in critical):
            category = 'global'
        elif ('budget_exhausted' in reason or 'started_session_failed' in reason or 'user_stopped' in reason
              or last.get('phase') == 'output_check' and isinstance(error, (ValueError, KeyError))):
            category = 'case'
        else:
            category = 'controller'
        state['failure_category'] = category
        state['first_failure'] = state.get('first_failure') or {'launch': len(state['attempts']), 'reason': reason}
    finally:
        f.write(root / 'receipt.json', state)
        lock.unlink(missing_ok=True)
    print(json.dumps(report(root), ensure_ascii=False, indent=2))


def stop(root):
    scope, state = f.read(root / 'scope.json'), f.read(root / 'receipt.json')
    (root / 'STOP').touch()
    if state['attempts'] and state['attempts'][-1]['status'] == 'started':
        name = state['attempts'][-1]['container']
        if not re.fullmatch(re.escape(root.name) + r'-\d{2}', name):
            raise ValueError('container_identity_invalid')
        base._ssh(HOST, f'docker stop -t 1 {name}', timeout=15, check=False)
    return {'stop_requested': True, 'scope': root.name}


def report(root):
    state = f.read(root / 'receipt.json')
    return {k: state.get(k) for k in ('status', 'submitted', 'review', 'trial', 'first_failure', 'stop_reason')} | {
        'launches_used': len(state['attempts']), 'consultations': len(state['consultations']),
        'dispositions': len(state.get('dispositions', [])),
        'final_versions': {role: item['id'] for role, item in state['current'].items()},
        'structural_results': [{'launch': a['ordinal'], 'role': a['role'], 'outcome': a.get('outcome')}
                               for a in state['attempts']],
        'native_elapsed_seconds': sum(a.get('elapsed_seconds', 0) for a in state['attempts']),
        'started_at': state.get('started_at'), 'stopped_at': state.get('stopped_at'),
        'model_request_count': None, 'total_cost': None,
        'professional_status': 'provisional/LLM-proxy', 'task_manual_edits': state['task_manual_edits']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'execute', 'status', 'stop', 'report'])
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument('--run-id')
    identity.add_argument('--batch-id')
    parser.add_argument('--source-bundle', type=Path)
    parser.add_argument('--dependency-lock', type=Path, default=DEFAULT_LOCK)
    parser.add_argument('--dependency-remote', default=DEFAULT_DEPS)
    args = parser.parse_args()
    root = safe_root(args.batch_id or args.run_id)
    if args.batch_id:
        from task_generator.production import agent_factory_batch as batch
        if args.action == 'prepare':
            if args.source_bundle is None:
                parser.error('--source-bundle is required to prepare a batch')
            batch.prepare(sys.modules[__name__], root, args.source_bundle, args.dependency_lock, args.dependency_remote)
            result = batch.report(root)
        elif args.action == 'execute':
            result = batch.execute(sys.modules[__name__], root)
        elif args.action == 'stop':
            result = batch.stop(sys.modules[__name__], root)
        else:
            result = batch.report(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.action == 'prepare':
        prepare(root, args.dependency_lock, args.dependency_remote)
        print(json.dumps(report(root)))
    elif args.action == 'execute':
        execute(root)
    else:
        print(json.dumps(stop(root) if args.action == 'stop' else report(root), ensure_ascii=False, indent=2))
