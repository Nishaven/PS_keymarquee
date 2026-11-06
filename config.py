# -*- coding: utf-8 -*-
"""config.py — 配置持久化（config.json，与程序同目录，绿色便携）

v3 变更（对应 20261103-1212 补充方案）：
  · 配色由「12 色自由选」收敛为 16 组固化预设（PALETTES），字色/底色不再独立暴露
  · 透明度 6 档 20/40/60/75/90/100（去掉实测塌陷的 15/30/45）
  · 每个预设带 min_opacity：低于该档框会与桌面同明度，实测 WCAG < 4.5（赤2=75、橙2=90）
  · 字透明度 3 档 60/80/100（描边恒定 100%，字芯过淡只剩轮廓）
  · 新增 500ms 按压规则、10 固定槽位、4 帧淡出等运行参数

所有枚举在 load() 时做白名单校验，脏值/旧版配置一律回落到默认，不会崩。
"""
import json
import os
import sys

APP_VERSION = "0.1.0"

# ---------------------------------------------------------------- 配色预设
# (名称, 字色, 底色, 说明, 最低框透明度%)
# 名称与色值来自需求方给定；min_opacity 由 WCAG 实测反解（见 取证/palette_contrast.txt）
PALETTES = [
    ("暖白", "#222222", "#F7F3EA", "内容型、阅读型", 20),
    ("浅灰", "#181D26", "#F8F9FA", "B 端工具、专业产品", 20),
    ("石板", "#0F172A", "#F1F5F9", "数据、工程、科技感", 20),
    ("深色", "#FFFFFF", "#121212", "标准深色模式", 20),
    ("蓝", "#FFFFFF", "#1D4ED8", "主按钮、强调块", 20),
    ("紫", "#FFFFFF", "#4A154B", "品牌导航、强调区", 20),
    ("绿", "#FFFFFF", "#064E3B", "金融、健康、稳重强调", 20),
    ("赤1", "#FFFFFF", "#B91C1C", "深红强调块、按钮", 20),
    ("赤2", "#7F1D1D", "#FEF2F2", "浅红提示区、标签", 75),
    ("赤3", "#1A1A1A", "#FECACA", "柔和红底，适合卡片", 20),
    ("橙1", "#FFFFFF", "#C2410C", "深橙按钮/强调", 20),
    ("橙2", "#9A3412", "#FFF7ED", "暖橙浅底", 90),
    ("橙3", "#1A1A1A", "#FFEDD5", "杏色底，正文清晰", 20),
    ("黄1", "#422006", "#FEF9C3", "黄系最稳，阅读舒适", 20),
    ("黄2", "#1A1A1A", "#FDE68A", "明黄底必须深字", 20),
    ("黄3", "#FFFFFF", "#A16207", "深金强调", 20),
]
PALETTE_BY_NAME = {p[0]: p for p in PALETTES}

SLOT_SIZES = {"100x42": (100, 42), "80x40": (80, 40)}
OPACITY_LEVELS = (20, 40, 60, 75, 90, 100)
FONT_OPACITY_LEVELS = (60, 80, 100)
FONT_SIZES = (12, 18, 22)
ANCHORS = ("br", "tr", "bl", "tl")
RENDER_MODES = ("auto", "translucent", "solid")
FRAME_MS_MIN = 16                # 心跳/帧间隔下限（防误配置把 UI 拖死）

DEFAULTS = {
    # ---- 布局（D3/D6：竖排 1 列 ×10，固定坐标，空槽不画）----
    "slot_size": "100x42",
    "slot_count": 10,              # 固定，不开放
    "slot_gap_y": 3,               # 固定，不开放
    "anchor": "br",
    "pos_offset_x": -28,
    "pos_offset_y": -48,
    "pos_screen": "",              # 屏幕名，拔副屏时自动落回主屏
    # ---- 外观（D8′/D10/D11/D12）----
    "palette": "暖白",             # 16 预设之一
    "font_size": 18,               # 12 / 18 / 22
    "box_opacity": 60,             # 20/40/60/75/90/100，且受预设 min_opacity 约束
    "font_opacity": 100,           # 60 / 80 / 100
    "text_outline": False,         # 文字描边：默认关（观感不佳），勾选启用后仍是恒 100%
    "box_border": False,           # 悬浮框描边：默认关，勾选启用
    # ---- 行为（D1/D2/D5/D7）----
    "press_repeat_ms": 500,
    "hold_ms": 2000,
    "fade_frames": 4,
    "frame_ms": 60,
    "scroll_burst_ms": 300,
    "mouse_label_lang": "zh",
    "show_xbutton2": False,
    "merge_repeat": False,         # C5：关闭 ×N 合并，每次按压独占一槽
    # ---- 运行 ----
    "locked": True,
    "paused": False,
    "debug_log": False,             # 默认关：每键 3 行文件 IO 在低配机上是卡顿源
    "monitor_visible": True,
    "monitor_topmost": True,
    "monitor_history": 200,
    "render_mode": "auto",
    "self_check": True,
    "tray_notice": False,           # 启动气泡默认关（低配机上强制 DWM 重排）
}


def config_path():
    """打包(PyInstaller)后与 exe 同目录；源码运行则与本文件同目录。"""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "config.json")


def palette(name):
    """按名称取预设，未知名称回落默认「暖白」"""
    return PALETTE_BY_NAME.get(name) or PALETTE_BY_NAME[DEFAULTS["palette"]]


def slot_px(size_key):
    return SLOT_SIZES.get(size_key, SLOT_SIZES[DEFAULTS["slot_size"]])


def allowed_opacities(palette_name):
    """该预设允许的框透明度档位（>= 实测下限）"""
    floor = palette(palette_name)[4]
    return tuple(lv for lv in OPACITY_LEVELS if lv >= floor)


class Config:
    def __init__(self):
        self.path = config_path()
        self.data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            for k in DEFAULTS:                       # 只接受已知键，防脏数据
                if k in stored:
                    self.data[k] = stored[k]
        except (FileNotFoundError, OSError, ValueError):
            pass                                     # 无配置/坏配置 → 全默认
        self.sanitize()

    def sanitize(self):
        """枚举白名单 + 区间夹紧。任何非法值回落到默认，避免运行期炸。"""
        d, s = self.data, DEFAULTS
        if d.get("slot_size") not in SLOT_SIZES:
            d["slot_size"] = s["slot_size"]
        d["slot_count"] = 10
        d["slot_gap_y"] = max(0, min(12, int(d.get("slot_gap_y", 3))))
        if d.get("anchor") not in ANCHORS:
            d["anchor"] = s["anchor"]
        if d.get("palette") not in PALETTE_BY_NAME:
            d["palette"] = s["palette"]
        if d.get("font_size") not in FONT_SIZES:
            d["font_size"] = s["font_size"]
        if d.get("font_opacity") not in FONT_OPACITY_LEVELS:
            d["font_opacity"] = s["font_opacity"]
        # 框透明度：先夹到枚举，再夹到该预设的下限
        box = d.get("box_opacity", s["box_opacity"])
        if box not in OPACITY_LEVELS:
            box = min(OPACITY_LEVELS, key=lambda lv: abs(lv - int(box or 0)))
        floor = palette(d["palette"])[4]
        d["box_opacity"] = box if box >= floor else floor
        for k, lo, hi in (("press_repeat_ms", 100, 3000),
                          ("hold_ms", 300, 20000),
                          ("fade_frames", 4, 4),
                          ("frame_ms", 16, 200),
                          ("scroll_burst_ms", 50, 2000),
                          ("monitor_history", 20, 2000)):
            try:
                v = int(d.get(k, s[k]))
            except (TypeError, ValueError):
                v = s[k]
            d[k] = max(lo, min(hi, v))
        if d.get("render_mode") not in RENDER_MODES:
            d["render_mode"] = s["render_mode"]
        for k in ("locked", "paused", "debug_log", "monitor_visible",
                  "monitor_topmost", "show_xbutton2", "self_check",
                  "merge_repeat", "tray_notice", "text_outline", "box_border"):
            d[k] = bool(d.get(k, s[k]))

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass                                     # 磁盘异常不阻塞主流程

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)
