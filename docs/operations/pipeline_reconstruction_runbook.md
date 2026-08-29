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

R10.0 与 R10.1 已完成：离线 schema/static admission，以及四个接纳的公开 Work Seed、两套专业规则和 seed-admission CLI 均已冻结。当前仍没有 Scenario Bible provider scope、campaign receipt 或任务包。不得把公开 seed 或离线 fixture 解释为生产结果、私有任务上传授权或 provider 授权。

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

R10.0/R10.1 已完成。开始 R10.2 语义执行前，必须先完成并批准一个执行计划，至少冻结：

1. 四个接纳 seed 对应的 Bible semantic input、teacher-only 输出边界和隐私边界。
2. R10.2 provider 批次、冻结输入、整批重启与失败证据合同。
3. Bible/projection/compiler、文件渲染和完整 package-isolation 测试。
4. R10 release、parity、campaign、solver 和 grader 的独立执行合同。

只有这些前置条件通过后，才能启动新的 R10 source-to-package campaign；任何 R10 任务都不得复用 R7 私有任务、旧 proposal 或旧 provider receipt。

## Closeout

每次 R10 切片结束时，更新《项目概要》中的当前状态，将细节报告写入 `artifacts/`，并在 workstream 关闭后归档其计划。不得把运行记录不断追加到本 runbook。
