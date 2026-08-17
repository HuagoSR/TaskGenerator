# TaskGenerator 流水线重构问题定义

> 状态：`active`
> 职责：总结截至 Milestone F4.3 已被证据确认的系统问题，定义下一轮流水线重构需要解决的研究问题；不预设具体实现方案，不替代《项目概要》的项目状态职能。

本文件只负责问题定义。当前阶段、实现切片、接口草案、验证矩阵、受控比较和 promotion 条件见 [`pipeline_reconstruction_optimization_plan.md`](pipeline_reconstruction_optimization_plan.md)。

## 一、结论摘要

当前系统已经能够自动完成公开来源收集、skill 提炼、任务包生成、teacher truth、rubric、文件验证、服务器运行和真实模型评测，但还不能稳定产出同时满足以下两项要求的任务：

1. **端到端正确且可执行**：候选材料、prompt、模板、teacher truth、rubric 和实际交付路径必须共同成立，而不仅是分别通过局部检查。
2. **具有有效难度和模型区分度**：任务不能只是一组规则完整、数据整齐、答案显然的结构化练习，而应保留真实工作中的多步规划、证据筛选、专业判断和交付质量要求。

Milestone F4.3 的真实评测给出了直接证据：8题的32个模型组合全部尝试，但只有15个组合真正生成交付文件；其中3题出现四模型一致无交付。对另外5道可以触发正确交付的任务，三个有效模型的平均分为 `0.98 / 0.96 / 1.00`，评分高度饱和。因此，当前问题既不是单纯的“任务有错误”，也不是单纯的“任务太简单”，而是生成目标、验证制度和真实评测之间尚未对齐。

## 二、当前证据基线

| 证据 | 已确认结论 | 不能推出的结论 |
| --- | --- | --- |
| 财务审计正式生产60题 | 自动化、批量生成、verifier/export 和 QA 可以稳定运行 | 60题均正确、有难度或适合训练 |
| 30题四模型评测 | 任务存在一定模型差异，但评分低且 grader 不稳定 | 任务已达到 GDPVal 质量或训练有效 |
| 8题人工式诊断 | 旧任务存在输入缺失、规则缺失、rubric 失配等系统问题 | LLM 审查可以自动保证任务正确 |
| F2/F3/F3.1 | LLM 能发现很多语义问题，生成器原生合同能修复部分问题 | 继续增加细粒度 finding 和门禁即可解决整体质量问题 |
| F4 固定8题修订 | “LLM整体编辑 + 程序重算 + candidate-blind 求解”能修好固定样本 | 该方法已经能从零稳定生产新题 |
| F4.2 从零生产8题 | source→skill→task 的混合闭环可以跑通，内部检查为8/8通过 | 任务在真实 rw-task 中都能正确提交，或具有足够难度 |
| F4.3 真实执行 | 实际交付仅15/32；3题系统性无交付；其余有效任务评分高度饱和 | 当前8题可直接进入训练池或证明 E2D 已可默认推广 |

详细运行证据见历史报告 [`../archive/phases/milestone_f4_3/MILESTONE_F4_3_MODEL_EVAL.md`](../archive/phases/milestone_f4_3/MILESTONE_F4_3_MODEL_EVAL.md)。

## 三、问题一：当前“正确性”主要是内部一致性，不是端到端有效性

### 3.1 局部正确不等于整体正确

当前流水线分别检查：

- reference files 能否打开；
- truth 能否由程序重算；
- GoldenRun、annotation 和 rubric 是否一致；
- package 是否 verifier pass；
- rw-task export 是否结构兼容；
- candidate-only 模型是否能理解材料并得到关键结果。

这些检查都可能通过，但最终执行者仍可能不知道应该提交哪个文件。F4.3 中出现了两类直接反例：

- prompt 中要求的目标文件名与 rw-task `deliverable_files` 合同不一致；
- prompt 要求原地填写候选区同名模板，却没有清楚说明输出副本和提交位置。

这说明现有 verifier/export 主要验证“包能够被导出”，没有验证“陌生 solver 按 prompt 行动后一定能满足导出合同”。

### 3.2 多个检查共享同一个错误前提

prompt、reference schema、teacher truth、rubric 和 deterministic validator 大多来自同一 motif adapter 或 semantic contract。它们彼此一致时，可能只是共同继承了源头错误。

因此，当前系统存在相关性验证问题：检查次数很多，但检查并不真正独立。内部一致性适合发现产物漂移，不能单独证明任务定义本身正确。

### 3.3 “正确性”没有分层定义

当前讨论常把以下概念统称为正确：

- **事实正确**：金额、数量、匹配、分类可以从候选材料重算；
- **语义正确**：要求清楚、材料充分、答案或判断依据成立；
- **合同正确**：prompt、模板、目标文件名和交付路径一致；
- **行为可执行**：陌生模型在真实工具环境中能够完成并提交；
- **专业合理**：任务像真实工作，判断和交付物达到领域实践要求。

当前流水线对前两项覆盖较多，对合同和真实执行覆盖不足，对专业合理性又缺少稳定的人类专家证据。下一轮重构必须明确区分这些层次，不能再用一个 `candidate_ready` 掩盖不同含义。

## 四、问题二：任务正确后趋向过度简单，无法形成有效能力梯度

### 4.1 为消除坏歧义，系统同时消除了有价值的复杂性

为了让答案唯一、truth 可重算、rubric 可自动核验，当前任务通常把以下信息直接告诉模型：

- 使用哪些字段和 join key；
- 具体计算公式；
- 容差和分类规则；
- 状态判断优先级；
- 输出表的列和顺序；
- 每一步应当如何处理异常。

这可以避免隐藏假设，却容易把任务变成“按照说明填表”。模型不再需要决定材料关系、计划步骤、筛选证据或组织专业交付物。

### 4.2 F4整体编辑存在天然的简化倾向

Terra 的职责是修复缺失输入、隐藏假设和 teacher/rubric 冲突。若没有独立的难度保持目标，最安全的修复方式就是补充更多规则、解释和字段。结果可能从“有难度但不严谨”变成“严谨但过度教材化”。

这不是 Terra 单个模型的问题，而是编辑目标只奖励可回答性和一致性，没有奖励 productive complexity。

### 4.3 固定 adapter 对任务形态的控制超过 source 和 skill

系统形式上遵循 `source → skill → task`，但最终任务结构主要由以下部分决定：

- motif；
- 固定 reference schema；
- deterministic resolver；
- prompt compiler；
- rubric builder。

公开来源和提炼出的 skill 进入了 registry，却未必真正改变任务的证据结构、工作步骤和交付物。若不同 source/skill 最终都被压入相同 adapter，生成结果就容易成为换数字、换名称的同构任务。

### 4.4 当前 rubric 容易产生分数饱和

F4.3 的部分 rubric 只有少量事实型 criterion，且不同 criterion 的表述高度相似。评分因此接近二元判断：

- 有文件且核心数字正确：接近满分；
- 没有文件：零分。

它没有充分区分过程可审计性、公式质量、证据追踪、结构可用性、异常说明、专业表达和行动建议。三个有效模型在5题上平均 `0.98 / 0.96 / 1.00`，既说明任务偏简单，也说明 rubric 分辨率不足。

### 4.5 当前 solver panel 没有形成有效弱—中—强梯度

`gpt-5.6-sol` 在8题中均未生成交付文件，暴露的是工具执行/提交失败，而不是可比较的业务能力。剩余三个模型能力接近且都能处理文件任务，因此高分接近不能被解释为严格的模型能力排序。

真实评测必须区分：

- provider 或工具链失败；
- 没有交付；
- 交付格式错误；
- 业务计算错误；
- 专业质量不足。

只有后两类才主要反映任务难度与模型能力。

## 五、问题三：流水线正在优化代理指标，而不是最终目标

项目先后建立了 structural readiness、verifier、export、QA、GoodTaskProfiler、LLMShadow、semantic contract、candidate-blind review 和整体编辑。每一层都解决了真实问题，但层数增加后出现了两个副作用：

1. 模块只看到局部上下文，难以判断完整任务是否合理；
2. 生成器逐渐针对门禁优化，越来越擅长通过检查，而不一定更接近真实工作任务。

当前事实说明：

- 静态质量指标不能替代真实 solver 执行；
- LLM 局部 shadow 不能替代完整任务理解；
- deterministic consistency 不能替代独立有效性验证；
- export compatible 不能替代实际交付成功；
- candidate-blind 可解不能替代有区分度；
- 任务数量不能替代训练数据价值。

下一轮重构不应继续默认“发现一个问题就新增一个阶段”。应先判断哪些复杂度确实提高了最终任务质量，哪些只提高了内部流程完整度。

## 六、与 GDPVal 风格任务的主要差距

当前任务更接近“带真实业务术语的结构化计算练习”，而 GDPVal 风格真实工作任务通常还要求：

- 从多份材料中自行判断信息关系；
- 处理冗余、不完整或轻微冲突的信息；
- 规划多步工作，而不是逐步照抄 prompt；
- 在事实、判断和建议之间建立边界；
- 生成不仅正确，而且便于真实人员使用和复核的交付物；
- 同时体现事实准确性、过程质量、专业结构和表达质量。

难度不能来自缺字段、矛盾合同或隐藏 primary truth。这些属于坏任务。下一轮需要保留的是“有依据的复杂性”：必要的信息均可见，但模型必须自己完成证据组织、工作规划和专业交付。

## 七、当前架构中应当保留的能力

重构不等于推倒重来。以下能力已经被多轮运行证明有价值，应作为底座保留：

- source provenance 和 GDPVal 污染隔离；
- scratch registry 与 canonical registry 分离；
- candidate-visible 与 teacher-only 隔离；
- manifest、checksum、版本化、resume 和外部效果记录；
- 文件安全、格式验证和可视化检查；
- 确定性事实重算；
- 真实 rw-task 执行与失败证据保留；
- provider、密钥、预算和服务器治理；
- 不覆盖历史任务和失败证据。

需要重构的主要是“谁负责设计任务、如何验证整体有效性、如何保持难度、如何定义反馈”，而不是这些治理底座。

## 八、下一轮重构需要回答的核心问题

### 8.1 任务设计权应如何分配？

需要重新寻找严格逐级流水线与自由 LLM 设计之间的平衡：

- LLM 是否应在完整上下文中负责场景、材料关系、任务目标和交付物整体设计；
- skill 应作为设计素材、约束还是生成步骤；
- deterministic adapter 应负责生成任务，还是只负责事实锚点和安全边界；
- 哪些结构必须固定，哪些结构必须允许 LLM 自由决定。

### 8.2 如何同时保证有效性和难度？

需要把两条轴独立管理：

```text
Validity：事实正确、材料充分、合同一致、真实可执行
Utility：真实、复杂、有区分度、对目标能力具有训练价值
```

一项任务只有两条轴都达到门槛，才能成为训练候选。不能再把“通过有效性门禁”直接等同于“高质量任务”。

### 8.3 如何获得真正独立的验证？

下一轮需要考虑至少三种独立证据：

- 不共享生成前提的整体任务审查；
- 陌生 solver 在真实工具环境中的行为验证；
- 与生成器不同视角的 rubric/专业质量检查。

程序可以证明可计算事实和合同一致性，LLM 可以发现整体语义问题，但两者都不能单独成为最终真值源。

### 8.4 如何评价“有价值的复杂性”？

难度指标不能只使用长度、文件数、步骤数或模型失败率。需要区分：

- productive complexity：证据整合、规划、判断、审计追踪和交付设计；
- accidental difficulty：缺字段、错误文件名、工具不兼容、模糊要求和 grader 不稳定。

下一轮比较必须奖励前者、阻塞后者。

### 8.5 source 和 skill 如何真正影响最终任务？

需要验证每项 skill 是否改变了任务的工作流、证据关系或交付要求，而不只是进入标签和 prompt 文本。若移除 source/skill 后任务几乎不变，说明 Pipeline A 尚未对任务价值产生实质贡献。

## 九、下一阶段的研究边界

下一轮工作应围绕流水线重构与受控比较展开，而不是立即继续扩题。可比较的方向仍包括：

- 严格模板流水线；
- Skill-only 或 skill-guided 生成；
- LLM 主导整体设计、程序负责治理的混合路线。

比较时应使用相同 source 范围、任务数量、solver 环境和评价合同，主要观察：

- 端到端有效任务率；
- 重大任务缺陷率；
- 实际交付率；
- rubric 分辨率；
- 模型差异和失败归因；
- 任务结构与 skill/source 的真实关联；
- 人工式整体审查成本；
- 系统复杂度与收益。

在完成该比较前：

- 不进入 RL/SFT；
- 不继续批量扩充训练候选池；
- 不推广 `evidence_to_deliverable`；
- 不切换服务器 production release；
- 不以现有内部 pass 数量证明训练数据已经准备完成。

### 9.1 v7 provider screening 对问题定义的补充

四个公开来源 brief 的 v7 授权筛选进一步确认，问题不只是“是否让 LLM 参与”，还包括 LLM 与程序之间的引用协议和修复反馈是否真实成立：

- 8 个 LLM assignments 仅 4 个完成物化，说明 schema-valid、source-admitted 的输入仍不足以保证跨 brief package completion；
- 失败 proposal 多次把章节裸文本或自造 `section_*` ID 当成 causal binding，说明程序内部的 canonical namespace 若没有明确暴露给模型，就会把可修复的引用错误误记为“装饰性 skill”；
- 5 次第二调用与第一次 prompt 相同，说明“最多一次重试”本身不构成 repair；没有失败 proposal、validator finding 和合法 ID 集合的反馈，成功只能视为随机重抽；
- skill-guided 1/4、LLM-led 3/4 不能用于路线优劣判断，因为 matched packages 不完整且没有任何 solver/grader 行为证据。

因此下一候选必须把“feedback-conditioned repair rate”和“canonical binding reference validity”作为 provider screening 的独立指标；未通过 package completion 前不得进入行为比较。

### 9.2 v15–v22 对接口问题的补充

后续证据表明，解决 canonical namespace 和 repair feedback 后，新的主要矛盾转移到“整体语义设计”与“大型执行 schema”之间：

- v15/v16 的 proposal 可以通过，但旧 materializer 把不同业务角色压成统一占位表，说明 schema pass 不代表语义工件成立；
- v21 的 V2 双路线首次生成真实业务字段和跨文件 anchors，但实际渲染仍发现机器式标签与长文本显示问题；
- v22 skill-guided 验证了业务可读标签，而 matched LLM-led 返回完整响应后仍在 V2 parse 阶段失败，且没有形成可反馈修复的 proposal；
- v22 历史报告只保留 `ValidationError`，进一步说明 contract failure 的安全诊断必须在下一次外呼前离线完成，而不能依赖重复调用碰运气。

因此，下一步不能简单放宽 schema 或增加无条件重试。需要验证一种受治理的接口分层：LLM 保留场景、证据关系、判断和交付意图的 proposal authority；程序负责把已验证语义结构归一化为执行合同，并继续独占事实、路径、隔离与 promotion authority。任何分层方案都必须通过 negative controls 证明它没有静默补造业务事实、删除 productive complexity 或把不完整输出伪装成合格 proposal。

该接口分层的离线核心现已实现并通过同指纹容器复验：`v3.task_design_semantic_proposal.1` 保留全部 provider-owned business semantics，normalizer 只增加执行语法和全 false authority，并以语义投影哈希、事实增删计数和 productive-complexity equality 证明无损。v24 进一步证明“proposal 通过”仍可能遗漏 artifact-level provenance 或在内容 gate 误判真实 prior-draft 输入；当前合同因此强制 artifact/node source projection 精确相等，并对明确否定语境做边界处理。persisted proposal 可零外呼重放当前验证合同，形成可审计 repair readiness，但不被计为 provider 观测。该阶段的 243/243、`103b59ad...01fb` 是历史快照；当前完整本地/固定容器基线已推进到 249/249、`0c1b3705...858a`。这些证据证明接口与治理合同可执行，不证明真实 provider、solver 或专业复核能在完整 matched campaign 中稳定通过。

### 9.3 v23–v28 对“生成正确性”的进一步补充

v23–v28 的真实 provider slices 把问题进一步定位到三个层次：

- semantic proposal 与程序执行合同可以无损分层；多条真实 proposal 已证明事实零增删、productive complexity 保留和零 mutation authority；
- feedback-conditioned repair 在 preserved proposal、blocking findings 和 canonical IDs 齐备时能够工作，但 provider/schema failure 或 materialization failure 不能靠重复调用补救；
- materialization 后的 deterministic semantic gate 本身也可能误判。v25–v27 连续暴露 plural/irregular-plural/typed-record 三类 role-header 假阳性，说明“更多门禁”若没有独立内容和实际渲染证据，也会成为新的代理指标。

当前修复把 provider-owned `record_type` 纳入角色语义，同时排除 field display names，避免门禁自证式通过；正负回归、冻结文件零外呼 replay 与 V27 实审均通过。V28 四个 briefs 的 8 个 provider assignments 已全部观测：LLM-led 4/4 首轮物化，skill-guided 3/4；唯一失败因 relation 缺少 required join contract 而在 semantic normalization 阶段 fail closed，且因没有 strict proposal 不具 repair 资格。这说明 typed-record gate 已稳定，但 route-conditioned provider 对完整关系合同的一次性遵从仍不稳定。7 条已物化路线的 47 个工作簿和 94 张实际渲染全部通过内容、公式、provenance 与 export-identity 审计。正式 provider screening 因 package completion 低于合同和跨 brief route instability 判为 `redesign_again`；matched packages 不完整，因此不能进入 solver panel、repeated grader、独立专业复核或路线优越性判断。

V28 之后的离线重构针对的是接口失配而非放宽正确性：semantic provider schema 现在直接要求每条 relation 的两个非空 join fields，prompt 明确禁止省略或 `null`，normalizer 仍不得代填业务关系。为了避免“整体可解析、局部缺失”被误归为不可反馈的广泛 schema failure，executor 新增 `semantic_proposal_blocked`：只在兼容 draft schema 能解析完整对象时保存 semantic draft、sanitized normalization findings 和实际初始 prompt，并允许唯一一次带原 draft、findings 与 canonical IDs 的完整替换修复。真正的 schema-invalid、provider failure、materialization failure 或无 draft 情况仍停止。该路径已通过 tracked missing-join negative fixture、42 项针对性测试和 local/container 252/252，尚未获得 fresh provider observation，因此只能把问题从“接口必然浪费一次响应”推进到“具备可验证修复能力”，不能声称跨 brief 稳定性已经解决。

V29 fresh provider pair 证明 join-field schema 修复后两条路线都能完成 normalization/materialization，但又暴露 skill-binding cardinality：skill-guided 首轮通过，LLM-led 对同一 skill 生成两个 binding objects，被 causal validator 阻断后由一次 feedback-conditioned repair 通过。16 个 provider-route XLSX/32 sheets 的真实导入、渲染、公式、provenance 与 export-identity 审计全部通过。问题不在 bound-element namespace，而在初始 prompt 只要求“每个 skill 有因果绑定”，没有明确“恰好一个 binding”。当前 prompt 已补齐 cardinality，screening 也分别报告 namespace/cardinality/missing-or-decorative；local/container 253/253 通过。该结果仍只证明 proposal repair 和静态 materialization，不证明行为 Utility 或跨 brief 稳定性。

V30 首个 fresh pair 对 cardinality 修复给出正向观察：skill-guided 首轮通过；LLM-led 没有重复 binding，而是因一个 frozen source 未进入 topology 被阻断，随后 feedback repair 通过。两条路线 2/2 materialized；15 个 provider-route XLSX/30 sheets 的真实审计全部通过。partial screening 只有 `provider_campaign_incomplete`，没有新的 contract redesign reason。这仍不足以声称跨 brief 稳定性，必须继续 matched provider screening，且在完整 packages 前不得启动 solver/grader。

V30 的 sequential authorization 审计还暴露了独立的状态机问题：旧 slice 的合法 receipt 曾可在未绑定当前 active request SHA 的情况下把 campaign 标成 `provider_generation_ready`。后续 task-scope gate 虽会阻断真正调用，但 ready 状态本身已不可信。用户对 request `74a6e65f...5d47` 的授权因此未被消费，且没有产生 provider 调用。当前 preflight 在状态变更前强制校验 receipt 的 `authorization_request_sha256` 与 active request 文件内容 SHA 完全一致；不一致返回 `authorization_receipt_active_request_mismatch` 并保持 campaign 不变。新增 sequential regression 后，本地与固定容器均通过 254 项测试。V30 冻结，V31 以新代码和容器指纹重新准备；其 exact request 为 `6e486b9d1e0a983bf9bd6b950213b095cb826dacbf9903e415f39732d5990ba5`，尚无外部调用。

V31 cross-check provider slice 随后证明 active-request 修复可在真实 sequential workflow 中工作。LLM-led 首轮通过；skill-guided 首轮唯一阻断为 proposal 试图声明 mutation authority，原 proposal、验证 finding 与首错均被保留，feedback-conditioned repair 随后通过。两路线最终 2/2 materialized，3 calls、58,916 tokens、501.297 秒、6 USD，0 unconditioned retry。18 个工作簿/36 张 sheet 的导入、渲染、公式、provenance 与 export identity 审计通过。该结果说明 authority boundary 能被验证并由受管反馈纠正，但仍只有一个 brief；partial screening 仅为 `awaiting_provider_completion`，不能推导行为 Utility、路线优越性或训练价值。

V31 policy-application slice 扩展了跨 brief 观察：skill-guided 与 LLM-led 均在首轮通过 schema、normalization、proposal validation 和 materialization，无 repair。两次调用共 24,923 tokens、269.062 秒和 4 USD；15 个工作簿/30 张 sheet 的内容、渲染、公式、provenance 与 export identity 审计全部通过。V31 累计 4/8 provider assignments materialized，正式 partial screening 仍只有 `provider_campaign_incomplete`。这提高了 provider-interface 跨 brief 稳定性证据，但 matched packages 尚未完整，仍不能启动 solver/grader 或声称路线优越性。

V31 fan-in slice 继续给出正向跨 brief 观察：两路线均首轮通过并物化，无 repair；2 calls、24,060 tokens、253.124 秒和 4 USD。13 个工作簿/26 张 sheet 的内容、渲染、公式、provenance 与 export identity 审计通过。V31 累计 6/8 provider assignments materialized，partial screening 仍只有 `provider_campaign_incomplete`。剩余一对属于 `evidence_to_deliverable` experimental motif；其 provider 完成只能关闭 screening 样本，不得自动解释为该 motif 已可推广或已具行为 Utility。

V31 final evidence-to-deliverable slice 关闭了 provider 样本。skill-guided 首轮通过；LLM-led 首轮因冻结来源未进入 evidence topology 而保留 `proposal_blocked`，唯一 feedback-conditioned repair 随后通过。该 pair 2/2 materialized，3 calls、40,810 tokens、387.391 秒、6 USD；12 workbooks/24 sheets 的内容、渲染、公式、provenance 与 12/12 export identity 审计通过。V31 总计 8/8 provider assignments materialized、10 calls、148,709 tokens、1410.874 秒、20 USD、2 feedback retries、0 unconditioned retry；formal screening=`proceed_to_behavioral_evaluation`。12/12 route-blind staging 随后通过且排除 teacher artifacts。该证据只证明 provider/materialization 接口在四个冻结 brief 上达到继续评估门槛；它仍未回答 solver 是否精确交付、任务是否区分模型、grader 是否稳定或路线是否有真实 Utility。

Provider 门关闭后又暴露一项治理缺口：原计划要求 solver preflight 与 business execution 独立授权，但行为层最初没有可校验授权对象。V1 两级合同补上 authority scope，却让一次 attempt 展开为 4/6/100 calls。V2/V3 逐步加入 call、turn、request-byte、provider token、completion reservation、零重试、contract-cost、request-hash 清单隔离和 legacy MD5 路径归一化。V3 已把三模型限制在 8/7/8 calls，却进一步证明“finish + 非空 + 精确路径”仍不等于有效提交：weak 交付的是两个只有 15/16 字节的纯文本伪 XLSX，medium 真正通过全部操作，strong 在 call ceiling 无交付。V3 closeout 因此为 `redesign_again`，且没有盲包或 grader 调用。当前 outcome 在返回成功前必须使用同一 `DeliverableContract` 检查文件可打开性；下一步应修正 agent-tool admission/feedback，而不是用更高预算掩盖工具失败。contract cost 不冒充第三方实际账单。只有三个 preflight 同环境通过后，第二级真实任务授权才具备生成资格。

## 十、重构问题的最终表述

下一阶段的核心研究问题应表述为：

> 如何让 LLM 在拥有完整任务上下文的前提下承担其擅长的整体设计与语义推理，同时用最少但关键的确定性治理保证来源、事实、隔离、合同和可审计性，从而稳定生成既正确可执行、又保留真实职业复杂性并能够区分模型能力的任务？

这比继续增加局部门禁更接近项目的原始目标，也是后续判断数据能否进入训练准备阶段的前置条件。
