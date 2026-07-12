# Milestone F2：LLM 语义有效性闭环

> 状态：`implementation_complete_external_calibration_blocked_by_runtime_policy`

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

## 未完成的外部执行边界

首次真实校准需要将固定 8 题的 candidate-visible package 发送给 DeepSeek，并在触发条件下把相同候选材料及审查证据发送给 Claude。用户已经明确授权该 campaign，但当前执行环境仍以非公开工作区数据外传风险拒绝了真实调用。确认没有后台进程启动、没有任务包上传、没有 provider 调用产生，因此以下步骤未执行：

1. 8 题 positive replay；
2. 8 个 repaired twin 的真实 negative-control review；
3. 5 题新生产 smoke；
4. 既有 60 题只读诊断审计；
5. 将 `finance-production` 从 diagnostic 晋升为 blocking。

在真实校准完成前不得宣称语义门禁已推广，也不得进入 RL。
