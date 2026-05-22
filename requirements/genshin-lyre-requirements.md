# 原神原琴 AI 自动编谱系统 — 需求与开发文档

**版本：** v2.0
**技术栈：** Python 后端（FastAPI）+ React 前端
**文档用途：** 供 Claude Code 阅读后独立编写完整可运行代码，文档中不含具体实现代码，仅描述行为、规则、接口契约与约束

---

## 目录

1. 项目概述与核心约束
2. 系统架构
3. 目录结构
4. 环境与依赖
5. 核心数据模型
6. 原琴键位系统（硬性规则）
7. 三版琴谱生成规则（核心设计）
8. 后端各模块行为规范
9. 前端各页面与组件规范
10. API 接口契约
11. 错误处理规范
12. 单元测试用例（文字描述）
13. 开发顺序建议

---

## 1. 项目概述与核心约束

### 1.1 功能流程

用户输入曲名 → 系统并发从四个平台搜索 MIDI 资源 → 用户从结果列表选择一个版本 → 系统下载并解析该 MIDI 文件，提取所有轨道信息 → 用户在轨道面板中确认主旋律轨道并勾选伴奏轨道（系统自动推荐，用户可调整）→ 系统同时生成三版原琴谱 → 前端以 Tab 形式展示三版，每版均提供 PC 字母谱与手机数字谱，支持复制和下载。

### 1.2 三版琴谱定义

系统对同一首曲目**同时生成以下三个版本**，用户可在结果页自由切换：

| 版本 | 名称 | 内容构成 | 适用场景 |
|------|------|---------|---------|
| 版本一 | 纯旋律版 | 仅主旋律轨道 | 单手入门，快速上手 |
| 版本二 | 简化伴奏版 | 主旋律 + 经过精简的伴奏 | 单人演奏，兼顾完整度与可行性 |
| 版本三 | 完整伴奏版 | 主旋律 + 全部伴奏音符 | 参考原曲或双人合奏 |

### 1.3 核心约束（所有模块、所有版本必须严格遵守）

**约束 A：原琴音域**
原琴共 21 个键位，音域为 C3 到 B5，每个八度仅含 7 个自然音（C D E F G A B），不含任何半音（无黑键）。

**约束 B：超界音符处理——局部就近偏移，禁止整体移调**
当某个音符超出原琴音域时，仅对该单个音符做八度偏移：低于 C3 则升高一个八度，高于 B5 则降低一个八度。此操作只影响当前音符，绝对不允许根据全曲音域统计对整首乐曲做整体移调或整体八度平移。此规则对主旋律和伴奏音符同等适用。

**约束 C：半音圆整**
遇到原琴不存在的半音（如 F#、Bb），将该音符就近圆整到相邻自然音。距离相同时（如 F# 距 F 和 G 均为 1 个半音），优先圆整到下方自然音（F# → F）。半音圆整只作用于单个音符，不影响其他音符。此规则对主旋律和伴奏音符同等适用。

**约束 D：旋律优先（仅版本二适用）**
版本二中，当同一时刻主旋律音符与伴奏音符的总数超过 4 键时，优先保留全部主旋律音符，削减伴奏音符至满足上限。主旋律永远不被裁剪。

---

## 2. 系统架构

整体为前后端分离架构：

- **前端**：React SPA，运行在 `localhost:5173`（开发）
- **后端**：FastAPI，运行在 `localhost:8000`，提供 RESTful API
- **通信**：前端通过 Axios 调用后端 HTTP 接口
- **文件存储**：MIDI 文件下载到服务器本地临时目录 `/tmp/genshin_lyre/`，无需数据库

后端内部分为五个主要功能层：

1. **搜索层**：并发调用四个平台，聚合去重
2. **解析层**：MIDI 文件解析、轨道分类（旋律 / 伴奏）与信息提取
3. **映射层**：音符映射（半音圆整 + 超界偏移 + 键位查表），主旋律和伴奏轨道统一处理
4. **合并层**：将主旋律与伴奏按三版规则合并，处理同一时刻的音符冲突
5. **格式化层**：生成 PC 字母谱与手机数字谱文本

---

## 3. 目录结构

```
genshin-lyre/
├── backend/
│   ├── main.py                  # FastAPI 应用入口，注册所有路由
│   ├── requirements.txt
│   ├── config.py                # 全局配置与所有 Pydantic 数据模型
│   ├── search/
│   │   ├── __init__.py
│   │   ├── base.py              # 抽象基类 BaseMusicSearcher
│   │   ├── freemidi.py          # freemidi.org 搜索器
│   │   ├── bitmidi.py           # bitmidi.com 搜索器
│   │   ├── musescore.py         # musescore.com 搜索器
│   │   ├── bilibili.py          # bilibili.com 搜索器
│   │   └── aggregator.py        # 并发聚合、去重、排序
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── midi_parser.py       # MIDI 文件下载与解析，提取所有轨道音符
│   │   └── track_classifier.py  # 轨道分类：识别主旋律轨、伴奏轨、低音轨等
│   ├── mapper/
│   │   ├── __init__.py
│   │   ├── constants.py         # 原琴键位常量（MIDI 编号映射表）
│   │   └── note_mapper.py       # 核心映射引擎（半音圆整 + 超界偏移 + 键位查表）
│   ├── arranger/
│   │   ├── __init__.py
│   │   ├── chord_reducer.py     # 和弦精简：从柱式和弦中提取 2~3 个优先音
│   │   ├── merger.py            # 三版合并引擎：将主旋律与伴奏按版本规则合并
│   │   └── conflict_resolver.py # 同一时刻超过 4 键时的冲突解决（版本二专用）
│   ├── formatter/
│   │   ├── __init__.py
│   │   └── score_formatter.py   # 将合并后的 MappedNote 列表转为可读琴谱文本
│   └── utils/
│       ├── __init__.py
│       ├── downloader.py        # 异步文件下载（带超时、大小限制）
│       └── cache.py             # 基于 URL 哈希的本地文件缓存
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx              # 路由配置
│       ├── api/
│       │   └── client.js        # Axios 实例封装
│       ├── pages/
│       │   ├── SearchPage.jsx
│       │   ├── ResultsPage.jsx
│       │   ├── TrackConfigPage.jsx  # 轨道配置页（选主旋律 + 勾选伴奏）
│       │   └── ScorePage.jsx        # 三版琴谱展示页
│       ├── components/
│       │   ├── SearchBar.jsx
│       │   ├── ResourceCard.jsx
│       │   ├── TrackPanel.jsx       # 轨道列表面板（主旋律选择 + 伴奏勾选）
│       │   ├── ScoreDisplay.jsx     # 单版琴谱展示组件
│       │   ├── VersionTabs.jsx      # 三版切换 Tab
│       │   └── LoadingSpinner.jsx
│       └── styles/
│           └── global.css
└── README.md
```

---

## 4. 环境与依赖

### 4.1 后端 `requirements.txt` 需包含

| 包名 | 用途 |
|------|------|
| `fastapi` | Web 框架 |
| `uvicorn[standard]` | ASGI 服务器 |
| `httpx` | 异步 HTTP 客户端（搜索与下载） |
| `beautifulsoup4` | HTML 页面解析 |
| `lxml` | BeautifulSoup 的高性能解析器后端 |
| `music21` | MIDI 深度解析（音符、调式、BPM、和弦识别） |
| `mido` | MIDI 轻量解析（music21 失败时的降级备用） |
| `python-multipart` | 支持文件上传（multipart/form-data） |
| `aiofiles` | 异步文件读写 |
| `pydantic` | 数据模型与请求校验 |

### 4.2 前端 `package.json` 需包含

| 包名 | 用途 |
|------|------|
| `react` / `react-dom` | UI 框架 |
| `react-router-dom` | 页面路由 |
| `axios` | HTTP 请求 |
| `tailwindcss` | 样式 |
| `vite` + `@vitejs/plugin-react` | 构建工具 |

### 4.3 启动方式

后端：在 `backend/` 目录下执行 `uvicorn main:app --reload --port 8000`

前端：在 `frontend/` 目录下执行 `npm run dev`，默认访问 `http://localhost:5173`

---

## 5. 核心数据模型

以下所有模型定义在 `backend/config.py`，使用 Pydantic BaseModel，整个后端共用。

### MusicSource（枚举）
值为字符串：`freemidi`、`bitmidi`、`musescore`、`bilibili`。

### TrackRole（枚举）
表示轨道在编谱中承担的角色，值为字符串：`melody`（主旋律）、`accompaniment`（伴奏）、`bass`（低音）、`ignored`（忽略，如打击乐）。

### ScoreVersion（枚举）
值为字符串：`melody_only`（纯旋律版）、`simplified`（简化伴奏版）、`full`（完整伴奏版）。

### SearchResult

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 唯一标识，格式：`{source}_{内容哈希}` |
| `title` | str | 曲目标题 |
| `source` | MusicSource | 来源平台 |
| `source_url` | str | 资源页面原始 URL |
| `download_url` | str 或 None | 直接下载链接，无法提供时为 None |
| `duration_seconds` | int 或 None | 时长（秒） |
| `file_size_kb` | int 或 None | 文件大小（KB） |
| `track_count` | int 或 None | MIDI 轨道总数 |
| `preview_keys` | str 或 None | 前 8 个主旋律音符的 PC 键位预览 |
| `score` | float | 相关度评分 0.0~1.0 |

### TrackInfo
解析后每条轨道的信息，用于前端展示和用户配置：

| 字段 | 类型 | 说明 |
|------|------|------|
| `index` | int | 轨道索引 |
| `name` | str | 轨道名称（来自 MIDI meta，无则显示"轨道 N"） |
| `note_count` | int | 音符数量 |
| `pitch_range` | str | 音高范围，如"C4~E5" |
| `preview_keys` | str | 前 8 个音符映射后的 PC 键位 |
| `suggested_role` | TrackRole | 系统推荐的轨道角色 |
| `chord_type` | str | 伴奏类型：`chordal`（柱式和弦）、`arpeggiated`（分解和弦）、`mixed`（混合）、`none`（非伴奏） |

### ParsedNote

| 字段 | 类型 | 说明 |
|------|------|------|
| `midi_num` | int | 原始 MIDI 音符编号（0~127） |
| `start_tick` | int | 开始时间（tick） |
| `duration_tick` | int | 时值（tick） |
| `velocity` | int | 力度（0~127） |
| `track_index` | int | 所属轨道索引 |
| `track_role` | TrackRole | 该音符所属轨道的角色 |

### MappedNote
经过原琴映射后的单个音符：

| 字段 | 类型 | 说明 |
|------|------|------|
| `original_midi` | int | 原始 MIDI 编号（未经任何处理） |
| `mapped_midi` | int | 映射后的合法原琴 MIDI 编号 |
| `key_pc` | str | PC 端键位字母（如 A、Q、Z） |
| `key_mobile` | str | 手机端数字谱（如 1、+3、-2） |
| `start_tick` | int | 开始时间 |
| `duration_tick` | int | 时值 |
| `track_role` | TrackRole | 该音符的轨道角色（旋律 / 伴奏） |
| `is_out_of_range` | bool | 是否经过超界八度偏移 |
| `is_semitone_adjusted` | bool | 是否经过半音圆整 |
| `is_chord_reduced` | bool | 是否为从柱式和弦中被精简掉的音符（版本二中被丢弃的音） |

### VersionScore
单个版本的完整琴谱：

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | ScoreVersion | 版本标识 |
| `version_label` | str | 版本显示名称（如"简化伴奏版"） |
| `pc_score` | str | PC 字母谱完整文本 |
| `mobile_score` | str | 手机数字谱完整文本 |
| `notes` | List[MappedNote] | 该版本全部音符（含角色标注） |
| `statistics` | VersionStats | 统计信息 |

### VersionStats

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_notes` | int | 总音符数 |
| `melody_notes` | int | 主旋律音符数 |
| `accompaniment_notes` | int | 伴奏音符数 |
| `out_of_range_count` | int | 经过超界偏移的音符数 |
| `semitone_count` | int | 经过半音圆整的音符数 |
| `chord_reduced_count` | int | 版本二中被精简的和弦音符数 |
| `max_simultaneous_keys` | int | 该版本中同一时刻最多同时按键数 |

### LyreScore
最终生成结果，包含三个版本：

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | str | 曲目名称 |
| `bpm` | int | 速度 |
| `ticks_per_beat` | int | tick 分辨率 |
| `versions` | List[VersionScore] | 三个版本，顺序为 melody_only、simplified、full |

---

## 6. 原琴键位系统（硬性规则）

定义在 `backend/mapper/constants.py`，**所有模块只能引用，不得修改**。

### 6.1 键位对照表

**低音行（键盘 Z X C V B N M）**

| MIDI 编号 | 音名 | PC 键位 | 手机数字 |
|-----------|------|---------|---------|
| 48 | C3 | Z | -1 |
| 50 | D3 | X | -2 |
| 52 | E3 | C | -3 |
| 53 | F3 | V | -4 |
| 55 | G3 | B | -5 |
| 57 | A3 | N | -6 |
| 59 | B3 | M | -7 |

**中音行（键盘 A S D F G H J）**

| MIDI 编号 | 音名 | PC 键位 | 手机数字 |
|-----------|------|---------|---------|
| 60 | C4 | A | 1 |
| 62 | D4 | S | 2 |
| 64 | E4 | D | 3 |
| 65 | F4 | F | 4 |
| 67 | G4 | G | 5 |
| 69 | A4 | H | 6 |
| 71 | B4 | J | 7 |

**高音行（键盘 Q W E R T Y U）**

| MIDI 编号 | 音名 | PC 键位 | 手机数字 |
|-----------|------|---------|---------|
| 72 | C5 | Q | +1 |
| 74 | D5 | W | +2 |
| 76 | E5 | E | +3 |
| 77 | F5 | R | +4 |
| 79 | G5 | T | +5 |
| 81 | A5 | Y | +6 |
| 83 | B5 | U | +7 |

### 6.2 关键常量

- 音域下界：MIDI 48（C3）
- 音域上界：MIDI 83（B5）
- 每个八度内的自然音半音偏移集合：{0, 2, 4, 5, 7, 9, 11}（对应 C D E F G A B）
- 合法 MIDI 编号集合（共 21 个）：上表中所有 MIDI 编号
- 版本二同一时刻总按键上限：4 键

---

## 7. 三版琴谱生成规则（核心设计）

本章是整个项目最重要的业务规则，所有版本的差异完全由本章定义。

### 7.1 共同前置处理（所有版本均执行）

在进入各版本独立处理逻辑之前，所有被选中轨道的音符均需完成以下统一处理：

1. **音符提取**：从所有用户标记为 `melody` 或 `accompaniment` 的轨道中提取全部 ParsedNote，保留 `track_role` 标注
2. **音符映射**：对所有音符统一执行半音圆整和超界偏移，生成 MappedNote 列表
3. **时间对齐**：以 tick 为单位记录每个音符的起始时刻，作为后续冲突检测的基准

### 7.2 版本一：纯旋律版（`melody_only`）

**规则**：仅保留 `track_role == melody` 的 MappedNote，丢弃所有伴奏音符。

**没有冲突处理**：由于只有主旋律，不存在多轨叠加问题。

**输出**：对保留的音符列表直接执行格式化。

### 7.3 版本二：简化伴奏版（`simplified`）

这是规则最复杂的版本，处理流程分为三步。

**步骤一：伴奏音符预处理（和弦精简与分解和弦识别）**

对每个伴奏轨道，先对音符按起始时刻分组（同一时刻或时差 ≤ 30 tick 视为同一时刻）：

- **判断是否为柱式和弦**：若同一时刻组内音符数量 ≥ 2，且各音符时值相近（最长与最短时值之比 ≤ 2），则视为柱式和弦
- **判断是否为分解和弦**：若相邻音符的起始时刻间距均匀（误差 ≤ 20%）且音符时值短（≤ 半拍），则视为分解和弦模式

柱式和弦的精简规则（按优先级排序保留）：
1. 最低音（根音，通常是和弦定调音）
2. 距根音最近的五度音（根音 MIDI + 7，若不在合法集合则取最近合法音）
3. 若仍未到 2 个音，补充三度音（根音 MIDI + 4 或 +3，取合法值）
4. 精简后最多保留 3 个伴奏音（含根音、五音、三音），超出则按以上优先级从后删除

分解和弦的处理规则：
- 分解和弦中的所有音符**全部保留**，不做删减

**步骤二：主旋律与伴奏合并**

将版本一的主旋律音符列表与步骤一处理后的伴奏音符列表合并，按 `start_tick` 升序排列，生成统一时间轴上的音符序列。

**步骤三：同时按键数冲突解决**

对合并后的音符列表，逐一检查每个时刻（以每个音符的 `start_tick` 为基准）同时处于发声状态的音符总数：

- 统计某一时刻所有 `start_tick ≤ 当前时刻 < start_tick + duration_tick` 的音符
- 若总数 ≤ 4：保留全部，无需处理
- 若总数 > 4：**主旋律音符优先保留（全部保留），从伴奏音符中按以下优先级删除直至总数 ≤ 4**：
  1. 先删除三度音（优先级最低的和弦音）
  2. 再删除五度音
  3. 最后保留根音（根音是伴奏中最后被删除的）
  4. 若删到只剩根音仍超过 4 键（说明旋律本身在该时刻就有 4 个音），则根音也删除

被删除的伴奏音符在 MappedNote 中将 `is_chord_reduced` 标记为 True，并从该版本的最终输出列表中移除（不出现在琴谱文本中，但保留在 notes 列表中供前端统计展示）。

### 7.4 版本三：完整伴奏版（`full`）

**规则**：将主旋律全部音符与伴奏全部音符（经过统一映射，但不做任何精简或删除）合并，按时间轴排列。

**没有同时按键数限制**：不执行冲突解决，允许某些时刻超过 4 键，适合参考学习或双人合奏。

**分解和弦**：全部保留。

**柱式和弦**：全部音符保留，不做精简。

**输出**：对合并后的完整音符列表直接执行格式化。

---

## 8. 后端各模块行为规范

### 8.1 搜索模块

#### 8.1.1 抽象基类 `search/base.py`

定义 `BaseMusicSearcher` 抽象类，要求实现两个方法：

**`search(query, limit)`**：并发安全，任何内部异常必须在方法内捕获，失败时返回空列表，不向上抛出。

**`get_download_url(result)`**：获取实际下载 URL，失败时抛出 `ValueError`。

#### 8.1.2 freemidi.org 搜索器 `search/freemidi.py`

- 搜索 URL：`https://freemidi.org/search-{query}`，空格替换为连字符
- 解析目标：HTML 中包含曲目标题和 download ID 的元素
- 下载链接构造：`https://freemidi.org/download2-{id}`
- 请求携带浏览器 User-Agent，连续请求间隔 ≥ 0.5 秒，超时 10 秒

#### 8.1.3 bitmidi.com 搜索器 `search/bitmidi.py`

- 优先尝试 JSON API：`https://bitmidi.com/search?q={query}`
- JSON API 不可用时降级解析 HTML
- 下载链接规则：`https://bitmidi.com/uploads/{slug}.mid`
- 文件大小字段（字节）转换为 KB 填入 `file_size_kb`

#### 8.1.4 musescore.com 搜索器 `search/musescore.py`

- 仅做资源发现，`download_url` 设为 None
- 搜索 URL：`https://musescore.com/sheetmusic?text={query}&instrument=piano`
- 优先解析 JSON-LD 结构化数据
- `preview_keys` 字段填写"请前往 MuseScore 手动下载 MIDI"

#### 8.1.5 bilibili.com 搜索器 `search/bilibili.py`

- 搜索关键词拼接：`"{query} 原神 原琴 MIDI"`
- 使用 B 站 Web 搜索 API，Headers 必须含 `Referer: https://www.bilibili.com`
- `source_url` 填写 `https://www.bilibili.com/video/{bvid}`
- 从视频简介中用正则提取 `download_url`，匹配 pan.baidu.com、github.com、以 .mid/.midi 结尾的 URL
- 无法提取时 `download_url` 设为 None

#### 8.1.6 聚合器 `search/aggregator.py`

- `asyncio.gather` 并发调用四个搜索器，`return_exceptions=True`
- 去重：标题相似度判定重复时保留 score 更高者
- 排序：有 `download_url` 的结果优先；同等情况按 score 降序
- 总返回上限 20 条

---

### 8.2 MIDI 解析模块

#### 8.2.1 解析器 `parser/midi_parser.py`

**下载行为：**
- 使用 httpx 异步下载到 `/tmp/genshin_lyre/{URL哈希}.mid`
- 文件超过 5MB 立即拒绝
- URL 哈希命中缓存则跳过下载

**解析行为：**
- 优先 music21，失败自动降级 mido
- 返回：BPM（默认 120）、ticks_per_beat、所有 TrackInfo 列表

**音符提取规则：**
- 过滤 velocity = 0 的 note_on
- 过滤时值 < 30 tick 的音符
- 音符时值 = 对应 note_off tick - note_on tick

#### 8.2.2 轨道分类器 `parser/track_classifier.py`

负责为每条轨道推荐 `TrackRole` 和判断 `chord_type`。

**轨道角色推荐规则（优先级从高到低）：**

1. **名称匹配**：轨道名含 `melody/vocal/主旋律/soprano/lead/right` → `melody`；含 `bass/left/低音` → `bass`；含 `drum/perc/打击` → `ignored`

2. **音高范围排除**：音符全部低于 MIDI 48 → `bass`；全部高于 MIDI 84 → `ignored`；音符数量 < 10 → `ignored`

3. **综合评分**：在剩余轨道中，评分最高的推荐为 `melody`，其余推荐为 `accompaniment`。评分维度：音符数量权重 0.4、音高集中在 MIDI 60~72 的比例权重 0.3、平均力度权重 0.3

**和弦类型判断规则：**

对每条角色为 `accompaniment` 的轨道，抽样检查若干时刻窗口（时差 ≤ 30 tick 视为同时）：
- 若同时发声的音符组占全部音符数 > 50%，且平均每组 ≥ 2 个音：`chordal`
- 若相邻音符间距均匀（分解特征）且极少出现同时发声：`arpeggiated`
- 两种特征都有：`mixed`
- 几乎全为单音：`none`

---

### 8.3 核心映射引擎 `mapper/note_mapper.py`

对所有音符（主旋律和伴奏）统一执行，**步骤顺序不可颠倒**。

**步骤一：半音圆整**

计算 `midi_num % 12`，若不在 `{0,2,4,5,7,9,11}` 中，则为半音：
- 计算与同八度内所有自然音的距离，取最近者
- 距离相同时取下方自然音（数值较小者）
- 重组 MIDI 编号（保持原八度），记录 `is_semitone_adjusted = True`

**步骤二：音域约束**

- MIDI 编号 < 48：加 12，记录 `is_out_of_range = True`
- MIDI 编号 > 83：减 12，记录 `is_out_of_range = True`

**步骤三：二次校验**

若结果仍不在 21 个合法编号中（极端边界情况），取合法集合中与当前值差距最小的编号。

**步骤四：键位查表**

从常量表中查出 `key_pc` 和 `key_mobile`。

**批量映射**：每个音符独立处理，严格禁止任何音符的处理结果影响其他音符。

---

### 8.4 编曲合并模块 `arranger/`

#### 8.4.1 和弦精简器 `arranger/chord_reducer.py`

仅用于版本二的伴奏预处理。

**柱式和弦精简逻辑：**

输入：同一时刻的一组伴奏 MappedNote（已完成映射）

输出：保留其中 ≤ 3 个音符，其余标记 `is_chord_reduced = True`

保留优先级：
1. 保留 `mapped_midi` 值最小的音符（根音/最低音）
2. 在剩余音符中，找距根音最近的纯五度音（+7 半音，若无则取最接近的合法音）
3. 若仍有音符且数量不足 3 个，再加入三度音（大三度 +4 或小三度 +3，取其中存在的合法音）
4. 其余音符全部标记 `is_chord_reduced = True`

**分解和弦判断**：`chord_type == arpeggiated` 的轨道，所有音符不经过精简，`is_chord_reduced` 全为 False。

`chord_type == mixed` 的轨道：对其中判断为柱式和弦的音符组执行精简，判断为分解和弦的片段保留全部。

#### 8.4.2 合并引擎 `arranger/merger.py`

职责：将主旋律 MappedNote 列表与伴奏 MappedNote 列表，按三版规则合并为一个统一列表。

版本一：直接返回主旋律列表，不调用其他 arranger 子模块。

版本二：
1. 调用 `chord_reducer.py` 对伴奏列表预处理
2. 合并两个列表，按 `start_tick` 升序排列
3. 将合并后列表传入 `conflict_resolver.py` 处理冲突
4. 返回最终列表（`is_chord_reduced = True` 的音符排除在琴谱文本之外，但保留在 notes 列表供统计）

版本三：直接合并两个列表，按 `start_tick` 升序排列，不经过任何精简或冲突处理。

#### 8.4.3 冲突解决器 `arranger/conflict_resolver.py`

仅被版本二调用。

**同时按键数检测逻辑：**

以每个音符的 `start_tick` 为检测时刻，统计该时刻所有满足 `start_tick ≤ 当前时刻 < start_tick + duration_tick` 的音符（即正在发声的音符）总数。

若总数 > 4，执行伴奏裁减（主旋律不参与裁减）：
1. 识别当前发声音符中 `track_role == accompaniment` 的音符
2. 优先标记三度音（非根音、非五度音）为 `is_chord_reduced = True`
3. 仍超 4 键则标记五度音
4. 仍超则标记根音
5. 裁减后若主旋律本身已 ≥ 4 个音（极少数情况），允许该时刻超过 4 键（主旋律绝不裁减）

裁减判断依赖和弦音色角色（根音/五音/三音）的标注，此信息由 `chord_reducer.py` 在精简时写入音符的扩展字段 `chord_position`（值为 `root`、`fifth`、`third`、`other`）。

---

### 8.5 格式化输出模块 `formatter/score_formatter.py`

接收某一版本的 MappedNote 列表（已排除 `is_chord_reduced = True` 的音符）、`ticks_per_beat`、`bpm`，输出 PC 字母谱和手机数字谱两种文本。

**PC 字母谱格式规则：**
- 音符之间用空格分隔
- 两相邻音符间隔 > 1 拍，插入 ` - ` 表示停顿
- 起始时刻差 ≤ 30 tick 的音符视为和弦，用括号括起，如 `(GH)` 或 `(AFQ)`
- 每 16 个音符（或到达小节线）换行
- 超界偏移音符（`is_out_of_range = True`）用方括号标注：`[Q]`
- 伴奏音符与旋律音符在纯文本中不做区分，外观一致（区分由前端颜色渲染负责）

**手机数字谱格式规则：**
- 逻辑与 PC 谱完全相同，键位替换为数字格式（`+3`、`5`、`-2`）
- 超界偏移音符同样方括号标注：`[+3]`

---

### 8.6 FastAPI 路由配置 `backend/main.py`

- 启用 CORS，开发阶段允许 `http://localhost:5173`
- 所有路由以 `/api` 为前缀
- 启动时自动创建 `/tmp/genshin_lyre/`
- 全局异常处理器返回统一格式的 500 响应

---

## 9. 前端各页面与组件规范

### 9.1 路由配置

| 路径 | 页面组件 | 说明 |
|------|---------|------|
| `/` | SearchPage | 搜索首页 |
| `/results` | ResultsPage | 搜索结果页（router state 接收数据） |
| `/tracks` | TrackConfigPage | 轨道配置页（选主旋律 + 勾选伴奏） |
| `/score` | ScorePage | 三版琴谱展示页（router state 接收数据） |

### 9.2 SearchPage

**UI 元素：**
- 应用标题："原神原琴 AI 编谱"
- 搜索输入框，placeholder："请输入曲名，如：小星星、Canon in D"
- 搜索按钮
- 搜索历史（localStorage，最近 10 条，点击可复用）

**交互行为：**
- 点击搜索或 Enter 触发 `GET /api/search`
- 加载中显示 LoadingSpinner，文案："正在同时搜索 FreeMIDI、BitMIDI、MuseScore、B站…"
- 成功后跳转 ResultsPage，router state 传递结果列表和搜索词
- 结果为空时原页面提示，建议尝试英文曲名或上传本地文件

### 9.3 ResultsPage

**UI 元素：**
- 搜索词回显 + 结果总数
- 来源筛选 Tab：全部 / FreeMIDI / BitMIDI / MuseScore / B站
- ResourceCard 列表
- 底部固定"上传本地 MIDI 文件"入口（accept=".mid,.midi"）

**ResourceCard 展示内容：**
- 曲目标题（超 40 字截断）
- 来源平台名称
- 时长 / 文件大小 / 键位预览
- 操作按钮：有 `download_url` 则"选择此版本"，无则"前往下载"（外链）

**交互行为：**
- 点击"选择此版本" → 调用 `POST /api/parse`，成功后跳转 TrackConfigPage
- 上传本地文件 → 调用 `POST /api/upload`，成功后跳转 TrackConfigPage

### 9.4 TrackConfigPage（关键新增页面）

此页面负责让用户确认轨道分配，是版本一/二/三差异的起点。

**UI 布局：**
- 页面标题："配置轨道"，副标题：曲目名称 + BPM
- 轨道列表（TrackPanel 组件），每条轨道一行，包含：
  - 轨道名称、音符数、音高范围、键位预览
  - 角色选择控件：单选，选项为"主旋律 / 伴奏 / 低音 / 忽略"
  - 系统推荐角色默认选中，标注"推荐"徽标
  - `chord_type` 标注（仅对 `accompaniment` 轨道显示）：如"分解和弦"、"柱式和弦"
- 说明文字（页面顶部，灰色小字）："系统已自动识别轨道角色，您可根据实际情况调整。分解和弦伴奏将完整保留；柱式和弦在简化版中将自动精简为 2~3 个关键音。"
- 底部确认按钮："生成琴谱"

**交互行为：**
- 至少选择 1 条轨道为"主旋律"，否则"生成琴谱"按钮不可点击，显示提示"请至少指定一条主旋律轨道"
- 可选择 0 条伴奏轨道（此时三版均等同于版本一）
- 点击"生成琴谱" → 调用 `POST /api/generate`，传入 file_token 和用户配置的轨道角色
- 生成成功后跳转 ScorePage

### 9.5 ScorePage

**UI 布局：**
- 顶部：曲目名称、BPM
- 版本切换 Tab（VersionTabs 组件）：纯旋律版 / 简化伴奏版 / 完整伴奏版
- 每个版本内部再有次级 Tab：PC 字母谱 / 手机数字谱
- 琴谱文本区（ScoreDisplay 组件）：等宽字体，每行 16 音符
  - 超界偏移音符（`[Q]` 形式）：橙色高亮
  - 主旋律音符与伴奏音符：可用颜色区分（旋律默认色，伴奏稍暗）
- 统计信息栏（折叠区域，默认收起）：显示 VersionStats 内容
- 操作按钮："复制琴谱"、"下载为 .txt"、"重新搜索"、"重新配置轨道"（返回 TrackConfigPage）
- 页脚注："本琴谱仅供个人游戏娱乐使用"

**默认展示版本：** 进入页面默认显示简化伴奏版（版本二）。

### 9.6 API 客户端 `api/client.js`

- Axios 实例，`baseURL` 读取 `VITE_API_URL`，默认 `http://localhost:8000`
- 统一超时 30 秒
- 响应拦截器：4xx 显示 `message` 字段，5xx 及网络错误提示"服务暂时不可用"
- 导出函数：`searchMusic(query)`、`parseResource(data)`、`uploadMidi(file)`、`generateScore(data)`

---

## 10. API 接口契约

### `GET /api/search`

**请求参数（Query String）：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `q` | string | 是 | 搜索关键词 |
| `limit` | int | 否，默认 5 | 每个来源最多返回条数 |

**成功响应（200）：**
```json
{
  "query": "小星星",
  "total": 12,
  "results": [
    {
      "id": "freemidi_a3f2c1",
      "title": "Twinkle Twinkle Little Star",
      "source": "freemidi",
      "source_url": "https://freemidi.org/download-12345",
      "download_url": "https://freemidi.org/download2-12345",
      "duration_seconds": 45,
      "file_size_kb": 12,
      "track_count": 2,
      "preview_keys": "A S D F G H J A",
      "score": 0.95
    }
  ]
}
```

---

### `POST /api/parse`

下载并解析 MIDI，返回所有轨道信息（含系统推荐角色）。

**请求体（JSON）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `result_id` | string | 是 | 搜索结果 ID |
| `download_url` | string | 是 | MIDI 下载 URL |
| `title` | string | 是 | 曲目标题 |

**成功响应（200）：**
```json
{
  "file_token": "tmp_abc123",
  "title": "Twinkle Twinkle Little Star",
  "bpm": 120,
  "ticks_per_beat": 480,
  "tracks": [
    {
      "index": 0,
      "name": "Piano Right",
      "note_count": 156,
      "pitch_range": "C4~E5",
      "preview_keys": "A S D F G H J A",
      "suggested_role": "melody",
      "chord_type": "none"
    },
    {
      "index": 1,
      "name": "Piano Left",
      "note_count": 98,
      "pitch_range": "C3~G3",
      "preview_keys": "Z X C V B N M Z",
      "suggested_role": "accompaniment",
      "chord_type": "arpeggiated"
    },
    {
      "index": 2,
      "name": "Strings",
      "note_count": 64,
      "pitch_range": "C3~C4",
      "preview_keys": "Z A Z A Z A Z A",
      "suggested_role": "accompaniment",
      "chord_type": "chordal"
    }
  ]
}
```

---

### `POST /api/upload`

上传本地 MIDI 文件，响应格式与 `/api/parse` 完全一致。

**请求格式：** `multipart/form-data`，字段名 `file`

---

### `POST /api/generate`

根据用户配置的轨道角色，同时生成三版琴谱。

**请求体（JSON）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_token` | string | 是 | parse/upload 返回的文件标识 |
| `title` | string | 是 | 曲目标题 |
| `track_roles` | object | 是 | 键为轨道索引（字符串），值为 TrackRole 枚举值 |

`track_roles` 示例：`{"0": "melody", "1": "accompaniment", "2": "ignored"}`

**成功响应（200）：**
```json
{
  "title": "Twinkle Twinkle Little Star",
  "bpm": 120,
  "ticks_per_beat": 480,
  "versions": [
    {
      "version": "melody_only",
      "version_label": "纯旋律版",
      "pc_score": "A A G G H H G - F F D D S S A",
      "mobile_score": "1 1 5 5 6 6 5 - 4 4 3 3 2 2 1",
      "notes": [],
      "statistics": {
        "total_notes": 42,
        "melody_notes": 42,
        "accompaniment_notes": 0,
        "out_of_range_count": 0,
        "semitone_count": 0,
        "chord_reduced_count": 0,
        "max_simultaneous_keys": 1
      }
    },
    {
      "version": "simplified",
      "version_label": "简化伴奏版",
      "pc_score": "A A G G H H G - (AF) F (DS) D (AS) S A",
      "mobile_score": "1 1 5 5 6 6 5 - (14) 4 (25) 3 (12) 2 1",
      "notes": [],
      "statistics": {
        "total_notes": 89,
        "melody_notes": 42,
        "accompaniment_notes": 47,
        "out_of_range_count": 3,
        "semitone_count": 1,
        "chord_reduced_count": 12,
        "max_simultaneous_keys": 4
      }
    },
    {
      "version": "full",
      "version_label": "完整伴奏版",
      "pc_score": "A A G G H H G - (ADFQ) F (DGSW) D (AGHS) S A",
      "mobile_score": "1 1 5 5 6 6 5 - (1345) 4 (2356) 3 (1256) 2 1",
      "notes": [],
      "statistics": {
        "total_notes": 134,
        "melody_notes": 42,
        "accompaniment_notes": 92,
        "out_of_range_count": 5,
        "semitone_count": 3,
        "chord_reduced_count": 0,
        "max_simultaneous_keys": 7
      }
    }
  ]
}
```

注：`notes` 数组在实际响应中为完整 MappedNote 列表，此处省略以节省篇幅。

---

### 错误响应格式（所有接口统一）

```json
{
  "error": "错误码",
  "message": "面向用户的中文说明",
  "detail": "技术细节（可选）"
}
```

**错误码清单：**

| 错误码 | HTTP 状态码 | 含义 |
|--------|------------|------|
| `SEARCH_FAILED` | 500 | 所有搜索源均失败 |
| `DOWNLOAD_FAILED` | 400 | MIDI 文件下载失败 |
| `FILE_TOO_LARGE` | 400 | 文件超过 5MB |
| `PARSE_FAILED` | 400 | MIDI 解析失败 |
| `INVALID_FILE_TYPE` | 400 | 非 MIDI 文件 |
| `NO_MELODY_TRACK` | 400 | 未指定主旋律轨道 |
| `FILE_NOT_FOUND` | 404 | file_token 对应文件不存在或已过期 |
| `INVALID_TRACK_INDEX` | 400 | track_roles 中含无效轨道索引 |

---

## 11. 单元测试用例（文字描述）

测试文件位于 `backend/tests/`，使用 pytest。

### 11.1 映射引擎测试 `test_mapper.py`

**半音圆整：**
- 自然音（MIDI 60 C4）输入后，输出编号不变，`is_semitone_adjusted = False`
- F#4（MIDI 66）输入，输出应为 F4（MIDI 65），`is_semitone_adjusted = True`
- Bb4（MIDI 70）输入，输出应为 A4（MIDI 69），取下方音
- C#4（MIDI 61）输入，输出应为 C4（MIDI 60）

**超界偏移：**
- C2（MIDI 36）输入，输出应为 C3（MIDI 48），`is_out_of_range = True`
- B6（MIDI 95）输入，输出应为 B5（MIDI 83），`is_out_of_range = True`
- G4（MIDI 67）输入，输出不变，`is_out_of_range = False`

**独立处理验证（禁止全局移调）：**
- 构造含 5 个音符的列表（2 个超界、3 个正常）
- 批量映射后，3 个正常音符的 `mapped_midi` 与原值相同，2 个超界音符仅自身偏移
- 验证 5 个音符的处理结果完全独立

**键位完整性：**
- 21 个合法 MIDI 编号在 PC 映射表中均有对应值
- 21 个合法 MIDI 编号在手机映射表中均有对应值

### 11.2 和弦精简测试 `test_chord_reducer.py`

- 输入 C 大三和弦（C4、E4、G4 同时），精简后应保留 C4（根音）和 G4（五音），E4 可选
- 输入 4 音和弦（C4、E4、G4、B4），精简后保留 C4、G4，其余标记 `is_chord_reduced = True`
- 输入分解和弦轨道（`chord_type = arpeggiated`），所有音符的 `is_chord_reduced` 均为 False

### 11.3 冲突解决测试 `test_conflict_resolver.py`

- 构造某时刻有 3 个旋律音 + 3 个伴奏音（总 6 键）的场景，解决后伴奏中三度音优先被删除，总按键数 ≤ 4
- 构造某时刻有 4 个旋律音 + 2 个伴奏音（总 6 键）的场景，旋律 4 个全部保留，伴奏全部被删除，总按键数为 4
- 构造某时刻有 5 个旋律音（主旋律自身已超 4 键）的极端场景，所有旋律音全部保留，不裁减

### 11.4 版本生成测试 `test_merger.py`

- 版本一输出不含任何 `track_role == accompaniment` 的音符
- 版本二输出中 `max_simultaneous_keys ≤ 4`（主旋律 ≥ 4 键的极端时刻除外）
- 版本三输出的 `total_notes = melody_notes + accompaniment_notes`，无任何音符被删除

### 11.5 搜索模块测试 `test_search.py`

- 聚合器在所有搜索源均抛出异常时，返回空列表而不是异常
- 搜索"canon"时，至少返回 1 条有效结果（集成测试，需要网络）

---

## 12. 开发顺序建议

**阶段一：核心映射引擎（不依赖网络，优先验证）**

实现 `mapper/constants.py` 和 `mapper/note_mapper.py`，运行 `test_mapper.py` 全部通过后再继续。这是最基础的正确性保证。

**阶段二：编曲合并逻辑**

实现 `arranger/chord_reducer.py`、`arranger/conflict_resolver.py`、`arranger/merger.py`，运行对应测试。可用硬编码的 MappedNote 列表进行测试，不依赖真实 MIDI 文件。

**阶段三：MIDI 处理管线**

实现 `parser/midi_parser.py`（先支持本地文件，暂不实现网络下载）和 `parser/track_classifier.py`，实现 `formatter/score_formatter.py`。用一个真实 MIDI 文件手动验证"解析 → 分类 → 映射 → 合并（三版）→ 格式化"完整流程。

**阶段四：搜索与下载**

依次实现四个搜索器，再实现聚合器，最后补充 `utils/downloader.py` 和 `utils/cache.py`，让 midi_parser.py 支持从 URL 下载。

**阶段五：后端 API**

实现 `main.py`，组装所有路由，用 curl 或 Postman 手工验证各接口（包括 /api/parse 返回轨道信息、/api/generate 返回三版琴谱）。

**阶段六：前端**

先用 Mock 数据实现 SearchPage → ResultsPage → TrackConfigPage → ScorePage 的完整页面结构，确认交互流程后替换为真实 API 调用，重点验证：
- TrackConfigPage 的轨道角色修改是否正确传入 /api/generate
- ScorePage 的三版 Tab 切换是否正常
- 超界音符的橙色高亮是否正确渲染

**阶段七：收尾**

完善错误处理，补充注释，更新 README（含环境配置和启动步骤），进行完整端到端测试。

---

*文档结束。版本 v2.0 相对 v1.0 的主要变更：新增三版琴谱设计（第 7 章）、新增 arranger/ 模块（chord_reducer、merger、conflict_resolver）、TrackConfigPage 页面、更新所有数据模型（含 TrackRole、ScoreVersion、VersionScore 等）、更新 /api/parse 响应含轨道角色推荐、更新 /api/generate 请求和响应以支持三版输出。*
