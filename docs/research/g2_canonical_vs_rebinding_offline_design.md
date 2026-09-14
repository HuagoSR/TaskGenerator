# G2 canonical vs rebinding：离线受控设计

> 状态：`materialized_offline_not_run`；2026-09-14。设计已按对称性要求物化并通过离线冻结检查；原 G2 未修改，且未授权 Solver、Grader 或任何外部调用。

## 单一假设

在最终可用事实、证据充分性和职业要求相同的条件下，**将测试属性重新绑定到更正后的实体**，是否比摄取从一开始就正确的实体—属性绑定更容易失败？

目标变量仅为 `binding history`：

- `canonical`：受控质量记录从首次签发起即为 `AP7-261184 | Pass | 698 CFM | Pass`。
- `rebinding`：首次记录为 `AP7-261148 | Pass | 698 CFM | Pass`，随后由正式批准的更正将 serial 及同一行测试属性绑定到 `AP7-261184`。

两侧最终支持的世界状态完全相同；操纵的是达到该状态是否需要撤销旧绑定并建立新绑定。

## 为什么不能直接改现有 G2-B 的 QC 文件

现有 v2 包把旧 mismatch 同时写入了三处候选材料：原 QC sequence 12、`destination_inspection_2026-08-31.xlsx` 的 serial-match/summary/record-note 字段，以及 `cor_supplier_correspondence_2026-08-31_to_2026-09-01.pdf` 的更正请求和 `QA-26-319` 待批状态。若 canonical 侧只替换 QC，这些记录仍会携带 rebinding 历史和旧状态，造成内部冲突；若只从 canonical 删除 correction，又会改变文件数和显著性。因此原 v2 输入不能作为干净的 canonical 条件直接复用。

## 已物化的最小构造

两侧使用相同的 state-neutral prompt、deliverable contract、PO、delivery/receipt、COR authority、`AP7-261191` condition evidence 及 CLIN 0002 证据。共同版本的 inspection 与 correspondence 只保留原始观察及其他未决事项：记录交付 serial `AP7-261184`，但不预判其 QC match；不写 serial correction 请求、`QA-26-319` 或“等待 revised certificate”。这些是为消除条件泄漏而进行的**共同输入重构**，不是实验变量。

唯一条件差异封装在一个两页、同名、候选可见的 `northstar_quality_record_QC-8827.pdf`：

| 页面 | Canonical | Rebinding |
| --- | --- | --- |
| 1：original controlled schedule | sequence 12 = `AP7-261184 / Pass / 698 / Pass` | sequence 12 = `AP7-261148 / Pass / 698 / Pass` |
| 2：record-control history | 说明原 identity 正确且未 amendment；随后以共同句子和共同 current-controlled 行重复 `AP7-261184 / Pass / 698 CFM / Pass` | 说明原 identity `AP7-261148` 被正式更正；随后以同一共同句子和共同 current-controlled 行重复 `AP7-261184 / Pass / 698 CFM / Pass` |

两侧保持相同文件名、文件数、页数、表格位置、签批强度和近似文字量，并在第 2 页同一位置再次明确最终正确绑定。唯一差异是 canonical 确认该绑定始终正确，rebinding 撤销旧绑定后建立该绑定。任何页面均不得写“满足 §1.4”“解除 hold”“可以验收”或 COR 应采取的行动。离线 identity、hash、文本差异、文件可打开性、视觉渲染和条件泄漏检查均已完成；冻结记录位于 `artifacts/r10/r10_g2_canonical_vs_rebinding_v1_20260914/`。

## 预注册观察

1. **Canonical uptake**：是否把 `AP7-261184` 与 `Pass / 698 CFM / Pass` 作为当前受控记录中的完整绑定。
2. **Rebinding update**：是否撤销 `AP7-261148` 的旧绑定，并把 serial 及全部同一行测试属性更新到 `AP7-261184`；只识别 serial correction 不算通过。
3. **共同下游结果**：两侧是否据此判断 `AP7-261184` 的 §1.4 文件性要求已有支持，并且不再为这一项保留 hold；`AP7-261191`、receipt ≠ acceptance、COR 权限及其他事项仍按共同证据处理。这些不变量是污染检查，不是第二个实验变量。

## 解释边界

- canonical 通过而 rebinding 失败：为该配对提供 **rebinding-specific difficulty** 的案例证据；不能由单对推出稳定的“更容易失败”概率。
- 两侧均通过：本对未观察到 rebinding 代价；不证明两者等难。
- 两侧均在 §1.4／disposition 处失败：更像共同下游 rule application 问题，不能归因于 rebinding。
- canonical 自身未正确摄取直接绑定：该对不能提供“canonical 是有效基线”的比较依据。

因此，单个首次配对只能作为 manipulation/behavior probe。若未来要检验“更容易失败”的频率命题，需要另行授权的独立重复；本文不设运行次数、模型、环境或预算。

## 依据

- [节点 directness 审计](dependency_node_directness_audit.md)
- [G2 state-neutral v2 结果](../../artifacts/r10/r10_g2_evidence_state_neutral_ab_v2_20260913/g2_evidence_state_ab_result.md)
