# R10 Rubric 编译验证 Runbook

> 状态：active；宏观状态见 [项目概要](../../项目概要.md)，实现顺序见 [优化计划](../architecture/pipeline_reconstruction_optimization_plan.md)。

## 冻结边界

- 精简 GDPval 评分已完成 12/12，不恢复旧 60 次队列或重新评分留出题。
- 本轮只编译 R10.9 两道 baseline 开发题的新 rubric，不运行 Solver 或评分。
- 原题干、candidate、Teacher Truth、矩阵与旧 rubric 前后 SHA 不变；发现事实问题只报告。

## 执行

- 文档提交 → 实现与定向/完整测试、diff/secret 检查 → 实现提交 → 外部执行。
- 沿用 huago-cone current 镜像与官方栈；Terra medium 生成两次，DeepSeek V4 Pro max 独立审查两次。
- 新 scope 绑定开发 task、白名单输入树、源码、镜像及模型，首次调用前消费用户本轮授权 receipt。
- 每项正常一次；仅明确传输/结构失败可同输入补跑一次，全批最多两次。running 不自动重启，语义不通过不重抽。
- 不上传旧 Solver 答案、成绩、排名、GDPval 或留出内容。
- 新 rubric、审查、中文材料和脱敏诊断全部留在 ignored artifacts。
- 无环境漂移不重复探针；有漂移停止，不增加适配层。

## 安全

密钥和认证不进入命令、镜像、日志或产物；复用受限 Docker 与现有 secret 注入。Test/v2_outputs 保持 no-touch。不构建、部署或激活 release，不清理无关项目，既有发布门槛 95 GiB 不变。不训练、不公开题库、不更新 Registry 或默认模型。

## 停止点

入口为 `Test/run_r10_rubric_compilation.py run/status --run-root <ignored路径> --run-id <新ID>`。状态读取不调用模型。

仅控制器格式/引用缺陷可离线接纳已有正常终态输出：`--import-completed-author`、`--import-completed-pair`、`--import-completed-drafts` 分别对应首份生成、首题完整结果、两份生成及首题审查。它们是本次固定调用序列的有界恢复，不是通用重跑入口：必须核验原 receipt、输入、模型、镜像、正常事件、原始输出和完整来源链，并继承全部已消耗尝试。原 run 不改写，已开始项不重跑，不能挑选第二份更满意的结论。最终模式仅执行未开始的采购审查。

两份 rubric 和独立审查完成后提供中文检查材料、提交状态。存在题干/监督/来源冲突时明确标记，不伪造通过。只作生成侧初步验证，不是专家证据或 evaluator_validated。

当前执行已收尾，禁止继续启动新的生成、审查或评分。模型审查结论与额外文字复核观察分别保留，不能为消除分歧改写原始 rubric 或追加复审。下一步先由用户查看检查材料，再确定新的编译实验。
