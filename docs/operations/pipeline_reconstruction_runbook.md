# TaskGenerator 运行 Runbook

> 状态：`active`
> 职责：记录当前可执行边界、停止规则和未来 R10 执行前置条件；不保存历史 provider 操作日志。

## Current Stop Point

R9/R7 的服务器、任务包和评测证据均已冻结。R7 从零复验停在 5/10 provider-stability diagnostic，禁止：

- 恢复、补齐或拼接 R7；
- 上传 R7 私有任务给 solver 或 grader；
- 用历史 cohort 填补 R7 缺口；
- 依据旧 receipt、旧 provider scope 或旧 campaign 继续调用；
- 因模型分数或个别任务表现重抽、手改或重评已冻结任务。

R10.0–R10.4 已完成：离线 schema/static admission、四个接纳的公开 Work Seed、两套专业规则、seed-admission CLI、四份 teacher-only Scenario Bible、两个 curated factory-side Skill、薄目录、按需加载器与来源绑定的 curation report 均已冻结。此前 provider/SDK response-validation 与截断 run 仅是基础设施和编译合同诊断；不得将其解释为模型能力证据。R10.3 readiness gate 同时证明：不得用更复杂的结构化 Bible V2 或手工补字段来绕过叙事 Bible 的确定性投影限制。后续已从这些冻结输入派生四道静态准入的 pilot 任务；不得将它们与早期 incomplete cohort 混用。

## Stable Operational Rules

### Release and server

- 仅从受控 Git commit 构建 release context；context 不得包含 secrets、认证、artifacts、缓存或原始 provider 输出。
- candidate release 必须通过本地和 Linux/amd64 网络关闭、只读根、无凭据 parity，以及 factory/eval smoke。
- huago-cone release 保留 `current` 与 `previous`；激活、rollback 和清理只作用于明确标记的 TaskGenerator 资源。
- 发布、构建和激活前可用空间不得低于 **95 GiB**。全局 Docker/BuildKit 清理由单独授权决定，禁止默认 `docker system prune` 或触碰其他项目。

### Secrets and external effects

- API key、认证文件和 `.env` 不进入镜像、命令、日志、任务包、文档或提交。
- 私有任务上传、provider 调用、solver、grader、registry mutation、release 激活和训练均须有当前阶段的独立授权。
- 运行产物写入 ignored `artifacts/` 或服务器持久化目录，保存首错、指纹、输出树和脱敏诊断。
- 现有项目模型策略继续生效：Tuzi `claude-*` 与 `gpt-5.4-pro` 不得进入生成、solver 或 grader，除非用户另行明确撤销该策略。

### Task integrity

- candidate-visible 输入、teacher-only truth 和治理证据分目录并分别指纹化。
- 仅精确路径、非空、可打开且非输入副本的交付物可进入 grader。
- provider/环境失败、无交付和业务错误必须分别记录；不得把基础设施失败计为模型能力失败。

## R10 Execution Preconditions

R10.0–R10.4 已完成。R10.5 的公开 agent/filesystem probe 已通过：原先的 Bubblewrap 嵌套 user-namespace 问题改由受限外层 Docker 承担隔离，Codex 在其中使用非嵌套 Shell；外层仍须保持只读根、无额外 capability、`no-new-privileges`、资源上限、单一临时工作区和只读认证挂载。公开 probe 已验证 XLSX、DOCX、PDF。

两个早期私有 cohort 均冻结为 `incomplete`，不得混入或选择性复用。extension/evidence-map 的最终接口只要求 teacher-only extension 登记安全、唯一的 ID 与 statement，并允许保留不参与闭合判断的 Agent 上下文；evidence map 只能使用父 Bible 或已登记 ID。不得以特权容器、Stirrup 或另一套 agent 框架改变实验条件。

自动 Skill Compiler 已在 Codex/Sol 上完成两项完整专业 Skill 包，并通过两项独立 DeepSeek 来源/内容审查。最新共同基础 A/B cohort 的四个 Terra session 均静态通过，DeepSeek 两次盲审完成并聚合为 `skill_effect_supported`。用户已授予 R10持续外部调用授权，每个新 run 仍须落盘新的 scope/receipt。

R10.6 两题 task/truth compilation 已完成：第三个 scope/receipt 绑定两份冻结有 Skill bundle、父 Bible、规则、Skill、Codex/Sol 和镜像；两题均静态通过。Teacher Truth 事实必须由所列 candidate evidence 的 evidence map 投影支持；路径规范化不改变证据含义，初始 blocked 报告保留。用户已完成两题表面审题。

R10.7A 已完成：控制缺陷组合评估与商业交付验收处置已形成两份有 Skill evidence bundle、两道 task/truth package 和中文用户检查包。四题均通过静态 admission 并获用户形态验收；候选 package 保持冻结。

R10.7B 原始结果为 `behaviorally_admitted`：两条 solver 均通过公开 XLSX/DOCX probe、各完成四份有效交付；16 次 route-blind LLM proxy 评分完整。随后 R10.8A 发现采购验收题的 teacher-side 容差算术错误（3/40 为 7.5%，不是 5% 以内）。候选文件和题干不变，原结果冻结为历史记录。

R10.8A 已完成新的 judge-only campaign：修正后的 Teacher Anchor Audit 通过；本机 Codex CLI 0.149.1 的多文件公开 Judge probe 通过后，GPT Judge 在本地运行，DeepSeek Judge保留官方 DeepSeek/OpenCode。两份冻结 Solver delivery 分别由两位 Judge评分，四项均完成；重聚合为 `behaviorally_admitted`，两条 solver 均 4/4 有效交付、四题双评委完整、无 teacher-anchor conflict。模型区分度仍为 `low_model_separation`。huago Codex candidate 继续不激活，且不再是本阶段阻塞条件。

R10.8B-1 的只读诊断已完成：采购价格合理性和采购验收题评分饱和，收入证据题接近平局，控制缺陷题存在 Judge 边界歧义；没有干净可比较的任务，结论为 `compiler_revision_candidate`。诊断报告只读取冻结 records、聚合与绑定，未调用 provider、未写入 candidate/teacher 目录，也未改变历史评分。

当前停止点：R10.8B-2 的离线校准与代码改良已完成，新的私有 campaign scope 尚待授权。该实验只从收入证据可靠性和价格合理性两个冻结 Bible 派生新版任务；不修改旧四题，不上传 GDPval 内容。公开 XLSX/DOCX probe 通过后，才允许将冻结 Bible、Rules、Skill 上传给本机 Codex 生成两份 evidence bundle 并编译两题。两题静态 admission 与用户检查完成前，不运行 solver 或 judge。十题扩展必须在该实验的两题行为结果均为干净、可解释差异后另行计划；不得混入旧 Solver、旧 receipt 或旧 Judge 结果。

后续派生证据包实验开始前，必须单独批准执行计划，至少冻结：

1. 专业 Skill 的来源、版本、触发边界与只供 factory-side 使用的范围。
2. 父 Bible、Skill selection、派生证据包、candidate 文件和 teacher-only 映射的隔离方式。
3. 无 Skill/有 Skill 的相同输入比较、最小硬检查和失败归因方式。
4. task/truth、solver/grader 各自独立的执行边界。

任何 R10 任务都不得复用 R7 私有任务、旧 proposal 或旧 provider receipt；每个阶段结束后必须先汇报并等待验收。

## Closeout

每次 R10 切片结束时，更新《项目概要》中的当前状态，将细节报告写入 `artifacts/`，并在 workstream 关闭后归档其计划。不得把运行记录不断追加到本 runbook。
