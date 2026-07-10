# Milestone F 财务审计候选任务正式生产

> 状态：`active / wave_1_remediation`
>
> 项目级状态源：[项目概要](../../项目概要.md)

本工作流先生产、后评测、再讨论训练。目标是在服务器上从公开网页开始，经 Serper 收集、DeepSeek official skill extraction、campaign scratch registry、Pipeline B、verifier 和 production QA，形成 60 个 candidate-ready 财务审计任务。生产分为 `5 + 15 + 20 + 20` 四波；第一波必须经过逐题工程审查后才允许扩产。

## Wave 1 原始证据

原始 Wave 1 已在候选 release `milestone-f-data-production-1d7d6e7` 上完成：5 个主题分别取得 `2/3/3/3/3` 个来源，DeepSeek 接受 30 个 skills，其中 20 个 sample-ready；自动链路报告 `5/5 candidate-ready`、`5/5 verifier pass`、`5/5 export compatible`、QA blocked 为 0，canonical registry 未改变，也没有进入 eval preparation 或外部评测。

逐题审查否决了该波次。主要原因是：多个案例复用了完全相同的参考文件；通用字段不能支持 prompt 中所选财务技能；GoldenRun 只是流程骨架而非可重算答案；XLSX 列宽和信息设计不足；DOCX 缺少标准页尺寸。候选 release 未激活，Wave 2 未启动，原始 manifest 与任务包保留为失败证据。

## Wave 1B 修复边界

修复只对 `finance_production_v1` 生效，不改变默认生成链：

- fan-in 使用银行流水与现金账匹配；
- cross-check 使用采购订单、收货和发票三单匹配；
- policy 使用费用交易与候选可见费用政策；
- 每个案例使用确定性但不同的数据，生成可重算 answer key；
- XLSX 增加表头、筛选、冻结窗格、列宽和金额格式；DOCX 增加标准页尺寸；
- campaign 增加 reference-file SHA-256 重复阻塞门禁。

本地三案例探针已恢复为 `3/3 candidate-ready`。下一步是构建新的候选 release，在服务器复用既有 Wave 1 scratch registry 运行 Wave 1B，重新完成五题视觉与逻辑审查；通过前不得激活或生产后续 55 题。

## 安全边界

- 只向 DeepSeek 发送公开 source prompt package；
- GDPVal、私有材料和生成后的任务包不得外发；
- 不执行外部模型答题、grader 或 rw-task eval preparation；
- 服务器仅挂载 DeepSeek key 和只含 `SERPER_API_KEY` 的 provider env，不上传完整 `.env`。
