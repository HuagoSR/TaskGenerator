# 里程碑 D 完成收口 - 2026-07-10

> 状态：`historical completion handoff`

## 最终判断

```text
milestone_d_status = completed
docker_server_reproduction = passed
local_server_structural_equivalence = passed
server_resume = passed
server_batch = passed
bounded_public_llm_smoke = passed_on_allowed_retry
external_eval_executed = 0
active_release = milestone-d-094c6cb
next_milestone = E_second_domain_vertical_slice
```

里程碑 D 已完成。服务器当前运行入口指向经过候选验收后显式激活的 `milestone-d-094c6cb`；前一 release `milestone-d-71fa214` 保留为 `previous`，可原子回滚。

## 固定 release

| 字段 | 值 |
| --- | --- |
| release | `milestone-d-094c6cb` |
| source commit | `094c6cb91694e8fcdaf311cabbc862fe43c61e16` |
| local image config digest | `sha256:6c15f6dfb5cf1c76eb30ddfccc77fe61574ae1f5ac426e626038e9c342f58aba` |
| image archive SHA-256 | `1ad61cf1b282635b192ae92ecf9aa7b98a790423fbc247028900a507163d9665` |
| rw-task snapshot | `d81ac8297b0c78b6f78d982c05d891ed2375f2e9e142340e748032cdf055f9e3` |
| architecture | `linux/amd64` |
| image size | `1,015,526,462 bytes` |
| compressed archive | `376,983,489 bytes` |

本机与服务器 RootFS layer digest 逐项一致。部署流程现为 `deploy candidate → candidate smoke → activate`；未经验收的 candidate 不会替换 current。

## 验收结果

| run | candidates | accepted | sample-ready | candidate-ready | verifier/export | eval prepared/executed | fingerprint |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| local offline A | 4 | 4 | 3 | 2/2 | 2/2 | 1/0 | `722497...1173` |
| local offline B | 4 | 4 | 3 | 2/2 | 2/2 | 1/0 | `722497...1173` |
| candidate server offline | 4 | 4 | 3 | 2/2 | 2/2 | 1/0 | `722497...1173` |
| bounded DeepSeek retry | 4 | 4 | 3 | 2/2 | 2/2 | 1/0 | `a24e064...e696` |

离线等价报告结论为 `equivalent`：source commit、五阶段结构、输入指纹、精确指标、canonical registry SHA-256、external-effects ledger 和 deterministic content fingerprint 全部一致。

## LLM 解阻证据

公开 LLM profile 固定为：

```text
provider = DeepSeek official
model = deepseek-v4-flash
output_profile = bounded_smoke
max_candidates = 4
max_tokens = 6000
mock_fallback = false
```

新 campaign 首次响应明确记录为 `finish_reason=length`、`completion_tokens=6000`、`response_char_count=10586`，因此失败证据被保留。唯一一次同配置重试成功：

```text
finish_reason = stop
prompt_tokens = 2800
completion_tokens = 5323
total_tokens = 8123
response_char_count = 13807
candidate_count = 4
accepted_count = 4
```

失败诊断只记录 finish reason、token/字符统计和 response SHA-256，不保存原始 provider 响应。没有 JSON 猜测修补、partial candidate 截取或第二模型修复。

## 安全与边界

- LLM campaign 只上传 tracked public synthetic fixture。
- `web_collection=false`、`external_eval=false`、`executed_eval_count=0`。
- canonical registry 前后 SHA-256 均为 `7329e377fd3ef794c1bbbf089bb326bb8bd482a54939968c720cc3ef4a090fc7`。
- 使用真实 key 值扫描候选 image archive 和拉回 artifacts，命中数均为 0；扫描过程未输出 key。
- key 仍由服务器独立文件以 `0600` 权限只读挂载。
- nginx 和 Minecraft 容器 ID、状态与端口未改变；TaskGenerator 不公开任何端口。
- 原始 release、manifests、provider outputs 和等价报告保留在 ignored `artifacts/releases/milestone_d/milestone-d-094c6cb/`，不提交 Git。

## 下一步

里程碑 E 只做一个第二领域垂直切片，继续复用当前 Docker、Manifest V2、scratch registry、QA 和 eval preparation 合同。D 的完成不授权外部 eval、SFT/RL、默认链 promotion 或多领域并行扩张。
