# Milestone E 仓储库存运营垂直切片

> 状态：`active / awaiting_external_authorization`
>
> 项目级状态源：[`../../项目概要.md`](../../项目概要.md)
>
> 本文职责：记录里程碑 E 的局部实验合同、离线证据和下一授权门。

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

## 下一授权门

下一步需要用户单独授权一次公开 source prompt package 的 DeepSeek official extraction，并允许一次同配置重试：

```text
model = deepseek-v4-flash
output_profile = bounded_smoke
max_candidates = 4
max_tokens = 6000
web_collection = false
external_eval = false
mock_fallback = false
```

只允许上传 O*NET/FEMA 公开 source package；生成任务包、GDPVal 和私有材料不得上传。真实 LLM 验收通过后才能激活 candidate release、归档本文并将路线切换到 F。
