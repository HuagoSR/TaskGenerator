import argparse
import json
import sys
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_skill_extractor import (  # noqa: E402
    FallbackSkillExtractor,
    LLMSkillExtractor,
    MockSkillExtractor,
    ProviderAttempt,
    build_deepseek_config,
    build_tuzi_config,
)
from v3_source_schema import SkillExtractionPromptPackage, load_json_file  # noqa: E402


DEFAULT_ENV_PATH = ROOT / ".env"
DEFAULT_DEEPSEEK_KEY_PATH = ROOT / "deepseek-key.txt"


def build_extractor(args: argparse.Namespace) -> tuple[FallbackSkillExtractor, List[ProviderAttempt]]:
    extractors = []
    setup_attempts: List[ProviderAttempt] = []

    if args.provider in {"auto", "tuzi"}:
        tuzi_config = build_tuzi_config(
            env_path=args.env_path,
            model_override=args.model,
            timeout_seconds=args.timeout_seconds,
        )
        if tuzi_config is not None:
            if not args.allow_external_upload:
                raise RuntimeError("Tuzi provider would upload prompt-package content externally. Re-run with --allow-external-upload if this source package is approved for external API use.")
            extractors.append(("tuzi", LLMSkillExtractor(tuzi_config)))
        elif args.provider == "tuzi":
            raise RuntimeError("Tuzi provider requested, but .env OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL are incomplete.")
        else:
            setup_attempts.append(
                ProviderAttempt(
                    provider_name="tuzi",
                    model=args.model or "unknown",
                    success=False,
                    error_type="ProviderNotConfigured",
                    error_message=".env OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL are incomplete.",
                )
            )

    if args.provider in {"auto", "deepseek"}:
        deepseek_config = build_deepseek_config(
            key_path=args.deepseek_key_path,
            model=args.deepseek_model,
            timeout_seconds=args.timeout_seconds,
        )
        if deepseek_config is not None:
            if not args.allow_external_upload:
                raise RuntimeError("DeepSeek provider would upload prompt-package content externally. Re-run with --allow-external-upload if this source package is approved for external API use.")
            extractors.append(("deepseek", LLMSkillExtractor(deepseek_config)))
        elif args.provider == "deepseek":
            raise RuntimeError("DeepSeek provider requested, but deepseek-key.txt is missing or empty.")
        else:
            setup_attempts.append(
                ProviderAttempt(
                    provider_name="deepseek",
                    model=args.deepseek_model,
                    success=False,
                    error_type="ProviderNotConfigured",
                    error_message="deepseek-key.txt is missing or empty.",
                )
            )

    include_mock = args.provider in {"auto", "mock"} or args.allow_mock_fallback
    if include_mock:
        extractors.append(("mock", MockSkillExtractor()))

    if not extractors:
        raise RuntimeError("No extraction provider is configured.")
    return FallbackSkillExtractor(extractors=extractors, allow_mock_fallback=include_mock), setup_attempts


def write_outputs(
    output_dir: Path,
    package: SkillExtractionPromptPackage,
    provider_name: str,
    candidates: List[object],
    attempts: List[object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_payload = {
        "request_id": package.request_id,
        "extractor": provider_name,
        "candidate_count": len(candidates),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    report_payload = {
        "request_id": package.request_id,
        "normalized_source_count": len(package.normalized_sources),
        "candidate_count": len(candidates),
        "candidate_names": [candidate.proposed_name for candidate in candidates],
        "provider_used": provider_name,
    }
    attempts_payload = {
        "request_id": package.request_id,
        "attempts": [attempt.to_report() for attempt in attempts],
    }

    with open(output_dir / "extracted_skill_candidates.json", "w", encoding="utf-8") as f:
        json.dump(candidate_payload, f, ensure_ascii=False, indent=2)
    with open(output_dir / "skill_extraction_report.json", "w", encoding="utf-8") as f:
        json.dump(report_payload, f, ensure_ascii=False, indent=2)
    with open(output_dir / "provider_attempts.json", "w", encoding="utf-8") as f:
        json.dump(attempts_payload, f, ensure_ascii=False, indent=2)

    print(json.dumps(report_payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V3 LLM-backed skill extraction with provider fallback.")
    parser.add_argument("--prompt-package", type=Path, required=True, help="Path to skill_extraction_prompt_package.json.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for extracted skill candidates and reports.")
    parser.add_argument("--provider", choices=["auto", "tuzi", "deepseek", "mock"], default="auto")
    parser.add_argument("--model", default=None, help="Override .env OPENAI_MODEL for the Tuzi/OpenAI-compatible provider.")
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash", help="DeepSeek official model.")
    parser.add_argument("--max-candidates", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--allow-mock-fallback", action="store_true")
    parser.add_argument("--allow-external-upload", action="store_true", help="Required before sending prompt-package content to Tuzi or DeepSeek.")
    parser.add_argument("--env-path", type=Path, default=DEFAULT_ENV_PATH)
    parser.add_argument("--deepseek-key-path", type=Path, default=DEFAULT_DEEPSEEK_KEY_PATH)
    args = parser.parse_args()

    package = SkillExtractionPromptPackage.model_validate(load_json_file(str(args.prompt_package)))
    extractor, setup_attempts = build_extractor(args)
    candidates = extractor.extract(package, max_candidates=args.max_candidates)
    provider_used = next(
        (attempt.provider_name for attempt in extractor.attempts if attempt.success),
        "unknown",
    )
    write_outputs(
        output_dir=args.output_dir,
        package=package,
        provider_name=provider_used,
        candidates=candidates,
        attempts=setup_attempts + extractor.attempts,
    )


if __name__ == "__main__":
    main()
