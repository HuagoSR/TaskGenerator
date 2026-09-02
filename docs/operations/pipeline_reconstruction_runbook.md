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

R10.8B-2 已用新的服务器 ChatGPT 认证目录完成独立公开门和两题私有 campaign。两模型均完成两题有效交付，8 项双评委评分完整；收入题仍为 `near_tie`，价格题虽有明显分差但为 `judge_ambiguous`，最终结论为 `evaluator_revision_required`。R10.8 已关闭，禁止继续六题/十题扩展、重抽答案、混合历史 Tuzi/旧账号证据、修改冻结题目或激活 release。

当前执行点是 R10.9 World-First / Task-Mining pilot：复用两项公开 Seed/Rules，但从零生成审计和采购工作世界，各形成普通版与职业对抗强化版。Task Miner 不得读取 world ledger、难度身份或预期答案；Truth Reconstructor 不得读取隐藏 ledger；正式 Solver 前必须完成三档完整交付的双 Judge 校准。用户已对该 R10.9 campaign 的服务器和第三方模型上传给出持续授权；仍须创建独立 scope/receipt，但无需等待逐 SHA 确认。

R10.9 执行前必须冻结：

1. Work Seed、Rules、专业 Skill、难度计划和官方来源 SHA。
2. 基础/强化工作世界、candidate 文件与 teacher-only ledger 的隔离方式。
3. Task Miner、Truth Reconstructor、Judge 校准与 Solver 的盲区。
4. matched task、交付合同、Decision Matrix 和 paired review 的执行边界。

任何 R10.9 任务都不得复用旧 Bible、R7/R8 私有任务、旧 proposal、旧答案或旧 provider receipt。前一门失败时停止后续调用；不因低分或希望提高区分度重抽。

## Closeout

每次 R10 切片结束时，更新《项目概要》中的当前状态，将细节报告写入 `artifacts/`，并在 workstream 关闭后归档其计划。不得把运行记录不断追加到本 runbook。
