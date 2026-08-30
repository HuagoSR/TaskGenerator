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

R10.0–R10.4 已完成：离线 schema/static admission、四个接纳的公开 Work Seed、两套专业规则、seed-admission CLI、四份 teacher-only Scenario Bible、两个 curated factory-side Skill、薄目录、按需加载器与来源绑定的 curation report 均已冻结。此前 provider/SDK response-validation 与截断 run 仅是基础设施和编译合同诊断；不得将其解释为模型能力证据。R10.3 readiness gate 同时证明：不得用更复杂的结构化 Bible V2 或手工补字段来绕过叙事 Bible 的确定性投影限制。当前尚无候选文件或任务包。

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

首个私有两领域 A/B run 已冻结为 `incomplete`。四个 session 都只运行一次；审计无 Skill bundle 的 evidence map 少了必填空数组，故静态 admission 不完整、两次 DeepSeek pair review 均未调用。不得补写该产物、重跑单一条件、复用其余三份 bundle 或从该 run 推断 Skill 效果。恢复必须先审阅统一输出合同，再以新的 run ID 从完整 audit A/B pair 开始；不得以特权容器、Stirrup 或另一套 agent 框架改变实验条件。

后续派生证据包实验开始前，必须单独批准执行计划，至少冻结：

1. 专业 Skill 的来源、版本、触发边界与只供 factory-side 使用的范围。
2. 父 Bible、Skill selection、派生证据包、candidate 文件和 teacher-only 映射的隔离方式。
3. 无 Skill/有 Skill 的相同输入比较、最小硬检查和失败归因方式。
4. task/truth、solver/grader 各自独立的执行边界。

任何 R10 任务都不得复用 R7 私有任务、旧 proposal 或旧 provider receipt；每个阶段结束后必须先汇报并等待验收。

## Closeout

每次 R10 切片结束时，更新《项目概要》中的当前状态，将细节报告写入 `artifacts/`，并在 workstream 关闭后归档其计划。不得把运行记录不断追加到本 runbook。
