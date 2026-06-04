# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ChapterForge (one-folder build).

One-folder (not one-file) is used deliberately: one-file builds extract to a
temporary directory on every launch, which is slow and can leave temp folders
behind. The one-folder output is what the Inno Setup installer packages.

Two executables share the same folder:
  * ``ChapterForge.exe``     — the windowed GUI (also routes CLI args).
  * ``chapterforge-cli.exe`` — a console build of the CLI, so terminal output
    (the chapter plan and live progress) is always visible.

ffmpeg.exe and ffprobe.exe are shipped in a ``bin`` subfolder; chapterforge.core
locates them next to the executable / inside the bundle automatically.
"""

block_cipher = None

datas = [
    ('bin/ffmpeg.exe', 'bin'),
    ('bin/ffprobe.exe', 'bin'),
    ('docs/html', 'docs/html'),
]

hiddenimports = ['wx._xml', 'wx.adv', 'wx.media']
excludes = ['tkinter', 'pytest', 'numpy', 'sympy']

gui_a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    cipher=block_cipher,
    noarchive=False,
)

cli_a = Analysis(
    ['cli_main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    cipher=block_cipher,
    noarchive=False,
)

# Share common dependencies so they are only collected once.
MERGE((gui_a, 'ChapterForge', 'ChapterForge'),
      (cli_a, 'chapterforge-cli', 'chapterforge-cli'))

gui_pyz = PYZ(gui_a.pure, gui_a.zipped_data, cipher=block_cipher)
cli_pyz = PYZ(cli_a.pure, cli_a.zipped_data, cipher=block_cipher)

gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name='ChapterForge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

cli_exe = EXE(
    cli_pyz,
    cli_a.scripts,
    [],
    exclude_binaries=True,
    name='chapterforge-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    gui_exe,
    gui_a.binaries,
    gui_a.datas,
    cli_exe,
    cli_a.binaries,
    cli_a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ChapterForge',
)
