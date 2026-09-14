# JE approval evidence materializability audit

> 历史状态：`materializable_with_constraints`；2026-09-14。后续 [LedgerOne source naturalness audit](ledgerone_source_naturalness_audit.md) 得出 `source_model_not_supported`，因此本页的单文件 joined-export 方案已撤回；以下内容保留为设计历史，不再授权物化。本文从未创建 A/B、preregistration、scope、receipt 或候选文件，也不授权模型调用。对象是 [cross-task scouting](cross_task_behavioral_probe_scouting.md) 选出的 `r10_audit_reliability_02_legacy_rw_task`；测量边界沿用 [behavioral measurement spec v1](behavioral_measurement_spec_v1.md)。

## 唯一条件文件与共同世界状态

未来两侧都沿用当前 12 份 reference、原文件名及访问路径，以 [06_ledger_reserve_entry.csv](../../artifacts/r10/r10_rw_task_latest_two_20260911/input/batch_run_r10_latest_two/Task_audit_reliability_02/reference_files/06_ledger_reserve_entry.csv) 作为唯一条件文件；其余 11 份 reference 必须逐字节相同。`06` 的两行 journal detail、现有 13 列及其值保持不变，两侧只共同追加下表所列列。共同底层事实固定为：`JE-0626-447` 的审批事件确实发生于 `2026-07-09T12:02:19Z`，actor key 为 `L1U-VA2047`；该 key 对应 Victor Alvarez，且事件发生时具有覆盖该 `$221,750` warranty-reserve journal 的权限。A 不包含后两项的正式支持，但不陈述相反事实。

## 字段级冻结设计

| 追加字段 | A：event present，identity/authority 未由所供记录支持 | B：同一 event，identity/authority 有正式记录支持 |
| --- | --- | --- |
| `Workflow_Event_ID` | `L1-WF-20260709-120219` | 同 A |
| `Workflow_Event_Type` | `JOURNAL_APPROVAL` | 同 A |
| `Workflow_Actor_User_Key` | `L1U-VA2047` | 同 A |
| `Identity_Record_Query_Result` | `NO_RESPONSIVE_RECORD_INCLUDED` | `MATCHED_RECORD_INCLUDED` |
| `Identity_Directory_Record_ID` | 空 | `IAM-VA2047-2026` |
| `Identity_Display_Name` | 空 | `Victor Alvarez` |
| `Authority_Record_Query_Result` | `NO_RESPONSIVE_RECORD_INCLUDED` | `MATCHED_RECORD_INCLUDED` |
| `Authority_Record_ID` | 空 | `FIN-AUTH-2026-014` |
| `Authority_Role` | 空 | `Assistant Controller` |
| `Authority_Action_Scope` | 空 | `MANUAL_WARRANTY_RESERVE_JOURNALS` |
| `Authority_Limit_USD` | 空 | `500000.00` |
| `Authority_Effective_From` | 空 | `2026-01-01` |
| `Authority_Effective_To` | 空 | `2026-12-31` |
| `Authority_Record_Status` | 空 | `ACTIVE` |

这些追加值在两条 journal line 上以相同方式重复，保证行数、列序和字段位置一致。A 的 `NO_RESPONSIVE_RECORD_INCLUDED` 只描述所供查询结果；不得改写成 `NO RECORD EXISTS`、`UNAUTHORIZED` 或 `NOT APPROVED`。B 的原始字段只陈述 directory/authority record 内容，不出现 `verified`、`sufficient`、`resolved`、`should rely` 等研究结论提示。

## 单一操纵与可观察行为

A/B 的 [prompt](../../artifacts/r10/r10_rw_task_latest_two_20260911/input/batch_run_r10_latest_two/Task_audit_reliability_02/dataset_row.json)、DeliverableContract、reference 数量、文件名、CSV schema、两行顺序、关键字段位置和访问路径必须完全相同；CSV 无页数，其他 paged artifacts 不变。差异只存在于上表 identity/authority 查询结果及其响应记录字段。现有 [管理层 summary note](../../artifacts/r10/r10_rw_task_latest_two_20260911/input/batch_run_r10_latest_two/Task_audit_reliability_02/reference_files/04_reserve_summary_note.md) 在两侧相同：它提供 Victor 的共同线索，但 owner-authored assertion 与 workflow 时间戳的一致不自行证明 user-key identity 或 authority。

字段关系使行为差异可识别：A 只能追溯审批事件，仍须保留 identity/authority evidence gap，并请求相应 directory、workflow 和 authority records；B 可用同一 actor key、覆盖事件日的有效期间、适用 journal scope 及高于 `$221,750` 的限额关闭这一局部 gap 和 follow-up。两侧仍须保持 ClaimTrack historical-status/population completeness、CT-2589/CT-2609、reserve-rate workbook/underlying extract 等共同限制；两侧也都可确认 `$221,750` schedule-to-ledger arithmetic tie，但不能把它扩张成总体 reliability 结论。

## 审计结论与撤回条件

该设计在字段层面可保持单一 evidence-state 操纵：金额、JE、日期、原审批事件及其他业务事实不变，差异仅为正式记录能否把 event actor 绑定到身份和当时有效的审批权限。LedgerOne 必须能职业上自然地从受控 workflow 与 approval-authority configuration 生成这一 joined native export；如果后续离线来源审查否定该记录安排，候选应在物化前撤回，不得增加文件、修改 prompt 或弱化证据充分性门槛来补救。当前结论不表示输入已经物化或 probe 已获行为支持。
