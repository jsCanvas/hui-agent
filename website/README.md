# 官网演示序列帧

四套动画**全部**从 `seq-webp/greetings` 同角色采样（与 `greetings/frame_0001.webp` 一致），按 tab 切换不同区段：

| Tab | 序列 | 区段 |
|-----|------|------|
| STT | listening | 早期微动 |
| 边缘 ack | greetings | 挥手问候 |
| Relay / 读屏 | idle | 慢速待机 |
| TTS | speaking | 中段表情 |

```bash
cd website && bash scripts/prepare-demo-frames.sh
```

**禁止**回退到 `seq/*.png` 或 `seq-webp/listening`（旧版错误形象）。
