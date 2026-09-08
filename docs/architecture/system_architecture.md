# 系统架构

> 状态：active；核对日期：2026-09-09。
> 只说明结构与职责；完成情况见[项目概要](../../项目概要.md)。

## R10 研究主线

```text
公开 Work Seed + Professional Rules
→ 专业 Skill 与来源约束的难度设计
→ 工作世界及自然业务材料
→ 冻结候选文件
→ 独立 Task Mining
→ 独立 Teacher Truth / Decision Matrix / Rubric 编译
→ 静态检查与按实验计划进行的行为验收
```

这是已实现的研究方法链，由阶段 runner 执行；不等于已验证的无人值守规模化生产服务。

## 各层职责

- **Work Seed / Rules**：解释角色为何此时收到工作、成果供谁使用，以及专业方法与规则。公开规范不是虚构组织的事实。
- **专业 Skill**：按需加载的出题侧职业知识包，说明自然证据关系、判断与常见错误。通用文件操作由现成工具承担；Skill 不预先决定题目模板，首轮不提供给 Solver。
- **工作世界**：先形成组织、时间线、正常业务背景与跨系统记录，不先写题干或 rubric。隐藏 world_ledger.md 和候选业务文件分离。
- **Task Miner**：只看候选材料与公开角色/触发背景，不看隐藏 ledger、难度条件或预期答案，从工作材料中发现任务。
- **Truth / Task Compiler**：从可见材料与规则重建专业判断，编译单一交付合同和监督；任务要求必须可由候选证据支持，包括允许不确定结论。
- **Admission / Evaluation**：分开记录结构有效、专业合理性、交付成功和模型行为。校准或 Agent 审查通过，不代替真实行为证据或专家有效性。

## 自主工厂与开发试做 harness

[自主工厂入口](../../Test/run_r10_agent_factory_pilot.py)复用原生 Codex/OpenCode；[核心模块](../../src/task_generator/production/agent_factory.py)管理角色会话、版本父依赖、预算及下游失效，[工具模块](../../src/task_generator/production/agent_factory_tools.py)提供文件检查、快照、咨询、意见处理和提交，[批次模块](../../src/task_generator/production/agent_factory_batch.py)管理固定位置。现有主链为生产、提交、终审、通过后的末端试做；试做不回流旧题修订。

开发 harness 由[入口](../../Test/run_r10_task_factory_harness.py)和[协议模块](../../src/task_generator/production/task_factory_harness.py)实现。编译者先基于候选材料冻结依据与计算脚本；控制器断网重放后才启动独立开发试做，再把试做证据和独立保存的设计意图交给原编译会话。计算依据version 2允许一个execution一次产出结构化JSON，多个rubric锚点以JSON Pointer读取；预期值留在教师侧。最终 solve 仍是终审通过后的新会话，不与开发试做混用。2026-09-09新采购开发scope已完成最终提交、独立终审和盲试做；这只是一题的provisional / LLM-proxy证据，状态与限制见概要。

隔离单位是任务、角色和版本，包括文件、提示词、反馈、持久会话和工具可见性。生产者说明单独存储，不能传给盲态试做者；编译者读取试做后不再称盲态审查。程序只管理合法请求与边界，不要求新增全知调度 Agent；同题修改按依赖顺序执行。设计论据见[调研记录](../research/agent_task_production_harness_20260907.md)。

## 保留的主评分路径（执行暂停）

固定任务、原 rubric 与一份匿名交付 → 材料完整性检查 → Judge 逐 rubric item 独立评分 → 控制器校验覆盖、分值、条件项和证据路径 → 控制器求和并绑定哈希。

主路径不产生 pairwise preference 或 holistic score，不在高分后启动第二轮降分审计，也不以 rubric 外偏好扣分。Agent-native 文件检查与逐项评分是保留的实验能力；pairwise 只作诊断。无效交付先在结构层停止；材料不足标记 `incomplete`，不进入可比较的语义总分。

任务交换边界保持 GDPval 兼容；R10 冻结任务只制作适配副本，原包不改动。实现入口见[合同索引](global_interface_contracts.md)。

评分扩展现已暂停；下述为保留实现，不代表已通过可靠性验收。完整评分基线不再是所有造题研究的前置条件，但行为分差结论仍需充分证据。现有 G2 容器仅系统根只读，workspace 实际为读写挂载；提示词中的只读要求不能视为输入只读挂载保证。原文件哈希核对与证据包哈希也不证明全部运行时输入未被修改或专业核验充分。

## Controlled Solver 校准路径

固定 GDPval 任务包与模型组 → 统一 `stirrup==0.1.8` 工具循环 → 固定 E2B template/build → GDPval 交付收集 → 交付合同核验 → strict 独立逐项主评分。昂贵 Solver 前先依次通过 route 目录快照、完整工具闭环预检和 Judge 合同微型探针；任何硬门槛失败均冻结 scope，不以换模型或改端点继续。跨 Judge 校准可将 strict 指令、原 rubric、证据根、确定性材料文本和 schema 固定成同一匿名 packet，transport 只负责返回逐项 JSON。模型间固定 prompt、工具、turn 上限与 sandbox；provider 输出上限与 Agent 上下文窗口分开配置；每次运行单独记录版本、哈希、不含机密的请求/工具进度、首次失败及合法技术恢复。交付收集遵循 rw-task 的 finish 路径语义，核验数量、类型、非空与可打开性，不将隐藏 reference 文件名当作 Solver 义务。

Codex/OpenCode 原生 harness 仍可用于真实 Agent-stack 行为诊断，但其不同工具编排不能替代受控模型比较。shadow downward audit 只解释旧系统的非对称降分效应，永不覆盖主分。实现保持为阶段薄控制器，不扩展成通用 evaluator 框架。

Motif 是生成后的信息关系标签，不是生成起点。难度来自业务量、口径、时间、权限和证据限制，不能来自不可见答案或格式破坏。文件数、记录数是质量指引，不是新配额。

## 既有局部改良：Rubric V2

冻结任务要求、候选材料及监督 → Terra 编译评分项 → DeepSeek 独立审查 → 中文检查材料。

一个专业判断可以对应多个可辨认的成果。每项同时说明要求来源、分值边界、条件例外、等价表达和核验范围；不套用固定拆分比例。开发试做现可在隔离上下文中向本题编译者提供实际完成证据，但不改变旧实验隔离规则或接入历史答案；同一上游版本只保留一个有效开发试做。上述派生实验不读取历史 Solver 答案、成绩、排名或 GDPval 内容，也不自动启动评分。接口见[合同索引](global_interface_contracts.md)。

## 历史能力与隔离

- R9 工厂保留“来源→skill→brief/proposal→确定性物化→验证/导出→评测”的批处理实现，不再作为 R10 的 motif-first 生成路线。
- R10 早期 ScenarioBibleV1 与 evidence A/B 结果只读保留；World-First 不要求补建 Bible V2。
- 历史 paired evaluator、major-error panel 和 GDPval 排名实验不构成当前默认评分方式。当前默认是独立单份、逐项 rubric 给分、程序求和；额外偏好不改变总分。
- 可复用实现放在 src/task_generator/，阶段入口放在 Test/，产物与运行诊断放在 ignored artifacts/。

## 硬边界

程序只承担来源/身份追溯、路径安全、文件可打开性、候选与监督隔离、引用闭合、直接答案泄漏检查及持久化。专业语义交给 Agent 并保留不确定性，不为每个业务情景建设新本体或通用验证器。训练、公开题库、部署和默认模型变更都不由实验结果自动触发。
