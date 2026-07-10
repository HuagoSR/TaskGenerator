# Milestone C Local End-to-End Automation Plan

> 状态：`historical / completed`
> 日期：2026-07-10

## 目标

在不新建平行流水线的前提下，将既有 `v3_end_to_end_pipeline` 收敛为 scratch-first、可恢复、可重复、默认无外部评测的本地统一入口。

## 实施合同

- actions：`run / resume / status / rerun`；
- profiles：`public-smoke-offline / public-smoke-llm / local-existing / local-source / web-source / custom`；
- stages：`source_to_skills → registry_prepare → task_generation → production_review → rw_task_eval(prepare_only)`；
- registry：`fresh_scratch / snapshot_scratch / existing compatibility`；
- Manifest V2：冻结 request、atomic write、attempt、checksum、relative artifact index、external-effects ledger；
- outputs：acceptance report、training-candidate index、single-task lifecycle index；
- default boundary：external eval disabled。

## 完成门槛

- 离线 public smoke 两次结果相同；
- 一次无 mock fallback 的 public LLM smoke；
- canonical registry hash 不变；
- candidate-ready、verifier、export 和 QA 非阻塞；
- 五阶段故障注入可从正确位置恢复；
- Phase 16 与文档治理测试不回退。
