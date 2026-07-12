# Milestone F4：整体任务总编辑与汇报收口

> 状态：`historical / authoritative for Milestone F4 closure`
> 结论：`holistic_editorial_review_completed`

## 一、为什么开展本轮工作

30题四模型评测显示较强模型总体优于弱模型，但得分普遍偏低。对固定8题的人工式抽查进一步发现：旧流水线的结构门禁可以保证文件存在、格式正确和流程可运行，却不能保证整道任务在语义上完整。银行对账缺少可支持“调整后余额”的数据，三单匹配缺少明确处置规则，费用政策缺少人均判断所需人数；8份 rubric 也没有独立事实核验。

F2/F3 尝试把问题拆成 semantic contract、finding code 和局部复审，但外部模型在多 requirement 输出和局部上下文中仍不稳定。因此本轮不再扩展细粒度门禁，而采用：

```text
Terra 整体总编辑
→ 版本化重建候选材料与 teacher truth
→ 程序独立重算
→ Luna 候选盲解
→ 确定性裁决与视觉验收
```

LLM负责理解和整体编辑，程序负责数值真值、隔离、版本、成本和发布门禁。

## 二、范围与执行合同

固定任务为 `#2 / #6 / #13 / #18 / #31 / #35 / #38 / #47`，覆盖2个银行对账、3个三单匹配和3个费用政策任务。原任务、teacher、solver 和 grader 证据保持只读；本轮只建立 `revision_01/02`。

模型和费用：

| 角色 | 模型 | 调用范围 |
| --- | --- | --- |
| 总编辑 | Tuzi `gpt-5.6-terra` | 完整 candidate、teacher、rubric 与既有诊断 |
| 独立候选 | Tuzi `gpt-5.6-luna` | 仅修订后的 candidate-visible prompt 与文件 |

只使用个人 `OPENAI_API_KEY_BACKUP`。预算上限为 ¥50，请求上限40次，不使用 Sol、DeepSeek、primary key、solver 或 grader。

## 三、修改内容

### 银行对账

- 删除无输入支持的 adjusted account balance 要求。
- 明确只报告候选材料中可重算的期间活动、匹配项和未匹配项。
- 禁止根据 activity 合计虚构期初、期末或调整后余额。

### 三单匹配

- 明确 `Received_Qty - Ordered_Qty`、`Invoiced_Qty - Received_Qty` 和 invoice/PO unit-price variance。
- 重复业务键固定为 `PO_ID + Item_ID + Invoiced_Qty + Unit_Price`。
- Luna 在 revision_01 中发现“重复组所有成员是否都 Hold”仍不够明确；revision_02 明确所有重复组成员均为潜在重复并进入 Hold。
- 状态优先级为 missing PO/receipt → investigate；否则 duplicate/variance → hold；否则 clear。

### 费用政策

- 使用新增候选文件 `attendee_counts.xlsx` 提供每笔交易的就餐人数。
- 明确每笔异常只计数一次，异常金额取完整交易金额。
- 人均餐费由候选数据确定性计算，不再把总额直接当作人均额。

### Rubric

- 每题统一为70%业务事实、25%交付与可追溯性、5%表达。
- 删除银行、三单、费用模板之间的跨领域技能残留。
- teacher truth、GoldenRun 和 annotation 均由候选材料重新计算。

## 四、最终证据

| 指标 | 结果 |
| --- | ---: |
| 版本化修订 | 8 / 8 |
| 整体编辑完成 | 8 / 8 |
| 确定性重算通过 | 8 / 8 |
| candidate/teacher 隔离 | 8 / 8 |
| fact-centered rubric | 8 / 8 |
| Luna 判断可独立完成 | 8 / 8 |
| Luna关键结果与重算一致 | 8 / 8 |
| 未解决重大歧义 | 0 / 8 |
| 原始证据哈希变化 | 0 |
| DOCX/XLSX视觉产物检查 | 11 |
| Tuzi请求 | 26 |
| 冻结价成本 | ¥0.975777 |

通过分布：银行对账 `2/2`、三单匹配 `3/3`、费用政策 `3/3`。最终判断为：

```text
holistic_editorial_review_completed
```

程序比较没有把 Luna 的自然语言字段名机械当作错误：结果先归一化，再使用明细行重算。例如 #31 的 Luna summary 把总行数写成12，但其11条逐行结果与候选文件一致；程序以逐行状态重新统计为 `7 clear / 4 hold / 0 investigate`，将 summary 算术误差归因为 solver 表述错误，而不是任务歧义。

## 五、#18 完整生命周期

原任务要求应用“每人100”餐费阈值，但交易表没有人数。旧 teacher 把交易总额直接当人均额，模型即使遵循 teacher 也不能证明结论由候选材料支持。

修订后：

1. Terra 从完整任务视角确认缺少人数是核心 blocker。
2. `revision_01` 增加候选可见 `attendee_counts.xlsx`，保留原交易表和业务主题。
3. 程序逐笔计算 `Amount / Attendee_Count`，并重建 teacher truth 和70%事实型 rubric。
4. Luna只看候选材料，独立识别4笔异常、异常总额 `1747.20`。
5. Luna结果与确定性重算完全一致，未依赖 teacher-only 文件。
6. XLSX和政策DOCX均完成视觉检查。

该案例证明本轮不是“让第二个模型同意第一个模型”，而是让编辑、独立解题和程序真值形成三方约束。

## 六、可以向老师汇报的结论

1. 项目已完成公开来源→skill→60题生产→30题多模型评测→8题深入诊断的完整研究链。
2. 真实评测暴露的低分不应简单解释为任务很难；旧任务存在候选合同和 rubric 问题。
3. 局部确定性门禁和 LLMShadow 能发现局部异常，但不能替代完整任务视角。
4. “LLM整体编辑 + 程序确定性治理”在固定8题上实现8/8修订闭环，成本不足1元。
5. 这支持把后续系统重构为 LLM 主导设计、确定性框架负责治理；但本轮不证明训练价值、benchmark权威性或财务专家认证。

## 七、边界与下一步

- 本轮没有重跑四模型，也没有外部 grader 评分；`export compatible` 只表示修订包符合当前结构和文件合同，不是新的执行评测证据。
- Terra/Luna 并非执业会计师；如需对外宣称财务专业真实性，仍应邀请专业人员抽查。
- 下一阶段应正式比较当前严格流水线、Skill-only 和 LLM主导混合路线，再决定是否重构默认生成链。
- 在该比较完成前，不进入 RL/SFT，不把历史60题自动纳入训练池。

运行证据保存在 ignored `artifacts/milestone_f4/holistic_editorial_01/`；任务包、provider 输出和密钥不进入 Git。
