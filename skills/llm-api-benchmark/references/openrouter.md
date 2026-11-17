# OpenRouter — 提供商备注

OpenAI 兼容。Base URL：`https://openrouter.ai/api/v1`，Bearer 鉴权，
key 来自 `OPENROUTER_API_KEY`（`~/.hermes/.env`）。
模型目录：`GET /api/v1/models`（400+ 条，含大量第三方 `:free` 路由）。

## 部分 `:free` 模型有「agentic harness」门禁

少数免费模型（Thinking Machines 的 Inkling 系列：`thinkingmachines/inkling:free`、
`thinkingmachines/inkling-small:free`、`thinkingmachines/inkling-2-small:free`，
以及非 free 的 `inkling` / `inkling-small`）**只在被认可的 agent 客户端里可用**。
裸 API 调用返回：

```json
{"error": {"code": 403,
  "message": "... is only available on agentic harnesses. ...",
  "metadata": {"routing_funnel": [{"step": "Initial Endpoints", "endpoint_count": 1}],
              "failed_routing_step": "Gate Free Endpoints by Agentic Harness"}}}
```

**这个 403 不代表模型下线、名字写错或 key 失效。** 带上 Hermes 的归属头即可通过：

```
HTTP-Referer: https://hermes-agent.nousresearch.com
X-Title: Hermes Agent
```

Hermes 的 openrouter provider 会**自动**发送这两个头
（`agent/auxiliary_client.py` 的 `build_or_headers`，由 `agent/agent_init.py`
按 `openrouter.ai` 主机注入），所以配置 `provider: openrouter` 的 cron 任务或
agent 会话不需要任何额外设置。手动 `curl` 探针必须自己加上这两个头，
否则会把「门禁」误判成「模型不可用」。

其他客户端（Claude Code、Codex 等）能解锁是因为它们同样在认可名单内并发送
自己的归属头——这是分发渠道策略，不是模型能力差异。

## 目录里有 ≠ 能调（第二个独立机制）

「listing ≠ callable」有两个互不相关的成因：

| 机制 | 表现 | 判定方法 |
|---|---|---|
| 账号免费层限制 | 模型在目录里，调用 404/403 | 用同 ID 的付费变体对比 |
| harness 门禁 | 模型在目录里，裸调用 403 且带 `failed_routing_step` | 补上归属头重试 |

判定可用性必须用**运行时实际会发送的完整请求头**做一次真实 completion，
而不是只看 `/models` 或一次裸请求的状态码。

## 免费额度

`:free` 模型有账户级每日额度，且与同一 key 上的其他用法共享。把多个 cron 任务
指向同一个免费模型时，撞限流是正常现象，不是配置错误；换模型前先确认不是
额度耗尽，否则会把限流当成模型失效再去换一个。
