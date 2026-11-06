# -*- coding: utf-8 -*-
"""formatter.py — 事件格式化：键名映射 / 修饰键拆槽 / 滚轮突发合并

v2 变更（对应已确认决策 D4 / C5 / C6）：
  · D4 修饰键拆成多槽：Ctrl、Alt、Del 各占一格，不再拼成 "Ctrl + Alt + Del"。
    因此修饰键改为「按下即成条」（旧规则是抬起时才单独成条，会漏显示）。
    主键与修饰键一律按下成条，抬起不显示。
  · C5 关闭 ×N 连击合并：每次按压独占一槽，长按由 listener 的 500ms 规则产生多槽。
  · C6 长标签短名表：80px 宽 + 22px 字号下「侧键·后退」放不下，统一用短名。
  · 滚轮仍走 300ms 突发合并（它不是连击，是同一次滚动的多格），
    合并结果把次数写进文本，如「上滚 ×10」。
"""
from PyQt6.QtCore import QTimer

MOD_TOKENS = ("ctrl", "alt", "shift", "win")

KEY_LABELS = {
    "space": "空格", "enter": "回车", "esc": "Esc", "tab": "Tab",
    "backspace": "退格", "delete": "删除", "insert": "插入",
    "home": "Home", "end": "End", "page_up": "PgUp", "page_down": "PgDn",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "caps_lock": "Caps", "num_lock": "Num", "scroll_lock": "ScrLk",
    "print_screen": "PrtSc", "pause": "Pause", "menu": "Menu",
    "shift": "Shift", "ctrl": "Ctrl", "alt": "Alt", "win": "Win",
    "f13": "F13", "f14": "F14", "f15": "F15", "f16": "F16",
}
MOUSE_LABELS = {
    "zh": {"left": "左键", "right": "右键", "middle": "中键",
           "x1": "后退", "x2": "前进"},
    "en": {"left": "LMB", "right": "RMB", "middle": "MMB",
           "x1": "Back", "x2": "Fwd"},
}
WHEEL_LABELS = {
    "zh": {1: "上滚", -1: "下滚"},
    "en": {1: "Up", -1: "Down"},
}


class EventParser:
    def __init__(self, cfg):
        self.cfg = cfg
        self.sink = None              # callable(text: str, count: int)
        self.debug = None             # 可选调试回调
        self._wheel_dir = 0
        self._wheel_count = 0
        self._wheel_token = 0

    # ---------------- 入口 ----------------
    def feed(self, ev):
        kind = ev.get("kind")
        if kind == "key":
            self._feed_key(ev.get("name", ""), ev.get("down", False))
        elif kind == "mouse":
            self._feed_mouse(ev.get("name", ""))
        elif kind == "wheel":
            self._feed_wheel(ev.get("dir", 0))

    # ---------------- 键盘：按下即成条（D4）----------------
    def _feed_key(self, name, down):
        if not name or not down:
            return                          # 抬起不显示
        self._emit(self._label(name), 1)

    # ---------------- 鼠标 ----------------
    def _feed_mouse(self, name):
        if name == "x2" and not self.cfg["show_xbutton2"]:
            return
        label = MOUSE_LABELS.get(self.cfg["mouse_label_lang"], {}).get(name)
        if label:
            self._emit(label, 1)

    # ---------------- 滚轮：突发窗口合并 ----------------
    def _feed_wheel(self, direction):
        if self._wheel_dir != direction:        # 方向反转 → 旧方向立即成条
            self._flush_wheel()
            self._wheel_dir = direction
        self._wheel_count += 1
        self._wheel_token += 1
        token = self._wheel_token
        QTimer.singleShot(int(self.cfg["scroll_burst_ms"]),
                          lambda: self._maybe_flush_wheel(token))

    def _maybe_flush_wheel(self, token):
        if token == self._wheel_token:          # 窗口期内无新事件 → 结算
            self._flush_wheel()

    def _flush_wheel(self):
        if self._wheel_count:
            lang = self.cfg["mouse_label_lang"]
            base = WHEEL_LABELS.get(lang, {}).get(self._wheel_dir, "滚轮")
            n = self._wheel_count
            self._wheel_count = 0
            self._wheel_dir = 0
            self._emit(base if n <= 1 else "{} ×{}".format(base, n), n)

    # ---------------- 标签 ----------------
    def _label(self, token):
        if len(token) == 1:
            return token.upper()                # 字母 / 数字
        if token.startswith("f") and token[1:].isdigit():
            return token.upper()                # F1~F24
        return KEY_LABELS.get(token, token)

    def _emit(self, text, count):
        if text and self.sink:
            if self.debug:
                self.debug("emit: {!r} x{}".format(text, count))
            self.sink(text, count)
