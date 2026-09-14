# G2 negative-control validity audit

> 状态：2026-09-14 回顾性离线审计；结论为 `ambiguous_control`。本文只限定既有 G2 behaviorally-identifiable rebinding v1 的测量解释，不修改冻结 preregistration、结果、receipt 或候选输入，也不授权新实验。

## 判定标准与候选可见依据

- `valid_control`：材料与交付职责共同锁定唯一可观察处置。
- `ambiguous_control`：必须披露的事实或限制明确，但材料允许不止一种职业上可辩护的处置表达。
- `invalid_control`：冻结期待超出材料或交付职责能够支持的范围。

[PO CREL-26-P-0183](../../artifacts/r10/r10_g2_behaviorally_identifiable_rebinding_v1_20260914/inputs/canonical/Task_g2_behaviorally_identifiable_rebinding_v1_canonical/reference_files/purchase_order_CREL-26-P-0183.pdf) §1.4 要求供应商在 tender 时提交签署证书和逐台 schedule，把每个交付 serial 绑定到 factory power-on、airflow check 及 measured airflow；完整候选 QC 集没有 `AP7-261190`。因此，`190` 的 mandatory documentation requirement 未满足是明确事实。§2.5 又要求 COR 报告 missing support，[COR designation](../../artifacts/r10/r10_g2_behaviorally_identifiable_rebinding_v1_20260914/inputs/canonical/Task_g2_behaviorally_identifiable_rebinding_v1_canonical/reference_files/cor_designation_priya_shah.pdf)禁止 COR 接受、豁免要求或指示供应商行动。一个合格交付必须把缺件、未解决状态以及取得 QC 或获得 CO 书面处置等 follow-up 保持可见。

## 四项核查

| 问题 | 核查结果 |
| --- | --- |
| §1.4 是否唯一支持 documentation hold？ | 它足以证明缺件和未满足的提交义务，却没有规定该状态必须使用 `hold` 标签，也没有给出唯一 disposition。 |
| “CO acceptance consideration” 能否与 deficiency 并存？ | 可以，但前提是交付同时保留缺件与限制，且没有把 referral／consideration 写成 COR acceptance 或事实上的 waiver。作为职业背景，[FAR 46.501](https://www.acquisition.gov/far/46.501)说明完成质量保证前通常不应验收；[FAR 46.407](https://www.acquisition.gov/far/46.407)又允许 CO 在取得所需书面依据后考虑接受或条件接受不完整／不符合项。这些规则强化权限和记录边界，并未把本题唯一答案改写为一个固定标签。 |
| Prompt 是否规定 mandatory gap → hold？ | [共同题干](../../artifacts/r10/r10_g2_behaviorally_identifiable_rebinding_v1_20260914/inputs/canonical/Task_g2_behaviorally_identifiable_rebinding_v1_canonical/dataset_row.json)要求识别 documentation issue；证据不足时说明 unresolved state 和所需证据／授权方向，并允许选择 acceptance consideration、hold 或 documented follow-up。它没有规定缺少 mandatory document 必须映射为 hold。 |
| `190` 是否构成唯一、自然的硬阴性控制？ | “必须识别缺少 serial-specific QC 并保持具体 follow-up”是唯一且可观察的；“必须保留 documentation hold”不是。冻结观察把两者捆绑为一个硬判据，因而整体属于 `ambiguous_control`。 |

## 对首次配对结果的解释限制

[Canonical 交付](../../artifacts/r10/r10_g2_behaviorally_identifiable_rebinding_v1_20260914/qa/deliverable_text/canonical_deliverables.txt)明确指出 `190` 没有 supplier QC record，却仍写入 CO acceptance consideration。仅凭后一句不能再推出共同 requirement-application failure，因为它可被理解为保留缺口后的 CO referral；其 follow-up 是否足够具体可以记录，但本审计不新增评分或重判原结果。[Rebinding 交付](../../artifacts/r10/r10_g2_behaviorally_identifiable_rebinding_v1_20260914/qa/deliverable_text/rebinding_deliverables.txt)则把 `190` 写成 “No unresolved issue”，这是更直接的 missing-support uptake failure，但单侧行为仍不能证明 rebinding 更难。QC-8895 对独立 QC-8894 的 pollution／spillover 继续作为既有独立观察保留，不用于证明该 negative control 的效度。

因此，[原始结果](../../artifacts/r10/r10_g2_behaviorally_identifiable_rebinding_v1_20260914/g2_behaviorally_identifiable_rebinding_v1_result.md)及冻结记录保持不变；更准确的回顾性结论是：**`190` 的证据缺口有效，但以特定 `documentation hold` 作为唯一成功表现缺乏 measurement identifiability。当前 negative control 整体为 `ambiguous_control`，不能据此把两侧结果直接定性为共同 disposition failure。**
