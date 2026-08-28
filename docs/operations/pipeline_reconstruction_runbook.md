# 流水线重构执行 Runbook

> 生命周期：`active`
>
> 职责：规定 R6/R7 从冻结 campaign、外部授权、provider 生成、盲化执行到 comparison、confirmation、服务器候选和 rollback 的操作顺序。项目状态仍只由根目录《项目概要》维护。

## 1. 当前执行状态

当前没有可执行的 provider、solver 或 grader 授权。V31 provider/materialization 已完成，但 behavioral 路径先停在 agent protocol diagnosis，不进入 replacement execution：

```text
active_campaign = r6_formal_public_v31
campaign_status = evaluation_ready
campaign_root = artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v31_20260719
provider_screening_decision = proceed_to_behavioral_evaluation
design_model = gpt-5.6-sol
provider_assignments_materialized = 8 / 8
strict_template_controls = 4
strict_template_materialized = 4 / 4
provider_attempts = 10
provider_feedback_conditioned_retries = 2
provider_unconditioned_retries = 0
provider_tokens = 148709
provider_duration_seconds = 1410.874
provider_reserved_cost_ceiling_usd = 20 / 32
public_tool_preflight_v3_internal_calls = 8 / 7 / 8
public_tool_preflight_v3_status = fail / pass / fail
public_tool_preflight_v3_integrity = pass
solver_panel_admission = retain_medium_replace_weak_strong
replacement_candidate_models_bound = experimental_request_only
replacement_external_authorization = false
replacement_request_sha256 = 8b6c6aad62279531cb26c26be57c205b3da5043c8ec1cabe5127a655c1fe65ab
replacement_request_status = superseded_pre_execution_no_receipt
strong_preflight_interpretation = model_gateway_agent_protocol_indeterminate
blind_business_solver_calls = 0
grader_calls = 0
latest_frozen_comparison_id = r6_formal_public_v30
latest_frozen_campaign_root = artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v30_20260719
replacement_slice_implementation_parity_fingerprint = e4c208f5c377bf8d3f9dc7941f4593036b9d9cbb11a7d586490e4418511cb865
replacement_slice_implementation_parity_report_sha256 = ec159667a91648d56e033f4e3a9842e2a11cad6ef9057e08d3a0578166a64aa5
exact_request_requires_post_document_sync_parity = true
v31_latest_consumed_authorization_request = 588d7708f7389622166c51bbae7b63af53077227b7bad2b514e045d36890af3f
v31_latest_consumed_receipt_sha256 = c977d216bb2127c2398c0b897b823cf85626deada7eb06aa4925753b3db4d1ea
v31_provider_screening = proceed_to_behavioral_evaluation
v31_route_blind_staging = pass_12_of_12
v31_campaign_status = evaluation_ready
v31_tool_preflight_solver_attempts = 3
v31_tool_preflight_v3_internal_provider_calls_reported = 8 / 7 / 8
v31_tool_preflight_v3_status = fail / pass / fail
v31_frozen_solver_panel = blocked
v31_blind_business_solver_calls_made = false
v31_grader_calls_made = false
v31_behavioral_authorization_level = v3_replacement_slice_offline_ready_no_external_authorization
v31_behavioral_contract_local_container_tests = 288 / 288
```

`8b6c6aad...e65ab` 只是在发现 strong 空响应根因前编译的候选替补申请，从未获授权、没有 receipt、没有外部调用。它现在是 superseded pre-execution artifact；不得确认、创建 receipt、dry-run 或执行。weak/strong replacement 合同代码可保留，但只有后述 compatibility gate 关闭后才能重新选择模型并编译全新 request。

V31 tool-only request `2b6f5cb8...e5049` 已消费，未上传 route-blind package 或执行 grader。weak/medium 通过；strong 在 100 turns 后无交付，外层 `[OK]` 被 artifact inspection 推翻，panel=`blocked`。V2 runner 已完成：SDK/Tenacity retry 均为零；每模型预算硬限制 provider calls、agent turns、请求 UTF-8 bytes（作为输入 token 保守上界）、provider-reported input/output tokens、completion reservation 和按冻结费率计算的 contract cost；无 finish signal、无非空交付或 outcome identity 不匹配均失败。V2 receipt 单次消费，源码指纹漂移、盲 ID/额外文件、campaign 外输入输出、既有失败/碰撞和 indeterminate resume 均阻断。contract cost 不是 provider billing telemetry，不得写成实际账单。当前 local/container 274/274；没有新 V2 外呼授权，仍不得启动第二级 business execution。

V31 cross-check request `6e486b9d...0ba5` 已消费。LLM-led 首轮通过并物化；skill-guided 首轮保存 mutation-authority `proposal_blocked`，唯一 feedback repair 后通过并物化。3 calls、58,916 tokens、501.297 秒、6/8 USD，0 unconditioned retry。18 workbooks/36 sheets 的 artifact-tool 导入、渲染、公式、provenance 与 18/18 export identity 审计通过。partial screening=`awaiting_provider_completion`，reason 仅 `provider_campaign_incomplete`；该 receipt 不得复用或扩大。

V31 policy request `5ad5bb68...546cf` 已由 receipt `fb194651...e55b8` 消费。两路线均首轮通过并物化，2 calls、24,923 tokens、269.062 秒、4/8 USD，无 repair。15 workbooks/30 sheets 的 artifact-tool 导入、渲染、公式、provenance 与 15/15 export identity 审计通过。累计 partial screening=`awaiting_provider_completion`，4/8 materialized，唯一 reason 为 `provider_campaign_incomplete`；该 receipt 不得复用或扩大。

V31 fan-in request `34b32317...77c0` 已由 receipt `4755fcec...7f2d0` 消费。两路线均首轮通过并物化，2 calls、24,060 tokens、253.124 秒、4/8 USD，无 repair。13 workbooks/26 sheets 的 artifact-tool 导入、渲染、公式、provenance 与 13/13 export identity 审计通过。累计 partial screening=`awaiting_provider_completion`，6/8 materialized，唯一 reason 为 `provider_campaign_incomplete`；该 receipt 不得复用或扩大。

V31 final provider request `588d7708...0af3f` 已由 receipt `c977d216...d1ea` 消费。skill-guided 首轮通过并物化；LLM-led 首轮保留 unused-source `proposal_blocked`，随后唯一 feedback-conditioned repair 通过并物化。该 pair 为 3 calls、40,810 tokens、387.391 秒、6/8 USD；12 workbooks/24 sheets 的 artifact-tool 导入、公式、显示、provenance 与 12/12 export identity 审计通过。V31 最终为 8/8 provider materialized、10 calls、148,709 tokens、1410.874 秒、20/32 USD，2 feedback retries、0 unconditioned retry。正式 screening=`proceed_to_behavioral_evaluation`，随后 12/12 route-blind staging pass，report SHA=`a1c014a5...928d3`，不含 teacher artifacts，campaign=`evaluation_ready`。该 receipt 不得复用；solver、grader、专业复核、registry、release 与 promotion 仍未授权。

用户对 V30 request `74a6e65f...5d47` 的确认没有被消费，也没有产生 provider 调用。receipt 编译前审计发现，旧 slice receipt 曾可在未匹配 active request SHA 时错误改变 campaign 状态；当前 preflight 已在任何状态变更前强制校验 exact active-request binding，不一致时返回 `authorization_receipt_active_request_mismatch`。V30 因代码指纹变化而冻结，该旧确认不得迁移到 V31。

V30 first request `32573db4...dcf1` 已由 receipt `66d011a2...fe95` 消费。skill-guided `cmp_9a365f866100f17c` 首轮通过并物化；LLM-led `cmp_ebf56b985922a6cc` 首轮保存 unused-source `proposal_blocked`，唯一 feedback repair 后通过并物化。3 calls、42,616 tokens、354.235 秒、6/8 USD，0 unconditioned retry。15 provider-route workbooks/30 sheets 经实际导入与逐图审计，0 formula/visual failures，15/15 provenance 非空且 15/15 export identity。partial screening=`awaiting_provider_completion`，仅 `provider_campaign_incomplete`；该 receipt 不得复用或扩大。

V29 request `df63258c...bf1d` 已由 receipt SHA `89c40027...a40d` 消费并冻结。skill-guided `cmp_2d7e813026db6bc2` 首轮 proposal/materialization pass；LLM-led `cmp_996bef081a8fa015` 首轮因 duplicate skill binding 而保存 `proposal_blocked` 首错，唯一 feedback-conditioned repair 随后通过并物化。总计 3 次 `gpt-5.6-sol` 调用、44,270 tokens、377.390 秒、6/8 USD，0 unconditioned retry。16 个 provider-route XLSX/32 sheets 经 artifact-tool 导入和逐图审计，0 formula/visual failures，16/16 provenance 非空，16/16 candidate/export 字节一致。V29 screening=`redesign_again` 且不得重写；旧 receipt 不得复用或扩大。

V29 后 prompt 明确要求每个 selected skill 恰好一个 binding；screening 分别报告 bound-element namespace、skill-binding cardinality 和 missing/decorative skill failure。新增回归后本地与固定容器均为 253/253，container parity `989dd8bb...4fe`，campaign code fingerprint `c0860676...4990`。V29 首错的 portable repair-readiness 为 1/1 pass；该离线证据只允许准备 V30，不授权 provider。

V28 首个 request `8badb407...71a1` 已获 exact 授权并消费，只使用 `gpt-5.6-sol`。skill-guided `cmp_a7592a98621238fc` 与 LLM-led `cmp_00fa0efa7275a8fa` 均首轮 proposal/materialization pass；两次调用共 23,887 tokens、248.937 秒、4/8 USD，无 repair。13 workbooks/26 Evidence/Provenance sheets 全部通过 artifact-tool 导入、公式和逐图检查，13/13 provenance 完整且 13/13 candidate/export 字节一致。receipt SHA 为 `143734d1...e847`，不得扩大或复用到其他 assignments。

第二个 request `73cc9ef2...6080` 也已获 exact 授权并消费。brief `brief_31f83336b665` 的 skill-guided 与 LLM-led 均首轮 proposal/materialization pass；两次调用共 30,640 tokens、337.766 秒、4/8 USD，无 repair。18 workbooks/36 sheets 全部通过内容、公式和逐图检查，18/18 provenance 完整且 18/18 candidate/export 字节一致。receipt SHA 为 `70cafe6e...e91ea`，不得扩大或复用。

第三个 request `2238fd1f...c09d8` 已获 exact 授权并消费。LLM-led 首轮通过并物化；skill-guided 因 `relation_walkthrough_to_deficiency_policy` 缺少 join contract 而 `contract_failed`，没有 proposal 落盘，因此没有合法 retry。两次调用共 24,090 tokens、245.750 秒、4/8 USD。LLM-led 的 4 workbooks/8 sheets 通过内容、公式、逐图、provenance 和 4/4 export identity 审计。receipt SHA 为 `0dadcf26...6dcf8`，首错不得覆盖。

最后 request `3b563b619cef92e94d1788ceb685b5aa7eba130711d690311625cb1ab3aec4f3` 已获 exact 授权，并由 receipt SHA `a5afbbfd...a922` 绑定。brief `brief_b9bf5ab545c1` 的 skill-guided `cmp_af4702186df55d37` 与 LLM-led `cmp_345146229dec7eab` 均首轮 proposal/materialization pass，未发生 repair。12 workbooks/24 sheets 通过 artifact-tool 自动扫描和逐页审计，12/12 provenance 完整、12/12 candidate/export 字节一致。该 receipt 已消费完毕，不得复用或扩大；solver、grader、专业复核、registry、release 和 promotion 均排除。

阶段边界：R0–R5 离线核心、R7 report-only 核心、join-contract、skill-binding-cardinality 与 active-request binding 重构均已完成；当前本地/固定容器为 254/254 parity。V28–V30 均冻结；当前只允许在新 fingerprint 下为 V31 exact request 取得授权，而不是 solver calibration、behavioral route screening 或 production promotion。

v24 cross-check request `8761b514...0f57` 已获 exact 授权并消费：两条路线各一次 `gpt-5.6-sol` 首轮调用，共 28,192 tokens、294.265 秒、4/8 USD。LLM-led 物化通过；skill-guided 因否定句误报被内容 gate 阻断，随后审计还发现其 12 个 artifact 未投影 node source refs。30 个工作簿、60 张 Evidence/Provenance 实图均可渲染、无公式错误且 candidate/export 副本一致。v24 冻结为诊断证据，不得追加执行。

当前代码已让 artifact `methodological_source_ref_ids` 与 node `source_ref_ids` 精确相等，否则在 proposal validation 层阻断；内容 detector 不再把明确的 `not candidate-authored` 当正向泄漏。`run_v3_task_design_offline_replay.py` 可在零外呼下重放 persisted strict V2 proposal，生成当前 validation/binding/authority 与 execution report；它固定 `allow_external_provider=false`，不产生 provider diagnostics，不能物化或 mutation。v24 skill proposal 据此生成的 portable repair-readiness 为 1/1 pass；其历史 parity 快照为 243/243、`103b59ad...01fb`，当前 parity 以本节后续 V25 closeout 记录为准。

fresh `r6_formal_public_v25` 已通过 formal admission、repair-readiness replay、四个 strict controls 与 structural preflight。cross-check request `023cb1df...62da` 已获授权并消费：skill-guided 首轮通过；LLM-led 首轮保存一个 `evidence_topology_provenance` 阻断后，由 feedback-conditioned repair 通过。2/2 路线物化，共 3 次 `gpt-5.6-sol` 调用、52,513 tokens、446.531 秒、6/8 USD；31 个工作簿、62 张 Evidence/Provenance sheet 的 content/render/provenance/export audit 全部通过。

fan-in request `a873d10e...e6f98` 也已获授权并消费：skill-guided 与 LLM-led 均首轮通过并物化，无 repair；两次 `gpt-5.6-sol` 调用共 23,926 tokens、253.187 秒、4/8 USD。21 个 matched-route 工作簿、42 张 Evidence/Provenance sheet 经实际导入、渲染和逐张检查，0 失败、0 公式错误、0 Evidence 机器标签、0 空 provenance，21/21 export 副本一致。v25 累计 screening 为 `awaiting_provider_completion`：4/8 provider assignments materialized、5 calls、1 feedback retry、0 unconditioned retry、76,439 tokens、699.718 秒、10 USD reserved。两份已消费 receipt 均不得扩大或重用。

policy-application request `fb3c00c98cde...f084` 已获授权并消费：两条 `gpt-5.6-sol` proposal 均首轮通过，无 loss/authority/source-binding 问题；LLM-led 物化，skill-guided 在 deterministic content gate 被冻结为 blocked。两次调用共 24,303 tokens、255.220 秒、4/8 USD；materialization failure 不具备 provider repair 资格，因此没有第二次调用。26 个 matched-route workbooks/52 sheets 经 artifact-tool 实际导入、渲染和逐张检查，0 failures、0 formula errors、0 Evidence machine tokens、0 blank provenance，26/26 export identity。

skill-guided block 的唯一原因是 role 中复数 `thresholds/metrics` 与 headers 中单数 `Threshold/Metric` 的 literal-token mismatch。当前 validator 已做保守 plural canonicalization，正向 plural/singular 与 unrelated-role negative tests 均通过；对冻结 proposal/files 的零外呼 content replay 为 11/11 pass。原 V25 first failure 不得覆盖，replay 不计作 provider attempt 或 materialization。修复后的本地与固定 Linux/amd64 parity 均为 245/245，指纹 `a437172ffbf9328a0a0edc6936aaacca981ad88d4eb8f968ce6cb0f673aa0ffd`，断网、只读、无凭据并清理成功。

V25 因代码指纹变化冻结，最终 screening=`awaiting_provider_completion`：5/8 provider assignments materialized、1 blocked、2 unrun experimental、7 calls、1 feedback retry、0 unconditioned retry、100,742 tokens、954.938 秒、14 USD reserved。禁止继续其 `evidence_to_deliverable` assignments、复用三份 receipt 或直接进入 solver/grader。任何下一 external slice 必须重新同步 campaign fingerprint、通过 local/container/strict controls，并生成新的 immutable exact request/receipt。

fresh `r6_formal_public_v26` 的 policy request `7457b1f7...57dc` 已获 exact 授权并消费。不可变 receipt SHA 为 `29d5f15c...6375`；skill-guided `cmp_372b35a616a8fb8b` 与 LLM-led `cmp_37f0cb3b9bffbfc8` 均首轮通过并物化。两次调用共 27,194 tokens、303.000 秒、4/8 USD；16 workbooks/32 sheets 审计全部通过。

fan-in request `79559adc...60da` 也已获授权并消费。skill-guided 首轮 proposal 通过，但 deterministic content gate 因 `criteria/Criterion` 假阳性阻断；materialization failure 不具 provider repair 资格。LLM-led 首轮保存一个 unused-source `proposal_blocked`，随后 feedback-conditioned repair 通过并物化。三次 `gpt-5.6-sol` 调用共 38,247 tokens、310.297 秒、6/8 USD，0 unconditioned retry。两路线 8/4 workbooks、24 sheets 经 artifact-tool 实际导入和逐张检查，0 failures、0 formula errors、0 Evidence machine tokens、12/12 provenance 非空、12/12 export identity。

当前 validator 已保守映射 `criteria` 到 `criterion`，同时保留 unrelated-role negative control；V26 原 first failure 不得覆盖，replay 不计作 provider attempt/materialization。V26 最终 screening=`awaiting_provider_completion`：3/8 materialized、1 blocked、4 pending、5 calls、1 feedback retry、65,441 tokens、613.297 秒、10 USD reserved；禁止继续或复用其 receipts。

V27 fan-in request `f187ccd3...45fc` 已获授权并消费。LLM-led 首轮物化；skill-guided proposal 首轮通过，但 deterministic content gate 忽略 typed `record_type=evidence_assessment_criterion` 后产生 role/header 假阳性，因此没有合法 provider retry。两次 `gpt-5.6-sol` 调用共 23,976 tokens、284.375 秒、4/8 USD。两路线 13 workbooks、26 sheets 经 artifact-tool 实际导入和逐张检查，0 failures、0 formula errors、0 Evidence machine tokens、13/13 provenance 非空、13/13 export identity。

validator 现把 provider-owned `record_type` 加入 role-side semantics，但不使用 field display names；针对性测试 15/15，冻结 proposal/files 的零外呼 content replay 为 8/8 pass。完整 local 与固定 Linux/amd64 parity 均为 249/249，指纹 `0c1b370571db556be559ebf8615fb91197c7f7b9ac31ed6ac1dde6a12c73858a`，断网、只读、无凭据并清理成功。V27 已冻结；代码变化后的正式 screening 写入必须并已因 fingerprint mismatch fail closed，不得覆盖原结果或复用 receipt。

fresh `r6_formal_public_v28` 已在当前指纹下完成四个 exact requests 和四个 strict controls。8 次 `gpt-5.6-sol` 调用共 102,082 tokens、1,076.593 秒、16 USD cumulative reserved；7/8 assignments 首轮物化，1 个 skill-guided semantic normalization block，0 retry。47 个已物化 provider-route workbooks/94 sheets 的内容、显示、provenance 与 export identity 审计全部通过。正式 screening=`redesign_again`，reason codes 为 `provider_package_completion_below_contract` 与 `provider_route_cross_brief_instability`。冻结 block 不得覆盖；matched packages 不完整，禁止进入 solver/grader、路线优越性判断或 promotion。任何 successor campaign 都必须先完成离线接口修复、完整回归和新指纹冻结，再生成新的 immutable exact request。

post-V28 join-contract 重构已完成且不得回写 V28。provider-facing semantic schema 现在要求每条 relation 的 `from_join_field`、`to_join_field` 均为非空必填，prompt 明确禁止省略或 `null`；normalizer 不得代填。若响应整体可由兼容 draft schema 解析但 normalization 阻断，executor 保存 `task_design_semantic_proposal.json`、sanitized findings 和调用前写入的实际 `task_design_proposal_prompt.md`，状态为 `semantic_proposal_blocked`。只有该状态或原有 `proposal_blocked` 且持久化 proposal、feedback、canonical IDs 全部存在时，campaign 才可预留唯一第二次 repair；广泛 `contract_failed`、`provider_failed`、materialization failure 或缺 draft 仍停止。42 targeted、252 full local 和 252 fixed-container tests 通过；container parity `2178bd38...c23b`，campaign code fingerprint `4ec4dadb...b36b`，服务器临时快照与镜像清理成功。该证据不授权 provider。

`r6_formal_public_v6` 是 bounded smoke 证据；`r6_formal_public_v7` 是已完成并冻结的 `redesign_again` provider-screening 证据。v15 的用户授权 cross-check slice 已完成：两条路线首轮通过、2/2 materialized、19,851 tokens、173.937 秒、4/8 美元，partial screening=`awaiting_provider_completion`；它不追加执行。执行后 report-semantics 修复使 v15 fail closed。v16 的已授权 policy-application slice 完成：LLM-led 首轮通过，skill-guided 首轮阻断后由 feedback-conditioned repair 通过；2/2 materialized、31,026 tokens、226.827 秒、6/8 美元。随后三路线内容审计发现 v15/v16 的 58 个 candidate XLSX 全部是统一占位表，并被 `v3.evidence_content_quality.1` 全部阻断；v16 因此冻结为诊断证据，禁止申请其余 6 个 provider assignments。

v21 的 V2 pair 已冻结为显示质量诊断证据。v22 fresh pair 中，skill-guided 首轮通过并物化 11 个工作簿，实图验证可读 enum/`Yes/No`；LLM-led 首轮 V2 schema parse 失败且无可修复 proposal，因此停止。累计 artifact-tool 审计覆盖 115 个工作簿、172 张预览，115/115 export 副本一致。v22 发生在 sanitized findings 功能加入之前，历史报告只有 `ValidationError`；当前代码才会为未来 schema failure 保存不含 provider 字段值的 location/type/message。`contract_failed`、`provider_failed` 或缺 proposal 的失败不得再次外呼。v22 不进入 solver/grader，也不得继续其余 assignments。

R2.1/R3.1 离线接口分层现已通过：provider schema 为 `v3.task_design_semantic_proposal.1`，程序只将其无损归一化为 strict V2，并持久化 semantic proposal、normalization report 与 strict proposal。normalization 必须证明 provider-owned semantic hashes 相等、`facts_added=0`、`facts_removed=0`、productive complexity 保留、authority 由程序写入且全 false。join fields 现为 semantic schema required；tracked malformed/missing-join cases、sanitized findings、semantic-loss/provenance/word-form/typed-record controls、本地与固定 Linux/amd64 252 tests 均通过。该证据不授权 provider。

新 campaign 的离线入口现要求：strict-template 与 tracked proposals 使用 `v3.task_design_proposal.2`；provider routes 请求 join fields 必填的 `v3.task_design_semantic_proposal.1` 并以 passing normalization report 生成 strict V2。所有 candidate-visible nodes 具有 artifact spec，所有 relations 具有 join contract，V2 materialization report 同时满足 `materialization_backend=hybrid_semantic_artifact_v2` 与 `evidence_content_quality_decision=pass`。strict controls 必须按四种 motif 使用不同业务字段、异常模式和 join/comparison contract，并完成实际 Evidence/Provenance 渲染。provider executor 收到 V1、广泛不可解析 payload 或超长 payload 必须 `contract_failed`；只有可解析 semantic draft 的局部 normalization failure 可成为 `semantic_proposal_blocked`。provider route 的 completion 下限仍为 16,000 tokens，费用天花板仍为每次 2 美元、campaign 32 美元。只有完整本地测试、固定容器、portable repair readiness 和离线 strict controls 在同一代码指纹下通过后，才可编译新的 immutable provider authorization request。

以下操作始终禁止：

- 使用 `claude-sonnet-4-6` 或其别名；
- 绕过 repository runner 直接调用 provider；
- 从 GDPVal、fixture、synthetic 或 unresolved source 生成正式任务；
- 修改 canonical registry、readiness、服务器 `current` release 或默认生成链；
- 将 `candidate_ready`、proposal pass 或 materialization pass解释为训练准备完成；
- 用后一次成功覆盖首次失败、失败日志或旧 package fingerprint。

## 2. 环境

使用现有环境：

```text
repository orchestration:
D:\miniconda3\envs\taskgenerator\python.exe

rw-task execution:
D:\miniconda3\envs\real-world-task\python.exe

rw-task repository:
E:\THU\2026Spring\SRT\rw-task
```

`.env` 只作为 runner 的认证输入。不得读取、打印、复制、写入 artifact 或提交。provider output 不保存 raw response。

## 3. 昂贵执行前置检查

每次 provider、solver、grader 或服务器候选执行前依次检查：

1. `git diff --check` 无新格式错误；
2. 完整本地 `unittest` 通过；
3. 固定 Linux/amd64、`network=none`、只读 root、无 provider credentials 的 parity 通过；
4. campaign structural preflight 为 `pass`；
5. source、admission、route manifest、execution policy、brief 和代码指纹未漂移；
6. exact assignments、模型、预算、有效期和排除权限已写入不可执行 authorization request；
7. request 必须落入用户明确授权范围；可由 exact request 批准或当前会话的持续外部调用授权提供 consent，但都必须编译 assignment-scoped receipt；
8. receipt preflight 为 `ready`；
9. 磁盘空间足够，输出根目录不存在冲突；
10. retry、timeout、首错保留和停止规则已确认。

本地完整测试：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe -m unittest discover -s Test -p "test_*.py"
```

固定容器复验：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_reconstruction_docker_parity.py `
  --output-root artifacts/pipeline_reconstruction/docker_parity
```

## 4. Campaign structural preflight

v22 历史 preflight（代码指纹漂移后只读，不得继续执行）：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action preflight `
  --campaign-root artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v22_20260717
```

新建后续 campaign 时，允许进入授权环节的结果必须同时满足：

```text
structural_decision = pass
execution_decision = authorization_required
assignment_count = 12
strict_template_materialized_count = 4
provider_assignment_count = 8
strict_v2_semantic_controls_pass = true
strict_motif_signature_count = 4
hard_blocked_models_absent = true
manifest_fingerprints_match = true
external_calls_made = false
```

## 5. Provider 授权与执行

v7 的四份授权已经消费完毕，不得复用 receipt、追加第三次 attempt 或补做人工 proposal。其正式筛选结果通过以下 report-only 命令生成：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action provider-screening-outcome `
  --campaign-root artifacts/pipeline_reconstruction/route_comparison/r6_formal_public_v7_20260716
```

冻结结果：

```text
decision = redesign_again
strict = 4 / 4
skill_guided_llm = 1 / 4
llm_led_hybrid = 3 / 4
provider_attempts = 13
feedback_conditioned_retries = 0
unconditioned_retries = 5
tokens = 115835
provider_duration_seconds = 1041.827
reserved_cost_ceiling_usd = 26 / 32
```

历史 v16 已执行申请位于（只读示例，不得执行或复用）：

```text
governance/authorization_requests/3e3bd45281008c0883ce2362cee839f2552019524301fb0a83cd544f89db7e94.json
```

它只覆盖：

```text
brief = brief_93974f826477
blind tasks = cmp_cea9e5ebb736a355, cmp_f7a66910d4d89a18
model = gpt-5.6-sol
second attempt = feedback_conditioned_repair
maximum reservation = 8 USD
excluded = solver, grader, professional review, registry, release, promotion
```

该 exact request 已由用户以“授权 v16 policy-application provider slice”批准，receipt 已进入 immutable governance storage。它不得复用于其他 brief、solver、grader 或 mutation。

授权申请保存在：

```text
governance/authorization_requests/<request_sha256>.json
```

每份当前 request 精确覆盖一个 brief 的两条 LLM 路线：

```text
requested_model = gpt-5.6-sol
maximum_provider_cost_usd = 8
maximum_attempts_per_assignment = 2
excluded = solver, grader, professional review, registry, release, promotion
```

新 campaign 获得覆盖 exact request 的用户授权后，不得手工拼 JSON。使用 immutable request 编译 `CampaignAuthorizationReceiptV1`：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action authorization-receipt `
  --campaign-root <new_campaign_root> `
  --authorization-request <new_campaign_root>/governance/authorization_requests/<request_sha256>.json `
  --authorization-id <user-approved-authorization-id> `
  --authorization-statement "<用户对该 exact request 的明确授权原文>" `
  --authorization-expires-at <带时区的未来时间> `
  --output <pending_receipt.json>
```

compiler 只接受 `governance/authorization_requests/<sha256>.json` 下文件名与内容哈希一致的 request，要求当前 campaign 处于初始 `authorization_required`，或处于存在 sequential pending slice 的 `package_generation_in_progress`，并要求全部冻结指纹匹配。它只生成候选 receipt，不接纳 receipt、不执行 provider，也不改变 campaign 状态；随后仍必须通过 preflight。receipt 必须逐字段绑定对应 request、route manifest、source、admission 和 policy SHA，且：

- `authorized_blind_task_ids` 与 request 完全相等；
- `authorized_models = ["gpt-5.6-sol"]`；
- `authorized_scopes = ["provider_proposal_generation"]`；
- `maximum_provider_cost_usd <= 8`；
- 时间戳含时区，未过期；
- release 和 registry mutation 均为 false。

若 `governance/provider_smoke_authorization_request.json` 存在，preflight 还必须在任何状态变更前证明 receipt 的 `authorization_request_sha256` 等于该 active request 文件的内容 SHA。上一 sequential slice 的历史合法 receipt 不得复用；不匹配时必须返回 `authorization_receipt_active_request_mismatch`，且不得写入 active receipt 或改变 campaign status。

执行前先校验 receipt：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action preflight `
  --campaign-root <new_campaign_root> `
  --authorization-receipt <receipt.json>
```

只有 `execution_decision=ready` 才能执行：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action provider-generate `
  --campaign-root <new_campaign_root> `
  --authorization-receipt <receipt.json> `
  --env-path .env `
  --blind-task-id <skill-guided-id> `
  --blind-task-id <llm-led-id> `
  --maximum-assignments 2
```

runner 会把 receipt 复制到 immutable governance storage。每个 authorization ID 独立累计预算，同时累计 campaign 总预算。中断后重新运行相同命令只处理仍具资格的 assignments。第二轮只接受两类首轮：`proposal_blocked` + 可解析 strict `proposal_path`，或 `semantic_proposal_blocked` + 可解析 `semantic_proposal_path`。repair context 必须包含原 strict/semantic proposal、blocking validation/normalization findings、canonical IDs，以及适用的 authority reasons；初始和修复实际 prompt 都必须在 attempt 目录留档且不同。`contract_failed`、`provider_failed`、materialization failure、缺 proposal/draft 或相同 prompt 重发均没有 repair 资格。

停止条件：

- provider 或 schema contract 首次失败且没有持久化、可解析 proposal；
- 当前 authorization 的 8 美元预留上限耗尽；
- campaign 总成本上限耗尽；
- 模型、指纹、receipt 或 assignment identity 不匹配；
- 出现 teacher leak、隐藏 fallback、未授权路径/状态 mutation；
- materializer、content gate 或实际渲染出现 blocking failure。

## 6. Package 审计与盲化

八个 provider assignments 全部 materialized 后，campaign 才能达到 `packages_ready`。逐包检查：

- proposal validation pass；
- hybrid materialization pass；
- deterministic fact anchors 仅由 candidate-visible files 重算；
- DeliverableContract valid；
- visual/openability pass；
- candidate/teacher isolation pass；
- Validity 与 Utility 分轴存在；
- export 仍为 draft，`training_admission_eligible=false`。

随后执行 route-blind staging：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action blind-stage `
  --campaign-root <new_campaign_root>
```

盲包只含 candidate-visible 内容。route mapping、package fingerprints 和 governance evidence 留在隔离目录。

v7 只有 4/8 provider assignments materialized，因此不满足本节入口条件；禁止对 v7 执行 `blind-stage`。

## 7. Solver、grader 与专业复核

provider/materialization 完成不授权 solver 或 grader。v7 已因 package completion 不完整而停止，不得申请其 solver/grader。只有后续 campaign 完成全量 matched packages 后，才可提出新的 campaign-scoped 授权，并冻结：

- weak/medium/strong 三模型 panel；
- 每个模型在同一 environment ID 下的 create/copy/edit/save/submit preflight；
- 每题成本、timeout 和 retry；
- grader model、repeat count 和稳定性阈值；
- generator-independent professional review 方式。

V31 起行为授权必须分两级。第一级只允许 weak/medium/strong 三个候选模型各运行一次通用 `create/copy/edit/save/submit` XLSX fixture，不得读取或上传任何 route-blind task package。申请必须绑定当前 campaign manifest、route manifest、final provider screening、12/12 blind-staging report 和最终 container parity report 的 SHA；容器证据必须为 `network=none`、read-only、无 provider credentials、测试通过且 cleanup 成功。旧 request/receipt、复制到非 immutable 目录的 request、过期 receipt 或任何 fingerprint 漂移都必须 fail closed。

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_behavioral_authorization.py `
  --action request `
  --campaign-root <campaign_root> `
  --panel <behavioral_preflight_panel_candidate.json> `
  --container-parity-report <final_container_parity_report.json> `
  --maximum-total-cost-usd <bounded_cost>
```

未提供 receipt 时，`--action check` 必须返回 `authorization_required` 且三类 call 计数均为 false。取得用户对 immutable request SHA 的 exact 确认后，才可编译 receipt 并再次 check。`ready` 只授权通用 tool preflight；它仍明确排除 task-package upload、business task execution、grader、professional review、registry、release 与 promotion。三个真实 preflight 全部 pass 并由 `freeze-panel` 逐字段复核后，才能生成第二级 business-execution exact request。

V2 首次真实执行还增加两条操作约束：不得把递归找到的任意非空文件视为提交成功，必须核对 `dataset_row.json` 中全部期望相对路径与实际文件集合完全相等；rw-task legacy MD5 子目录只能由受管 wrapper 在 basename 唯一、文件数相等且无额外文件时归一化。执行 CLI 的 `blocked` 或 `indeterminate` 必须以非零退出码传播给自动化。每份新申请使用 `governance/behavioral_preflight_executions/<request_sha256>.json`，不得覆盖或续跑旧申请清单。若保守 request-byte 上界提前阻断，应冻结原预算证据并重新编译新指纹、新预算和新 exact request，不得复用 receipt 或就地放宽。

V3 进一步要求进程 outcome 在 `finish + nonempty + exact path` 后，使用同一 `DeliverableContract` 运行文件可打开性检查；把纯文本改名为 `.xlsx` 必须在 wrapper 返回前失败。事后 preflight 报告仍需独立重读文件并可推翻 raw outcome。V3 strong 的七个 assistant turns 均为空，0 tool calls，虽然 provider transport 与 token usage 正常；它没有进入 E2B，因此不得解释为模型能力失败。历史 `agent_nonconvergence` 保留但当前操作分类为 `model_gateway_agent_protocol_indeterminate`。

兼容性关闭顺序固定为：先离线增加脱敏 response metadata（finish reason、字段存在性、content length、tool-call count、reasoning presence、usage），连续一至两次空 assistant 即 fail-fast；再拆分真实 context window、summarization threshold 与 completion reservation；最后最多申请一次 1–2 call 的同一公共 fixture 探针。若正确 client/protocol 下仍无 tool call，停止适配并选择已知兼容模型。不得用提高 turns/calls、扩大模型矩阵或新增治理 schema 代替该诊断。

solver budget 必须写入 `governance/solver_execution_budgets/<request_sha256>/`，process stdout/stderr 必须写入对应 execution output root 的隔离日志目录；两者都不得使用跨 request 共用的 `<model>` 路径。每次 closeout 前运行 `run_v3_behavioral_evidence_integrity.py`，重算 budget、outcome、stdout/stderr、output tree 和模型/状态身份。integrity pass 只证明证据完整，不代表 preflight 或 panel pass；integrity blocked 则使该 slice 失去 formal evidence 资格，即使其历史诊断仍可阅读。

panel blocked 后先区分真实 tool behavior failure 与 protocol indeterminate。hash-complete pass 可 retain；真实失败成员可进入 replacement boundary，但 protocol-indeterminate 模型必须先完成上述限额式兼容性闭环，不能直接据此降级或替换。保留成员不得为方便而重复调用，Claude Sonnet 4.6 继续硬阻断。

兼容性闭环之后若仍需替补，才使用 `run_v3_behavioral_authorization.py --action request-v3-replacement` 编译全新 request；旧 `8b6c...e65ab` 不得复用。输入包括 admission plan、replacement boundary、retained frozen panel、retained report 清单、retained integrity、候选独立 budgets 和 fresh fixed-container parity。只有用户确认新 immutable SHA 后，才可生成单次 receipt。执行后仍须先生成 integrity report，再合并 final panel；任一 blocked 时不得进入 level-two blind business authorization。

执行顺序：

1. solver tool preflight；
2. solver 真实执行；
3. 精确路径、非空、可打开的 delivery inspection；
4. 仅 valid delivery 进入 grader；
5. 重复 grader observations；
6. 独立专业复核；
7. evidence compiler 检查完整 12-task、3-solver panel。

在 evidence compile 前还必须逐项核验：

- frozen panel 中每个嵌入 preflight 与其持久化报告逐字段相同；
- evidence template 不能直接进入分析；必须在全部行为、grader 与专业复核证据落盘后执行一次显式 freeze；
- frozen evidence input 必须覆盖 comparison manifest、route-blind staging report、solver panel、grader observations、12 组 behavioral reports、professional reviews 及其全部 supporting evidence 的路径与 SHA256；
- evidence input 中的 source export、staged candidate package 和实际 solver input package 必须内容指纹相同；local/server 的绝对路径允许不同，但不得以路径差异替代内容一致性；
- `BehavioralExecutionReport` 中的 solver input package、solver output tree、preflight report 和 delivery inspection 必须与当前文件内容一致；
- 每个 grader output 文件存在且 SHA256 与 observation 声明相同；
- professional review 的每个 supporting evidence path 都真实存在。

任一证据文件缺失、错配或在冻结后被修改，都必须阻断整批 evidence，不能只丢弃单题后继续排名。

不得把进程成功、低分或缺失文件混为一类。`BehavioralExecutionReport` 必须区分 provider、tool、non-delivery、wrong-path、invalid-file、business 和 professional-quality failure。

## 8. Screening、confirmation 与 R7

先从已落盘证据生成可编辑 template：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action evidence-template `
  --campaign-root <new_campaign_root> `
  --solver-panel <frozen_solver_panel.json> `
  --grader-observations <grader_observations.json> `
  --output <route_comparison_evidence_template.json>
```

补齐 template 中 12 个 blind task 的 behavioral/professional evidence 后，显式冻结全部内容哈希：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action evidence-freeze `
  --campaign-root <new_campaign_root> `
  --evidence-input <route_comparison_evidence_template.json> `
  --output <route_comparison_evidence_frozen.json>
```

只有 `evidence_frozen=true` 且完整 evidence compile pass 的输入才能分析：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_comparison_campaign.py `
  --action evidence-analyze `
  --campaign-root <new_campaign_root> `
  --evidence-input <route_comparison_evidence_frozen.json>
```

screening 只能输出 confirmation candidates 或 `redesign_again`，不能直接 promotion。

胜出路线必须在冻结合同下完成 confirmation，包括：

- absolute Validity 和 Utility gates；
- matched environment；
- server candidate reproduction；
- rollback 验证；
- major validity findings closure。

五类 gate 必须分别使用 `v3.route_confirmation_gate_evidence.1`，由 generator-independent evaluator 产出，并为自身 supporting evidence 提供完整 SHA 覆盖。随后编译 artifact-bound confirmation：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_route_confirmation.py `
  --screening-report <route_comparison_screening_report.json> `
  --winning-route <skill_guided_llm|llm_led_hybrid> `
  --gate absolute_gates=<absolute_gates.json> `
  --gate matched_environment=<matched_environment.json> `
  --gate server_candidate_reproduction=<server_candidate_reproduction.json> `
  --gate rollback_verification=<rollback_verification.json> `
  --gate major_validity_closure=<major_validity_closure.json> `
  --output <route_confirmation_report.json>
```

最后的 promotion record 必须重新读取原始 12 条 evidence、重算 screening，并校验 confirmation 及其五类 gate/support 哈希：

```powershell
D:\miniconda3\envs\taskgenerator\python.exe Test/run_v3_reconstruction_promotion.py `
  --screening-report <route_comparison_screening_report.json> `
  --confirmation-report <route_confirmation_report.json> `
  --output <reconstruction_promotion_record.json>
```

`ReconstructionPromotionRecordV1` 的合法结论为：

```text
promote | hold | redesign_again
```

即使为 `promote`，也只表示 opt-in candidate profile 资格；release activation、默认链切换、registry mutation 和训练授权仍为 false，必须另行 review/apply。

## 9. 服务器空间与清理

只有空间不足时才清理本项目过时资源。先只读检查目标和磁盘：

```text
docker system df
du -sh ~/taskgenerator-deploy/releases/* ~/taskgenerator-data/runs/* 2>/dev/null
readlink -f ~/taskgenerator-deploy/current
readlink -f ~/taskgenerator-deploy/previous
readlink -f ~/taskgenerator-deploy/candidate
```

允许删除的对象必须同时满足：

- 明确属于 TaskGenerator；
- 不是 `current`、`previous`、`candidate` 指向的 release；
- 不是当前 campaign、首次失败或 promotion/rollback 证据；
- 已确认本地或服务器 manifest 不再引用；
- 删除路径已解析并位于预期 TaskGenerator 根目录内。

禁止执行全局 `docker system prune`，禁止影响其他项目、Docker daemon、nginx、Minecraft、swap 或防火墙。清理后记录删除对象、释放空间和保留 release。

当前协议探针离线实现已经完成。任何后续请求必须仅包含 `gpt-5.6-sol`、公开 `solver_tool_preflight` fixture、一个 attempt 和最多两个 provider calls；连续两次空响应即停止。该作用域不得上传 blind/business package，不得调用 grader，也不得产生 review、registry、release 或 promotion 权限。旧 request `8b6c6aad...e65ab` 继续保持 `superseded_pre_execution_no_receipt`。

协议探针 request `993d31a4...f37a4` 的 receipt 已消费但未进入 subprocess/provider：执行器在解析 timeout 字段时本地失败，随后 manifest 被标为 `indeterminate`。不得修补或重用该 receipt；修复后必须使用新 fingerprint、parity 和 exact request。

修复后的 request `ea3afe62...aae45` 已消费并关闭：2/2 provider responses 经映射后为空 assistant 形状，零 tool/sandbox/delivery，首错为 `solver_protocol_blocked:consecutive_empty_assistant_responses`；不得重试或扩展该 request。其结论只适用于当前 Tuzi Chat Completions → Stirrup agent 路径。后续工具型 behavioral solver 必须使用通过公开 preflight 的兼容模型，并为任何新的外部 scope 单独申请授权。

Reality cohort LLM review 的执行顺序固定为：验证六个 package fingerprints 与 blind staging；预编译并检查 12 个隔离 payload；完成本地与断网只读容器 parity；编译 immutable request；等待用户确认 exact SHA；创建 receipt；最后才允许调用官方 `deepseek-v4-pro`。receipt 绑定 12 个有效阶段、每阶段最多两次尝试、最多 24 calls/0.25 USD，SDK 自动重试为零。仅 timeout/408/429/5xx、空响应、截断、非法 JSON 或 schema 缺失可补跑一次；必须保存首次输入、原始输出、诊断、failure code 与树 SHA。第二次失败或非白名单失败立即输出 `incomplete`。

Reality request `1dfe222e...32916` 在 provider client 前因 XLSX datetime JSON 序列化失败，冻结为 0 calls 的 `incomplete`；不得重用其 receipt。后续执行器必须在 receipt 消费前后都复核六个 candidate trees、package fingerprints 和 rubric hashes，并使用真实 XLSX datetime 回归测试覆盖 provider payload 序列化。

Reality request `2cff1fa3...ceae9` 在第三个 candidate-blind response 的 JSON 解析失败后冻结：3 provider calls、2 completed reviews，前两条五维均 pass，rubric 未开始。其证据只作 Gemini provider 诊断，不进入新的 DeepSeek cohort。Gemini continuation request `76c34304...d554` 标记 `superseded_model_change`，receipt 编译和执行均须拒绝。DeepSeek 必须从 12 个阶段重新开始，不读取 retained Gemini call trees。

项目级外呼策略禁止 Tuzi `claude-*` 与 `gpt-5.4-pro`。活动 provider 配置、执行入口和 exact-request 编译必须 fail closed；只有用户明确撤销该策略后才能解除，历史记录不改写。

DeepSeek exact request `8d04b2c0...acee0` 已消费并完成：12 completed stages、12 provider calls、0 retries、6 completed cases。结果为 `revise_before_screening`：所有 candidate-blind dimensions pass，但 `cmp_34da237cf93dcc20` 的 rubric-focus 为 revise，指出多个 criteria 复用相同 skill/evidence binding、可能重复计分。不得启动 screening。后续先生成 report-first rubric 去重方案；若应用修订，必须更新 rubric SHA、完成本地/parity、编译只覆盖变更 rubric-focus stage 的新 exact request，并保留原始审查，不得原地覆盖。

Rubric recalibration 不修改 package。先对六题生成确定性 scoring-authority audits，要求恰好七个唯一最终 criteria、21 对完整、binding non-scoring、权重/维度元数据和唯一 failure signals/behaviors 全部通过；再完成本地与固定容器 parity，编译只含六个 `rubric_focus_v3` stage 的 exact request。申请必须绑定原 completed manifest/result、六个 candidate call-tree/review SHA、六个 rubric SHA、audit SHA、structure signature 与 scoring-semantic signature。完整 provider message（system、schema、example、payload）必须低于 12k input ceiling。最多 12 calls/0.13 USD，每阶段仅格式或白名单传输故障可补跑一次；SDK retry 为零。任何相同 semantic signature 下的异结论或 pair 分类差异产生 `reviewer_inconsistency` 并停止，不能选择性修包或启动 screening。

恢复检查点：V2 兼容、Rubric Focus V3、完整消息预算、成本预留、首次失败保存及受控补跑已通过本地 313/313；六份 audit 共同 scoring-semantic signature 为 `1c4ffda4...b9525ec`。任何 current request 必须绑定文档同步后的固定 Linux/amd64 parity；完成 parity 后只能编译 immutable request 并暂停等待用户确认 SHA，不得在同一步创建 receipt 或调用 provider。文档或代码再次变化会使该 request 自动失效并要求重跑 parity。

Request `63a9b799...e0897` 已消费：第一题首轮 pass；第二题首轮与唯一补跑均在 4,000 completion tokens 处截断。冻结 manifest 为 `incomplete`，3 provider calls、1 controlled retry、0.03 USD reserved ceiling，manifest SHA `656c1d50...ead31`。不得重用 receipt、追加第三次尝试或把截断输出解析为实质结论。任何后续 slice 必须先改变输出合同或 completion ceiling，并重新完成测试、文档、parity 和 exact authorization。

后续 slice 使用 Compact V4，不提高 token/cost ceilings。离线预检必须确认六个完整 provider messages 均低于 12k input，标准 pass response 明显低于 4k completion，并验证 `risk_findings` 与 risky pair 一一对应。新 request 版本必须只包含六个 `rubric_focus_v4_compact` stages；旧 V3 receipt 永久不可续跑。完成全量本地和文档后固定 parity 后，只能编译新的 immutable request 并等待用户确认 SHA。

Compact V4 request `f96a2ab6...af1b1` 已消费并完成：6 stages/6 calls、0 retries、0.06 USD reserved ceiling；六题均 pass，pair pattern 唯一且一致，无 risk findings 或 reviewer inconsistency。result SHA=`d2a9dee6...0f840`，manifest SHA=`bb66391e...b2202`。Cohort 可标记 `screening_ready`，但不得复用该 receipt 启动 screening。受限 12 题 matched screening 需要新的输入清单、solver/grader 合同、成本上限、parity 和 exact authorization。

### 两路线 Matched Screening V2

若 generation 返回 completed proposal 但 deterministic content gate 误判，先修复 validator、运行回归和 parity，再把原 proposal materialize 到新的 replay 目录；保留原 package/block，不调用 provider。若首次响应在 normalization 前因 schema 错误失败且没有 persisted draft，则冻结 assignment 为 blocked；旧 receipt 不得补跑。只有新的 `v3.matched_generation_recovery_request.1` 可以对该唯一 assignment 授权一次 replacement call。六个 replicate-B assignments 全部 materialized 前，blind staging 与 Reality request 编译必须 fail closed。

先用 `run_v3_matched_screening_campaign.py --action prepare` 冻结三个 replicate-A briefs、六个已有 package roots、source ledger、Reality result 和 repair-readiness report。prepare 只生成三个 replicate-B briefs及 12-assignment manifest，不调用 provider。文档同步后重新运行完整测试与固定 parity，再用 `--action request-generation --parity-report <report>` 生成唯一 immutable request。未取得该 SHA 的 exact 授权前不得创建 receipt或执行 replicate B。

Generation scope 固定六个 replicate-B assignments、`gpt-5.6-sol`、最多 12 calls、16k completion/attempt、24 USD，且第二次调用只允许持久化 strict/semantic blocked proposal 的 feedback repair。六包全部 materialized 后运行 matched blind staging，并只选择 replicate B 六包进入新的 DeepSeek Reality cohort。任一 Reality 非 pass 时停止。

DeepSeek solver 先运行公共 `create/copy/edit/save/submit` fixture，官方 endpoint、非 thinking tool mode、8 calls、零 retry、1 USD；失败时保存证据并只复用已有 Gemini pass。业务 scope 每题一次 session、12 calls/turns、64k context、8k completion、零 retry。只有 exact/nonempty/openable delivery才调用一次 thinking-high DeepSeek grader。业务 request 必须绑定十二个 package/candidate-tree/Reality hashes、solver selection、parity 和总成本，并继续排除 expert、training、registry、release 与 promotion。

### DeepSeek 公共 Solver Preflight 的授权恢复

已授权 exact request `789f4f85...e742a3` 在 receipt 编译前被发现缺少 matched-screening 专用执行入口，因此该申请标记为 `superseded_pre_execution_no_receipt`：零 provider calls、零私有包上传、零 grader calls，不得补写 receipt 或直接调用 provider。

当前入口复用既有 Stirrup wrapper、`SolverExecutionBudgetV1` 与 `SolverProcessOutcomeV1`，新增 matched campaign 的 exact receipt、单次执行状态和审计报告。执行顺序固定为：同步文档与 source fingerprint，完整本地测试，断网/只读/无凭据 Linux parity，编译新的 immutable request，等待 exact SHA 授权，编译 receipt，最后才允许一次公共 fixture session。执行状态必须在子进程前落盘；中断、崩溃或已有状态均视为 receipt 已消费，不得静默重跑。stdout/stderr、预算、outcome、交付树及首次失败必须持久化，密钥只进入子进程环境并从日志中脱敏。

Request `33fa2c1d...bc061f` 已授权并生成 receipt，但在 provider/solver 子进程之前因 public fixture 缺少 `dataset_row.json` 被阻断，调用数为零。该 receipt 不得在修复后的源码上复用。fixture 必须由 `--action prepare-deepseek-preflight-fixture` 生成完整 dataset root；`request-deepseek-preflight` 会在编译 exact SHA 前使用与 executor 相同的严格文件集和 row 合同验证。

Request `c6e149b5...3bf0f1` 已消费并通过：6 calls、零 retry、0.25901 USD contract cost，DeepSeek 完成全部五类文件操作并提交精确可打开 XLSX。其 report/outcome/log hashes 已编译为 `solver_selection.json`，后续不得重新运行 preflight 或启用 Gemini fallback。

业务阶段固定顺序为：`select-business-solver`（只读审计）→ 完整实现/测试/文档/parity → `request-business-screening` → 等待 exact SHA → `receipt-business-screening` → `execute-business-screening`。业务 receipt 消费前必须复核 12 个 package/tree/Reality hashes。执行后仅有效交付进入 route-blind grader；每题低分、major defect 或 non-delivery 都不得触发 solver/grader 重抽。最终 result 不启动 confirmation。

首份 business request `d9373c88...cb1b9b` 已消费但未进入 provider：12/12 stderr 均为 `no test cases found`，solver/grader calls=0。原因是 wrapper 需要 dataset root，而非直接 case root。该 receipt 永久冻结；新 runner 在 request-SHA 目录内创建每题单 case dataset view，并在子进程前验证 case 数量、blind identity 和 candidate-tree hash。禁止通过修改已通过 preflight 的 wrapper 来掩盖该错误。

Replacement request `f3addd1f...337873` 已消费并完成：12 sessions、56 provider calls、5.22242 USD contract cost、0 valid deliveries、0 grader calls。七条首错为 tool arguments `Unterminated string`，五条为 `contract_cost_reservation_exceeded`；两条路线各 0/6 delivery，result=`redesign_required`，SHA=`5479b333...a69de0`。该 receipt 不得续跑，失败题不得重抽，且本结果不授权 confirmation。后续若研究 solver protocol 或预算映射，必须建立新的窄 scope，并保留本轮作为冻结基线。

## 10. Closeout

只有活跃计划的十项完成定义全部有直接证据时：

1. 更新《项目概要》的最终结论；
2. 同步 AGENTS、架构、接口、production contract 和本 runbook；
3. 将优化计划和详细报告迁入 `docs/archive/`；
4. 验证 active docs 不再依赖已关闭计划维护当前状态；
5. 保留 rollback、fingerprints、成本、首次失败和授权历史。
## Tuzi Codex × E2B compatibility slice

1. Run `Test/run_v3_codex_e2b_slice.py --action prepare` against the frozen matched-screening campaign. Confirm the scope contains only the two approved fan-in task IDs and template `codex`.
2. Run targeted tests, the complete local suite, and fixed Linux/amd64 no-credential parity. Do not execute externally if any gate is incomplete.
3. Execute the generated scope and receipt once. The runner first creates a public synthetic XLSX probe in a fresh sandbox, installs `openpyxl` before credential injection, and invokes one `codex exec` with the key supplied only in `envs`.
4. If the public probe reports any Responses/authentication/event-stream/Codex/E2B infrastructure failure, retain its JSONL, stderr, exit code, sandbox ID, output tree, and first failure; stop before reading or uploading private packages.
5. If it passes, run the two frozen tasks in separate fresh sandboxes. Continue the second task after a task-level delivery failure, but freeze on provider or infrastructure failure. Validate the exact path, XLSX openability, a non-empty sheet, and non-identity with every input workbook.
6. Stop after the slice result. Do not call the grader, run the remaining ten tasks, reinterpret the frozen DeepSeek evidence, or make a route decision.

First execution record: scope `4fa7726c...6fd26` is consumed and frozen `incomplete`. The process failed before sandbox creation because E2B SDK authentication was absent. No private package was read or uploaded and neither Codex nor Tuzi was entered. Do not reuse the receipt. A future slice must bind E2B SDK authentication as process-only secret material separately from the task-level `TUZI_API_KEY`; neither secret may enter commands, config, logs, or artifacts.

Second execution record: scope `fc0e898f...84b72` is consumed and frozen `incomplete`. Explicit E2B SDK authentication succeeded and sandbox `inthikgd5zgob6be7t2tx` was created. The pre-credential runtime preparation command for `openpyxl` exited with code 1, before `codex exec`; consequently no Tuzi credential was injected, no private package was uploaded, and no provider or grader call occurred. Do not reuse this receipt or interpret it as a Responses compatibility result. Any continuation must first determine, offline or with a new public-only scope, the stock template's supported Python package-install mechanism and improve command-failure diagnostics without adding a provider adapter or touching private tasks.

Third execution record: scope `9d3bcb57...f7e2a` is consumed and frozen `incomplete`. The public probe passed with normal Codex turn/command events and a valid non-copied XLSX, establishing Tuzi Responses compatibility without Stirrup or a project provider adapter. `ms_2c770ac494eb53b8` passed the same delivery contract in a fresh sandbox. `ms_7e4e35a9be2befda` then ended with command exit 1 before auditable JSONL or delivery existed and is classified as infrastructure failure. Do not retry under this receipt, grade the successful artifact, execute the remaining ten tasks, or infer route quality. Preserve the public and first-task successes independently from the final cohort-level `incomplete` decision.
## Codex/E2B screening recovery closeout（2026-07-27）

The bounded second-task recovery passed, establishing 2/2 compatibility. The ten-task expansion then exposed systemic Tuzi Responses stream disconnections and a runner bug that had hard-coded one deliverable filename across heterogeneous packages. After correcting per-package paths and transport classification, a nine-task recovery again produced repeated stream/incomplete-body failures; the sixth active task exceeded the 1,800-second contract without the E2B SDK returning timeout, so orchestration was terminated and three tasks remained unrun.

Preserve the three valid deliveries and all first failures. Scope `1f6d2e7b...df4cf` is consumed and frozen `incomplete`; make zero grader calls and do not create another retry scope without a materially different provider transport strategy. This is infrastructure incompleteness, not route-comparison evidence.

## Local Codex CLI 12-task execution

1. Run the local-Codex targeted tests, the complete local suite and the fixed Linux/amd64 parity after the final documentation sync. The parity report must show `network_mode=none`, read-only root, no provider credentials and the exact current source fingerprint. It validates governance only, not ChatGPT/Codex behavior.
2. Install one exact `@openai/codex` version under the ignored tooling directory and persist its package-lock hash, launcher hash and installation-tree hash. Do not use the desktop-bundled executable and do not read or copy `CODEX_HOME/auth.json`.
3. Compile `CodexLocalScreeningScopeV1` from the frozen twelve-task campaign and the final parity report, then compile its standing-authorization receipt. The scope must contain twelve unique cells and both full-package and candidate-projection hashes.
4. Execute the public synthetic probe. Any CLI installation, ChatGPT authentication, service/protocol or local runtime failure freezes the campaign before private workspaces are created. A valid probe must show normal turn and command events and produce an exact, non-copied, openable XLSX.
5. After probe pass, run all twelve tasks in blind-task-ID order. Copy only the candidate-visible projection. Start one `codex exec` process per task, with no automatic retry and a 1,800-second hard timeout. Persist state before process start. Continue after a task-level non-delivery, but freeze on systemic infrastructure failure.
6. Resume only entries still marked `not_started`. Convert stale `running` entries to `interrupted`; never silently rerun them under the same scope. Preserve JSONL, stderr, exit code, usage, duration, output tree and first failure.
7. Grade only valid exact XLSX deliveries using official `deepseek-v4-pro`. One substantive grade is allowed; a second call is only for transport, truncation, invalid JSON or schema failure. Programmatically recompute the seven-dimensional weighted score and do not retry low scores.
8. Apply the frozen matched-screening thresholds and write one of the four screening decisions. Update the overview and evidence report, then stop. Do not automatically start confirmation, training, promotion or release.

Active runner: `Test/run_v3_codex_local_screening.py`. Historical `Test/run_v3_codex_e2b_slice.py` remains readable but is no longer an active solver entrypoint.

First local execution record: scope `af28364d...bdf48` is consumed and frozen `incomplete`. The public probe reached ChatGPT `gpt-5.6-sol` and emitted normal turn/command events, but inherited desktop-host `CODEX_PERMISSION_PROFILE` state overrode the requested workspace-write sandbox and rejected every Python/file-write attempt. No private task workspace was created, no private package was read, and no grader call occurred. Do not reuse the receipt. Any replacement scope must prove that the child environment removes every inherited `CODEX_*` marker except a freshly assigned `CODEX_HOME`.

Scopes `bab6bd1...fdd` and `db1dd24...9e4` are also consumed and frozen. The former failed before a model turn because built-in ChatGPT provider retry fields cannot be overridden; the latter proved that deleting ambient `CODEX_*` variables still leaves the desktop managed read-only policy attached to the child process. A replacement scope must bind `execution_isolation=outer_managed_workspace_codex_danger_full_access`, invoke the nested CLI with `--sandbox danger-full-access`, retain outer managed-workspace and per-task projection boundaries, and reject `--dangerously-bypass-approvals-and-sandbox`.

Completed business record: scope `a23babbc...a3fa0` passed the public probe and all twelve one-shot solver sessions. Both routes delivered 6/6 admitted XLSX files; no solver task was retried and no infrastructure failure occurred. Preserve the execution root `codex_local_screening_v4_outer_isolated/execution` and never rerun or replace these outcomes.

The associated official DeepSeek grader run is frozen `incomplete`: 19 calls used 204,768 prompt tokens, 72,726 completion tokens and about 1,014 provider seconds. Six records completed and six exhausted the only permitted format repair; 12/19 responses ended with `finish_reason=length` at 4,000 completion tokens. Missing grader evidence is not a route defect or zero score. All six completed records scored 1.0, so they also diagnose saturation. Any continuation must be grader-only, reuse the twelve frozen deliveries, compact/calibrate the JSON output contract offline first, preserve every first response, and must not execute Codex, E2B, Stirrup, Tuzi solver, task generation, confirmation, training or promotion.

### Compact Grader V2 continuation

1. Run `Test.test_compact_screening_grader`, the complete local suite and fixed Linux/amd64 parity after final documentation sync.
2. Compile a new grader-only scope with `run_v3_codex_local_screening.py --action compile-compact-grader --solver-execution-root <frozen-execution> --parity-report <final-report> --output-root <new-compact-root>`. The command must make zero external calls.
3. Confirm the scope contains exactly twelve unique route/motif/replicate cells and exact solver-outcome, delivery, rubric and fact-anchor hashes. The source fingerprint must equal the parity report.
4. Execute once with `--action execute-compact-grader --scope <scope> --output-root <same-root>`. The existing ignored official DeepSeek key may be read into memory but never copied or logged.
5. A task receives one substantive score. Only transport, truncation, empty/invalid JSON or schema failure may receive the single format-preserving retry. A low score, finding or major defect is terminal evidence.
6. Stop before F7 unless all twelve grades are present, systematic truncation is absent and the score distribution is not saturated. Regardless of the decision, do not rerun Codex, start confirmation, admit training data or change a generator route.

Compact V2 execution record: scope `ac8fcb1d...ff427b` is frozen `incomplete` with 2 completed, 2 infrastructure-failed, 1 interrupted and 7 not-started tasks. The two completed reviews both scored seven dimensions at 3, yielding weighted score 0.75 with no major defect; this is useful calibration evidence but not a complete cohort. The four failed attempts across two tasks all ended at exactly 2,000 completion tokens with `finish_reason=length` and empty visible content. The interrupted task and seven unstarted tasks must not be resumed under this scope.

The next legal continuation is grader-only Compact V2.1. Keep the compact schema, DeepSeek high-thinking mode, frozen twelve deliveries and one controlled format/transport retry, but set the completion ceiling to 4,000 tokens. After code/test/document synchronization and fresh fixed parity, compile a new immutable scope and regrade all twelve deliveries homogeneously; do not merge the two V2 successes. If systematic truncation persists at 4k, stop and reconsider thinking mode before any further external run. Codex solver, task generation, confirmation and training remain excluded.

Compact V2.1 completion record: source fingerprint `f3d52e54...60271` passed local and fixed Linux/amd64 372/372. Scope `bc38a3d7...3d6f6` completed 12/12 grades with zero infrastructure failure in 16 calls and four legal format retries. Eleven weighted scores are 0.75 and one is 0.70; all twelve are professional-plausibility pass with seven effective dimensions, no major defect and no route identity exposure. The frozen analyzer returns `confirmation_ready_both`, with both routes passing 6/6 offline validity, delivery, productive-complexity and skill-causal gates and all six matched pairs comparable. Preserve `compact_screening_outcome_v2.json`, every review, raw response and first-failure diagnostic; never merge the frozen V2 partial records into this cohort.

Do not interpret `confirmation_ready_both` as route superiority or execute confirmation automatically. Before production expansion, perform one route-blind cross-model professional-calibration sample covering both routes and all three motifs. The second reviewer may compare its criterion-level judgment with Compact V2.1 only after making an independent judgment. Any disagreement is evaluator-calibration evidence, not authorization to mutate a task or rerun a low score. Training, promotion and release remain excluded.

### Six-task cross-model professional calibration

1. Run `Test.test_professional_calibration`, the complete local suite and fresh fixed Linux/amd64 parity after documentation sync.
2. Compile one `ProfessionalCalibrationScopeV1` from the completed Compact V2.1 scope/outcome and final parity. Verify exactly six unique tasks cover both routes and all three production motifs and include both replicate labels.
3. Execute with Tuzi `gemini-3.1-pro-preview`. The key is read only as authentication material from the ignored environment file. Do not persist or print it.
4. Each provider payload contains only the blind task ID, candidate prompt, compact rubric, deterministic fact anchors and actual workbook content. It must not contain route identity, DeepSeek scores, Compact review text, solver logs or other tasks.
5. Permit one substantive judgment and only one format/transport retry per task; never retry disagreement or low scores. Save raw response, diagnostics and first failure.
6. After all six independent reviews are frozen, compare 42 criterion scores programmatically. `calibration_consistent` requires professional-plausibility agreement ≥5/6, major-defect agreement 6/6, mean absolute criterion delta ≤0.5 and maximum absolute delta ≤1.
7. Any result remains LLM proxy evidence with professional validity provisional. Do not mutate tasks, start confirmation, expand production or admit training data automatically.

Pre-provider record: scope `74ec9ac1...d9871` made zero calls and uploaded no task data. Configuration loading stopped because the ignored environment exposes the established `AGENT_*`/`GRADER_*` aliases rather than `OPENAI_*`. The loader now accepts those aliases without rewriting or logging the file, and execution revalidates source, Compact scope/outcome and parity hashes. Because that fix changes the governed fingerprint, never execute the old scope; repeat full regression, parity and scope compilation first.

Second pre-provider record: replacement scope `4ce10cc6...0baf8` also made zero calls and uploaded no data. Runtime byte hashing correctly rejected it because the compiler hashed LF text before Windows `write_text` translated it to CRLF. Scope persistence now uses sorted JSON encoded to canonical UTF-8 bytes with one LF terminator, immutable collision checking and filename SHA over the exact written bytes. Never rename or bypass either failed scope; compile a fresh one after regression and parity.

Final calibration record: canonical scope `920977c2...f01f65` passed local/fixed parity 378/378 at source `e053d45a...d2284` and entered Gemini. Stop conditions were triggered after two tasks each exhausted their one format repair. The frozen state is 0 completed, 2 infrastructure-failed, 1 interrupted and 3 not-started, with 4 calls. All four responses had `finish_reason=stop` and non-empty content, but assigned seven 4s with only two exceptional-evidence records; one response also had an extra brace and one repair omitted `findings`. Preserve all raw responses and diagnostics. Do not resume, reparse the invalid scores as evidence, create a Gemini adapter, switch models in the same scope, or start the production pilot. This is reviewer-contract incompatibility and score saturation, not task or route failure.

### Human domain-expert packet

1. Use only `expert_review_packet_v1_20260731/expert_blind_packet.zip`. Do not send `governance_manifest.json`, route mappings, Compact/DeepSeek scores or solver/grader logs to the reviewer.
2. Before handoff, verify ZIP SHA256 `7b4c11522a7de8dd644f86c8186325112d19f120a8a7115021a89a5a750c9b76`. The untouched blank `expert_review_form.xlsx` SHA256 is `7e2344049e89d0626cc0485972e49d4ab5e6e97e87bab070b4572e103a855859`.
3. Ask one independent domain expert to inspect all six task folders and complete the yellow fields in `Criterion Review`. Every task requires seven 0–4 scores; every 4 requires concrete evidence and every score of 2 or below requires a concrete issue. The reviewer must also complete name/role, independence confirmation and final recommendation fields.
4. Do not expose route or replicate identity before the workbook is returned and frozen. Do not coach the reviewer toward agreement with the automated score.
5. On return, copy the completed workbook to a new timestamped artifact directory; never overwrite the blank form. Record its SHA256 before parsing.
6. Validate six unique tasks, 42 scores, allowed ranges, required evidence/issues, summary formulas and reviewer attestation. An incomplete or malformed review remains `incomplete`; do not silently repair expert judgments.
7. Compare the frozen human scores with Compact V2.1 only after the independent review is complete. Treat disagreement as calibration evidence. Do not rerun low scores, mutate individual tasks, start the production pilot or admit training data automatically.

The packet is retained as optional future evidence. On 2026-07-31 the user explicitly deferred the human-review gate and accepted AI proxy evidence for a bounded production pilot. Do not fabricate a completed workbook or convert this waiver into `expert_evidence_present=true`.

### R8.3 representative production pilot

1. Compile 12 fresh matched briefs covering `audit_compliance` and `procurement_operations`, each crossed with the three production motifs and two scenario replicates. Materialize both reconstructed routes for every brief, for 24 assignments total.
2. Validate the new procurement/operations public sources, extracted skills/capabilities and contamination boundary before any task proposal call. Existing matched-screening packages may inform contracts but must not be copied or counted.
3. Use only the working task-design path (`gpt-5.6-sol`) for proposal generation. Continue to block Tuzi Claude and `gpt-5.4-pro`. A repair is legal only when the existing persisted-draft contract permits it.
4. Require package/content/render/provenance/export-identity checks and route-blind Reality proxy admission before behavior execution.
5. Execute every admitted package once with the pinned local Codex CLI. Do not reopen E2B, Stirrup or solver-provider adaptation.
6. Grade only valid exact XLSX deliveries with Compact V2.1 semantics. Preserve format-only retry boundaries and never rerun a low score.
7. Aggregate delivery, professional plausibility, major defects, duplication, score distribution, route/motif/domain coverage, provider failures and operator time. Infrastructure failures remain incomplete rather than route failures.
8. Stop after the report. The AI-proxy waiver does not authorize expert claims, production release, registry mutation, SFT, RL or any other training.

R8.3 source record as of 2026-07-31:

- `federal_procurement_controls` exact-URL collection: 3 requested, 3 collected, 3 accepted; source-quality pass with no warning.
- First `deepseek-v4-pro` extraction: 6 candidates, 5 accept, 1 revise, 0 reject; registry delta 0; graph-ready with one motif-coverage warning.
- `procurement_award_acceptance_controls` exact-URL collection: 3/3 accepted and source-quality pass. Its only extraction attempt ended with `finish_reason=length` and invalid truncated JSON at the 12k completion ceiling. Preserve that failure and do not rerun it.
- Compile procurement briefs only from the five accepted first-run skills. Map invoice and receiving-report validation to `cross_check_validation`, threshold and competition analysis to `policy_application`, and QA/nonconformance evidence to `fan_in_reconciliation`. This mapping is a planning proposal, not authority: formal brief admission must still prove source, skill, capability and productive-complexity coverage.

R8.3 generation record:

- Formal brief admission is complete at 12/12, with 24 unique route assignments and no registry or training authority.
- Local and fixed Linux/amd64 regression pass 385/385 at source fingerprint `82ae7770...df90`.
- Provider generation completed all assignments in 26 calls: 24 first attempts and two legal persisted-proposal repairs. The repairs both passed; provider/infrastructure failures are zero.
- Freeze the original generation result as `incomplete`: 22 packages materialized, skill-guided 12/12 and LLM-led 10/12. The two blocks are `candidate_output_modeled_as_reference_input` in audit cross-check replicate A and procurement fan-in replicate B.
- Report-first diagnosis confirmed a deterministic false positive, not two task-design defects. The governed references support or require later candidate-authored judgments; they are not candidate outputs. The validator now recognizes only explicit input-to-output relational contexts, while the true output-leak negative control remains blocking.
- Replay only the two preserved proposals with external providers disabled. Both replays must pass the complete materializer, content, provenance, visual, export and isolation gates. Preserve the original failure evidence.
- Compile `RepresentativePilotPackageReadinessV1` from 22 hash-matching original packages and the two eligible replay trees. Continue only when it records 24 unique package fingerprints and `decision=packages_ready`; do not describe the frozen generation result itself as 24/24.
- Run Reality candidate-blind for all 24 cases before any rubric call, then run Compact Rubric Focus V4 for all 24. Bind source package, blind tree, rubric, deterministic audit, parity and governed-source hashes. One format/transport retry per stage is allowed; substantive conclusions are never redrawn. Any incomplete stage freezes the cohort before local Codex.
- The first Reality scope froze before provider entry because its evidence writer received a raw XLSX `datetime`. Preserve its zero-call incomplete manifest and never reuse the scope. A replacement execution must serialize one frozen JSON-safe payload before both evidence persistence and provider submission, then bind a fresh post-fix parity/source fingerprint.
- Replacement Reality completed 24/24 candidate stages and 24/24 Compact V4 rubric stages in 51 calls with three successful controlled length retries. All cases pass, pair classifications are consistent and the cohort is `screening_ready`. Bind result SHA `db897fed...b631` before local Codex execution; do not reinterpret the LLM proxy as expert evidence.
- Representative local Codex scope `3c215519...4852a7` completed the public probe and 24/24 private tasks with valid XLSX delivery, no task/infrastructure failure and no runner retry. Preserve solver manifest SHA `4cf2c7dd...214d4`. Grade all 24 admitted deliveries under one Compact contract; do not rerun any solver process or grade a different file.
- The representative Compact scope uses V3 cohort binding with the unchanged Compact V2.1 score contract. It must contain all 24 unique `domain × route × motif × replicate` cells, preserve every solver outcome and delivery hash, and produce route plus domain summaries. The route gate scales the historical 5/6 thresholds to 10/12 and the saturation ceiling from 4/6 to 8/12.
- Representative Compact scope `5cfeed30...dffe` is consumed and frozen `incomplete`: 22 reviews completed, two infrastructure failures occurred in the same procurement cross-check matched pair, and 30 calls were made. Preserve manifest SHA `b5d51eb0...a90f` and outcome SHA `04eb40a0...f963`. Do not rerun either failed task, truncate the overlong field into validity, impute scores or mix another scope into this cohort. The 22 valid non-saturated reviews are diagnostic evidence; full route convergence remains paused.
- A recovery scope may use Compact V3.1 only: all 24 frozen deliveries are regraded with official DeepSeek thinking disabled, while the rubric, schema, 4k ceiling, zero SDK retry and one format/transport retry remain fixed. Use a fresh output root and manifest. Never copy completed V3 reviews into V3.1 or invoke Codex again.
- Compact V3.1 scope `c4b4c855...61ad` is consumed and frozen `incomplete`: 21 completed, three infrastructure failures and 32 calls. Preserve manifest SHA `398598ff...7c43` and outcome SHA `f56a51dd...0d24`. All failed calls ended normally and exposed schema-invariant or string-length violations rather than truncation. Do not compile V3.2, normalize raw provider text into acceptance, or start route convergence without a revised evaluation decision.
- The revised decision retires DeepSeek grading and permits one homogeneous local-Codex grader cohort. Bind the pinned CLI and all 24 delivery/rubric/fact-anchor hashes after final parity. Use native `--output-schema`/`--output-last-message`, one route-blind process per task and zero retry. Keep workspaces separate from solver workspaces. Mark all output `same_model_behavioral_proxy`; never claim independent-model or expert evidence and do not start training or promotion.
- Local-grader scope `e41ac3b1...51bee` is frozen with zero valid grades: its raw Pydantic schema failed strict Responses validation before reasoning because defaulted properties were absent from `required`. Preserve the five 400 records and interrupted state. A replacement must use the recursive strict-schema compiler, pass fresh parity and start in a new output root; never reuse its workspaces as completed evidence.

Second local execution record: scope `bab6bd17...6dfdd` is consumed and frozen before provider entry because Codex rejects retry overrides for the reserved built-in `openai` provider. There were no private workspaces or model turns. Do not create a custom provider to bypass this limitation. The executable contract is one Codex process per task and zero runner retries; the scope must disclose that internal ChatGPT transport reconnect behavior is owned by Codex and is not user-configurable.

### R8.3 closeout and R8.4 report-only convergence

- Preserve local-grader scope `37a227d9...e9cf`, manifest SHA `e12588f...b1ffa` and outcome SHA `57fd039f...6700` as the sole homogeneous 24-task local-grader cohort. It completed 24/24 with no retry or failure and returned `production_candidate_both`.
- Compile route convergence only from that outcome, its completed manifest/scope chain and `representative_codex_campaign.json`. Recompute all scores, pairs and candidate XLSX projections; do not copy summary numbers from Markdown.
- The accepted report SHA is `0eaa56f1...a2077`: mean-score gap 0.015625, matched wins 6/5 with one tie, and LLM-led footprint 52 workbooks/329,373 bytes versus skill-guided 101/629,370.
- Record `llm_led_hybrid` as report-only production candidate and `skill_guided_llm` as challenger/control. Do not mutate the default generator, registry, release pointer or promotion state.
- R8.5 may now compile a candidate data-admission manifest, but must stop before SFT, RL, reward-model training or any other model update. Keep `expert_evidence_present=false`, `professional_validity=provisional_ai_assumed_sufficient_for_pilot` and `evidence_kind=same_model_behavioral_proxy`.

### R8.5 candidate data admission

- Accepted manifest SHA is `e229994a...6385`, with 24/24 admitted audit records: 12 LLM-led production-candidate and 12 skill-guided challenger/control.
- Before accepting a record, verify campaign/package/Reality identity, completed exact delivery, completed grader review SHA, all offline validity/utility gates, professional plausibility and zero major defect.
- The manifest is not a dataset. Do not copy teacher rubric, fact anchors, Codex JSONL, hidden reasoning or authentication material into any future export.
- Current export count is zero. Do not build SFT JSONL, upload a dataset, run preprocessing for training, fine-tune a model or change a release/default route under this workstream.

### R8.6 external model stack comparison

1. Run targeted tests, the complete local suite and fixed network-disabled/read-only/no-credential Linux parity after documentation sync.
2. Compile one immutable scope with `Test/run_v3_external_model_comparison.py --action compile-scope`, binding the representative campaign, baseline solver/grader manifests, parity and pinned tooling. The user's explicit comparison authorization permits automatic receipt creation/consumption.
3. Execute with `--action execute`. Gemini runs first, DeepSeek second. Each stack first receives only the public fixture; a failed probe must leave all 24 private task records `not_started`.
4. For a passing probe, run all 24 task processes once. Persist redacted JSONL/stderr, usage, duration, exact delivery inspection and first failure. Freeze a stack after three consecutive identical infrastructure codes; never build a fallback adapter.
5. Run `--action grade` only after solver execution reaches a terminal state. Missing or invalid deliveries are `not_eligible` and receive zero grader attempts. Valid deliveries receive one local Codex structured grade.
6. Run `--action aggregate` to combine the frozen GPT baseline with external solver/grader evidence. Report overall, domain, motif and common-task pair metrics; do not impute missing scores.
7. Stop after the report. Do not switch the default solver, modify the route recommendation, export training data, train a model, activate a release or promote a provider.

Frozen R8.6 outcome:

- Pre-execution local and fixed Linux/amd64 parity: 411/411; source fingerprint `65a44da5...c6db0`.
- Scope: `1e4577de...16cc4`, consumed once.
- Gemini: public probe failed with a high-demand service error; zero private task workspaces/uploads; 24 tasks remained `not_started`.
- DeepSeek: public probe passed; six private tasks attempted; every raw terminal error was `stream disconnected before completion`; zero normal completions and zero grader-eligible deliveries; stack froze and eighteen tasks remained `not_started`.
- Aggregate: `comparison_incomplete`; do not construct a model ranking because neither external stack meets the 20/24 capability or 20-pair floor.
- Preserve the original outcomes. The initial five `authentication_failure` labels were a classifier false positive caused by candidate task text containing authorization/status-code terms. The corrected classifier uses only terminal error events and stderr; this changes no external call, delivery count, infrastructure count or final decision.

### R8.7 official DeepSeek × OpenCode execution

1. After final documentation sync, run the complete local suite and the fixed network-disabled, read-only-root, no-credential Linux/amd64 parity. Compile no scope from an earlier fingerprint.
2. Compile one `OfficialDeepSeekOpenCodeCampaignV1` with `Test/run_v3_official_deepseek_opencode.py compile`; its receipt is created from the user's explicit campaign authorization and consumed once by `execute`.
3. Read `deepseek-key.txt` only into process memory. Pass it only as `DEEPSEEK_API_KEY` to the OpenCode process. Read the E2B key from the ignored `.env` and pass it only to the E2B SDK. Abort if either secret appears in persisted text.
4. Run public official-provider probes first: `/models` must include `deepseek-v4-pro`, and a streamed public tool call must complete its tool-result continuation. Failure means `official_provider_incomplete` and zero private upload.
5. Inspect E2B's official `opencode` template without the DeepSeek key. Prepare Python/openpyxl in the public sandbox. Run one public XLSX agent probe. Use WSL Ubuntu only if E2B/template/runtime infrastructure fails; never switch environments after a business task result.
6. Run `rp_003152533de5b652` and `rp_fb0d66050783b08e` first. Both must finish normally and pass exact XLSX admission before the other 22 tasks start.
7. Run each remaining task once in a fresh sandbox/workspace. Continue after an isolated business failure, but freeze after three consecutive identical infrastructure failures. Resume only `not_started`; preserve `running` as `interrupted`.
8. Grade only normally completed valid deliveries with `grade`; each gets one local GPT structured review and low scores are never redrawn. Aggregate against the frozen GPT baseline with `aggregate`.
9. Stop after `official_deepseek_comparison_ready`, `official_deepseek_partial` or `stack_incomplete`. Do not change the default solver, route recommendation, training data, release or promotion state.

First-run recovery note:

- Preserve consumed scope `5a8d5bb7...e1835` as `stack_incomplete`: official provider probe passed, both public environment candidates failed, and all private tasks remained `not_started`.
- Do not treat the run as a DeepSeek or OpenCode failure. E2B inspection propagated the expected missing-openpyxl import status before installation; WSL received an invalid positional path.
- The replacement runner must terminate the diagnostic command successfully, then install openpyxl in a public venv, and must quote concrete WSL paths rather than `$1`/`$2`. Complete full regression and parity before compiling a new scope.

Frozen replacement outcome:

- Scope `56c134a0...ed8a6` selected E2B official `opencode` template with OpenCode 1.17.13 after official provider and public XLSX probes passed.
- The matched pair passed 2/2. Preserve all original task outcomes; do not rerun any solver task.
- Run `audit` before final aggregation. The accepted audit prefix ends at `rp_44ce4deec29d8311`: seven passes followed by three `service_or_stream_failure` records. Mark the later fourteen attempts `out_of_scope_after_freeze`.
- Preserve the seven one-attempt grader records: three completed and four infrastructure-failed. Do not retry the four DNS/stream failures and do not impute scores.
- Aggregate only with the audit file. The final decision is `stack_incomplete`, common graded count is three, and the pairwise decision is `insufficient_common_coverage`.

### R8.8 network-recovery execution

1. Keep every R8.7 artifact immutable. Create a new output root, scope and receipt after documentation-synchronized local regression and fixed parity.
2. Start from the public official-provider and E2B/OpenCode XLSX probes. Do not reuse the earlier environment-selection record as an execution pass.
3. Execute all 24 private tasks from new workspaces. The matched pair remains first and must pass 2/2. Apply the corrected DNS/stream classifier online and freeze after three consecutive identical infrastructure failures.
4. Always run the immutable execution audit before grading or aggregation. Any post-freeze attempt is excluded even if it produced a file.
5. Create a new grader output root and grade every valid in-scope delivery once. Do not import R8.7 reviews and do not retry transport failures or low scores.
6. Require at least 20 valid deliveries, complete grading of every valid delivery and at least 20 common GPT pairs for comparison readiness. Otherwise close as incomplete/partial and do not launch a third campaign automatically.
7. The governed parity uploader uses compressed `scp -C` with a 600-second transfer ceiling. This changes transport tolerance only; snapshot selection, fixed image, network-disabled/read-only execution, credential exclusion and exact project-directory cleanup remain unchanged.

Frozen R8.8 outcome:

- Transfer-hardened pre-execution evidence passed 11/11 targeted tests, 421/421 full local tests and 421/421 fixed Linux/amd64 parity; source fingerprint `4bb8c702...75e65`, parity report SHA `8b1e9012...7f53b`.
- Scope `eb3c3960...50506` was consumed exactly once. Official provider, E2B/OpenCode public XLSX and matched 2/2 gates all passed.
- Solver execution completed 24/24 new sessions and admitted 24/24 exact valid XLSX deliveries. Execution SHA is `05dd9d2a...d452`; audit SHA is `ea7c3265...469c`, with 24 counted records, no freeze point, no post-freeze attempt and no governance breach.
- Grading completed once for each of the 24 valid deliveries. Grader manifest SHA is `630413f1...0bad`; do not rerun or replace any score.
- Result SHA is `ea2a5163...ef8d`: `official_deepseek_comparison_ready`, practical winner `gpt_baseline`. GPT wins 22 common tasks, DeepSeek wins one and one ties; paired mean delta is 0.157812. DeepSeek has six major defects and 14/24 professional-plausibility passes despite 24/24 delivery.
- Stop here. Preserve R8.8 as the accepted comparison evidence. Do not launch a third automatic campaign, switch the default solver, change the route recommendation, export training data, activate a release or promote a provider.

### R9 Huago-cone production run

1. Work on `codex/r9-huago-cone-production`. Run the full suite and secret scan, stage explicit governed paths, inspect and commit. Never use `git add .`; exclude env, keys, auth, artifacts, logs and the local legacy `Test/` directory.
2. Run `taskgen-release --action prepare`, then `taskgen-release --action deploy --host huago-cone`. Install only minimal secrets with `--action secrets`; existing Codex auth stays a mounted secret. If invalid, the user runs `codex login --device-auth`.
3. Run `--action parity` and `--action smoke`. Only both passes permit `--action activate`. Use `--action status` and `--action rollback` for operations.
4. In factory, run `taskgen-produce --action collect`, then `taskgen-produce --action build-substrate`. The latter owns HTML visible-text normalization, two domain-specific Tuzi extraction calls, deterministic review and the scratch registry. It must record unchanged canonical-registry hashes and at least three accepted source/block-grounded skills per domain; no fallback extractor is permitted. Bind its accepted-candidate outputs with `--action compile-briefs`, then `--action compile` and `--action generate`.
5. Preserve first failures; only persisted strict/semantic findings receive the one conditioned repair. Continue for ten ready or the allowed 8–9 partial cohort.
6. In eval, run public probes for GPT/Codex, official DeepSeek/OpenCode and Gemini/Tuzi/OpenCode. A failed probe causes zero private upload. Run one audit and one procurement canary before remaining tasks.
7. Grade valid deliveries once with both judges. Only format/transport failure may receive one formatting retry; never redraw low scores. Aggregate, publish internal reports, update the active release record and stop.

Fresh reproduction rule (2026-08-26): run `r9_huago_cone_fresh_reproduction_10_20260826` in a previously absent run root. Re-fetch all six allowlisted pages and regenerate skills, briefs, blind IDs and packages; reuse only code, URL allowlist, model policy and 5+5/4+3+3 schedule. Require 10/10 materialized packages before private solver upload. A generation-side code repair requires a new release and new source-to-package campaign; an evaluation-only repair keeps package fingerprints frozen but restarts the affected full solver or judge stack. Do not modify a task, rubric or answer in response to model scores.

For a provider-backed production generation, launch the server container detached and poll its named container plus the persisted result file; a transient SSH session must not be the process lifetime. `generate` converts `SIGTERM`/`SIGHUP` into an `interrupted` case record and refuses to resume that run silently. Preserve the interrupted run as diagnostic evidence and start any from-zero reproduction under a new run root.

If a provider response is valid JSON but cannot instantiate even `TaskDesignSemanticDraftProposalV1`, retain the raw-response hash, diagnostics and normalization findings. It may use exactly one same-input **format retry**; it has no proposal and therefore cannot consume feedback-repair authority. Any other broad contract failure remains non-retryable.

Fresh-reproduction execution freeze (2026-08-27): r1 is an SSH-lifecycle interruption diagnostic; r2 is a 9/10 schema-invalid provider-output diagnostic; r3 has 9/10 materialized packages but its final provider request exceeded the configured 15-minute task-design limit without returning. The detached container was stopped with `SIGTERM`; the runner persisted the case as `interrupted`, proving that it does not silently resume. The two allowed correction releases have been consumed. Preserve all three run roots, do not upload their partial private packages, and do not create r4 or any evaluator campaign. Resume only after a new approved plan addresses provider-client timeout enforcement below the process layer.

Timeout-enforcement resumption (2026-08-28): the user reopened the work after the r3 diagnostic. The old freeze still protects r1–r3 and their partial packages, but no longer prohibits a new reproduction. Before creating r4, the task-design exchange must run with `max_retries=0` and, on Linux in the main production thread, a 900-second `SIGALRM` deadline around the SDK call. A deadline exception is classified as `provider_failed/timeout`; it may consume only the pre-existing single same-input format/transport retry. It cannot create a repair prompt, reuse a partial package, or extend the call deadline. After source/test/parity/release checks, create a previously absent run root and repeat the entire source-to-package chain. Do not start solver or judge execution unless that new cohort is 10/10.

Frozen first-run outcome (2026-08-17):

- Release commit `d70be7da0589caca4353f1a011e22642984f4d49` is active as `milestone-r9-huago-cone-094cbe481df3`. Local/final parity is 429/429, secret scan found zero exact leaks, factory/eval smoke passed, and 137 GiB remains free.
- Preserve run `r9_huago_cone_first_production_10` and its six fresh official-source hashes. Scratch skill review did not mutate the canonical registry. The procurement extractor used local Codex only after the existing Tuzi extractor and official DeepSeek fallback failed on public source text; all five resulting candidates passed the existing deterministic reviewer.
- Preserve generation result `production_insufficient`: 10 normal task-design calls, 7 materialized, 3 `InternalServerError`, zero unconditional redraw. The failed task IDs are `prod_579e378937b75d7c`, `prod_951abfa7ee1b6fb3` and `prod_1323bd30303e8f30`.
- Preserve generation result SHA `f87b600c...bbb36` and `production_package_integrity_report.json` SHA `c47fb50e...e9d10`: 7/7 package reports pass and 31/31 candidate XLSX files are openable, nonempty and byte-identical to rw-task export copies.
- Stop before step 6 because the cohort has fewer than eight packages. No model probe, private solver session, grader call or comparison record exists for this run. Do not retry the three tasks inside the consumed run, import historical packages, or lower the threshold. A future attempt requires a new homogeneous production campaign and an explicit provider choice.

Recovery production outcome:

- Campaign `r9_huago_cone_recovery_production_10` reuses only the frozen public source/skill/brief inputs. It has ten new blind IDs and imports no proposal, package or result from the 7/10 run.
- Preserve cohort SHA `77e7835f...15b6bd`, generation SHA `0d519c5d...91812` and integrity SHA `37c31a1b...1ba16`. Ten normal calls produced 10/10 first-attempt materializations, and all 39 candidate XLSX files pass openability, nonempty-content and candidate/export identity checks.
- Treat this recovery cohort as the only R9 evaluation cohort. Never merge the first campaign's seven packages.
- Run every server solver through `taskgen-evaluate`. The public probe must pass before `solve`; a canary infrastructure failure stops expansion, while three consecutive later infrastructure failures freeze the stack. Persist only secret-redacted stdout/stderr.
- The pre-run manual GPT public probe passed. The manual DeepSeek probe timed out with no events or delivery and uploaded no private task. The manual Gemini probe failed before model entry because CRLF env substitution made the OpenCode config invalid; its credential-bearing stderr was immediately cleared. Do not reuse the shell probe. Rotate the Tuzi key and use only the tracked in-memory-redacting runner after the replacement release passes parity.

Final pre-private state:

- Current release is `milestone-r9-huago-cone-5d8f76146a38`, source `5d8f7614...3b35a`, commit `4e01a66`; local/fixed parity is 432/432 and smoke passes. Previous release remains selectable and free disk is 127 GiB.
- Fresh tracked public probes pass for all three stacks: GPT/Codex 24.096s, official DeepSeek/OpenCode 35.950s, Gemini/Tuzi/OpenCode 52.714s. Every probe has empty stderr and an exact valid XLSX.
- No recovery private task had been submitted at the pre-private snapshot. The user subsequently gave explicit campaign-specific authorization for all ten route-blind packages, all three solver destinations and both GPT/DeepSeek judges. Do not request another per-stage SHA; first publish the 435-test dual-judge release, then run fresh probes, cross-domain canary, remaining solver sessions, both judges and deterministic aggregation.
- `grade` receives one solver campaign and one judge identity. It stages only candidate requirements, frozen rubric, deterministic fact anchors and the valid delivery; it removes temporary Codex authentication links after the process. `compile-evaluations` accepts a mapping of the three solver manifests and their two bound judge manifests, verifies every hash/task identity and writes the sole input for `--action aggregate`.

R9 completed operational closeout (2026-08-19): `milestone-r9-huago-cone-6c3ae7f21ba6` is `current`, `milestone-r9-huago-cone-5d8f76146a38` is `previous`, and the server has 122 GiB free. The release passed local and fixed-container 435/435 parity, network-disabled/read-only/no-credential parity, and both image smokes. Recovery production remains 10/10 package-ready with 39/39 valid candidate workbooks. All three tracked probes, canaries and ten-task solver runs passed: 30/30 valid deliveries, zero provider/infrastructure or business-delivery failures.

All six `v3.r9_judge_manifest.1` files completed at 10/10; `compile-evaluations` verified their solver/generation/review hash bindings and produced `/data/runs/r9_huago_cone_model_comparison_v3/aggregate/evaluation_records.json` (`df0be942...de84`). `aggregate` then produced `production_model_comparison_result.json` (`2a3b4f0c...b9a3`): decision `comparison_complete`, discrimination `usefully_discriminative`. Do not rerun solver or judge sessions. Treat the host-visible `/home/huagosr/taskgenerator-data/runs/...` as the mount backing container-visible `/data/runs/...`; use the latter only inside the container. No result authorizes training, default-solver mutation, public release or promotion.
