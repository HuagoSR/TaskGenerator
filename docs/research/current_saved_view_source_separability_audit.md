# Current saved-view source separability audit

> 结论：`cleanly_separable_and_materializable`；2026-09-14。本文只审计 Ardent Trail Equipment `REV_DEC_FULFILLED` 的 hidden source model，不创建或拆分候选文件，不创建 A/B、preregistration、scope 或 receipt，不授权 Solver、Grader 或外部模型。

## 1. 记录类别是否已经存在

是。[Hidden process](../../artifacts/r10/r10_agent_factory_batch_20260907/cases/r10_agent_factory_batch_20260907_val_03/turns/03/draft/hidden/process.md) 已分别定义 Eli Barr 维护 Meridian saved view、production data dictionary 和 revenue-interface mapping；其 2026-01-09 chronology 明确写为 Eli “attached the current definition and MIG-2741”，而非把二者定义为不可分的单一系统记录。[Manifest](../../artifacts/r10/r10_agent_factory_batch_20260907/cases/r10_agent_factory_batch_20260907_val_03/turns/03/draft/hidden/manifest.json) 虽将候选交付包装成一个 `05_report_configuration_and_migration.pdf`，但把 `Meridian production data dictionary`、`saved-view definition` 和 `migration ticket MIG-2741` 列为三个独立 source dependencies。实际 [05 文件](../../artifacts/r10/r10_agent_factory_batch_20260907/cases/r10_agent_factory_batch_20260907_val_03/package/reference_files/05_report_configuration_and_migration.pdf) 也将 “Current saved-view definition / Current field semantics” 与 “Migration ticket MIG-2741” 分成独立内容区，并为 current definition 给出单独 extract time。

因此，**current saved-view definition / data-dictionary extract 是现有记录类别的自然实例**；候选 PDF 是一次合并呈现，不是要求这些底层记录永远合并的 source ontology。未来不得通过裁页或删除 `05` 的 migration 段落来伪装原生记录，而应从 hidden model 已定义的 current definition/data dictionary 生成一份独立 native-style extract。

## 2. Producer、时间、query scope 与 custody

| 项目 | 现有 source model 支持的定义 |
| --- | --- |
| System / producer | Meridian Cloud production saved-view definition 与 production data dictionary；由既有 record owner **Eli Barr, ERP Applications Administrator** 提取。无需新增系统、owner 或 actor identity。 |
| Record time | 使用现有事实：current definition extracted **2026-01-09 09:42 America/Chicago**；它是 extract time，不是字段配置的生效日，也不替代 MIG-2741 history。 |
| Query scope | 精确限定为 saved view `REV_DEC_FULFILLED` 的当前 column mapping、row filter、external joins，以及 `sales_order.fulfilled_at` 的 current field definition/write trigger。不得查询 ticket status、validation attachment、accounting approval 或 operating results。 |
| Custody | 沿用现有因果链：Eli 为 audit inquiry AV-2025-REV-07 准备 system excerpt，并在 2026-01-09 11:05 的回复中向 audit senior 发送 current definition。记录本身保留 record owner、environment、saved-view ID、extract time 和 inquiry ID；现有 world 没有独立 PBC receipt、native-mail-header inspection 或 file-hash custody，因此不得补称这些控制已存在。该限制不妨碍记录证明 declared configuration，但仍限制更强的 authenticity/operating-effectiveness 主张。 |

## 3. 可证明内容与隔离边界

纯 current-definition extract 可以且只应证明：`Fulfillment Date / Time` 映射自 `sales_order.fulfilled_at`；该字段在首次打印 pack slip 时写入；saved view 的 external joins 为 none，HarborLink data 不被查询。它还可列出当前 row filter，以使字段和查询对象可定位，但不应出现 reliance 或 cutoff disposition 结论。

这些 current-state 字段不需要、也不会自行证明 post-migration validation 是否完成。Validation attachment、Accounting sign-off、ticket status 和 follow-up completion 属于独立的 MIG-2741 history/evidence state；未把 ticket 放入 extract 只表示本次 query 不涵盖该记录，不能被解释为 validation 已完成、未完成或不存在。该 extract 同样只证明 declared design，不证明每行 operating effectiveness、report completeness、carrier-file provenance 或任何订单的正确 accounting period。

## 4. 物化门与撤回条件

未来 B 可以自然多取得上述 current-definition extract，A 则真实地未取得该记录；不需要空白占位文件，也不要求两侧文件数相同。共同 prompt 必须保持 state-neutral，且共同材料不得从其他位置重复泄露完整 current semantics。A 应保留字段语义和取得正式配置记录的 follow-up；B 应关闭这一局部取证 gap，同时继续保留 carrier provenance、SO-5118 missing event、SO-5119 corroboration 等共同限制。

本结论只在 builder 能按上述既有 producer、query scope 和 metadata 生成独立 current-definition record 时成立。如果实际做法只能裁剪旧 PDF、改写 MIG-2741、虚构更强 custody，或让 current extract 携带 validation status，则应撤回候选；不得为了实验单一性硬拆现有 `05`。该边界与 [existing-world scouting](existing_world_behavioral_probe_scouting.md) 和 [behavioral measurement spec v1](behavioral_measurement_spec_v1.md) 一致。
