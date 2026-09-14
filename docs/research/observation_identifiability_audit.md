# G2 observation identifiability audit

> 状态：2026-09-14 回顾性离线审计。仅限定既有 G2 access-matched v2 结果的解释力；不修改冻结 preregistration、原结果或 receipt，不授权新实验。

## 判定标准

- `required_observable`：题干或职业交付完整性要求该状态直接出现在最终交付中；缺失本身可以判交付不足。
- `behaviorally_observable`：中间状态不必写出，但在合格交付中必然改变 unresolved issue、follow-up 或局部 disposition；应从这种下游差异判断。
- `latent_not_identifiable`：合格交付可以省略该中间状态，且同一可观察结果可能由不同内部路径产生；“未写出”不能证明模型未完成更新。

[候选题干](../../artifacts/r10/r10_g2_canonical_vs_rebinding_access_matched_v2_20260914/inputs/canonical/Task_g2_access_matched_v2_canonical/dataset_row.json)要求识别有证据支持的未决 documentation／inspection／acceptance 问题，按 CLIN 给出 recommendation，并区分 receipt、recommendation 与 CO acceptance authority；但只规定 DOCX/XLSX 文件名，没有要求 serial-level evidence matrix、resolved-issue ledger、完整四元组或推理链。因此 `evidence_reconciliation.xlsx` 这个名称本身不能增加未写明的字段义务。

## 冻结观察点的可识别性

| 被测状态 | 分类 | 理由与本次可见结果 |
| --- | --- | --- |
| Current binding 的完整 `AP7-261184 / Pass / 698 CFM / Pass` 四元组 | `latent_not_identifiable` | 职业 memo 可以引用 QC-8827 的 current controlled entries，并直接形成处置，而不逐项抄录全部测试字段。两侧未外化四元组，不能单独判定内部 relation 未建立。 |
| `AP7-261148` 已 superseded，测试属性已重绑定到 `AP7-261184` | `latent_not_identifiable` | 题干要求披露仍未解决的问题，不要求复述已经解决的 record history。Rebinding 未写 correction 链，既可能是未维护关系，也可能是已吸收后省略。 |
| 是否继续把 `AP7-261184` 当作 unresolved documentary mismatch | `behaviorally_observable` | 若仍未解决，题干要求将其列为未决 documentation issue 并形成 follow-up／hold；若交付作出 closed-set 表述，则可以观察其是否仍在集合内。Rebinding 明确写 “hold … for `AP7-261191` only”，没有继续列旧 mismatch；Canonical 称 `AP7-261191` 为 “the only identified exception”。[逐项提取证据](../../artifacts/r10/r10_g2_canonical_vs_rebinding_access_matched_v2_20260914/qa/deliverable_text/rebinding_deliverables.txt)与[Canonical 对照](../../artifacts/r10/r10_g2_canonical_vs_rebinding_access_matched_v2_20260914/qa/deliverable_text/canonical_deliverables.txt)。 |
| `AP7-261184` 的局部 §1.4 文件性 hold 是否解除 | `behaviorally_observable` | 不必直接写 “§1.4 satisfied”，但该状态应改变 exception／hold／follow-up。两侧都没有为 `AP7-261184` 保留局部 hold，并把实际 hold 限于 `AP7-261191`。 |
| `AP7-261191` physical issue；receipt ≠ acceptance；COR authority | `required_observable` | 这些分别是记录中仍影响处置的未决实体问题，以及题干明确要求保持的 acceptance 与权限边界；两侧均予以保留。 |

可观察性具有不对称性：若 mismatch 仍然未决，合格交付必须披露；若已经解决，合格交付不必重放完整更正链。单纯“没有提到 `AP7-261184`”仍可能是遗漏，只有 “唯一 exception／only hold” 这类 closed-set 表述，结合交付对未决问题的完整性责任，才较强地支持“它未被继续保留”。

## 审计结论

[Canonical access audit](../../artifacts/r10/r10_g2_canonical_vs_rebinding_access_matched_v2_20260914/access_audit_canonical.json)与[Rebinding access audit](../../artifacts/r10/r10_g2_canonical_vs_rebinding_access_matched_v2_20260914/access_audit_rebinding.json)均确认完整 Current binding 进入模型侧 ToolMessage，故上一版的证据获取解释已被排除。两侧又都达到正确的可观察局部处置：旧 mismatch 未继续出现，只对 `AP7-261191` 保留 hold，并保持 receipt／authority 边界。

因此，[冻结结果](../../artifacts/r10/r10_g2_canonical_vs_rebinding_access_matched_v2_20260914/g2_canonical_vs_rebinding_access_matched_v2_result.md)中的原始 `category_4` 判定必须保留，但不应进一步解释为模型没有完成 rebinding。更准确的研究描述是：**本实验对完整内部 rebinding 路径缺乏 measurement identifiability；现有交付物只能支持“两侧均得到正确的下游局部 disposition”，不能区分它们是否以不同内部路径维护了完整 relation。** 若为了可见而强制逐项抄录四元组，测量将混入报告详尽程度，而不再单独指向 relational updating 能力。
