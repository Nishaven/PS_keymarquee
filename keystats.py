# -*- coding: utf-8 -*-
"""keystats.py — 按键计数器（20261105 新增需求）

自软件开启起累计各按键按压次数（进程内存计数，重启归零——需求原话"从开启到当前"）：
  · 计数口径：显示链口径（bridge.got）——即经 listener 500ms 去重后的"有效按压"。
    按住不放 3 秒 = 6 次（每跨过 500ms 记一次），与悬浮层槽位出现次数一致，
    这样"悬浮层出现过多少格、统计表就是多少次"，两个视图数字自洽。
  · 范围：键盘按键 down、鼠标按键按下、滚轮（按方向合并）。
  · 不落盘：纯内存 dict，键数级（<300 种），零 IO 开销。
  · 独立于 UI：本模块不 import 任何 Qt 组件，方便单测与未来复用。
"""
import threading

# 滚轮方向 → 展示名（与悬浮层 formatter 的短标签一致）
WHEEL_NAMES = {1: "上滚", -1: "下滚"}

# 鼠标键 → 展示名（与 formatter MOUSE_LABELS zh 短标签一致）
MOUSE_NAMES = {"left": "左键", "right": "右键", "middle": "中键",
               "x1": "后退", "x2": "前进"}


def _label_key(token):
    """token → 展示名；与 monitor._label_key 同规则（避免循环 import，此处复制一份）"""
    if not token:
        return ""
    if len(token) == 1:
        return token.upper()
    if token.startswith("f") and token[1:].isdigit():
        return token.upper()
    from formatter import KEY_LABELS
    return KEY_LABELS.get(token, token)


class KeyStats:
    """线程安全按键计数器。feed() 在 GUI 线程调用（与悬浮层同一信号源）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._counts = {}          # label -> 次数
        self._total = 0            # 总按压次数
        self._started = None       # 统计起点（首次按压时记录）

    # ---------------- 事件入口 ----------------
    def feed(self, ev):
        """订阅 bridge.got。返回展示名（供调用方决定是否计入流水）"""
        kind = ev.get("kind")
        label = None
        if kind == "key":
            if ev.get("down"):                       # 只计按下
                label = _label_key(ev.get("name", ""))
        elif kind == "mouse":
            label = MOUSE_NAMES.get(ev.get("name", ""), ev.get("name", ""))
        elif kind == "wheel":
            label = WHEEL_NAMES.get(ev.get("dir", 0))
        if not label:
            return None
        with self._lock:
            self._counts[label] = self._counts.get(label, 0) + 1
            self._total += 1
            if self._started is None:
                import time
                self._started = time.time()
        return label

    # ---------------- 查询 ----------------
    def top(self, n=15):
        """前 n 名 [(label, count), ...]，按次数降序、同次按首次出现序"""
        with self._lock:
            items = sorted(self._counts.items(),
                           key=lambda kv: -kv[1])[:n]
        return items

    def all_sorted(self):
        """全部按键表 [(label, count), ...]，按次数降序"""
        with self._lock:
            return sorted(self._counts.items(), key=lambda kv: -kv[1])

    @property
    def total(self):
        with self._lock:
            return self._total

    @property
    def distinct(self):
        with self._lock:
            return len(self._counts)

    def started_at(self):
        return self._started

    # ---------------- 维护 ----------------
    def clear(self):
        """清零（诊断窗口「清空」联动）"""
        with self._lock:
            self._counts.clear()
            self._total = 0
            self._started = None
