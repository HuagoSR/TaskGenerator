# 里程碑 D：Docker 服务器复现工作流

状态：`active`

## 目标

把里程碑 C 的 `v3_end_to_end_pipeline` 固定为同一个 Linux/amd64 镜像，在本机与 `serene-cloud` 运行，并以 Manifest V2、acceptance report、内容指纹和镜像 ID 证明结构等价。

## 已冻结边界

- 服务器仅通过 SSH 与 Docker Compose 操作，不开放新端口。
- 不修改 nginx、Minecraft、Docker daemon、防火墙或 swap。
- 默认无 web collection、无外部模型评测、无 canonical registry mutation。
- 唯一外发验收是把 tracked public synthetic fixture 发送给 DeepSeek official 做一次 skill extraction smoke。
- `.env`、`deepseek-key.txt`、provider 输出和运行 artifacts 不进入镜像或 Git。

## 交付检查

- [ ] Linux/amd64 固定镜像与 release manifest
- [ ] 本机两次 offline smoke 精确复现里程碑 C 指标
- [ ] 服务器 offline smoke 与本机结构等价
- [ ] 跨容器 resume、server batch 与公开 LLM smoke
- [ ] 等价报告、资源记录、操作与回滚说明
- [ ] 完成文档归档并把下一主线切换至里程碑 E

完成后，本文件与 completion handoff 一并迁入 `docs/archive/phases/milestone_d/`。
