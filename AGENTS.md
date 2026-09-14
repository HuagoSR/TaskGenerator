# TaskGenerator Project Instructions

## Read First

1. [项目概要.md](项目概要.md)：唯一宏观状态源，包含当前证据、限制与下一方向。
2. [docs/README.md](docs/README.md)：文档职责与生命周期。
3. [System architecture](docs/architecture/system_architecture.md)：当前结构与组件边界。
4. [Contracts](docs/architecture/global_interface_contracts.md)：接口索引；字段定义以代码为准。
5. [Production MVP](docs/architecture/production_mvp_definition.md)：生产与证据语义。
6. [Research problem](docs/architecture/pipeline_reconstruction_problem_statement.md)：研究问题与非目标。
7. [Next direction](docs/architecture/pipeline_reconstruction_optimization_plan.md)：当前方法方向。
8. [Runbook](docs/operations/pipeline_reconstruction_runbook.md)：执行、停止与恢复边界。

历史文档和 ignored artifacts 不覆盖《项目概要》的当前结论。不要在多个活跃文档重复 campaign 状态。

## Goal and Current Method

项目制造真实、有自然复杂度、可解且可公平评分的多文件职业任务。评测服务于任务生成研究，不以建设排行榜为目标。

- 所有候选包保持 GDPval 形状：`dataset_row.json`、`reference_files/`、`deliverable_files/`；GDPval 内容仅用于 evaluator calibration，不进入生成或调参输入。
- S1 是优先开发路径：一个强作者读取完整生成合同与适用 Professional Skill，可使用工具和 self-check，再进入共同有限准入。历史多阶段 P 只作研究参照。
- World-First 先产生业务材料，再挖掘任务。公开 Work Seed/规则只描述职业触发与方法，不提供组织事实或答案。
- 通用性是硬约束：个体任务用于提炼可复用规则，不围绕单题反复修补以制造理想结果。
- 不建设通用业务本体、evidence-graph runtime、额外角色链或自动“分数→生成器”优化器；RL、训练和公开发布不在当前范围。

## Evidence, Rubric and Quality Rules

- 候选文件、教师监督/rubric、计算依据和运行证据必须隔离。作者意图、编辑声明、Solver 答案和 grader 评价都不是候选义务来源。
- 新任务使用版本化原子 rubric：每项只检查一个独立可观察成果，评分条件、适用边界、容差和合理替代表达必须自洽；正式 rubric 是唯一评分权威。
- 关键职业结果只是教师侧的 rubric 诊断映射，不是第二套分数、隐含义务或固定模板。
- 行为核对先看 evidence state、unresolved matter、匹配 follow-up 和后续职业行为，再判断 disposition 表达是否合理；不因未复述内部推理或特定标签直接判失败。
- 全格式检查必须覆盖 PDF、CSV、XLSX、DOCX、Markdown 等所有 candidate-visible 内容，包括行宽、公式/重算、打开性、视觉可读性和答案泄漏。
- 记录来源必须具有可信的 producer、record time、query scope、版本和 custody。受控实验的结构对称不能凌驾于业务因果真实性。
- 结构通过、专业正确、可解性、文件交付、正式评分和模型行为必须分开报告。失败位置、成本和人工介入均计入结果。

## Architecture and Repository

- 实现：`src/task_generator/`；研究/阶段 runner：`Test/`。
- 架构与操作：`docs/architecture/`、`docs/operations/`；研究记录：`docs/research/`；历史：`docs/archive/`。
- Professional Skills：`.agents/skills/r10/`；目录：`data/r10/professional_skills/catalog.json`。
- 生成任务、provider 响应、日志和 receipts 只放 ignored `artifacts/`；不要在仓库根新增实验产物。
- `SkillRegistry/` 对 R10 只读；`Test/v2_outputs/` 除非明确重开，否则不触碰。
- 公开 `taskgen` CLI 只读、离线，不得导入 `Test/` runner、接收凭据/远端配置、创建执行 scope 或暗示 preview 会运行模型。
- 活跃文档保持简短且职责单一；详细历史进归档或 Git 历史，不复制字段 schema、运行日志和 campaign 流水账。

## Execution and Recovery Safety

- 没有当前用户明确授权时，不启动作者、Solver、Judge、Grader、外部模型、SSH 或新实验。每次外部执行必须新建输入/模型/环境/预算绑定 scope 和 receipt；旧 scope、剩余额度或历史方向不构成授权。
- 调用前执行适用的 readiness、identity、fingerprint 和环境检查。模型目录可见、历史成功或一次 preflight 不证明整个运行窗口持续可用。
- 保留首次失败、原始输入、响应、日志和 receipt。不得覆盖终态 scope、静默重跑、重抽低分结果、改变冻结输入或把技术恢复写成首次成功。
- 可恢复的本地控制器问题在新 scope 中绑定父证据；先用真实失败/成功产物离线回归修复，再继续尚未取得有效结果的项。Provider 502/503 等失败即使无 usage 也计入尝试。
- 不评分无效交付。logger 展示截断本身不证明模型上下文截断；必须沿实际代码与工具命令确认。
- 使用 `taskgenerator` conda 环境。手工编辑使用 `apply_patch`；保留无关 dirty changes，禁止 destructive reset。
- 不打印、提交或打包 `.env`、`deepseek-key.txt`、API key、token 或认证内容。提交前检查 diff、秘密、链接、状态和测试证据；只暂存本次文件。
- 不自动扩题、部署、发布、训练、修改 registry、切换默认模型或 push。提交/push 必须来自当前用户授权；禁止 force-push，远端分歧先 fetch 并非破坏性合并。
