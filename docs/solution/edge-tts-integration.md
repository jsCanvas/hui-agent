# Edge TTS HTTP 集成说明

> 版本：v1.0 · 2026-07-26  
> 参考实现：`faco/office/share-web-ppt/tts-proxy.py`  
> 关联：[PRD FR-10](../prd/desktop-mcp-client.md#512-fr-10-语音通话tts--stt) · [技术方案](./desktop-mcp-client.md#46-语音模块tts--stt)

---

## 1. 选型结论

HuiAgent Desktop 的 **TTS 默认且优先** 使用 **Microsoft Edge TTS（Neural 语音）**，通过本机 HTTP 代理暴露给 MCP / Socket / 数字人播放层。

| 维度 | Edge TTS HTTP | 离线 piper（降级） |
|------|---------------|-------------------|
| 音质 | ★★★ 拟人化、自然 | ★★ 机械感 |
| 延迟 | 依赖网络，短句 ~0.5–1.5s | ~100ms |
| 离线 | ❌ | ✅ |
| 首期优先级 | **P1 默认** | P2 降级 |

---

## 2. 服务接口（与 tts-proxy.py 一致）

### 2.1 启动

```bash
# 环境变量
export TTS_PROXY_PORT=8896          # 默认
export EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural

python3 tts-proxy.py
# → Edge TTS proxy → http://127.0.0.1:8896
```

HuiAgent Desktop 应在 MCP 启动时 **自动 spawn** 该服务（内嵌 `mcp-server/voice/tts_proxy.py`，逻辑与参考实现保持一致）。

### 2.2 GET /health

```http
GET http://127.0.0.1:8896/health
```

响应：

```json
{"ok": true, "engine": "edge-tts"}
```

### 2.3 POST /tts

```http
POST http://127.0.0.1:8896/tts
Content-Type: application/json

{
  "text": "好的，我正在为您滚动页面，请稍等。",
  "voice": "zh-CN-XiaoxiaoNeural",
  "rate": "+5%",
  "pitch": "+2Hz",
  "volume": "+0%"
}
```

响应：`200` + `Content-Type: audio/mpeg`（MP3 二进制）

错误：`500` + `{"error": "..."}`

### 2.4 字段说明

| 字段 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `text` | ✅ | — | **纯文本**，勿传完整 SSML |
| `voice` | — | `zh-CN-XiaoxiaoNeural` | Edge Neural 音色 ID |
| `rate` | — | `+0%` | 语速，如 `-10%` / `+15%` |
| `pitch` | — | `+0Hz` | 音调 |
| `volume` | — | `+0%` | 音量 |

兼容旧字段 `ssml`：仍按**纯文本**处理（与 tts-proxy 一致）。

---

## 3. 文本清洗（必做）

合成前调用与 tts-proxy 相同的 `_clean_text` 逻辑：

```python
def _clean_text(text: str) -> str:
    t = text.strip()
    t = re.sub(r"https?://\S+", "", t)           # 去掉 URL
    t = re.sub(r"\bdot\s+cursor\b", "Cursor 配置", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()
```

额外建议（HuiAgent Agent 层）：

| 原文 | TTS 可读替换 |
|------|-------------|
| `~/projects/demo` | 「项目 demo 目录」 |
| `FR-10` | 「F R 10」或「需求条目 10」 |
| 长路径 | 只读目录名 |

---

## 4. 推荐音色（数字人助手）

| voice | 描述 | 场景 |
|-------|------|------|
| **`zh-CN-XiaoxiaoNeural`** | 晓晓，年轻女声，自然亲和 | **默认** |
| `zh-CN-XiaoyiNeural` | 晓伊，活泼 | 可选 |
| `zh-CN-XiaohanNeural` | 晓涵，温柔 | 可选 |
| `en-US-JennyNeural` | 英文女声 | 双语场景 |

语气预设（映射到 rate/pitch）：

| 预设 | rate | pitch |
|------|------|-------|
| 自然（默认） | `+5%` | `+2Hz` |
| 沉稳 | `+0%` | `-2Hz` |
| 活泼 | `+12%` | `+5Hz` |

---

## 5. MCP Tool `tts_speak` 实现流程

```
tts_speak(text, voice?, rate?, pitch?, volume?)
    │
    ├─ 1. normalize_text(text)     # 清洗 + 口语化
    ├─ 2. POST http://127.0.0.1:8896/tts
    ├─ 3. 收到 audio/mpeg
    ├─ 4. 播放 + 推送 voice.tts.start / lip-sync
    ├─ 5. 播放结束 → voice.tts.end
    └─ 6. 返回 { duration_ms, voice, engine: "edge-tts" }
```

失败降级（P2）：

```
Edge TTS 失败 → log stderr → 尝试 piper 本地 → 仍失败返回 TTS_UNAVAILABLE
```

---

## 6. 进程与端口

```
HuiAgent Desktop 启动
    ├─ MCP Server (:stdio)
    ├─ Socket Bridge (:18765)
    └─ Edge TTS Proxy (:8896)   ← 新增，随应用生命周期
```

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `TTS_PROXY_PORT` | `8896` | HTTP 端口 |
| `EDGE_TTS_VOICE` | `zh-CN-XiaoxiaoNeural` | 默认音色 |
| `HUI_AGENT_TTS_URL` | `http://127.0.0.1:8896` | MCP 客户端合成地址 |

写入 `~/.hui-agent/config.json`：

```json
{
  "tts": {
    "engine": "edge-tts",
    "url": "http://127.0.0.1:8896",
    "voice": "zh-CN-XiaoxiaoNeural",
    "rate": "+5%",
    "pitch": "+2Hz",
    "volume": "+0%"
  }
}
```

---

## 7. 依赖

```bash
pip install edge-tts
```

`edge-tts` 通过 Bing Speech WebSocket 合成，**需要可访问外网**（无需 API Key）。

---

## 8. 验收

- [ ] `GET /health` 返回 `engine: edge-tts`
- [ ] 短句「好的，我先帮你看一下文档第三节」听感自然，非机械音
- [ ] 含 `https://` 的文本不会读出 URL 字符
- [ ] `tts_stop` 可打断播放
- [ ] 断网时返回明确错误（P2 验证 piper 降级）

---

## 9. 参考源码摘要

来源：`faco/office/share-web-ppt/tts-proxy.py`

```python
comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
await comm.save(path)  # → MP3
```

> **注意**：`edge_tts.Communicate` 将传入字符串当纯文本；切勿传入完整 SSML markup。
