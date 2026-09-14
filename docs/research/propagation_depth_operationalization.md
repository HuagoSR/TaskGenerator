# Propagation depth：离线操作化

> 状态：开发阶段、回顾性操作化；2026-09-14。仅重述既有 G1/W3 与 G2 结果，不修改原实验、创建新任务或授权模型运行。

## 变量定义

**传播深度**是：从候选可见的证据状态节点出发，Solver 沿预先指定的依赖链，保持语义正确且连续传播到的最远层级。

| Depth | 可观察状态 | 判定问题 |
| --- | --- | --- |
| 0 | 证据状态 | Solver 是否摄取了相关证据的存在、缺失及正式性？ |
| 1 | 直接事实更新 | 是否得到该证据直接支持的事实状态？ |
| 2 | 关系／属性／假设状态更新 | 是否把直接事实用于正确的实体—属性绑定，或正确改变分析假设的地位？ |
| 3 | 方法或要求满足状态更新 | 是否据此更新适用分析处理或职业要求的满足状态？ |
| 4 | 局部职业 disposition 更新 | 是否把更新落实为对应的 hold、处置或结论边界？ |

计数单位是**语义依赖边**，不是文件数、检索次数、工具调用数或推理文本长度。仅引用新证据算到 depth 0；不能据此推定更深层已经完成。`reached depth` 取从 depth 0 开始的最大连续正确前缀；即使更深处偶然出现正确表述，也不能跨过中间断裂计分。`first failure` 是此前各层均成立后，首个 `not observed` 或 `contradicted` 的层。无关状态是否保持不变继续记录为边界检查，但本轮不把它并入传播深度变量。

## G1/W3：证据充分性传播链

```text
D0  承运商比例计费证据：A 缺失；B 存在
 ↓
D1  记录是否建立 freight 随 kit 数量线性变化
 ↓
D2  12→18 缩放的地位：sensitivity assumption ↔ 有事实支持的处理
 ↓
D3  历史 freight normalization 的方法状态随之更新
 ↓
D4  F&R 结论保留或解除“线性缩放无事实依据”这一局部限制
```

| 条件 | 连续观察结果 | Reached depth | First failure |
| --- | --- | --- | --- |
| A | 正确识别无 carrier quote；把缩放标为 sensitivity assumption，并把该限制带入最终判断。 | 4 | 无（就该局部链而言） |
| B | 使用新增比例计费事实，把缩放改为有证据支持的确定处理，并只消除这一证据不足。 | 4 | 无（就该局部链而言） |

W3-A 的 IGCE 与历史订单算术错误不属于这条 freight evidence-update 链，故不改写其局部传播深度；它们仍使整体数值质量和最终效应比较受到混淆。

## G2：身份更正与属性重绑定传播链

```text
D0  正式批准的 QC correction：A 缺失；B 存在
 ↓
D1  sequence 12 serial：AP7-261148 → AP7-261184
 ↓
D2  sequence 12 的 power-on Pass / 698 CFM / overall Pass 重绑定到 AP7-261184
 ↓
D3  AP7-261184 的“交付序列号 ↔ factory test record”满足 PO §1.4
 ↓
D4  只解除 AP7-261184 的 §1.4 文件性 hold
```

| 条件 | 连续观察结果 | Reached depth | First failure |
| --- | --- | --- | --- |
| A | 正确识别批准更正缺失、供应商 transposition 解释不足，因而不作重绑定，判定 §1.4 尚未满足并保留 hold。 | 4 | 无（以 A 状态下应有的负向节点值计） |
| B | 摄取批准更正并正确更新 serial；未把同一 sequence 的测试属性重绑定给 `AP7-261184`。随后 §1.4 满足状态未更新，hold 被错误保留。 | 1 | **Depth 2：fact rebinding** |

G2-B 对 `AP7-261191`、receipt ≠ acceptance 与 COR 权限的正确保持说明没有明显全局污染，但这不增加 reached depth；本变量只回答目标链传播到了多远。

## 当前可用解释

按此定义，W3 的局部 A/B 均连续传播至 depth 4；G2-A 也完成与缺证状态一致的负向传播，而 G2-B 在读取新证据并完成直接身份事实更新后，仅达到 depth 1，首个断裂发生在 depth 2。因而“看见 correction”与“完成 evidence-conditioned disposition”被明确分开。

这只是对两个既有案例的可计数描述。它尚未证明传播深度本身导致失败，也没有建立跨模型、seed 或任务类型的稳定难度关系。

## 证据记录

- G1/W3：`w3_assumption_boundary.md`、`w3_diff_note.md`、`w3_ab_result.md`。
- G2 v2：[配对结果](../../artifacts/r10/r10_g2_evidence_state_neutral_ab_v2_20260913/g2_evidence_state_ab_result.md)。
