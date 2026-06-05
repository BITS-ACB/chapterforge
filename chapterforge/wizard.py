"""Startup wizard for ChapterForge.

A guided, accessible, multi-step dialog shown on first launch and available
at any time from Help -> Setup Wizard. Each step explains one aspect of the
app and, where relevant, lets the user configure the matching setting right
there. Every step can be skipped; all choices can be revisited in Settings.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import wx

from . import a11y
from . import core
from . import settings as settings_mod


# ---------------------------------------------------------------------------
# Internal step descriptor
# ---------------------------------------------------------------------------

class _Step:
    """One page in the wizard."""

    def __init__(self, title: str, heading: str, body: str,
                 make_setting=None):
        # title   - short name used in the dialog title bar
        # heading - large text shown at the top of the content panel
        # body    - explanatory prose (multi-line, screen-reader navigable)
        # make_setting(panel) -> (wx.Sizer, wx.Window, apply_fn) or None
        self.title = title
        self.heading = heading
        self.body = body
        self.make_setting = make_setting


# ---------------------------------------------------------------------------
# Main wizard dialog
# ---------------------------------------------------------------------------

class StartupWizard(wx.Dialog):
    """Multi-step guided setup wizard."""

    def __init__(self, parent, settings: dict,
                 on_open_folder: Optional[Callable] = None):
        super().__init__(
            parent,
            title="ChapterForge Setup Wizard",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.settings = settings
        self._on_open_folder = on_open_folder
        self._step_index = 0
        self._setting_apply: Optional[Callable] = None
        self._steps: List[_Step] = []

        self._define_steps()
        self._build_chrome()
        self._go_to(0)
        self.SetMinSize((620, 500))
        self.SetSize((720, 580))
        self.CentreOnParent()

    # ------------------------------------------------------------------
    # Step definitions
    # ------------------------------------------------------------------

    def _define_steps(self):
        self._steps = [

            _Step(
                title="Welcome",
                heading="Welcome to ChapterForge!",
                body=(
                    "ChapterForge turns a folder of MP3 files into a single, "
                    "professionally chaptered audiobook.\n\n"
                    "Each MP3 becomes one named chapter, with its own title "
                    "and start time embedded right in the file. The finished "
                    "audiobook plays in Overcast, Pocket Casts, AntennaPod, "
                    "Apple Books, and most other podcast and audiobook apps "
                    "without any extra steps.\n\n"
                    "This short wizard walks you through the key choices before "
                    "you build your first project. Each step takes about "
                    "30 seconds to read. You can skip any step at any time, "
                    "and all of these preferences can be changed later in "
                    "the Settings dialog."
                ),
            ),

            _Step(
                title="How It Works",
                heading="The Simple Two-Step Workflow",
                body=(
                    "ChapterForge keeps things clear with two pages:\n\n"

                    "Step 1 - Chapters\n"
                    "Open a folder of MP3 files. ChapterForge lists them in "
                    "natural order - so 'Chapter 2' always comes before "
                    "'Chapter 10'. You can rename any chapter, reorder them "
                    "with Alt+Up and Alt+Down, or remove chapters you do not "
                    "need. This is where you build your table of contents.\n\n"

                    "Step 2 - Tags and Build\n"
                    "Set the audiobook title, author, and other details. "
                    "Choose where to save the finished file, then click Build. "
                    "ChapterForge stitches the audio together, writes the "
                    "chapter markers, and saves a human-readable chapter "
                    "report alongside your master file.\n\n"

                    "Use Ctrl+1 and Ctrl+2 to jump between the two steps "
                    "from anywhere in the app."
                ),
            ),

            _Step(
                title="Opening Files",
                heading="Opening Your MP3 Files",
                body=(
                    "Click 'Choose Your MP3 Folder' on the main screen, or "
                    "use File menu, then Open Folder (Ctrl+Shift+O).\n\n"
                    "ChapterForge scans the folder and lists every MP3 it "
                    "finds, sorted in natural order. If a previously built "
                    "master file exists in the same folder, it is skipped "
                    "automatically so you never accidentally re-combine a "
                    "finished audiobook.\n\n"
                    "You can also drag a .cfjob saved-setup file onto the "
                    "app to restore a previous project instantly, or use "
                    "File menu, Open Recent to jump back to a folder you "
                    "used before."
                ),
            ),

            _Step(
                title="Chapter Titles",
                heading="How Chapters Get Their Names",
                body=(
                    "By default each chapter takes its title from the MP3 "
                    "file name, with the extension stripped and any leading "
                    "track numbers removed automatically.\n\n"
                    "For example, a file named '03 - The Journey Begins.mp3' "
                    "becomes a chapter titled 'The Journey Begins'. That means "
                    "you can get a great chapter list straight away just from "
                    "well-named files.\n\n"
                    "If your MP3 files already have title tags embedded inside "
                    "them, you can read titles from those tags instead. Choose "
                    "whichever source matches your recording workflow.\n\n"
                    "You can also rename any individual chapter by selecting "
                    "it and typing in the title field, or pressing F2 to open "
                    "the full chapter editor."
                ),
                make_setting=self._make_title_source,
            ),

            _Step(
                title="Output Format",
                heading="Choosing Your Output Format",
                body=(
                    "ChapterForge can produce two types of chaptered audiobook:\n\n"

                    "MP3 with embedded chapters\n"
                    "Works in almost every podcast and audiobook app. This is "
                    "the safe, universal choice. If you are unsure, pick MP3.\n\n"

                    "M4B Audiobook\n"
                    "Apple's audiobook format. Required for Apple Books. Supported "
                    "by most modern podcast apps. Slightly smaller files than "
                    "MP3 at the same quality level.\n\n"

                    "You can change this at any time in Settings, or on the "
                    "main screen before building each project."
                ),
                make_setting=self._make_output_format,
            ),

            _Step(
                title="Audio Quality",
                heading="Choosing Audio Quality",
                body=(
                    "When ChapterForge re-encodes your audio - because the "
                    "source files have mixed formats or quality levels - it "
                    "uses the bitrate you choose here.\n\n"
                    "192k gives excellent quality for spoken word. It is the "
                    "recommended setting for most audiobooks and the best "
                    "balance of quality and file size for speech.\n\n"
                    "Higher bitrates produce larger files with little "
                    "improvement you would notice in speech recordings.\n\n"
                    "If all your source files already share the same format "
                    "and quality, ChapterForge copies them without re-encoding "
                    "and this setting has no effect on those files."
                ),
                make_setting=self._make_bitrate,
            ),

            _Step(
                title="Podcasting 2.0",
                heading="Podcasting 2.0 Chapter Files",
                body=(
                    "Podcasting 2.0 is a set of open podcast standards that "
                    "add rich features to audio content. One feature is a "
                    "separate chapters file saved alongside your audiobook.\n\n"
                    "This chapters file, ending in .chapters.json, lists each "
                    "chapter with its start time, title, and optional link URL "
                    "or per-chapter cover image. Apps that support "
                    "Podcasting 2.0, such as Podverse and Castamatic, use this "
                    "file to display chapter titles and images as the audio "
                    "plays.\n\n"
                    "For most listeners this file is not required. Enable it "
                    "if you publish via a Podcasting 2.0 host, if your "
                    "listeners use a Podcasting 2.0 app, or if you want to "
                    "set per-chapter cover images or link URLs.\n\n"
                    "You can set a link URL and image for each chapter "
                    "individually using the Edit Chapter Details dialog (F2)."
                ),
                make_setting=self._make_write_pod2,
            ),

            _Step(
                title="Cover Art",
                heading="Automatic Cover Art",
                body=(
                    "ChapterForge can automatically find a cover image in your "
                    "source folder and embed it in the finished audiobook as "
                    "album art that appears in your podcast or audiobook app.\n\n"
                    "It looks for images named cover.jpg, folder.jpg, "
                    "cover.png, and similar common names. If it finds one, "
                    "it shows a preview on the Tags page before you build.\n\n"
                    "You can always add, replace, or remove a cover image "
                    "manually on the Tags page, regardless of this setting. "
                    "Supported formats are JPEG and PNG."
                ),
                make_setting=self._make_auto_cover,
            ),

            _Step(
                title="Keyboard and Screen Reader",
                heading="Full Keyboard and Screen Reader Support",
                body=(
                    "ChapterForge is built for complete keyboard and screen "
                    "reader use with NVDA, JAWS, and Narrator.\n\n"
                    "Key shortcuts:\n"
                    "  Ctrl+Shift+O   Open a folder of MP3 files\n"
                    "  Ctrl+B         Build the audiobook\n"
                    "  Ctrl+1         Go to the chapter list (Step 1)\n"
                    "  Ctrl+2         Go to Tags and Build (Step 2)\n"
                    "  Alt+Up         Move selected chapter up\n"
                    "  Alt+Down       Move selected chapter down\n"
                    "  F2             Edit the selected chapter's details\n"
                    "  Delete         Remove or merge a chapter\n"
                    "  Ctrl+,         Open Settings\n"
                    "  Ctrl+Shift+P   Command Palette - search all commands\n"
                    "  F1             Open the User Guide in your browser\n"
                    "  Ctrl+/         Open keyboard shortcuts in your browser\n\n"
                    "Every control has a descriptive accessible name. "
                    "Build progress and all state changes are announced "
                    "automatically through your screen reader."
                ),
            ),

            _Step(
                title="All Set!",
                heading="You Are Ready to Build!",
                body=(
                    "Your preferences are saved. Here is a quick recap of "
                    "your choices:\n\n"
                    "{summary}\n\n"
                    "You can change any of these at any time in Settings "
                    "(Ctrl+comma, or the Tools menu).\n\n"
                    "To get started, click 'Open a Folder of MP3 Files' below. "
                    "You can also close this wizard and use the main window "
                    "whenever you are ready.\n\n"
                    "For help at any time: press F1 for the User Guide, "
                    "or Ctrl+Shift+P to search all commands by name."
                ),
            ),
        ]

    def _summary_text(self) -> str:
        s = self.settings
        fmt = ("MP3 with embedded chapters"
               if s.get("output_format", "mp3") == "mp3"
               else "M4B audiobook")
        src = ("File name" if s.get("title_source", "filename") ==
               core.TITLE_SOURCE_FILENAME else "Embedded tag")
        bits = s.get("bitrate", "192k")
        pod2 = "On" if s.get("write_pod2", False) else "Off"
        cover = "On" if s.get("auto_cover", True) else "Off"
        return (
            f"  Output format:      {fmt}\n"
            f"  Chapter titles:     {src}\n"
            f"  Build quality:      {bits}\n"
            f"  Podcasting 2.0:     {pod2}\n"
            f"  Auto cover art:     {cover}"
        )

    # ------------------------------------------------------------------
    # Setting control factories
    # ------------------------------------------------------------------

    def _make_title_source(self, panel):
        box = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(panel, label="Chapter title source:")
        box.Add(lbl, 0, wx.BOTTOM, 4)
        ctrl = wx.Choice(panel, choices=[
            "File name - strip numbers, use the file name (recommended)",
            "Embedded tag - read the title stored inside each MP3"])
        ctrl.SetName("Chapter title source - file name or embedded ID3 tag")
        ctrl.SetSelection(
            1 if self.settings.get("title_source") == core.TITLE_SOURCE_EMBEDDED
            else 0)
        box.Add(ctrl, 0, wx.EXPAND)

        def apply_fn():
            self.settings["title_source"] = (
                core.TITLE_SOURCE_EMBEDDED if ctrl.GetSelection() == 1
                else core.TITLE_SOURCE_FILENAME)
        return box, ctrl, apply_fn

    def _make_output_format(self, panel):
        box = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(panel, label="Output format:")
        box.Add(lbl, 0, wx.BOTTOM, 4)
        ctrl = wx.Choice(panel, choices=[
            "MP3 - universal, works in every app (recommended)",
            "M4B - Apple audiobook format"])
        ctrl.SetName("Output format - MP3 or M4B audiobook")
        ctrl.SetSelection(
            1 if self.settings.get("output_format") == "m4b" else 0)
        box.Add(ctrl, 0, wx.EXPAND)

        def apply_fn():
            self.settings["output_format"] = (
                "m4b" if ctrl.GetSelection() == 1 else "mp3")
        return box, ctrl, apply_fn

    def _make_bitrate(self, panel):
        box = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(panel, label="Build quality (bitrate):")
        box.Add(lbl, 0, wx.BOTTOM, 4)
        choices = [
            "128k - smaller file, good for speech",
            "160k - good quality",
            "192k - excellent for audiobooks (recommended)",
            "256k - very high quality",
            "320k - maximum quality, largest file",
        ]
        ctrl = wx.Choice(panel, choices=choices)
        ctrl.SetName("Build quality - audio bitrate for re-encoded files")
        _idx = {"128k": 0, "160k": 1, "192k": 2, "256k": 3, "320k": 4}
        ctrl.SetSelection(_idx.get(self.settings.get("bitrate", "192k"), 2))
        box.Add(ctrl, 0, wx.EXPAND)

        def apply_fn():
            vals = ["128k", "160k", "192k", "256k", "320k"]
            self.settings["bitrate"] = vals[max(0, min(4, ctrl.GetSelection()))]
        return box, ctrl, apply_fn

    def _make_write_pod2(self, panel):
        box = wx.BoxSizer(wx.VERTICAL)
        ctrl = wx.CheckBox(
            panel,
            label="Write a Podcasting 2.0 chapters file alongside each master")
        ctrl.SetName(
            "Write Podcasting 2.0 chapters JSON sidecar file")
        ctrl.SetValue(bool(self.settings.get("write_pod2", False)))
        box.Add(ctrl, 0)

        def apply_fn():
            self.settings["write_pod2"] = ctrl.GetValue()
        return box, ctrl, apply_fn

    def _make_auto_cover(self, panel):
        box = wx.BoxSizer(wx.VERTICAL)
        ctrl = wx.CheckBox(
            panel,
            label="Auto-detect and use a cover image from the source folder (recommended)")
        ctrl.SetName(
            "Automatically detect and use a cover image from the source folder")
        ctrl.SetValue(bool(self.settings.get("auto_cover", True)))
        box.Add(ctrl, 0)

        def apply_fn():
            self.settings["auto_cover"] = ctrl.GetValue()
        return box, ctrl, apply_fn

    # ------------------------------------------------------------------
    # Chrome construction (header, content area, footer - built once)
    # ------------------------------------------------------------------

    def _build_chrome(self):
        outer = wx.BoxSizer(wx.VERTICAL)

        # ── Coloured header banner ────────────────────────────────────
        hdr = wx.Panel(self)
        accent = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        hdr.SetBackgroundColour(accent)
        hdr_sz = wx.BoxSizer(wx.VERTICAL)

        self._hdr_heading = wx.StaticText(hdr, label="")
        self._hdr_heading.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT))
        hf = self._hdr_heading.GetFont()
        hf.SetPointSize(hf.GetPointSize() + 5)
        hf.MakeBold()
        self._hdr_heading.SetFont(hf)
        hdr_sz.Add(self._hdr_heading, 0, wx.LEFT | wx.TOP | wx.RIGHT, 16)

        self._hdr_step = wx.StaticText(hdr, label="")
        self._hdr_step.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT))
        hdr_sz.Add(self._hdr_step, 0, wx.LEFT | wx.BOTTOM, 16)

        hdr.SetSizer(hdr_sz)
        outer.Add(hdr, 0, wx.EXPAND)

        # ── Scrollable content area ───────────────────────────────────
        self._content = wx.Panel(self)
        self._content_sz = wx.BoxSizer(wx.VERTICAL)
        self._content.SetSizer(self._content_sz)
        outer.Add(self._content, 1, wx.EXPAND | wx.ALL, 16)

        # ── Separator + footer ────────────────────────────────────────
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        foot = wx.BoxSizer(wx.HORIZONTAL)

        self._btn_back = wx.Button(self, label="< &Back")
        self._btn_back.SetName("Go to the previous step")
        self._btn_back.Bind(wx.EVT_BUTTON, self._on_back)
        foot.Add(self._btn_back, 0, wx.ALL, 8)

        foot.AddStretchSpacer()

        self._btn_skip = wx.Button(self, label="&Skip This Step")
        self._btn_skip.SetName(
            "Skip this step and keep the current default setting")
        self._btn_skip.Bind(wx.EVT_BUTTON, self._on_skip)
        foot.Add(self._btn_skip, 0, wx.ALL, 8)

        self._btn_next = wx.Button(self, label="&Next Step >")
        self._btn_next.SetName(
            "Save this choice and go to the next step")
        self._btn_next.Bind(wx.EVT_BUTTON, self._on_next)
        foot.Add(self._btn_next, 0, wx.ALL, 8)

        self._btn_open = wx.Button(self, label="Open a Folder of &MP3 Files")
        self._btn_open.SetName(
            "Close the wizard and open a folder of MP3 files to start building")
        self._btn_open.Bind(wx.EVT_BUTTON, self._on_open_clicked)
        foot.Add(self._btn_open, 0, wx.ALL, 8)

        self._btn_finish = wx.Button(self, wx.ID_CLOSE, label="&Close Wizard")
        self._btn_finish.SetName("Close the setup wizard")
        self._btn_finish.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CLOSE))
        foot.Add(self._btn_finish, 0, wx.ALL, 8)

        outer.Add(foot, 0, wx.EXPAND)
        self.SetSizer(outer)

    # ------------------------------------------------------------------
    # Step rendering
    # ------------------------------------------------------------------

    def _go_to(self, idx: int):
        self._step_index = idx
        step = self._steps[idx]
        n = len(self._steps)
        last = (idx == n - 1)
        first = (idx == 0)
        has_setting = step.make_setting is not None

        # Dialog title (NVDA reads this on focus)
        self.SetTitle(
            f"Setup Wizard - Step {idx + 1} of {n}: {step.title}")

        # Header
        self._hdr_heading.SetLabel(step.heading)
        self._hdr_step.SetLabel(f"Step {idx + 1} of {n}")
        self._hdr_heading.GetParent().Layout()

        # Rebuild content panel
        self._content_sz.Clear(delete_windows=True)
        self._setting_apply = None

        # Body text (read-only TextCtrl so NVDA navigates line-by-line)
        body = step.body
        if last:
            body = body.replace("{summary}", self._summary_text())

        body_ctrl = wx.TextCtrl(
            self._content, value=body,
            style=(wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_BESTWRAP
                   | wx.TE_NO_VSCROLL | wx.NO_BORDER))
        body_ctrl.SetName(f"{step.heading} - description")
        body_ctrl.SetBackgroundColour(self._content.GetBackgroundColour())
        self._content_sz.Add(body_ctrl, 1, wx.EXPAND | wx.BOTTOM, 8)
        self._body_ctrl = body_ctrl

        # Optional setting widget
        if has_setting:
            result = step.make_setting(self._content)
            sizer, ctrl, apply_fn = result
            self._setting_apply = apply_fn
            sep = wx.StaticLine(self._content)
            self._content_sz.Add(sep, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 8)
            self._content_sz.Add(sizer, 0, wx.EXPAND)
            self._first_setting_ctrl = ctrl
        else:
            self._first_setting_ctrl = None

        self._content.Layout()

        # Navigation buttons
        self._btn_back.Show(not first)
        self._btn_skip.Show(has_setting and not last)
        self._btn_next.Show(not last)
        self._btn_open.Show(last)
        self._btn_finish.Show(last)

        if last:
            self._btn_open.SetDefault()
        elif first:
            self._btn_next.SetDefault()
        else:
            self._btn_next.SetDefault()

        self.Layout()

        # Accessibility
        a11y.announce(f"Step {idx + 1} of {n}: {step.heading}")

        # Focus body so NVDA reads the content immediately on step change
        body_ctrl.SetFocus()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _apply_and_save(self):
        if self._setting_apply:
            self._setting_apply()
            settings_mod.save(self.settings)

    def _on_next(self, _evt):
        self._apply_and_save()
        if self._step_index + 1 < len(self._steps):
            self._go_to(self._step_index + 1)

    def _on_back(self, _evt):
        if self._step_index > 0:
            self._go_to(self._step_index - 1)

    def _on_skip(self, _evt):
        # Move forward without applying the current step's setting
        if self._step_index + 1 < len(self._steps):
            self._go_to(self._step_index + 1)

    def _on_open_clicked(self, _evt):
        self._apply_and_save()
        self.EndModal(wx.ID_OK)
        if self._on_open_folder:
            wx.CallAfter(self._on_open_folder)


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def show_wizard(parent, settings: dict,
                on_open_folder: Optional[Callable] = None) -> bool:
    """Show the setup wizard modally.

    Returns True if the user clicked 'Open a Folder of MP3 Files'.
    """
    dlg = StartupWizard(parent, settings, on_open_folder=on_open_folder)
    result = dlg.ShowModal()
    dlg.Destroy()
    return result == wx.ID_OK
