# 原神原琴 AI 编谱

> [English](./README.en.md) · 简体中文

将网络上的 MIDI 文件或音频转写为可在《原神》风物之诗琴上演奏的琴谱。
基于 Python（FastAPI）+ React 全栈实现：搜索 MIDI、解析音轨、自动映射至原琴 21 键，并同时生成三个版本的琴谱（纯旋律版、简化伴奏版、完整伴奏版）。

## 功能概览

- **MIDI 搜索**：从 FreeMIDI、BitMIDI、MuseScore、B 站四个平台并发搜索 MIDI 文件并下载。
- **音频转 MIDI**：粘贴 YouTube / Bilibili / QQ 音乐链接，或上传本地 mp3/m4a/mp4，使用 Spotify Basic Pitch 自动转写为 MIDI（钢琴独奏效果最佳）。
- **轨道配置**：自动识别主旋律 / 伴奏 / 低音 / 打击乐，可在「轨道配置」页面手动调整角色，并支持每个轨道的预听（钢琴音色，原琴音 / 原始音可切换）。
- **三版琴谱并行生成**：
  - **纯旋律版** — 仅主旋律，单手入门。
  - **简化伴奏版** — 主旋律 + 精简伴奏，单人演奏的最佳折中。
  - **完整伴奏版** — 主旋律 + 全部伴奏音符，参考或双人合奏。
- **三种琴谱视图**：人类阅读谱（按小节分组）、PC 字母谱（单行）、手机数字谱（单行）。节奏由空格直接编码，便于跟谱。

## 快速开始

### 后端

需先准备 Python 3.11+（建议 3.12）。可使用 [pyenv](https://github.com/pyenv/pyenv)、Homebrew、系统包管理器或 [官方安装包](https://www.python.org/downloads/) 任选其一。下面命令中的 `python` 默认指向已安装的 3.11+ 解释器。

```bash
cd backend
python -m venv .venv
source .venv/bin/activate         # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API 文档：<http://localhost:8000/docs>

### 前端

需先准备 Node 18+（建议 20）。

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

打开：<http://localhost:5173>

### 运行测试

激活后端虚拟环境后：

```bash
cd backend
pytest -v
```

可选：跑慢测试（首次 Basic Pitch 加载模型 ~30 秒）

```bash
pytest -m slow -v
```

## 系统依赖

- **ffmpeg** 必须在 `PATH` 中（音频管线用它解码 `.mp3` / `.m4a` / `.mp4`）：
  - macOS：`brew install ffmpeg`
  - Debian / Ubuntu：`sudo apt install ffmpeg`
  - Windows：从 [ffmpeg.org](https://ffmpeg.org/download.html) 下载并加入 `PATH`

## 安装体积

后端依赖约 **1.5 GB**，主要来自 TensorFlow + Spotify Basic Pitch 模型权重。第一次音频转写时模型懒加载约 30 秒，之后会很快。

如果只需要 MIDI 搜索功能，可以不安装 `basic-pitch` 和 `yt-dlp`：音频接口会优雅返回错误，其他功能不受影响。

## 适用范围与免责声明

- **钢琴独奏（cover）转写效果最好。** 完整混音（人声 + 鼓 + 贝斯）出来的 MIDI 噪声较多，建议在「轨道配置」页中删除大多数伴奏轨。
- **仅供个人使用。** 本工具会从 YouTube、Bilibili、QQ 音乐等第三方平台下载内容，请勿部署为公共服务。
- **QQ 音乐为尽力支持。** 大多数歌曲付费或区域限制，封装库可能因接口变化失效。YouTube 和 Bilibili 最稳定。

## 架构

- `backend/mapper/` — 单音符到原琴 21 键的映射（局部就近偏移，禁止整体移调）。
- `backend/arranger/` — 三版琴谱合并（柱式和弦精简、4 键同时按键冲突解决、按版本规则合并）。
- `backend/parser/` — MIDI 解析、轨道分类、和弦分组。
- `backend/search/` — 四平台搜索器 + 异步聚合。
- `backend/formatter/` — 节奏感知的网格化琴谱（PC / 手机 / 人类阅读三种视图）。
- `backend/audio/` — 音频源（YouTube / Bilibili / QQ 音乐）+ Basic Pitch 转写器 + 任务编排。
- `backend/api/` — FastAPI 路由：`/api/search`、`/api/parse`、`/api/upload`、`/api/generate`、`/api/preview-track`、`/api/audio/*`。
- `backend/utils/` — 异步下载 + URL 哈希缓存。
- `frontend/src/pages/` — Search → Results → TrackConfig → Score 完整流程。

详细设计见 `docs/superpowers/specs/`，逐任务实施计划见 `docs/superpowers/plans/`，原始需求见 `requirements/genshin-lyre-requirements.md`。

## 运行环境

- Python 3.11+（已在 3.12 上构建并测试）
- Node 18+（已在 20 上构建）
- ffmpeg 4+（已在 7.x 上测试）
