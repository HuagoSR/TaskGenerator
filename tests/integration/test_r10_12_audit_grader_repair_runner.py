import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "run_r10_12_audit_grader_repair", ROOT / "Test/run_r10_12_audit_grader_repair.py"
)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_prepare_freezes_three_deliveries_and_no_solver_calls(tmp_path):
    scope = RUNNER.prepare(tmp_path / "g1")
    dry = json.loads((tmp_path / "g1/dry_run.json").read_text(encoding="utf-8"))
    assert scope["solver_calls"] == 0
    assert (dry["primary_normal"], dry["check_normal"]) == (3, 3)
    assert set(dry["deliveries"]) == {"gpt-5.5", "gpt-5.6-sol", "gpt-5.4-mini"}
