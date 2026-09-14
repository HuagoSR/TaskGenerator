# Evidence-update dependency graph：G1/W3 与 G2 的统一抽象

> 状态：开发阶段研究抽象；2026-09-14。它整理已有单案例观察，不是已验证理论、难度量表或后续实验授权。

## 最小统一结构

职业任务中的证据更新不只是“发现一条新信息”，而是对一个有方向、有边界的依赖图做局部状态更新：

```text
候选可见证据状态 E
        │  provenance / sufficiency
        ▼
事实与关系状态 F
（事实成立性、epistemic status、实体—属性绑定）
        │  supports / binds / conditions
        ▼
分析方法或适用要求 M/R
        │  satisfies / constrains
        ▼
局部职业判断 D
（处理方式、hold/disposition、结论边界）

并行约束：不属于上述更新后代的事实、要求和判断应保持不变。
```

一次正确的 evidence-conditioned update 至少同时满足四点：摄取证据及其正式性；更新证据直接支持的事实或关系；沿依赖边传播到受影响的要求和局部判断；保持非后代节点不变。由此可区分三类错误：**校准错误**（事实与假设的地位判错）、**传播错误**（证据已读到但下游节点未更新）和**污染错误**（无关判断被一并放宽或收紧）。

## 两个已观察子图

| 案例 | 最小更新链 | 已观察结果 | 首要边界 |
| --- | --- | --- | --- |
| G1/W3 | `freight evidence status → linear-scaling assumption status → normalization treatment → F&R conclusion boundary` | A 在无承运商依据时把按数量缩放保留为 sensitivity assumption；B 在新增正式比例计费事实后，将同一处理改为有事实支持的确定处理。局部 manipulation check 得到支持。 | A 的两处无关算术错误污染后续数值，不能由该对干净估计新增证据对整体数值质量或最终结论强度的净影响。 |
| G2 v2 | `approved identity correction → sequence-12 attribute rebinding → PO §1.4 satisfaction → AP7-261184 local disposition` | B 摄取并引用了 `AP7-261148 → AP7-261184` 的批准更正，却没有把同一 sequence 的 `power-on Pass / 698 CFM / overall Pass` 重绑定给 `AP7-261184`，因而错误保留其文件性 hold。首个断裂点是 **fact rebinding**。 | B 同时正确保留 `AP7-261191` 损坏、receipt ≠ acceptance、COR 权限等无关限制；因此这是局部传播失败，不是整体状态混乱，也不是未读到 correction。 |

## 当前候选机制

两类任务可以统一为 **relational evidence updating**：模型必须维护 `evidence → fact/relation → method/requirement → decision` 的依赖图；证据变化后，既要改变全部且仅有受支持的后代节点，也要保留证据来源、充分性和假设性质。W3 主要暴露“证据充分性改变假设地位”，G2 进一步暴露“实体身份变化要求关联属性重绑定，再触发要求满足与局部 disposition 更新”。

据此，职业任务的候选难度来源不是材料数量或跨文件距离本身，而可能是：更新边的类型是否涉及关系重绑定、需要传播的深度，以及在更新受影响节点时维持无关状态不变的选择性。现有证据只支持把这些作为可操作的开发假设：W3 给出局部正向观察，G2 给出单案例端到端负向观察；尚未证明它们可跨模型、seed 或工作类型稳定复现，也未证明图结构复杂度能够预测任务难度。

当前核心问题可压缩为：在控制表面材料量后，**关系重绑定、传播深度与局部更新选择性**是否会系统性改变正确职业判断的成功率？

## 证据记录

- G1/W3：`w3_assumption_boundary.md`、`w3_diff_note.md`、`w3_ab_result.md`。
- G2 v2：[配对结果](../../artifacts/r10/r10_g2_evidence_state_neutral_ab_v2_20260913/g2_evidence_state_ab_result.md)；[日志截断代码路径核查](../../artifacts/r10/r10_g2_evidence_state_neutral_ab_v2_20260913/stirrup_truncation_path_audit.md)。
