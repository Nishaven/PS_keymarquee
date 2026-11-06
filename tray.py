# -*- coding: utf-8 -*-
"""tray.py — 系统托盘图标与菜单

v2 变更：
  · 透明度子菜单从旧的 25/50/75/100 改为实测过的 6 档 20/40/60/75/90/100，
    并按当前配色预设的下限动态收窄（赤2 只给 ≥75、橙2 只给 ≥90）
  · 新增「显示自检」：投放一条测试槽并检查窗口可见性与自身渲染像素，
    把结果用气泡告知 —— 现场不必再靠"我看不见"来回描述现象
  · 完整的外观设置窗口在 M2 落地，这里先保证配置项与新 config 键一致、不炸
"""
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import (QAction, QActionGroup, QColor, QFont, QIcon,
                         QPainter, QPixmap)
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import config as C
from settings import SettingsDialog


def build_icon():
    """运行时绘制托盘图标（青底圆角方块 + K），免外部资源文件"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#22d3ee"))
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("#062a33"))
    f = QFont("Segoe UI", 30)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "K")
    p.end()
    return QIcon(pm)


class TrayController:
    def __init__(self, cfg, overlay, monitor, dbg=None):
        self.cfg = cfg
        self.overlay = overlay
        self.monitor = monitor
        self.dbg = dbg or (lambda m: None)
        self._settings_dlg = None
        self.tray = QSystemTrayIcon(build_icon())
        self.tray.setToolTip("KeyMarquee 按键跑马灯\n双击图标：切换锁定/移动模式")
        self.menu = QMenu()

        # ---- 移动 / 锁定（互斥）----
        self.act_lock = QAction("锁定", self.menu, checkable=True)
        self.act_move = QAction("移动模式", self.menu, checkable=True)
        group = QActionGroup(self.menu)
        group.addAction(self.act_lock)
        group.addAction(self.act_move)
        group.setExclusive(True)
        self.act_lock.triggered.connect(lambda checked: self._set_locked(checked))
        self.act_move.triggered.connect(
            lambda checked: self._set_locked(not checked))

        # ---- 框透明度（6 档，按预设下限动态收窄）----
        self._op_actions = []
        self.op_menu = self.menu.addMenu("框透明度")

        # ---- 暂停 / 测试 / 自检 ----
        self.act_pause = QAction("暂停显示", self.menu, checkable=True)
        self.act_pause.toggled.connect(self._set_paused)
        act_test = QAction("显示测试（投放 3 条）", self.menu)
        act_test.triggered.connect(self._self_test)
        act_check = QAction("显示自检（看得见吗）", self.menu)
        act_check.triggered.connect(self._visibility_check)

        # ---- 诊断窗口 / 强制置顶 ----
        self.act_monitor = QAction("监听诊断窗口", self.menu, checkable=True)
        self.act_monitor.triggered.connect(self._toggle_monitor)
        self.act_topmost = QAction("诊断窗强制置顶", self.menu, checkable=True)
        self.act_topmost.triggered.connect(self._toggle_topmost)

        act_clear = QAction("清空悬浮层", self.menu)
        act_clear.triggered.connect(lambda: self.overlay.clear_all())

        # ---- 设置窗口（M2）----
        act_settings = QAction("设置…", self.menu)
        act_settings.triggered.connect(self._open_settings)

        act_quit = QAction("退出", self.menu)
        act_quit.triggered.connect(self._quit)

        for a in (self.act_lock, self.act_move, self.act_pause):
            self.menu.addAction(a)
        self.menu.addAction(act_settings)
        self.menu.addAction(act_test)
        self.menu.addAction(act_check)
        self.menu.addSeparator()
        self.menu.addAction(self.act_monitor)
        self.menu.addAction(self.act_topmost)
        self.menu.addAction(act_clear)
        self.menu.addSeparator()
        self.menu.addAction(act_quit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self._rebuild_opacity_menu()

    # ---------------- 展示 ----------------
    def show(self):
        self.sync()
        self.tray.show()
        # 气泡通知默认关（卡顿嫌疑之一：全屏置顶气泡会强制 DWM 重排任务栏区域，
        # 低配机上造成全屏卡顿）。需要时托盘菜单可手动打开。
        if self.cfg.get("tray_notice", False):
            self.tray.showMessage(
                "KeyMarquee 已启动",
                "当前：{} · 配色「{}」 · 框透明度 {}%".format(
                    "锁定（鼠标穿透）" if self.cfg["locked"] else "移动模式",
                    self.cfg["palette"], self.cfg["box_opacity"]),
                QSystemTrayIcon.MessageIcon.Information, 3000)

    def sync(self):
        self.act_lock.setChecked(bool(self.cfg["locked"]))
        self.act_move.setChecked(not bool(self.cfg["locked"]))
        self.act_pause.setChecked(bool(self.cfg["paused"]))
        self.act_monitor.setChecked(self.monitor.isVisible())
        self.act_topmost.setChecked(bool(self.cfg["monitor_topmost"]))
        for a in self._op_actions:
            a.setChecked(int(a.text().rstrip("%")) == int(self.cfg["box_opacity"]))

    def _rebuild_opacity_menu(self):
        self.op_menu.clear()
        self._op_actions = []
        for lv in C.allowed_opacities(self.cfg["palette"]):
            a = QAction("{}%".format(lv), self.op_menu, checkable=True)
            a.triggered.connect(
                lambda _checked=False, v=lv: self._set_box_opacity(v))
            self.op_menu.addAction(a)
            self._op_actions.append(a)
        self.sync()

    # ---------------- 动作 ----------------
    def _set_locked(self, locked):
        self.overlay.set_locked(locked)
        self.cfg.save()
        self.sync()

    def _set_box_opacity(self, pct):
        self.cfg["box_opacity"] = int(pct)
        self.cfg.save()
        self.overlay.refresh_style()
        self.sync()
        self.dbg("box_opacity -> {}".format(pct))

    def _set_paused(self, on):
        self.cfg["paused"] = bool(on)
        self.cfg.save()

    def _open_settings(self):
        """打开设置窗口（非模态：改外观可实时看到悬浮层变化）"""
        if self._settings_dlg is None:
            self._settings_dlg = SettingsDialog(self.cfg, self.overlay, self)
        else:
            self._settings_dlg._load()      # 重新拉取当前配置（可能被外部改过）
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def _toggle_monitor(self, on):
        if on:
            self.monitor.show()
        else:
            self.monitor.hide()
        self.cfg["monitor_visible"] = bool(on)
        self.cfg.save()
        self.sync()

    def _toggle_topmost(self, on):
        self.monitor.set_topmost(bool(on))
        self.sync()

    def _self_test(self):
        """现场自检：依次投放 3 条示例（含中文长标签，便于目视截断效果）"""
        ov = self.overlay
        ov.push("左键", 1)
        QTimer.singleShot(300, lambda: ov.push("Ctrl", 1))
        QTimer.singleShot(600, lambda: ov.push("退格", 1))

    def _visibility_check(self):
        ok, painted = self.overlay.selfcheck()
        if not ok:
            self.overlay.push("自检 SELF", 1)
            ok, painted = self.overlay.selfcheck()
        msg = ("看得见：已绘制 {} 像素".format(painted) if ok
               else "看不见：窗口未显示或绘制为空，请检查杀软/配色透明度")
        self.dbg("visibility_check ok={} painted={}".format(ok, painted))
        self.tray.showMessage("显示自检", msg,
                              QSystemTrayIcon.MessageIcon.Information, 4000)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._set_locked(not self.cfg["locked"])

    def _quit(self):
        from main import force_exit_later
        self.cfg.save()                 # 数据先同步落盘
        # 已实证缺陷（取证/hang_hunter*.txt）：Qt 的退出标志可被嵌套事件循环
        # 反复消费，连补多次 app.exit() 都不保证 exec() 返回 → 进程关不掉。
        # 确定性方案：数据已保存，起后台线程 1.5s 后 os._exit(0) 兜底；
        # 正常退出时进程先行消失，该线程无感消亡。
        force_exit_later(1.5, self.dbg)
        QApplication.instance().quit()
