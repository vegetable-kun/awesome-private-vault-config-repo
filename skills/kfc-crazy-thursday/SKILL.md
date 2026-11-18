---
name: kfc-crazy-thursday
description: Use when the user says "疯狂星期四", "KFC疯狂星期四", "V我50", or asks for a Crazy Thursday copy. Fetch a random Chinese KFC copy and output only the original text.
---

# KFC Crazy Thursday 文案

当用户输入“疯狂星期四”、`KFC疯狂星期四`、`V我50`，或明确要求生成肯德基疯狂星期四文案时，使用本 Skill。

## 执行规则

1. 运行 `scripts/fetch.py` 获取 `https://v50.viki.moe/random` 的随机文案。
2. 只按长度判断：返回文本必须 **大于 50 个字符**。
3. 不做色情、暴力、自伤、政治、医疗或其他内容过滤；不调用 LLM 改写原文。
4. 如果文案不超过 50 个字符，重新请求，最多尝试 5 次。
5. 如果网站不可用或连续 5 次都没有得到合格文案，明确报告失败，不编造内容。
6. 最终只向用户返回网站返回的原文；需要时附上来源链接 `https://v50.viki.moe/random`。

## 执行命令

```bash
/home/ecs-assist-user/.hermes/hermes-agent/venv/bin/python3 \
  /home/ecs-assist-user/.hermes/skills/kfc-crazy-thursday/scripts/fetch.py
```

脚本成功时向标准输出打印文案；失败时向标准错误打印原因并返回非零退出码。
