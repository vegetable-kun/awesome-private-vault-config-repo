---
name: session-recap
description: 用户说「查看本轮会话完成情况」时，总结会话内容并渲染成图片。
version: 0.1.0
author: 坤 (vegetable-kun), Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [session, recap, summary, visualization]
    related_skills: [answer-me-with-html, pretty-mermaid]
---

# 会话完成情况总结

当用户说「查看本轮会话完成情况」时，扫描当前会话历史，生成完整的可视化总结（任务清单+状态、关键决策、数据变化、未完成项），渲染成 HTML 或 Mermaid 图片并通过 MEDIA: 发送。不编造会话中未发生的内容。

## When to Use

- 精确短语：「查看本轮会话完成情况」
- 近似变体：「查看会话完成情况」「本轮会话总结」「会话完成情况」
- **不适用于**：用户要求总结某个文件/项目（非会话）、或要求生成报告文档

## Prerequisites

- `answer-me-with-html` skill（HTML 渲染）
- `pretty-mermaid` skill（Mermaid 渲染）
- Node.js 20+（am.mjs / render.mjs 依赖）
- `~/.hermes/hermes-agent/venv/bin/python3`（am2png.py 依赖 PIL）

## Procedure

1. **收集** — 扫描当前会话历史中的所有用户请求和 Agent 响应。完成标准：会话中每个用户消息都被扫描到。
2. **提取** — 构建总结，包含以下部分：
   - 任务清单及状态（✅ 完成 / ⏳ 进行中 / ❌ 未完成）
   - 会话中的关键决策
   - 数据变化（之前 → 之后，附具体数字）
   - 未完成项
   - 当前状态总结
   完成标准：五个部分都有内容，无遗漏。
3. **选择输出格式**：
   - 结构化对比 / 多面板 / 表格 → HTML（`answer-me-with-html`）
   - 流程 / 时间线 / 时序 → Mermaid（`pretty-mermaid`）
   - **无法判断时默认用 HTML**
   完成标准：格式选择有明确理由。
4. **清理输出目录** — 渲染前清理 `~/.output/`：删超过 7 天的旧文件，并删 `photo/*.webp`（原始格式，PNG 已转好）与 `pages/*.html`（源文件，PNG 已生成）。**只保留 PNG**。完成标准：`~/.output` 内无 webp / html，PNG 齐全。
5. **渲染**：
   - HTML：`AM_HOME=~/.output node ~/.hermes/skills/answer-me-with-html/scripts/am.mjs render - <<'AM_EOF' ... AM_EOF`
   - Mermaid：`node ~/.hermes/skills/pretty-mermaid/scripts/render.mjs --input <file>.mmd --output ~/.output/<file>.png --format png --theme tokyo-night`
   完成标准：渲染命令退出码 0，输出文件非空。
6. **转 PNG**（仅 HTML）：
   ```bash
   ~/.hermes/hermes-agent/venv/bin/python3 \
     ~/.hermes/skills/answer-me-with-html/scripts/am2png.py \
     ~/.output/<page.html> ~/.output/<page.png>
   ```
   完成标准：PNG 文件生成且大小 > 10KB。**`am2png.py` 成功行里的尺寸（如 `1280x2`）不是最终尺寸** —— 用 PIL 读实际宽高确认，别据此重渲染。**Mermaid 路径跳过此步**，直接进入验证。
7. **验证** — 用 `vision_analyze` 读回图片确认内容完整、无截断。完成标准：图片中所有面板文字可见。
8. **发送** — 单独一行 `MEDIA:~/.output/<output.png>`。完成标准：QQ 消息中出现图片。

## Output Rules

- 语言：简体中文
- 格式：§ 分隔符，无行号
- QQ 发送：始终渲染 PNG 并用 MEDIA: 发送
- **统一输出目录：`~/.output/`**（HTML 和 Mermaid 共用）
- HTML 渲染：设置 `AM_HOME=~/.output`，输出到 `~/.output/pages/`（am.mjs 自动创建 pages 子目录）
- Mermaid 渲染：`--output ~/.output/<file>.png`，直接放 `~/.output/`
- 旧图清理：渲染前清理 `~/.output/` 中超过 7 天的文件；**只保留 PNG**（删 webp 原始格式与 `pages/*.html` 源文件）

## Pitfalls

- 使用 HTML 渲染前先加载 `answer-me-with-html` skill；使用 Mermaid 渲染前先加载 `pretty-mermaid`
- 只总结会话中实际发生的内容，不得编造
- 会话很短（1-2 轮）时仍生成总结，但保持简洁
- 未经用户同意不得运行 `am clean` 或更新命令
- Mermaid 中文字体可能缺失——如渲染出乱码，改用 HTML

## Verification

1. 渲染命令退出码 0，输出文件非空
2. PNG 大小 > 10KB（过小说明截断）
3. 读回图片：所有面板标题和表格行可见
4. QQ 消息中 MEDIA: 行触发图片发送
5. 总结内容与会话历史一致——无编造任务或状态