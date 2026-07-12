# 财务审计 30 题评测：8 题人工式诊断审查

> 审查状态：`completed`
>
> 审查范围：任务 `#2 / #6 / #13 / #18 / #31 / #35 / #38 / #47`
>
> 结论边界：这是 AI 辅助的工程、逻辑与基础财务核算复核，不是执业会计师或审计师认证。

## 一、结论先行

本次低分不能主要归因于“任务很难”。8 题的业务骨架、合成数据和文件可读性总体可用，但三类模板都存在会影响唯一作答的候选材料缺口；8 份 rubric 又都缺少直接事实核验项，并把大部分权重分配给与具体任务关系很弱的通用技能。这两个问题共同压低并压缩了模型分数，也放大了 grader 差异。

核心诊断如下：

- `8/8` 任务需要修改候选材料或任务合同后才能作为可靠评测题使用；这并不等于全部推倒重做，主要是补齐关键事实和判定规则。
- `8/8` rubric 需要重写。每份 rubric 均为 15 条，其中 12 条 reasoning、3 条 compliance、`0` 条独立 fact-check；直接对应可见交付要求的最后 3 条仅占 `9/37 = 24.3%`。
- `#13 / #18 / #35` 的双 grader 分歧不能用模型质量解释，存在明确的评分标准不一致；其中 `#18` 的三份有效交付物主评与复评相差约 `0.38–0.43`。
- `gpt-4o-mini` 暴露了真实的文件工具与任务执行能力不足：`#18`、`#31` 未交付，`#2` 产生 0 字节 XLSX，`#38` 用 CSV 替代要求的 DOCX；这些失败不能归咎于 grader。
- 强一些的模型通常能完成匹配、差异计算和成品文件，但有时会顺着 teacher truth 的隐含假设作答。例如费用题把“单笔餐费总额”直接当作“人均餐费”，材料并不支持这一推断。

因此，30 题评测可以向老师证明：系统已能批量生成可执行的文件型任务，并且真实模型在文件交付能力上存在明显差异；但当前分数不能直接当作任务质量或模型财务能力的可靠标尺。在训练前，优先工作应是修复任务合同和 rubric，再用小规模复评确认分数含义。

## 二、方法与证据边界

审查严格按两层进行：先只读取 candidate-visible prompt、reference files 和 deliverable contract，独立重算关键事实；记录盲审结果后，才读取 GoldenRun、deterministic answer key、training annotation、rubric、四模型交付物和已有 grader 证据。没有重新调用 solver 或 grader，没有补跑 `non_delivery`，也没有修改原任务或服务器评测结果。

证据按以下目录隔离保存在 ignored artifacts：

```text
artifacts/finance_30_human_review_01/
├── candidate_view/
├── blind_review/
├── teacher_view/
├── solver_outputs/
├── grades/
└── evidence_sha256_manifest.json
```

候选输入的 16 个 XLSX、16 个相关 sheet 已完成值、类型、关键关系和视觉检查：表格均可打开，蓝色表头、列宽和数值显示正常，未发现截断或不可读 sheet。DOCX 已完成文本和表格结构检查，但本机与候选 Docker 镜像均缺少 LibreOffice，Word COM 回退也未成功，因此本次没有把 DOCX 结构检查冒充逐页视觉验收；这是本报告的明确验证限制。

## 三、8 题核心诊断表

| 任务 | motif / 原标签 | 主分类 | 主要严重度 | 核心证据 | 辅助标签 |
| --- | --- | --- | --- | --- | --- |
| #2 | fan-in / informative | `task_needs_revision` | major | 缺少期初或期末余额，却要求 adjusted bank/ledger balances；活动净额不能唯一代表账户余额 | `rubric_needs_revision`, `solver_capability_failure` |
| #6 | fan-in / mixed | `task_needs_revision` | major | 与 #2 相同；匹配事实可确定，但最终余额合同不可执行 | `rubric_needs_revision` |
| #13 | cross-check / grader unstable | `task_needs_revision` | major | 差异事实可重算，但没有规则定义 `clear/hold/investigate`；grader 对合理交付给出跨通过线分歧 | `rubric_needs_revision`, `grader_problem` |
| #18 | policy / non-delivery + unstable | `task_needs_revision` | blocking | policy 以“每人 100”为阈值，输入没有就餐人数；teacher 将交易总额当人均额；有效输出双评分差极大 | `rubric_needs_revision`, `grader_problem`, `solver_capability_failure` |
| #31 | cross-check / non-delivery | `task_needs_revision` | major | 状态规则缺失；三个有效模型主评分均为 0.4865，显示 rubric 压缩；mini 未产生要求文件 | `rubric_needs_revision`, `solver_capability_failure` |
| #35 | policy / too-hard + unstable | `task_needs_revision` | blocking | 与 #18 相同的 per-person 缺口；双 grader 对相同文件的通用技能得分差异显著 | `rubric_needs_revision`, `grader_problem`, `solver_capability_failure` |
| #38 | policy / stable too-hard | `task_needs_revision` | blocking | per-person 规则不可判定；mini 用两个 CSV 替代要求的 DOCX | `rubric_needs_revision`, `solver_capability_failure` |
| #47 | cross-check / compressed | `task_needs_revision` | major | 业务差异可确定，处置状态不可唯一确定；低 spread 主要受 rubric 与模板同质性影响 | `rubric_needs_revision` |

这里的 `blocking` 指当前版本不适合直接作为有确定答案的训练或评测样本，并不代表任务主题本身不可用。

## 四、Candidate-blind 独立核算

### 4.1 银行对账：#2、#6

两题均有 10 笔可按日期、金额和业务关系精确匹配的记录，另有 2 笔 bank-only 与 2 笔 ledger-only。两侧未匹配记录的日期和金额一一对应，只是引用编号分别使用 `BANK-*` 与 `BOOK-*`，更像引用差异而不是真正未达项。

| 任务 | bank activity 合计 | ledger activity 合计 | matched activity 合计 | blind 结论 |
| --- | ---: | ---: | ---: | --- |
| #2 | -3,096.70 | -3,096.70 | -1,108.85 | 匹配和差异可确定；adjusted balance 不可确定 |
| #6 | -2,959.50 | -2,959.50 | -1,040.25 | 匹配和差异可确定；adjusted balance 不可确定 |

问题不在算术，而在语义：输入只有期间 activity，没有 bank statement ending balance、book ending balance 或 opening balance。把 activity 合计命名为 unadjusted/adjusted balance 是额外假设。Teacher key 也只复述了匹配事实，没有提供能补足这一缺口的真实余额。

### 4.2 三单匹配：#13、#31、#47

每题 11 条 invoice line，blind 重算均能稳定识别：

- 1 条 unit-price variance（发票单价相对 PO 高 3）；
- 1 条 quantity variance（发票数量相对 receipt 高 3、相对 PO 高 2）；
- 1 对 duplicate invoice records；
- 其余 7 条在数量与单价层面无差异。

Teacher key 将 duplicate pair 的两条记录都列为异常，这在“重复组”语义下合理；但 candidate-visible policy 没有说明 duplicate pair 应处置原始记录、后续记录还是两者，也没有阈值或规则将异常映射为 `hold` 或 `investigate`。因此金额与数量事实是确定的，最终状态不是唯一答案。

### 4.3 费用政策：#18、#35、#38

每题 14 条交易。三类异常中，缺收据、娱乐费缺 Director approval、娱乐费缺收据均可由输入直接判定；餐费规则则写为“above 100 per person requires Director approval”，但交易表没有 attendee count 或 per-person amount。

| 任务 | 可确定异常数 / 金额 | 无法判定的餐费数 / 金额 | Teacher key 异常数 / 金额 |
| --- | ---: | ---: | ---: |
| #18 | 3 / 1,095.50 | 2 / 996.40 | 5 / 2,091.90 |
| #35 | 3 / 1,087.40 | 2 / 991.00 | 5 / 2,078.40 |
| #38 | 3 / 1,116.05 | 2 / 1,010.10 | 5 / 2,126.15 |

Teacher key 隐含采用“交易总额等于人均金额”的假设。该假设未出现在 prompt、policy 或输入字段中，属于 primary truth 缺口。合理修法是增加 attendee count/per-person amount，或把政策改成“单笔餐费总额超过 100”。

## 五、Teacher truth 与 rubric 审计

GoldenRun 的执行结构完整，但它主要记录通用中间状态，不能补充 candidate 不可见的余额、处置规则或就餐人数。三类 key 的情况分别是：银行对账的匹配事实正确但未真正给出账户余额；三单匹配的差异事实正确但处置标签缺少政策依据；费用题的 POL-002 判定建立在不可见假设上。

Rubric 是更系统的问题。8 题均使用 15 条、37 分的结构，前 12 条占 28 分，主要检查通用 reasoning skill；最后 3 条占 9 分，才直接检查任务要求。未发现独立核对金额、数量、匹配集合或异常集合的 fact-check 条目。

跨领域残留示例包括：

- 银行对账 rubric 要求 “Cross-verify Quantities Across Order, Receipt, and Invoice”；
- 三单匹配 rubric 出现费用抽样、银行对账、executive travel/hospitality；
- 费用题 rubric 出现 missing goods receipt、cash posting、FAA pre-authorization 等无关能力。

这会产生两个后果：第一，业务结果正确的文件仍因没有展示无关技能而失分；第二，grader 必须主观判断“是否体现某种技能”，导致不同 grader 的尺度差异。#2 的 Claude 交付物被主 grader 评价为专业且匹配/差异计算可靠，仍因无关 criteria 只得 `28/37 = 0.7568`，是最直观的例子。

建议 rubric 改为：关键业务事实与公式 55%–65%，交付物完整性与可追溯性 20%–30%，文件可用性与表达 10%–15%；只有任务明确要求时才加入过程性或风格性 criteria。

## 六、模型交付与 grader 诊断

### 6.1 Solver 失败

- `#18 / gpt-4o-mini`：多次尝试创建或移动 `expense_exception_summary.xlsx`，最终要求文件不存在；没有可评分交付物。
- `#31 / gpt-4o-mini`：尝试 CSV/XLSX 路径但最终均不存在；没有可评分交付物。
- `#2 / gpt-4o-mini`：生成了 0 字节 `cash_reconciliation.xlsx`，虽然流程记录不属于 `non_delivery`，文件实际不可用。
- `#38 / gpt-4o-mini`：生成两个 CSV，而合同要求 DOCX，属于格式与工具执行失败。

#18、#31 日志尾部还出现 `/home/taskgenerator/.cache` 只读错误。它发生在 agent 已经没有交付文件之后，不能解释业务输出缺失，但说明容器 session 收尾仍有环境噪声，后续 runner 应把 cache 指向可写临时目录。

### 6.2 有效交付物质量

Claude、DeepSeek 和 Gemini 大多能生成可打开的多 sheet XLSX 或结构完整 DOCX。以 #13 为例，三个模型都识别了价格差、数量差和 duplicate pair；`gpt-4o-mini` 虽计算出 variance，却把所有行标成 clear，属于核心业务判断失败。

费用题中，较强模型通常与 teacher key 一致地标出 5 个异常，但这反而揭示了 teacher 假设的传播：模型可能只是采用了最直接的阈值解释。DeepSeek 在 #18 中明确提示没有 attendee count，却仍把总额超过 100 的餐费列为 review，这比把它宣称为确定违规更审慎。

### 6.3 Grader 分歧

- #13：有效模型在主评与复评间出现约 `0.14–0.16` 差异，并有 0.60 通过线判断不一致；差异主要来自前 12 条通用技能，而直接交付要求得分相对稳定。
- #18：Gemini、DeepSeek、Claude 主评分分别约 `0.432 / 0.351 / 0.378`，复评约 `0.838 / 0.757 / 0.811`。如此大的同文件分差说明 grader 标尺本身不稳定，不能据此判断任务“太难”。
- #35：有效模型主评分约 `0.243–0.297`，复评约 `0.459–0.514`；最后 3 条直接要求通常得分较接近，差异仍集中在无关 reasoning criteria。

本轮不调用第三 grader。上述三题标为 `grader_problem`；其余题没有足够证据证明 grader 稳定，只能说未触发既定 instability 门槛。

## 七、八维严重度汇总

| 维度 | pass | minor | major | blocking | 解释 |
| --- | ---: | ---: | ---: | ---: | --- |
| 任务真实性与清晰度 | 0 | 3 | 5 | 0 | 场景真实，但关键术语/处置口径不足 |
| 输入材料充分性 | 0 | 0 | 5 | 3 | 费用题缺 per-person 信息最严重 |
| GoldenRun/答案正确性 | 0 | 2 | 3 | 3 | 费用 key 含不可见假设；另两类未覆盖语义缺口 |
| 交付物合同可执行性 | 0 | 0 | 5 | 3 | 核心文件可产出，但最终结论不总能唯一确定 |
| rubric 对齐与权重 | 0 | 0 | 8 | 0 | 0 fact-check，大量跨任务技能残留 |
| 文件可用性与视觉质量 | 8 | 0 | 0 | 0 | candidate XLSX 全部通过；DOCX 仅结构检查，视觉验收受限 |
| 模型失败归因 | 4 | 0 | 4 | 0 | 主要集中于 gpt-4o-mini 文件工具与核心判断 |
| grader 可靠性 | 5 | 0 | 3 | 0 | #13/#18/#35 有明确不稳定证据 |

“文件可用性与视觉质量”一栏的 pass 只表示 candidate XLSX 和 DOCX 结构没有发现阻塞缺陷；由于 DOCX 未完成逐页渲染，该维度仍带上述验证限制。

## 八、可汇报结论与下一步

可以向老师汇报：

1. 系统已完成 60 题批量生产，并从中对 30 题进行了四模型真实执行；弱模型的文件交付失败与较强模型的稳定交付形成了真实区分信号。
2. 8 题人工式抽查表明，合成数据的主要匹配、金额和异常关系大多可重算，文件也基本可用，因此流水线不是在生成完全无意义的题。
3. 当前低分被任务合同缺口和 rubric 错配显著污染，尤其不能把 `too_hard` 直接解释成高质量难题。
4. LLM grader 能用于批量初筛，但 10/30 的不稳定率和本次三个典型案例说明，推广前必须抽审评分依据。

建议按以下顺序继续：

1. 先修三类模板的 candidate-visible contract：补余额、补处置政策、补 attendee count 或改阈值措辞。
2. 重建以事实核验为主的 rubric，删除跨领域技能残留，并用确定性 checker 覆盖可计算项。
3. 不重做 60 题；先从本次 8 题生成修订版小 cohort，仅复评 3–5 题验证分数是否恢复可解释性。
4. 在 rubric 稳定前，不进入 RL 数据格式和奖励设计；否则训练会把错误或不稳定的评分信号放大。
5. 若准备正式对外声称财务专业真实性，再请具备会计/审计背景的人对修订后的少量样本签字复核。

本次审查的最终状态为：

```text
human_style_review = completed
reviewed_tasks = 8 / 8
task_contract_revision_required = true
rubric_revision_required = true
new_external_calls = 0
remaining_30_tasks_started = false
training_readiness_claim_allowed = false
```
