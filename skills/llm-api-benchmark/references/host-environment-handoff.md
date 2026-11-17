# 本机环境交接（阿里云 Ubuntu 24.04 / Hermes 部署机）

> 用途：下次在本机排查 LLM API 连通性时先读这一页，不要再从零走一遍诊断流程。
> 最后更新：2026-09-13（实测数据均为当日本机结果）

## 一句话结论

本机**不能**直连 Cloudflare 默认解析的 IP 段（TLS ClientHello 被静默丢弃），
但已通过 `/etc/hosts` 固定可用边缘 IP，`inference-api.nousresearch.com` 与
`openrouter.ai` 现在都能**本机直连**（HTTP 200）。

## 已确认事实（都实测过，别再猜）

| 现象 | 实测结果 |
|---|---|
| TCP 443 / 80 | **通**（`/dev/tcp` 握手成功）——安全组没问题，别去查安全组 |
| TLS | ClientHello 发出后静默超时，无 ServerHello、无 RST |
| CF 被过滤的默认段 | 104.16.x / 104.18.x / 172.64.x / 162.159.36.x / 141.101.x / 190.93.x / 198.41.x / 108.162.x / 131.0.72.x / 103.21.244.x |
| CF 可用段（实测 200） | 188.114.96.1 / 188.114.97.1 / 188.114.98.1 / 162.159.140.1 / 104.20.0.1 / 104.20.1.1 / 104.21.0.1 / 172.64.80.1 |
| portal.nousresearch.com（Vercel 66.33.60.129） | **一直可直连** —— 文档页能正常读 |
| 域名前置（SNI=cloudflare.com + Host=目标） | 无效 |
| IPv6 | 不通 |
| 非 CF 目标（fastly 151.101.1.140） | 同样超时（过滤不限于 CF） |

## 已做的系统级修改

`/etc/hosts` 末尾的 `cf-edge-pin` 块（**勿手改**，会被刷新脚本覆盖）：

```
# BEGIN cf-edge-pin (cf-ip-refresh.sh 自动维护，勿手改)
188.114.96.1  inference-api.nousresearch.com
188.114.96.1  openrouter.ai
# END cf-edge-pin
```

- 备份：`/etc/hosts.bak.20260913`（改动前原始文件）；每次刷新还会留 `/etc/hosts.bak.YYYYMMDD-HHMM`
- 回滚：`sudo cp /etc/hosts.bak.20260913 /etc/hosts`
- `sudo` 本机**免密**（`sudo -n true` 通过）

## 日常操作

```bash
~/.hermes/scripts/cf-ip-refresh.sh          # 重扫 + 更新 /etc/hosts + 验证
~/.hermes/scripts/cf-ip-refresh.sh --dry    # 只扫描不写入

# 单次请求临时绕过（不改系统）
curl --resolve inference-api.nousresearch.com:443:188.114.96.1 ...

# 扫描工具（skill 自带）
VENV_PY=~/.hermes/hermes-agent/venv/bin/python3
$VENV_PY ~/.hermes/skills/mlops/llm-api-benchmark/scripts/cf_edge_pin.py HOST --path /v1/models --json
```

**何时跑刷新脚本**：本机调用突然又开始超时 → 先看 `/etc/hosts` 有没有 `cf-edge-pin` 块，
有就直接刷新（说明固定的 IP 被墙了），不要重新走一遍全量诊断。

**验证 pin 是否生效**：`curl -w '%{remote_ip}'` 看实际连的是哪个 IP。
长驻进程（Hermes 主进程）可能缓存旧 DNS，重启后生效。

## Nous Portal API 要点

- Base URL：`https://inference-api.nousresearch.com/v1`（OpenAI 兼容，Bearer 鉴权）
- Key：`~/.hermes/.env` 的 `NOUS_API_KEY`（`sk-nou` 开头，**永远不要打印出来**）
- 文档：`https://portal.nousresearch.com/api-docs`（JS SPA，浏览器能读文本，其 OpenAPI JSON 拉不到）
- **免费模型必须带 `tags: ["user=<任意字符串>"]`**，否则 400 `missing user tag`；
  非免费 ID 不要求。标签值不做校验。错误升级链见 `references/nous-portal.md`。
- 实测可用的免费模型：`meituan/longcat-2.0:free`、`upstage/solar-pro4:free`
- 目录有 **400+ 模型**，文档页只列 Hermes 家族 → **以 `/v1/models` 为准**
- 套餐限速：Free 50 RPM / 500k TPM，Plus 400，Super 800，Ultra 1,600

### 本机实测延迟（2026-09-13，直连，非浏览器代跑）

| 模型 | 结果 | 延迟 | 备注 |
|---|---|---|---|
| meituan/longcat-2.0:free | 200 x3 | 2.5-3.6s | 不需要 tags |
| upstage/solar-pro4:free | 200 x3 | 1.4-3.5s | 必须带 tags |

## 关键路径速查

| 用途 | 路径 |
|---|---|
| venv Python（所有脚本用它） | `/home/ecs-assist-user/.hermes/hermes-agent/venv/bin/python3` |
| 密钥集合 | `/home/ecs-assist-user/.hermes/.env` |
| Hermes 配置 | `/home/ecs-assist-user/.hermes/config.yaml` |
| 刷新脚本 | `/home/ecs-assist-user/.hermes/scripts/cf-ip-refresh.sh` |
| 本 skill | `/home/ecs-assist-user/.hermes/skills/mlops/llm-api-benchmark/` |

## 备用通道：云浏览器

本机 shell 不通但站点能开时，可走浏览器探测：Hermes 的 browser 后端是
**Firecrawl 云浏览器 + 代理**（实测出口 IP `113.30.192.110`，非本机公网 IP），
能访问本机访问不了的域名。用法见 SKILL.md 步骤 2。

## 排查决策树（30 秒版）

```
curl -4 -sv -o /dev/null -m 12 https://HOST/v1/models 2>&1 | grep -E 'Trying|Connected|TLS|HTTP/|timed'
│
├─ 没有 Connected            → DNS / 路由 / 出方向安全组
├─ Connected 后 TLS Client hello 卡住
│    ├─ /etc/hosts 已有 cf-edge-pin 块 → 跑 cf-ip-refresh.sh（IP 失效了）
│    └─ 没有该块                      → 跑 cf_edge_pin.py 扫描可用 IP
└─ 出现任意 HTTP 行（401/403/404/429）→ 通路没问题，读响应体查 key/参数/模型名
```

## 本机踩过的坑

1. **同步 XHR 不能设 `timeout`**（浏览器通道）——报错文案：`Timeouts cannot be set for synchronous requests made from a document`。
2. **浏览器 daemon 的 IPC 约 5 秒超时**：慢请求（长生成）会整个调用失败；
   改用异步 `fetch` 把结果写进 `window` 变量，再分多次 `js()` 轮询。
3. **`tags` 写成字符串会 500**，必须是数组。
4. 免费模型报 400，**先怀疑 tags 缺失**，不要先怀疑模型名写错。
5. **别把 API key 打进任何输出**：脚本里从 `.env` 读、直接注入请求。
6. 侧信道顺序：`403 Forbidden` 只代表「没带鉴权头」，**不代表不可达**，带真实头再测一次。
