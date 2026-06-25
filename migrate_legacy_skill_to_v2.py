import json
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parent
LEGACY_SKILL_PATH = ROOT / "Skill" / "skills_config.json"
OUTPUT_PATH = ROOT / "v2_semantic_skills_migrated.json"


SKILL_TYPE_MAP = {
    "base": "compliance",
    "mutate": "fact",
    "trap": "robustness",
    "global": "compliance",
}


MANUAL_CAPABILITY_TAGS: Dict[str, List[str]] = {
    "load_tour_manager_data": ["multi_source_ingestion", "raw_evidence_setup"],
    "load_production_ledger": ["multi_source_ingestion", "ledger_intake"],
    "trap_implicit_currencies": ["currency_inference", "hidden_data_quality_issue"],
    "identify_implicit_currency": ["currency_inference", "jurisdiction_reasoning"],
    "convert_to_usd": ["currency_normalization", "fx_conversion"],
    "load_tax_rates_incomplete": ["reference_table_handling", "tax_reference_setup"],
    "handle_missing_tax_rate": ["reference_gap_resolution", "defensible_assumption_handling"],
    "filter_ledger_entries": ["scope_filtering", "period_isolation"],
    "categorize_expenses": ["expense_mapping", "financial_classification"],
    "calculate_withholding_tax": ["tax_reasoning", "rule_application"],
    "aggregate_source_level_pnl": ["aggregation", "net_income_calculation"],
}


MANUAL_DIFFICULTY_TAGS: Dict[str, List[str]] = {
    "trap_implicit_currencies": ["hidden_signal", "implicit_business_rule"],
    "identify_implicit_currency": ["reasoning_required", "contextual_inference"],
    "handle_missing_tax_rate": ["incomplete_reference_data", "edge_case_reasoning"],
    "filter_ledger_entries": ["scope_disambiguation"],
    "categorize_expenses": ["messy_labels", "taxonomy_mapping"],
    "aggregate_source_level_pnl": ["multi_source", "final_business_deliverable"],
}


def infer_skill_type(legacy_node: dict) -> str:
    return SKILL_TYPE_MAP.get(legacy_node.get("node_type", ""), "hybrid")


def infer_domain_tags(legacy_node: dict) -> List[str]:
    keywords = " ".join(legacy_node.get("keywords", [])).lower()
    tags = []
    if any(token in keywords for token in ["tax", "ledger", "revenue", "expense", "currency", "audit"]):
        tags.extend(["finance", "audit"])
    if "currency" in keywords:
        tags.append("reporting")
    if not tags:
        tags.append("general")
    return list(dict.fromkeys(tags))


def infer_capability_tags(skill_id: str, legacy_node: dict) -> List[str]:
    if skill_id in MANUAL_CAPABILITY_TAGS:
        return MANUAL_CAPABILITY_TAGS[skill_id]
    keywords = [kw.lower().replace(" ", "_") for kw in legacy_node.get("keywords", [])[:3]]
    return keywords or ["legacy_migrated_skill"]


def infer_difficulty_tags(skill_id: str, legacy_node: dict) -> List[str]:
    if skill_id in MANUAL_DIFFICULTY_TAGS:
        return MANUAL_DIFFICULTY_TAGS[skill_id]
    skill_type = infer_skill_type(legacy_node)
    if skill_type == "robustness":
        return ["robustness", "data_quality_issue"]
    if skill_type == "reasoning":
        return ["reasoning_required"]
    return []


def build_semantic_intent(legacy_node: dict) -> dict:
    intents = legacy_node.get("semantics", {}).get("intents", [])
    first_intent = intents[0] if intents else legacy_node.get("skill_name", "Unknown skill")
    business_context = legacy_node.get("data_profile", {}).get("business_context", "")
    return {
        "goal": first_intent,
        "business_meaning": business_context or "Migrated from legacy skill library; business meaning should be refined by a human reviewer.",
        "hidden_difficulty": "This is a migrated starter semantic skill. Refine the hidden challenge intent before large-scale generation use.",
    }


def build_usage_priors(legacy_node: dict) -> dict:
    deliverables = legacy_node.get("semantics", {}).get("deliverables", [])
    return {
        "common_scenarios": [],
        "common_deliverables": deliverables,
        "common_traps": [],
    }


def build_assembly_hints(legacy_node: dict) -> dict:
    data_profile = legacy_node.get("data_profile", {})
    evidence = []
    if "declarative_schemas" in data_profile:
        for _, columns in data_profile["declarative_schemas"].items():
            evidence.extend(columns[:3])
    return {
        "preferred_task_roles": [],
        "preferred_evidence": evidence[:5],
        "suggested_intermediate_artifacts": [],
    }


def migrate_skill(skill_id: str, legacy_node: dict) -> dict:
    requires = legacy_node.get("ports", {}).get("requires", [])
    provides = legacy_node.get("ports", {}).get("provides", [])
    return {
        "skill_id": skill_id,
        "skill_name": legacy_node.get("skill_name", skill_id),
        "skill_type": infer_skill_type(legacy_node),
        "version": "2.0-migrated",
        "domain_tags": infer_domain_tags(legacy_node),
        "capability_tags": infer_capability_tags(skill_id, legacy_node),
        "difficulty_tags": infer_difficulty_tags(skill_id, legacy_node),
        "input_contract": {
            "requires_semantics": requires,
            "optional_semantics": [],
            "provides_semantics": provides,
        },
        "output_contract": {
            "requires_semantics": [],
            "optional_semantics": [],
            "provides_semantics": provides,
        },
        "semantic_intent": build_semantic_intent(legacy_node),
        "usage_priors": build_usage_priors(legacy_node),
        "assembly_hints": build_assembly_hints(legacy_node),
    }


def main() -> None:
    with open(LEGACY_SKILL_PATH, "r", encoding="utf-8") as f:
        legacy_db = json.load(f)

    migrated = [migrate_skill(skill_id, node) for skill_id, node in legacy_db.items()]

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(migrated, f, indent=2, ensure_ascii=False)

    print(f"Migrated {len(migrated)} skills to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
