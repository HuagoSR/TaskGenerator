# TaskGenerator

TaskGenerator 研究如何以可复现的方法构造真实、多文件、具有实质职业判断且可公平评分的职业任务。它不是模型排行榜、训练系统或公开题库。

## 从这里开始

- [项目概要](项目概要.md) 是目标、当前证据、限制与下一方向的唯一事实源。
- [文档索引](docs/README.md) 说明架构、合同、研究问题与运行边界的阅读顺序。
- [项目规则](AGENTS.md) 规定输入隔离、产物处理、评分暂停与外部运行授权。

实现位于 `src/task_generator/`，阶段入口位于 `Test/`。候选包保持 GDPval 形状：`dataset_row.json`、`reference_files/` 与 `deliverable_files/`。教师依据、计算包、模型响应和运行日志与候选输入隔离。

## 当前边界

仓库包含可复用的生产 Harness、候选任务编辑、原子 rubric、计算重放、质量诊断以及仅供兼容性观察的 legacy rw-task 适配器。它们的结构测试不等同于职业语义、评分公平性或规模化生产已获验证；结论与已关闭 scope 见《项目概要》。

`artifacts/`、`Test/v2_outputs/`、凭据、模型响应和生成任务包均为本机受忽略证据，不会随仓库发布。GDPval 只用于 evaluator calibration，其任务、文件、答案和 rubric 不进入生成或训练输入。

## 开发与运行

代码变更应运行定向测试及 `pytest tests`，并检查差异、秘密和文档链接。所有模型调用、Solver 或评分运行都需要新的、明确绑定输入、模型、环境与预算的授权 scope；已关闭 scope 的剩余额度不能复用。
