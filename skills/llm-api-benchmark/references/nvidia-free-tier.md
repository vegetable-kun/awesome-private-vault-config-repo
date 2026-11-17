# NVIDIA 免费层细则

## 速率限制（2026 年）

| 限制 | 数值 | 作用域 |
|---|---|---|
| 请求/分钟 | 30-40 RPM | 账户级（所有模型共享） |
| Token/分钟 | 100 TPM | 标准层 |
| 初始额度 | 1,000 | 申请可达 5,000 |
| 429 响应头 | `Retry-After` | 需等待的秒数 |

## 模型可用性

**关键：**`/v1/models` 列出**所有**目录模型，但免费层账户只能调用其中约 12%
（截至 2026 年 9 月为 10/81）。

## 为什么模型返回 404

NVIDIA 使用基于函数的路由系统。每个模型映射到一个函数 ID。
如果你的账户未获该函数访问权限，会收到：

```json
{"status":404,"title":"Not Found","detail":"Function 'uuid': Not found for account '...'"}
```

这**不是**模型可用性问题——是账户权限问题。

### 免费层普遍可用的模型

以下在 2026 年 9 月新免费账户上验证可用：

- `openai/gpt-oss-20b` — 20B 通用
- `meta/muse-glimmer-30b` — 30B 通用
- `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` — 30B 推理
- `meta/llama-3.2-11b-vision-instruct` — 11B 多模态
- `nvidia/llama-3.1-nemoguard-8b-content-safety` — 安全分类器
- `nvidia/llama-3.1-nemotron-safety-guard-8b-v3` — 安全守卫
- `nvidia/nemotron-3.5-content-safety` — 内容安全
- `nvidia/riva-translate-4b-instruct-v1.1` / `v2` — 翻译
- `nvidia/ising-calibration-1.5-31b` — 校准

### 免费层稳定 404 的模型

- 所有 Nemotron-4、Nemotron-Ultra、Nemotron-3-Super/Ultra
- 所有 DeepSeek v4（Pro/Flash）
- 所有 Kimi（K2.6、K3）
- 所有 Llama-3.1-Nemotron（51B、70B）
- 所有 Mistral Large / Mixtral
- 所有 Writer Palmyra
- 所有 Databricks DBRX
- 所有 Google Gemma（3.x、4.x）

## 错误码

| 状态码 | 含义 | 处理 |
|---|---|---|
| 404 | 函数未授权 | 跳过——需升级账户 |
| 429 | 超出速率限制 | 等待 `Retry-After` 秒 |
| 500 | 服务器内部错误 | 5 秒后重试一次 |
| 503 | 服务不可用 | 模型可能已下线 |
| 超时 | 15 秒+ 无响应 | 模型可能过载 |

## API 端点

```
https://integrate.api.nvidia.com/v1/chat/completions
```

兼容 OpenAI Python SDK：
```python
from openai import OpenAI
client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=KEY)
```

## Key 位置

NVIDIA API Key 存储在 `~/.hermes/.env` 中，变量名 `NVIDIA_API_KEY=...`。
默认不会导出到 shell——需要先 source 或提取。
