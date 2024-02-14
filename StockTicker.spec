# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['StockTicker.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('res/Add.png', 'res'),
        ('res/Down_Arrow.png', 'res'),
        ('res/edit.png', 'res'),
        ('res/exit.png', 'res'),
        ('res/font.png', 'res'),
        ('res/StockTickerIcon.ico', 'res'),
        ('res/StockTickerIcon.png', 'res'),
        ('res/Up_Arrow.png', 'res')
        ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StockTicker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StockTicker',
)
