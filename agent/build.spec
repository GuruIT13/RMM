# PyInstaller spec — build with: pyinstaller build.spec
# Output: dist/rmm_agent.exe

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Windows / COM
        'wmi',
        'win32api',
        'win32con',
        'win32service',
        'win32security',
        'winreg',
        'ctypes',
        'ctypes.wintypes',
        # Tray
        'pystray._win32',
        'PIL._tkinter_finder',
        'PIL.Image',
        # Supabase / networking
        'supabase',
        'postgrest',
        'realtime',
        'realtime._async.client',
        'realtime._async.channel',
        'gotrue',
        'httpx',
        'httpcore',
        'websockets',
        'websockets.legacy',
        'websockets.legacy.client',
        'h2',
        'hpack',
        # stdlib that PyInstaller sometimes misses
        'asyncio',
        'logging.handlers',
        'threading',
        'subprocess',
        'json',
        'uuid',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='rmm_agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
