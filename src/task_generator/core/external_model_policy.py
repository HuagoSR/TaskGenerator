from __future__ import annotations


class ExternalModelPolicyError(PermissionError):
    """Raised when a provider/model pair is forbidden by project policy."""


def enforce_external_model_policy(provider: str, model: str) -> None:
    normalized_provider = provider.strip().lower()
    normalized_model = model.strip().lower()
    if normalized_model == "gpt-5.4-pro":
        raise ExternalModelPolicyError("external_model_project_blocked:gpt-5.4-pro")
    if normalized_provider == "tuzi" and normalized_model.startswith("claude-"):
        raise ExternalModelPolicyError("external_model_project_blocked:tuzi_claude")
