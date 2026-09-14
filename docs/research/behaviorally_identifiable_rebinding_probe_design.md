# G2 behaviorally-identifiable rebinding probe：离线设计

> 状态：`prepared_frozen_not_run`；2026-09-14。三台设备的 Canonical／Rebinding 输入已完成离线物化并通过冻结验证；见 [preparation record](../../artifacts/r10/r10_g2_behaviorally_identifiable_rebinding_v1_20260914/preparation_record.md)。该 scope 不创建执行 receipt 或运行授权，也不修改既有 G2 实验与结果。

## 研究问题与最小世界

目标是检验：在最终事实和证据充分性相同的条件下，正式撤销旧实体绑定并建立当前绑定，是否比直接摄取一直正确的绑定更容易导致错误的职业处置。测量不要求模型抄录完整测试 tuple、复述 correction chain 或展示推理过程；relation update 是否正确必须直接改变逐 serial 的可观察 disposition。

| Serial | 共同事实 | 正确的局部处置 |
| --- | --- | --- |
| `AP7-261184` | 已交付、无 physical issue，且最终存在符合 PO §1.4 的 serial-specific factory-test support | 不得仅因 §1.4 documentation 问题 hold；可纳入 CO 的 acceptance consideration |
| `AP7-261190` | 已交付、物理状态正常，但没有 serial-specific QC record | 保留 documentation hold，并指出所缺记录 |
| `AP7-261191` | 已交付并具有有效 QC record，但 destination inspection 发现 caster／mobility defect | 保留 physical-condition hold；不得把有效 QC 当作缺陷已解决 |

三个 serial 构成闭集：`AP7-261184` 是目标项，`AP7-261190` 是缺失文件的共同阴性控制，`AP7-261191` 是与 QC 正交的 physical-condition 控制。小批量逐台 disposition 对 COR 的验收建议具有职业合理性；receipt、inspection、COR recommendation 与 CO contractual acceptance 始终分开。

## 唯一操纵与输入对称性

- **Canonical**：受控 QC 从最初即把 `AP7-261184` 绑定到合格的 power-on、airflow 与 overall-result 记录。
- **Rebinding**：同一 QC 先把这些测试属性绑定到 `AP7-261148`，再由正式批准的 record-control correction 撤销旧关系，并建立对 `AP7-261184` 的当前绑定。
- 两侧最终 evidence state、测试属性、批准强度、文件数量、文件名、页数、关键字段位置、可访问性和其他材料完全相同；唯一差异是 `AP7-261184` 的 `binding history`。`AP7-261190` 的 QC 缺口与 `AP7-261191` 的 physical defect 在两侧逐字节一致。
- QC 与其他候选材料只陈述事实，不出现 §1.4 是否满足、hold／release、acceptability 或 COR 应采取何种行动等 disposition 提示。

## 交付合同与冻结观察

State-neutral prompt 要求一份简短 COR recommendation，以及覆盖全部三个交付 serial 的闭集 disposition register。每个 serial 仅需包含证据来源、局部 recommendation、未决事项和具体 follow-up；字段顺序与版式由候选决定，固定的是信息义务而不是日志模板。缺少任一 serial 即为结构性不完整。合同不要求完整测试 tuple、supersession 叙述、resolved-issue ledger 或推理链。

仅观察三个职业行为结果，不增加总分：

1. `AP7-261184` 是否获得正确局部 disposition，即不再保留 §1.4 documentation hold；不以是否外化 tuple 或 correction chain 判定。
2. `AP7-261190` 是否继续保持 documentation hold，并把原因限定为缺少 serial-specific QC support。
3. `AP7-261191` 是否保持 physical-condition hold，同时维持 receipt ≠ acceptance 和 COR／CO authority 边界。

要求每个 serial 都有 disposition，使错误 rebinding 不能靠省略中间关系隐藏：若模型没有把有效测试支持更新到 `AP7-261184`，目标行就会错误保留 documentation hold；若更新正确，目标行的该项 hold 必须消失。逐行证据来源保证处置可追溯，但行为正确仍只证明输出与 evidence-conditioned rebinding 一致，不识别模型内部表示。

## 解释与离线可行性门槛

- Canonical 正确，而 Rebinding 仅在 `AP7-261184` 上错误，且两项共同控制与 evidence access 正常：提供单案例 `rebinding-specific behavioral difficulty` 证据。
- 两侧均正确：本对未观察到 rebinding 成本；不证明两者等难。两侧均错在目标项：更像共同 requirement application／disposition 问题。任一共同控制失败、输入不对称或决定性证据未进入模型侧上下文：不能干净归因于 rebinding。
- 职业自然性、闭集可观察性、单一操纵、证据可追溯性、access matching 与 disposition-leakage 检查均已离线通过；这不授权 Solver、Grader 或后续实验。方法边界遵循 [procurement-delivery-acceptance skill](../../.agents/skills/r10/procurement-delivery-acceptance/SKILL.md) 及其 source map：影响处置的未决事项必须可见，但已解决的中间关系无需机械外化。
