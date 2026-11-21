---
name: research
description: 针对高可信度原始来源调研问题，将发现结果保存为仓库中的 Markdown 文件。用于用户想调研某个主题、收集文档或 API 事实，或希望将阅读工作委派给后台 agent 时。
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.

## Pitfalls

- **变更/发布调研先取官方口径，不要从源码反推。** 用户问「某版本更新了什么」时，一手答案是 release notes / changelog / PR 描述——那是维护者自己的结论，权威、快，且与用户看到的口径一致。逐文件读源码实现既慢，又容易给出与官方不一致的解读。只有官方 notes 明确留空（例如 release body 写明 "undocumented on purpose"）时才用源码 diff 补齐，并标注那是你的推断、不是官方结论。
- **Official pages often embed data in images or PDFs that aren't text-extractable.** Government/university admissions pages especially: cutoff lines, admission counts, and score distributions are frequently published as scanned images or PDF tables. `web_extract` returns empty or garbled text for these. When you hit this, note explicitly that the data is **image/PDF-only** and cannot be machine-verified; do not silently skip it or fabricate numbers.
- **Third-party transcriptions are not official data.** Sites like chinakaoyan, zhihu, CSDN often transcribe official image/PDF data into text. These can be useful leads but **must be labeled as third-party** and cross-checked against the original whenever possible. Never present a third-party transcription as an official figure.
- **When official data is unavailable, say so.** If the only data available is third-party or unverified, state that clearly in the findings rather than presenting it as authoritative. The user's trust in the research depends on this distinction.
