#!/usr/bin/env python3
"""ChapterForge entry point.

* With command-line arguments -> run the terminal CLI (prints progress).
* With no arguments           -> launch the graphical app.

On Windows the GUI build is a windowed executable with no console. When it is
started from a terminal *with* arguments we best-effort attach to the parent
console so CLI output is visible.
"""

import sys


def _attach_parent_console_windows() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ATTACH_PARENT_PROCESS = -1
        if ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            # Re-bind Python's standard streams to the now-attached console.
            try:
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                sys.stdin = open("CONIN$", "r", encoding="utf-8")
            except OSError:
                pass
    except Exception:
        pass


def main() -> None:
    if len(sys.argv) > 1:
        _attach_parent_console_windows()
        from chapterforge.cli import run
        sys.exit(run())
    from chapterforge.app import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
