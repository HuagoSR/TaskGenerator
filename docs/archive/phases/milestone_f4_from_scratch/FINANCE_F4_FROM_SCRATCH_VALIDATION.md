# Finance F4 从零生产验证结论

> Lifecycle: `historical / completed / blocked`

## 结论

本轮按一次来源冻结、逐题生成、逐题人工式放行执行。公开 source collection 和 DeepSeek skill extraction 只运行一次，scratch registry 已冻结，canonical registry 未修改，服务器 current release 未切换。

Campaign 在第1题的两轮版本化尝试后按合同停止：

```text
decision = f4_from_scratch_validation_blocked
completed_slots = 0 / 8
blocked_slot = 1 / fan_in_reconciliation
source_collection_count = 1
external_solver_eval = false
external_grader_eval = false
```

## 两轮发现

`revision_01` 暴露编排错误：逐题 runner 未启用 `finance_semantic_contract_v2`，生成器退回通用 Evidence_Items/Control_Totals 模板。prompt 要求发票、收货、账簿截止日和确定性分类，但候选文件没有对应字段与规则；Luna 判定不可解，Terra要求替换全部核心材料。旧 verifier 仍为 pass。

系统修复后，`revision_02` 使用 generator-owned finance contract，候选数据已足以独立算出：10个精确匹配、2个 bank-only、2个 ledger-only，双方期间活动均为 `-3170.30`。但交付合同要求使用不存在的 `reconciliation_template.xlsx`，clause map 与 teacher/rubric 仍有跨模板或 locator 不一致。Luna因此仍判定不可完成。

Terra 能提出合理的完整替换包，但当前生产架构只能保存 revision proposal，不能通用地物化 XLSX/DOCX、重新构建 truth/rubric 并验证修改后的任务。把建议 JSON 当作已修任务会形成虚假通过，因此第二轮后按上限阻塞。

## 架构判断

F4 的整体模型审查对发现全局问题有效；逐题 checkpoint 也成功阻止了坏题扩散。当前缺口不是再增加 finding code，而是建立受治理的 whole-task revision materializer：将模型的整体修订转换为 schema/data/prompt/teacher/rubric 的版本化变更，再由确定性重算和 candidate-blind solve 验证。

`evidence_to_deliverable` 两个实验槽位没有启动，不能据此形成新结论或改变 Phase 16 决策。

