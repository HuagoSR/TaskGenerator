# Behavioral measurement spec v1

> 状态：`frozen_offline_v1`；2026-09-14。适用于未来 evidence-conditioned behavioral probe，不回溯修改既有 preregistration 或结果，不授权创建输入或运行模型。该规范区分任务难度与测量难度：测量对象是证据状态是否被维护并影响职业行为，而不是是否出现研究者预设措辞。

## 两层测量合同

| 层 | 必须可观察的内容 | 判定边界 |
| --- | --- | --- |
| **1. Evidence-state uptake** | 对每个受测实体识别必需证据是存在、缺失、无效、已取代还是仍有冲突；缺口必须保持为 unresolved；follow-up 必须针对该缺口及有权行动者。证据状态改变后，只更新受其支持的实体／问题，并保持无关状态不变。 | 这是主要行为观察。无需抄完整 tuple 或推理链，但最终交付必须直接陈述该状态，或通过 closed-set unresolved／follow-up 产生唯一可见的下游差异。沉默不能被解释为成功。 |
| **2. Disposition expression** | 局部处置必须与已维护的 evidence state、合同要求和权限边界相容。 | `hold`、referral、conditional consideration、request for evidence 等可以是等价的职业表达。除非候选可见合同或任务明确规定排他处置，否则不得把某一标签、字段名或句式设为唯一答案。 |

## `evidence uptake failure` 与 `expression variation`

以下属于 `evidence uptake failure`：把缺失证据写成已存在，或把有效／更正后的证据继续写成缺失；发现缺口却在 closed-set 结果中把它写成 resolved／无未决事项；遗漏与缺口匹配的 follow-up，或要求重复取得已经满足的证据；把一条局部更正扩散到无关实体、记录或限制；以及虽复述缺口、但下游行为无条件忽略该 mandatory unresolved state。该标签描述**交付中可观察的状态维护失败**，不声称直接识别模型内部表示。

以下只是 `expression variation`：在同一 evidence state 下使用 hold、提交 CO review、conditional consideration 或其他职业上可辩护的措辞；改变列顺序、详略或引用方式；省略已经解决的 correction chain。前提是未决状态仍清楚可见，follow-up 与缺口相符，处置没有暗示 requirement 已满足、被 COR 豁免或已经完成 contractual acceptance。若措辞改变了这些实质含义，就不再是无害的表达差异。

## Closed-set register 与 follow-up

- Register 必须覆盖材料定义的全部实体；每个实体都应能识别 evidence source／state、unresolved issue、local disposition 和 follow-up。允许等价列名、顺序及合并表达，不要求固定模板。缺行使该实体的 uptake 不可观察，因此不能判为成功。
- 对缺失或不足证据，follow-up 应取得对应证据，或请求有权主体作出明确书面处置；不得用泛化的 “review” 掩盖所缺内容。对已经充分的证据，不应继续要求重复取得。不同实体或问题的 follow-up 必须保持局部，不得相互污染。
- 判定时先独立核对 evidence-state uptake，再检查 disposition 是否与该状态相容；不得从某个词反推状态。只有候选材料明确规定 “must hold／reject／accept” 等排他结果时，特定 disposition 才可成为硬观察点。

## 冻结解释边界

未来 probe 的 preregistration 应分别列出事实状态、必须保留的 unresolved condition、合格 follow-up 的语义范围，以及允许的 disposition 表达族。Evidence-state uptake 正确且 disposition 属于允许表达族时，应判行为一致；不能因为没有写出预设标签而判失败。相反，状态遗漏、错误关闭、错误重开或 spillover 即使配有正确术语，也不能判成功。该边界继承 [observation identifiability audit](observation_identifiability_audit.md) 与 [G2 negative-control validity audit](g2_negative_control_validity_audit.md) 的结论。
