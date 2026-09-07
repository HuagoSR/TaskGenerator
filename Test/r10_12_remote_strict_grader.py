"""One-call strict item grader for a staged R10.12 anonymous submission."""

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

STRICT_SYSTEM = """You independently grade one anonymous professional work product against a fixed rubric.
Assess every rubric item exactly once and award an integer from zero through max_score. Full credit is rare:
award it only when explicit, complete, direct candidate-visible evidence satisfies the entire criterion. Partial,
ambiguous, indirect, or incomplete evidence receives partial credit rather than default full credit. For a
highest-weight item, require strong direct evidence for full credit. When uncertain between two defensible scores,
choose the lower score unless the higher score is clearly justified. Cite actual candidate-visible files. Never
add criteria, apply a holistic preference or veto, infer authorship, penalize a high aggregate score, or perform a
second downward audit. Unsupported claims reduce only rubric items they directly affect. If a visible prerequisite
did not trigger, mark not_triggered and award full item credit. If material cannot be read or applicability cannot
be established, mark unresolved and material_status incomplete; do not guess. Explicit format and structure
requirements remain requirements. Return only JSON matching the supplied schema; do not output totals."""

CONCISE_APPENDIX = """
Keep material_notes to at most 60 words and each item rationale to at most 35 words. State the final evidence-based
decision once; never narrate deliberation, repeat alternatives, or revise the score inside the rationale."""

SHADOW_APPENDIX = """
This is a shadow downward audit and cannot alter the official primary grade. Use the supplied primary grade as the
upper bound for every item: never increase an awarded score. Keep it only when the direct evidence justifies it;
otherwise reduce it. Return the complete rubric item set in the same draft schema."""


def _xml_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        chunks = []
        for name in sorted(archive.namelist()):
            if not name.endswith(".xml") or not name.startswith(("word/", "xl/", "ppt/")):
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
            ["pdftotext", "-layout", str(path), "-"], text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=120,
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


def _endpoint(provider: str) -> tuple[str, str, str]:
    if provider == "deepseek_official":
        return "https://api.deepseek.com/chat/completions", os.environ["DEEPSEEK_API_KEY"].strip(), "deepseek-v4-pro"
    if provider == "tuzi":
        base = os.environ["TUZI_BASE_URL"].strip().rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        return base + "/chat/completions", os.environ["TUZI_API_KEY"].strip(), "gpt-5.6-terra"
    raise ValueError("r10_12_unknown_grader_provider")


def main() -> None:
    request_spec = json.loads((ROOT / "grade_request.json").read_text(encoding="utf-8"))
    rubric = json.loads((ROOT / "rubric_items.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "grade_schema.json").read_text(encoding="utf-8"))
    mode = request_spec["mode"]
    system = STRICT_SYSTEM + CONCISE_APPENDIX
    payload = {
        "rubric_items": rubric,
        "required_evidence_path_roots": ["candidate_task.md", "reference_files/", "anonymous_submission/"],
        "materials": _materials(),
        "output_schema": schema,
    }
    if mode == "shadow":
        system += SHADOW_APPENDIX
        payload["primary_grade_upper_bounds"] = json.loads(
            (ROOT / "primary_grade.json").read_text(encoding="utf-8")
        )
    elif mode not in {"primary", "check"}:
        raise ValueError("r10_12_unknown_grading_mode")
    endpoint, key, model = _endpoint(request_spec["provider"])
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 16384,
        "stream": False,
    }
    if request_spec["provider"] == "deepseek_official":
        body["thinking"] = {"type": "disabled"}
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        provider = json.loads(response.read().decode("utf-8"))
    (ROOT / "provider_response.json").write_text(
        json.dumps(provider, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    parsed = json.loads(provider["choices"][0]["message"]["content"])
    (ROOT / "grade.raw.json").write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
