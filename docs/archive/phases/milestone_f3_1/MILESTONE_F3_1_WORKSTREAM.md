# Milestone F3.1 Workstream

> 生命周期：`historical / closed`

本 workstream 的范围是：以显式 backup key 和 `gpt-5.6-sol` 建立低成本 secondary review；压缩复审 payload；增加 ¥10 原子预算门禁；修订三单匹配的候选规则、resolver、teacher truth 与 fact rubric；随后执行公开 fixture、8题校准，并仅在通过时执行五题 smoke。

冻结边界：不使用 primary key 或 `gpt-5.4-pro`，不调用 solver/grader，不审计全部60题，不进入 SFT/RL，不切换服务器 current release。

执行因 DeepSeek 主审连续两次 requirement 覆盖不完整而按合同停止。详细证据与最终判断见 `MILESTONE_F3_1_LOW_COST_RECALIBRATION.md`。
