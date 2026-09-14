# Natural multi-record approval evidence design

> 结论：`requires_world_extension`；2026-09-14。本文只设计 `JE-0626-447` 的自然多记录证据链，不创建候选文件、A/B、preregistration、scope 或 receipt，不授权 Solver、Grader 或外部模型。现有 [source naturalness audit](ledgerone_source_naturalness_audit.md) 已撤回向 journal-detail CSV 追加 joined fields 的方案。

当前 [process](../../artifacts/r10/r10_task_factory_quality_development_v1_20260910_v2/cases/r10_task_factory_quality_development_v1_20260910_v2_quality_audit_reliability_02/turns/03/draft/hidden/process.md) 只定义 Victor Alvarez 是 Assistant Controller、实际 review/approve reserve journals；现有 [LedgerOne detail](../../artifacts/r10/r10_rw_task_latest_two_20260911/input/batch_run_r10_latest_two/Task_audit_reliability_02/reference_files/06_ledger_reserve_entry.csv) 只显示两条分录与 approval timestamp。下列 system capability、record class、producer、ID 和 custody 均是 **proposed world extension**，不得写成原 world 已有事实。

## 两类正式记录

| 记录 | 最小字段与查询 | Producer、record time 与 custody |
| --- | --- | --- |
| **LedgerOne workflow audit trail export** | `Export_ID`、`Export_Run_UTC`、`Query_Journal_ID`、`Workflow_Instance_ID`、`Event_ID`、`Event_UTC`、`Event_Type`、`Prior_Status`、`New_Status`、`Actor_User_ID`、`System_Of_Record`。Query 固定为 `JE-0626-447` 的完整 workflow history，不按 actor 或 event type 预筛；建议 proposed IDs 为 export `L1-WF-EX-20260715-0447`、instance `L1-WF-JE0626447`、approval event `L1-WFE-20260709-120219`、actor `L1U-VA2047`。 | LedgerOne 原生生成；由新增的 Financial Systems/LedgerOne Administrator 导出并声明 query scope。Journal effective date 仍为 `2026-06-30`，approval evidence 的相关时间是 `2026-07-09T12:02:19Z`，workflow record 不另造 policy effective date。Producer 于 `2026-07-15` 交付，Serena Patel 记录 PBC receipt ID、received UTC、原始文件 hash 与未变更 custody。 |
| **Finance approval-authority register extract** | `Extract_ID`、`Extract_Run_UTC`、`Query_Actor_User_ID`、`Query_As_Of_UTC`、`Authority_Record_ID`、`Actor_User_ID`、`Employee_ID`、`Display_Name`、`Role`、`Authority_Action_Scope`、`Authority_Limit_USD`、`Effective_From`、`Effective_To`、`Record_Status`、`Record_Owner`。Query 用 `L1U-VA2047` 与 approval event UTC，返回覆盖该时点的 active row 及相邻历史 row，不用姓名搜索；建议 proposed IDs 为 extract `FIN-AUTH-EX-20260715-VA2047`、record `FIN-AUTH-VA2047-2026-01`。 | 由新增的 Finance Controls Authority Register 原生生成、Finance Controls record owner 导出。记录必须是 journal approval authority 的正式来源，不是普通 employee directory；它将 actor key 映射到 Victor，并显示适用于 manual warranty-reserve journals、限额不低于 `$221,750`、有效期间覆盖 approval event。Producer 与 PBC 分别记录 export/receipt UTC、query scope、record ID、hash 和 custody。 |

## A/B evidence state

**A：**只取得上述完整 workflow audit trail。它可确认同一 approval event、event time、status transition 和 actor account，但候选 evidence set 中没有 authority-register extract，因而不能把 `L1U-VA2047` 正式映射到 Victor，也不能证明该 account 在事件日具有适用 scope/limit。Identity/authority 必须保持 unresolved，并请求 Finance Controls 的 effective-dated authority record。A 不创建空白 authority 文件、零行查询、`NO_RESPONSIVE_RECORD_INCLUDED`、虚假“无记录”状态或替代性占位说明；未取得就是实际未进入 evidence set。

**B：**保留与 A 逐字相同的 workflow audit trail，并新增正式 authority-register extract。`Actor_User_ID` 精确匹配、employee identity 明确、effective period 覆盖事件日、scope 覆盖 warranty-reserve journal、limit 覆盖 `$221,750` 且 status active 时，足以关闭**该局部** identity/authority evidence gap 及对应 follow-up，无需再用额外 HR 文件证明同一事项。它仍不证明 journal appropriateness、LedgerOne control effectiveness、reserve calculation 或总体 evidence reliability；[管理层 note](../../artifacts/r10/r10_rw_task_latest_two_20260911/input/batch_run_r10_latest_two/Task_audit_reliability_02/reference_files/04_reserve_summary_note.md) 在两侧只能作为共同线索，不能替代上述正式记录。

## World extension 与撤回边界

物化前必须显式扩展 hidden world/source model：增加 LedgerOne workflow event store 与稳定 actor ID；增加 effective-dated Finance approval-authority register；增加两个 record owners、原生 export/query semantics、PBC supplemental receipt/custody flow，并把 supplied-record cutoff 从 `2026-07-14` 延至能容纳上述取得过程的日期。所有 extension 必须先于候选 materialization 冻结。

自然 A 与 B 的文件数会不同，因为 B 真正多取得一类正式记录。不得用占位文件伪造结构对称；若未来 probe 又要求完全相同文件数量且找不到真实业务流程产生的对称记录，应撤回该 decision point。当前设计仅说明自然证据生成链可以在扩展 world 后成立，不表示旧 world 已支持、输入已物化或行为实验已获授权。
