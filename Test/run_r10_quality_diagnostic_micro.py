"""Bounded native validation of quality-diagnostic tooling on synthetic fixtures.

The fixtures are developer diagnostics, not occupational task production and not
expert labels.  Their local answer keys are never copied to the remote runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import time
import copy

import run_r10_agent_factory_pilot as runner
from task_generator.production import agent_factory as f
from task_generator.production import quality_diagnostics as quality
from task_generator.production import task_factory_harness as harness


CASES = (
    {"id": "edit_and_rubric_conflict", "amount": 48, "variant": "conflict",
     "expected": ["formal alternative conflicts with the full-credit conclusion", "no candidate material edit"]},
    {"id": "unexplained_knowledge_time", "amount": 63, "variant": "time_issue",
     "expected": ["summary predates the approval it says already occurred"]},
    {"id": "atomic_amount_unit_scope", "amount": 75, "variant": "atomic_control",
     "expected": ["amount, unit, and scope remain one calculation result", "no mechanical split"]},
    {"id": "documented_update_and_plan", "amount": 91, "variant": "time_control",
     "expected": ["planned event is not treated as completed", "documented later update is not a contradiction"]},
)


def _task():
    basis = [{"path": "reference_files/instructions.md", "locator": "line 1",
              "explanation": "Candidate-visible request."}]
    return {"natural_task": True, "rationale": "Synthetic diagnostic fixture only.",
            "title": "Synthetic record review", "prompt": "Review the supplied records and report the requested total.",
            "requirements": [{"id": "r1", "requirement": "Report the total with its unit and stated scope.",
                              "expected_work_product": "A short review memo.", "basis": basis}],
            "deliverables": [{"file_name": "memo.txt", "relative_path": "deliverable_files/memo.txt",
                              "format": "txt", "creation_mode": "create"}]}


def _candidate(path: Path, case):
    path.mkdir(parents=True)
    f.write(path / "record.json", {"items": [{"amount": case["amount"]}], "unit": "synthetic credits"})
    (path / "instructions.md").write_text(
        "Report the total amount in synthetic credits for all rows in record.json and state the included scope.\n",
        encoding="utf-8")
    if case["variant"] == "time_issue":
        (path / "status_note.md").write_text(
            "Created 2031-05-04T08:10Z. The approval was completed at 2031-05-04T09:30:20Z.\n",
            encoding="utf-8")
    elif case["variant"] == "time_control":
        (path / "status_note.md").write_text(
            "Created 2031-05-04T08:10Z. A review is planned for 2031-05-04T09:30Z. "
            "Updated 2031-05-04T10:05Z after the review to record completion.\n", encoding="utf-8")


def _initial_teacher(path: Path, inputs: Path, case):
    (path / "calculation_scripts").mkdir(parents=True)
    (path / "calculation_scripts/total.py").write_text(
        "import argparse,json,pathlib\np=argparse.ArgumentParser();p.add_argument('--inputs');a=p.parse_args()\n"
        "v=json.loads((pathlib.Path(a.inputs)/'reference_files/record.json').read_text())\n"
        "print(json.dumps({'total':sum(row['amount'] for row in v['items'])}))\n", encoding="utf-8")
    evidence = [{"path": "reference_files/record.json", "locator": "/items",
                 "explanation": "Contains the included synthetic amounts."}]
    f.write(path / "supervision.json", {"status": "compiled", "upstream_issues": [], "decisions": [{
        "decision_id": "d1", "requirement_ids": ["r1"], "reference_analysis": "Sum every listed amount.",
        "known_facts": [f"The total is {case['amount']} synthetic credits."], "uncertainties": [],
        "follow_up": [], "evidence": evidence}]})
    alternative = ("A supported conclusion that the amount is not 48 is also full credit."
                   if case["variant"] == "conflict" else
                   "An equivalent formula is accepted when it produces the same scoped total.")
    rubric = {"rubric_version": "r10.atomic_rubric.1", "task_id": "anonymous_task",
              "scoring": "binary_weighted", "criteria": [{
        "criterion_id": "total", "decision_id": "d1",
        "requirement": "Reports the total, unit, and included scope.", "max_points": 2,
        "full_credit_condition": f"Reports {case['amount']} synthetic credits for all rows in record.json.",
        "weight_rationale": "This is one independently observable scoped calculation result.",
        "requirement_basis": [{"path": "candidate_task.md", "locator": "paragraph 1",
                               "explanation": "The assignment requests the scoped total."}],
        "evidence_paths": ["reference_files/record.json", "candidate_task.md"],
        "applicability": "Applies when record.json is readable.", "acceptable_alternatives": alternative,
        "tolerance": "Exact integer result; no rounding tolerance.",
        "verification": "Inspect the reported value, unit, and scope together."}]}
    f.write(path / "new_rubric.json", rubric)
    f.write(path / "basis_draft.json", {"requirements": [{
        "requirement_id": "r1", "obligation": "Report the scoped total.", "basis_kind": "explicit",
        "rubric_ids": ["total"], "candidate_obligation_refs": [{
            "path": "candidate_task.md", "locator": "paragraph 1",
            "explanation": "Candidate-visible request.", "sha256": f.digest(inputs / "candidate_task.md")}]}]})
    f.write(path / "calculation_evidence.json", {"version": 2, "executions": [{
        "execution_id": "total", "script": "total.py", "sources": [{
            "path": "reference_files/record.json", "locator": "/items",
            "sha256": f.digest(inputs / "reference_files/record.json")}]}], "calculations": [{
        "calculation_id": "total", "execution_id": "total", "result_pointer": "/total",
        "rubric_ids": ["total"], "unit": "synthetic credits", "scope": "all rows",
        "method": "sum amount", "assumptions": [],
        "expected": {"value": case["amount"], "tolerance": 0}, "alternatives": []}]})


def _prepare_case(root: Path, case, readiness: Path):
    public = root.parent / (root.name + "_public")
    public.mkdir()
    f.write(public / "public_context.json", {"kind": "synthetic_quality_fixture",
                                              "warning": "No occupational validity claim."})
    f.write(public / "professional_rules.json", {"rules": []})
    f.write(public / "sources.json", {"kind": "synthetic_fixture"})
    candidate = public / "fixture_candidate"
    _candidate(candidate, case)
    scope = runner.prepare(root, protocol="task_factory_harness_v1", synthetic_public=public,
                           spec={"id": case["id"], "seed": "synthetic_tool_fixture", "domain": "synthetic"},
                           harness_options={"purpose": "quality_diagnostic_microtest", "max_launches": 2,
                               "production_launches": 1, "seconds": 7200, "per_launch_seconds": 900,
                               "terminal_reserve_seconds": 900, "atomic_rubric_version": 1,
                               "quality_diagnostics_version": 1, "calculation_contract_version": 2,
                               "authorization": "Two native diagnostic turns per frozen synthetic case."})
    subjects = ['rubric', 'edit']
    if case['variant'] in ('time_issue', 'time_control'):
        subjects.append('record-relations')
    scope.update(diagnostic_micro_version=1, diagnostic_subjects=subjects,
                 diagnostic_batch_id=root.parent.parent.name,
                 remote=f'{runner.REMOTE_BASE}/{root.parent.parent.name}_{root.name}')
    world = root / "fixture/world"
    shutil.copytree(candidate, world / "candidate")
    state = f.read(root / "receipt.json")
    state.update(atomic_rubric_version=1, quality_diagnostics_version=1, compile_stage="basis",
                 upstream_revisions=0, calculation_replays=[])
    state["current"]["world"] = {"id": f.fingerprint(f.files(world)), "role": "world", "parents": {},
                                  "path": "fixture/world", "hashes": f.files(world), "synthetic_preseed": True}
    mine_inputs = root / "fixture/mine_inputs"
    runner.build_inputs(root, state, "mine", mine_inputs, protocol=scope["protocol"])
    mine = root / "fixture/mine"
    f.write(mine / "task.json", _task())
    f.write(mine / "design_intent.json", {"occupational_use": "Synthetic diagnostic only",
            "analysis_points": ["Scoped arithmetic"], "likely_difficulties": ["Quality diagnostics"],
            "evidence": [{"path": "reference_files/instructions.md", "locator": "line 1"}]})
    state["current"]["mine"] = {"id": f.fingerprint(f.files(mine)), "role": "mine",
        "parents": {"world": state["current"]["world"]["id"]}, "path": "fixture/mine",
        "inputs": "fixture/mine_inputs", "hashes": f.files(mine), "synthetic_preseed": True}
    compile_inputs = root / "fixture/compile_inputs"
    runner.build_inputs(root, state, "compile", compile_inputs, protocol=scope["protocol"])
    starter = root / "fixture/initial_compile_draft"
    _initial_teacher(starter, compile_inputs, case)
    before = _task()
    after = copy.deepcopy(before)
    if case['variant'] == 'conflict':
        before['rationale'] = 'Previous internal description.'
    versions = {'before': before, 'after': after,
                'before_result': {'candidate_task': before['prompt'], 'contract': {}},
                'after_result': {'candidate_task': after['prompt'], 'contract': {}}}
    f.write(root / 'fixture/diagnostic_context/edit_versions.json', versions)
    f.write(starter / 'edit_record.json', {'changes': ([{
        'area': 'prompt', 'actual_change_paths': ['/rationale']}] if case['variant'] == 'conflict' else [])})
    compile_prompt = """This is a frozen synthetic quality-diagnostic microtest, not occupational production.
Read only candidate-visible inputs and the starter teacher files in /draft. Do not browse or call another model.
Use factory-tools schema, inspect, diagnose rubric, and status. Check whether the formal rubric is atomic,
internally consistent, and supported by the candidate obligation. Correct teacher files only when evidence warrants it;
never alter candidate records or assignment facts. Write rubric_diagnostic.json using the exact diagnose identities,
criterion hashes, clause pointers, and peer IDs. The formal new_rubric.json remains the sole scoring authority.
Read diagnostic_context/edit_versions.json and correct edit_record.json declarations to match actual differences;
do not modify either version or candidate files. Internal rationale changes are not prompt changes.
For required record-relations, locate and compare the dated statements in candidate files and save record_relations.json.
Query schema for artifact diagnostic_result. Save diagnostic_result.json with current candidate hashes and explain
completed or upstream_issue; unresolved issues may be reported honestly. Run check, then finish and end immediately.
The controller replays calculations and hands the result to independent review. Do not request production submit,
consultation, development trials, or replay actions. Required subjects: SUBJECTS.
"""
    compile_prompt = compile_prompt.replace('SUBJECTS', ', '.join(subjects))
    (root / "prompts/compile.md").write_text(compile_prompt, encoding="utf-8")
    (root / "prompts/review.md").write_text(harness.prompt("review", {
        "atomic_rubric_version": 1, "quality_diagnostics_version": 1}), encoding="utf-8")
    scope.update(initial_compile_draft="fixture/initial_compile_draft",
                 initial_compile_draft_hashes=f.files(starter), fixture_hashes=f.files(root / "fixture"),
                 prompt_hashes=f.files(root / "prompts"), readiness_sha256=f.digest(readiness), frozen_at=runner.now())
    f.write(root / "scope.json", scope)
    state.update(scope_sha=f.digest(root / "scope.json"), next={"role": "compile"}, status="prepared")
    f.write(root / "receipt.json", state)
    shutil.copyfile(readiness, root / "readiness.json")


def prepare(root: Path, readiness: Path):
    if root.exists():
        raise FileExistsError("quality_microtest_exists")
    ready = f.read(readiness)
    if ready.get("tests_passed") is not True:
        raise ValueError("offline_readiness_required")
    root.mkdir(parents=True)
    (root / "cases").mkdir()
    cases = []
    for case in CASES:
        child = root / "cases" / case["id"]
        _prepare_case(child, case, readiness)
        cases.append({"id": case["id"], "path": child.relative_to(root).as_posix(),
                      "scope_sha256": f.digest(child / "scope.json")})
    f.write(root / "answer_keys.json", {"warning": "developer expectations; not expert labels",
                                         "cases": [{"id": row["id"], "expected": row["expected"]} for row in CASES]})
    f.write(root / "batch.json", {"purpose": "quality_diagnostic_microtest", "max_launches": 8,
                                   "diagnostic_micro_version": 1,
                                   "runner_sha256": f.digest(Path(__file__)),
                                   "seconds": 7200, "cases": cases,
                                   "answer_keys_sha256": f.digest(root / "answer_keys.json")})
    f.write(root / "receipt.json", {"status": "prepared", "attempts": 0, "started_at": None,
                                     "deadline_epoch": None, "cases": {}})


def launch_counts(root):
    manifest = f.read(root / 'batch.json')
    cases = {}
    for row in manifest['cases']:
        state = f.read(root / row['path'] / 'receipt.json')
        attempts = state.get('attempts', [])
        # Staging attempts have not entered the native invocation boundary.
        cases[row['id']] = sum(harness.attempt_consumes_launch(a) for a in attempts)
    return {'total': sum(cases.values()), 'cases': cases}


def check_batch_launch(child, scope):
    root = child.parent.parent
    manifest, batch = f.read(root / 'batch.json'), f.read(root / 'receipt.json')
    if scope.get('diagnostic_batch_id') != root.name or batch.get('status') != 'running' or batch.get('active_case') != child.name:
        raise ValueError('diagnostic_batch_entry_required')
    row = next((r for r in manifest['cases'] if root / r['path'] == child), None)
    if row is None or row['scope_sha256'] != f.digest(child / 'scope.json'):
        raise ValueError('diagnostic_child_identity_changed')
    counts = launch_counts(root)
    if counts['total'] >= manifest['max_launches'] or counts['cases'][child.name] >= scope['max_launches']:
        raise ValueError('quality_microtest_batch_budget_exhausted')
    if time.time() >= batch['deadline_epoch']:
        raise ValueError('quality_microtest_batch_budget_exhausted')
    return batch['deadline_epoch']


def persist_batch_launches(child):
    root = child.parent.parent
    batch = f.read(root / 'receipt.json')
    batch['attempts'] = launch_counts(root)['total']
    f.write(root / 'receipt.json', batch)


def execute(root: Path):
    manifest, batch = f.read(root / "batch.json"), f.read(root / "receipt.json")
    if manifest.get('diagnostic_micro_version') != 1 or manifest.get('runner_sha256') != f.digest(Path(__file__)):
        raise ValueError('diagnostic_micro_method_changed_or_historical_scope')
    if batch["status"] != "prepared" or batch["attempts"]:
        raise ValueError("fresh_quality_microtest_required")
    if launch_counts(root)['total']:
        raise ValueError('fresh_quality_microtest_required')
    batch.update(status="running", started_at=runner.now(), deadline_epoch=time.time() + manifest["seconds"])
    f.write(root / "receipt.json", batch)
    hard_stop = False
    for row in manifest["cases"]:
        child = root / row["path"]
        scope, state = runner.verify(child)
        if f.digest(child / "scope.json") != row["scope_sha256"] or scope["fixture_hashes"] != f.files(child / "fixture"):
            raise ValueError("quality_microtest_fixture_changed")
        state.update(status="running", deadline_epoch=batch["deadline_epoch"],
                     budget_limits={key: scope[key] for key in (
                         "max_launches", "production_launches", "seconds", "per_launch_seconds", "terminal_reserve_seconds")})
        f.write(child / "receipt.json", state)
        try:
            batch['active_case'] = child.name
            f.write(root / 'receipt.json', batch)
            runner.environment(child, scope)
            for expected_role in ("compile", "review"):
                batch['attempts'] = launch_counts(root)['total']
                if time.time() >= batch["deadline_epoch"] or batch["attempts"] >= manifest["max_launches"]:
                    raise ValueError("quality_microtest_batch_budget_exhausted")
                if state.get("next", {}).get("role") != expected_role:
                    raise ValueError("quality_microtest_sequence_not_satisfied")
                runner.run_turn(child, scope, state, state["next"])
                batch["attempts"] = launch_counts(root)['total']
                f.write(root / "receipt.json", batch)
                if state.get('next') is None:
                    break
            batch["cases"][row["id"]] = {"status": state.get("status"), "launches": len(state["attempts"])}
        except (Exception, KeyboardInterrupt) as error:
            runner.record_execution_failure(child, state, error)
            batch["cases"][row["id"]] = {"status": "incomplete", "launches": len(state["attempts"]),
                                            "reason": f"{type(error).__name__}:{error}"}
            if any(token in str(error) for token in ("authentication_failed", "identity", "fingerprint", "changed")):
                hard_stop = True
        finally:
            f.write(child / "receipt.json", state)
            batch['attempts'] = launch_counts(root)['total']
            f.write(root / "receipt.json", batch)
        if hard_stop:
            break
    batch.update(status="stopped" if hard_stop else "completed", active_case=None, stopped_at=runner.now())
    f.write(root / "receipt.json", batch)
    return report(root)


def report(root: Path):
    manifest, batch = f.read(root / "batch.json"), f.read(root / "receipt.json")
    rows = []
    for row in manifest["cases"]:
        child = root / row["path"]
        state = f.read(child / "receipt.json")
        rows.append({"id": row["id"], "status": state.get("status"),
                     "launches": len(state.get("attempts", [])),
                     "stop_reason": state.get("stop_reason"),
                     "review": state.get("review"), "submitted": state.get("submitted", False)})
    return {"purpose": manifest["purpose"], "status": batch["status"],
            "launches": launch_counts(root)['total'], "recorded_launches": batch['attempts'],
            "launch_count_mismatch": batch['attempts'] != launch_counts(root)['total'],
            "validation_complete": all(row.get('review') is not None for row in rows),
            "max_launches": manifest["max_launches"],
            "started_at": batch["started_at"], "cases": rows,
            "claim": "Synthetic native diagnostic evidence only; not occupational production or expert validation."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "execute", "status", "report"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--readiness", type=Path)
    args = parser.parse_args()
    root = runner.safe_root(args.run_id)
    result = prepare(root, args.readiness) if args.action == "prepare" else (
        execute(root) if args.action == "execute" else report(root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
