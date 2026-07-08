from task_generator.v3_llm_shadow_common import LLMShadowBuilder, LLMShadowRequest


def build_goldenrun_shadow(request: LLMShadowRequest):
    return LLMShadowBuilder().build(request)
