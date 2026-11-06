# -*- mode: python ; coding: utf-8 -*-
# KeyMarquee 构建规格（单文件 EXE，v0 发布版）
# 用法: .venv\Scripts\python.exe -m PyInstaller build.spec
"""
设计要点
- 单文件(--onefile) + 无控制台(--noconsole)：绿色免安装，托盘常驻。
- icon.ico：桌面/任务栏/文件图标，青底 K 品牌标识（Pillow 生成）。
- 版本信息(file_version_info)：Windows 资源管理器右键“属性→详细信息”可见。
- hiddenimports：pynput 在 Windows 上动态加载 _win32 后端，PyInstaller 静态分析抓不到，
  显式声明避免运行时 ImportError。
- excludes：剔除本项目未使用的重型子模块（PyQt6 网络/QML/多媒体/WebEngine 等、
  PyInstaller 测试工具），显著缩小体积。
"""
APP_NAME = "KeyMarquee"
APP_VERSION = "0.1.0.0"
COMPANY = "KeyMarquee"
DESCRIPTION = "KeyMarquee · 按键跑马灯与按压统计（Windows）"

# ---- Windows 版本信息资源（独立文件，EXE.version 接受文件路径） ----
FILE_VERSION_INFO = "version_info.txt"

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        "pynput.keyboard._base",
        "pynput.mouse._base",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt6.QtNetwork",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineQuick",
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebKit",
        "PyQt6.QtDesigner",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtSql",
        "PyQt6.QtXml",
        "PyInstaller.utils.tests",
        "unittest",
        "doctest",
        "pydoc",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
    version=FILE_VERSION_INFO,
)
