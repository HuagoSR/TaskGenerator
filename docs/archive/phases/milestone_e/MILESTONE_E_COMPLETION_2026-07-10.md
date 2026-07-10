# Milestone E 仓储库存运营垂直切片完成报告

> 状态：`historical / completed`
>
> 项目级状态源：[`../../项目概要.md`](../../项目概要.md)
>
> 本文职责：记录里程碑 E 的最终实验合同、离线证据、真实 LLM 证据和服务器激活结果。

## 决策与边界

第二领域固定为 `warehouse_inventory`，职业锚点是 Shipping, Receiving, and Inventory Clerks。生成来源只使用 O*NET 和 FEMA 的公开材料摘录/结构化转述；GDPVal 只用于离线 aggregate taxonomy/file-type 审计和生成后的隔离污染检查。

本工作流禁止将 GDPVal prompt、rubric、附件或 URI 输入生成进程；禁止 web collection、私有来源上传、外部任务评测，也不得将 mock extractor 结果作为研究质量证据。真实公开来源 LLM 验收前不激活服务器 release 或宣称里程碑完成。

## 实现合同

- 统一入口新增冻结字段 `domain_profile / domain_profile_path / motifs`。
- profile registry 固定 `finance_audit` 和 `warehouse_inventory`；finance profile 保持旧行为。
- warehouse profile 使用 `fan_in_reconciliation / cross_check_validation / policy_application`。
- warehouse 输入限定 XLSX/DOCX/MD/TXT，输出限定 XLSX/DOCX。
- local-source normalizer 自动附加 profile domain tags。
- seed、prototype、production runner 和 teacher/verifier 链支持领域中性的文件名与 policy evidence。
- canonical registry 不参与 mutation；所有新技能进入 run-local scratch registry。

## 公开来源

| 来源 | 用途 | 本地材料 |
| --- | --- | --- |
| O*NET 43-5071.00 | 岗位职责、收发记录与差异处理边界 | `Test/v3_warehouse_inventory_source/onet_warehouse_clerk.md` |
| FEMA Distribution Management Plan Guide 2.0 Appendix F | 入库、出库、数量及位置记录结构 | `Test/v3_warehouse_inventory_source/fema_inventory_management.md` |

`source_manifest.json` 记录 URL、出版方、页码、获取日期和内容 SHA-256。标准运行读取冻结 Markdown，不在线抓取 PDF。

## 离线证据

权威 warehouse run 为 `artifacts/milestone_e_runs/milestone_e_warehouse_offline_02/`。

| 指标 | finance control | warehouse inventory |
| --- | ---: | ---: |
| candidates | 4 | 4 |
| accepted | 4 | 4 |
| sample-ready | 3 | 4 |
| generated cases | 3 | 3 |
| candidate-ready | 3 | 3 |
| verifier pass | 3 | 3 |
| export compatible | 3 | 3 |
| QA blocked | 0 | 0 |
| eval prepared/executed | 1/0 | 1/0 |

Warehouse content fingerprint 为 `f4091ea1ee548b245fffc15b4c34cc71d5db7d1c51a6d90a3f7e3d28d638bab3`。Milestone C compatibility regression 继续得到 `722497164acf1138bbfccd4975e9a0ed75ddf7adbc463738b3c90b9ab6881173`。

污染台账结论为 `pass`：task ID、GDPVal URI、prompt hash、reference-file hash 和连续 12-token 指纹均无命中。warehouse artifacts 中也没有 profile 禁止的 finance/audit persona 词汇。离线比较只允许表述为 `offline_vertical_slice_passed`，不能扩张为广泛跨领域泛化。

## Docker candidate

授权前 candidate 已构建并部署，但未激活：

```text
release_id = milestone-e-ed0568e
source_commit = ed0568e3e56fa725858d6c33e0cfb04bbec043d8
image_archive_sha256 = b8cbd71e12de43f933083615821fdf6f84ab4676167d7bae549bb89ac2e615ed
archive_config_digest = sha256:d1e51a5442f2e1f5410674c5b4bdffbbe4b8bb9a286975af77891d1eab18c4f6
server_runtime_image_id = sha256:9f3f731c2492999a2a547b9a34fdea0d6682aa41e725a594f2106d60e0b5faf5
```

本地和服务器读取的是 SHA-256 完全一致的 image archive，其 manifest config digest 均为 `d1e51a...c4f6`；服务器 Docker 29 load 后报告了不同的 runtime image ID，作为激活前待解释诊断保留，不用结果 fingerprint 掩盖。候选的本地/服务器旧 public smoke 均复现 `722497...1173`，本地/服务器 warehouse smoke 均复现 `f4091e...bab3` 和 `4 / 4 / 4 / 3 / 3 / 0 / 1 / 0`。

服务器 symlink 保持：

```text
current = milestone-d-094c6cb
candidate = milestone-e-ed0568e
```

nginx 与既有 Minecraft 容器未重启，未新增端口。

## 真实公开来源 LLM 验收

用户已单独授权公开 source prompt package 的 DeepSeek official extraction，并允许一次同配置重试。首次运行即成功，未消耗重试额度：

```text
model = deepseek-v4-flash
output_profile = bounded_smoke
max_candidates = 4
max_tokens = 6000
web_collection = false
external_eval = false
mock_fallback = false
```

真实运行 `milestone_e_warehouse_llm_01` 得到：

| 指标 | 结果 |
| --- | ---: |
| candidates / accepted / sample-ready | 4 / 4 / 3 |
| generated / candidate-ready | 3 / 3 |
| verifier / export compatible | 3 / 3 |
| QA blocked | 0 |
| eval prepared / executed | 1 / 0 |

Provider 诊断：

```text
provider = deepseek
model = deepseek-v4-flash
finish_reason = stop
response_chars = 13364
prompt_tokens = 3446
completion_tokens = 4231
total_tokens = 7677
likely_truncated = false
response_sha256 = 30bd63239c3fe9cfe1bb42995c53d59816dcc1e40b7ba222a363676760d7d004
```

External-effects ledger 仅有 `external_source_upload=true`、`llm_extraction=true` 和 `eval_preparation=true`；`web_collection=false`、`external_eval=false`。真实 LLM artifacts 再次通过 GDPVal 污染审计，真实 key 扫描命中数为 0。

## 最终决策

```text
milestone_e_status = completed
domain_slice_decision = warehouse_inventory_vertical_slice_passed
broad_cross_domain_generalization_claim = false
server_release = milestone-e-ed0568e
next_milestone = F_training_data_readiness
```

`milestone-e-ed0568e` 已原子激活为服务器 `current`，`milestone-d-094c6cb` 保留为 `previous`。没有重启 nginx/Minecraft，没有新增端口。里程碑 E 只证明一个受控第二领域垂直切片成立，不代表多领域或训练价值已经得到验证。
