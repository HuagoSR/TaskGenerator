# Milestone F 四模型差异评测

> 状态：`thirty_task_eval_completed_awaiting_research_interpretation`

对财务审计生产任务进行分阶段真实执行评测。solver 固定为 `gpt-4o-mini`、`gemini-3.1-pro-preview`、DeepSeek official `deepseek-v4-pro` 和 `claude-sonnet-4-6`，主 grader 为 `gpt-5.4-pro`，抽审 grader 为 `claude-opus-4-6`。

6 题 Pilot 已完成：`24/24 solver completed`、`24/24 primary graded`、`24/24 audit graded`，无重试、无 OOM，总耗时约 2 小时 27 分钟。主 grader 平均分依次为 `gpt-4o-mini=0.180`、`gemini-3.1-pro-preview=0.360`、`deepseek-v4-pro=0.392`、`claude-sonnet-4-6=0.478`。六题中 5 题为 `mixed_signal`、1 题为 `too_hard`，4/6 题存在 grader instability，因此评分需继续抽审，不得当作绝对质量真值。

扩展 cohort 已完成：总计 30 题，三个 motif 各 10 题，selection SHA-256 为 `50065110e35916a4835fe421a0764064315eabd17043935947ca000d5a17d7c9`。原 Pilot 24 条证据经指纹校验只读导入，新增 96 个 solver 进程全部正常返回，无重试、无 provider 故障、无 OOM。`gpt-4o-mini` 其中 4 次没有产生可评分交付物，因此有效交付物为 116/120，这 4 次保留为真实 `non_delivery`，不视为技术调用失败。

116 份有效交付物均完成 `gpt-5.4-pro` 主评；原 Pilot 双评加新 cohort 固定抽审/异常扩审共得到 63 份 `claude-opus-4-6` 复评。6 个新任务触发异常扩审，最终 10/30 题标记为 `grader_unstable`。全程容器 wall time 约 11 小时 23 分钟：solver 约 7 小时 8 分钟，grading 约 4 小时 14 分钟。

## 30 题核心结果

| 模型 | 有效交付 | 平均分 | 中位数 |
| --- | ---: | ---: | ---: |
| `gpt-4o-mini` | 26/30 | 0.202 | 0.176 |
| `gemini-3.1-pro-preview` | 30/30 | 0.400 | 0.405 |
| `deepseek-v4-pro` | 30/30 | 0.438 | 0.459 |
| `claude-sonnet-4-6` | 30/30 | 0.459 | 0.486 |

在 26 个四模型完整 panel 中，标签为 `18 mixed_signal / 5 too_hard / 2 compressed / 1 informative / 0 too_easy`，没有 rank inversion。排除 grader instability 后剩余 17 个稳定且完整的 panel：`10 mixed_signal / 4 too_hard / 2 compressed / 1 informative`。这表明任务整体确实能分离弱模型与较强模型，但当前分数普遍偏低，且 grader 不稳定率较高，不适合宣称这 30 题已是成熟 benchmark 或已证明训练价值。

DeepSeek 新增 24 次 solver 的事前线性估算为 3.52 RMB，实际费用仍以用户账户为准；Tuzi 新增调用为 72 次 solver、92 次主评和 39 次复评，费用不可得，保持 `unknown`。评测已按合同停止，不继续剩余 30 题，不切换服务器 `current` release。

任务包可以发送给本 campaign 指定 provider，但 solver 输入不得包含 GoldenRun、rubric、training annotation 或 answer key。继续复用服务器上的 Tuzi、DeepSeek 和 E2B 最小 secret，不上传完整 `.env`。本评测只是任务区分度和可执行性证据，不证明训练价值或 benchmark 权威性。
