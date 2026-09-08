# 接口合同索引

> 状态：reference；核对日期：2026-09-09。
> 只说明接口职责和兼容边界。字段以代码为准，运行结果见[项目概要](../../项目概要.md)。

## 生成侧 Rubric V2

实现：[rubric_compiler_v2.py](../../src/task_generator/planning/rubric_compiler_v2.py)。

| 合同 | 职责 |
| --- | --- |
| `TaskSpecificRubricV2` | 独立版本的任务评分标准，一个专业判断可对应多个条目。 |
| `TaskSpecificRubricItemV2` | 要求、整数满分、完整得分边界、要求依据、证据路径、适用条件、等价表达与核验说明。 |
| `RubricCompilationV2` | 返回新 rubric，或报告 upstream_issue，不补造事实掩盖上游问题。 |
| `RubricAuthorReviewV2` | 审查要求一致性、重复计分、证据、条件例外、等价表达、核验范围及监督一致性；不是给 Solver 打分。 |

结构与引用规则：

- 专业条目覆盖既有 Decision Matrix；ID 唯一，每个可得整数都有边界描述，无固定条目数量。
- 要求依据只能引用候选可见题干、交付合同或参考材料，不能由隐藏 Teacher Truth 创设义务。
- 明确的交付结构要求可用 `deliverable_structure` 组，依据只来自题干/合同。核验目标可为合同精确声明的未来交付路径，不要求出题时该文件存在。
- 独立审查可额外引用新 rubric、Teacher Truth 和 Decision Matrix；这不改变作者的要求依据边界。
- 程序检查结构、路径、引用和计分；专业合理性由 Agent 审查。未来计分为逐项给分、程序求和，不另加整体偏好或隐性总分否决。
- JSON 规范化仅限已实现的外层说明剥离和说明字段引号转义，保留原始记录与证明；不修改 ID、分值、结论或补全截断内容。

V2 是独立派生物，不覆盖旧 rubric，也不因审查通过而自动启用评分。

## 独立逐项评分合同

实现：[independent_rubric_grader.py](../../src/task_generator/evaluation/independent_rubric_grader.py)。

| 合同 | 职责 |
| --- | --- |
| `FrozenRubricItemV1` | 固定 item ID、整数满分和原 criterion；不改写 rubric 语义。 |
| `IndependentRubricGradeDraftV1` | Judge 仅返回材料状态与每项整数得分、适用性、证据路径、理由。 |
| `IndependentRubricGradeV1` | 控制器补入 item 满分，重算总分/满分/归一化分，并绑定输入、rubric、交付和评审哈希。 |

每个 item 必须且只能出现一次，得分在 `0..max_score`；`not_triggered` 不得失分，`unresolved` 或材料不足不产生可比较总分。证据只能定位到候选可见题干、参考文件或匿名交付。GDPval adapter 保留原整数满分；R10.9 V1 adapter 仅把精确百分比权重映射为 100 分制，不改原 criterion。GDPval 导出仍使用 `dataset_row.json`、`reference_files/`、`deliverable_files/` 与原 rubric；适配副本不修改冻结包。

G2 的 Agent-native 扩展实现见 [agent_rubric_grader.py](../../src/task_generator/evaluation/agent_rubric_grader.py)：

| 合同 | 职责 |
| --- | --- |
| `EvidenceRefV1` | Judge 返回结构化文件、sheet、连续 A1 范围与 support/defect 角色，不自行拼接 locator。 |
| `AgentRubricGradeDraftV1` | 逐 item 返回 satisfaction、核验范围、整数分、结构化证据、support、defects 与理由。 |
| `CanonicalCitationV1` | 控制器验证路径、sheet、非空范围和文件哈希后生成稳定 citation ID 与规范 locator。 |

XLSX 证据服务保留原值、公式、重算值、格式和循环诊断；只作事实层，不直接决定专业得分。

`AgentRubricGradeDraftV2` 将 `coverage` 与 `verification_methods` 分开，已通过离线测试，未完成真实评分验证。V1 保留冻结结果读取兼容。当前 V2 仍沿用量化满分强制候选/参考范围的机械规则；本次不修复。合法引用、方法和覆盖标签不等于专业核验充分。

评分执行暂停；合同存在不代表可启动实验，宏观结果见概要，操作边界见 Runbook。

## Stirrup 校准合同

实现：[stirrup_calibration.py](../../src/task_generator/evaluation/stirrup_calibration.py)。

| 合同 | 职责 |
| --- | --- |
| `StirrupPreflightResultV1` | 记录固定模型的预检状态、是否进入语义阶段、首次错误及恢复关系。 |
| `FrozenStirrupPanelV1` | 仅在三档均通过后冻结实际模型；回退映射固定且正式运行前不可再变。 |
| `StirrupSolverAttemptV1` | 记录一次 Solver 的阶段边界、turn 数、交付状态与错误分类。 |
| `StirrupSolverReceiptV1` | 绑定任务、solver/provider、Stirrup/E2B 版本、template build、输入与交付哈希及首次失败链。 |
| `ShadowDownwardAuditDiagnosticV1` | 单独保存旧式降分诊断；显式引用主评分，但不能修改 `IndependentRubricGradeV1`。 |

R10.12 固定 100-turn 上限，只有首个语义 turn 前的 E2B 创建、传输或路由故障可技术恢复；无效交付不得进入 strict 语义评分。provider 单次输出上限与 Agent 上下文窗口是两个独立参数；进度记录不得包含密钥或完整 provider 输出。GDPval 交付以 Solver 通过 finish 提交的路径为准，检查数量、文件类型、非空和可打开性；不向 Solver 泄露或强求复制隐藏 reference 文件名。strict 只改变给分证据阈值，不增加 rubric 外义务，最终总分仍由 `IndependentRubricGradeV1` 控制器求和。

R10.12-S1 的补充合同实现见 [stirrup_supplement.py](../../src/task_generator/evaluation/stirrup_supplement.py)：

| 合同 | 职责 |
| --- | --- |
| `StirrupSupplementProtocolProbeV1` | 对固定 Tuzi Chat route 记录至少两轮请求、工具回传、`code_exec`、`finish` 和预检文件闭环。 |
| `FrozenStirrupSupplementPanelV1` | 只允许 `gpt-5.5`、`gpt-5.6-sol`、`glm-5.2`、`gpt-5.4-mini` 四个精确 route，无回退。 |
| `StirrupSupplementSolverReceiptV1` | 绑定补充 session 的 route、Chat 端点、Stirrup/E2B、turn/输出上限、首次尝试及交付哈希。 |
| `TerraTransportDiagnosticReceiptV1` | 绑定一次无重试 Terra transport probe 的环境、输入、请求状态、结构校验与结果哈希。 |
| `StrictGradePacketV1` | 固定 strict 指令、原 rubric、证据根、确定性材料文本和输出 schema，供不同 Judge transport 消费同一匿名输入。 |

补充控制器只记录脱敏请求元数据：requested/response model、response object、端点、Request-ID、usage、请求序号和工具名；不记录密钥、完整响应、工具参数或材料正文。固定使用 `/v1/chat/completions`、`context_window=64000`、`max_completion_tokens=8192`、`max_turns=100`。它不把三档合同扩展成通用 evaluator，也不改变冻结 R10.12 结果。

S1-B receipt 额外绑定脱敏 provider/tool 轨迹哈希、完成请求数和观察到的工具名。grade packet 只存在于 ignored scope；合同不允许用近似 UUID、模型身份或历史成绩修补 Judge 输出。

## 可复用的生产合同

| 层 | 主要合同与实现入口 |
| --- | --- |
| 种子与规则 | `WorkSeedV1`、`ProfessionalRuleSetV1`：职业触发、公开来源、适用规则；见 [scenario_first.py](../../src/task_generator/core/scenario_first.py)。 |
| 专业 Skill | `ProfessionalSkillCatalogEntryV1`：目录元数据；SKILL.md 为知识正文权威。见 [professional_skills.py](../../src/task_generator/substrate/professional_skills.py) 与 [professional_skill_compiler.py](../../src/task_generator/substrate/professional_skill_compiler.py)。 |
| 世界与任务 | `WorldFirstPilotManifestV1`、`ProfessionDifficultyPlanV1`：阶段、身份及难度依据；见 [r10_world_first.py](../../src/task_generator/production/r10_world_first.py)。 |
| 任务编译 | `TaskCompilationOutputV1`、`ScenarioTaskCompilationPlanV1/V2`、`TaskDecisionMatrixV1`：任务、监督、判断点与证据关系；见 [scenario_task_compiler.py](../../src/task_generator/planning/scenario_task_compiler.py)。 |
| 交付 | `DeliverableContractV1`：题干提交说明、预期路径、staging 和交付检查的共同依据。 |
| 准入 | `ScenarioFirstAdmissionReportV1` 及 task admission：来源、隔离、文件、引用、泄漏与可解性检查；静态通过不等于专业有效。 |

## 自主工厂与开发 harness 接口

现有入口为 [run_r10_agent_factory_pilot.py](../../Test/run_r10_agent_factory_pilot.py) 的 prepare / execute / status / stop / report；单题与批次标识互斥。状态、版本父依赖和角色会话校验见 [agent_factory.py](../../src/task_generator/production/agent_factory.py)，工具参数和当轮错误反馈见 [agent_factory_tools.py](../../src/task_generator/production/agent_factory_tools.py)，固定位置与联合预算见 [agent_factory_batch.py](../../src/task_generator/production/agent_factory_batch.py)。这些是现有实现入口，不是新增通用 SDK。

新入口 [run_r10_task_factory_harness.py](../../Test/run_r10_task_factory_harness.py) 提供同名 `prepare / execute / status / stop / report`。默认仍是两个开发位置、32次/8小时总预算；准备时可显式使用`--case procurement`冻结为一个采购位置、16次/4小时，执行时不能改选。协议见 [task_factory_harness.py](../../src/task_generator/production/task_factory_harness.py)：新增只读`devsolve`角色、一次上游返工、开发试做依赖和可复算依据合同；旧入口默认协议不变。子scope绑定所属批次，不能绕过批次锁、总预算和时钟独立执行。

Miner 额外保存隔离的`design_intent.json`。编译快照增加`basis_draft.json`、`calculation_evidence.json`和`calculation_scripts/*.py`；重放结果属于运行证据。`calculation_evidence` version 2把执行与评分锚点分开：一个execution绑定脚本及候选来源路径、定位和哈希，只执行一次并输出不超过1 MiB的单个有限JSON对象；多个calculation以唯一JSON Pointer提取标量，再在教师侧与预期值、容差和rubric ID比较。重放容器不挂载预期值、rubric、监督、试做答案或凭据。version 1继续读取和历史重放，单个manifest不能混用两个版本。

`factory-tools schema`可按`calculation_evidence / task / rubric / basis / comparison / review / development_diagnostic`定向查询；计算查询同时返回当前rubric ID及候选文件路径和哈希。`inspect`支持目录inventory和有限多路径读取。`check`分`draft`与`ready`：咨询只要求安全、可读、身份一致的草稿，交接、重放、试做和提交要求完整合同。阶段动作的snapshot可省略，工具会在同一次服务调用中检查并创建或复用与草稿完全一致的快照；显式snapshot和旧参数仍兼容。`record-dispositions`先验证同一请求的全部finding，再原子保存一个快照下的所有处置；逐条接口保留兼容。动态`status`返回当前草稿哈希、匹配快照、检查等级、未处理意见、阶段前提和实际预算。开发试做的`diagnostic.json`不属于DeliverableContract，最终候选交付仍由该合同精确管理。

下一版拟扩展编译依据与比较合同：编译前依据须把每个评分义务映射到候选可见来源和rubric条目；试做后的比较须列出新增或改变的评分要求及候选依据。设计意图、试做、监督和计算结果均不是候选义务来源。拟增加`factory-tools <action> --input-file <角色可读JSON>`，与位置参数和stdin互斥；同时聚合并定位rubric/计算问题、标明inspect截断和继续位置、拒绝version 2重复脚本与同execution重复result_pointer。实现完成前这些是proposed接口，旧调用继续有效。

绑定续跑通过父receipt哈希继承当前不可覆盖快照及开发试做，清除角色会话，并累计既有真实Provider启动数、生产启动数和原始截止时刻；语义前控制器操作保留诊断但不虚扣启动，已进入collection的超时仍计入。它不能重置预算或把失败改为首次尝试。2026-09-09的新采购开发scope已用version 2完成提交、独立终审和盲试做；这只证明接口在一个开发样例中可用，运行结论和限制见概要。

## 历史兼容

- R9 的 source/skill registry、proposal、materialization、package、生产及评测合同保留读取兼容。
- `ScenarioBibleV1`、严格 `EvidenceProjectionPlanV1`、旧 Skill curation 和 A/B evidence 合同服务于历史实验；不恢复 Bible V2 或固定文件/记录配额。
- `TaskSpecificRubricV1`、paired evaluator、GDPval 校准与独立评分合同及其结果保持冻结。相关实现见 [r10_evaluator_v2.py](../../src/task_generator/evaluation/r10_evaluator_v2.py) 与 [r10_gdpval_validation.py](../../src/task_generator/evaluation/r10_gdpval_validation.py)。
- 旧文档中的 proposed 接口不自动成为当前实施要求；任何新接口以新的明确计划和代码为准。

## 通用边界

候选材料、teacher 监督、运行证据分离；GDPval 内容仅作评测校准，不进入生成或训练。外部执行绑定输入/输出 SHA、模型、环境、scope/receipt 和首次失败，不能混合历史 cohort 或重抽低分答案。合同存在不等于授权执行；当前停止点见 [runbook](../operations/pipeline_reconstruction_runbook.md)。
