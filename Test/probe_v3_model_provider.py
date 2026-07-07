from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RW_TASK_ENV = ROOT.parent / "rw-task" / ".env"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "phase14" / "model_provider_probes"


def load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def read_key_from_file(path: Optional[str]) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip()


def resolve_profile(args: argparse.Namespace) -> Dict[str, str]:
    env_values = load_env_file(Path(args.env_path)) if args.env_path else {}
    if args.provider in {"tuzi-openai", "tuzi-gemini-openai"}:
        api_key = (
            args.api_key
            or env_values.get("OPENAI_API_KEY")
            or env_values.get("GRADER_API_KEY")
            or env_values.get("OPENAI_API_KEY_BACKUP")
            or os.getenv("OPENAI_API_KEY", "")
        )
        base_url = args.base_url or env_values.get("OPENAI_BASE_URL") or "https://api.tu-zi.com/v1"
        return {"api_key": api_key, "base_url": base_url.rstrip("/"), "key_source": "tuzi_env_or_arg"}
    api_key = args.api_key or read_key_from_file(args.key_path) or os.getenv("DEEPSEEK_API_KEY", "")
    base_url = args.base_url or "https://api.deepseek.com"
    return {"api_key": api_key, "base_url": base_url.rstrip("/"), "key_source": "deepseek_key_path_or_arg"}


def post_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    json_mode: bool,
    timeout: int,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 256,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
        return {
            "status_code": response.status_code,
            "ok": 200 <= response.status_code < 300,
            "body": response.json() if response.content else {},
        }


def get_models(*, base_url: str, api_key: str, timeout: int) -> Dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"})
            body = response.json() if response.content else {}
            ids = []
            if isinstance(body, dict):
                ids = [str(item.get("id")) for item in body.get("data", []) if isinstance(item, dict) and item.get("id")]
            return {"status_code": response.status_code, "ok": 200 <= response.status_code < 300, "model_ids": ids[:200]}
    except Exception as exc:
        return {"status_code": None, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


def content_from_response(response: Dict[str, Any]) -> str:
    body = response.get("body") or {}
    try:
        return str(body.get("choices", [{}])[0].get("message", {}).get("content") or "")
    except (AttributeError, IndexError):
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe OpenAI-compatible model providers without printing secrets.")
    parser.add_argument("--provider", choices=["tuzi-openai", "tuzi-gemini-openai", "deepseek-official"], required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--env-path", default=str(DEFAULT_RW_TASK_ENV))
    parser.add_argument("--key-path", default=str(ROOT / "deepseek-key.txt"))
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    profile = resolve_profile(args)
    api_key = profile["api_key"]
    report: Dict[str, Any] = {
        "report_version": "v3.model_provider_probe.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": args.provider,
        "model": args.model,
        "base_url": profile["base_url"],
        "key_source": profile["key_source"],
        "has_api_key": bool(api_key),
        "models_endpoint": None,
        "chat_probe": None,
        "json_probe": None,
        "usable": False,
        "failure_reasons": [],
    }
    if not api_key:
        report["failure_reasons"].append("missing api key")
    else:
        report["models_endpoint"] = get_models(base_url=profile["base_url"], api_key=api_key, timeout=args.timeout_seconds)
        chat = post_chat(
            base_url=profile["base_url"],
            api_key=api_key,
            model=args.model,
            messages=[{"role": "user", "content": "Reply with exactly: pong"}],
            json_mode=False,
            timeout=args.timeout_seconds,
        )
        chat_content = content_from_response(chat)
        report["chat_probe"] = {
            "status_code": chat.get("status_code"),
            "ok": chat.get("ok"),
            "non_empty_content": bool(chat_content.strip()),
            "content_preview": chat_content[:80],
        }
        json_probe = post_chat(
            base_url=profile["base_url"],
            api_key=api_key,
            model=args.model,
            messages=[{"role": "user", "content": "Return JSON only: {\"ok\": true, \"value\": 7}"}],
            json_mode=args.provider == "deepseek-official",
            timeout=args.timeout_seconds,
        )
        json_content = content_from_response(json_probe)
        parsed_json = None
        try:
            parsed_json = json.loads(json_content)
        except json.JSONDecodeError:
            parsed_json = None
        report["json_probe"] = {
            "status_code": json_probe.get("status_code"),
            "ok": json_probe.get("ok"),
            "non_empty_content": bool(json_content.strip()),
            "parsed_json": parsed_json,
            "content_preview": json_content[:120],
        }
        if not report["chat_probe"]["non_empty_content"]:
            report["failure_reasons"].append("chat probe returned empty content")
        if parsed_json is None:
            report["failure_reasons"].append("json probe did not parse")
        report["usable"] = not report["failure_reasons"]

    if args.write_report:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{args.provider}_{args.model.replace('/', '_').replace(':', '_')}_probe.json"
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["report_path"] = str(output_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["usable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
