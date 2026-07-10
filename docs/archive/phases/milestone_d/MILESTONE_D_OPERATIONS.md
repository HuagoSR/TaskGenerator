# 里程碑 D Docker 操作说明

> 状态：`historical reference`

容器内唯一流水线入口仍是 `Test/run_v3_end_to_end_pipeline.py`。本地部署控制入口为 `Test/run_v3_server_reproduction.py`，SSH target 使用本机配置中的 `serene-cloud`。

常用动作：

```text
--action preflight
--action build --release-id <release>
--action deploy --release-id <release>
--action activate --release-id <release>  # 仅在 candidate 验收通过后执行
--action demo-offline --target server --release-id <release> --run-id <run>
--action demo-llm --target server --release-id <release> --run-id <run>
--action batch --target server --release-id <release> --run-id <run>
--action status|resume --target server --release-id <release> --run-id <run>
--action resume --service online ...  # 仅用于已明确批准的 LLM run
--action rerun --from-stage <stage> ...
--action fetch --release-id <release> --run-id <run>
--action compare --local-manifest <path> --remote-manifest <path> --output <path>
--action rollback
```

服务器固定目录：

```text
~/taskgenerator-deploy/current
~/taskgenerator-deploy/candidate
~/taskgenerator-deploy/previous
~/taskgenerator-deploy/releases/<release_id>
~/taskgenerator-data/runs
~/taskgenerator-data/inputs
~/taskgenerator-secrets/deepseek_api_key
```

`offline` Compose service 使用 `network_mode: none`；`online` 仅用于显式批准的公开 source LLM extraction。两个服务均不映射端口，默认 `allow_web_collection=false`、`allow_external_eval=false`。

`deploy` 只更新 `candidate`；server smoke 直接按 `--release-id` 运行。验收通过后由 `activate` 将旧 `current` 保存为 `previous`。回滚只交换 `current` 与 `previous` symlink。不得使用全局 Docker prune，也不得修改服务器现有 nginx、Minecraft、Docker daemon、防火墙或 swap。
