# Milestone F4.2 系统修复记录

> 状态：`historical`

本轮坚持“发现重大问题先修共性流程，再重做同一槽位”，没有通过换题规避失败。

| 问题 | 暴露位置 | 系统级修复 | 结果 |
| --- | --- | --- | --- |
| 整体编辑建议不能安全落地为文件 | 旧 blocked campaign / slot 1 | 新增受限 WholeTaskRevisionBundleV2 和 XLSX/DOCX/JSON 物化器；版本化写入并拒绝路径穿越、宏、嵌入对象和超限结构 | 新 campaign 8/8 均形成完整 revision |
| 通用模板回退、请求不存在模板、teacher/rubric 跨模板残留 | slot 1 初始版本 | 绑定 finance semantic profile；prompt 只引用实际存在文件；teacher/rubric 从最终合同与重算 truth 重建 | slot 1 revision_02 通过 |
| 三单匹配模板可读性差，rubric 只核验计数，prompt 出现字符损坏 | slot 2 revision_01 | 增强宽表渲染与已知文本规范化；resolver 保存逐发票事实；fact rubric 核验每行数量、价格、重复和状态 | slot 2 revision_02 通过，slot 6 首次通过 |
| 最终镜像复验最初把 resolver 最小 truth 与 richer answer key 做全对象相等比较 | 收口复验 | 改为逐 claim、允许 answer key 含额外审计明细的子集比较 | 最终 candidate 8/8 复验通过 |

这些修复都落在 adapter、materializer、resolver、rubric builder 或验证器上；原始失败证据未覆盖。

