from task_generator.v3_llm_shadow_common import LLMShadowBuilder, LLMShadowRequest


def build_reference_narrative_shadow(request: LLMShadowRequest):
    return LLMShadowBuilder().build(request)
