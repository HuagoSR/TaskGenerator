# Milestone F 财务审计候选任务正式生产

> 状态：`active / in_progress`
>
> 项目级状态源：[`../../项目概要.md`](../../项目概要.md)

本工作流先生产、后评测、再讨论训练。目标是在服务器上从公开网页开始，经 Serper 收集、DeepSeek official skill extraction、scratch registry、Pipeline B、verifier 和 production QA，形成 60 个 candidate-ready 财务审计任务。

生产分为 `5 + 15 + 20 + 20` 四波。第一波 5 题全程监管并逐题检查 prompt、候选可见文件、GoldenRun、rubric、verifier 和交付物一致性；未通过不得扩大生产。

安全边界：

- 只向 DeepSeek 发送公开 source prompt package；
- GDPVal、私有材料和生成后的任务包不得外发；
- 不执行外部模型答题、grader 评测或 rw-task eval preparation；
- canonical registry 不变，新技能只进入 campaign scratch registry；
- 服务器只挂载独立 DeepSeek key 和仅含 `SERPER_API_KEY` 的最小 provider env，不上传完整 `.env`。

权威 campaign contract 为 `SkillRegistry/v3_finance_production_campaign.experimental.json`。运行产物位于 ignored 的 `artifacts/finance_production_runs/` 或服务器 `/data/runs/finance_audit_production_01/`。完成后本文与 completion handoff 一并迁入 `docs/archive/phases/milestone_f/`。
