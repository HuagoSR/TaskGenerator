# Milestone F4.2 八题生命周期索引

> 状态：`historical / sanitized index`

统一服务器根目录：`/home/huagosr/taskgenerator-data/runs/finance_f4_from_scratch_validation_02`。

| Slot | Motif | 最终 revision | Pipeline manifest SHA 前缀 | Holistic evidence SHA 前缀 | Assistant review SHA 前缀 |
| ---: | --- | --- | --- | --- | --- |
| 1 | fan_in_reconciliation | 02 | `4d432cef` | `0576b546` | `d6efb81b` |
| 2 | cross_check_validation | 02 | `491b432a` | `8d6e1dca` | `c4c9fe85` |
| 3 | policy_application | 01 | `12098800` | `1877a939` | `4e7ad6ea` |
| 4 | evidence_to_deliverable | 01 | `5e446773` | `0c6fde83` | `78365c9f` |
| 5 | fan_in_reconciliation | 01 | `fd9012ac` | `102dc504` | `030cc930` |
| 6 | cross_check_validation | 01 | `130ed923` | `0ba9e402` | `8d6af913` |
| 7 | policy_application | 01 | `c5ea0e39` | `8d80af7d` | `4fcd8cb5` |
| 8 | evidence_to_deliverable | 01 | `9736e2f3` | `6bb8e0e9` | `c1d3ccfd` |

每个最终目录均包含且按 checksum 关联：初稿指纹、Terra revision bundle、物化后的 candidate/teacher 包、deterministic answer key、visual QA、Luna candidate-blind 结果、assistant review、verifier 与 rw-task export。完整路径和原始内容仅保留在 ignored artifacts。

