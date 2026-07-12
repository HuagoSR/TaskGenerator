# Milestone F2：LLM 语义有效性闭环

> 状态：`superseded_by_calibration_hold`

## 目标

在结构性 verifier 与 production QA 之间增加 `semantic_validation`，独立检查候选材料充分性、答案唯一性、teacher truth、GoldenRun 和 rubric 对齐。该层不替代确定性验证，也不让 LLM 直接修改任务。

## 当前实现合同

```text
task_generation
→ semantic_validation
→ production_review
→ rw_task_eval
```

- 每题生成 `TaskSemanticContract`，显式连接 requirement、claim、candidate dependency、determinism、teacher expectation 和 rubric criterion。
- Candidate-blind review 物理排除 GoldenRun、answer key、annotation 和 rubric。
- Teacher/rubric review 只能在 blind review 固定 SHA-256 后执行。
- 主审固定为 DeepSeek official `deepseek-v4-pro`；低置信度、无确定性佐证的 blocker、冲突和固定 10% 抽审使用 `claude-sonnet-4-6`。
- blocking 模式要求全部 case 的 semantic gate pass；否则 production QA 不得晋升。
-修复只能进入 `revision_01/02`，上游修复使 teacher、annotation、rubric、verifier 和 QA 失效；两轮后仍失败则 blocked。
-历史 profile 默认关闭外部语义调用；旧 Manifest 和原 60 题保持只读。

## 当前证据

- 核心 schema、隔离包、deterministic adjudicator、版本化修复计划、secondary-review routing 和 production QA 接口已实现。
- 离线 prepare smoke 对两个既有任务生成合同和盲审包；在没有真实 review 时均为 `revise`，外部效果为 false。
- 8 题人工诊断的 aggregate acceptance contract 已冻结，不包含 prompt、reference、teacher truth、rubric 正文或 GDPVal 内容。

## 最终执行结果

运行环境解除限制后，用户再次授权并完成 DeepSeek 主审。Claude 复审连续两次违反 JSON 输出合同，按 campaign 规则停止该通道。原始 8 题全部被阻塞，但两轮 repaired twin 仅有 5/8 消除主审 blocking 问题，未达到 7/8 门槛，因此最终为 `semantic_gate_hold_for_redesign`。

1. 8 题 positive replay：完成；
2. repaired twin revision 01/02：完成但未达门槛；
3. 5 题新生产 smoke：按停止规则未执行；
4. 既有 60 题只读诊断审计：按停止规则未执行；
5. `finance-production` blocking promotion：拒绝。

最终证据见 `MILESTONE_F2_SEMANTIC_VALIDITY_CALIBRATION.md`。不得宣称语义门禁已推广，也不得进入 RL。
