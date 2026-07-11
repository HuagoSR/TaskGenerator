# Milestone F 四模型差异评测

> 状态：`pilot_completed / thirty_task_extension_authorized`

对财务审计生产任务进行分阶段真实执行评测。solver 固定为 `gpt-4o-mini`、`gemini-3.1-pro-preview`、DeepSeek official `deepseek-v4-pro` 和 `claude-sonnet-4-6`，主 grader 为 `gpt-5.4-pro`，抽审 grader 为 `claude-opus-4-6`。

6 题 Pilot 已完成：`24/24 solver completed`、`24/24 primary graded`、`24/24 audit graded`，无重试、无 OOM，总耗时约 2 小时 27 分钟。主 grader 平均分依次为 `gpt-4o-mini=0.180`、`gemini-3.1-pro-preview=0.360`、`deepseek-v4-pro=0.392`、`claude-sonnet-4-6=0.478`。六题中 5 题为 `mixed_signal`、1 题为 `too_hard`，4/6 题存在 grader instability，因此评分需继续抽审，不得当作绝对质量真值。

已授权将 cohort 扩展为总计 30 题，三个 motif 各 10 题。现有 6 题证据只读复用，新增 24 题产生 96 份 solver 输出，全部主评；每题固定抽审一份，分差超过 0.20 或 0.60 通过线判断不一致时补齐该题复评。扩展完成后停止在 `thirty_task_eval_completed_awaiting_research_interpretation`，不自动评测剩余 30 题。

任务包可以发送给本 campaign 指定 provider，但 solver 输入不得包含 GoldenRun、rubric、training annotation 或 answer key。继续复用服务器上的 Tuzi、DeepSeek 和 E2B 最小 secret，不上传完整 `.env`。本评测只是任务区分度和可执行性证据，不证明训练价值或 benchmark 权威性。
