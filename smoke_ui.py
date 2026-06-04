"""Headless-ish smoke test: construct the frame, drive a few actions, destroy."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wx
from chapterforge.app import MainFrame

app = wx.App(False)
frame = MainFrame()

# Inject fake items to exercise list/reorder/rename logic without ffmpeg.
from chapterforge import core
frame.items = [
    core.Mp3Item("a.mp3", "Intro", 1.0, "mp3", 44100, 2, "stereo"),
    core.Mp3Item("b.mp3", "Middle", 2.0, "mp3", 44100, 2, "stereo"),
    core.Mp3Item("c.mp3", "End", 1.5, "mp3", 44100, 2, "stereo"),
]
frame._set_output_path("out.mp3")
frame._refresh_list(select=0)
assert frame.list.GetItemCount() == 3, "list not populated"

frame.list.Select(0)
frame._move(1)
assert frame.items[0].title == "Middle", "move failed"

frame.list.Select(0)
frame.title_ctrl.ChangeValue("Renamed")
class E:  # minimal fake event
    def Skip(self): pass
frame._on_apply_title(E())
assert frame.items[0].title == "Renamed", "rename failed"

frame._remove_selected()
assert len(frame.items) == 2, "remove failed"

frame.Destroy()
app.Destroy()
print("UI smoke test OK")
