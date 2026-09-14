# Existing-world behavioral probe scouting

> 状态：`candidate_found_without_world_extension`；2026-09-14。本文只做离线 scouting，不创建 A/B 输入、preregistration、scope 或 receipt，不授权 Solver、Grader 或外部模型。候选来自已有有限支持的 `r10_agent_factory_batch_20260907_val_03`（Ardent Trail Equipment 收入截止审计）；其生成审查为 provisional/LLM-proxy，不能据此声称 production-level 质量。

## 候选 decision point

候选点是 Meridian saved view `REV_DEC_FULFILLED` 中 `fulfilled_at` 的当前系统语义。现有 [任务题干](../../artifacts/r10/r10_agent_factory_batch_20260907/cases/r10_agent_factory_batch_20260907_val_03/package/dataset_row.json) 要求审计 senior 判断该字段实际证明什么、哪些事项仍未解决，并为每个 open item 给出 resolution action 和 conditional effect。当前 [管理层 memo](../../artifacts/r10/r10_agent_factory_batch_20260907/cases/r10_agent_factory_batch_20260907_val_03/package/reference_files/02_management_cutoff_memo.docx) 只提供旧流程理解：`Fulfillment Date` 代表 carrier manifest close；它同时承认管理层尚未审阅 post-migration field mapping。正式的当前配置证据则能证明 `fulfilled_at` 在首次打印 pack slip 时写入、不会接收 HarborLink event。

未来概念条件应保持同一 state-neutral prompt 和相同共同材料。**A** 的 evidence set 不包含当前 saved-view definition/data-dictionary extract，因此管理层说法只能作为 representation，字段语义及取得正式配置证据的 follow-up 必须保持 unresolved。**B** 自然多取得一份由 Eli Barr / ERP Applications 从既有 Meridian production saved-view definition 和 data dictionary 提取的当前配置记录，直接说明字段来源、写入事件和无 HarborLink join；它只关闭字段语义识别及重复取证这一局部 gap。两侧底层系统语义、订单、金额、carrier events 和会计政策完全相同。

## 严格门槛核对

| 门槛 | 判定 | 依据与物化边界 |
| --- | --- | --- |
| 决策点天然存在 | **PASS** | [Hidden process](../../artifacts/r10/r10_agent_factory_batch_20260907/cases/r10_agent_factory_batch_20260907_val_03/turns/03/draft/hidden/process.md) 已定义 Eli 维护 saved view/data dictionary，并明确当前字段语义；[manifest](../../artifacts/r10/r10_agent_factory_batch_20260907/cases/r10_agent_factory_batch_20260907_val_03/turns/03/draft/hidden/manifest.json) 已把 current report definition、Meridian production data dictionary 和 saved-view definition 列为既有记录及 source dependency。无需新增系统、record owner、actor key、query class 或 custody model。 |
| Evidence-state change 必然影响可观察行为 | **PASS** | A 必须把字段语义及正式配置支持列为 unresolved，并请求当前 definition/mapping；B 应使用正式配置事实、删除这一取证 follow-up，并据此明确 saved view 不能自行证明 carrier possession。题干直接要求解释 field semantics、open items、resolution action 和 conditional effect，因此观察的是 evidence-state uptake，而不是是否复述内部推理链或使用特定 disposition 标签。 |
| 至少一个无标签歧义的共同控制 | **PASS** | 两侧共同的 HarborLink CSV 仍使 SO-5118 缺 first-possession event；[REV-04](../../artifacts/r10/r10_agent_factory_batch_20260907/cases/r10_agent_factory_batch_20260907_val_03/package/reference_files/01_revenue_recognition_policy.pdf) 明确要求 missing/delayed scan 必须取得 alternative contemporaneous support 后才能决定 accounting period。因此 SO-5118 必须保持 unresolved 并有匹配 follow-up，不依赖 `hold` 等研究者预设标签。Carrier-file provenance 与 SO-5119 contemporaneous corroboration 也保持共同限制。 |
| 可只改变 evidence state | **PASS，附冻结约束** | A 的真实状态是未取得该记录，不得制造空文件或“no record”占位；B 可自然多一份既有记录类别。文件数不同不是混淆。未来物化必须让共同文件逐字节相同、prompt 不点名缺失文件、配置证据位于短且可直接访问的单一记录中，并保持当前系统事实不变。 |

## 单一操纵与回退边界

现有 `05_report_configuration_and_migration.pdf` 同时包含 current field semantics 和 `MIG-2741` validation status。若直接让它只出现在 B，会同时操纵“字段语义是否有正式支持”和“migration validation gap 是否可见”，不够干净。未来物化只能使用 hidden source model 已定义的 **current saved-view definition/data-dictionary extract**，且不夹带 migration completion、reliance 或 cutoff disposition 结论；这不是新增 record class，而是从现有 source dependency 取其当前配置部分。若无法把该原生 current-definition record 与 migration-history evidence 职业上自然地分开，就撤回候选，不靠改 prompt、占位文件或答案提示补救。

因此该候选在不扩展 world/source model 的前提下满足 [behavioral measurement spec v1](behavioral_measurement_spec_v1.md)：主要观察为 unresolved state 与匹配 follow-up 的局部关闭；允许 memo/workpaper 使用不同职业表达。正确行为只能说明交付与 evidence-conditioned updating 一致，不能识别模型内部表示，也不构成跨任务验证结果。
