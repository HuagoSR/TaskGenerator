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

如果首次审查已正常结束但仅序列化/控制器引用检查失败，误触发的第二次尝试已停止且未产生正常终态，可用 `--import-completed-pair <原run>` 离线接纳首题首次生成与首次审查。该模式仅允许这一个固定首题，验证完整来源链、原输入、正常事件和停止证明；三个已消耗尝试全部计入新 scope 上限，原 run 不改写，不读取或挑选第二份审查结论。

入口为 `Test/run_r10_rubric_compilation.py run/status --run-root <ignored路径> --run-id <新ID>`。首项已正常结束但因控制器准入缺陷未接纳时，可显式使用 `--import-completed-author <原run>`：只允许唯一的首个 author，校验 receipt、任务/输入/模型/镜像、正常终态与原输出；新 scope 绑定导入证明并继承一次调用计数。旧 run 不改写，running 或其余已开始项不允许重跑。

两份 rubric 和独立审查完成后提供中文检查材料、提交状态。存在题干/监督/来源冲突时明确标记，不伪造通过。只作生成侧初步验证，不是专家证据或 evaluator_validated。
