#!/usr/bin/env python3
"""Fetch a KFC Crazy Thursday copy longer than 50 characters."""

from __future__ import annotations

import argparse
import random
import sys
import time

import httpx

URL = "https://v50.viki.moe/random"
MIN_CHARS = 50
DEFAULT_ATTEMPTS = 3
DEFAULT_TIMEOUT = 10.0
BACKOFF_MIN = 5.0
BACKOFF_MAX = 12.0
USER_AGENT = "Hermes-KFC-Crazy-Thursday/1.0"


def fetch_text(
    min_chars: int = MIN_CHARS,
    max_attempts: int = DEFAULT_ATTEMPTS,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """Return the first response longer than ``min_chars`` characters.

    This function intentionally performs no content filtering. It only checks
    the character count and retries when a response is too short.
    """
    last_error: Exception | None = None

    with httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for attempt in range(max_attempts):
            if attempt:
                delay = random.uniform(BACKOFF_MIN, BACKOFF_MAX)
                print(
                    f"第 {attempt} 次未达标，退避 {delay:.1f}s 后重试…",
                    file=sys.stderr,
                )
                time.sleep(delay)
            try:
                response = client.get(URL)
                response.raise_for_status()
                text = response.text.strip()
            except (httpx.HTTPError, UnicodeError) as exc:
                last_error = exc
                continue

            if len(text) > min_chars:
                return text

    if last_error is not None:
        raise RuntimeError(
            f"请求文案接口失败，已尝试 {max_attempts} 次：{last_error}"
        ) from last_error

    raise RuntimeError(
        f"已尝试 {max_attempts} 次，没有获取到超过 {min_chars} 字的文案"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="获取一则大于 50 字的肯德基疯狂星期四随机文案"
    )
    parser.parse_args()
    try:
        text = fetch_text()
    except RuntimeError as exc:
        print(f"获取文案失败：{exc}", file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
