# 历史文档归档

> 状态：`historical index`

本目录保存已经完成或被替代的计划、handoff、阶段报告和早期架构材料。归档文件用于追溯决策，不承担当前项目状态管理职责，原则上不再更新正文。

## 目录

- `foundations/`：旧 V2/V3 roadmap、Pipeline B completion plan、旧 global plan、schema 历史和 Pipeline A handoff。
- `phases/phase11/`：candidate-ready quality closure。
- `phases/phase12/`：hardening、negative controls 和 executed mini-campaign。
- `phases/phase13/`：finance/audit production MVP。
- `phases/phase14/`：GDPVal calibration 和 LLM shadow evidence。
- `phases/phase15/`：generator reform 与 Phase 15B `hold_for_redesign`。
- `phases/phase16/`：Contract V2 redesign、真实四案例评测和 `redesign_again` 收口。
- `phases/milestone_c/`：本地端到端自动化、Manifest V2、恢复测试和 public smoke 收口。
- `reports/`：早期阶段性报告、Phase 14 报告和配套图片。

## 使用规则

- 当前项目状态以根目录 `项目概要.md` 为准。
- 同一阶段存在 blocked、success 和 completion 多份材料时，以该阶段最终 completion 文档为准。
- `superseded` 文档只解释当时的执行状态，不能覆盖后续结论。
- 历史 runner 重新运行时必须写入 `artifacts/historical_phase_runs/`，不得覆盖本目录。
