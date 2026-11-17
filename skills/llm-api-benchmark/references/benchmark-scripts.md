# 基准测试脚本模板

异步模型可用性扫描器 + 串行基准测试。

## scan.py — 查找可调用的模型

```python
#!/usr/bin/env python3
"""扫描哪些模型实际可调（异步 + 并发）。"""
import os, asyncio, json
from openai import AsyncOpenAI

API_KEY = os.environ["NVIDIA_API_KEY"]
BASE = "https://integrate.api.nvidia.com/v1"

ALL_MODELS = [...]  # 从 /v1/models 填充

async def test_one(client, model_id):
    try:
        r = await asyncio.wait_for(
            client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=30,
            ),
            timeout=15,
        )
        return model_id, True, r.usage.completion_tokens
    except Exception as e:
        return model_id, False, type(e).__name__

async def main():
    client = AsyncOpenAI(base_url=BASE, api_key=API_KEY, timeout=15)
    sem = asyncio.Semaphore(10)
    async def limited(mid):
        async with sem:
            return await test_one(client, mid)
    results = await asyncio.gather(*[limited(m) for m in ALL_MODELS])
    ok = [(m, t) for m, s, t in results if s]
    fail = [(m, t) for m, s, t in results if not s]
    print(f"可用: {len(ok)}/{len(results)}")
    for m, t in ok:
        print(f"  ✓ {m}: {t} tok")
    with open("/tmp/available.json", "w") as f:
        json.dump({"ok": ok, "fail": fail}, f)

if __name__ == "__main__":
    asyncio.run(main())
```

## bench.py — 测量延迟/吞吐

```python
#!/usr/bin/env python3
"""基准测试可调模型——串行，5 秒间隔，流式。"""
import os, time, json
from openai import OpenAI

API_KEY = os.environ["NVIDIA_API_KEY"]
BASE = "https://integrate.api.nvidia.com/v1"
GAP_S = 5

SYSTEM = "You are a concise assistant. Answer in 2-3 sentences max."
PROMPT = "Explain the difference between synchronous and asynchronous programming."

MODELS = [
    (1, "openai/gpt-oss-20b", "GPT-OSS-20B"),
    # ... 从扫描结果补充可用模型
]

def bench(rank, model_id, label):
    client = OpenAI(base_url=BASE, api_key=API_KEY, timeout=60)
    t0 = time.perf_counter()
    first_t = None
    stream = client.chat.completions.create(
        model=model_id,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":PROMPT}],
        max_tokens=256,
        temperature=0.3,
        stream=True,
    )
    chunks = []
    usage = None
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            if first_t is None:
                first_t = time.perf_counter()
            chunks.append(chunk.choices[0].delta.content)
        if chunk.usage:
            usage = chunk.usage
    t1 = time.perf_counter()
    ttft = first_t - t0 if first_t else None
    gen_time = t1 - first_t if first_t else None
    comp_tok = usage.completion_tokens if usage else None
    tps = (comp_tok / gen_time) if (comp_tok and gen_time) else None
    return {
        "rank": rank, "label": label, "model": model_id,
        "ttft_s": round(ttft, 3) if ttft else None,
        "gen_time_s": round(gen_time, 3) if gen_time else None,
        "tokens_per_sec": round(tps, 2) if tps else None,
        "completion_tokens": comp_tok,
    }

def main():
    for i, (rank, mid, label) in enumerate(MODELS):
        if i > 0:
            time.sleep(GAP_S)
        r = bench(rank, mid, label)
        print(f"{r['rank']} {r['label']}: TTFT {r['ttft_s']}s | {r['tokens_per_sec']} tok/s")

if __name__ == "__main__":
    main()
```

## 用法

```bash
# 第一步：扫描
NVIDIA_API_KEY=$(grep NVIDIA_API_KEY ~/.hermes/.env | cut -d= -f2-) \
  ~/.hermes/hermes-agent/venv/bin/python3 scan.py

# 第二步：基准测试（用可用模型更新 MODELS 列表）
NVIDIA_API_KEY=$(grep NVIDIA_API_KEY ~/.hermes/.env | cut -d= -f2-) \
  ~/.hermes/hermes-agent/venv/bin/python3 bench.py
```
