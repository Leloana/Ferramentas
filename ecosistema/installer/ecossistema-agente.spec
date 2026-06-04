# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['..\\agente.py'],
    pathex=['..'],
    binaries=[],
    datas=[],
    # painel.py/pareamento.py sao importados sob demanda (import painel/pareamento),
    # entao o PyInstaller nao os ve pela analise estatica -> declarados aqui.
    # tkinter/PIL/qrcode/pystray idem (o painel so importa quando em --panel).
    hiddenimports=[
        'painel',
        'pareamento',
        'tkinter',
        'tkinter.ttk',
        'PIL._tkinter_finder',
        'qrcode',
        'pystray',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ecossistema-agente',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='ecossistema-agente',
)
