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

R10.9 World-First / Task-Mining pilot 已完成：4/4 世界和任务静态通过，Task Miner、Truth Reconstructor、独立 truth audit 与四题三档 Judge 校准完整；GPT/DeepSeek Solver 形成 8/8 有效交付。正式 paired review 四题均为 `judge_ambiguous`，原因是两位 Judge 的偏好方向或 major-error 边界不一致。最终结论为 `evaluator_revision_required`，不是 World-First 成功或失败的能力结论。

R10.9 已冻结并保留：

1. Work Seed、Rules、专业 Skill、难度计划和官方来源 SHA。
2. 基础/强化工作世界、candidate 文件与 teacher-only ledger 的隔离方式。
3. Task Miner、Truth Reconstructor、Judge 校准与 Solver 的盲区。
4. matched task、交付合同、Decision Matrix 和 paired review 的执行边界。

任何后续工作都不得重跑或手改 R10.9 的 world、task、Solver 交付或 paired review。当前不得扩十题、提升候选难度 Skill、训练或发布；如继续研究，应建立单独的 evaluator 稳定性实验，而不是反复调整同一题直到两位 Judge 一致。

R10.10 已获独立私有上传授权，允许把冻结 R10.9 任务、监督材料和 8 份 Solver 交付上传给指定 Judge。执行顺序固定为：文档提交 → Evaluator V2 实现 → R10 开发集最多三版迭代 → 一次留出验证 → 公开 GDPval Gold 子集校准。不得在查看留出结果后继续调参。

模型执行边界：GPT-5.6 Sol Solver仅使用 `none`；GPT Judge最多 `medium`，优先 Terra；DeepSeek V4 Pro使用 `max`，V4 Flash使用 `high`；Luna `medium` 只能按预设条件整批启用。Gemini 不是必需依赖。Tuzi若被使用，必须先通过公开探针并形成独立 transport campaign，结果不得与官方栈混合。

R10.10 可以在开发集上最多修订三版 evaluator，但每版只能修复一个已结构化归因的共性问题：重大错误边界、展示位置效应或客观/专业得分漂移。不得修改任务、Teacher Truth、原 rubric、Solver交付或专业事实。基础设施/结构错误可同输入补跑一次；低分和结论不理想不能重抽。

## Closeout

### R10.10 GDPval 恢复与评分入口

- 用户已将当前评分收缩为小样本诊断。原后台控制器已停止派发；仅允许收回已经启动的远端评分，禁止直接重启旧 `continue_after_solvers.ps1` 或全量 `judge` 命令。原 scope/receipt 与完成评分保持不变，缩减记录保存在 run root 的 `scope_reduction.json`。后续如需额外样本，先固定具体子集，不默认恢复 60 次队列。
- 最新批准的后续子集为三道开发题、九份单独主评与三份固定抽查。使用新的单份评分入口和 scope；不得调用旧全量 judge/aggregate。每项一次实质评分，最多一次格式/传输补跑且全局最多两次；不能重试仍活跃的远端 Agent。排名只使用九份 DeepSeek 主评分，Terra 抽查不加权混入。无新环境漂移时不重复 provider 探针。
- `Test/run_r10_gdpval_validation.py solve` 只承接原 Solver campaign；已开始项不得再次调用 Agent。
- 本机控制器中断但远端已经正常结束时，先下载白名单回传目录；`recover-solver` 校验原输入、正常终态、交付可打开性后仅导入结果，保存原 running 状态，不伪造退出码或耗时。
- 全部 Solver 状态落盘后，使用独立 run root 执行 `judge --solver-run-root <冻结Solver运行目录>`。新 scope 绑定原 receipt、输出 SHA 和修复后的评分协议；旧自动续跑脚本不得直接在 Solver run root 启动评分。
- 每个 pair 只进行一次实质评分；正常结束但空/非法/schema 不完整输出可原输入补跑一次。无正常终态不是格式失败，不自动再启动 Agent。
- 六组 sentinel 额外执行主要 Judge 反向顺序与次要 Judge 原顺序；位置一致率和 Judge 一致率分别计算。不得根据结果重新挑选 sentinel。
- 当前控制器运行在本机、Agent 运行在服务器；本机关机后不能保证队列继续调度。仅“已启动的远端 Agent 可完成”不等于“整批已在服务器自主运行”。

每次 R10 切片结束时，更新《项目概要》中的当前状态，将细节报告写入 `artifacts/`，并在 workstream 关闭后归档其计划。不得把运行记录不断追加到本 runbook。
