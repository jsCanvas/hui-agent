#!/usr/bin/env python3
"""Socket client: scroll-read a document section and summarize via Agent Runtime."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path


def load_config() -> dict:
    path = Path.home() / ".hui-agent" / "config.json"
    return json.loads(path.read_text(encoding="utf-8"))


def send_line(sock: socket.socket, obj: dict) -> None:
    sock.sendall((json.dumps(obj, ensure_ascii=False) + "\n").encode())


def recv_line(sock: socket.socket) -> dict:
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return json.loads(buf.decode())


def chat_send(host: str, port: int, token: str, text: str) -> dict:
    with socket.create_connection((host, port), timeout=10) as sock:
        send_line(sock, {"type": "auth", "token": token})
        auth = recv_line(sock)
        if auth.get("type") != "auth.ok":
            raise RuntimeError(f"auth failed: {auth}")

        send_line(sock, {"type": "chat.send", "text": text})
        last: dict = {}
        while True:
            msg = recv_line(sock)
            mtype = msg.get("type")
            if mtype == "task.progress":
                print(f"[{msg.get('step')}] {msg.get('message')}", file=sys.stderr)
            elif mtype == "chat.delta":
                last = msg
            elif mtype == "chat.done":
                return last
            elif mtype == "error":
                raise RuntimeError(msg.get("message", msg))


def main() -> int:
    parser = argparse.ArgumentParser(description="Socket → chat.send 完整阅读章节并总结")
    parser.add_argument(
        "text",
        nargs="?",
        default="完整阅读物流服务文档第四节并总结",
        help="发给 Agent Runtime 的任务描述",
    )
    args = parser.parse_args()

    cfg = load_config()
    sock = cfg.get("socket", {})
    host = sock.get("host", "127.0.0.1")
    port = int(sock.get("port", 18765))
    token = sock.get("token", "")
    if not token:
        print("error: missing socket.token in ~/.hui-agent/config.json", file=sys.stderr)
        return 1

    print(f"→ Socket {host}:{port}", file=sys.stderr)
    print(f"→ chat.send: {args.text}", file=sys.stderr)
    result = chat_send(host, port, token, args.text)
    print(result.get("text", ""))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
