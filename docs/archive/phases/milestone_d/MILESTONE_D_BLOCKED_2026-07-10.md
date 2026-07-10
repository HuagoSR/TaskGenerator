# 里程碑 D 阻塞收口 - 2026-07-10

> 状态：`historical blocked handoff`

## 最终判断

```text
milestone_d_status = blocked
docker_server_reproduction = passed
local_server_structural_equivalence = passed
server_resume = passed
server_batch = passed
public_llm_smoke = failed_twice
external_eval_executed = 0
next_action = resolve_deepseek_truncated_json_before_new_smoke
```

里程碑 D 的 Docker、路径可移植性、持久化、恢复、batch 和离线等价目标均已实现。唯一未满足的硬门槛是服务器真实 LLM smoke：DeepSeek official `deepseek-v4-flash` 连续两次返回被截断的 JSON。根据预先冻结的规则，第二次失败后停止，不使用 mock 结果替代，因此本轮必须标记为 `blocked`，不能宣布 completed。

## 固定 release

| 字段 | 值 |
| --- | --- |
| release | `milestone-d-71fa214` |
| source commit | `71fa214d17182bfa471fccea17546c2dcf7e9727` |
| archive config digest | `sha256:1dddb0c70d11311ce34be3c10bfa0d1b1a089b59783af6afe279b84b918fe634` |
| image archive SHA-256 | `06de215ff55288e29c8c967024a372108cff9482fddd117289078a2c2c12f830` |
| rw-task snapshot | `d81ac8297b0c78b6f78d982c05d891ed2375f2e9e142340e748032cdf055f9e3` |
| architecture | `linux/amd64` |
| image size | `1,015,491,255 bytes` |
| compressed archive | `376,968,670 bytes` |

Docker Desktop 28 与服务器 Docker 29/containerd 对 loaded image 的 daemon display ID 不同；服务器显示 `sha256:a3a0...`。传输 archive SHA-256、archive config digest、12 个 RootFS layer digest、source commit、rw-task snapshot 和 OCI labels 全部一致，因此这是存储后端的 ID 表示差异，不是镜像内容差异。

## 验收结果

| run | candidates | accepted | sample-ready | candidate-ready | verifier/export | eval prepared/executed | fingerprint |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| local offline A | 4 | 4 | 3 | 2/2 | 2/2 | 1/0 | `722497...1173` |
| local offline B | 4 | 4 | 3 | 2/2 | 2/2 | 1/0 | `722497...1173` |
| server offline | 4 | 4 | 3 | 2/2 | 2/2 | 1/0 | `722497...1173` |
| server recovery | 4 | 4 | 3 | 2/2 | 2/2 | 1/0 | `722497...1173` |
| server batch | 0 | 0 | 20 | 4/4 | 4/4 | 2/0 | `8caf0b...c512` |

等价报告结论为 `equivalent`：manifest version、source commit、五阶段结构、输入指纹、精确指标、canonical registry hash、external-effects ledger 和 normalized content fingerprint 全部一致。服务器 batch 使用 `snapshot_scratch`，canonical registry 前后 SHA-256 均为 `7329e377...90fc7`。

恢复测试在 `task_generation=running` 时停止容器，退出码 `143`、`OOMKilled=false`。随后 `resume` 将 `source_to_skills` 和 `registry_prepare` 标记为 `reused`，从 `task_generation` 恢复并完成下游阶段。

资源探针 run：退出码 `0`、`OOMKilled=false`、wall time 约 `10.47 s`，采样峰值约 `124.3 MiB`，峰值 CPU 约 `100.74%`，低于 `2.5 GiB / 1.5 CPU` 容器上限。

## LLM 阻塞证据

| attempt | run status | provider/model | failure |
| --- | --- | --- | --- |
| first | `failed` | DeepSeek official / `deepseek-v4-flash` | JSON `Unterminated string`，约在 char 21182 |
| retry | `failed` | DeepSeek official / `deepseek-v4-flash` | JSON `Unterminated string`，约在 char 20546 |

两次均只发生 `external_source_upload=true` 和 `llm_extraction=true`；`web_collection=false`、`eval_preparation=false`、`external_eval=false`。未启用 mock fallback。

新的 LLM smoke 必须先明确批准一个解阻切片，例如缩短输出 schema、降低候选数量或增加可验证的 JSON continuation/repair。不得在本轮既有两次证据上追加第三次同配置尝试。

## 安全与服务器影响

- key 只读挂载自 `~/taskgenerator-secrets/deepseek_api_key`，权限 `0600`。
- 使用真实 key 值扫描 image archive 和已拉回 artifacts，命中数均为 0；扫描过程未输出 key。
- 镜像和 release context 不含 `.env`、key、历史 artifacts、provider 输出、pycache 或 `.DS_Store`。
- nginx 和 Minecraft 容器 ID、运行状态和端口全程不变；本项目没有公开端口。
- 项目测试容器已清理；服务器保留 release、持久化 runs 和独立 secret，以便后续解阻后复用。

原始 release、manifests、provider failure outputs、等价报告和资源采样保留在 ignored `artifacts/releases/milestone_d/milestone-d-71fa214/`，不提交 Git。
