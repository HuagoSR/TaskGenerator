# Public V3 Skill Extraction Smoke Package

This package is synthetic and intentionally safe to send to external LLM APIs for smoke testing.

Milestone C uses this same package in two governed profiles:

- `public-smoke-offline`: deterministic mock extraction, no network, exact acceptance counts.
- `public-smoke-llm`: DeepSeek skill extraction with explicit source-upload permission, still with external task evaluation disabled.

The package is a pipeline fixture, not evidence of training-data or benchmark quality. See `acceptance_contract.json` for the governed smoke thresholds.
