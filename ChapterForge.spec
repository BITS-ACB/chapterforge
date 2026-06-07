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

libmpv-2.dll (the in-app player's playback engine, see THIRD_PARTY.md for its
LGPL/GPL redistribution notice) is bundled at ``bin/mpv/libmpv-2.dll``;
chapterforge.audio_engine looks for it at that path next to the executable.
"""

import os

block_cipher = None

# chapterforge.audio_engine resolves this relative to the frozen exe dir, so
# it must land at exactly this path inside the collected build.
_libmpv_dll = os.path.join(SPECPATH, 'bin', 'mpv', 'libmpv-2.dll')
gui_binaries = [(_libmpv_dll, 'bin/mpv')]

datas = [
    # FFmpeg is downloaded at runtime if needed - not bundled to keep size small
    # Docs are available online - not bundled to reduce installer size
]

hiddenimports = ['wx._xml', 'wx.adv', 'wx.media']
excludes = ['tkinter', 'pytest', 'numpy', 'sympy']

gui_a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=gui_binaries,
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
