---
name: search-router
description: 搜索路由：根据搜索类型选择最佳搜索引擎。用户要求搜索时调用。
metadata:
  origin: user-defined
tools: tool_search, tool_describe, tool_call
---

# Search Router

根据搜索类型自动路由到最佳搜索引擎。

## 路由规则

| 搜索类型 | 关键词特征 | 优先工具 | 备选 |
|----------|-----------|----------|------|
| 综合/模糊/多源 | "查找" "搜索" "了解" "介绍" | mcp__anysearch__search | mcp__tavily__tavily_search |
| 技术文档/学术/官方 | "技术文档" "论文" "官方文档" "深度研究" "API" | mcp__exa__web_search_exa | mcp__firecrawl__firecrawl_search |
| 垂直领域（金融/代码/法规等） | "股价" "汇率" "航班" "代码库" "法规" "临床试验" | mcp__anysearch__search（先 get_sub_domains） | mcp__firecrawl__firecrawl_search |
| 结构化提取/详情页 | "提取" "抓取" "详情页" "结构化" | mcp__firecrawl__firecrawl_scrape | mcp__anysearch__extract（仅单 URL） |
| 兜底 | 以上工具均不可用/超限/报错 | web_search（原生） | 无 |

> ⚠️ **不要用需要数组参数的工具**：`batch_search`、`tavily_extract`、`exa__web_fetch_exa` 
> 的数组入参在本环境下会被改写而报错（4/4 复现），且无标量替代。
> 跨 URL 提取改用 `firecrawl__scrape` 逐个抓。详见 `references/engines.md`。

## 必填参数硬规则

调任何引擎前先过这三条，漏了必报错：

1. **exa 必须带 `objective`** —— `web_search_exa` 必填 `query` + `objective`
   （REST 层 optional，**MCP 层 required**）
2. **anysearch vertical 搜索前必须先调 `get_sub_domains`** —— 
   `sub_domain_params` 只能用它返回的值，禁止自造
3. **firecrawl 要实时数据必须 `maxAge=0`** —— 默认会返回缓存内容

## 调用流程

1. 判断搜索类型 → 匹配上表
2. 检查工具是否可用（tool_search → tool_describe → tool_call）
   ⚠️ 系统提示里的工具 catalog 不完整（漏 13 个，含 exa 全家），**必须 tool_search 确认**
3. 执行搜索
4. 在回复开头显式告知：[搜索工具] 工具名: "查询词"
   ⚠️ 这个标记**由门禁插件的 `transform_llm_output` 自动前置**，别自己手写 ——
   插件只对「完全相同的开头」去重，你换个措辞手写就会变成两行标记。
   `[skill] <名>` 同理，也是插件注入的。
   （插件只把**搜索引擎**类调用写进这行；shell 里的 `gh api` / `requests.get`
   不出现，那是刻意去掉的噪音。）
5. 失败时降级到下一优先级工具

### ⚠️ 长会话里要重新加载本 skill

> **先确认本 skill 是否已由 `skills.auto_load` 常驻**。配置了 auto_load 且门禁插件
> 认它（插件把 auto_load 中的技能也算作已加载）时，本会话从第一轮起就满足门禁，
> **不会出现下面的拦截**，本节只在未配置 auto_load 时才适用。

门禁记的是「本次会话是否加载过 search-router」，而这个状态**有 TTL（约 2 小时）**。
在一个跑了很久的会话里（部署、调试、长时间排查），早先的加载会**过期**，
下一次搜索会被拒：`🚫 搜索路由违规：你尚未加载搜索路由 skill`。

被拒时不要换工具、不要改用原生 web_search —— 直接 `skill_view(name='search-router')`
重新加载一次，然后重试即可。**同一个工具连续被拒 2 次就换引擎**这条不适用于此情况。

**`gh api` 也吃这条 TTL，别以为它是例外。** 它不在硬拦名单里（不像 curl/wget/搜索域名），
所以「取数不会因为命令本身被拒」——但只要本会话没加载过本 skill，
`execute_code`/`terminal` 里的 `gh api` 一样会被 `搜索路由违规（shell 出口）` 挡下。
拿 `gh api` 取数前同样先确认本 skill 已加载。

### ⚠️ shell 出口门禁也拦 curl / wget / python 联网

拦截**不只在调 MCP 引擎时发生**，`terminal` / `execute_code` 里的 shell 出口同样受门禁约束。
以下命令都会被 `🚫 搜索路由违规（shell 出口）` 挡下，**且被拦时返回空输出**——
看起来像「这个源没数据」「这个包不存在」，极易误判：

| 命令 | 典型用途 |
|------|---------|
| `curl` / `wget` | 抓 RSS、抓网页、探活 |
| `python3 -c "import requests …"` / `urllib` | 脚本化取数 |
| `pip download` / `curl -L -o pkg.deb` | **下载二进制/安装包**（常被误认为与搜索无关而漏防） |

规则：**本会话先加载过本 skill**（或它在 `skills.auto_load` 里），shell 出口才放行；
TTL 过期后，早先的加载不再作数。被拦时不要换工具、不要改用原生 `web_search`——
`skill_view(name='search-router')` 重载一次，然后原命令重试即可。

**被拦的代价不对称**：本地命令（`ls`/`grep`/`git`/`cat`）不受限，所以一次拦截往往
表现为「本地那半跑完了、联网那半静默返回空」。**任何依赖联网输出的判断，都要先确认
门禁已满足再执行**，否则你会拿着空数据去推理。

**降级纪律同样适用**：`curl` 被拦 ≠ 换搜索引擎。先重载 skill；重载后仍被拦，
再改用 MCP 引擎（`anysearch__extract` / `firecrawl__scrape`）取那个已知 URL 的内容。

### ⚠️ MCP 工具间歇性不可用

anysearch / exa / firecrawl 等 MCP 工具可能在会话中途变得不可用（直接调用报
"Tool does not exist"），但通过 `tool_search` + `tool_describe` + `tool_call`
链路仍然可用。**遇到直接调用失败时，不要放弃，改用 tool_call 链路重试。**

### ⚠️ 降级触发条件

同一工具**连续失败 2 次就换引擎**，不要重试第三次 ——
MCP 服务端会进入 41–51 秒暂停窗口，期间所有调用一律被拒。
anysearch 不可用时首选 `mcp__tavily__tavily_search` 替代（实测 1.2s）。

## 组合搜索策略

复杂任务可组合多工具：
- P0 广度覆盖 → P1 深度挖掘 → P3 结构化提取
- 例：先用 anysearch 找概览 → 再用 exa 查技术细节 → 最后 firecrawl 提取具体数据

## 已知来源取数：不走搜索引擎

（npm 包的完整 intake 流程见 `comparison-research` 技能下的 `agent-extension-marketplaces.md` 参考文件）

**先问一句「我需要的是搜索，还是已知位置的取数？」** 目标仓库 / 组织 / 文件已知时，
搜索引擎只会给你二手转述，直接读源：

| 需求 | 正确工具 |
|------|----------|
| GitHub 仓库元数据 / 目录树 / 文件内容 / release | **`gh api`**（不在硬拦名单，但**同样受本会话加载门禁约束**） |
| 已知 URL 的网页正文 | `mcp__anysearch__extract`（仅 HTML）/ `mcp__firecrawl__firecrawl_scrape` |
| GitHub 上的模糊检索（不知道 owner） | `gh api 'search/repositories?q=...'` 或 `gh api 'search/code?q=repo:owner/name+kw'` |
| npm 包元数据（版本/下载量/依赖/许可） | 包的**市场页**（如 `https://<marketplace>/packages/<pkg>`）一页拿全：版本、发布日期、月/周下载量、作者、许可、体积、依赖数、manifest、README。**不要用 shell `curl` 打 registry** —— shell 出口会被 AGENTS.md 门禁拦下，且被拦时返回空输出，看起来像“这个包不存在” |

**为什么**：`gh api` 返回结构化 JSON，可直接 `--jq` 取字段；搜索引擎返回的是
转述和过期快照。本次对比 6 个 agent 项目时，⭐/语言/许可/创建日期全部来自
`gh api 'repos/<owner>/<repo>'`，一次调用拿全，比搜 6 次再拼凑可靠得多。

**⚠️ 别用重定向落盘取内容**：`gh api ... > /tmp/x.md` 会让 Hermes 把该文件当附件
发给用户。用管道内联，或直接读 stdout：

```bash
# ❌ 会触发自动附件投递
gh api 'repos/o/r/contents/README.md' -H 'Accept: application/vnd.github.raw' > /tmp/rm.md
# ✅ 管道内联
gh api 'repos/o/r/contents/README.md' -H 'Accept: application/vnd.github.raw'
# ✅ 单字段用 --jq，天然免重定向
gh api 'repos/o/r' --jq '"\(.stargazers_count)|\(.language)|\(.license.spdx_id)"'
```

**读大仓库源码的定位顺序**（避免一次拉整个树）：

```bash
gh api 'repos/o/r/contents/'            --jq '.[]|"\(.type)|\(.name)"'   # 顶层
gh api 'repos/o/r/contents/packages'    --jq '.[]|"\(.type)|\(.name)|\(.size)"'  # 逐层下探
```
`size` 字段很有用 —— 一眼看出哪个文件是核心实现（如 `agent-loop.ts` 29KB vs
`index.ts` 170B）。

**读超长 release body / README：先列标题行号，再按行切片**

`gh api ... --jq '.body'` 一次拉回来会被工具输出上限（约 50KB）**从中间截断**，
而且截断标记会混进你拿到的字符串 —— 之后再按长度切片，就是在一份中间有洞的内容上
操作，整段章节会被静默漏掉。先量大小，再按结构取数：

```bash
# 0) 先量大小，判断要不要分片
gh api 'repos/o/r/releases/tags/TAG' --jq '.body | length'

# 1) 取结构：只打印标题和行号，输出很小
gh api 'repos/o/r/releases/tags/TAG' --jq '.body' | python3 -c "
import sys
lines=sys.stdin.read().splitlines()
print('TOTAL_LINES', len(lines))
for i,l in enumerate(lines):
    if l.startswith('#'): print(i, l[:95])
"

# 2) 按行号切片，只打印要的章节
gh api 'repos/o/r/releases/tags/TAG' --jq '.body' | python3 -c "
import sys
lines=sys.stdin.read().splitlines()
print('\n'.join(lines[220:241]))
"
```

先拿行号表再按章节取数，每次输出都在上限内，且不会漏段。
同一手法适用于超长 README、issue body 和任何大 JSON 字段。

**比对上游版本时取指定 tag，不要只取最新**

判断一个本地已改过的第三方 skill/文件要不要更新时，**必须把旧版上游也拉下来**：

```bash
gh api 'repos/o/r/contents/path/to/FILE?ref=v1.2.3' --jq '.content' \
  | python3 -c "import sys,base64; print(base64.b64decode(sys.stdin.read().strip()).decode())"
```

只做「本地 vs 最新」的 diff，会把**你自己的本地适配**和上游改动混在一起，
一行上游改动看起来像整篇重写。取旧 tag 做 tag→tag 对比，才看得到上游真正改了什么；
看完再决定是否把本地适配重新贴回去（直接覆盖会丢掉适配，功能失效）。

## 禁止行为

- ❌ 不检查就直接用原生 web_search
- ❌ 工具失败就放弃（必须降级到下一优先级工具）
- ❌ 搜索后不告知工具名称
- ❌ 同一工具连续失败 3 次（会触发服务端暂停）
- ❌ 拿 anysearch__extract 抓 GitHub / SPA 等 JS 页面（官方限定 HTML only）

## 引擎速查

引擎的必填参数、批量能力、时效性、调用陷阱见 `references/engines.md`。