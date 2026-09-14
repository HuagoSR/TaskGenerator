# LedgerOne source naturalness audit

> 结论：`source_model_not_supported`；2026-09-14。本文只做离线来源合理性审计，不创建或修改 A/B 输入，不授权 Solver、Grader 或外部模型。被审计方案是把 identity/authority 字段 join 到 `06_ledger_reserve_entry.csv`；原字段设计保留在 [materializability audit](approval_evidence_materializability_audit.md) 中作为已撤回历史。

## 1. 当前 source model 支持什么

候选可见的 [LedgerOne CSV](../../artifacts/r10/r10_rw_task_latest_two_20260911/input/batch_run_r10_latest_two/Task_audit_reliability_02/reference_files/06_ledger_reserve_entry.csv) 只含 journal query、两条会计分录、effective/posting dates、workflow approval timestamp 和 source document；没有 actor key、directory identity、authority configuration、limit、scope 或 effective-authority dates。[PBC source index](../../artifacts/r10/r10_rw_task_latest_two_20260911/input/batch_run_r10_latest_two/Task_audit_reliability_02/reference_files/11_pbc_source_index.md) 只称其为针对 `JE-0626-447` 的 native LedgerOne query。

隐藏 [world/process](../../artifacts/r10/r10_task_factory_quality_development_v1_20260910_v2/cases/r10_task_factory_quality_development_v1_20260910_v2_quality_audit_reliability_02/turns/03/draft/hidden/process.md) 可以作为工厂侧因果约束，但不能给候选增加证据。它只设定 Victor Alvarez 是 Assistant Controller、负责 review/approve reserve journals，并在 [manifest](../../artifacts/r10/r10_task_factory_quality_development_v1_20260910_v2/cases/r10_task_factory_quality_development_v1_20260910_v2_quality_audit_reliability_02/turns/03/draft/hidden/manifest.json) 中称 `06` 为 Noah Kim 生成的 direct LedgerOne journal-detail export，依赖 `JE-0626-447` 与 `RA-2026-0709` journal package；它没有定义 IAM directory、approval-authority configuration、稳定 user key、跨记录 join 或相关报表能力。原 [material check](../../artifacts/r10/r10_task_factory_quality_development_v1_20260910_v2/cases/r10_task_factory_quality_development_v1_20260910_v2_quality_audit_reliability_02/turns/03/draft/hidden/material_checks.json) 还将 `06` 的范围限定为 journal、balances 和 dates。现有 [diagnostic](../../artifacts/r10/r10_task_factory_quality_development_v1_20260910_v2/cases/r10_task_factory_quality_development_v1_20260910_v2_quality_audit_reliability_02/development_trials/09/diagnostic.json)／rubric 要求补取的是 “LedgerOne workflow log and user-role listing”／“workflow audit trail and authorization evidence”，即两个可追溯记录类别，而不是当前 journal-detail export 中已存在但未展示的字段。

因此，对 actor user key 只有抽象 workflow-event 需求，没有已定义字段或来源；对 identity directory、authority configuration、effective dates、limit 和 scope 均无当前 world/source 依据。不能据此声称 LedgerOne 可原生携带或 join 这些内容。

## 2. 职业上最自然的记录形态

在当前 source model 下，最自然的形态是：LedgerOne 的独立 workflow audit export 记录 approval event 与 actor account；另由受控 user-role／delegation or authority register 证明该 account 的人员身份、适用权限、限额和生效期间，并分别保留 producer、query scope、record ID 与 custody。只有 world 另行定义 LedgerOne 内置 authority configuration 及受控 join/report capability 后，system-generated joined report 才可能自然。直接把上述字段追加到现有 journal-detail native export 没有来源支持，不能仅因实验对称而采用。

## 3. A 状态值是否自然

`NO_RESPONSIVE_RECORD_INCLUDED` 不是现有 LedgerOne 文件、manifest 或 process 中定义的系统状态。把它放进 `06` 会暗示系统已经对 directory/authority store 执行了有界查询，并能权威说明响应范围；当前 world 没有这种查询、数据源或结果语义。它可以作为人为占位值被生成，但不是当前 source model 自然产生的业务记录，亦可能把实验条件直接显著化。

## 4. B 是否足以关闭局部缺口

单个 client-generated joined CSV 即使列出 Victor、role、scope、limit 和 dates，也不能只凭字段共现证明 identity mapping、authority record 的来源完整性或当时有效性；这会把管理层生成信息当作自我佐证。关闭局部缺口至少需要可追溯的 workflow event、稳定 account-to-person mapping、受控 authority record及其 event-date applicability，并保留各自来源和取得范围。当前 world 所指向的 workflow log 加 user-role/authorization listing 可以形成这种证据链，但现有 `06` 加字段不能替代它们。

## 5. 处置

当前单文件、同 schema 的 joined-export 物化方案撤回。它物理上可以制作，但在现有 world/source 中没有职业记录因果依据，因此不能以较弱结论继续使用。若以后要研究该 decision point，必须先用新的离线设计明确自然的多记录来源与 A/B 结构；该可能性不构成本轮 A/B、scope 或运行授权。
