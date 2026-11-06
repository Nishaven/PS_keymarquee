# -*- coding: utf-8 -*-
"""monitor.py — 诊断窗口：监听状态 + 最近按键流水（M1 极简化，对应已确认 C1）

v2 变更：
  · 删除「当前按住（实时时长）」整张 QTableWidget —— 它既是 80ms 周期重绘的来源，
    也是 v1 定位的崩溃源（removeRow 析构 item 后 _tick 仍访问 → RuntimeError →
    PyQt6 qFatal → 无控制台 exe 静默闪退）。D1 决定不再计算时长，这张表随之消失。
  · 保留「监听状态」与「最近按键」两块：产线需要一眼确认"软件到底有没有在收按键"。
  · 修 S6：_apply_topmost 原来用「改标志之后」的 isVisible() 决定是否 show()，
    而 Qt 改窗口标志会先隐藏窗口 → 判据恒为 False → 一勾一放监控窗口自己消失。
    现改为改标志「之前」取快照。
  · 窗口隐藏时停掉状态轮询定时器，不再空转。
"""
import datetime

from PyQt6.QtCore import Qt, QRect, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

import keystats as KS

BAR_CYAN = QColor("#22d3ee")          # 柱状图/进度条主色
BAR_CYAN_DIM = QColor("#0b3a47")      # 进度条底色

MOUSE_LABELS = {
    "left": "左键", "right": "右键", "middle": "中键",
    "x1": "后退", "x2": "前进",
}
WHEEL_LABELS = {1: "上滚", -1: "下滚"}


def _now():
    return datetime.datetime.now().strftime("%H:%M:%S")


class TopBarChart(QWidget):
    """TOP15 水平柱状图：每行 = 按键名 | 条形(宽度=占全部输入的百分比) | 次数+占比"""

    ROW_H = 16
    NAME_W = 64
    NUM_W = 92

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []                  # [(label, count, pct)]
        self.setMinimumHeight(60)

    def set_data(self, rows):
        self._rows = rows
        self.setMinimumHeight(
            max(60, TopBarChart.ROW_H * (len(rows) + 1) + 8))
        self.update()

    def paintEvent(self, e):
        # 防御性绘制：宽度不足时直接不画（实证 self.rect() 传入 drawText
        # 会触发本机 PyQt6 6.12 原生段错误——见 取证/_ks_err*.txt 二分记录）
        w = self.width()
        if w < 180 or self.height() < 12:
            return
        p = QPainter(self)
        # 根因修复（取证/_ks_err*.txt 完整二分）：Antialiasing 提示 + 圆角矩形
        # 在"统计页前台 + set_data 动态重绘"组合下触发本机 PyQt6 6.12 原生段错误
        # （去 AA + 直角后 3/3 稳定；带 AA 必崩）。此路径不使用抗锯齿。
        f = p.font()
        f.setPixelSize(11)
        p.setFont(f)
        x0 = 4
        y = 2
        bar_w = max(10, w - TopBarChart.NAME_W - TopBarChart.NUM_W - 16)
        if not self._rows:
            p.setPen(QColor("#6b7f94"))
            p.drawText(QRect(8, 4, max(10, w - 16), max(10, self.height() - 8)),
                       Qt.AlignmentFlag.AlignCenter,
                       "暂无数据，按任意键后此处显示 TOP15 占比")
            p.end()
            return
        for label, cnt, pct in self._rows:
            # 名字（右对齐，超宽省略）
            p.setPen(QColor("#8fa3b8"))
            from PyQt6.QtGui import QFontMetrics
            fm = QFontMetrics(f)
            shown = fm.elidedText(label, Qt.TextElideMode.ElideRight,
                                  TopBarChart.NAME_W - 4)
            p.drawText(QRect(x0, y, TopBarChart.NAME_W, TopBarChart.ROW_H),
                       Qt.AlignmentFlag.AlignVCenter
                       | Qt.AlignmentFlag.AlignRight, shown)
            # 条（全部几何值钳为正）
            bx = x0 + TopBarChart.NAME_W + 4
            by = y + (TopBarChart.ROW_H - 8) // 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(BAR_CYAN_DIM)
            p.drawRect(bx, by, bar_w, 8)
            if pct > 0:
                bw = max(2.0, min(float(bar_w), bar_w * float(pct)))
                p.setBrush(BAR_CYAN)
                p.drawRect(bx, by, int(bw), 8)
            # 数字（次数 + 占比）
            p.setPen(QColor("#cfe6f5"))
            p.drawText(QRect(bx + bar_w + 6, y, TopBarChart.NUM_W,
                              TopBarChart.ROW_H),
                       Qt.AlignmentFlag.AlignVCenter
                       | Qt.AlignmentFlag.AlignLeft,
                       "{} 次  {:.1f}%".format(cnt, pct * 100))
            y += TopBarChart.ROW_H
        p.end()


class MonitorWindow(QWidget):
    def __init__(self, cfg, listener=None, stats=None):
        super().__init__()
        self.cfg = cfg
        self._listener = listener
        self.stats = stats or KS.KeyStats()      # 按键计数器（可注入，测试用）
        self._count = 0

        self.setWindowTitle("KeyMarquee · 监听诊断")
        self.setMinimumWidth(420)
        self.setMinimumHeight(400)
        self._build_ui()
        self._apply_topmost(bool(cfg["monitor_topmost"]))

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(2000)
        self._refresh_status()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        self._status = QLabel("● 检测中")
        self._status.setStyleSheet("color:#22d3ee;font-weight:600;")
        top.addWidget(self._status, 1)
        self._counter = QLabel("已捕获 0 次")
        self._counter.setStyleSheet("color:#94a3b8;")
        top.addWidget(self._counter)
        self._topmost = QCheckBox("强制置顶")
        self._topmost.setChecked(bool(self.cfg["monitor_topmost"]))
        self._topmost.toggled.connect(self._on_topmost_toggled)
        top.addWidget(self._topmost)
        clear = QLabel('<a href="clear">清空</a>')
        clear.setOpenExternalLinks(False)
        clear.linkActivated.connect(self._clear_all)
        top.addWidget(clear)
        root.addLayout(top)

        # ---- 页签：流水 / 按键统计 ----
        self._tabs = QTabWidget(self)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self._tabs, 1)
        self._build_history_tab()
        self._build_stats_tab()

        hint = QLabel(
            "本窗口只用于确认软件确实在收按键，不显示按压时长（已按需求取消）。\n"
            "「按键统计」自软件启动起累计，重启归零；计数口径与悬浮层一致（含 500ms 长按记次）。\n"
            "若长时间无任何记录，多为杀软拦截了全局键盘钩子（SetWindowsHookEx）："
            "请将本程序加入白名单，或右键“以管理员身份运行”。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#94a3b8;font-size:11px;")
        root.addWidget(hint)

    def _build_history_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 6, 0, 0)
        self._history = QListWidget(page)
        self._history.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._history.setStyleSheet(
            "QListWidget{background:#0b1220;border:1px solid #1e2b3a;"
            "color:#e2e8f0;font-family:'Consolas','Microsoft YaHei UI';}"
            "QListWidget::item{padding:2px 6px;}")
        lay.addWidget(self._history)
        self._tabs.addTab(page, "最近按键")

    def _build_stats_tab(self):
        """统计区拆为两个独立标签页（v2.6，用户用例反馈）：
        「TOP 15」柱状图+明细，「全部按键」完整明细。
        明细装在 ScrollableStatList 里：行数再多也只在页内滚动，
        不再把窗口撑出显示区。"""
        from statlist import ScrollableStatList
        # ---- 页 1：TOP 15 ----
        page_top = QWidget()
        lay_t = QVBoxLayout(page_top)
        lay_t.setContentsMargins(0, 6, 0, 0)
        lay_t.setSpacing(6)
        self._stats_summary = QLabel("暂无按压")
        self._stats_summary.setStyleSheet(
            "color:#8fe6f5;font-weight:600;font-size:12px;")
        lay_t.addWidget(self._stats_summary)
        lay_t.addWidget(QLabel("TOP 15 占比（占全部按键输入的百分比）",
                               page_top))
        self._bar_chart = TopBarChart(page_top)
        lay_t.addWidget(self._bar_chart)
        self._top_table = ScrollableStatList(page_top)
        lay_t.addWidget(self._top_table, 1)
        self._tabs.addTab(page_top, "TOP 15")

        # ---- 页 2：全部按键 ----
        page_all = QWidget()
        lay_a = QVBoxLayout(page_all)
        lay_a.setContentsMargins(0, 6, 0, 0)
        self._all_table = ScrollableStatList(page_all)
        lay_a.addWidget(self._all_table)
        self._tabs.addTab(page_all, "全部按键")

    # ---------------- 事件入口（订阅 bridge.got）----------------
    def feed(self, ev):
        kind = ev.get("kind")
        # 计数器先记（返回展示名；滚轮每格都计，不受 300ms 突发合并影响——
        # 合并是显示行为，统计按实际物理事件计）
        label = self.stats.feed(ev)
        text = None
        if kind == "key":
            if ev.get("down"):
                text = _label_key(ev.get("name", ""))
        elif kind == "mouse":
            text = MOUSE_LABELS.get(ev.get("name", ""), ev.get("name", ""))
        elif kind == "wheel":
            text = WHEEL_LABELS.get(ev.get("dir", 0))
        if not text:
            return
        self._count += 1
        self._counter.setText("已捕获 {} 次".format(self._count))
        self._add_history(text)
        # 统计页可见时实时刷新（索引 1=TOP15 / 2=全部按键；流水页 0 不刷新）
        if self._tabs.currentIndex() >= 1:
            self._refresh_stats()

    # ---------------- 统计页刷新 ----------------
    def _refresh_stats(self):
        """TOP15 + 全部按键表刷新（只在统计页可见时刷新，省开销）"""
        if self._tabs.currentIndex() < 1:
            return
        total = self.stats.total
        distinct = self.stats.distinct
        started = self.stats.started_at()
        if total == 0:
            self._stats_summary.setText("暂无按压")
        else:
            import time as _t
            mins = (_t.time() - started) / 60.0
            dur = ("{:.0f} 分钟".format(mins) if mins >= 1
                   else "{:.0f} 秒".format(mins * 60))
            self._stats_summary.setText(
                "累计 {} 次按压 · {} 种按键 · 统计时长 {}".format(
                    total, distinct, dur))

        top15 = self.stats.top(15)
        all_items = self.stats.all_sorted()
        # 占比 = 该键次数 / 全部按压总次数（total=0 时防零除）
        top_rows = [(lb, c, (c / total if total else 0.0))
                    for lb, c in top15]
        self._bar_chart.set_data(top_rows)
        self._top_table.set_rows(top_rows)
        self._all_table.set_rows(
            [(lb, c, (c / total if total else 0.0))
             for lb, c in all_items])

    def _add_history(self, text):
        item = QListWidgetItem("{}  {}".format(_now(), text))
        self._history.addItem(item)
        maxn = int(self.cfg["monitor_history"])
        while self._history.count() > maxn:
            self._history.takeItem(0)
        self._history.scrollToBottom()

    # ---------------- 监听状态 ----------------
    def _refresh_status(self):
        if self._listener is None:
            kb = ms = True
        else:
            kb = self._listener.is_alive_kb()
            ms = self._listener.is_alive_ms()
        if kb and ms:
            self._status.setText("● 监听中（键盘 ✓  鼠标 ✓）")
            self._status.setStyleSheet("color:#22d3ee;font-weight:600;")
        else:
            self._status.setText("● 监听异常（键盘 {}  鼠标 {}）".format(
                "✓" if kb else "✗", "✓" if ms else "✗"))
            self._status.setStyleSheet("color:#f87171;font-weight:600;")

    # ---------------- 强制置顶（S6 快照法）----------------
    def set_topmost(self, on):
        self._topmost.setChecked(bool(on))
        self.cfg["monitor_topmost"] = bool(on)
        self.cfg.save()
        self._apply_topmost(bool(on))

    def _on_topmost_toggled(self, on):
        self.cfg["monitor_topmost"] = bool(on)
        self.cfg.save()
        self._apply_topmost(bool(on))

    def _apply_topmost(self, on):
        was_visible = self.isVisible()          # ← 改标志「之前」取快照
        flags = self.windowFlags()
        if on:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if was_visible:
            self.show()
            self.raise_()

    def _clear_all(self):
        self._history.clear()
        self._count = 0
        self._counter.setText("已捕获 0 次")
        self.stats.clear()
        self._refresh_stats()

    # ---------------- 生命周期 ----------------
    def hideEvent(self, e):
        self._status_timer.stop()               # 隐藏时不空转
        super().hideEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._status_timer.isActive():
            self._status_timer.start(2000)
        self._refresh_status()
        self._refresh_stats()

    def _on_tab_changed(self, idx):
        """切到统计相关页（TOP15=1 / 全部按键=2）时刷新一次"""
        if idx >= 1:
            self._refresh_stats()

    def closeEvent(self, event):                # 关闭=隐藏，托盘常驻
        event.ignore()
        self.hide()


def _label_key(token):
    if not token:
        return ""
    if len(token) == 1:
        return token.upper()
    if token.startswith("f") and token[1:].isdigit():
        return token.upper()
    from formatter import KEY_LABELS
    return KEY_LABELS.get(token, token)
