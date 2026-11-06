# -*- coding: utf-8 -*-
"""settings.py — 设置窗口（M2）：全部下拉/单选，不可输入（"仅供选择，不做可编辑"）

对应 v3 方案 8.2 节：
  · 16 组固化配色单选，每项带 16×16 色块预览与说明文字
  · 框透明度 6 档，随所选预设的实测下限动态收窄（赤2 只给 ≥75%、橙2 只给 ≥90%）
  · 字体透明度 3 档；字号 12/18/22；槽尺寸 100×42 / 80×40；锚点四选
  · 内嵌实时预览（按当前选择渲染 3 个槽），配色与透明度所见即所得
  · 「应用」即时生效并落盘；「恢复默认」一键回到出厂；关闭窗口不改变任何设置
"""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget, QFormLayout, QGroupBox,
)

import config as C

ANCHOR_LABELS = {"br": "右下", "tr": "右上", "bl": "左下", "tl": "左上"}


def _swatch_icon(fg, bg, size=18):
    """左底色右字色的双色块图标"""
    pm = QPixmap(size * 2 + 2, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(bg))
    p.drawRect(0, 0, size - 2, size)
    p.setBrush(QColor(fg))
    p.drawRect(size + 2, 0, size - 2, size)
    p.end()
    return QIcon(pm)


class PreviewStrip(QWidget):
    """3 个槽的实时预览：直接复用 overlay 的绘制语义（底板/描边/截断）"""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self._samples = ["Ctrl", "退格", "上滚"]
        self.setMinimumHeight(150)

    def set_cfg(self, cfg):
        self.cfg = cfg
        self.update()

    def paintEvent(self, e):
        from PyQt6.QtGui import QFontMetrics, QPainterPath, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        cfg = self.cfg
        w, h = C.slot_px(cfg["slot_size"])
        gap = int(cfg["slot_gap_y"])
        pal = C.palette(cfg["palette"])
        fg, bg = QColor(pal[1]), QColor(pal[2])
        f = QFont("Microsoft YaHei UI")
        f.setPixelSize(int(cfg["font_size"]))
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        box_pct = int(cfg["box_opacity"])
        font_pct = int(cfg["font_opacity"])
        # 3 个槽靠左竖排，底部对齐
        x, y0 = 10, self.height() - (h * 3 + gap * 2) - 8
        for k, txt in enumerate(self._samples):
            y = y0 + k * (h + gap)
            box = QColor(bg)
            box.setAlpha(int(255 * (box_pct / 100.0)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(box)
            p.drawRoundedRect(x, y, w, h, 8, 8)
            if cfg.get("box_border", False):
                bd = QColor(fg)
                bd.setAlpha(int(255 * 0.6))
                p.setPen(QPen(bd, 1.0))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(x, y, w, h, 8, 8)
            avail = max(6, w - 16)
            shown = fm.elidedText(txt, Qt.TextElideMode.ElideRight, avail)
            tw = fm.horizontalAdvance(shown)
            tx = x + max(8, (w - tw) // 2)
            ty = y + (h + fm.ascent() - fm.descent()) // 2
            path = QPainterPath()
            path.addText(float(tx), float(ty), f, shown)
            if cfg.get("text_outline", False):
                halo = QColor("#FFFFFF") if fg.lightnessF() < 0.5 else QColor("#000000")
                p.setPen(QPen(halo, max(1.0, int(cfg["font_size"]) / 16.0),
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                              Qt.PenJoinStyle.RoundJoin))
            else:
                p.setPen(Qt.PenStyle.NoPen)
            core = QColor(fg)
            core.setAlpha(int(255 * (font_pct / 100.0)))
            p.setBrush(core)
            p.drawPath(path)
            p.setBrush(Qt.BrushStyle.NoBrush)
        # 说明文字
        p.setPen(QColor("#8fa3b8"))
        note = QFont("Microsoft YaHei UI")
        note.setPixelSize(11)
        p.setFont(note)
        p.drawText(x + w + 14, y0 + h * 2,
                   "预览（实际尺寸 {}×{}）\n配色「{}」 框 {}% 字 {}%\n描边恒 100%，空槽不画".format(
                       w, h, cfg["palette"], box_pct, font_pct))
        p.end()


class SettingsDialog(QDialog):
    """KeyMarquee 设置：全下拉单选，应用即生效"""

    def __init__(self, cfg, overlay, tray=None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.overlay = overlay
        self.tray = tray
        self.setWindowTitle("KeyMarquee 设置")
        self.setModal(False)                 # 非模态：设置时可看悬浮层实时变化
        self.setMinimumWidth(430)
        self._build_ui()
        self._load()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        grp = QGroupBox("外观")
        form = QFormLayout(grp)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(8)

        self.cmb_palette = QComboBox()
        for name, fg, bg, desc, _floor in C.PALETTES:
            self.cmb_palette.addItem(_swatch_icon(fg, bg), name)
            self.cmb_palette.setItemData(self.cmb_palette.count() - 1, desc, Qt.ItemDataRole.ToolTipRole)
        self.cmb_palette.currentTextChanged.connect(self._on_palette_changed)
        form.addRow("配色方案", self.cmb_palette)

        self.cmb_box_op = QComboBox()
        self.cmb_box_op.currentIndexChanged.connect(self._preview_refresh)
        form.addRow("框透明度", self.cmb_box_op)

        self.cmb_font_op = QComboBox()
        for lv in C.FONT_OPACITY_LEVELS:
            self.cmb_font_op.addItem("{}%".format(lv))
        self.cmb_font_op.currentIndexChanged.connect(self._preview_refresh)
        form.addRow("字透明度", self.cmb_font_op)

        self.cmb_font = QComboBox()
        for lv in C.FONT_SIZES:
            self.cmb_font.addItem("{} px".format(lv))
        self.cmb_font.currentIndexChanged.connect(self._preview_refresh)
        form.addRow("字体大小", self.cmb_font)

        self.cmb_size = QComboBox()
        for k in C.SLOT_SIZES:
            w, h = C.SLOT_SIZES[k]
            self.cmb_size.addItem("{} × {}（10 槽总高 {}px）".format(k.replace("x", " × "), w,
                             h * 10 + int(self.cfg["slot_gap_y"]) * 9))
        self.cmb_size.currentIndexChanged.connect(self._preview_refresh)
        form.addRow("悬浮框大小", self.cmb_size)

        self.cmb_anchor = QComboBox()
        for k in C.ANCHORS:
            self.cmb_anchor.addItem(ANCHOR_LABELS.get(k, k))
        self.cmb_anchor.currentIndexChanged.connect(self._preview_refresh)
        form.addRow("屏幕锚点", self.cmb_anchor)

        # 描边开关：默认关（用户反馈描边后不好看），勾选启用
        self.chk_outline = QCheckBox("文字描边（低对比配色下提高可读性）")
        self.chk_outline.setChecked(False)
        self.chk_outline.toggled.connect(self._preview_refresh)
        form.addRow("", self.chk_outline)
        self.chk_border = QCheckBox("悬浮框描边（浅色框叠浅色桌面时可辨边界）")
        self.chk_border.setChecked(False)
        self.chk_border.toggled.connect(self._preview_refresh)
        form.addRow("", self.chk_border)
        root.addWidget(grp)

        self.preview = PreviewStrip(self.cfg)
        pv = QGroupBox("预览")
        pv_l = QVBoxLayout(pv)
        pv_l.setContentsMargins(8, 8, 8, 8)
        pv_l.addWidget(self.preview)
        root.addWidget(pv)

        btns = QHBoxLayout()
        self.btn_apply = QPushButton("应用")
        self.btn_apply.clicked.connect(self._apply)
        self.btn_default = QPushButton("恢复默认")
        self.btn_default.clicked.connect(self._reset_default)
        btns.addStretch(1)
        btns.addWidget(self.btn_default)
        btns.addWidget(self.btn_apply)
        root.addLayout(btns)

        tip = QLabel("「应用」立即生效并保存；直接关闭窗口放弃本次修改。\n"
                     "配色与透明度档位按可读性实测结果锁定，赤2/橙2 档位受限。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#94a3b8;font-size:11px;")
        root.addWidget(tip)

    # ---------------- 数据装载 ----------------
    def _load(self):
        """把当前 config 装入控件（不触发应用）"""
        i = self.cmb_palette.findText(self.cfg["palette"])
        self.cmb_palette.setCurrentIndex(max(0, i))
        self._rebuild_box_opacity()
        bo = int(self.cfg["box_opacity"])
        j = -1
        for k in range(self.cmb_box_op.count()):
            if int(self.cmb_box_op.itemText(k).rstrip("%")) == bo:
                j = k
                break
        self.cmb_box_op.setCurrentIndex(max(0, j))
        self.cmb_font_op.setCurrentIndex(
            C.FONT_OPACITY_LEVELS.index(int(self.cfg["font_opacity"]))
            if int(self.cfg["font_opacity"]) in C.FONT_OPACITY_LEVELS else 2)
        self.cmb_font.setCurrentIndex(
            C.FONT_SIZES.index(int(self.cfg["font_size"]))
            if int(self.cfg["font_size"]) in C.FONT_SIZES else 1)
        keys = list(C.SLOT_SIZES.keys())
        self.cmb_size.setCurrentIndex(
            keys.index(self.cfg["slot_size"]) if self.cfg["slot_size"] in keys else 0)
        self.chk_outline.setChecked(bool(self.cfg.get("text_outline", False)))
        self.chk_border.setChecked(bool(self.cfg.get("box_border", False)))
        self.cmb_anchor.setCurrentIndex(
            C.ANCHORS.index(self.cfg["anchor"]) if self.cfg["anchor"] in C.ANCHORS else 0)
        self._preview_refresh()

    def _rebuild_box_opacity(self):
        """按当前预设的下限重建框透明度档位（动态收窄）"""
        pal = self.cmb_palette.currentText()
        allowed = C.allowed_opacities(pal)
        cur = int(self.cfg["box_opacity"])
        self.cmb_box_op.blockSignals(True)
        self.cmb_box_op.clear()
        for lv in allowed:
            self.cmb_box_op.addItem("{}%".format(lv))
        # 当前值若不在允许集合，跳到允许范围内的最近档
        if cur not in allowed:
            cur = min(allowed, key=lambda lv: abs(lv - cur))
        self.cmb_box_op.setCurrentIndex(
            [int(self.cmb_box_op.itemText(k).rstrip("%"))
             for k in range(self.cmb_box_op.count())].index(cur))
        self.cmb_box_op.blockSignals(False)

    def _on_palette_changed(self, _name):
        self._rebuild_box_opacity()
        self._preview_refresh()

    def _collect(self):
        """控件 → 一份新的配置 dict（未落盘）"""
        d = dict(self.cfg.data)
        d["palette"] = self.cmb_palette.currentText()
        d["box_opacity"] = int(self.cmb_box_op.currentText().rstrip("%"))
        d["font_opacity"] = C.FONT_OPACITY_LEVELS[self.cmb_font_op.currentIndex()]
        d["font_size"] = C.FONT_SIZES[self.cmb_font.currentIndex()]
        d["slot_size"] = list(C.SLOT_SIZES.keys())[self.cmb_size.currentIndex()]
        d["anchor"] = C.ANCHORS[self.cmb_anchor.currentIndex()]
        d["text_outline"] = self.chk_outline.isChecked()
        d["box_border"] = self.chk_border.isChecked()
        return d

    def _preview_refresh(self):
        class _V:                     # 预览用轻量只读视图
            def __init__(self, d):
                self.data = d
            def __getitem__(self, k):
                return self.data[k]
            def get(self, k, default=None):
                return self.data.get(k, default)
        self._pv = _V(self._collect())
        self.preview.set_cfg(self._pv)

    # ---------------- 动作 ----------------
    def _apply(self):
        d = self._collect()
        for k in ("palette", "box_opacity", "font_opacity", "font_size",
                  "slot_size", "anchor", "text_outline", "box_border"):
            self.cfg[k] = d[k]
        self.cfg.sanitize()
        self.cfg.save()
        if self.overlay is not None:
            self.overlay.refresh_style()      # 热生效（尺寸/锚点/颜色全部重算）
        if self.tray is not None:
            self.tray._rebuild_opacity_menu()
            self.tray.sync()
        self._load()

    def _reset_default(self):
        for k in ("palette", "box_opacity", "font_opacity", "font_size",
                  "slot_size", "anchor", "text_outline", "box_border"):
            self.cfg[k] = C.DEFAULTS[k]
        self._load()
