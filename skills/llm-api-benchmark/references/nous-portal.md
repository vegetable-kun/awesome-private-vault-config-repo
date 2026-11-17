# Nous Portal 推理 API — 提供商备注

OpenAI 兼容。Base URL：`https://inference-api.nousresearch.com/v1`，
Bearer 鉴权，使用 `NOUS_API_KEY`（`sk-nou...` 开头）。
API 文档：`https://portal.nousresearch.com/api-docs`（JS SPA，文档页能以文本读取，
但其链接的 OpenAPI JSON 无法拉取）。套餐限速见文档：Free 50 RPM / 500k TPM、
Plus 400 RPM、Super 800 RPM、Ultra 1,600 RPM。

Cloudflare 前端——当主机存在 CF 出站过滤时，先阅读
`references/cloudflare-ip-pinning.md` 再下结论。

## 模型目录比文档声称的大得多

文档页只列 Hermes 家族，但 `/v1/models` 返回 400+ 条目，包含大量第三方 `:free` 路由
（`meituan/longcat-2.0:free`、`upstage/solar-pro4:free`、`poolside/laguna-s-2.1` 等）。
枚举 `/v1/models` 并按子串过滤，不要信任文档里的"可用模型"列表。

免费与付费变体**仅**相差 `:free` 后缀：

```
meituan/longcat-2.0     (付费)   meituan/longcat-2.0:free
upstage/solar-pro4      (付费)   upstage/solar-pro4:free
```

用相同请求体测试两种变体，是区分"免费层限制"与"模型 ID 错误"的最快方法。

## `:free` 模型需要用户标签

对 `:free` 模型的请求**必须**携带 `tags`：包含一个 `key=value` 条目的列表，
其中 key 为 `user`。

```json
{"model": "upstage/solar-pro4:free",
 "messages": [{"role": "user", "content": "hi"}],
 "max_tokens": 32,
 "tags": ["user=connectivity-test"]}
```

错误信息随请求体逼近而升级——这就是实战中找到该规则的方式：

| 发送的请求体 | 响应 |
|---|---|
| 无 `tags` | 400 `... Additional info: missing tags` |
| `"tags": ["t"]` | 400 `... missing user tag` |
| `"tags": ["product=hermes-agent", "client=hermes-client-vX"]` | 400 `... missing user tag` |
| `"tags": "t"`（裸字符串） | 500 |
| `"tags": ["user=<任意内容>"]` | 200 |

值不做校验——任何字符串均可。非 `:free` ID 接受不带 tags 的请求体，
因此 `:free` ID 上出现 400 通常是这个限制，而非模型名写错。
`meituan/longcat-2.0:free` 接受不带 tags 的请求体。

## 真相藏在本地 Hermes 安装中

Hermes 作为 Nous 官方参考客户端发布，因此当 400 提到一个你从未见过的字段时，
读客户端源码而非猜参数：

- `plugins/model-providers/nous/__init__.py` → `build_extra_body()` — 合并到每个请求的内容
  （注意：文档提到客户端提供的 provider 路由偏好会被 400 拒绝）
- `agent/portal_tags.py` → `nous_portal_tags()` — 标准标签列表格式
  （`product=…`、`client=…`、`conversation=…`）；注意：仅这些**不满足**免费层的 `user` 要求

`grep -rn "<字段>" <hermes-agent>/agent <hermes-agent>/plugins`
比猜参数高效；同样的技巧适用于任何安装了官方本地客户端的提供商。
