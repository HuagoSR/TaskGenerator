"""Local file tools and a scope-bound Unix socket broker; no provider credentials."""
from __future__ import annotations

import json
import contextlib
import io
import os
from pathlib import Path
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile

from task_generator.production import agent_factory as f


class Broker:
    def __init__(self, config):
        self.config = config
        self.root = Path(config['root'])
        self.draft = self.root / 'draft'
        self.store = self.root / 'snapshots'
        self.store.mkdir(exist_ok=True)
        self.events = []
        self.process = config.get('process')
        self.pending = None
        self.dispositions = list(config.get('dispositions', []))

    def handle(self, request):
        action = request['action']
        role = self.config['role']
        if action == 'log-check':
            result = {'recorded': request['result']}
        elif action == 'finish' and role in ('consult', 'review', 'solve'):
            if self.pending:
                raise ValueError('request_pending_end_turn')
            hashes = f.files(self.draft)
            if not any(e['action'] == 'log-check' and e['result']['recorded'].get('tool') == 'check'
                       and e['result']['recorded'].get('hashes') == hashes for e in self.events):
                raise ValueError('current_version_check_required: run factory-tools check')
            self.pending = {'action': 'finish', 'hashes': hashes}
            result = {'status': 'checked_end_turn_now'}
        elif role not in f.AUTHOR_ROLES:
            raise ValueError('read_only_role')
        elif self.pending:
            raise ValueError('request_pending_end_turn')
        elif action == 'record-disposition':
            consultation = next((c for c in self.config.get('consultations', [])
                                 if c['request_id'] == request.get('request_id')), None)
            if not consultation or request.get('finding_id') not in consultation['finding_ids']:
                raise ValueError('unknown_consultation_finding')
            identity = request.get('snapshot')
            matching = [e['result'] for e in self.events if e['action'] == 'snapshot' and e['result']['id'] == identity]
            if not matching or f.files(self.draft) != matching[-1]['hashes']:
                raise ValueError('snapshot_current_draft_required')
            if request.get('decision') not in ('accept', 'partial', 'reject') or not request.get('reason', '').strip():
                raise ValueError('disposition_decision_and_reason_required')
            evidence = request.get('evidence', [])
            if not evidence:
                raise ValueError('disposition_evidence_required')
            for ref in evidence:
                root = self.draft if ref.get('area') == 'draft' else self.root / 'workspace/inputs'
                if ref.get('area') not in ('draft', 'inputs') or not ref.get('locator'):
                    raise ValueError('disposition_area_and_locator_required')
                if not f.safe_path(root, ref['path']).is_file():
                    raise ValueError('disposition_evidence_missing:' + ref['path'])
            result = {k: request[k] for k in ('request_id', 'finding_id', 'snapshot', 'decision', 'reason', 'evidence')}
            self.dispositions.append(result)
        elif action == 'handoff' and request.get('target') == 'stop':
            if not request.get('reason', '').strip():
                raise ValueError('reason_required')
            self.pending = {**request, 'request_id': f.fingerprint(request)}
            result = {'request_id': self.pending['request_id'], 'status': 'queued_end_turn_now'}
        elif action == 'save-process':
            if role != 'world':
                raise ValueError('world_only')
            path = self.draft / 'hidden/process.md'
            value = f.digest(path)
            if not self.process and any((self.draft / 'candidate').rglob('*')):
                raise ValueError('initial_candidate_precedes_process')
            target = self.root / 'processes' / (value + '.md')
            target.parent.mkdir(exist_ok=True)
            if target.exists():
                raise ValueError('process_already_saved')
            shutil.copyfile(path, target)
            self.process = {'hash': value, 'event': len(self.events) + 1}
            result = self.process
        elif action == 'snapshot':
            result = f.snapshot(self.draft, self.store, role, self.config['parents'],
                                request.get('reason', ''), self.process)
        elif action == 'diff':
            previous = f.safe_path(self.store, request['snapshot'])
            old, new = f.files(previous), f.files(self.draft)
            if not previous.is_dir():
                raise ValueError('unknown_snapshot')
            result = {'added': sorted(new.keys() - old.keys()), 'removed': sorted(old.keys() - new.keys()),
                      'changed': sorted(k for k in old.keys() & new.keys() if old[k] != new[k])}
        elif action in ('consult', 'handoff', 'submit'):
            identity = request['snapshot']
            matching = [e['result'] for e in self.events if e['action'] == 'snapshot' and e['result']['id'] == identity]
            if not matching or f.files(self.draft) != matching[-1]['hashes']:
                raise ValueError('snapshot_current_draft_required')
            if not any(e['action'] == 'log-check' and e['result']['recorded'].get('tool') == 'check'
                       and e['result']['recorded'].get('hashes') == matching[-1]['hashes'] for e in self.events):
                raise ValueError('current_version_check_required: run factory-tools check')
            if action != 'consult':
                self.require_dispositions(identity)
            if not request.get('reason', '').strip():
                raise ValueError('reason_required')
            if action == 'submit' and role != 'compile':
                raise ValueError('compiler_submits_only')
            if action == 'handoff':
                allowed = {'world': ('mine', 'stop'), 'mine': ('world', 'compile', 'stop'),
                           'compile': ('world', 'mine', 'stop')}
                if request.get('target') not in allowed[role]:
                    raise ValueError('invalid_handoff')
            self.pending = {**request, 'snapshot_entry': matching[-1], 'request_id': f.fingerprint(request)}
            result = {'request_id': self.pending['request_id'], 'status': 'queued_end_turn_now'}
        else:
            raise ValueError('unknown_broker_action')
        self.events.append({'ordinal': len(self.events) + 1, 'action': action, 'request': request, 'result': result})
        f.write(self.root / 'broker.json', {'events': self.events, 'pending': self.pending, 'process': self.process,
                                          'dispositions': self.dispositions})
        return result

    def require_dispositions(self, identity):
        for c in self.config.get('consultations', []):
            for finding in c['finding_ids']:
                if not any(d['request_id'] == c['request_id'] and d['finding_id'] == finding
                           and d['snapshot'] == identity for d in self.dispositions):
                    raise ValueError('disposition_required:' + c['request_id'] + ':' + finding)


def serve(config_path):
    broker = Broker(f.read(config_path))

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                data = self.rfile.readline(1024 * 1024)
                result = {'ok': True, 'result': broker.handle(json.loads(data))}
            except Exception as error:
                result = {'ok': False, 'error': type(error).__name__ + ':' + str(error)}
            self.wfile.write((json.dumps(result) + '\n').encode())

    address = broker.root / 'socket/tool.sock'
    address.parent.mkdir(exist_ok=True)
    # Bind relative to the scope directory: Linux sockaddr_un limits path bytes.
    # Clients access the same inode through their short, read-only socket mount.
    os.chdir(broker.root)
    with socketserver.UnixStreamServer('socket/tool.sock', Handler) as server:
        os.chmod(address, 0o600)
        server.serve_forever()


def broker_call(action, args):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(60)
        client.connect('/run/factory/tool.sock')
        client.sendall((json.dumps({'action': action, **args}) + '\n').encode())
        result = json.loads(client.makefile('rb').readline(1024 * 1024))
    if not result['ok']:
        raise ValueError(result['error'])
    return result['result']


def check(role, draft, inputs):
    from task_generator.production import task_method_pilot as m
    from r10_process_first_tools import validate
    with contextlib.redirect_stdout(io.StringIO()):
        validate(draft)
    if role == 'world':
        records = f.read(draft / 'hidden/manifest.json')['records']
        actual = f.files(draft / 'candidate')
        if len(records) != len(actual) or {r['path'] for r in records} != set(actual):
            raise ValueError('manifest_coverage')
        for r in records:
            if not r.get('producer') or not r.get('business_purpose') or not isinstance(r.get('source_dependencies'), list):
                raise ValueError('manifest_provenance')
        if not (draft / 'hidden/world.md').is_file():
            raise ValueError('world_record_missing')
        return {'status': 'completed', 'files': actual}
    if role == 'mine':
        return m.task_result(draft, inputs)
    if role == 'compile':
        return m.compilation_result(draft, inputs)
    if role == 'review':
        review = f.read(draft / 'review.json')
        for i, dimension in enumerate(review.get('checks', [])):
            for j, finding in enumerate(dimension.get('findings', [])):
                try:
                    m.reference(inputs, finding.get('path'))
                except ValueError as error:
                    raise ValueError(f'review.json checks[{i}].findings[{j}].path: use one exact file from schema citation_inputs; separate multiple sources into separate findings') from error
        return m.review_result(draft, inputs)
    if role == 'consult':
        result = f.read(draft / 'consultation.json')
        if not isinstance(result.get('summary'), str) or not isinstance(result.get('findings'), list) or not isinstance(result.get('questions'), list):
            raise ValueError('invalid_consultation')
        for r in result['findings']:
            m.reference(inputs, r['path'])
            if not all(r.get(k) for k in ('locator', 'observation', 'limitation')):
                raise ValueError('consultation_evidence_required')
        return {'status': 'completed'}
    contract = f.read(inputs / 'deliverable_contract.json')
    expected = {r['relative_path'] for r in contract['deliverables']}
    actual = set(f.files(draft))
    return {'status': 'completed', 'delivery_status': 'valid' if expected == actual else 'invalid',
            'missing': sorted(expected - actual), 'extra': sorted(actual - expected), 'professional_correctness': 'not_scored'}


def inspect(args):
    area = args.get('area', 'draft')
    if area not in ('draft', 'inputs'):
        raise ValueError('unknown_area')
    root = Path('/draft' if area == 'draft' else '/workspace/inputs')
    path = f.safe_path(root, args['path'])
    f.files(root)
    if path.suffix == '.xlsx':
        from openpyxl import load_workbook
        book = load_workbook(path, data_only=args.get('cached', False))
        sheet = book[args['sheet']] if args.get('sheet') else book.active
        cells = sheet[args.get('range', sheet.calculate_dimension())]
        if not isinstance(cells, tuple):
            cells = ((cells,),)
        elif cells and not isinstance(cells[0], tuple):
            cells = (cells,)
        return {'sheets': book.sheetnames, 'sheet': sheet.title,
                'cells': [{'cell': c.coordinate, 'value': str(c.value), 'type': c.data_type} for row in cells for c in row if c.value is not None][:500]}
    if path.suffix == '.docx':
        from docx import Document
        doc = Document(path)
        return {'paragraphs': [{'paragraph': i, 'text': p.text} for i, p in enumerate(doc.paragraphs, 1)],
                'tables': [[[c.text for c in row.cells] for row in table.rows] for table in doc.tables]}
    if path.suffix == '.pdf':
        from pypdf import PdfReader
        pdf = PdfReader(path)
        page = args.get('page', 1)
        return {'pages': len(pdf.pages), 'page': page, 'text': pdf.pages[page-1].extract_text()}
    return {'text': path.read_text(encoding='utf-8')[:30000]}


def render(args):
    root = Path('/draft' if args.get('area', 'draft') == 'draft' else '/workspace/inputs')
    path = f.safe_path(root, args['path'])
    target = Path(tempfile.mkdtemp(prefix='factory-render-'))
    if args.get('recalculate'):
        if path.suffix != '.xlsx':
            raise ValueError('recalculate_xlsx_only')
        fmt = 'xlsx'
    else:
        fmt = 'pdf'
    if path.suffix != '.pdf':
        subprocess.run(['libreoffice', '-env:UserInstallation=file://' + str(target / 'profile'), '--headless',
                        '--convert-to', fmt, '--outdir', str(target), str(path)], check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        path = target / (path.stem + '.' + fmt)
    if not path.is_file():
        raise ValueError('render_output_missing')
    if fmt == 'pdf':
        subprocess.run(['pdftoppm', '-scale-to', '1400', '-png', str(path), str(target / 'page')], check=True, timeout=120, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return {'output': str(path), 'pages': [str(p) for p in sorted(target.glob('page-*.png'))], 'original_unchanged': True}


def client(action, args):
    cfg = f.read('/workspace/role.json')
    if action == 'help':
        return {'commands': {'inspect': 'area draft|inputs, path, optional sheet/range/page/cached',
                'render': 'area, path, optional recalculate:true; writes scratch only',
                'check': 'no arguments; validates current role artifacts', 'schema': 'no arguments',
                'save-process': 'world only; first save before any candidate files',
                'snapshot': 'reason', 'diff': 'snapshot', 'consult': 'snapshot, reason (visible evidence question)',
                'record-disposition': 'request_id, finding_id, snapshot, decision accept|partial|reject, reason, evidence:[{area:draft|inputs,path,locator}]',
                'finish': 'consult/review/solve only; checks current output, then end normally',
                'handoff': 'snapshot, target world|mine|compile|stop, reason', 'submit': 'snapshot, reason'},
                'role': cfg['role'], 'inputs': sorted(f.files('/workspace/inputs')),
                'remaining_production_launches': cfg['remaining_production_launches'],
                'consultations': cfg.get('consultations', [])}
    if action == 'schema':
        from task_generator.production import task_method_pilot as m
        from task_generator.planning.rubric_compiler_v2 import TaskSpecificRubricV2
        return {'mine': m.MINING.replace('/output', '/draft'), 'compile': m.COMPILATION.replace('/output', '/draft'), 'rubric': TaskSpecificRubricV2.model_json_schema(),
                'review': m.REVIEW.replace('/output', '/draft'),
                'evidence_path_contract': 'Each finding.path is one exact existing file from citation_inputs. No joined paths, prefixes, or directories. Use separate findings for multiple sources.',
                'reserved_decision_id': 'deliverable_structure',
                'citation_inputs': sorted(f.files('/workspace/inputs'))}
    if action in ('check', 'inspect', 'render'):
        result = check(cfg['role'], Path('/draft'), Path('/workspace/inputs')) if action == 'check' else (inspect(args) if action == 'inspect' else render(args))
        broker_call('log-check', {'result': {'tool': action, 'arguments': args, 'ok': True,
                                           'hashes': f.files('/draft'), 'role': cfg['role']}})
        return result
    if action in ('consult', 'handoff', 'submit') and not (action == 'handoff' and args.get('target') == 'stop'):
        outcome = client('check', {})
        if outcome.get('status') != 'completed' and not (action == 'handoff' and args.get('target') in ('world', 'mine')):
            raise ValueError('output_not_ready: request upstream revision or handoff to stop; ' + outcome['status'])
    if action == 'finish':
        if cfg['role'] not in ('consult', 'review', 'solve'):
            raise ValueError('readonly_roles_finish_only')
        outcome = client('check', {})
        if outcome.get('delivery_status') == 'invalid':
            raise ValueError('delivery_contract_invalid: run check for missing and extra paths')
    return broker_call(action, args)


if __name__ == '__main__':
    if sys.argv[1] == 'serve':
        serve(sys.argv[2])
    elif sys.argv[1] == 'validate':
        print(json.dumps(check(sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])), ensure_ascii=False))
    else:
        try:
            text = sys.stdin.read() if not sys.stdin.isatty() else ''
            args = json.loads(text) if text.strip() else {}
            print(json.dumps({'ok': True, 'result': client(sys.argv[1], args)}, ensure_ascii=False))
        except Exception as error:
            print(json.dumps({'ok': False, 'error': type(error).__name__ + ':' + str(error)}))
            sys.exit(1)
