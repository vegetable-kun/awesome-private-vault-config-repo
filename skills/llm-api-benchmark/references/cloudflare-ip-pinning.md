# Cloudflare 边缘 IP 固定（过滤型 TLS 出站）

当 Cloudflare 前端的主机在 `Client hello` **之后**挂起时的恢复方案：
TCP 能连上，但后续毫无响应——没有 Server hello、没有 RST、没有证书。
`curl` 会耗尽整个超时后报告 `000`，而代理/云端的浏览器却能正常加载同一 URL。
这种组合意味着 **ClientHello 在传输途中被丢弃**，而非服务商宕机。

## 诊断（30 秒）

```bash
curl -4 -sv -o /dev/null -m 12 https://HOST/v1/models 2>&1 \
  | grep -E 'Trying|Connected|TLS|HTTP/|timed'
```

- `Trying ...` 后失败 → DNS / 路由问题
- `Connected ...` 后出现 `TLS handshake, Client hello`，接着
  `Connection timed out` → **本文件适用**
- 出现任意 `HTTP/` 行 → 通路正常，是应用层问题

区分"此主机被过滤"与"所有出站都被阻断"：

```bash
timeout 5 bash -c 'echo > /dev/tcp/HOST/443' && echo TCP_OK
timeout 5 bash -c 'echo > /dev/tcp/1.1.1.1/443' && echo OTHER_OK
```

再对比 80 端口的明文 HTTP 请求：TLS 被过滤但 80 端口正常，能确认丢弃发生在 TLS 层而非 IP 层。

## 为什么换个 IP 就能通

Cloudflare 采用 anycast 路由，**每个**边缘 IP 都为**所有** zone 提供服务——
ClientHello 中的 SNI 来选择证书和 zone，而非依赖 IP 地址。
因此可以保持真实域名不变（TLS 校验仍然通过），同时连接到一个未被过滤的边缘 IP。

已验证可用于 `inference-api.nousresearch.com` 与 `openrouter.ai`：
`188.114.96.1`、`188.114.97.1`、`162.159.140.1`、`104.20.0.1`、`104.20.1.1`。
默认解析到的 `104.16 / 104.18 / 172.64` 地址则为被过滤的 IP。

## 修复

按请求——无需改系统，安全内联执行：

```bash
curl --resolve HOST:443:162.159.140.1 -H "Authorization: Bearer $KEY" \
  https://HOST/v1/chat/completions -d @payload.json
```

全局——影响所有本地工具，包括 agent 自身的 provider 调用：

```
# /etc/hosts
162.159.140.1  inference-api.nousresearch.com
188.114.96.1   openrouter.ai
```

修改 `/etc/hosts` 属于系统级变更：须先获得用户明确授权
（`sudo -n true` 可判断当前是否免密）。固定的 IP 迟早也会被过滤——请保留 2-3 个备用。

## 查找可用 IP

```bash
python3 scripts/cf_edge_pin.py HOST --path /v1/models
```

固定 IP 停止响应时重新扫描；anycast 地址会轮流进出被过滤集合。

## 判断要点

- 探测返回 `403 Forbidden` **代表可达**——API 对未鉴权请求回复 403。带上真实请求头再测一次，别急着判死刑。
- 用鉴权请求**加**真实补全来确认；仅 `/v1/models` 返回 200 不能证明生成路径可用。
- 按"网络通路问题"报告，不要报成"提供商宕机"。
- 网络层过滤是独立的一类，不同于 WAF / 403 / 付费墙阻断——后者归 `blocked-page-recovery` skill 处理。
