"""Edge TTS HTTP proxy — same contract as faco/office/share-web-ppt/tts-proxy.py."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

try:
    import edge_tts
except ImportError:
    print("请先安装: pip install edge-tts", file=sys.stderr)
    sys.exit(1)

DEFAULT_PORT = int(os.environ.get("TTS_PROXY_PORT", "8896"))
DEFAULT_VOICE = os.environ.get("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
DEFAULT_HOST = os.environ.get("TTS_PROXY_HOST", "127.0.0.1")


def clean_text(text: str) -> str:
    """Remove URLs and noisy tokens before synthesis."""
    t = text.strip()
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\bdot\s+cursor\b", "Cursor 配置", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


async def synthesize(
    text: str,
    voice: str,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%",
) -> bytes:
    text = clean_text(text)
    if not text:
        raise ValueError("text is empty after cleanup")
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
    fd, path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        await comm.save(path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)


class TTSHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[tts-proxy] {fmt % args}", file=sys.stderr)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true,"engine":"edge-tts"}')
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/tts":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n))
            text = body.get("text") or body.get("ssml")
            if not text:
                raise ValueError("text required")
            data = asyncio.run(
                synthesize(
                    text,
                    body.get("voice", DEFAULT_VOICE),
                    body.get("rate", "+0%"),
                    body.get("pitch", "+0Hz"),
                    body.get("volume", "+0%"),
                )
            )
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(500)
            self._cors()
            self.send_header("Content-Type", "application/json")
            msg = json.dumps({"error": str(e)}, ensure_ascii=False).encode()
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    srv = ThreadedHTTPServer((host, port), TTSHandler)
    print(f"Edge TTS proxy → http://{host}:{port}", file=sys.stderr)
    print("  POST /tts   JSON {text, rate?, pitch?, volume?, voice?}", file=sys.stderr)
    print("  GET  /health", file=sys.stderr)
    srv.serve_forever()


def main() -> None:
    import urllib.error
    import urllib.request

    health_url = f"http://127.0.0.1:{DEFAULT_PORT}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=1) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("ok"):
                    print(
                        f"TTS proxy already running on {health_url}, skip",
                        file=sys.stderr,
                    )
                    return
    except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError, ValueError):
        pass

    serve(DEFAULT_HOST, DEFAULT_PORT)


if __name__ == "__main__":
    main()
