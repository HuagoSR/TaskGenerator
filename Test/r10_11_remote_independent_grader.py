"""One-call official DeepSeek grader used inside the fixed R10.11 image."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path("/workspace")
MAX_FILE_CHARS = 80_000
MAX_TOTAL_CHARS = 260_000


def _xml_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        chunks = []
        for name in sorted(archive.namelist()):
            if not name.endswith(".xml") or not name.startswith(("word/", "xl/")):
                continue
            try:
                root = ET.fromstring(archive.read(name))
            except ET.ParseError:
                continue
            text = " ".join(value.strip() for value in root.itertext() if value.strip())
            if text:
                chunks.append(f"[{name}]\n{text}")
        return "\n".join(chunks)


def _extract(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix in {".txt", ".md", ".csv", ".json"}:
        value = path.read_text(encoding="utf-8", errors="replace")
    elif suffix in {".docx", ".xlsx", ".pptx"}:
        value = _xml_text(path)
    elif suffix == ".pdf":
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"], text=True,
            encoding="utf-8", errors="replace", capture_output=True, timeout=120,
        )
        if result.returncode:
            raise RuntimeError(f"pdf_text_failed:{path.name}")
        value = result.stdout
    else:
        raise ValueError(f"unsupported_material:{path.name}")
    return value[:MAX_FILE_CHARS]


def _materials() -> str:
    files = [ROOT / "candidate_task.md"]
    files += sorted(path for path in (ROOT / "reference_files").rglob("*") if path.is_file())
    files += sorted(path for path in (ROOT / "anonymous_submission").rglob("*") if path.is_file())
    parts, used = [], 0
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        text = _extract(path)
        available = MAX_TOTAL_CHARS - used
        if available <= 0:
            raise RuntimeError("material_text_budget_exceeded")
        text = text[:available]
        parts.append(f"\n===== {relative} =====\n{text}")
        used += len(text)
    return "".join(parts)


def main() -> None:
    rubric = json.loads((ROOT / "rubric_items.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "grade_schema.json").read_text(encoding="utf-8"))
    system = """You independently grade one anonymous professional work product against a fixed rubric.
Use a balanced item-by-item policy. Assess every rubric item exactly once and award an integer from zero through max_score. Cite actual candidate-visible files. Never add criteria, apply a holistic preference or veto, infer authorship, penalize a high score, or perform a second downward audit. If a condition did not trigger under the visible evidence, mark not_triggered and award full item credit. If a needed file cannot be read or applicability cannot be established, mark unresolved and material_status incomplete; do not guess. Explicit format or structure requirements remain requirements. Return only JSON matching the supplied schema; do not output totals."""
    user = json.dumps({
        "rubric_items": rubric,
        "required_evidence_path_roots": ["candidate_task.md", "reference_files/", "anonymous_submission/"],
        "materials": _materials(),
        "output_schema": schema,
    }, ensure_ascii=False)
    body = {
        "model": "deepseek-v4-pro",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "temperature": 0.4,
        "max_tokens": 8192,
        "stream": False,
    }
    key = os.environ["DEEPSEEK_API_KEY"].strip()
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        provider = json.loads(response.read().decode("utf-8"))
    (ROOT / "provider_response.json").write_text(
        json.dumps(provider, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    content = provider["choices"][0]["message"]["content"]
    # Parsing here is deliberately strict: campaign recovery is controlled by
    # the outer runner and can never become a semantic redraw.
    parsed = json.loads(content)
    (ROOT / "grade.raw.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
