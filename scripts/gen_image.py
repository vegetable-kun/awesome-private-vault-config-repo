#!/usr/bin/env python3
"""OpenRouter 生图 → 本地文件（按 media_type 自动选后缀）。

用法:
    set -a; . ~/.hermes/.env; set +a          # 注入凭据（不进 argv）
    python3 gen_image.py --model recraft/recraft-v4.1-flash-v2:free \
        --prompt "snow mountain" --aspect 16:9 --outdir ~/.hermes/images

说明:
    - 走 OpenRouter **dedicated Image API**（POST /api/v1/images）。
      Hermes 内置 image_generate 工具走 chat-completions 协议，对 `:free`
      变体会 404，所以免费模型用本脚本。
    - 凭据从环境变量 OPENROUTER_API_KEY 读，脚本不解析 .env、不进 argv。
    - 输出按 media_type 命名（webp/png/jpeg），可选 --to-png 转码。
    - 计费全有全无：失败不计费，成功按 usage.cost 计。
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

ENDPOINT = "https://openrouter.ai/api/v1/images"
DEFAULT_OUTDIR = Path.home() / ".output" / "photo"

# media_type -> 文件后缀
_EXT = {
    "image/webp": ".webp",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
}


def resolve_token() -> str:
    token = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not token:
        sys.exit("✗ 环境变量 OPENROUTER_API_KEY 未设置；先 `set -a; . ~/.hermes/.env; set +a`")
    return token


def pick_ext(media_type: str | None, fallback: str) -> str:
    if media_type:
        return _EXT.get(media_type.lower(), fallback)
    return fallback


def to_png(src: Path) -> Path:
    """尽力转 PNG；无 PIL 时返回原文件并提示。"""
    try:
        from PIL import Image
    except ImportError:
        print(f"· 无 PIL，跳过转码（保留 {src.suffix}）")
        return src
    dst = src.with_suffix(".png")
    with Image.open(src) as im:
        im.convert("RGB").save(dst)
    print(f"· 已转 PNG: {dst}")
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenRouter 生图（dedicated Image API）")
    ap.add_argument("--model", required=True, help="模型 id，可带 :free")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--aspect", default=None, help="如 16:9 / 1:1（模型支持时）")
    ap.add_argument("--n", type=int, default=None, help="张数（Recraft 1-6）")
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR))
    ap.add_argument("--out", default=None, help="指定输出文件名（不含目录）")
    ap.add_argument("--to-png", action="store_true", help="生成后转 PNG（QQ 通用）")
    ap.add_argument("--send", action="store_true", help="真正调用（可能计费）")
    args = ap.parse_args()

    payload = {"model": args.model, "prompt": args.prompt}
    if args.aspect:
        payload["aspect_ratio"] = args.aspect
    if args.n:
        payload["n"] = args.n

    print("=" * 60)
    print(f"endpoint: {ENDPOINT}")
    print(f"model   : {args.model}")
    print(f"payload : {json.dumps(payload, ensure_ascii=False)}")
    print("=" * 60)

    if not args.send:
        print("· dry-run（未加 --send），不联网、不计费")
        return 0

    outdir = Path(args.outdir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)

    import requests
    token = resolve_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("· 调用中 …")
    t0 = time.time()
    try:
        resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=240)
    except Exception as exc:
        print(f"✗ 请求异常: {exc}")
        return 1
    print(f"· HTTP {resp.status_code}  ({time.time() - t0:.1f}s)")

    try:
        data = resp.json()
    except Exception:
        print(f"✗ 非 JSON 响应: {resp.text[:300]}")
        return 1

    if resp.status_code != 200:
        print(f"✗ 失败（不计费）: {json.dumps(data, ensure_ascii=False)[:500]}")
        return 1

    images = data.get("data") or []
    if not images:
        print("✗ 响应无 data[]")
        return 1

    base = args.out or f"openrouter_{int(time.time())}"
    written = []
    for i, img in enumerate(images):
        b64 = img.get("b64_json")
        if not b64:
            continue
        ext = pick_ext(img.get("media_type"), ".bin")
        name = base if i == 0 and not base.endswith(ext) else f"{base}_{i}"
        path = outdir / f"{name}{ext}"
        path.write_bytes(base64.b64decode(b64))
        written.append(path)
        print(f"✓ [{i}] {img.get('media_type', '?')} → {path}  ({path.stat().st_size} bytes)")

    usage = data.get("usage") or {}
    cost = usage.get("cost")
    print()
    print(f"· 费用: cost={cost}  usage={json.dumps(usage, ensure_ascii=False)}")
    if cost:
        print(f"⚠️ 本次扣费 ${cost}")
    else:
        print("· cost=0 / 未提供 → 免费")

    if args.to_png:
        for p in list(written):
            if p.suffix.lower() != ".png":
                to_png(p)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
