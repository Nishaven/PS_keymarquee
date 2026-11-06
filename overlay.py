# -*- coding: utf-8 -*-
"""overlay.py — 悬浮覆盖层：10 个固定槽位、自绘、空槽不画、4 帧淡出（M1 重写）

对应已确认决策：
  D3 竖排 1 列 ×10，编号不上屏（顺序由「上早下晚」表达）
  D6 槽位坐标算死，窗口尺寸固定，空槽什么都不画 → 运行期零 resize / 零 move
  D7 不做淡入；淡出 4 帧（75/50/25/0），由一个心跳按时间戳驱动
  D8′ 配色取 16 组固化预设；D9 文字描边（与字色明度相反、恒定 100%、只一圈）
  N4 1px 边框用预设字色，保证浅底预设叠浅桌面时"底板轮廓"仍可辨
  S7 set_locked 改窗口标志「之前」取可见性快照（原版用改后的 isVisible，
     导致默认 locked=true 时窗口被自己隐藏且永不恢复 —— 桌面看不见的真因）

实现要点：
  · 不用子控件、不用布局、不用 QPropertyAnimation、不用 setStyleSheet：
    10 个槽只是本窗口 paintEvent 里的 10 个矩形 + 一份状态，重绘只 update 变化的那一格
  · 环形缓冲：head 单调推进，新按压写在 head 上（视觉上自上而下填充，与示意图一致）；
    槽过期就地清空，不塌陷（C2 位置绝对稳定）
  · 心跳只在有活动槽时运行，空闲自动 stop() → 空闲期 0 周期任务
"""
import math
import time

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPainterPath,
                         QPen)
from PyQt6.QtWidgets import QApplication, QWidget

import config as C

PAD_X = 8                   # 槽内左右留白，超出用省略号截断
CORNER = 8                  # 圆角半径
BORDER_ALPHA = 60           # N4：底板轮廓边框的不透明度（%）


class OverlayWindow(QWidget):
    """无边框 / 置顶 / 半透明覆盖层（不进任务栏，不抢焦点）"""

    def __init__(self, cfg, dbg=None):
        super().__init__()
        self.cfg = cfg
        self.dbg = dbg or (lambda m: None)
        self.tick_hook = None             # main 注入 listener.sweep_stuck

        self._n = int(cfg["slot_count"])
        self._texts = [""] * self._n
        self._alphas = [0] * self._n
        self._expire = [None] * self._n   # 淡出结束时刻（monotonic 秒）
        self._fade_start = [None] * self._n
        self._rects = []
        self._dragging = False
        self._drag_off = None
        self._positioned = False
        self._ticks = 0

        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.Tool)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._apply_render_mode(cfg["render_mode"])

        self._timer = QTimer(self)
        self._timer.setInterval(max(C.FRAME_MS_MIN, int(cfg["frame_ms"])))
        self._timer.timeout.connect(self._tick)

        self._recompute_geometry()

    # ================= 渲染模式 =================
    def _apply_render_mode(self, mode):
        """translucent = 逐像素 alpha（空槽真透明）；solid = 保底，整窗一块不透明底"""
        eff = mode
        if mode == "auto":
            eff = "translucent" if _composition_enabled() else "solid"
        self._solid = (eff == "solid")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,
                          not self._solid)
        if self._solid:
            self.setWindowOpacity(max(0.20, self.cfg["box_opacity"] / 100.0))

    # ================= 几何（固定，不随内容变化）=================
    def _recompute_geometry(self):
        w, h = C.slot_px(self.cfg["slot_size"])
        gap = int(self.cfg["slot_gap_y"])
        n = self._n
        total_h = h * n + gap * (n - 1)
        self.setFixedSize(w, total_h)
        self._rects = [QRect(0, i * (h + gap), w, h) for i in range(n)]
        self._slot_h = h

    # ================= 事件入口 =================
    def push(self, text, count=1):
        """一次按压占一格（C5 已关闭 ×N 合并，count 参数仅为兼容旧调用）。

        FIFO 语义（20261103 需求修正）："从 10 进，从 1 出"：
          · 新内容无条件进入第 10 格（屏幕最下）；
          · 若第 10 格已被占用（未到期的活内容），全列上移一格，
            最旧（顶部）一格被挤出 —— 与 10 格全满时的行为完全一致；
          · 淡出过期的槽就地清空留位，不塌陷（D6 位置稳定）。
          旧实现的两处错误已废弃：
            ① 环形覆盖（写满回写第 1 格 → 新内容出现在顶部）；
            ② "找最靠下空槽"（活内容过期后，新内容会插到旧内容上方 → 顺序错乱）。"""
        if not text:
            return
        now = time.monotonic()
        hold = int(self.cfg["hold_ms"]) / 1000.0
        fade_total = (int(self.cfg["fade_frames"])
                      * int(self.cfg["frame_ms"])) / 1000.0

        if self._expire[self._n - 1] is not None:
            # 底格被占：整体上移一格，顶格挤出（无论它是活内容还是空位）
            self._texts.pop(0)
            self._alphas.pop(0)
            self._expire.pop(0)
            self._fade_start.pop(0)
            self._texts.append("")
            self._alphas.append(0)
            self._expire.append(None)
            self._fade_start.append(None)
        i = self._n - 1

        self._texts[i] = str(text)
        self._alphas[i] = 100
        self._fade_start[i] = now + hold            # 到点开始 4 帧淡出
        self._expire[i] = self._fade_start[i] + fade_total
        self.update()
        if not self._timer.isActive():
            self._timer.start()
        self.dbg("slot[{}] <- {!r}".format(i, text))

    # ================= 心跳（唯一周期任务）=================
    def _tick(self):
        now = time.monotonic()
        frames = max(1, int(self.cfg["fade_frames"]))
        step_ms = max(C.FRAME_MS_MIN, int(self.cfg["frame_ms"]))
        step = step_ms / 1000.0
        alive = False
        for i in range(self._n):
            if self._expire[i] is None:
                continue
            if now < self._fade_start[i]:
                new = 100
            else:
                k = int((now - self._fade_start[i]) // step) + 1
                new = 100 - k * (100 // frames)
            if new <= 0:
                self._texts[i] = ""
                self._alphas[i] = 0
                self._expire[i] = None
                self._fade_start[i] = None
                self.update(self._rects[i])
                continue
            alive = True
            if new != self._alphas[i]:
                self._alphas[i] = new
                self.update(self._rects[i])
        self._ticks += 1
        if self.tick_hook and (self._ticks % 16 == 0):
            try:
                self.tick_hook()
            except Exception as e:                      # 兜底不影响显示
                self.dbg("tick_hook err: {}".format(e))
        if not alive:
            self._timer.stop()                          # 空闲 → 0 周期任务
            self.dbg("heartbeat stopped (idle)")

    # ================= 绘制 =================
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        pal = C.palette(self.cfg["palette"])
        fg = QColor(pal[1])
        bg = QColor(pal[2])
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(int(self.cfg["font_size"]))
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        box_pct = int(self.cfg["box_opacity"])
        font_pct = int(self.cfg["font_opacity"])
        for i, r in enumerate(self._rects):
            a = self._alphas[i]
            txt = self._texts[i]
            if a <= 0 or not txt:
                continue                                   # D6：空槽什么都不画
            if e.rect().intersects(r):
                self._paint_slot(p, r, txt, fg, bg, fm, a, box_pct, font_pct)
        p.end()

    def _paint_slot(self, p, r, txt, fg, bg, fm, a, box_pct, font_pct):
        fade = a / 100.0
        rect = QRect(r)
        # 底板
        box = QColor(bg)
        box.setAlpha(int(255 * (box_pct / 100.0) * fade))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(box)
        target = rect.adjusted(0, 0, -1, -1)
        p.drawRoundedRect(target, CORNER, CORNER)
        # 悬浮框描边：默认关（用户反馈描边不好看），勾选 box_border 启用
        if self.cfg.get("box_border", False):
            bd = QColor(fg)
            bd.setAlpha(int(255 * (BORDER_ALPHA / 100.0) * fade))
            pen = QPen(bd)
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(target, CORNER, CORNER)
        # 文本（描边默认关，勾选 text_outline 启用；描边恒 100% 不吃字透明度）
        avail = max(6, rect.width() - 2 * PAD_X)
        shown = fm.elidedText(txt, Qt.TextElideMode.ElideRight, avail)
        tw = fm.horizontalAdvance(shown)
        x = rect.x() + max(PAD_X, (rect.width() - tw) // 2)
        y = rect.y() + (rect.height() + fm.ascent() - fm.descent()) // 2
        path = QPainterPath()
        path.addText(float(x), float(y), p.font(), shown)
        if self.cfg.get("text_outline", False):
            halo = QColor("#FFFFFF") if fg.lightnessF() < 0.5 else QColor("#000000")
            halo.setAlpha(int(255 * fade))
            p.setPen(QPen(halo, max(1.0, int(self.cfg["font_size"]) / 16.0),
                          Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
        else:
            p.setPen(Qt.PenStyle.NoPen)
        core = QColor(fg)
        core.setAlpha(int(255 * (font_pct / 100.0) * fade))
        p.setBrush(core)
        p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)

    # ================= 外观热更新 =================
    def refresh_style(self):
        self._n = int(self.cfg["slot_count"])
        if len(self._texts) != self._n:
            self._texts = [""] * self._n
            self._alphas = [0] * self._n
            self._expire = [None] * self._n
            self._fade_start = [None] * self._n
            self._apply_render_mode(self.cfg["render_mode"])
        self._recompute_geometry()
        self._positioned = False
        self._apply_anchor()
        self.update()

    # ================= 位置与锁定（S7）=================
    def set_locked(self, locked):
        self.cfg["locked"] = bool(locked)
        was_visible = self.isVisible()          # ← 改标志「之前」取快照
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput,
                           bool(locked))
        if was_visible:
            self.show()
            self.raise_()
        self.update()
        self.dbg("set_locked({}) was_visible={} now_visible={}".format(
            locked, was_visible, self.isVisible()))

    def showEvent(self, e):
        super().showEvent(e)
        if not self._positioned:
            self._positioned = True
            self._apply_anchor()
        # 重检补漏：隐藏期间可能有槽已过期/心跳已停，重新显示时若仍有活槽则恢复心跳，
        # 否则这些槽会冻结在隐藏前的透明度上不再消退
        if (not self._timer.isActive()
                and any(t is not None for t in self._expire)):
            self._timer.start()

    def _screens(self):
        return QApplication.screens()

    def _pick_screen(self):
        want = str(self.cfg.get("pos_screen") or "")
        for s in self._screens():
            if s.name() == want:
                return s
        return self.screen() or QApplication.primaryScreen()

    def _apply_anchor(self):
        scr = self._pick_screen()
        if scr is None:
            self.move(60, 60)
            return
        av = scr.availableGeometry()
        w, h = self.width(), self.height()
        ox, oy = int(self.cfg["pos_offset_x"]), int(self.cfg["pos_offset_y"])
        anchor = self.cfg["anchor"]
        if anchor == "br":
            x, y = av.right() - w + ox + 1, av.bottom() - h + oy + 1
        elif anchor == "tr":
            x, y = av.right() - w + ox + 1, av.top() - oy
        elif anchor == "bl":
            x, y = av.left() - ox, av.bottom() - h + oy + 1
        else:                                    # tl
            x, y = av.left() - ox, av.top() - oy
        x = min(max(x, av.left()), max(av.left(), av.right() - w))
        y = min(max(y, av.top()), max(av.top(), av.bottom() - h))
        self.move(x, y)

    def save_position(self):
        """把当前坐标折算成「最近锚点 + 偏移」保存，换分辨率/拔屏后仍能落回可视区"""
        scr = self._pick_screen()
        if scr is None:
            return
        av = scr.availableGeometry()
        w, h = self.width(), self.height()
        x, y = self.x(), self.y()
        cands = {
            "br": (av.right() - w + 1, av.bottom() - h + 1),
            "tr": (av.right() - w + 1, av.top()),
            "bl": (av.left(), av.bottom() - h + 1),
            "tl": (av.left(), av.top()),
        }
        best = min(cands.items(),
                   key=lambda kv: math.hypot(x - kv[1][0], y - kv[1][1]))
        self.cfg["anchor"] = best[0]
        bx, by = best[1]
        self.cfg["pos_offset_x"] = int(x - bx)
        self.cfg["pos_offset_y"] = int(y - by)
        self.cfg["pos_screen"] = scr.name()
        self.cfg.save()
        self.dbg("saved pos anchor={} offset=({},{}) screen={}".format(
            self.cfg["anchor"], self.cfg["pos_offset_x"],
            self.cfg["pos_offset_y"], scr.name()))

    # ================= 移动模式：拖拽 =================
    def mousePressEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton
                and not self.cfg["locked"]):
            self._dragging = True
            self._drag_off = (e.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())

    def mouseMoveEvent(self, e):
        if self._dragging and self._drag_off is not None:
            self.move(e.globalPosition().toPoint() - self._drag_off)

    def mouseReleaseEvent(self, e):
        if self._dragging:
            self._dragging = False
            self.save_position()

    # ================= 自检（S9 轻量版）=================
    def selfcheck(self):
        """返回 (是否可见, 自身渲染非透明像素数)。真·屏幕像素 diff 由取证脚本量。"""
        img = self.grab().toImage()
        img = img.convertToFormat(img.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        buf = img.bits()
        try:
            buf.setsize(w * h * 4)
        except AttributeError:
            buf.setBytes(w * h * 4)
        alpha = bytes(buf)[3::4]
        painted = sum(1 for v in alpha if v > 0)
        vis = self.isVisible()
        ok = bool(vis and painted > 50)
        self.dbg("selfcheck visible={} painted_px={} geo={} mode={}".format(
            vis, painted, self.frameGeometry().getRect(),
            "solid" if self._solid else "translucent"))
        return ok, painted

    def clear_all(self):
        for i in range(self._n):
            self._texts[i] = ""
            self._alphas[i] = 0
            self._expire[i] = None
            self._fade_start[i] = None
        self._head = 0
        self._timer.stop()
        self.update()

    def hideEvent(self, e):
        self._timer.stop()                 # 隐藏时不空转
        super().hideEvent(e)


def _composition_enabled():
    """DwmIsCompositionEnabled；拿不到就按 True 处理（Win10 默认合成开启）"""
    try:
        import ctypes
        en = ctypes.c_int(0)
        if ctypes.windll.dwmapi.DwmIsCompositionEnabled(ctypes.byref(en)) == 0:
            return bool(en.value)
    except Exception:
        pass
    return True
