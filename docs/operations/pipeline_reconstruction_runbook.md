# TaskGenerator 研究运行手册

> 状态：`active / execution boundary`；更新：2026-09-15。
> 本文规定通用 prepare、执行、停止、恢复和收尾规则，不记录 campaign 结果，也不构成模型调用授权。

## 1. 授权与环境

任何作者、Solver、Judge、Grader、SSH 或外部模型调用都必须有当前用户明确授权，并在调用前建立新的 scope，绑定：

- 目标与固定位置；
- 输入目录、task ID、prompt、文件清单及哈希；
- 模型、provider、runner、环境和模板；
- 会话/请求/重试/时间预算；
- 顺序、停止规则、观察点和解释边界。

旧 scope、未用预算、历史计划、模型目录可见或仓库公开均不授权新调用。日常本地操作使用 conda 环境 `taskgenerator`，不用 `base`。

## 2. Prepare

1. 在 ignored `artifacts/` 下创建唯一 scope，拒绝覆盖现有目录。
2. 保存 `run_scope.json`、输入 manifest、代码/runner/environment fingerprint 和执行前 receipt。
3. 候选输入、教师文件和运行证据使用不同目录；候选包保持 GDPval 形状。
4. 如果复用上游包，只读复制或哈希绑定明确版本；不得读取旧 Solver 答案、评分或教师内容作为新作者输入。
5. 运行适用的本地结构检查、计算重放、文件打开/提取/渲染和秘密扫描。
6. 外部调用前确认输出目录不存在或为空。

Prepare 成功只表示输入和装置就绪，不表示任务质量、模型能力或 provider 持续可用。

## 3. Identity Gate

每个外部会话启动前独立核对并保存：

- scope、condition、task ID 与唯一 case 目录；
- 实际 `dataset_row.prompt` SHA-256，而不是作者提示或计划文本；
- reference、deliverable、DeliverableContract 及输入树哈希；
- 候选侧不含 rubric、计算锚点、教师观察或生成脚本；
- 模型、provider、runner hash、Python/依赖版本、sandbox/template 和 worker；
- 本次输出目录为空，预算仍足够。

任何身份不符在模型调用前停止。不得“先跑再核对”。

## 4. 生成与准入

### 生成

- 每个位置使用独立世界和独立作者会话；顺序与预算在首次调用前冻结。
- 作者可在同一会话内使用工具、自检和修正；模型完成后主控制器不修改业务材料或 rubric。
- 原始输出、日志、开始/结束时间、usage、内部工具恢复和控制器介入全部保留。
- 一个位置失败不自动补题；是否继续其他独立位置由 scope 的冻结停止规则决定。

### 离线准入

在查看任何 Solver 答案前完成：

1. GDPval 结构、路径、文件名、引用和隔离检查；
2. CSV/TSV 逐行字段数、XLSX ZIP/重算/公式错误/渲染、DOCX/PDF 打开与视觉检查；
3. 日期、实体、金额、数量、版本、producer、record time、query scope 和 custody 核对；
4. Rubric 要求来源、独立可观察成果、条件边界、容差和替代表达核对；
5. 计算锚点重放与证据定位；
6. 全格式答案提示和 candidate-visible evidence 检查。

发现重大材料、可解性或评分歧义则不准入，保留原稿和检查记录，不由控制器修复后替换首次结果。

## 5. 冻结与行为评测

候选准入后冻结输入、正式 rubric、计算依据及关键职业结果。关键结果必须映射现有 rubric 和候选义务，不增加隐含要求。

Solver 规则：

- 每个 task/model 一个全新隔离会话；worker=1，顺序离线随机并记录。
- 不复用 workspace、session 或非空输出目录；0 人工介入。
- 交付缺失/损坏与职业推理错误分开记录；无效交付不评分。
- 展示层日志截断不等于模型上下文截断。关键行为失败时，沿实际工具命令和 ToolMessage 路径检查 evidence access。

行为核对先判断 evidence-state uptake、unresolved matter 和 follow-up，再判断 disposition 是否职业上合理。允许等价表达，不要求外化非必要内部推理。

## 6. Legacy rw-task 诊断评分

Legacy grader 只接收一份匿名交付及其候选任务和兼容 rubric 视图。适配可复制 `max_points` 到旧字段 `score`，不得改变正式 rubric 的 ID、条件或权重。

- 原生文件先完成 QA；文件失败不交给 Judge。
- 每个 rubric item 必须且只能返回一次，ID、max、award 范围和总分由控制器机械校验。
- 初评、条件复审和最终分分别保存；复审只能向下调整。
- HTTP、解析和控制器重试策略必须在 scope 中明确；失败请求即使无 usage 也计入尝试。
- Legacy 部分分、高分复审和文本提取可能漏掉原生公式/布局问题，结果统一标为 diagnostic。

正式原子 rubric、关键职业结果、文件 QA 和 legacy 总分分别报告，不互相覆盖。

## 7. 停止与恢复

以下情况按 scope 规则停止当前或剩余外部执行：身份错误、认证/隔离/指纹异常、runner 非零退出、确认的模型侧上下文异常、必要交付不可读、provider/框架技术失败或预算不足。

恢复规则：

1. 保留父 scope、receipt、首次响应、失败输出和日志；不得改写终态。
2. 先只读诊断，区分输入错误、模型行为、provider、文件交付和控制器问题。
3. 本地控制器修复用真实失败或成功产物离线回归；不要只用自造 happy-path fixture。
4. 只有新用户授权时才建立 continuation scope，精确绑定未完成项、模型、环境和预算。
5. 已有有效结果不重跑；低分、共同失败或不漂亮结果不构成恢复理由。
6. Provider 502/503、超时和无 usage 请求仍按实际尝试记录；preflight 成功不证明后续稳定。

同一 Solver 会话内自行修正工具命令不等于控制器重跑，但应原样记录。

## 8. Closeout

结束时必须：

- 冻结 receipt 真实状态、所有输入/输出/日志哈希、开始/结束时间、会话和请求计数；
- 汇总全部位置，包括失败、未启动、跳过、人工介入、token 和不可得数据；
- 区分结构有效、专业判断、交付质量、正式 rubric、legacy diagnostic 和研究解释；
- 把宏观结果更新到《项目概要》，详细运行证据只留 ignored artifacts；
- 不自动启动下一批、重跑、发布、训练、部署或 push。

代码变更运行定向/完整回归；纯文档变更检查链接、状态、职责、秘密和 `git diff --check`。提交时只暂存本次文件，保留无关 dirty changes。禁止 force-push；远端分歧先 fetch 并非破坏性合并。

## 9. 只读入口

公开 `taskgen` CLI 只读取版本化本地 JSON 和有限投影，不联网、不读取凭据、不调用模型、不创建 scope。历史 runner 与命令只用于读取既有证据；重新执行必须获得新授权并写入新 scope。
