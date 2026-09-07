import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_r10_12_terra_transport_diagnostic", ROOT / "Test/run_r10_12_terra_transport_diagnostic.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_prepare_is_provider_free_and_non_overwriting(tmp_path):
    run_root = tmp_path / "diagnostic"
    scope = RUNNER.prepare(run_root)
    assert scope["normal_calls"] == 3
    assert scope["retries"] == 0
    assert scope["solver_calls"] == 0
    packet = json.loads((run_root / "strict_grade_packet.json").read_text(encoding="utf-8"))
    assert packet["task_id"] == "r10_12_d_abstract_probe"
    try:
        RUNNER.prepare(run_root)
    except FileExistsError:
        pass
    else:
        raise AssertionError("diagnostic scope must not overwrite")


def test_transport_selection_prefers_server_tuzi_then_codex(tmp_path, monkeypatch):
    def receipt(transport, passed):
        return RUNNER.TerraTransportDiagnosticReceiptV1(
            transport=transport, request_started=True, status="passed" if passed else "http_failure",
            environment_sha256="a" * 64, input_sha256="b" * 64,
            output_sha256="c" * 64 if passed else None, http_status=200 if passed else 401,
            evidence_path=f"paths/{transport}",
        )
    first = tmp_path / "first"
    RUNNER.prepare(first)
    monkeypatch.setattr(RUNNER, "_local_tuzi", lambda *_: receipt("local_tuzi_chat", True))
    monkeypatch.setattr(RUNNER, "_server_tuzi", lambda *_: receipt("server_tuzi_chat", True))
    monkeypatch.setattr(RUNNER, "_server_codex", lambda *_: receipt("server_chatgpt_codex", True))
    assert RUNNER.execute(first)["selected_judge_transport"].endswith("tuzi_chat_completions")

    second = tmp_path / "second"
    RUNNER.prepare(second)
    monkeypatch.setattr(RUNNER, "_server_tuzi", lambda *_: receipt("server_tuzi_chat", False))
    assert RUNNER.execute(second)["selected_judge_transport"].endswith("chatgpt_codex")
