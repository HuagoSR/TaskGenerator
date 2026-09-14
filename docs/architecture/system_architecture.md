# 系统架构

> 状态：`active`；更新：2026-09-15。
> 本文说明当前组件和职责，不记录 campaign 结果；宏观状态见[项目概要](../../项目概要.md)。

## 1. 总体数据流

```text
Public Work Seed / Rules + Professional Skill
                    ↓
             World-First authoring
                    ↓
 business world → candidate task/materials
                    ├─ candidate package (Solver-visible)
                    └─ teacher supervision / rubric / calculations
                    ↓
       offline structural + professional admission
                    ↓
          frozen behavioral evaluation (optional)
                    ↓
       native artifact QA + diagnostic grading
```

S1 是当前优先运行路径：一个强作者在同一会话中读取完整生成合同与适用 Skill，使用工具和 self-check，提交后进入共同准入。历史多阶段 P 保留为研究参照，不是默认生产依赖。

## 2. 分层职责

| 层 | 主要职责 | 不负责 |
|---|---|---|
| Public seed/rules | 职业触发、公开方法和边界 | 组织事实、异常答案 |
| Professional Skill | 来源支持的专业生成规则 | 固定题型或业务世界模板 |
| World/records | 业务实体、事件、producer、时点、query scope、custody | Rubric 标签和预期处置 |
| Candidate task | 题干、reference、DeliverableContract | 教师答案、锚点、评分脚本 |
| Teacher package | 监督、正式 rubric、计算依据、关键结果映射 | 向 Solver 增加候选不可见义务 |
| Admission | 身份、隔离、全格式、因果、可解性、公平性和重放检查 | 以结构通过替代专业判断 |
| Evaluation | 冻结输入上的独立 Solver、文件 QA 和有限诊断 | 自动生产反馈或模型排行榜 |
| Artifacts | scope、receipt、日志、原始响应和哈希 | 当前宏观状态管理 |

## 3. 核心隔离

候选包保持 GDPval 形状：

```text
case/
  dataset_row.json
  reference_files/
  deliverable_files/
```

Solver 只能看到真实题干、reference 和提交说明。正式 rubric、教师监督、计算期望、作者上下文、编辑记录和历史答案留在教师/运行侧。输入身份由 task ID、prompt hash、文件清单和输入树共同绑定。

生成与盲解可以使用相同候选输入，但 producer intent、试做答案和 grader 评价都不是任务义务来源。GDPval held-out 内容只用于 evaluator calibration，不能进入生成或提示调优。

## 4. Rubric 与诊断映射

新任务使用版本化原子 rubric：一个条目对应一个独立可观察成果，包含权重、满分条件、适用边界、容差、候选义务来源和合理替代表达。代码检查字段、引用、覆盖和分数一致性；专业语义仍由人工/Agent 审查。

关键职业结果是教师侧的高价值成果摘要，可映射一个或多个正式条目，但不形成第二套评分。它们用于观察 evidence state、unresolved matter、follow-up 和局部职业行为，不要求模型外化不必要的内部推理。

## 5. 准入与原生文件 QA

机械检查覆盖安全路径、文件存在、引用、候选/教师隔离、CSV/TSV 行宽、计算重放和 score consistency。格式工具负责 PDF/DOCX/XLSX 的打开、提取、公式重算、错误扫描和渲染。

程序能证明“被检查的结构成立”，不能证明记录来源真实、专业口径正确、rubric 语义原子或任务达到专家质量。全格式检查与专业审查共同决定有限准入。

## 6. 行为评测

Controlled Solver 使用冻结 Stirrup/E2B harness：每个 task/model 独立会话，固定候选输入、工具循环、sandbox 和交付收集。昂贵调用前执行 route/tool/Judge 预检和逐会话 identity gate；provider 与控制器失败单独记录。

评测输出分四层：

1. 结构/文件交付是否有效；
2. 冻结关键职业结果是否满足；
3. 正式原子 rubric（若获得独立授权执行）；
4. legacy rw-task diagnostic 部分分。

四层不得合并。Legacy grader 的文本提取和高分复审可能漏掉原生文件公式或布局问题，文件 QA 始终保留独立权威。

## 7. 公开只读 CLI

`src/task_generator/cli/main.py` 提供 `taskgen`，只读取本地版本化 JSON、GDPval-shaped 包、R10 scope 和有限诊断投影。它不导入 `Test/` runner、不读取凭据、不联网、不创建 scope、不启动模型；显式 report 只写入用户指定的新派生路径。

## 8. 实现与历史边界

- 核心实现：`src/task_generator/`；研究 runner：`Test/`；代码拥有字段定义。
- Professional Skills：`.agents/skills/r10/`；历史 Registry 对 R10 只读。
- 历史 Scenario Bible、Rubric V2、多阶段 P、pairwise/holistic evaluator 和旧 harness 保持可读，但不构成当前默认路径或执行授权。
- 不新增通用业务本体、evidence-graph runtime、自动评分反馈系统或远端部署假设。
- 运行、停止与恢复遵循[运行手册](../operations/pipeline_reconstruction_runbook.md)；接口见[合同索引](global_interface_contracts.md)。
