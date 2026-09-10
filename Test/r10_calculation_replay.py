"""Execute untrusted teacher calculation scripts without exposing expected answers."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import signal
import threading
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def observed_sha(path):
    """Return the current hash without letting a damaged input hide replay evidence."""
    try:
        return sha(path) if Path(path).is_file() else None
    except OSError:
        return None


def finite_json(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and finite_json(item) for key, item in value.items())
    return value is None or isinstance(value, (str, int, bool))


def bounded_run(command, timeout, env, output_limit=1024 * 1024):
    """Bound both pipes while running; kill the execution group on any limit."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, start_new_session=os.name != 'nt')
    exceeded = threading.Event()
    buffers = [bytearray(), bytearray()]

    def consume(pipe, buffer):
        try:
            while True:
                chunk = os.read(pipe.fileno(), 8192)
                if not chunk:
                    break
                available = output_limit - len(buffer)
                buffer.extend(chunk[:max(available, 0)])
                if len(chunk) > available:
                    exceeded.set()
                    break
        finally:
            pipe.close()

    threads = [threading.Thread(target=consume, args=(pipe, buffer), daemon=True)
               for pipe, buffer in zip((process.stdout, process.stderr), buffers)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    error = None
    while process.poll() is None or any(t.is_alive() for t in threads):
        if exceeded.is_set():
            error = 'output_exceeds_1_mib'
            break
        if time.monotonic() >= deadline:
            error = 'timeout'
            break
        time.sleep(0.005)
    if exceeded.is_set():
        error = 'output_exceeds_1_mib'
    # Also remove descendants left after a successful parent exits (Linux runtime).
    if os.name != 'nt':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.kill()
    process.wait()
    for thread in threads:
        thread.join(timeout=1)
    if error == 'timeout':
        raise subprocess.TimeoutExpired(command, timeout)
    result = subprocess.CompletedProcess(command, process.returncode,
                                         buffers[0].decode('utf-8', errors='replace'),
                                         buffers[1].decode('utf-8', errors='replace'))
    result.limit_error = error
    return result


def main(scripts, inputs, manifest_path, output, timeout_seconds=120):
    scripts, inputs, manifest_path, output = map(Path, (scripts, inputs, manifest_path, output))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rows = []
    deadline = time.monotonic() + timeout_seconds
    status = 'executed'
    version = str(manifest.get('version', 1))
    if version not in ('1', '2'):
        raise ValueError('unsupported_calculation_version')
    entries = manifest['calculations'] if version == '1' else manifest['executions']
    identity_key = 'calculation_id' if version == '1' else 'execution_id'
    result_key = 'calculations' if version == '1' else 'executions'
    for entry in entries:
        identity = entry[identity_key]
        script = (scripts / entry['script']).resolve()
        if not script.is_relative_to(scripts.resolve()) or not script.is_file():
            rows.append({identity_key: identity, 'status': 'error',
                         'error': 'calculation_script_missing_or_escaped'})
            status = 'error'
            break
        script_before = sha(script)
        sources_before = {}
        for source in entry.get('sources', []):
            path = (inputs / source['path']).resolve()
            if not path.is_relative_to(inputs.resolve()) or not path.is_file():
                sources_before[source['path']] = None
            else:
                sources_before[source['path']] = sha(path)
        if (entry.get('script_sha256', script_before) != script_before
                or any(sources_before[row['path']] != row['sha256'] for row in entry.get('sources', []))):
            rows.append({identity_key: identity, 'status': 'error', 'error': 'execution_input_hash_mismatch'})
            status = 'error'
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            rows.append({identity_key: identity, 'status': 'timeout'})
            status = 'timeout'
            break
        started = time.monotonic()
        try:
            result = bounded_run(
                [sys.executable, '-s', str(script), '--inputs', str(inputs)],
                timeout=remaining,
                env={'PYTHONPATH': '/deps/site', 'PYTHONDONTWRITEBYTECODE': '1'},
            )
        except subprocess.TimeoutExpired:
            rows.append({identity_key: identity, 'status': 'timeout',
                         'script_sha256': observed_sha(script),
                         'input_changed': observed_sha(script) != script_before or any(
                             observed_sha(inputs / path) != value for path, value in sources_before.items()),
                         'elapsed_seconds': time.monotonic() - started})
            status = 'timeout'
            break
        script_after = observed_sha(script)
        changed = script_after != script_before or any(
            observed_sha(inputs / path) != value for path, value in sources_before.items())
        if changed or result.limit_error or result.returncode:
            rows.append({identity_key: identity, 'status': 'error',
                         'script_sha256': script_after, 'returncode': result.returncode,
                         'error': 'execution_input_changed' if changed else result.limit_error, 'output_truncated': bool(result.limit_error),
                         'diagnostic': result.stderr[-1000:], 'elapsed_seconds': time.monotonic() - started})
            status = 'error'
            break
        try:
            actual = json.loads(result.stdout)
        except json.JSONDecodeError:
            actual = None
        too_large = len(result.stdout.encode('utf-8')) > 1024 * 1024
        value = actual.get('value') if version == '1' and isinstance(actual, dict) and set(actual) == {'value'} else None
        invalid = (too_large or not isinstance(actual, dict) or not finite_json(actual)
                   or version == '1' and (set(actual) != {'value'} or isinstance(value, (dict, list))))
        if invalid:
            rows.append({identity_key: identity, 'status': 'error',
                         'script_sha256': script_after,
                         'error': ('stdout_exceeds_1_mib' if too_large else
                                   'stdout_must_be_finite_json_object' if version == '2' else
                                   'stdout_must_be_finite_json_scalar'),
                         'elapsed_seconds': time.monotonic() - started})
            status = 'error'
            break
        rows.append({identity_key: identity, 'status': 'executed',
                     'script_sha256': script_after,
                     ('value' if version == '1' else 'output'): value if version == '1' else actual,
                     'elapsed_seconds': time.monotonic() - started})
    payload = {'status': status, result_key: rows, 'version': int(version), 'network': 'none',
               'credentials': 'not_mounted', 'timeout_seconds': timeout_seconds}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'executed': 0, 'error': 1, 'timeout': 124}[status]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scripts', required=True)
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout-seconds', type=int, default=120)
    args = parser.parse_args()
    raise SystemExit(main(args.scripts, args.inputs, args.manifest, args.output, args.timeout_seconds))
