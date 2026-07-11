# Milestone F 四模型差异评测

> 状态：`pilot_implementation_ready / awaiting_e2b_secret_authorization`

对 60 个财务审计任务进行分阶段真实执行评测。首阶段只运行 6 题 × 4 模型；solver 固定为 `gpt-4o-mini`、`gemini-3.1-pro-preview`、DeepSeek official `deepseek-v4-pro` 和 `claude-sonnet-4-6`，主 grader 为 `gpt-5.4-pro`，抽审 grader 为 `claude-opus-4-6`。

Pilot 完成后固定停止在 `pilot_completed_awaiting_cost_decision`，不自动运行剩余 54 题。任务包可以发送给本 campaign 指定 provider，但 solver 输入不得包含 GoldenRun、rubric、training annotation 或 answer key。

现有 rw-task 文件执行依赖 E2B sandbox。服务器启动前除 Tuzi 和 DeepSeek secret 外，还需要经用户明确允许安装最小 `E2B_API_KEY` secret；不上传完整 `.env`。
