"""Concurrency demo: open N clients in parallel, send STATUS, measure latency.

Usage:
    python -m scripts.demo_load --host localhost --port 8080 --clients 20

Output:
    - Per-client elapsed time
    - Total wall-clock time
    - Server-reported thread snapshot (from STATUS response)

For the school demo, point this at the coordinator server. Run once with
CLIENT_MAX_WORKERS=1 and once with CLIENT_MAX_WORKERS=8 (set in .env or
env vars) to show speedup.
"""
from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import threading
import time
import uuid
from pathlib import Path

# Allow `python scripts/demo_load.py` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HEADER_FMT = "!I"
HEADER_SIZE = 4


def send_frame(sock: socket.socket, payload: bytes) -> None:
    sock.sendall(struct.pack(HEADER_FMT, len(payload)) + payload)


def recv_frame(sock: socket.socket) -> bytes:
    header = recv_exact(sock, HEADER_SIZE)
    (length,) = struct.unpack(HEADER_FMT, header)
    return recv_exact(sock, length)


def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed mid-frame")
        buf.extend(chunk)
    return bytes(buf)


def one_client(host: str, port: int, msg_type: str, results: list, idx: int) -> None:
    request_id = str(uuid.uuid4())
    msg = json.dumps({"type": msg_type, "requestId": request_id, "payload": {}}).encode()
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=10) as sock:
            send_frame(sock, msg)
            raw = recv_frame(sock)
        elapsed = time.perf_counter() - start
        resp = json.loads(raw.decode())
        results.append((idx, elapsed, resp))
    except Exception as e:
        elapsed = time.perf_counter() - start
        results.append((idx, elapsed, {"error": str(e)}))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--clients", type=int, default=20, help="parallel client count")
    parser.add_argument(
        "--msg",
        default="STATUS",
        choices=["STATUS", "PING"],
        help="message type to send",
    )
    args = parser.parse_args()

    print(f"Spawning {args.clients} parallel clients -> {args.host}:{args.port} [{args.msg}]")
    results: list = []
    threads = []

    wall_start = time.perf_counter()
    for i in range(args.clients):
        t = threading.Thread(
            target=one_client,
            args=(args.host, args.port, args.msg, results, i),
            name=f"DemoClient-{i}",
        )
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    wall_elapsed = time.perf_counter() - wall_start

    results.sort()
    latencies = [r[1] for r in results]
    print()
    print("Per-client latency (s):")
    for idx, elapsed, _ in results:
        print(f"  client {idx:3d}: {elapsed*1000:8.1f} ms")
    print()
    print(f"Wall-clock total : {wall_elapsed*1000:.1f} ms")
    print(f"Avg per client   : {sum(latencies)/len(latencies)*1000:.1f} ms")
    print(f"Max per client   : {max(latencies)*1000:.1f} ms")

    # Print thread snapshot from the last STATUS response we got
    last_status = next(
        (r[2] for r in reversed(results) if r[2].get("type") == "STATUS_RESPONSE"),
        None,
    )
    if last_status:
        threads_info = last_status.get("payload", {}).get("threads")
        if threads_info:
            print()
            print("Server thread snapshot (from STATUS response):")
            print(f"  total      : {threads_info.get('total')}")
            print(f"  by prefix  : {threads_info.get('byPrefix')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
