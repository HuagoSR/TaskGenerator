"""Execute untrusted teacher calculation scripts without exposing expected answers."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_json(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and finite_json(item) for key, item in value.items())
    return value is None or isinstance(value, (str, int, bool))


def main(scripts, inputs, manifest_path, output, timeout_seconds=120):
    scripts, inputs, manifest_path, output = map(Path, (scripts, inputs, manifest_path, output))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rows = []
    deadline = time.monotonic() + timeout_seconds
    status = 'executed'
    version = str(manifest.get('version', 1))
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
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            rows.append({identity_key: identity, 'status': 'timeout'})
            status = 'timeout'
            break
        started = time.monotonic()
        try:
            result = subprocess.run(
                [sys.executable, '-s', str(script), '--inputs', str(inputs)],
                text=True, capture_output=True, timeout=remaining,
                env={'PYTHONPATH': '/deps/site', 'PYTHONDONTWRITEBYTECODE': '1'},
            )
        except subprocess.TimeoutExpired:
            rows.append({identity_key: identity, 'status': 'timeout',
                         'script_sha256': sha(script), 'elapsed_seconds': time.monotonic() - started})
            status = 'timeout'
            break
        if result.returncode:
            rows.append({identity_key: identity, 'status': 'error',
                         'script_sha256': sha(script), 'returncode': result.returncode,
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
                         'script_sha256': sha(script),
                         'error': ('stdout_exceeds_1_mib' if too_large else
                                   'stdout_must_be_finite_json_object' if version == '2' else
                                   'stdout_must_be_finite_json_scalar'),
                         'elapsed_seconds': time.monotonic() - started})
            status = 'error'
            break
        rows.append({identity_key: identity, 'status': 'executed',
                     'script_sha256': sha(script),
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
