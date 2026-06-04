"""Per-user 'run at sign-in' registration (Windows).

Writes an ``HKEY_CURRENT_USER`` Run entry so the background watcher can start
when the current user signs in. This is the correct per-user mechanism (the
installer deliberately does not touch per-user areas, which avoids the
admin-install / per-user mismatch warning).

All functions are best-effort and degrade silently on non-Windows or when the
registry is unavailable.
"""

from __future__ import annotations

import os
import sys

from . import __app_name__

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = f"{__app_name__}Watcher"


def _launch_command() -> str:
    """The command that starts the tray watcher."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --watch'
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "main.py")
    return f'"{sys.executable}" "{script}" --watch'


def is_supported() -> bool:
    return sys.platform.startswith("win")


def is_enabled() -> bool:
    if not is_supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enable: bool) -> bool:
    """Enable/disable run-at-sign-in. Returns True on success."""
    if not is_supported():
        return False
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enable:
                winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ,
                                  _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, _VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
