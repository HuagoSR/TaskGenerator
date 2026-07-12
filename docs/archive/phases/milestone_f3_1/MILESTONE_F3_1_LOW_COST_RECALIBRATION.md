# Milestone F3.1 低成本复审与三单匹配修订报告

> 状态：`historical / authoritative for Milestone F3.1 closure`
> 结论：`f3_1_semantic_gate_hold`

## 本轮完成的改进

- 新增显式 `backup` key slot，只读取 `OPENAI_API_KEY_BACKUP`，不回退到 primary key。
- 二次复审固定为 Tuzi `gpt-5.6-sol`、1200 tokens 和 ¥10 硬预算。
- 新增原子成本账本，并把复审改为 claim/finding 定向投影和按问题 scope 调用。
- 三单匹配明确两种数量差异、价格差异、潜在重复业务键和状态优先级；候选规则、resolver 和确定性答案同步更新。
- Secondary 合同限制为最多6个判断、每条4个 locator、240字符 rationale。

## 公开 fixture 预检

正式准入证据位于 ignored `artifacts/milestone_f3_1/provider_preflight_02/`：

```text
gpt-5.6-sol available = true
compact blind + teacher repeats = 2 / 2 passed
provider calls ledgered = 4 / 4
max prompt/completion tokens = 949 / 542
frozen-price cost = ¥0.051811
backup-key artifact hits = 0
```

`provider_preflight_01` 因本地命令超时与 resume 并发造成4份输出只有3条账本记录，作为失败证据保留，不用于准入。

## 新任务与真实校准

新生成8个 V2 修复任务，均为 `contract verified + candidate-ready`；三个 cross-check 使用新规则。新旧逻辑任务包指纹均不同，因此未复用旧 DeepSeek 证据。

真实主审第一题时，DeepSeek official `deepseek-v4-pro` 的 candidate-blind review 连续两次未覆盖全部 requirement，均为 `Provider contract violation: requirement review coverage mismatch`。按冻结合同最多重试一次，第二次失败后立即停止；没有第三次调用、没有用 secondary 替代 primary、没有启动其余任务或五题 smoke。

旧负例 #2、#13、#18 的只读 F3 证据仍为3/3 non-pass，但未把历史结果冒充为新 cohort 的完整校准。

## 成本、安全与结论

- 干净预检成本 ¥0.051811；失败预检账本另记 ¥0.027666，均远低于 ¥10。
- 项目任务阶段没有发生 Tuzi secondary 调用。
- artifacts 未命中备用 key；`.env`、任务包和 provider 原始响应均不提交。

```text
decision = f3_1_semantic_gate_hold
low_cost_secondary_contract = validated
three_way_match_contract = revised
eight_task_real_recalibration = incomplete
five_task_external_smoke = not_started
default_chain_promotion = false
server_current_release_changed = false
rl_or_sft_authorized = false
```

低成本复审与三单匹配合同已经解阻；新的阻塞是 DeepSeek 多 requirement 主审覆盖稳定性。下一轮应先设计逐 requirement 分片或覆盖补审机制，再申请独立 campaign，不能在本轮追加第三次调用。
