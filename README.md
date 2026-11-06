[README.md](https://github.com/user-attachments/files/34462286/README.md)
<div align="center">

# KeyMarquee

**A lightweight Windows keystroke & mouse marquee overlay — with a live FIFO history strip, press counting and TOP-15 statistics.**

**轻量级 Windows 键鼠操作跑马灯：实时悬浮显示 · 10 槽 FIFO 历史条 · 按键计数与 TOP15 统计**

[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)](#)
[![Python](https://img.shields.io/badge/python-3.10%2B-green)](#)
[![GUI](https://img.shields.io/badge/GUI-PyQt6-41cd52)](#)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)

*Formerly known as KeyCast (internal name).*

</div>

---

## What is KeyMarquee?

KeyMarquee overlays a compact, always-on-top "marquee strip" on your screen that
shows what you are typing and clicking — in real time, and the way you want it:

- a live **10-slot FIFO history strip** (newest at the bottom, oldest pushed out at the top),
- an optional **press counter** with TOP-15 and full-key statistics,
- a tray-resident, zero-noise design: nothing runs unless you need it.

Built for demos, screen recordings, training material and factory-floor
operation reviews.

**KeyMarquee 是什么？** KeyMarquee 在屏幕上常驻一条紧凑的置顶“跑马灯”条，实时显示
你正在按下的按键与鼠标操作——并按你定义的方式显示：10 槽 FIFO 历史条（最新在底部、
最旧从顶部挤出）、可选的按键计数统计（TOP15 + 全部按键 + 占比柱状图）。
适合软件演示、录屏教程、培训材料与产线操作复盘。

> 截图占位：`docs/screenshot-overlay.png`（悬浮条）、`docs/screenshot-stats.png`（统计页）

---

## Features / 功能

| | Feature | 说明 |
|---|---------|------|
| 🎞️ | **FIFO history strip** | 10 fixed slots, newest enters at the bottom (slot 10), oldest exits at the top (slot 1). Expired slots fade out in place — positions never jump. / 10 个固定槽位，新内容从第 10 格进入、最旧从第 1 格挤出；过期槽就地淡出，位置永不跳动 |
| ⏱️ | **Long-press aware** | Holding a key counts as a new press every 500 ms (configurable) — the strip shows "still holding" without flooding. Windows auto-repeat is absorbed upstream. / 长按每 500ms 记一次新按压，Windows 自动重复在最上游吸收 |
| 🖱️ | **Mouse actions** | Left/right/middle clicks, side buttons, wheel up/down. / 左中右键、侧键、滚轮 |
| 🔢 | **Press counter** | Since app start: total presses, distinct keys, TOP-15 with share-of-total bars, and a full key table — all zero-IO, in-memory. / 自启动累计：总次数、按键种数、TOP15 占比条形图与全量表，纯内存零 IO |
| 🎨 | **16 fixed color presets** | Curated contrast-safe palettes (WCAG-checked), pick-and-go — no free-form color editing by design. / 16 组对比度实测过的固化配色，仅供选择不做自由编辑 |
| 🖥️ | **Settings dialog** | Font size, slot size, screen anchor, opacities — applied live, persisted. / 字号/槽尺寸/锚点/透明度，应用即生效并持久化 |
| 🫥 | **Click-through & drag** | Locked mode passes all input through; move mode drags the strip and remembers position per anchor. / 锁定态鼠标穿透，移动态拖拽定位并记忆 |
| 🪶 | **Lightweight** | Idle CPU ≈ 0% (heartbeat stops when idle), no background services, single-file portable exe. / 空闲 CPU≈0%，无后台服务，单文件绿色便携 |

### Statistics view / 统计页

The diagnostics window has two views: a live **recent-presses feed** and a
**statistics tab** (TOP-15 bar chart + full table with per-key share of total
input). Counting shares the same signal path as the overlay, so the strip and
the numbers always agree — including the 500 ms long-press rule.

诊断窗口含「最近按键」流水与「按键统计」两页：TOP15 柱状图、全量表、占比精确到
0.01%；计数与悬浮层同源同口径（含长按记次规则），两个视图数字永远一致。

---

## Install / 安装

### Portable exe (recommended / 推荐)

1. Download `KeyCast.exe` from
   [**Releases**](../../releases) (single file, no installer, no runtime needed);
2. Put it anywhere (e.g. `D:\Tools\KeyMarquee\`);
3. Double-click. A tray icon appears; the strip shows up bottom-right.

1. 从 [**Releases**](../../releases) 下载单文件 `KeyCast.exe`（免安装、免运行库）；
2. 放到任意目录（如 `D:\Tools\KeyMarquee\`）；
3. 双击运行——托盘出现图标，悬浮条显示在屏幕右下。

> ⚠️ Antivirus false positives are common for unsigned PyInstaller binaries.
> If Windows Defender / 360 / Huorong flags it, add an exclusion or build from
> source (see below). / 未签名的 PyInstaller 单文件常见杀软误报，加白名单或从源码构建即可。

### From source / 从源码运行

```bat
git clone https://github.com/<you>/keymarquee.git
cd keymarquee
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

Requirements: Windows 10/11, Python 3.10+, `PyQt6`, `pynput`.
Locked versions are listed in `requirements.lock.txt`.

依赖：Windows 10/11、Python 3.10+、`PyQt6`、`pynput`；锁定版本见 `requirements.lock.txt`。

### Build a single-file exe / 打包单文件 exe

```bat
.venv\Scripts\python -m PyInstaller --noconfirm --workpath build\work --distpath dist build.spec
```

Output: `dist\KeyCast.exe` (≈ 35 MB, includes icon & version info).

---

## Usage / 使用

| Action | How |
|--------|-----|
| Show strip | Runs automatically at startup, bottom-right anchor / 启动即显示，默认右下 |
| Move the strip | Tray → uncheck **锁定** (or double-click tray icon), then drag; position is remembered / 托盘取消锁定后拖拽，位置自动记忆 |
| Change look | Tray → **设置…** — 16 color presets, font size, slot size, anchor, opacities; applied live / 托盘「设置…」：16 配色、字号、槽尺寸、锚点、透明度，即时生效 |
| See statistics | Tray → **监听诊断** → 「按键统计」tab / 托盘「监听诊断」→ 统计页签 |
| Clear counters | Diagnostics window → **清空** / 诊断窗口「清空」 |
| Exit | Tray → **退出** / 托盘「退出」 |

### Configuration / 配置

All settings live in `config.json` next to the exe (portable — move the folder,
keep your settings). Every value is validated on load; unknown/old keys are
migrated automatically. All options are **preset-only** (no free-form editing):
16 curated color palettes, font sizes 12/18/22, slot sizes 100×42 / 80×40,
opacities 20–100%, anchors at 4 screen corners.

所有配置存于 exe 同目录的 `config.json`（便携式，挪目录不丢设置）。加载时全量校验，
旧版配置自动迁移。所有外观项均为**预设选择制**：16 组配色、字号 12/18/22、
槽尺寸 100×42/80×40、透明度 20–100%、四角锚点。

---

## Design notes / 设计取舍

This tool makes a few opinionated choices that differ from other keystroke
visualizers (Keyviz, KeyCastr):

- **Fixed 10-slot FIFO** instead of free-growing stacks — positions are stable,
  readable, and the "numbers 1–10 = oldest → newest" mapping never changes;
- **Preset-only styling** instead of a full theming engine — every combination is
  contrast-checked (WCAG) before shipping, so you cannot configure an invisible
  result;
- **Session-free, always-on** — no recording, no logging, no network. The counter
  is in-memory only and resets on restart.

与 Keyviz / KeyCastr 等工具不同的三个取舍：固定 10 槽 FIFO（位置稳定、序号即时间序）；
配色仅提供 16 组 WCAG 对比度实测过的预设（不会配出“看不见”的组合）；无会话无记录无网络
——计数纯内存，重启归零。

---

## Known limitations / 已知限制

- **Windows only** (Win32 APIs for hooks, foreground window, tray). / 仅支持 Windows。
- **Secure input sequences** (Ctrl+Alt+Del, Win+L, UAC prompts) are not visible to
  any user-mode hook — by OS design. / 系统安全序列（Ctrl+Alt+Del、Win+L、UAC）对
  用户态钩子不可见，属系统设计。
- **Chinese IME composition** is recorded as raw key sequence (pinyin), not the
  final committed characters — Windows does not expose those to hooks. /
  中文输入法的拼音过程可见，最终上屏汉字钩子拿不到（系统机制）。
- Some overlay-heavy scenarios (RDP sessions, exotic GPU drivers) may need the
  fallback render mode (`render_mode: solid` in config). / 远程桌面或特殊显卡驱动下
  可用保底渲染模式（config 中 `render_mode: solid`）。

---

## Project layout / 工程结构

```
keycast/
├── main.py        # assembly & lifecycle / 装配与生命周期
├── listener.py    # pynput hooks → Qt signals (500ms long-press rule) / 全局钩子→信号
├── formatter.py   # key naming, modifier split, wheel burst merge / 键名与合并
├── overlay.py     # 10-slot self-painted FIFO strip / 10 槽自绘悬浮条
├── keystats.py    # in-memory press counter / 内存计数器
├── statlist.py    # self-painted statistics list / 自绘统计列表
├── monitor.py     # diagnostics window (feed + stats + chart) / 诊断窗口
├── settings.py    # settings dialog / 设置窗口
├── tray.py        # tray icon & menu / 托盘
├── config.py      # config load/save/validate / 配置读写校验
└── build.spec     # PyInstaller single-file build / 打包规格
```

## Acknowledgements / 致谢与同类项目

- [Keyviz](https://github.com/mulaRahul/keyviz) — the most polished cross-platform
  keystroke visualizer; KeyMarquee took a different route (fixed FIFO strip,
  preset-only styling, Windows-first, zero-config counter). / 最精致的跨平台键鼠
  可视化工具；KeyMarquee 走了固定 FIFO 条 + 预设化配色 + Windows 优先的不同路线。
- [KeyCastr](https://github.com/keycastr/keycastr) — the classic macOS keystroke
  visualizer. / macOS 经典键击显示工具。

## License / 许可证

[MIT](LICENSE) for this project's code. Bundled third-party components keep
their own licenses — PyQt6 is **LGPL-3.0**; the PyInstaller single-file build is
provided for convenience, and the source tree allows rebuilding the app against
a system-installed PyQt6 (satisfying the user-replaceable-library requirement).
See [LICENSE](LICENSE) for details.

本项目代码以 [MIT](LICENSE) 发布。第三方组件沿用其自身许可证——PyQt6 为 **LGPL-3.0**；
随附的单文件 exe 仅为便利性提供，源码树允许用户以系统安装的 PyQt6 重新构建
（满足 LGPL“用户可替换动态库”的要求）。详见 [LICENSE](LICENSE)。

---

<div align="center">
<sub>Built with PyQt6 + pynput · Windows-first · made for factory floors and screen recordings</sub>
</div>
