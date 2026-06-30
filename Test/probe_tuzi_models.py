import argparse
import json
import sys
import time
from pathlib import Path

import requests


DEFAULT_ENV_PATH = Path(r"E:\THU\2026Spring\SRT\rw-task\.env")
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODELS = [
    "gpt-5-mini",
    "gpt-5",
    "gpt-5-pro",
    "gpt-5.4-pro",
    "gpt-5.4",
    "o3",
    "o4-mini",
    "gpt-4.1",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3-pro-preview",
    "gemini-3.1-pro-preview",
]


def load_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def probe_model(base_url: str, api_key: str, model: str, timeout_s: float) -> dict[str, object]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise assistant."},
            {"role": "user", "content": "Reply with exactly: pong"},
        ],
        "temperature": 0,
        "max_tokens": 32,
    }

    started = time.perf_counter()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
        elapsed = time.perf_counter() - started
    except Exception as exc:
        return {
            "model": model,
            "ok": False,
            "elapsed_s": round(time.perf_counter() - started, 2),
            "error": repr(exc),
        }

    result: dict[str, object] = {
        "model": model,
        "ok": response.ok,
        "status_code": response.status_code,
        "elapsed_s": round(elapsed, 2),
    }

    try:
        data = response.json()
    except Exception:
        result["error"] = response.text[:500]
        return result

    if response.ok:
        content = ""
        try:
            content = data["choices"][0]["message"]["content"]
        except Exception:
            content = json.dumps(data, ensure_ascii=False)[:500]
        result["reply"] = content
        usage = data.get("usage")
        if usage:
            result["usage"] = usage
    else:
        result["error"] = data

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe tuzi/OpenAI-compatible models with a tiny chat request.")
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH, help="Path to .env file containing AGENT_API_KEY/AGENT_BASE_URL.")
    parser.add_argument("--timeout", type=float, default=60.0, help="Per-model timeout in seconds.")
    parser.add_argument("--model", action="append", dest="models", help="Model id to test. Repeatable.")
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    args = parser.parse_args()

    if not args.env_path.exists():
        raise FileNotFoundError(f".env file not found: {args.env_path}")

    env_values = load_env_file(args.env_path)
    api_key = (
        env_values.get("AGENT_API_KEY")
        or env_values.get("STIRRUP_OPENAI_API_KEY")
        or env_values.get("OPENAI_API_KEY")
        or ""
    )
    base_url = (
        env_values.get("AGENT_BASE_URL")
        or env_values.get("STIRRUP_OPENAI_BASE_URL")
        or env_values.get("OPENAI_BASE_URL")
        or DEFAULT_BASE_URL
    )
    if not api_key:
        raise RuntimeError("No AGENT_API_KEY/STIRRUP_OPENAI_API_KEY/OPENAI_API_KEY found in env file.")

    models = args.models or DEFAULT_MODELS
    results = [probe_model(base_url, api_key, model, args.timeout) for model in models]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"Base URL: {base_url}")
    print(f"Env file: {args.env_path}")
    print()
    for item in results:
        status = "OK" if item["ok"] else "FAIL"
        line = f"[{status}] {item['model']}  status={item.get('status_code', 'ERR')}  time={item['elapsed_s']}s"
        print(line)
        if item["ok"]:
            print(f"  reply: {str(item.get('reply', '')).strip()[:200]}")
        else:
            print(f"  error: {str(item.get('error', ''))[:400]}")
    print()
    ok_count = sum(1 for item in results if item["ok"])
    print(f"Usable models: {ok_count}/{len(results)}")


if __name__ == "__main__":
    main()



