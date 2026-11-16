# hermes-config

Hermes Agent 配置与知识库的镜像仓库。

把本机 `~/.hermes/` 下由 Hermes 生成和维护的内容，**单向同步**备份到 GitHub，
用于版本管理、跨机恢复与成果展示。

> **同步方向**：`~/.hermes/`（源） → 本仓库（副本）。
> 本仓库不反向写入 `~/.hermes/`。在本地修改配置后，运行 `sync.sh` 即可更新仓库。

---

## 目录结构

```
hermes-config/
├── .gitignore                  # 排除运行时状态 / 虚拟环境 / 缓存
├── README.md                   # 本文件
├── sync.sh                     # 同步脚本：复制 → 提交 → 推送
├── AGENTS.md                   # Agent 行为规范
├── SOUL.md                     # Agent 人格与沟通风格
├── memories/                   # 记忆存储
│   ├── MEMORY.md               #   长期记忆（环境、工具经验、约定）
│   ├── USER.md                 #   用户画像（偏好、背景、交付习惯）
│   └── personal.yaml           #   单条偏好记忆（trigger / action 结构）
├── scripts/                    # 定时任务依赖脚本
│   ├── news_fetcher.py         #   新闻抓取
│   ├── news_fetcher_v4.py      #   新闻抓取 v4
│   ├── news_processor.py       #   新闻处理
│   ├── briefing_cron.py        #   AI 简报定时任务
│   ├── cf-ip-refresh.sh        #   Cloudflare 边缘 IP 刷新
│   ├── news_fetcher.sh         #   新闻抓取 shell 入口
│   ├── panyu_weather.py        #   广州番禺天气查询
│   ├── python3                 #   cron 专用 Python 解释器入口
│   ├── .cron-python            #   同上（内容与 python3 相同）
│   └── tavily_shim/            #   Tavily 调用 shim
├── hooks/                      # 钩子插件
│   └── agents-md-gate/         #   AGENTS.md 强制门禁（含搜索路由）
├── skills/                     # 按需纳入的技能
│   ├── search-router/          #   搜索路由（配合 hooks/agents-md-gate）
│   └── session-recap/          #   会话完成情况总结（渲染成图）
└── cron/
    └── jobs.json               # 定时任务定义与 prompt
```

---

## 内容来源

| 仓库路径 | 源位置（`~/.hermes/`） | 说明 |
|---|---|---|
| `AGENTS.md` | `AGENTS.md` | 工作优先级、任务流程、授权范围等行为规范 |
| `SOUL.md` | `SOUL.md` | 人格语气、核心原则、回应风格 |
| `memories/MEMORY.md` | `memories/MEMORY.md` | 长期记忆条目 |
| `memories/USER.md` | `memories/USER.md` | 用户画像 |
| `memories/personal.yaml` | `memories/personal.yaml` | 偏好记忆 |
| `scripts/` | `scripts/` | 定时任务依赖脚本 |
| `hooks/agents-md-gate/` | `plugins/agents-md-gate/` | AGENTS.md 强制规则门禁插件 |
| `skills/search-router/` | `skills/productivity/search-router/` | 搜索路由技能（含 engines 参考） |
| `skills/session-recap/` | `skills/productivity/session-recap/` | 会话完成情况总结技能 |
| `cron/jobs.json` | `cron/jobs.json` | 定时任务配置与 prompt |

---

## 同步机制

`sync.sh` 采用**白名单制**，只复制上表列出的条目，**绝不整目录扫描 `~/.hermes/`**，
以避免把敏感文件带入仓库。

```bash
./sync.sh             # 同步 + 提交 + 推送
./sync.sh --no-push   # 只同步 + 提交，不推送
```

流程：复制 → `git add -A` → 有变更则 commit（`sync: YYYY-MM-DD HH:MM`）→ `git push`。

`.gitignore` 排除：`*.lock`、`*.bak*`、`__pycache__/`、`*.pyc`、`.DS_Store`、
`.venv/`、`.hub/`、`.curator_backups/`、`*.tar.gz`。

---

## hook 插件（hooks/）

`hooks/agents-md-gate/` 是一个 Hermes 插件，通过 `pre_tool_call` / `post_tool_call` /
`transform_llm_output` 三个 hook 强制执行 `AGENTS.md` 的强制规则：

1. **搜索路由门禁**：未加载 `search-router`（或 `search-first`）技能时，拦截
   `web_search` / `web_extract` 及 MCP 搜索工具；shell 里的 `curl` / `wget` /
   搜索引擎域名同样被拦。
2. **代码库分析提醒**：对大型项目路径使用 `read_file` 时提示改用 codegraph。
3. **状态 TTL**：技能加载状态保留约 2 小时，过期后需重新加载技能。

### 启用方式

```bash
mkdir -p ~/.hermes/plugins
cp -r hooks/agents-md-gate ~/.hermes/plugins/
```

然后在 `~/.hermes/config.yaml` 的 `plugins.enabled` 列表中加入 `agents-md-gate`，
并重启 gateway：

```bash
hermes gateway restart
```

> 修改插件代码后需先删除 `__pycache__` 再重启 gateway（gateway 只在启动时加载插件）。

---

## 技能（skills/）

`skills/` 下目前纳入两个技能：

| 技能 | 作用 |
|---|---|
| `search-router` | 定义搜索路由规则：按搜索类型选引擎、必填参数、降级顺序与已知陷阱 |
| `session-recap` | 扫描会话历史，输出「任务清单 / 关键决策 / 数据变化 / 未完成项」总结图 |

`search-router` 与 `hooks/agents-md-gate/` 配合——插件负责在未加载本技能时
拦截违规的搜索调用。

`session-recap` 有**两个渲染依赖**，均**未纳入本仓库**（见下方「仓库范围」）：

| 依赖技能 | 用途 |
|---|---|
| `answer-me-with-html` | HTML 渲染与出图（`scripts/am.mjs`） |
| `pretty-mermaid` | Mermaid 渲染（`scripts/render.mjs`） |

> `skills/` 下约 58 MB 多为第三方上游内容，**默认不同步**；目前仅纳入指定的两个。
> 如需新增，在 `sync.sh` 中按相同格式加一行即可。

---

## cron 任务清单

`cron/jobs.json` 定义了以下 6 个任务（均为 qqbot 投递）：

| 任务 | 计划 | 用途 |
|---|---|---|
| 工作日早晨提醒 | `0 12 * * *` | 当日工作提醒 |
| 广州番禺天气预报 | `0 9 * * *` | 每日天气 |
| 晚间收尾提醒 | `50 23 * * *` | 收尾复盘 |
| 今日 AI 午报（Tavily） | `30 12 * * *` | AI 新闻简报 |
| 下午的热点新闻速览 | `0 14 * * *` | 热点新闻 |
| 投递简历 | `5 14 * * *` | 校招投递跟进 |

---

## 仓库范围

**当前已纳入**：`AGENTS.md`、`SOUL.md`、`memories/`、`scripts/`、`hooks/`、
`skills/`（`search-router`、`session-recap`）、`cron/jobs.json`

**尚未纳入**：

- `skills/` 其余技能：约 58 MB，含大量第三方上游技能包。**默认不同步**；
  按需指定后在 `sync.sh` 中加对应行。
- `session-recap` 的**两个渲染依赖均未纳入**：`answer-me-with-html`（HTML 渲染，
  含约 1 MB 打包产物 `scripts/am.mjs`）与 `pretty-mermaid`（Mermaid 渲染）。
  只克隆本仓库时，`session-recap` 无法出图，需另行安装这两个技能。
- **永不纳入**（敏感 / 运行时内容）：`config.yaml`、`.env`、`auth.json`、
  `sessions/`、`state.db`、`logs/`、`cache/` 等。
