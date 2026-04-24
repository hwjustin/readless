# readless

[English](./README.md) · [中文](./README.zh.md)

本地 MCP server，让 Claude Code（及其他支持 MCP 的 agent）通过 OpenAI TTS 把状态、总结和阻塞问题"念"出来。设计目的是让你在 agent 跑长任务时可以离开屏幕，不丢失对进度的感知。

暴露给 agent 的三个工具：

| 工具 | 调用时机 | 最大词数 |
|---|---|---|
| `speak_summary(headline, details="")` | 用户会关心的任务节点完成时 | ~15 |
| `speak_status(message)` | 长任务中间报进度（服务端限频 1 次/分钟） | ~10 |
| `speak_blocker(question)` | Agent 卡住，需要用户输入。绕过静音时段，打断正在播报的语音。 | ~20 |

## 快速开始

```bash
git clone https://github.com/hwjustin/readless.git
cd readless
./install.sh
# 然后编辑 ~/.readless/config.yaml 填入 OPENAI_API_KEY，
# 把 CLAUDE_EXAMPLE.md 里的中文段落复制到 ~/.claude/CLAUDE.md，
# 重启 Claude Code，让它调一次 speak_summary 验证。
```

`install.sh` 是幂等的：建 venv、`pip install -e .`、从 `config.example.yaml` 拷一份种子配置到 `~/.readless/config.yaml`、跑 `claude mcp add --scope user`。重复跑没事——已经做过的步骤会自动跳过。

## 安装（细节）

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

macOS 上 `sounddevice` 依赖 PortAudio。装失败时：

```bash
brew install portaudio
```

## 配置

把 [`config.example.yaml`](./config.example.yaml) 拷到 `~/.readless/config.yaml`，填入 OpenAI key（或者在 shell 里 export `OPENAI_API_KEY` 环境变量——env 优先级更高）。如果该文件不存在，server 第一次启动也会自动生成默认配置。

没填 key 也能跑——工具会把 `[readless:<kind>] <text>` 打到 stderr 并写入 JSONL log。可以在拿到 key 之前先把 MCP 链路调通。

## 注册到 Claude Code

```bash
claude mcp add --scope user readless -- "$(pwd)/.venv/bin/python" -m readless.server
claude mcp list
```

必须用 venv python 的绝对路径——Claude Code 启动 server 时用的是它自己的 `$PATH`。`--scope user` 表示在所有项目里都可用。

移除：`claude mcp remove readless --scope user`。

## 告诉 agent 怎么用

把 [CLAUDE_EXAMPLE.md](./CLAUDE_EXAMPLE.md) 里的段落贴到 `~/.claude/CLAUDE.md` 或某个项目的 `CLAUDE.md`。这是调节 agent 行为的杠杆——如果 agent 太啰嗦或太安静，改这个段落，不是改代码。

只靠 CLAUDE.md 是模型"自觉"调用，不稳定。想要每轮稳定播报，还要装下面的 Stop hook。

## Stop hook（推荐）

[`hooks/readless_stop.py`](./hooks/readless_stop.py) 是 Claude Code 的 **Stop hook**：在 agent 想结束本轮回复时扫一下，如果本轮没有调用过 `speak_summary`，就 block 掉这次结束，让模型必须调一次再收尾。headline 依然由模型自己写，hook 只保证调用一定发生。

在 `~/.claude/settings.json` 里加：

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "python3 /绝对路径/到/readless/hooks/readless_stop.py" }
        ]
      }
    ]
  }
}
```

把路径换成你 clone 下来的仓库里的绝对路径（`cd readless` 后用 `$(pwd)/hooks/readless_stop.py`）。重启 Claude Code，之后每一轮 agent 回复结束前都会自动播报一条总结。

想关掉就从 `settings.json` 里删掉这段。

## 验证

1. `claude mcp list` 显示 `readless ✓`。
2. Claude Code 里 `/mcp` 能看到 readless 的三个工具。
3. 让 agent："call readless.speak_summary with headline='test'。"
   - 还没填 key → 工具返回 `tts_no_key_logged`，检查 `~/.readless/log.jsonl`。
   - Key 填好 → 笔记本扬声器念出"test"。

## 日志

所有工具调用追加写入 `~/.readless/log.jsonl`：

```json
{"ts": "2026-04-24T10:15:03+08:00", "kind": "summary", "headline": "测试通过", "details": "3 files modified"}
```

## 排错

- **没声音但也没报错**：`OPENAI_API_KEY` 没设。看 stderr 里的 `[readless] (no-key)` 行，或者改 yaml。
- **`sd.PortAudioError: Error querying device`**：音频输出设备缺失或变化。插耳机或在系统设置 → 声音里选个默认输出。
- **Claude Code 看不到 server**：跑 `claude mcp list`——如果没显示，用 venv python 的绝对路径重新跑 `claude mcp add`。加完之后重启 Claude Code。
- **频繁返回 `throttled`**：设计如此——`speak_status` 限频 1 次/分钟。想更密就把 yaml 里的 `status_throttle_seconds` 调小。

## 协议

Apache 2.0——见 [LICENSE](./LICENSE)。

## 设计要点

- `speak_status` 限频在服务端做，重启不保留状态。Agent "调得太频"不算错误。
- `speak_blocker` 会打断正在播报的语音并忽略静音时段——既然你启动了长任务，那应该有精力来解锁。
- 没有终端反向总结、没有 STT、没有多 TTS backend 抽象。v1 故意做薄。

## 结构

```
src/readless/
  server.py    FastMCP 入口 + 工具定义
  tts.py       OpenAI 流式 -> sounddevice + 无 key / 失败回落
  config.py    YAML + 环境变量加载 + 静音时段计算
  throttle.py  StatusThrottle（带测试）
  logger.py    JSONL 追加写
hooks/
  readless_stop.py  Claude Code Stop hook（强制每轮调用 speak_summary）
tests/
  test_throttle.py
```
