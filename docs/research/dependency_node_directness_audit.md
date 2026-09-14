# Dependency-node directness audit：G1/W3 与 G2

> 状态：开发阶段、离线回顾性核查；2026-09-14。仅审计既有候选材料与结果，不修改实验记录、创建任务或授权模型运行。

## 判定规则

- `directly_stated`：一份候选可见材料明确陈述完整节点命题（或该条件下的否定命题），无需与另一事实组合。
- `derived`：材料不直接给出节点命题，必须计算、应用规则或组合上游事实才能得到。
- `mixed`：核心事实直接给出，但完整节点状态仍需跨来源匹配、处理时间／正式性冲突或完成关系组合。

这里审计的是**节点取得方式**，不是节点在职业依赖图中的层号。图上的 D2 不自动代表两步 inference。

## G1/W3 directness

| 节点 | 条件下的节点命题 | Directness | 最小候选来源 |
| --- | --- | --- | --- |
| D0 | A：没有证明按 kit 线性计费的 carrier quote；B：新增正式承运商确认。 | `directly_stated` | A：`market_research.md`；B：`freight_rate_confirmation.md`。 |
| D1 | A：线性关系未由记录建立；B：同一路线无固定起步费且 freight 随 kit 数量成比例。 | `directly_stated` | 同上；两份材料分别直接说出“不足”与“比例计费”。 |
| D2 | 12→18 缩放是 sensitivity assumption，或已成为有事实支持的处理。 | A：`directly_stated`；B：`mixed` | A：`market_research.md` 明称 sensitivity assumption；B：`freight_rate_confirmation.md` 直接允许 per-kit adjustment，但需与仍在材料中的较早 “no carrier quote” 记录按日期和证据状态协调。 |
| D3 | 选择并执行历史 freight normalization 方法。 | `derived` | `historical_order_export.csv`（12 kit、$1,180/LOT）＋当前 18-kit 要求＋`market_research.md`（4.20%）＋相应 A/B freight 证据。材料不直接给归一化结果。 |
| D4 | 在 F&R 判断中保留或解除“线性缩放无事实依据”这一局部结论限制。 | `derived` | D3 的分析结果＋任务对 assumption、limitation、decision effect 的要求；整体结论还需报价、IGCE 等其他比较依据。 |

因此 W3 的 D0→D2 不是三层纯推理链：A 的“不足”和“sensitivity assumption”甚至在同一段中直接写明；B 的比例关系也直接写明，只有把后来的新证据用于覆盖较早证据状态属于组合更新。真正明显增加推理距离的是 D3 的方法执行，以及 D4 的结论边界更新。

## G2 directness

| 节点 | 条件下的节点命题 | Directness | 最小候选来源 |
| --- | --- | --- | --- |
| D0 | A：批准更正缺失；B：`QC-8827-C1` 已正式批准。 | `directly_stated` | A：supplier correspondence 的记录状态；B：correction 的 approval status、日期与 `QA-26-319` 完成记录。 |
| D1 | sequence 12 的 serial 从 `AP7-261148` 更正为 `AP7-261184`。 | A：`mixed`（应保持未纠正）；B：`directly_stated` | A：原 QC、交付／检查记录和未批准的供应商解释；B：correction 的 “Approved correction” 段及表格。 |
| D2 | sequence 12 的 `power-on Pass / 698 CFM / overall Pass` 属于 `AP7-261184`。 | A：`mixed`（不得正式重绑定）；B：**`directly_stated`** | B correction 单独一句和更正表格均完整直述该归属；无需先从 D1 推出。 |
| D3 | `AP7-261184` 已满足 PO §1.4 的 serial-to-factory-test-record 对应要求。 | `derived` | B correction 的 D1、D2 事实＋`purchase_order_CREL-26-P-0174.pdf` §1.4。材料不直接给合同满足结论。 |
| D4 | 只解除 `AP7-261184` 的 §1.4 文件性 hold。 | `derived` | D3＋PO 的 acceptance/authority 条款及任务要求；“只解除这一项”还需区分其他未决事项。 |

G2-B 更准确的证据拓扑不是串行的 `D1 → D2`，而是：

```text
approved correction ─┬─→ serial identity = AP7-261184        （直接陈述）
                     └─→ tests/results belong to AP7-261184  （直接陈述）
两项事实 + PO §1.4 ─────→ requirement satisfied               （推导）
requirement state ──────→ remove only this documentary hold   （推导）
```

## 审计结论

当前 graph depth 不能直接当作 inference depth。W3 中 D0–D2 大量由材料直接暴露或只需一次证据状态协调；G2-B 中 D1 与 D2 是同一 correction 的并列直接陈述，只有 D3、D4 构成清楚的下游推导。

因此 G2-B 在原图 D2 的首个失败应收紧表述为 **relation uptake / state rebinding failure**：模型摄取了 correction 和 identity correction，却没有把其中另一条已经直接可见的关系事实纳入状态。它支持 relational updating 存在困难，但不能作为“传播到 depth 2 太深而失败”的证据，也尚不足以证明传播深度本身导致失败。

## 证据记录

- G1/W3：`w3_assumption_boundary.md`、`w3_diff_note.md`、`w3_ab_result.md`，以及冻结的 W3 A/B candidate inputs。
- G2 v2：[配对结果](../../artifacts/r10/r10_g2_evidence_state_neutral_ab_v2_20260913/g2_evidence_state_ab_result.md)及 B 的 `northstar_quality_certificate_QC-8827_correction_1.pdf`。
