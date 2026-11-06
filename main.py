# -*- coding: utf-8 -*-
"""main.py — KeyMarquee 按键可视化跑马灯 · 入口（M1 重构版）

装配：配置 → 信号桥 → 监听线程 → 事件解析 → 覆盖层（10 固定槽位）→ 诊断 → 托盘

v2 变更：
  · S8 装配顺序：先 set_locked 配置窗口标志，再唯一一次 show()。
    原版是 show() 之后立刻 set_locked(True)，而 Qt 改窗口标志会先隐藏窗口，
    叠加 overlay.set_locked 里「改标志之后才判 isVisible」的写法，
    导致默认 locked=true 时覆盖层被自己隐藏且永不恢复 —— 桌面看不见的真因。
  · 事件管线加 try/except：槽函数里的未捕获异常在 PyQt6 中会触发 qFatal()
    → 无控制台的单文件 exe 表现为"没有报错、直接消失"。现在改为记录堆栈并继续跑。
  · listener 接管 500ms 按压规则；overlay 接管 10 槽位与心跳。
"""
import datetime
import os
import sys
import threading
import traceback

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from config import APP_VERSION, Config
from formatter import EventParser
from keystats import KeyStats
from listener import EventBridge, InputListener
from monitor import MonitorWindow
from overlay import OverlayWindow
from tray import TrayController


def _make_debug_logger(cfg):
    """返回 debug(msg) 回调：仅当 cfg['debug_log'] 为真时写 keymarquee_debug.log。
    性能要点（用户报"操作界面卡顿"后改）：
      · 句柄常驻（一次 open，退出时关闭）——不再每行 open/append/close，
        否则高频打字时每键 3 次文件开关，叠加杀软实时扫描会拖慢整个系统；
      · 事件级日志（event/emit/slot）只在需要排查"没捕获/没显示"时手动打开；
      · 默认关闭（config DEFAULTS debug_log=False）。"""
    if not cfg.data.get("debug_log", False):
        return lambda msg: None
    base = os.path.dirname(
        sys.executable if getattr(sys, "frozen", False) else __file__)
    path = os.path.join(base, "keymarquee_debug.log")
    try:
        fh = open(path, "a", encoding="utf-8", buffering=1)   # 行缓冲
    except OSError:
        return lambda msg: None

    def dbg(msg):
        try:
            fh.write(datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
                     + " " + msg + "\n")
        except (OSError, ValueError):        # 磁盘异常/句柄已关：静默降级
            pass
    dbg._fh = fh                              # 供退出路径统一关闭
    return dbg


def _safe_slot(fn, dbg):
    """槽函数兜底：任何一次投递失败都不允许带走整个进程"""
    def wrapped(ev):
        try:
            fn(ev)
        except Exception:
            dbg("SLOT-ERR {} {}".format(
                getattr(fn, "__name__", "?"), traceback.format_exc()))
    wrapped.__name__ = getattr(fn, "__name__", "slot")
    return wrapped


def force_exit_later(seconds, dbg):
    """确定性退出兜底（已实证：Qt 退出标志可被嵌套事件循环反复消费，
    连续多次 app.exit() 也不保证 exec() 返回 —— 取证/hang_hunter4/6.txt）。
    调用前提：需要落盘的数据（config 等）已同步保存完毕。
    正常退出时进程先行消失，本线程随之消亡，无副作用。"""
    def _killer():
        threading.Event().wait(seconds)
        os._exit(0)
    t = threading.Thread(target=_killer, daemon=True)
    t.start()
    dbg("exit-guard armed (+{:.1f}s)".format(seconds))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("KeyMarquee")
    app.setQuitOnLastWindowClosed(False)        # 关闭窗口不退出，托盘常驻

    cfg = Config()
    dbg = _make_debug_logger(cfg)
    dbg("=== KeyMarquee 启动 (pid={} ver={}) ===".format(os.getpid(), APP_VERSION))

    bridge = EventBridge()                      # pynput 线程 → GUI 线程 信号桥
    parser = EventParser(cfg)                   # 键名映射 / 修饰键拆槽 / 滚轮合并
    stats = KeyStats()                          # 按键计数器（软件启动→当前的累计）
    overlay = OverlayWindow(cfg, dbg)           # 10 固定槽位覆盖层
    listener = InputListener(bridge, cfg)       # 500ms 按压规则在最上游
    listener.start()
    monitor = MonitorWindow(cfg, listener, stats)   # 监听诊断窗口（含按键统计页）
    tray = TrayController(cfg, overlay, monitor, dbg)

    parser.sink = overlay.push                  # 解析结果 → 覆盖层
    parser.debug = dbg
    overlay.tick_hook = listener.sweep_stuck    # 丢失抬起事件的兜底结算

    def on_event(ev):
        dbg("event: {}".format(ev))
        if cfg["paused"]:                       # 隐私总开关：暂停时不显示
            return
        parser.feed(ev)

    bridge.got.connect(_safe_slot(on_event, dbg))
    bridge.got.connect(_safe_slot(monitor.feed, dbg))

    dbg("listener started (kb_alive={}, ms_alive={})".format(
        listener.is_alive_kb(), listener.is_alive_ms()))
    # 退出路径分段打点：定位"到点不退"到底卡在哪一段
    app.aboutToQuit.connect(lambda: dbg("aq: begin"))
    app.aboutToQuit.connect(listener.stop)
    app.aboutToQuit.connect(lambda: dbg("aq: listener.stop done"))
    app.aboutToQuit.connect(cfg.save)
    app.aboutToQuit.connect(lambda: dbg("aq: cfg.save done"))
    # 调试日志句柄统一在退出时关闭（dbg 为空函数时无属性，getattr 兜底）
    app.aboutToQuit.connect(
        lambda: getattr(dbg, "_fh", None) and getattr(dbg, "_fh").close())

    overlay.set_locked(cfg["locked"])           # ① 先配置窗口标志
    overlay.show()                              # ② 再唯一一次 show（S8）
    dbg("overlay shown visible={} geo={} mode={} palette={}".format(
        overlay.isVisible(), overlay.frameGeometry().getRect(),
        "solid" if overlay._solid else "translucent", cfg["palette"]))
    if cfg["monitor_visible"]:
        monitor.show()
    tray.show()
    # CI/现场自检钩子：正常双击运行时这两个环境变量不存在，行为完全不变。
    # KEYCAST_SMOKE_MS=9000 → 9 秒后自动退出（供冒烟测试验证启动→运行→干净退出全链路）
    # KEYCAST_SMOKE_PUSH=1  → 中途投放一条测试槽（供外部像素取证看到内容）
    smoke_ms = os.environ.get("KEYCAST_SMOKE_MS", "")
    if smoke_ms.strip().isdigit() and int(smoke_ms) >= 1000:
        ms = int(smoke_ms)
        if os.environ.get("KEYCAST_SMOKE_PUSH"):
            QTimer.singleShot(min(4500, ms // 2),
                              lambda: overlay.push("自检", 1))

        def _smoke_quit():
            cfg.save()                   # 数据先落盘
            force_exit_later(1.5, dbg)   # 确定性退出兜底
            dbg("smoke-quit: timer fired, calling app.quit()")
            app.quit()
            dbg("smoke-quit: app.quit() returned")
        QTimer.singleShot(ms, _smoke_quit)
        QTimer.singleShot(ms + 1500,
                          lambda: dbg("smoke-quit: loop STILL ALIVE at +1.5s"))
        dbg("smoke mode: quit at {}ms".format(ms))
        # 注意：不再有每秒 hb 心跳 —— 它是排查挂起时的调试残留，
        # 每秒唤醒主线程 + 一次文件 IO，在低配机/杀软实时扫描下会造成卡顿
        import faulthandler
        faulthandler.dump_traceback_later((ms + 5000) / 1000.0, exit=True)
    rc = app.exec()
    dbg("exec returned rc={}".format(rc))
    sys.exit(rc)


if __name__ == "__main__":
    main()
