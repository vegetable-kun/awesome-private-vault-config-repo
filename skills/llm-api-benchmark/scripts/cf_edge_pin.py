#!/usr/bin/env python3
"""Find Cloudflare edge IPs that complete a TLS handshake for a hostname.

Use when a Cloudflare-fronted host hangs after the TLS ClientHello (TCP
connects, no Server hello). Cloudflare is anycast: every edge IP answers for
every zone, so a reachable edge IP can serve a host whose default-resolved
addresses are filtered.

Usage:
  python3 cf_edge_pin.py inference-api.nousresearch.com --path /v1/models
  python3 cf_edge_pin.py openrouter.ai --json
"""

import argparse
import concurrent.futures
import json
import socket
import ssl
import sys

CANDIDATES = [
    "188.114.96.1", "188.114.97.1", "188.114.98.1", "188.114.99.1",
    "162.159.140.1", "162.159.36.1", "162.159.44.1",
    "104.20.0.1", "104.20.1.1", "104.21.0.1", "104.22.0.1",
    "172.64.80.1", "172.66.0.1",
    "104.16.132.229", "104.17.0.1", "104.18.0.1", "104.19.0.1",
    "108.162.192.1", "141.101.64.1", "190.93.240.1",
    "198.41.128.1", "131.0.72.1", "103.21.244.1",
]


def probe(ip, host, path, timeout):
    """Return (ip, status_line): TLS handshake plus one HTTP request."""
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((ip, 443), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                request = (
                    f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                    "Connection: close\r\n\r\n"
                )
                ss.sendall(request.encode())
                return ip, ss.recv(120).decode(errors="replace").split("\r\n")[0]
    except Exception as exc:  # timeout, reset, cert mismatch, ...
        return ip, f"FAIL {type(exc).__name__}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("host", help="hostname to reach (used as SNI and Host header)")
    ap.add_argument("--path", default="/", help="path to request (default /)")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(
            pool.map(
                lambda ip: probe(ip, args.host, args.path, args.timeout),
                CANDIDATES,
            )
        )

    reachable = [(ip, status) for ip, status in results if status.startswith("HTTP/")]

    if args.json:
        print(json.dumps({
            "host": args.host,
            "working": [ip for ip, _ in reachable],
            "detail": {ip: status for ip, status in results},
        }, indent=2))
    else:
        for ip, status in results:
            print(f"{ip:18} {status}")

    # With --json the summary must not pollute stdout (callers pipe it into a parser).
    summary = sys.stderr if args.json else sys.stdout

    if not reachable:
        print(
            "No edge IP completed TLS — the block is probably not IP-level.",
            file=sys.stderr,
        )
        return 1

    print(f"Working: {' '.join(ip for ip, _ in reachable)}", file=summary)
    first = reachable[0][0]
    print(f"Pin one: curl --resolve {args.host}:443:{first} https://{args.host}{args.path}", file=summary)
    print("A 403 here just means 'no auth header sent' — re-test with real headers.", file=summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
