# 搜索引擎引擎速查

> 只记录 **必填参数、批量能力、时效性、已知失效场景**。
> 完整 schema 用 `tool_describe` 实时查，不要在这里抄 —— 会过期。
>
> 来源标注：`[文档]` = 官方文档确认；`[实测]` = 本机实测确认；`[待验证]` = 仅文档，未实测。

---

## 调用陷阱（先读这节）

### ⚠️ 1. 数组类型参数 **完全无法传入** `[已确认 · 4/4 复现]`

本环境的 `tool_call` 桥接层会把数组改写成 `{"item": ...}`。**不是写法问题，是桥接层行为。**

| 工具 | 传入 | 到达时变成 |
|------|------|-----------|
| `anysearch__batch_search` | `queries: [...]` | `queries[0]: query is required` |
| `tavily__tavily_extract` | `urls: [...]` | `is not of type 'string'` |
| `firecrawl__scrape` | `formats: [...]` | `{'item': 'markdown'} is not of type 'string'` |
| `anysearch__get_sub_domains` | `domains: [...]` | `{'item': 'finance'} is not one of [...]` |

**规避：用标量参数代替数组参数**

| 工具 | ❌ 数组 | ✅ 标量替代 |
|------|--------|-----------|
| `get_sub_domains` | `domains: [...]` | **`domain: "finance"`** ✅ 已验证 |
| `firecrawl__scrape` | `formats: [...]` | **省略**，默认即 markdown ✅ 已验证 |
| `batch_search` | `queries: [...]` | ❌ 无替代，基本不可用 |
| `tavily_extract` | `urls: [...]` | ❌ 无替代，多 URL 提取不可用 |
| `exa__web_fetch_exa` | `urls: [...]` | ❌ 无替代 |

**结论**：需数组参数的工具等于单次调用。跨 URL 提取改用 `firecrawl__scrape` 逐个抓。

### ⚠️ 2. MCP 服务端有暂停窗口 `[实测]`

**连续 3 次调用被拒 → 服务端暂停 41–51 秒**，期间所有工具调用一律被拒：

```
MCP server 'anysearch' rejected the last 3 calls (it is reachable).
Paused for ~51s. Do NOT repeat the same call.
```

**规避**：连错 2 次就停手，等冷却或立刻切引擎（`tavily_search` 实测可作为
anysearch 不可用时的替代，1.2s 返回）。冷却后恢复可用。

### ⚠️ 3. `mcp__*` 不能在 tool_call 里批量 `[实测]`

```
tool_call takes exactly one entry for local tools; you sent 3.
Only connectors__ names may be batched together.
```

`mcp__*` 被注册为 local tool，**一次只能调一个**。
「批量」只有两种正确方式：
- `mcp__anysearch__batch_search` —— 引擎内部并行（1–5 条）
- 引擎自带的数组参数 —— `tavily_extract.urls`、`exa__web_fetch_exa.urls`

### ⚠️ 4. 系统提示的工具 catalog 不完整 `[实测]`

系统提示的 deferred catalog 声称列出全部工具，实际**漏了 13 个**
（声明 51，`tool_search` 报告 64），`mcp__exa__*` 全家 6 个都不在其中。
**只读 catalog 会误判工具不存在 —— 必须 `tool_search` 确认。**

---

## Anysearch `[文档]`

官方仓库 `anysearch-ai/anysearch-mcp-server`（Apache-2.0）· 端点 `https://api.anysearch.com/mcp`（Streamable HTTP）

| 工具 | 必填 | 可选 |
|------|------|------|
| `search` | `query` | `domain`、`sub_domain`、`sub_domain_params`、`max_results`(1–10，默认 10) |
| `get_sub_domains` | `domain` 或 `domains`(string[] ≤5，推荐) | — |
| `batch_search` | `queries`(object[]，**1–5**) | — |
| `extract` | `url` | — |

**硬规则**
- 🔴 `extract` 是 **"HTML pages only"**，截断 **50,000 字符**
  → GitHub / SPA 等 JS 页面**必然失败**，换 `gh api` 或 `firecrawl_scrape` `[实测]`：GitHub 页面 `extract_failed`
- 🔴 任何 vertical 搜索**必须先调 `get_sub_domains`**；`sub_domain_params` 官方标注 **"NEVER invent values"**
- `search` 官方要求 **"ONE intent per call"** —— 一次查询一个意图，多意图用 `batch_search`
- 限流：code `42901` / `rate_limited` → 按 `Retry-After` 退避，无则停止重试
- 免 key 可匿名访问，速率较低；key 优先级 `--api_key` > `ANYSEARCH_API_KEY` > `.env` > 匿名

### REST API —— 脚本调用，绕过 MCP 桥接层 `[实测]`

上面的 MCP 工具走桥接层（数组参数被改写、一次只能调一个、有暂停窗口）。**脚本化取数直接用 REST**，无桥接层限制：

```
POST https://api.anysearch.com/v1/search
Authorization: Bearer <key>
Content-Type: application/json

{"query": "...", "max_results": 5, "language": "zh-CN"}
```

响应：`{"code": 0, "message": "success", "data": {"results": [{"title", "url", "description", "content"}]}}`

- key 从 `~/.hermes/.env` 读（`MCP_ANYSEARCH_API_KEY`），**不要硬编码**；与 MCP 共用同一 key
- 与 MCP 是同一后端，结果一致；`code != 0` 时 `message` 是错误说明
- 适用：cron 采集脚本、MCP 不可用时、需要批量/结构化时
- 注册取 key：`POST https://api.anysearch.com/v1/auth/email/register`，body `{"email": "..."}`，
  返回 `data.api_key.key`（`as_sk_...`，**只显示一次**）；`email_already_registered` 表示已注册，去返回的 `login_url` 登录，不要重试

---

## Exa `[文档]`

官方文档 `exa.ai/docs/reference/search`

| 项 | 说明 |
|----|------|
| `web_search_exa` 必填 | **`query` + `objective`**（两个都必填） |
| `web_fetch_exa` 必填 | `urls`（数组，可一次多 URL） |
| `objective` | REST API 里是 `string \| null`，**MCP 包装层设为 required** |
| `objective` 上限 | 4096 字符 |

**官方对 `objective` 的释义**（原文）：
> The broader goal this search serves: the task the caller is working on, beyond the query itself.

**其他**
- MCP 默认只暴露 `web_search_exa` + `web_fetch_exa`；
  `web_search_advanced_exa`、`agent_run` 需用 `tools` 查询参数**显式开启**
- `exa.ai/docs/llms.txt` —— 官方标注 "If you're an LLM, read LLMs.txt"

---

## Firecrawl `[文档]`

官方文档 `docs.firecrawl.dev`

| 参数 | 默认 | 备注 |
|------|------|------|
| `onlyMainContent` | **true** | 剥掉 nav/footer 等样板 |
| **`maxAge`** | — | ⚠️ **缓存 TTL，要实时内容必须设 0** |
| `minAge` | — | 内容最小年龄 |
| `formats` | `markdown` | 支持 `json` + `schema` 做结构化抽取 |
| `waitFor` | 0 | 等待 ms |
| `timeout` | 15000 | 超时 ms |
| `proxy` | — | 支持 `auto` |
| `includeTags`/`excludeTags` | — | ⚠️ 作用于**原始 DOM**，不是 `onlyMainContent` 过滤后的结果 |

**规则**
- 404 **不算 crawl 错误** —— 页面照常出现在 `data` 里，状态码在 `metadata.statusCode`
- `firecrawl.dev/agent-onboarding/SKILL.md` 是官方给 agent 的接入说明
- `tavily_extract` 的 `extract_depth: "advanced"` 与 firecrawl 同类需求可互换

### SPA / hash 路由页面：把完整 `#/route` 传给渲染型抓取 `[实测]`

JS 渲染的站点（各类高校/政务办事系统、`ehall.*` 类应用）用普通 extract 只能拿到空壳
——返回 200 但正文只有导航和页脚。

**修法是换渲染型抓取，并且把 hash 路由一起传进去**：

```
❌ https://host/app/index.do            → 只返回目录壳
✅ https://host/app/index.do#/2027/1/104/085402   → 返回该条目的完整正文
```

`firecrawl_scrape` 实测能执行 JS 并渲染出 hash 路由对应的内容。判断标志：
响应 `metadata.renderer` 出现（如 `webkit`）、`proxyUsed` 为 `stealth`，且正文里
带上了只有 JS 才能取到的字段。

**顺序**：先拿列表页壳 → 从壳里读出每个条目的 hash 路由 → 逐个抓详情页。
列表页本身可能不带业务数据，不要因为它是空的就判定站点不可达。

---

## Tavily `[文档]`

官方文档 `docs.tavily.com` · 端点全集 `/search` `/extract` `/crawl` `/map` `/research`

| 工具 | 必填 | 关键可选 |
|------|------|---------|
| `tavily_search` | `query` | — |
| `tavily_extract` | `urls`（数组） | `extract_depth`(`basic`/**`advanced`**)、`chunks_per_source`(默认 3)、`format`、`query`(rerank)、`timeout` |

**规则**
- `extract_depth`：`advanced` 用于 LinkedIn / 受保护站点 / 表格与嵌入内容
- 认证：`Authorization: Bearer tvly-...`；可选头 `X-Session-Id`、`X-Human-Id`、`X-Project-ID`
- 实测 1.2s 返回，作为 anysearch 不可用时的首选替代 `[实测]`

---

## 实测速记

| 现象 | 结论 |
|------|------|
| anysearch extract 抓 GitHub 失败 | ✅ 官方已说明 "HTML pages only"，非配置问题 |
| exa 漏 `objective` | ✅ 官方证实 REST 层「remaining fields are optional」，但 **MCP 层 required** |
| 数组参数传入 | 🔴 **桥接层改写成 `{"item":...}`，4/4 复现，彻底不可用** |
| `get_sub_domains` | ✅ 用 `domain: "finance"` 标量，不可用 `domains: [...]` |
| `firecrawl__scrape` | ✅ 省略 `formats` 得 markdown；`maxAge:0` + `onlyMainContent:true` 实测生效 |
| tavily_search | ✅ 1.2s 返回，质量高，可作 anysearch 的降级替代 |
| 系统提示 catalog | ✅ 缺 13 个工具，`mcp__exa__*` 差点被误判为不存在 |
| `tavily_extract` / `exa__web_fetch_exa` 多 URL | 🔴 因数组不可用，**实测无法调用**（非文档问题） |
| SPA / hash 路由站点（`ehall.*` 类） | ✅ 普通 extract 只得空壳；`firecrawl_scrape` 带完整 `#/route` 可拿到正文 |
| firecrawl 连续失败 3 次 | ✅ 进入 ~42s 暂停窗口，与 anysearch 同机制 —— 连错 2 次就切引擎 |
