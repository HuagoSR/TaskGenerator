# Milestone C Completion - 2026-07-10

## Final decision

```text
milestone_c_status = completed
manifest_version = v3.end_to_end_pipeline.2
scratch_first = true
resumable = true
repeatable = true
external_eval_default = disabled
external_eval_executed = 0
next_milestone = D_server_reproduction
```

## Core result table

| run | extractor | candidates | accepted | sample-ready | candidate-ready | verifier pass | export compatible | prepared/executed eval |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `milestone_c_offline_final_a` | deterministic mock | 4 | 4 | 3 | 2/2 | 2/2 | 2/2 | 1/0 |
| `milestone_c_offline_final_b` | deterministic mock | 4 | 4 | 3 | 2/2 | 2/2 | 2/2 | 1/0 |
| `milestone_c_public_llm` | DeepSeek `deepseek-v4-flash` | 5 | 3 | 3 | 2/2 | 2/2 | 2/2 | 1/0 |

Both offline runs produced normalized content fingerprint:

```text
722497164acf1138bbfccd4975e9a0ed75ddf7adbc463738b3c90b9ab6881173
```

The LLM run uploaded only `Test/v3_public_smoke_package/skill_extraction_prompt_package.json` for skill extraction. It did not perform web collection or external task evaluation.

## Recovery evidence

- Unit fault injection covered all five stages.
- Resume reused checksum-valid upstream stages and restarted at the failed stage.
- Real `rerun --from-stage task_generation` reused source/registry stages and reran task generation plus both downstream stages.
- Missing checksum artifacts force stage rerun.
- Resume preserves the frozen request instead of replacing it with new CLI values.
- V1 manifests remain status-readable but cannot be resumed in place.

## Boundaries

- Mock extraction is `smoke_only`, not task-quality evidence.
- Production promotion and strict release are not Milestone C gates.
- Training candidate index is not the final Milestone F training export.
- Raw manifests, public/LLM outputs, command logs and provider responses remain ignored artifacts.
- Milestone D should validate the same manifest and lifecycle contracts on the server rather than create another orchestrator.
