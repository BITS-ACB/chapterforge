"""Allow running ChapterForge as a module: python -m chapterforge"""

import sys

# Import and run the main entry point from root main.py
# This allows both 'python main.py' and 'python -m chapterforge' to work

def _attach_parent_console_windows() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ATTACH_PARENT_PROCESS = -1
        if ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            try:
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
                sys.stdin = open("CONIN$", "r", encoding="utf-8")
            except OSError:
                pass
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1:
        _attach_parent_console_windows()
        from chapterforge.cli import run
        sys.exit(run())
    from chapterforge.app import main as gui_main
    gui_main()
