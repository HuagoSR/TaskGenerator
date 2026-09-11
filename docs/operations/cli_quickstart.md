# Public read-only CLI Quickstart

`taskgen` is a local, offline reader and preview tool. It does not use model credentials, SSH, E2B, rw-task, or any historical runner. It cannot create a scope, run a task, score a delivery, or recover a closed experiment.

## Install

Use a Python 3.12+ environment from a source checkout:

```powershell
python -m pip install --no-build-isolation --no-deps -e .
taskgen --help
taskgen doctor
```

`doctor` reports only local CLI capabilities. A missing provider key or remote host is not a failure because neither is read.

## Read existing local evidence

```powershell
taskgen runs --root "artifacts/r10" --json
taskgen inspect "path/to/candidate-package" --json
taskgen report "path/to/report.json" --format markdown --output "artifacts/cli/reports/summary.md"
```

Supported objects are a GDPval-shaped candidate package, an R10 directory with `scope.json` or `receipt.json`, and a legacy rw-task `report.json`. The public repository does not ship ignored artifacts; these commands are useful only when the caller has a permitted local copy.

`report --output` refuses an existing target. All other read commands keep their source tree unchanged. The CLI does not execute document macros, scripts, archives, models, or remote tools.

## Preview a future scope

```powershell
taskgen generate --spec data/cli/generate.example.json --dry-run --json
taskgen evaluate --spec data/cli/evaluate.legacy.example.json --dry-run --json
```

Examples are neutral, local-only shapes. They refer only to the adjacent synthetic `example_input.json`. Copy `data/cli/local.example.json` to ignored `data/cli/local.json` only for local artifact and report paths. Local configuration and specs reject unknown fields, absolute/UNC paths, parent traversal, and any provider or credential setting.

Preview validates local files and optional hashes, then reports that provider authentication and remote readiness remain unknown. It does not create output directories, receipts, scopes, or budget records. A later `--execute` interface requires a separately authorized, input/model/environment/budget-bound scope and is not implemented here.

## Interpretation limits

The CLI keeps legacy rw-task diagnostics separate from formal atomic-rubric scoring. A displayed legacy score is neither a formal score nor evidence of occupational validity, fairness, difficulty, model ranking, or scalable production. Project-level evidence and current research limits remain in [项目概要](../../项目概要.md).
