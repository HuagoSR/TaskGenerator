# Milestone F 财务审计首轮正式任务生产收口

> 状态：`production_completed_awaiting_eval_design`

服务器 release `milestone-f-data-production-6304e84` 已完成正式财务审计任务生产。四波规模为 `5 + 15 + 20 + 20 = 60`，candidate-ready、verifier pass 和 rw-task export compatible 均为 `60 / 60`；fan-in、cross-check、policy application 各 20，主交付物为 40 个 XLSX 和 20 个 DOCX，QA blocked 为 0，跨四波 candidate-visible reference SHA-256 重复组为 0。

原始 Wave 1 的自动结构门槛虽然通过，但逐题审查发现通用参考表、跨题重复、任务语义与数据字段脱节、GoldenRun 不可重算以及 DOCX 页尺寸缺失，因此未扩产。修复限定在 `finance_production_v1`，改用现金对账、三单匹配和费用政策数据合同，生成确定性 answer key，并加入 reference hash 阻塞门禁。Wave 1B 通过后才放行后续三波。

所有生产容器 ExitCode=0，未发生 OOM；canonical registry SHA-256 保持 `7329e377...fc7`。GDPVal 隔离审计为 pass，task ID、prompt、reference hash 和连续 12-token 命中均为 0。未执行 rw-task eval preparation、外部模型答题或 grader。

11 个 Wave 1B XLSX reference workbook 已完成渲染检查；DOCX 已验证正文、可打开性和标准页尺寸。本机标准 DOCX 像素渲染因缺少 LibreOffice 未完成，这是审查工具环境限制。

结论固定为 `production_completed_awaiting_eval_design`。这批任务证明系统可以稳定批量形成结构合格、可重算、可导出的候选任务；尚不能证明训练价值或 benchmark 权威性。下一步单独设计不同模型执行差异评测，不自动开始 SFT/RL。
