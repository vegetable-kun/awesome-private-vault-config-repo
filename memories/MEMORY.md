QQ ID 57544CD377342E3D0BDDA7ABE789C15E — 超级管理员，拥有全部权限（设定 cron、运行代码、提问等）。
§
Hermes 部署在阿里云，2G 内存，Ubuntu 24.04。公网 IP：8.163.87.180，内网 IP：172.21.53.246。STT/TTS 已配置（Whisper-1 / edge-tts）。
§
网络：本机到 Cloudflare 默认解析 IP 段 TCP:443 通但 TLS 握手被重置。绕过方法=固定可用 CF 边缘 IP（188.114.96.1、162.159.140.1、104.20.0.1、104.20.1.1），curl 用 --resolve、全局用 /etc/hosts。inference-api.nousresearch.com 与 openrouter.ai 均可此法直连。
§
Obsidian Vault：~/.hermes/ObsidianVault（GitHub 私有仓库 vegetable-kun/obsidian-vault），与 memory.md 符号链接同步。含 3 套笔记模板（General/Learning/Project）和学习笔记。
§
Nous Portal 免费模型：请求体必须带 `tags: ["user=<任意标识>"]`（:free 模型强制，缺失报 400）。仅 Hermes 官方 tags（product/client/conversation）不带 user= 会被拒。
§
工具经验——MCP 桥接层：数组型入参会被改写成 `{"item":...}`（batch_search/tavily_extract/firecrawl_scrape/get_sub_domains 全中），前三个无标量替代。替代：get_sub_domains 用 `domain:"finance"` 标量、firecrawl_scrape 省略 formats。deferred catalog 漏 13 个工具（含 mcp__exa__* 全家），必须 tool_search 确认。MCP 连续 3 次拒调用暂停 41–51s，连错 2 次换引擎。详见 skill `search-router`。
§
`hermes cron run <id>` 前台超时 ≠ 任务没执行：采集已完成写入状态，只是模型阶段被杀，日志记 unknown。触发前先 `hermes cron runs <id>` 查状态，勿直接重触发。
§
凭据安全：用 curl -K 配置文件传 key（不进 argv/ps），umask 077 + chmod 600，用完 shred -u + 删目录，最后 grep 扫残留。判断残留用 `grep | wc -l` 计数，勿用 `| head`。
§
查询文件内容一律用 ripgrep（rg）而非 grep——索引更快。
§
本机开发环境：Ubuntu + GNOME X11 桌面，用户名 cxk，家目录 /home/cxk，dotnet SDK 在 /home/cxk/app/dotnet/sdk/10.0.401。
§
Hermes 三端使用：主要使用 CLI、TUI、Dashboard（仪表盘）。涉及 Hermes 更新或新功能时优先考虑这三端，而不是桌面端。
§
LightPanda 已部署：二进制 ~/.local/bin/lightpanda v1.0.2（deb 包解压，免 sudo）。Hermes 配置 browser.engine=lightpanda + browser.cloud_provider=local —— local 必须显式设置，否则 .env 里的 Nous/BrowserUse 凭据会被 autodetect 选中并 shadow 掉 engine。Hermes 内置 tools/browser_lightpanda.py（每会话起 lightpanda serve）+ Chrome fallback（截图等命令自动回退）。实测内存 29MB（Chromium ~2GB），无图形渲染故不支持截图。
§
Hermes terminal 工具：默认工作目录可能指向不存在的 ~/.hermes/images，导致 exit 126（报 cd 失败）。调用时必须传 workdir 参数指定一个存在的目录（如 /home/ecs-assist-user）。