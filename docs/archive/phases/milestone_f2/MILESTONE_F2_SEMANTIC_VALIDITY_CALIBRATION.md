# Milestone F2 语义有效性门禁校准结论

> 最终状态：`semantic_gate_hold_for_redesign`

## 结论

新门禁证明了 LLM 能稳定发现原任务中的语义缺陷，但当前 reviewer contract、复审通道和 deterministic adjudication 尚不足以安全推广为 blocking production gate。

原始 8 题结果：

- `8/8` 被 DeepSeek 主审阻塞，blocking recall 为 `100%`；
- 三个已知问题家族全部被发现；
- 严格 reason-code 同名 recall 为 `16/19 = 84.2%`；
- `8/8` 原 rubric 的 fact weight 被审计为 `0.0`；
- Claude secondary reviewer 两次返回非 JSON，按合同停止，未进行 JSON 猜测修复或第三次调用。

两轮 repaired twin：

| cohort | 主要修复 | 无主审 blocking 的任务 | 直接 gate pass |
| --- | --- | ---: | ---: |
| revision 01 | 补余额语义、处置规则、Attendee_Count、事实型 rubric | 3/8 | 0/8 |
| revision 02 | 补公式、duplicate 定义、follow-up truth、GoldenRun addendum | 5/8 | 0/8 |

Revision 02 仍未达到预设 `>=7/8` negative-control 通过门槛。#31、#38、#47 仍有明确的 candidate/teacher/GoldenRun 对齐 blocker；#2、#13、#18 属于固定抽审样本，但 Claude 通道不可用；#6、#35 只剩 advisory finding，当前 blocking 模式仍将任何 finding 降为 `revise`。

## 调用与失败证据

- 正式 positive 与两轮 twin 共完成 DeepSeek 主审 `48` 次，另有 `3` 次保留的失败 attempt；
- DeepSeek 模型固定为 `deepseek-v4-pro`，无 mock fallback；
- Tuzi `claude-sonnet-4-6` 两次 blind review 均为 provider contract failure，此后全 campaign 停止该通道；
- 首次接口 hardening 还保留了空 review 误接受和 reason-code 非枚举两类失败证据，二者均通过严格 schema 修复，未混入正式结论；
- 没有 solver 做题、grader 评分、GDPVal 调用或服务器 release 切换。

## 为什么必须 hold

当前实现仍有三个系统问题：

1. Legacy semantic contract 主要从 prompt 迁移，无法提供 generator-owned 的精确 claim dependency；LLM 有时会重复判断实际已存在的材料为缺失。
2. Teacher review package 只接收 blind review、contract 和 teacher artifacts，没有携带经过压缩的 candidate evidence inventory，容易误判新增规则未进入 GoldenRun。
3. Gate 把任何非空 finding 都降为 `revise`，没有把“有证据佐证的 blocker”与 advisory wording suggestion 清晰分层；secondary unavailable 又使固定抽审无法完成。

因此，8/8 positive recall 证明“LLM 有帮助”，但 5/8 repaired-twin blocker clearance 证明“当前门禁还不能作为真值裁决器”。继续扩大到 5 个新任务或 60 题只会放大成本和误判，不能提供推广证据。

## 下一次 redesign 的边界

- Semantic contract 必须由生成器在 reference schema 和 teacher truth 产生前声明，而不是事后从 prompt 反推。
- Teacher review package 必须携带 candidate evidence inventory、字段 schema、规则 locator 和 blind 独立结果的确定性摘要。
- 只有高置信度且有 locator/contract corroboration 的 blocking finding 能阻塞；warning 只进入观察台账。
- Secondary reviewer 需要先用公开 fixture 证明结构化输出通道稳定，再参与私有任务校准。
- 以现有 8+8 作为冻结 regression set；下一次仍需达到 positive `8/8`、repaired twin `>=7/8`，才允许 5 题新生产 smoke。

最终决策：

```text
semantic_validation_implemented = true
positive_blocking_recall = 8 / 8
known_issue_family_recall = 3 / 3
repaired_twin_blocker_clearance = 5 / 8
secondary_channel_valid = false
promotion_decision = semantic_gate_hold_for_redesign
five_task_smoke_started = false
sixty_task_audit_started = false
default_chain_change_allowed = false
```
