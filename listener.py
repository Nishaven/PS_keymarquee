# -*- coding: utf-8 -*-
"""listener.py — pynput 键鼠全局监听 → 跨线程信号桥

约定：pynput 回调线程内只做"归一化 + emit"，零耗时、无任何 UI 操作。
事件经 Qt 队列连接自动投递到 GUI 线程消费。

v2 变更（D1，已确认「每跨过 500ms 记一次新按压」）：
  Windows 按住不放会以 ~30ms 间隔重复投递 down（现场日志实测：按住 '2' 0.42s
  出现 14 条 down）。这些重复在最上游被吞掉，只有跨过 press_repeat_ms 才再算
  一次新按压。抬起始终放行，保证与按下配对。
  好处：下游事件量降约 15~30 倍；「持续时长」不再被反复重置；
        监控窗口 removeRow 抖动（v1 崩溃放大器）也随之消失。
  兜底：锁屏 / UAC / 切换桌面会吞掉 up，sweep_stuck() 超时会补发抬起事件。
"""
import time

from pynput import keyboard, mouse
from PyQt6.QtCore import QObject, pyqtSignal

STUCK_SEC = 15.0          # 按住超过这么久仍没等到 up → 判定事件丢失，强制结算


class EventBridge(QObject):
    """信号桥：pynput 回调线程 emit → GUI 线程 slot（跨线程自动队列连接）"""

    got = pyqtSignal(dict)


class InputListener:
    """全局键鼠监听器（键盘 + 鼠标各一条 pynput 线程）"""

    def __init__(self, bridge, cfg=None):
        self._bridge = bridge
        self._cfg = cfg
        self._held = {}                 # name -> 上次计数时刻（monotonic 秒）
        self._kb = keyboard.Listener(
            on_press=self._on_key_down, on_release=self._on_key_up)
        self._ms = mouse.Listener(
            on_click=self._on_click, on_scroll=self._on_scroll)

    # ---------------- 配置 ----------------
    def _gap(self):
        ms = 500
        if self._cfg is not None:
            try:
                ms = int(self._cfg["press_repeat_ms"])
            except (KeyError, TypeError, ValueError):
                ms = 500
        return max(0.1, ms / 1000.0)

    def start(self):
        self._kb.start()
        self._ms.start()

    def stop(self):
        self._kb.stop()
        self._ms.stop()

    def is_alive_kb(self):
        try:
            return bool(self._kb.is_alive())
        except Exception:
            return False

    def is_alive_ms(self):
        try:
            return bool(self._ms.is_alive())
        except Exception:
            return False

    # ---------------- 键盘 ----------------
    def _on_key_down(self, key):
        name = self._norm_key(key)
        if not name:
            return
        now = time.monotonic()
        last = self._held.get(name)
        if last is not None and now - last < self._gap():
            return                      # 自动重复：最上游吞掉，不 emit
        self._held[name] = now          # 首次按下 或 跨过 500ms → 一次新按压
        self._bridge.got.emit({"kind": "key", "name": name, "down": True})

    def _on_key_up(self, key):
        name = self._norm_key(key)
        if not name:
            return
        self._held.pop(name, None)      # 结束重复计时
        self._bridge.got.emit({"kind": "key", "name": name, "down": False})

    def sweep_stuck(self):
        """补发丢失的抬起事件（由覆盖层心跳顺带调用，不额外加定时器）"""
        if not self._held:
            return
        now = time.monotonic()
        for name, t in list(self._held.items()):
            if now - t > STUCK_SEC:
                self._held.pop(name, None)
                self._bridge.got.emit({"kind": "key", "name": name,
                                       "down": False})

    # ---------------- 鼠标 ----------------
    def _on_click(self, x, y, button, pressed):
        if pressed:                      # 只在按下时显示，释放不显示
            self._bridge.got.emit({"kind": "mouse", "name": button.name})

    def _on_scroll(self, x, y, dx, dy):
        if dy:                           # 横向滚轮 dx 暂不显示
            self._bridge.got.emit({"kind": "wheel", "dir": 1 if dy > 0 else -1})

    # ---------------- 归一化：pynput 键对象 → token 字符串 ----------------
    @staticmethod
    def _norm_key(key):
        """Key/KeyCode → token：'ctrl'/'shift'/'f5'/'a'/'5'；不可识别返回 None"""
        if isinstance(key, keyboard.Key):
            n = key.name
            if n.startswith("ctrl"):
                return "ctrl"            # ctrl / ctrl_l / ctrl_r
            if n.startswith("alt"):
                return "alt"             # alt / alt_l / alt_r / alt_gr
            if n.startswith("shift"):
                return "shift"           # shift / shift_l / shift_r
            if n.startswith("cmd"):
                return "win"             # cmd / cmd_l / cmd_r
            return n                     # f1~f24 / enter / esc / up ...
        if isinstance(key, keyboard.KeyCode):
            ch = key.char
            if ch and ch.isprintable() and ch.strip():
                return ch.lower()        # 普通可打印字符
            vk = getattr(key, "vk", None)
            if vk is not None:
                # 按住 Ctrl 时 char 变控制符（如 '\x03'），用 vk 还原
                if 65 <= vk <= 90:       # A~Z
                    return chr(vk).lower()
                if 48 <= vk <= 57:       # 0~9
                    return chr(vk)
                if 96 <= vk <= 105:      # 小键盘 0~9
                    return str(vk - 96)
            return None
        return None
