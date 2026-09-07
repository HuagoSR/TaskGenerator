"""Run the immutable R10.12-D Terra transport diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

import run_r10_12_stirrup_calibration as base
from r10_12_remote_strict_grader import STRICT_SYSTEM
from run_r10_behavioral_pilot import CHATGPT_CODEX_STACK, _run_remote
from task_generator.evaluation.codex_grader import _strict_output_schema
from task_generator.evaluation.independent_rubric_grader import (
    IndependentRubricGradeDraftV1,
    canonical_json_sha256,
)
from task_generator.evaluation.stirrup_supplement import (
    StrictGradePacketV1,
    TerraTransportDiagnosticReceiptV1,
)


RUN_ID = "r10_12_terra_transport_diagnostic_20260904"
DEFAULT_RUN = ROOT / "artifacts/r10" / RUN_ID
REMOTE_ROOT = base.REMOTE_ROOT
CODEX_AUTH_DIR = "/home/huagosr/taskgenerator-secrets/codex-auth-current"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path: Path, value: Any) -> None:
    base._write(path, value)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _packet() -> StrictGradePacketV1:
    schema = _strict_output_schema(IndependentRubricGradeDraftV1.model_json_schema())
    return StrictGradePacketV1(
        task_id="r10_12_d_abstract_probe",
        strict_system=STRICT_SYSTEM,
        rubric_items=[{"rubric_item_id": "probe_item", "max_score": 1,
                       "criterion": "The submitted note contains exactly OK."}],
        required_evidence_path_roots=["candidate_task.md", "reference_files/", "anonymous_submission/"],
        materials="\n===== candidate_task.md =====\nCreate a note containing exactly OK.\n"
                  "\n===== anonymous_submission/note.txt =====\nOK\n",
        output_schema=schema,
    )


def prepare(run_root: Path) -> dict[str, Any]:
    if run_root.exists():
        raise FileExistsError(f"r10_12_d_run_root_exists:{run_root}")
    run_root.mkdir(parents=True)
    packet = _packet()
    _write(run_root / "strict_grade_packet.json", packet)
    scope = {
        "scope_version": "r10.terra_transport_diagnostic_scope.1", "campaign_id": run_root.name,
        "created_at": _now(), "model": "gpt-5.6-terra", "normal_calls": 3, "retries": 0,
        "transports": ["local_tuzi_chat", "server_tuzi_chat", "server_chatgpt_codex"],
        "input_sha256": packet.canonical_sha256(), "endpoint_switching": False,
        "model_fallback": False, "solver_calls": 0, "secret_material_recorded": False,
    }
    _write(run_root / "scope.json", scope)
    return scope


def snapshot(run_root: Path) -> dict[str, Any]:
    target = run_root / "environment_snapshot.json"
    if target.exists():
        raise FileExistsError("r10_12_d_snapshot_exists")
    env, _ = base._solver_environment()
    key = env["AGENT_API_KEY"].strip()
    url = env["AGENT_BASE_URL"].strip().rstrip("/")
    api_root = url[:-3] if url.endswith("/v1") else url
    request = urllib.request.Request(api_root + "/v1/models", headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(request, timeout=90) as response:
        visible = json.loads(response.read().decode("utf-8"))
    model_visible = any(row.get("id") == "gpt-5.6-terra" for row in visible.get("data", []))
    remote = base._ssh(base.HOST,
        "stat -c '%a' /home/huagosr/taskgenerator-secrets/eval_tuzi.env; "
        "sha256sum /home/huagosr/taskgenerator-secrets/eval_tuzi.env | cut -d' ' -f1; "
        "test -d /home/huagosr/taskgenerator-secrets/codex-auth-current && echo auth_present; "
        "docker run --rm --entrypoint codex taskgenerator-eval:milestone-r9-huago-cone-a2d8a5e35099 --version",
        timeout=180,
    )
    lines = [line.strip() for line in remote.stdout.splitlines() if line.strip()]
    result = {
        "snapshot_version": "r10.terra_transport_environment.1", "captured_at": _now(),
        "local_key_sha256": hashlib.sha256(key.encode()).hexdigest(),
        "local_base_url_sha256": hashlib.sha256(url.encode()).hexdigest(),
        "local_terra_visible": model_visible, "visible_model_ids_sha256": canonical_json_sha256(
            sorted(row.get("id") for row in visible.get("data", []) if row.get("id"))
        ),
        "server_secret_mode": lines[0] if lines else None,
        "server_secret_sha256": lines[1] if len(lines) > 1 else None,
        "server_codex_auth_present": "auth_present" in lines,
        "server_codex_version": next((line for line in lines if line.startswith("codex-cli")), None),
        "secret_material_recorded": False,
    }
    _write(target, result)
    return result


def _validate_grade(path: Path) -> str:
    draft = IndependentRubricGradeDraftV1.model_validate_json(path.read_text(encoding="utf-8"))
    if len(draft.assessments) != 1 or draft.assessments[0].rubric_item_id != "probe_item":
        raise ValueError("r10_12_d_item_coverage")
    return canonical_json_sha256(draft)


def _environment_hash(run_root: Path, transport: str) -> str:
    snapshot_value = json.loads((run_root / "environment_snapshot.json").read_text(encoding="utf-8"))
    return canonical_json_sha256({"transport": transport, "snapshot": snapshot_value})


def _local_tuzi(run_root: Path, workspace: Path) -> TerraTransportDiagnosticReceiptV1:
    workspace.mkdir(parents=True)
    env, _ = base._solver_environment()
    url = env["AGENT_BASE_URL"].strip().rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    packet = json.loads((run_root / "strict_grade_packet.json").read_text(encoding="utf-8"))
    body = {"model": "gpt-5.6-terra", "messages": [
        {"role": "system", "content": packet["strict_system"]},
        {"role": "user", "content": json.dumps({key: packet[key] for key in (
            "rubric_items", "required_evidence_path_roots", "materials", "output_schema")}, ensure_ascii=False)},
    ], "response_format": {"type": "json_object"}, "temperature": 0, "max_tokens": 4096, "stream": False}
    request = urllib.request.Request(url + "/chat/completions", data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {env['AGENT_API_KEY'].strip()}"}, method="POST")
    status, http_status, output_sha = "protocol_failure", None, None
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            http_status = response.status
            provider = json.loads(response.read().decode("utf-8"))
        parsed = json.loads(provider["choices"][0]["message"]["content"])
        _write(workspace / "grade.raw.json", parsed)
        output_sha, status = _validate_grade(workspace / "grade.raw.json"), "passed"
    except urllib.error.HTTPError as exc:
        http_status, status = exc.code, "http_failure"
    except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as exc:
        status = "format_failure"
        _write(workspace / "failure.json", {"type": type(exc).__name__, "message": str(exc)[:300]})
    return TerraTransportDiagnosticReceiptV1(
        transport="local_tuzi_chat", request_started=True, status=status,
        environment_sha256=_environment_hash(run_root, "local_tuzi_chat"),
        input_sha256=_sha(run_root / "strict_grade_packet.json"), output_sha256=output_sha,
        http_status=http_status, evidence_path=workspace.relative_to(run_root).as_posix(),
    )


def _stage_remote(run_root: Path, workspace: Path) -> None:
    workspace.mkdir(parents=True)
    shutil.copy2(run_root / "strict_grade_packet.json", workspace)
    _write(workspace / "grade_request.json", {"provider": "tuzi"})
    shutil.copy2(ROOT / "Test/r10_12_remote_packet_grader.py", workspace / "r10_12_remote_strict_grader.py")


def _server_tuzi(run_root: Path, workspace: Path) -> TerraTransportDiagnosticReceiptV1:
    _stage_remote(run_root, workspace)
    code, error = base._remote_grade_call(workspace, f"{REMOTE_ROOT}/{run_root.name}/server_tuzi", "tuzi")
    status, output_sha, http_status = "protocol_failure", None, None
    if (workspace / "provider_status.json").is_file():
        provider_status = json.loads((workspace / "provider_status.json").read_text(encoding="utf-8"))
        http_status = provider_status.get("http_status")
    if code:
        status = "http_failure" if http_status else "protocol_failure"
        _write(workspace / "failure.json", {"type": status, "detail": error[-300:]})
    else:
        try:
            output_sha, status = _validate_grade(workspace / "grade.raw.json"), "passed"
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            status = "format_failure"
            _write(workspace / "failure.json", {"type": type(exc).__name__, "message": str(exc)[:300]})
    return TerraTransportDiagnosticReceiptV1(
        transport="server_tuzi_chat", request_started=True, status=status,
        environment_sha256=_environment_hash(run_root, "server_tuzi_chat"),
        input_sha256=_sha(run_root / "strict_grade_packet.json"), output_sha256=output_sha,
        http_status=http_status, exit_code=code, evidence_path=workspace.relative_to(run_root).as_posix(),
    )


def _server_codex(run_root: Path, workspace: Path) -> TerraTransportDiagnosticReceiptV1:
    workspace.mkdir(parents=True)
    shutil.copy2(run_root / "strict_grade_packet.json", workspace)
    packet = json.loads((run_root / "strict_grade_packet.json").read_text(encoding="utf-8"))
    _write(workspace / "grade_schema.json", packet["output_schema"])
    (workspace / "TASK.md").write_text(
        "Read only strict_grade_packet.json. Apply its strict_system to its rubric_items and materials. "
        "Return exactly one JSON object matching grade_schema.json. Do not inspect other files or add criteria.\n",
        encoding="utf-8",
    )
    code, _, error = _run_remote(
        host=base.HOST, remote=f"{REMOTE_ROOT}/{run_root.name}/server_codex", local=workspace,
        stack=CHATGPT_CODEX_STACK, grade=True, image=base.IMAGE, codex_auth_dir=CODEX_AUTH_DIR,
        timeout_seconds=900, codex_reasoning_effort="medium", model_override="gpt-5.6-terra",
    )
    status, output_sha = "protocol_failure", None
    if code == 0:
        try:
            output_sha, status = _validate_grade(workspace / "grade.raw.json"), "passed"
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            status = "format_failure"
            _write(workspace / "failure.json", {"type": type(exc).__name__, "message": str(exc)[:300]})
    else:
        _write(workspace / "failure.json", {"type": status, "detail": error[-300:]})
    return TerraTransportDiagnosticReceiptV1(
        transport="server_chatgpt_codex", request_started=True, status=status,
        environment_sha256=_environment_hash(run_root, "server_chatgpt_codex"),
        input_sha256=_sha(run_root / "strict_grade_packet.json"), output_sha256=output_sha,
        exit_code=code, evidence_path=workspace.relative_to(run_root).as_posix(),
    )


def execute(run_root: Path) -> dict[str, Any]:
    if (run_root / "results.json").exists():
        raise FileExistsError("r10_12_d_results_exist")
    receipts = [
        _local_tuzi(run_root, run_root / "paths/local_tuzi_chat"),
        _server_tuzi(run_root, run_root / "paths/server_tuzi_chat"),
        _server_codex(run_root, run_root / "paths/server_chatgpt_codex"),
    ]
    _write(run_root / "results.json", receipts)
    by = {row.transport: row for row in receipts}
    selected = None
    if by["server_tuzi_chat"].status == "passed":
        selected = "gpt-5.6-terra@tuzi_chat_completions"
    elif by["server_chatgpt_codex"].status == "passed":
        selected = "gpt-5.6-terra@chatgpt_codex"
    summary = {
        "summary_version": "r10.terra_transport_diagnostic_summary.1",
        "status": "supported" if selected else "incomplete", "selected_judge_transport": selected,
        "local_tuzi_success_not_sufficient": True, "completed_at": _now(),
    }
    _write(run_root / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "snapshot", "execute"))
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    result = {"prepare": prepare, "snapshot": snapshot, "execute": execute}[args.command](args.run_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
