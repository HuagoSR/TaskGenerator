# R10 研究结论与执行经验摘要（截至 2026-09-14）

> 状态：`historical summary`。本文保留跨阶段可复用结论，不承担当前状态管理；当前状态以根目录《项目概要》为准。瘦身前活跃文档的逐字版本见 Git `66ce931`。

## 生成方法的演进

- 历史多阶段流程 P 完成过复杂角色编排；同期有限对照未观察到足以证明的额外质量收益，且耗时和运行复杂度明显高于单作者 S1。
- S1 因而成为优先开发路径：一个强作者接收完整合同和 Professional Skill，使用工具与自检，提交后走共同准入。P 保留为研究参照。
- S1 在多个审计和采购世界生成过获得有限支持的任务包；这证明方法可运行，不证明稳定合格率、专家质量或生产就绪。
- 两个 2026-09-14 四题小批均为 4 个首次位置、3 个准入、1 个 CSV 结构失败。失败位置不修复补位，是生产率和工程成本的一部分。

## Blind-use 与输入隔离

G1 的第三次正确 blind-use 中，隔离 Solver 只看到真实题干、8 份候选材料和提交说明，完成价格重建、跨来源比较及有边界结论。作者与 Solver 同源、仅单案例且无正式 Grader。

此前两次错误启动必须永久保留：

- `wrong_input_dataset`：运行了旧 rep2/ArdentHome 输入。
- `wrong_input_prompt`：把 S1 作者提示发送给 Solver，模型再次构建任务包而非完成候选任务。

这些错误促成启动前 identity gate：核对 task ID、真实 `dataset_row.prompt`、实际输入树、模型、provider、runner 和空输出目录。错误运行计入真实消耗，不能改名为有效实验。

## 难度机制的当前证据

### G1/W2

W2 要求跨文件组合保修期、数量和每台成本。`gpt-5.4-mini` 在无辅助和机械汇总辅助两侧都完整完成该步骤；单对 token 差异不能归因于辅助。当前证据不支持把“藏一个跨文件数字”当作主要瓶颈。

### G1/W3

历史 freight 缺少线性随数量变化的承运商证据。A 正确把线性缩放标为 sensitivity assumption；B 在新增正式承运商事实后将其改为有事实依据的处理。该局部 manipulation check 支持 evidence-conditioned epistemic calibration。A 同时出现两处无关算术错误（IGCE `70,440` 而非 `77,940`；历史订单 `56,320` 而非 `52,120`），因此不能干净估计整体数值或最终结论效应。

### G2

早期 G2-B 看到了批准 correction，却未完整把测试属性沿 `identity → attribute → requirement → disposition` 传导，形成 relation/state updating 候选机制。后续审计修正了过强解释：

- correction 已直接陈述部分下游关系，graph depth 不等于 inference depth；没有证据说明“越深越难”。
- 职业交付不必外化完整 tuple 或 correction chain；未写出不能证明内部状态未更新。
- 是否继续列旧 mismatch、是否保留局部限制属于 behaviorally observable；内部完整关系可能 latent/not identifiable。
- `AP7-261190` 缺 mandatory QC 明确成立，但材料未唯一规定必须使用 `documentation hold` 标签，因此原阴性控制为 `ambiguous_control`。

由此形成 behavioral measurement spec：先测证据存在/缺失、unresolved state 和匹配 follow-up，再允许 hold、referral、conditional consideration 等职业上合理表达。正确处置只证明行为与证据一致，不识别模型内部表示。

## 受控实验与材料因果

- A/B 前必须审计 PDF、CSV、XLSX、DOCX 等全部 candidate-visible 内容，确认目标事实确实只随条件变化。
- accessibility、页数、关键位置和提取路径需要匹配，但结构对称不能凌驾于业务因果真实性。
- 记录类别必须由真实 producer、source system、record time、query scope、effective date 和 custody 支持。
- Northbridge 审批身份/权限候选需要新增 workflow store 和 authority register，结论为 `requires_world_extension`；不能把 IAM/权限字段硬塞进 journal detail。
- ATE current-definition 候选虽结构上接近可物化，但共同 XLSX 已包含目标语义，最终死于 evidence isolation。项目没有删除原始材料“救活”实验。

## 文件质量与准入经验

- T3 的 CSV 行短于表头，导致字段错位；N2 的两行比表头多一个尾随字段。共同检查器通过不代表每个表格记录可用，CSV 行宽必须逐行核对。
- XLSX 需要 ZIP/openability、公式重算、错误扫描、机械读取和视觉渲染；缓存存在与否不证明公式正确。
- N3/Terra 工作簿有 3 个公式错误，但 legacy grader 给出 100/100，证明文本化评分会漏掉原生文件缺陷。
- DOCX/XLSX/Markdown 的结构有效、职业正确和评分表现必须分开报告。

## 评测与恢复经验

N1/N3/N4 共完成 9 个隔离 Solver 会话。Legacy Judge 最终分数为：

| 任务 | Terra | Flash-lite | Mini |
|---|---:|---:|---:|
| N1 | 88 | 58 | 39 |
| N3 | 100 | 85 | 71 |
| N4 | 100 | 96 | 50 |

恢复过程中依次暴露：

1. wrapper 按文件启动时未把 `rw-task` 根加入 `sys.path`，在 HTTP 前失败；
2. post-response 校验错误假定 rubric 字段为 `id`，实际适配视图保留 `criterion_id`；
3. audit 原始响应只有逐项结果，没有总分字段，必须按真实结构校验 downward merge；
4. Tuzi 出现一次 503、两次 502；无有效响应的尝试仍计数，预检成功不代表评测窗口持续稳定。

修复原则是保留父 scope 和失败产物，在新授权 scope 中绑定原输入、环境和预算；先用真实失败/成功响应回归本地修复，再继续未完成项。不得覆盖 receipt、静默重试或把 provider 故障归因于任务。

## 稳定边界

- 正式原子 rubric 是唯一评分权威；关键职业结果是诊断映射，legacy 整数分是辅助信号。
- 单次模型差异不证明稳定排名或区分率；共同失败也不自动证明任务困难且优质。
- GDPval 内容只用于 evaluator calibration，不进入生成、提示调优或策略选择。
- 不建设自动评分反馈优化器、通用业务本体或 evidence-graph runtime；RL、训练和公开发布不在当前范围。
