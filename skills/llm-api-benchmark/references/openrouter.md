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

## 推理链路整体故障：所有模型返回同一条不透明 400

判定「平台推理层挂了」而不是「某个模型坏了 / 账号出问题」的特征组合：

- **每一个**模型都返回同一条不透明 400（免费、付费、不同厂商一视同仁）；
- 读接口照常 200：`GET /api/v1/models`、`GET /api/v1/key`、`GET /api/v1/credits`；
- 错误响应头带 `x-openrouter-error-origin: client`，由 cloudflare 边缘返回。

实测样例：`chat/completions`（流式与非流式）与 `responses` 全部返回
`400 {"message":"Request path cannot be relayed"}`，而读接口 200 —— 请求确实
到达了 OpenRouter，是它自己的转发（relay）层拒绝继续往下走。

按顺序排除，别跳步：

1. **换 3~4 个不同模型各打一次。** 全挂才继续；只有一个挂，那就是那个模型的事。
2. **`GET /api/v1/key`** 看 `free_model_daily_requests.remaining` 与
   `budgets` / `effective_budget`。额度与预算耗尽报的是 402/403，不是这条 400。
3. **换 Cloudflare 边缘 IP**（`curl --resolve openrouter.ai:443:<ip>`）重打一遍，
   排除 `/etc/hosts` 钉的那条已被过滤 —— 见 `references/cloudflare-ip-pinning.md`。
4. **`hermes cron run <job_id>` 复现一次**，确认不是探针自身的问题。

仍然全挂即为平台侧故障。此时**换模型名没有任何意义**（换多少条都是同一条错），
正确动作是切 provider。同时拿错误原文去做 GitHub 代码搜索 + 社区论坛检索：
这类故障通常已有人踩到并记下起始时间，比官方状态页可靠 —— 状态页很可能仍显示
Operational。零散报告称换海外出口后恢复，但未证实，不要据此下结论、更不要建议
对抗性绕行。
