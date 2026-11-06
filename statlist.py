# -*- coding: utf-8 -*-
"""statlist.py — 按键统计列表（QPainter 自绘，20261105）

背景：QTableWidget 在本机 PyQt6 6.12 + Win10 组合下，"切页 + 有数据首渲染"
会触发不可复现的原生层段错误（见 取证/_ks_err*.txt 的完整二分记录；
同一代码在独立脚本中 10+ 次不崩、在集成测试中 100% 崩，faulthandler 无法捕获）。
工程决策：统计明细弃用 Qt 表格控件，改为自绘——与悬浮层（overlay.py）、
柱状图（monitor.TopBarChart）同一技术路线，该路线已被验证数百次无原生问题。

职责：以紧凑行渲染 (名次 | 按键名 | 条形占比 | 次数 | 百分比)，
支持 TOP15 与全部按键两种用途（只是数据源不同，绘制完全一致）。
"""
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QScrollArea, QWidget

COL_RANK_BG = QColor("#131c28")
TXT = QColor("#cfe6f5")
TXT_DIM = QColor("#8fa3b8")
BAR = QColor("#22d3ee")
BAR_BG = QColor("#0b3a47")
ROW_BG = QColor("#0b1220")
ROW_BG_ALT = QColor("#0e1620")
LINE = QColor("#1e2b3a")

ROW_H = 20
COL_W = {"rank": 44, "name": 76, "bar": None, "cnt": 64, "pct": 64}
HDR_H = 20


class StatListWidget(QWidget):
    """自绘统计列表（固定高度、内容滚动的版本由 ScrollableStatList 提供）。

    本控件：按数据行数给出 sizeHint，自身不滚动；放入 QScrollArea 后
    由外层滚动。行数不再撑爆父布局（v2.5 的缺陷：setMinimumHeight 随行数
    增长把窗口撑出显示区）。"""

    def __init__(self, parent=None, show_header=True):
        super().__init__(parent)
        self._rows = []                    # [(label, count, pct)]
        self._show_header = show_header

    def set_rows(self, rows):
        self._rows = list(rows or [])
        self.setMinimumHeight(
            HDR_H + ROW_H * len(self._rows) + 4)
        self.updateGeometry()
        self.update()

    def row_count(self):
        return len(self._rows)

    def row_text(self, r):
        """测试读取接口：返回 (label, count, pct_text)"""
        if 0 <= r < len(self._rows):
            lb, c, pct = self._rows[r]
            return lb, c, "{:.2f}%".format(pct * 100)
        return None

    def find(self, label):
        """测试读取接口：返回 (count, pct_text) 或 None"""
        for lb, c, pct in self._rows:
            if lb == label:
                return c, "{:.2f}%".format(pct * 100)
        return None

    # ---------------- 绘制 ----------------
    def paintEvent(self, e):
        w, h = self.width(), self.height()
        if w < 100 or h < 10:
            return
        p = QPainter(self)
        # 不使用抗锯齿（同 monitor.TopBarChart 的根因修复）
        f = p.font()
        f.setPixelSize(12)
        p.setFont(f)
        fm = QFontMetrics(f)

        # 列坐标
        x_rank = 4
        x_name = x_rank + COL_W["rank"]
        x_cnt = w - COL_W["cnt"] - COL_W["pct"] - 4
        x_pct = x_cnt + COL_W["cnt"]
        x_bar = x_name + COL_W["name"] + 6
        bar_w = x_cnt - x_bar - 8

        # 背景
        p.fillRect(0, 0, w, h, ROW_BG)

        y = 0
        if self._show_header:
            p.fillRect(0, 0, w, HDR_H, COL_RANK_BG)
            p.setPen(TXT_DIM)
            p.drawText(QRect(x_rank, 0, COL_W["rank"], HDR_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "名次")
            p.drawText(QRect(x_name, 0, COL_W["name"], HDR_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       "按键")
            p.drawText(QRect(x_cnt, 0, COL_W["cnt"], HDR_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       "次数")
            p.drawText(QRect(x_pct, 0, COL_W["pct"], HDR_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       "占比")
            y = HDR_H

        for i, (label, cnt, pct) in enumerate(self._rows):
            if y + ROW_H > h:
                break                                  # 可视区截断
            if getattr(StatListWidget, '_NO_DRAW', False):
                y += ROW_H
                continue
            if i % 2 == 1:
                p.fillRect(0, y, w, ROW_H, ROW_BG_ALT)
            # 名次
            p.setPen(TXT_DIM if i >= 3 else BAR)
            p.drawText(QRect(x_rank, y, COL_W["rank"], ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       str(i + 1))
            # 按键名（超宽省略）
            p.setPen(TXT)
            shown = fm.elidedText(label, Qt.TextElideMode.ElideRight,
                                  COL_W["name"] - 6)
            p.drawText(QRect(x_name, y, COL_W["name"], ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       shown)
            # 占比条
            if bar_w > 8:
                by = y + (ROW_H - 8) // 2
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(BAR_BG)
                p.drawRect(x_bar, by, bar_w, 8)
                if pct > 0:
                    p.setBrush(BAR)
                    p.drawRect(x_bar, by, max(2, int(bar_w * pct)), 8)
            # 次数
            p.setPen(TXT)
            p.drawText(QRect(x_cnt, y, COL_W["cnt"], ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       str(cnt))
            # 百分比
            p.drawText(QRect(x_pct, y, COL_W["pct"], ROW_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       "{:.2f}%".format(pct * 100))
            y += ROW_H

        # 底部边线
        p.setPen(QPen(LINE))
        p.drawLine(0, h - 1, w, h - 1)
        if not self._rows:
            p.setPen(TXT_DIM)
            p.drawText(QRect(8, 4, max(10, w - 16), max(10, h - 8)),
                       Qt.AlignmentFlag.AlignCenter, "暂无数据")
        p.end()


class ScrollableStatList(QScrollArea):
    """可滚动的统计列表容器：StatListWidget + 滚动条 + 滚轮。

    v2.6 修复（用户用例反馈）：按键种类超过 15 时，旧实现把明细列表
    按行数撑高、把窗口顶出显示区。现在明细固定占满可视区，
    内容超出时滚动（滚轮 + 右侧滚动条）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inner = StatListWidget()
        self._inner.show_header = False          # 外层有标题，内部不重复表头
        self.setWidget(self._inner)
        self.setWidgetResizable(True)            # 宽度跟随视口（无横向滚动）
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setStyleSheet(
            "QScrollArea{background:#0b1220;border:1px solid #1e2b3a;}"
            "QScrollBar:vertical{background:#131c28;width:10px;margin:0;}"
            "QScrollBar::handle:vertical{background:#2d5f86;"
            "border-radius:3px;min-height:24px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{"
            "height:0;width:0;}")

    def set_rows(self, rows):
        self._inner.set_rows(rows)

    def row_count(self):
        return self._inner.row_count()

    def row_text(self, r):
        return self._inner.row_text(r)

    def find(self, label):
        return self._inner.find(label)
