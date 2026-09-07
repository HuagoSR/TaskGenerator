"""Grade one immutable strict packet through a fixed Chat endpoint."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path("/workspace")


def main() -> None:
    request_spec = json.loads((ROOT / "grade_request.json").read_text(encoding="utf-8"))
    packet = json.loads((ROOT / "strict_grade_packet.json").read_text(encoding="utf-8"))
    provider = request_spec["provider"]
    if provider == "deepseek_official":
        endpoint = "https://api.deepseek.com/chat/completions"
        key = os.environ["DEEPSEEK_API_KEY"].strip()
        model = "deepseek-v4-pro"
    elif provider == "tuzi":
        base = os.environ["TUZI_BASE_URL"].strip().rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        endpoint = base + "/chat/completions"
        key = os.environ["TUZI_API_KEY"].strip()
        model = "gpt-5.6-terra"
    else:
        raise ValueError("r10_12_packet_unknown_provider")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": packet["strict_system"]},
            {"role": "user", "content": json.dumps({
                "rubric_items": packet["rubric_items"],
                "required_evidence_path_roots": packet["required_evidence_path_roots"],
                "materials": packet["materials"],
                "output_schema": packet["output_schema"],
            }, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 16384,
        "stream": False,
    }
    if provider == "deepseek_official":
        body["thinking"] = {"type": "disabled"}
    request = urllib.request.Request(
        endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            raw = response.read().decode("utf-8")
            status = response.status
            request_id = response.headers.get("x-request-id")
    except urllib.error.HTTPError as exc:
        (ROOT / "provider_status.json").write_text(json.dumps({
            "request_started": True, "http_status": exc.code, "error_type": "HTTPError",
        }, indent=2) + "\n", encoding="utf-8")
        raise
    result = json.loads(raw)
    usage = result.get("usage") or {}
    (ROOT / "provider_status.json").write_text(json.dumps({
        "request_started": True, "http_status": status, "response_model": result.get("model"),
        "response_object": result.get("object"), "request_id": request_id,
        "usage": {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    parsed = json.loads(result["choices"][0]["message"]["content"])
    (ROOT / "grade.raw.json").write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
