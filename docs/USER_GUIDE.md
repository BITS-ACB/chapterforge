# ChapterForge 1.0.0 - Comprehensive User Guide

Welcome to ChapterForge 1.0.0, an accessible audio chapter management solution. This comprehensive user guide will walk you through every feature, function, and workflow to help you create chaptered audio content.

Whether you're a visually impaired user requiring full keyboard navigation and screen reader support, a content creator producing audiobooks, or a podcaster looking to enhance your episodes with precise chapter markers, this guide has everything you need to succeed.

ChapterForge 1.0.0 is designed to help you create chaptered audio content from collections of audio files. With support for popular audio formats and accessibility features, ChapterForge empowers users to create quality audio content.

---

## 1. Getting Started with ChapterForge 1.0.0

### 1.1 Launching the Application

ChapterForge 1.0.0 can be launched in multiple ways to suit your workflow:

- **Graphical Interface**: Click the ChapterForge shortcut in your Start Menu or desktop
- **Command Line**: Type `chapterforge` in your terminal or command prompt
- **Background Watcher**: Run `chapterforge --watch` to start the system tray watcher

Upon launch, you'll be greeted with a clean, intuitive interface designed for maximum accessibility and efficiency. The application automatically detects your system's accessibility settings and configures itself accordingly.

### 1.2 Understanding the Interface

The ChapterForge 1.0.0 interface is organized into two main sections for efficient workflow:

1. **Chapter Management Panel** (Left): Organize and edit your chapter list
2. **Metadata and Tagging Panel** (Right): Set ID3 tags, cover art, and export options

Each panel is fully accessible with keyboard navigation and screen reader support. The interface features a clean design with a dark/light theme toggle to suit your preferences.

### 1.3 Quick Start Workflow

#### Method 1: Basic Chapter Creation from Folder
1. Launch ChapterForge 1.0.0
2. **File → Open Folder** (`Ctrl+Shift+O`) and select a folder containing your audio files
3. Review the automatically generated chapter list in the Chapter Management Panel
4. Make any necessary adjustments to chapter titles or order
5. Click **Set Tags & Build** to proceed to metadata configuration
6. Fill in the required metadata fields (Title, Artist, Album, etc.)
7. Set your output file location and format
8. Click **Build Master File** (`Ctrl+B`) to create your chaptered audio file

#### Method 2: Advanced Workflow with Silence Detection
1. Launch ChapterForge 1.0.0
2. **File → Open File** (`Ctrl+O`) and select a single long audio recording
3. Enable **Auto-chapter by Silence** in the processing options
4. Adjust silence detection parameters (threshold and minimum duration)
5. Click **Detect Chapters** to automatically find chapter boundaries
6. Review and adjust the automatically detected chapters
7. Proceed with metadata configuration and building as above

#### Method 3: Using Job Files
1. Launch ChapterForge 1.0.0
2. **File → Open Job File** (`Ctrl+L`) and select an existing .cfjob file
3. Review the loaded configuration
4. Make any necessary adjustments
5. Click **Build Master File** to process according to the job file

### 1.4 System Requirements

- **Operating System**: Windows 10/11 (64-bit)
- **Memory**: 4GB RAM minimum (8GB recommended)
- **Storage**: 500MB available disk space plus space for audio files
- **Accessibility**: Compatible with NVDA, JAWS, and Windows Narrator
- **Additional**: Internet connection for the one-time FFmpeg download (if FFmpeg is not already installed), optional metadata lookup, and update checks

---

## 2. Comprehensive Feature Guide

### 2.1 Chapter Management Panel

The Chapter Management Panel is where you organize, edit, and optimize your chapter structure. This panel provides powerful tools for managing your audio content with precision.

#### Chapter List Operations
- **Add Chapter**: Click the "+" button or press `Insert` to add a new chapter
- **Remove Chapter**: Select a chapter and press `Delete` or click the "-" button
- **Reorder Chapters**: Use `Ctrl+Up/Down` arrows or drag-and-drop to rearrange chapters
- **Edit Chapter Title**: Double-click on a chapter title or select and press `F2`
- **Batch Edit**: Select multiple chapters using `Ctrl+Click` or `Shift+Click` for bulk operations

#### Chapter Merging and Splitting
- **Merge Chapters**: Select adjacent chapters and choose "Merge Selected" to combine them
- **Split Chapter**: During playback, click "Split Here" to divide a chapter at the current position
- **Chapter Splitting Wizard**: Select a chapter and use "Split into Individual Files" to break it into separate audio files

#### Advanced Chapter Features
- **Auto-chapter by Silence**: Automatically detect chapter breaks in long recordings by analyzing silence gaps
- **Chapter Title Patterns**: Use the Batch Edit Titles dialog to apply naming patterns to multiple chapters
- **Chapter Duration Analysis**: View detailed timing information for each chapter
- **Chapter Validation**: Automatic checking for potential issues with chapter boundaries

### 2.2 Metadata and Tagging Panel

ChapterForge 1.0.0 includes a professional-grade metadata editor that supports all standard ID3 fields and advanced tagging features.

#### Basic Tags
- **Title**: The main title of your audio work
- **Artist**: Primary artist or narrator
- **Album**: Collection or series name
- **Album Artist**: For multi-artist collections
- **Genre**: Categorization for organization
- **Year**: Publication or recording year
- **Comment**: Additional descriptive information
- **Narrator**: The voice talent, written as ID3v2 TPE4 (and as a Vorbis or MP4 field for other formats)
- **Series**: Series title and part number, for audiobook apps that group by series

#### Advanced Tagging Features
- **Custom Fields**: Add custom ID3 fields
- **Cover Art**: Automatic detection or manual selection of album art
- **Tag Templates**: Save tagging configurations for reuse across projects

#### Format and Quality Options
- **Output Format**: MP3 (CHAP/CTOC chapters), M4B (native MP4 chapters), FLAC (lossless), or Opus
- **Bitrate Settings**: Configure quality levels from 128k to 320k bitrate
- **Loudness Normalization**: Two options - normalize the whole book in one pass, or normalize each chapter individually to a LUFS target (use -23 for ACX). The per-chapter option takes priority if both are enabled.
- **Inter-Chapter Gaps**: Insert configurable silence between chapters

### 2.3 Preview and Control Panel

The Preview and Control Panel provides playback controls for reviewing your audio content.

#### Playback Controls
- **Play/Pause**: Spacebar or click the play button
- **Stop**: Stop playback and return to beginning
- **Previous/Next Chapter**: Navigate between chapters with dedicated buttons
- **Rewind/Forward**: Jump forward or backward by configurable time increments
- **Volume Control**: Adjust playback volume with slider or keyboard shortcuts
- **Position Slider**: Drag to any point in the audio or click for precise positioning

#### Basic Information
- **Chapter Information**: Current chapter details and timing

#### Play Controls Menu
Right-click the player, or press the Menu key (Shift+F10) while it's
focused, for a "Play Controls" menu with Play/Pause, Stop, Previous/Next
Chapter, Rewind, Forward, and Go to Time. The same menu appears as a
submenu when you right-click a chapter in the chapter list, so you can
start playing or jump around without first moving focus to the player.
Items are enabled or disabled to match what's currently possible - for
example, "Pause" replaces "Play" once something is playing, and Previous/
Next Chapter are unavailable when there's nothing to navigate to.

### 2.4 Audio Trimming and Cutting Tools

ChapterForge 1.0.0 includes powerful audio editing tools for precise trimming and cutting:

#### Lossless Audio Trimming
- **Set Begin/End Points**: Mark precise trim boundaries using the current playhead position
- **Pre-listen as Cut**: Hear exactly how the trimmed audio will sound
- **Save Trimmed Selection**: Export the selected region as a new file using lossless FFmpeg copy
- **Reset Trim State**: Automatically reset trim markers when loading new files

#### Chapter Splitting
- **Split One Long Recording**: Break a single long audio file into individual chapter files
- **Lossless File Splitting**: Use FFmpeg copy to split files without quality loss
- **Progress Callbacks**: Monitor splitting progress with detailed feedback
- **Batch File Output**: Save split chapters with customizable naming patterns

---

## 3. Keyboard Shortcuts and Accessibility

### 3.1 Comprehensive Keyboard Navigation

ChapterForge 1.0.0 is designed from the ground up for full keyboard accessibility:

#### Global Shortcuts
| Key Combination | Action |
|-----------------|--------|
| `Ctrl+N` | New project |
| `Ctrl+Shift+O` | Open folder of audio files |
| `Ctrl+O` | Open existing chaptered file |
| `Ctrl+S` | Save current project |
| `Ctrl+Shift+S` | Save As... |
| `Ctrl+P` | Print/export report |
| `Ctrl+Q` | Quit application |
| `F1` | Help on the focused control |
| `Ctrl+F1` | Open User Guide |
| `F2` | Rename selected chapter |
| `F5` | Refresh chapter list |
| `F11` | Toggle full screen mode |
| `Ctrl+,` | Open Settings dialog |

#### Chapter Management Shortcuts
| Key Combination | Action |
|-----------------|--------|
| `Insert` | Add new chapter |
| `Delete` | Remove selected chapter |
| `Ctrl+Up/Down` | Move chapter up/down in list |
| `Ctrl+A` | Select all chapters |
| `Ctrl+E` | Edit chapter title |
| `Ctrl+D` | Duplicate selected chapter |
| `Ctrl+R` | Reset chapter boundaries |
| `Ctrl+Shift+R` | Reset all chapters |
| `Ctrl+T` | Merge selected chapters |
| `Ctrl+Shift+T` | Split chapter at playhead |

#### Playback Controls Shortcuts
| Key Combination | Action |
|-----------------|--------|
| `Space` | Play/Pause |
| `Ctrl+Space` | Stop |
| `Left/Right Arrow` | Rewind/Forward 5 seconds |
| `Ctrl+Left/Right` | Previous/Next chapter |
| `Shift+Left/Right` | Rewind/Forward 30 seconds |
| `Alt+Left/Right` | Rewind/Forward 1 minute |
| `Ctrl+Shift+Left/Right` | Jump to first/last chapter |
| `Up/Down Arrow` | Increase/decrease volume 5% |
| `Ctrl+Up/Down` | Increase/decrease playback speed 0.1x |
| `Ctrl+1-9` | Jump to bookmark 1-9 |
| `[` | Set loop start point |
| `]` | Set loop end point |
| `\` | Clear loop selection |

#### Trimming and Cutting Shortcuts
| Key Combination | Action |
|-----------------|--------|
| `Ctrl+B` | Set begin trim point |
| `Ctrl+E` | Set end trim point |
| `Ctrl+C` | Clear trim selection |
| `Ctrl+Shift+C` | Save trimmed selection |

#### Accessibility Features
- **Screen Reader Optimization**: Intelligent announcements provide context-aware feedback
- **High Contrast Themes**: Multiple high-contrast color schemes for visual accessibility
- **Customizable Text Size**: Adjust interface text from 8pt to 24pt
- **Keyboard Focus Indicators**: Clear visual indication of currently focused controls
- **Alternative Navigation**: Tab-based navigation through all interface elements

### 3.2 Screen Reader Integration

ChapterForge 1.0.0 includes advanced screen reader support:
- **Context-Aware Announcements**: Only relevant information is announced to avoid noise
- **Customizable Verbosity**: Adjust how much detail is announced during operations
- **Progress Reporting**: Real-time progress updates during long operations
- **Error Guidance**: Clear, actionable error messages with recovery suggestions
- **Workflow Assistance**: Step-by-step guidance through complex operations

#### Context-Sensitive Help (F1)
Press `F1` while any control has keyboard focus to hear exactly what it is,
what it currently shows, and what activating it will do right now:
- Descriptions reflect your own settings and the app's current state - for
  example, the Rewind button names the skip amount you've actually
  configured, and the chapter list names how many chapters you have and
  whether you're in build or edit mode
- Buttons whose meaning changes between modes (Move Up/Down, Remove/Merge
  Up) explain both meanings and tell you which one currently applies
- Anything not specifically covered still gets a useful description built
  from its accessible name, tooltip, and control type
- The help opens in a small read-only window - title, description, and a
  Close button - so it's easy to dismiss and read with a screen reader
- Press `Ctrl+F1` instead for the full User Guide

Every description here comes from the same source the app itself reads
from at runtime, so this guide and the in-app help can never disagree. For
a complete list of every control and what F1 says about it (with
illustrative example values in place of live state), see the generated
**Control Reference** page alongside this guide.

---

## 4. Advanced Features and Workflows

### 4.1 Job Files (.cfjob)

Job files are powerful, human-readable text files that store complete project configurations. They enable reproducible builds, template creation, and collaborative workflows.

#### Job File Structure
```ini
# ChapterForge 1.0.0 Job File - Professional Audiobook Project
# Created: 2026-06-05
# Author: [Your Name]

# Global Settings
@version     = 1.0.0
@title       = The Complete Guide to Audio Chaptering
@artist      = Jane Author
@album       = Audiobook Masterclass Series
@albumartist = Audiobook Publishers Inc.
@genre       = Education
@year        = 2026
@comment     = Professional educational audiobook
@tracktotal  = 12

# Output Configuration
@output      = The Complete Guide to Audio Chaptering - Master.m4b
@format      = m4b
@bitrate     = 128k
@quality     = high
@normalize   = true
@target_lufs = -16.0

# Cover Art
@cover       = cover.jpg

# Custom Fields
@composer    = John Composer
@copyright   = © 2026 Audiobook Publishers Inc.
@publisher   = Audiobook Publishers Inc.
@isrc        = US-XXX-23-12345

# Chapter List (filename | title | start | duration | custom tags)
01_Introduction.mp3      | Introduction to ChapterForge 2.0 | 00:00:00 | 00:05:32 | @genre=Introduction
02_Getting_Started.mp3   | Getting Started with ChapterForge | 00:05:32 | 00:22:15 | @genre=Tutorial
03_Advanced_Features.mp3 | Advanced Features and Workflows | 00:27:47 | 00:18:44 | @genre=Advanced
# ... additional chapters
```

#### Job File Benefits
- **Version Control**: Store project configurations in Git or other VCS
- **Reproducible Builds**: Exactly recreate projects at any time
- **Batch Processing**: Process multiple job files in sequence
- **Template System**: Create reusable templates for common project types
- **Collaboration**: Share complete project configurations with team members

#### Job File Operations
- **Create**: File → Save Project As... (`Ctrl+Shift+S`)
- **Load**: File → Open Project... (`Ctrl+L`)
- **Template**: File → Save as Template...
- **Batch Process**: Tools → Batch Process Job Files...
- **Validate**: Tools → Validate Job File Structure

### 4.2 Background Watcher System

The Background Watcher allows automated processing of audio folders with system tray integration:

#### Setting Up Watch Processes
1. **Tools → Watch Folders...** (`Ctrl+W`)
2. Click **New Process** to create a watch configuration
3. Set the **Watch Folder** (folder to monitor for new content)
4. Configure **Naming Templates** using variables:
   - `{folder}` - Name of the source folder
   - `{parent}` - Parent folder name
   - `{date}` - Current date (YYYY-MM-DD)
   - `{datetime}` - Current date and time
5. Set default **Metadata Values** for automated builds
6. Configure **Output Location** and format preferences
7. Enable **Start at Sign-in** for persistent watching

#### Advanced Watcher Features
- **Stability Detection**: Only processes folders after content stabilizes
- **Duplicate Prevention**: Built-in system prevents double-processing
- **Progress Notifications**: System notifications for build start/completion
- **Error Handling**: Automated error recovery and reporting
- **Custom Scripts**: Run pre/post processing scripts on build completion

#### Watcher Safety Features
- **Lock Files**: Atomic `.chapterforge_processing` locks prevent double-processing
- **Done Markers**: `.chapterforge_done` markers make folders one-shot
- **Failure Backoff**: `.chapterforge_failed` files retry only after content changes
- **Output Exclusion**: Generated masters are written to `_ChapterForge` sub-folder

#### Watching Cloud-Synced Folders
You can point a watch folder at a local OneDrive, Dropbox or Google Drive
sync folder just like any other folder - ChapterForge watches the synced
copy on disk, so cloud-based production setups work without any special
configuration.

One thing worth knowing: these services can list "online-only" placeholder
files - showing the final size and date before the audio has actually
downloaded. ChapterForge detects these placeholders and waits for every
file in a folder to finish downloading before it builds, so you never end
up with a master built from incomplete audio. While it waits, you'll see a
"ChapterForge - waiting" notification telling you how many files are still
downloading; the build starts automatically the moment they finish.

#### Playback from the Tray
If you minimize the main window to the system tray while audio is loaded
in the player, the tray icon's right-click menu gains Play/Pause, Stop,
and Previous/Next Chapter, so you can keep listening and navigate between
chapters without restoring the window. (The standalone watcher-only tray
icon doesn't show these, since it has no player of its own.)

### 4.3 Batch Processing System

Process entire libraries with minimal setup using the Batch Processing Wizard:

#### Batch Processing Wizard
1. **Tools → Batch Processing Wizard**
2. Select **Source Folder** containing multiple sub-folders
3. Choose **Processing Mode**:
   - **Recursive**: Process all sub-folders
   - **Flat**: Process only immediate sub-folders
   - **Pattern**: Process folders matching specific naming patterns
4. Configure **Naming Conventions** for output files
5. Set **Default Metadata** or enable automatic fetching
6. Review and confirm the **Processing Queue**
7. Start processing and monitor progress

#### Batch Processing Options
- **Parallel Processing**: Process multiple folders simultaneously
- **Error Tolerance**: Continue processing after individual failures
- **Progress Reporting**: Detailed logs and summary reports
- **Scheduling**: Set processing to run at specific times
- **Resource Management**: Control CPU and memory usage

### 4.4 Silence-Based Chapter Detection

Automatically detect chapter boundaries in long recordings using silence detection:

#### Silence Detection Parameters
- **Noise Threshold**: Set sensitivity level for silence detection (default: -30dB)
- **Minimum Silence Duration**: Configure minimum length of silence to trigger a chapter break (default: 0.8 seconds)

#### Using Silence Detection
1. **Method 1 - GUI**: Select a long audio file and enable silence detection in processing options
2. **Method 2 - CLI**: Use `chapterforge --split-silence --noise-db -30 --min-silence 0.8 input.mp3`

### 4.5 Release Channels and Feature Flags

**Help → Feature Flags** is where you choose how early you want access to
new, optional functionality, and switch individual features on or off:

1. Pick a **release channel** - **General** (the default, fully tested
   features only), **Beta**, or **Alpha** (earlier access to newer
   features, which may be less polished)
2. Switching to an earlier channel immediately reveals any features it
   unlocks, each shown with its own description so you know what you're
   opting into
3. Turn any available feature on or off individually - your choice is
   remembered even if you later switch channels
4. Features you turn off disappear from menus and the interface entirely,
   rather than being merely greyed out, so you only ever see what you can
   actually use

Your channel and per-feature choices are saved as `release_channel` and
`feature_flags` in your settings. **Restart ChapterForge for changes to
take effect** - menus and panels are only built once at startup, so a
newly enabled (or disabled) feature appears (or disappears) the next time
the app opens.

---

## 5. Command Line Interface

ChapterForge 1.0.0 includes a comprehensive CLI for automation and scripting:

### Basic Commands
```bash
# Convert a folder of audio files
chapterforge "C:\Audiobooks\My Book"

# Convert with custom output location
chapterforge -i .\chapters -o book.mp3

# Set metadata during conversion
chapterforge .\chapters --title "My Book" --artist "Jane Doe" --album "My Collection"

# Normalize audio loudness
chapterforge .\chapters --normalize

# Show what would be processed without building
chapterforge .\chapters --dry-run --list

# Choose the output format (mp3, m4b, flac or opus)
chapterforge .\chapters --format m4b

# Process using existing job file
chapterforge --job mybook.cfjob

# Check for application updates
chapterforge --check-updates

# Show detailed help
chapterforge --help
```

### Advanced CLI Features
```bash
# Batch-build every book sub-folder under a parent folder
chapterforge --batch "C:\Audiobooks"

# Set the re-encode bitrate
chapterforge .\chapters --bitrate 192k

# Normalize each chapter to a loudness target (use -23 for ACX)
chapterforge .\chapters --per-file-normalize --normalize-lufs -16.0

# Also write a Podcasting 2.0 chapters JSON sidecar
chapterforge .\chapters --pod2-chapters

# Set narrator and series metadata
chapterforge .\chapters --narrator "John Reader" --series "My Series" --series-part 2

# Process with custom cover art
chapterforge .\chapters --cover artwork.jpg

# Split a long recording into chapters by silence
chapterforge --split-silence --noise-db -30 --min-silence 0.8 long_recording.mp3

# Trim leading/trailing silence from each file before joining
chapterforge .\chapters --trim-silence

# Quiet mode for automated scripts (errors only)
chapterforge .\chapters --quiet

# Write a podcast RSS feed pointing at the hosted media URL
chapterforge .\chapters --rss-url https://example.com/book.mp3
```

### CLI Return Codes
- `0`: Success
- `1`: Aborted (for example, the output exists and was not overwritten)
- `2`: Invalid arguments, or the input is not a folder
- `3`: FFmpeg not found
- `4`: No usable audio files found
- `5`: Build error
- `6`: Update check or download error
- `130`: Cancelled (Ctrl+C)

### CLI Automation Examples
```bash
# Process an entire library quietly
for /d %i in ("C:\Audiobooks\*") do chapterforge "%i" --quiet

# Batch-build a whole library
chapterforge --batch "C:\Audiobooks"

# Nightly processing script with per-chapter normalization
chapterforge --batch "C:\Audiobooks" --quiet
```

---

## 6. Troubleshooting and Support

### Common Issues and Solutions

#### Issue: "FFmpeg not found" error
**Solution**: 
1. Ensure FFmpeg is installed and on your system PATH
2. Or let ChapterForge download FFmpeg for you - it offers this automatically on first run, and any time from Help > Download FFmpeg
3. Verify installation with `ffmpeg -version` in command prompt

#### Issue: Chapters not displaying in player
**Solution**:
1. Check that your player supports ID3v2 CHAP/CTOC frames
2. Verify chapter file was built successfully
3. Try exporting in M4B format for better player compatibility

#### Issue: Slow processing times
**Solution**:
1. Close other applications to free system resources
2. Ensure sufficient free disk space
3. Check that your audio files are not corrupted
4. Consider using SSD storage for temporary files

#### Issue: Accessibility features not working
**Solution**:
1. Ensure screen reader is running before launching ChapterForge
2. Check that Prismatoid package is installed for enhanced accessibility
3. Review accessibility settings in ChapterForge preferences

#### Issue: Background watcher not processing folders
**Solution**:
1. Check that the watcher is running in the system tray
2. Verify watch folder paths are correct and accessible
3. Check for `.chapterforge_done` or `.chapterforge_failed` marker files
4. Review watcher logs in the ChapterForge settings directory
5. If the watch folder is inside OneDrive, Dropbox or Google Drive, look for
   a "ChapterForge - waiting" notification - the watcher pauses until every
   file has finished downloading from the cloud, and resumes automatically
   once they're all present locally

### Getting Help

- **User Guide**: [chapterforge.app](https://chapterforge.app) (this document, published online)
- **Discussions**: [github.com/BITS-ACB/chapterforge/discussions](https://github.com/BITS-ACB/chapterforge/discussions) - ask questions, share ideas, and talk with the community
- **Bug Reports**: [github.com/BITS-ACB/chapterforge/issues](https://github.com/BITS-ACB/chapterforge/issues)

---

## 7. Tips and Best Practices

### Audio File Preparation
- **Consistent Format**: Use the same sample rate and bit depth for all files in a project
- **Quality Check**: Verify all files play correctly before processing
- **Naming Conventions**: Use descriptive filenames that will become chapter titles
- **Metadata Cleanup**: Remove any existing chapter data to avoid conflicts

### Chapter Management
- **Logical Lengths**: Aim for chapters between 3-15 minutes for optimal navigation
- **Natural Breaks**: Place chapter boundaries at logical content breaks
- **Consistent Titling**: Use a consistent naming scheme across all chapters
- **Prelude Chapters**: Consider adding short introductory chapters for branding

### Export Optimization
- **Format Selection**: 
  - MP3 with CHAP/CTOC for podcast compatibility
  - M4B for audiobook players and iOS devices
- **Quality Settings**: 128k for spoken word, 192k-320k for music
- **Loudness Normalization**: Enable for consistent playback levels
- **Cover Art**: Include cover art for better player compatibility

### Performance Tips
- **SSD Storage**: Use solid-state drives for temporary files and processing
- **Sufficient RAM**: Allocate at least 4GB RAM for large projects
- **Background Processing**: Use the watcher system for automatic processing
- **Regular Maintenance**: Clean temporary files periodically to maintain performance

### Accessibility Best Practices
- **Descriptive Titles**: Use clear, descriptive chapter titles for screen reader users
- **Consistent Structure**: Maintain consistent formatting across all projects
- **Testing**: Always test with screen readers to ensure accessibility
- **Feedback**: Provide accessibility feedback to the ChapterForge development team

---

## 8. Auphonic Integration

ChapterForge includes a built-in Auphonic integration for professional audio post-production. You connect your own Auphonic account and process audio using your own Auphonic credits. See [AUPHONIC_INTEGRATION.md](AUPHONIC_INTEGRATION.md) for the full reference. Key points:

### Access

Open the **Auphonic** menu (between View and Help):

| Menu item | Action |
|---|---|
| Connect Account | OAuth connect / view credit balance |
| New Production | Submit audio to Auphonic for processing |
| Job History | View submitted jobs and download results |

### Workflow

1. **Auphonic > Connect Account** - click Connect Auphonic, complete login in your browser, return to ChapterForge.
2. Your available credit balance is shown in the connect dialog.
3. **Auphonic > New Production** - browse for an audio file, choose a preset, enter a title, click Submit.
4. ChapterForge validates the file (rejects video streams), estimates credits, and submits to Auphonic.
5. Processing runs in the background. When complete, open **Job History** to download results.

### Built-in Presets

- Podcast Cleanup (-16 LUFS, denoise, MP3)
- Podcast Cleanup + Transcript (adds SRT/WebVTT captions and transcript HTML/TXT)
- Audiobook / ACX Draft (-18 LUFS, WAV + FLAC)
- Lecture Cleanup (silence cutting, MP3 + captions)
- Meeting / Interview Multitrack (host/guest tracks)
- Archive Master (minimal processing, FLAC + WAV)

### Audio-only policy

Only audio files are accepted. Any file containing a video stream is rejected at the validation step. Video output formats are blocked even if Auphonic returns them.

---

## 9. Glossary of Terms

**Chapter Marker**: A timestamp in an audio file that indicates the start of a named section

**ID3v2 CHAP**: The ID3v2 frame format used to store chapter information in MP3 files

**CTOC Frame**: The Container Table Of Contents frame that organizes chapters hierarchically

**LUFS**: Loudness Units Full Scale - standardized measurement of audio loudness

**Waveform**: Visual representation of audio amplitude over time

**Sample Rate**: Number of audio samples per second (e.g., 44.1kHz, 48kHz)

**Bitrate**: Amount of data processed per second of audio (e.g., 128k, 192k, 320k)

**Lossless**: Audio processing that preserves original quality without compression artifacts

**Fade-in/Fade-out**: Gradual volume increase/decrease at beginning/end of audio segments

**Silence Detection**: Algorithmic identification of quiet periods in audio for chapter boundaries

**Job File**: Human-readable text file containing complete ChapterForge project configuration

**Background Watcher**: System tray application that automatically processes new audio folders

**Auphonic**: Cloud audio post-production service used via the Auphonic menu for leveling, noise reduction, transcription, and more.

---

*ChapterForge User Guide - Where Accessibility Meets Professional Power*

#### Method 1: Basic Chapter Creation
1. Launch ChapterForge 1.0.0
2. **File → Open Folder** (`Ctrl+Shift+O`) and select a folder containing your audio files
3. Review the automatically generated chapter list in the Chapter Management Panel
4. Click **Set Tags & Build** to proceed to metadata configuration
5. Fill in the required metadata fields (Title, Artist, Album, etc.)
6. Set your output file location and format
7. Click **Build Master File** (`Ctrl+B`) to create your chaptered audio file

| Key | Action |
| --- | --- |
| `Ctrl+Shift+O` | Open folder of MP3 files |
| `Ctrl+O` | Open an existing chaptered file to edit |
| `Ctrl+S` | Build (build mode) or Save Changes (edit mode) |
| `Ctrl+B` | Build master - explicit |
| `Ctrl+Shift+S` | Save changes to the open master - explicit |
| `Ctrl+L` | Load a Saved Setup (`.cfjob`) |
| `Ctrl+G` | Save This Setup as a Template |
| `Ctrl+W` | Set Up Automatic Building |
| `Ctrl+,` | Settings |
| `Ctrl+Shift+P` | Command Palette - search all commands |
| `Ctrl+/` | Open keyboard shortcuts in browser |
| `Ctrl+=` | Larger text |
| `Ctrl+-` | Smaller text |
| `Ctrl+0` | Reset text size |
| `F1` | User Guide |
| `Alt+F4` | Exit |

**In the Chapters list:**

| Key | Action |
| --- | --- |
| `Up` / `Down` | Move selection (also selects the focused item) |
| `F2` | Edit the selected chapter title inline |
| `Delete` | Remove chapter (build) or merge up (edit mode) |
| `Alt+Up` / `Alt+Down` | Move chapter up or down |

All actions are also available as labeled buttons and via the menus.

---

## 2. Comprehensive Feature Guide

### 2.1 Chapter Management Panel

The Chapter Management Panel is where you organize, edit, and optimize your chapter structure.

#### Chapter List Operations
- **Add Chapter**: Click the "+" button or press `Insert` to add a new chapter
- **Remove Chapter**: Select a chapter and press `Delete` or click the "-" button
- **Reorder Chapters**: Use `Ctrl+Up/Down` arrows or drag-and-drop to rearrange chapters
- **Edit Chapter Title**: Double-click on a chapter title or select and press `F2`
- **Batch Edit**: Select multiple chapters using `Ctrl+Click` or `Shift+Click` for bulk operations

#### AI Transcription

ChapterForge can transcribe your audio to text and suggest chapter boundaries using a local AI model (no internet connection required after setup).

**Setup:** Open **Transcription > AI Model...** to download and configure a model. The dialog detects what is already on your system:
- If a model is already downloaded it opens in settings mode, showing the current tier and model with a Save button.
- If nothing is downloaded it opens a three-step wizard that installs the required package and downloads the model. Estimated download sizes range from 75 MB (tiny) to 3 GB (large).

**Tiers:**
- **Basic** - uses whisper.cpp (no Python packages needed; binary must be on PATH).
- **Strong** - uses faster-whisper (requires `pip install faster-whisper`; recommended for most users).
- **Premium** - uses Parakeet ONNX (requires `pip install onnxruntime`; highest accuracy on English).

**Using AI features after setup:**
- **Transcription > Transcribe Audio...** - transcribes the loaded audio to a text file.
- **Transcription > Suggest AI Chapters...** - runs transcription and automatically inserts chapter markers at detected boundaries.

#### Waveform Visualization
The enhanced waveform visualization provides real-time visual feedback:
- **Zoom Controls**: Use mouse wheel or `+/-` keys to zoom in/out
- **Navigation**: Click and drag to pan through the waveform
- **Chapter Boundaries**: Visual markers indicate current chapter start/end points
- **Playback Position**: Moving cursor shows current playback position

### 2.2 Metadata and Tagging Panel

ChapterForge 1.0.0 includes a professional-grade metadata editor:

#### Basic Tags
- **Title**: The main title of your audio work
- **Artist**: Primary artist or narrator
- **Album**: Collection or series name
- **Album Artist**: For multi-artist collections
- **Genre**: Categorization for organization
- **Year**: Publication or recording year
- **Comment**: Additional descriptive information
- **Narrator**: The voice talent, written as ID3v2 TPE4 (and as a Vorbis or MP4 field for other formats)
- **Series**: Series title and part number, for audiobook apps that group by series

#### Advanced Tagging Features
- **Custom Fields**: Add any number of custom ID3 fields
- **Cover Art**: Automatic detection or manual selection of album art
- **Multiple Images**: Attach multiple images with different types (cover, artist, etc.)
- **Import Metadata**: Fetch information from MusicBrainz and Open Library (Tools > Look Up Metadata)
- **Export Templates**: Save tagging configurations for reuse

#### Format and Quality Options
- **Output Format**: Choose from MP3, M4B, FLAC, and Opus
- **Bitrate Settings**: Configure quality levels from 64k to 320k bitrate
- **Loudness Normalization**: ITU-R BS.1770-4 compliant loudness adjustment
- **Sample Rate Conversion**: Automatic or manual sample rate settings
- **Channel Mapping**: Mono, stereo, or multi-channel output options

### 2.3 Preview and Control Panel

The Preview and Control Panel provides comprehensive playback and analysis tools:

#### Playback Controls
- **Play/Pause**: Spacebar or click the play button
- **Stop**: Stop playback and return to beginning
- **Previous/Next Chapter**: Navigate between chapters with dedicated buttons
- **Rewind/Forward**: Jump forward or backward by configurable time increments
- **Volume Control**: Adjust playback volume with slider or keyboard shortcuts
- **Position Slider**: Drag to any point in the audio or click for precise positioning

#### Real-time Analysis
- **Spectral Display**: Visualize frequency content in real-time
- **Level Meters**: Monitor audio levels to prevent clipping
- **Chapter Information**: Current chapter details and timing
- **Playback Statistics**: Detailed playback performance metrics

#### Advanced Playback Features
- **Loop Selection**: Set start and end points to loop a section
- **Variable Speed**: Adjust playback speed from 0.5x to 2.0x
- **A-B Repeat**: Define a section to repeat continuously
- **Bookmark System**: Save important positions for later reference
- **Chapter Preview**: Listen to individual chapters before building

## 3. Keyboard Shortcuts and Accessibility

### 3.1 Comprehensive Keyboard Navigation

ChapterForge 1.0.0 is designed from the ground up for full keyboard accessibility:

#### Global Shortcuts
| Key Combination | Action |
|-----------------|--------|
| `Ctrl+N` | New project |
| `Ctrl+Shift+O` | Open folder of audio files |
| `Ctrl+O` | Open existing chaptered file |
| `Ctrl+S` | Save current project |
| `Ctrl+Shift+S` | Save As... |
| `Ctrl+P` | Print/export report |
| `Ctrl+Q` | Quit application |
| `F1` | Help on the focused control |
| `Ctrl+F1` | Open User Guide |
| `F2` | Rename selected chapter |
| `F5` | Refresh chapter list |
| `F11` | Toggle full screen mode |
| `Ctrl+,` | Open Settings dialog |

#### Chapter Management Shortcuts
| Key Combination | Action |
|-----------------|--------|
| `Insert` | Add new chapter |
| `Delete` | Remove selected chapter |
| `Ctrl+Up/Down` | Move chapter up/down in list |
| `Ctrl+A` | Select all chapters |
| `Ctrl+E` | Edit chapter title |
| `Ctrl+D` | Duplicate selected chapter |
| `Ctrl+Shift+D` | Download chapter metadata |
| `Ctrl+R` | Reset chapter boundaries |
| `Ctrl+Shift+R` | Reset all chapters |

#### Playback Controls Shortcuts
| Key Combination | Action |
|-----------------|--------|
| `Space` | Play/Pause |
| `Ctrl+Space` | Stop |
| `Left/Right Arrow` | Rewind/Forward 5 seconds |
| `Ctrl+Left/Right` | Previous/Next chapter |
| `Shift+Left/Right` | Rewind/Forward 30 seconds |
| `Alt+Left/Right` | Rewind/Forward 1 minute |
| `Ctrl+Shift+Left/Right` | Jump to first/last chapter |
| `Up/Down Arrow` | Increase/decrease volume 5% |
| `Ctrl+Up/Down` | Increase/decrease playback speed 0.1x |
| `Ctrl+1-9` | Jump to bookmark 1-9 |
| `[` | Set loop start point |
| `]` | Set loop end point |
| `\` | Clear loop selection |

#### Accessibility Features
- **Screen Reader Optimization**: Intelligent announcements provide context-aware feedback
- **High Contrast Themes**: Multiple high-contrast color schemes for visual accessibility
- **Customizable Text Size**: Adjust interface text from 8pt to 24pt
- **Keyboard Focus Indicators**: Clear visual indication of currently focused controls
- **Alternative Navigation**: Tab-based navigation through all interface elements

### 3.2 Screen Reader Integration

ChapterForge 1.0.0 includes advanced screen reader support:
- **Context-Aware Announcements**: Only relevant information is announced to avoid noise
- **Customizable Verbosity**: Adjust how much detail is announced during operations
- **Progress Reporting**: Real-time progress updates during long operations
- **Error Guidance**: Clear, actionable error messages with recovery suggestions
- **Workflow Assistance**: Step-by-step guidance through complex operations

## 4. Advanced Features and Workflows

### 4.1 Job Files (.cfjob)

Job files are powerful, human-readable text files that store complete project configurations:

```ini
# ChapterForge 1.0.0 Job File - Professional Audiobook Project
# Created: 2026-06-05
# Author: [Your Name]

# Global Settings
@version     = 1.0.0
@title       = The Complete Guide to Audio Chaptering
@artist      = Jane Author
@album       = Audiobook Masterclass Series
@albumartist = Audiobook Publishers Inc.
@genre       = Education
@year        = 2026
@comment     = Professional educational audiobook
@tracktotal  = 12

# Output Configuration
@output      = The Complete Guide to Audio Chaptering - Master.m4b
@format      = m4b
@bitrate     = 128k
@quality     = high
@normalize   = true
@target_lufs = -16.0

# Cover Art
@cover       = cover.jpg

# Custom Fields
@composer    = John Composer
@copyright   = © 2026 Audiobook Publishers Inc.
@publisher   = Audiobook Publishers Inc.
@isrc        = US-XXX-23-12345

# Chapter List (filename | title | start | duration | custom tags)
01_Introduction.mp3      | Introduction to ChapterForge 2.0 | 00:00:00 | 00:05:32 | @genre=Introduction
02_Getting_Started.mp3   | Getting Started with ChapterForge | 00:05:32 | 00:22:15 | @genre=Tutorial
03_Advanced_Features.mp3 | Advanced Features and Workflows | 00:27:47 | 00:18:44 | @genre=Advanced
# ... additional chapters
```

#### Job File Benefits
- **Version Control**: Store project configurations in Git or other VCS
- **Reproducible Builds**: Exactly recreate projects at any time
- **Batch Processing**: Process multiple job files in sequence
- **Template System**: Create reusable templates for common project types
- **Collaboration**: Share complete project configurations with team members

#### Job File Operations
- **Create**: File → Save Project As... (`Ctrl+Shift+S`)
- **Load**: File → Open Project... (`Ctrl+L`)
- **Template**: File → Save as Template...
- **Batch Process**: Tools → Batch Process Job Files...
- **Validate**: Tools → Validate Job File Structure

### 4.2 Background Watcher System

The Background Watcher allows automated processing of audio folders:

#### Setting Up Watch Processes
1. **Tools → Watch Folders...** (`Ctrl+W`)
2. Click **New Process** to create a watch configuration
3. Set the **Watch Folder** (folder to monitor for new content)
4. Configure **Naming Templates** using variables:
   - `{folder}` - Name of the source folder
   - `{parent}` - Parent folder name
   - `{date}` - Current date (YYYY-MM-DD)
   - `{datetime}` - Current date and time
5. Set default **Metadata Values** for automated builds
6. Configure **Output Location** and format preferences
7. Enable **Start at Sign-in** for persistent watching

#### Advanced Watcher Features
- **Stability Detection**: Only processes folders after content stabilizes
- **Duplicate Prevention**: Built-in system prevents double-processing
- **Progress Notifications**: System notifications for build start/completion
- **Error Handling**: Automated error recovery and reporting
- **Custom Scripts**: Run pre/post processing scripts on build completion
- **Cloud-Synced Folders**: A watch folder can live inside a OneDrive,
  Dropbox or Google Drive sync folder. ChapterForge detects "online-only"
  placeholder files these services list before the audio finishes
  downloading, and waits for every file to be fully downloaded before it
  builds - so a master is never built from incomplete audio.

### 4.3 Batch Processing System

Process entire libraries with minimal setup:

#### Batch Processing Wizard
1. **Tools → Batch Processing Wizard**
2. Select **Source Folder** containing multiple sub-folders
3. Choose **Processing Mode**:
   - **Recursive**: Process all sub-folders
   - **Flat**: Process only immediate sub-folders
   - **Pattern**: Process folders matching specific naming patterns
4. Configure **Naming Conventions** for output files
5. Set **Default Metadata** or enable automatic fetching
6. Review and confirm the **Processing Queue**
7. Start processing and monitor progress

#### Batch Processing Options
- **Parallel Processing**: Process multiple folders simultaneously
- **Error Tolerance**: Continue processing after individual failures
- **Progress Reporting**: Detailed logs and summary reports
- **Scheduling**: Set processing to run at specific times
- **Resource Management**: Control CPU and memory usage

## 5. Command Line Interface

ChapterForge 1.0.0 includes a comprehensive CLI for automation and scripting:

### Basic Commands
```bash
# Convert a folder of audio files
chapterforge "C:\Audiobooks\My Book"

# Convert with custom output location
chapterforge -i .\chapters -o book.mp3

# Set metadata during conversion
chapterforge .\chapters --title "My Book" --artist "Jane Doe" --album "My Collection"

# Normalize audio loudness
chapterforge .\chapters --normalize

# Show what would be processed without building
chapterforge .\chapters --dry-run --list

# Choose the output format (mp3, m4b, flac or opus)
chapterforge .\chapters --format m4b

# Process using existing job file
chapterforge --job mybook.cfjob

# Check for application updates
chapterforge --check-updates

# Show detailed help
chapterforge --help
```

### Advanced CLI Features
```bash
# Batch-build every book sub-folder under a parent folder
chapterforge --batch "C:\Audiobooks"

# Set the re-encode bitrate
chapterforge .\chapters --bitrate 192k

# Normalize each chapter to a loudness target (use -23 for ACX)
chapterforge .\chapters --per-file-normalize --normalize-lufs -16.0

# Also write a Podcasting 2.0 chapters JSON sidecar
chapterforge .\chapters --pod2-chapters

# Set narrator and series metadata
chapterforge .\chapters --narrator "John Reader" --series "My Series" --series-part 2

# Process with custom cover art
chapterforge .\chapters --cover artwork.jpg

# Trim leading/trailing silence from each file before joining
chapterforge .\chapters --trim-silence

# Quiet mode for automated scripts (errors only)
chapterforge .\chapters --quiet

# Write a podcast RSS feed pointing at the hosted media URL
chapterforge .\chapters --rss-url https://example.com/book.mp3
```

### CLI Return Codes
- `0`: Success
- `1`: Aborted (for example, the output exists and was not overwritten)
- `2`: Invalid arguments, or the input is not a folder
- `3`: FFmpeg not found
- `4`: No usable audio files found
- `5`: Build error
- `6`: Update check or download error
- `130`: Cancelled (Ctrl+C)

## 6. Troubleshooting and Support

### Common Issues and Solutions

#### Issue: "FFmpeg not found" error
**Solution**:
1. Ensure FFmpeg is installed and on your system PATH
2. Or let ChapterForge download FFmpeg for you - it offers this automatically on first run, and any time from Help > Download FFmpeg
3. Verify installation with `ffmpeg -version` in command prompt

#### Issue: Chapters not displaying in player
**Solution**:
1. Check that your player supports ID3v2 CHAP/CTOC frames
2. Verify chapter file was built successfully
3. Try exporting in M4B format for better player compatibility

#### Issue: Slow processing times
**Solution**:
1. Close other applications to free system resources
2. Ensure sufficient free disk space
3. Check that your audio files are not corrupted
4. Consider using SSD storage for temporary files

#### Issue: Accessibility features not working
**Solution**:
1. Ensure screen reader is running before launching ChapterForge
2. Check that Prismatoid package is installed for enhanced accessibility
3. Review accessibility settings in ChapterForge preferences

### Getting Help

- **User Guide**: [chapterforge.app](https://chapterforge.app) (this document, published online)
- **Discussions**: [github.com/BITS-ACB/chapterforge/discussions](https://github.com/BITS-ACB/chapterforge/discussions) - ask questions, share ideas, and talk with the community
- **Bug Reports**: [github.com/BITS-ACB/chapterforge/issues](https://github.com/BITS-ACB/chapterforge/issues)

## 7. Tips and Best Practices

### Audio File Preparation
- **Consistent Format**: Use the same sample rate and bit depth for all files in a project
- **Quality Check**: Verify all files play correctly before processing
- **Naming Conventions**: Use descriptive filenames that will become chapter titles
- **Metadata Cleanup**: Remove any existing chapter data to avoid conflicts

### Chapter Management
- **Logical Lengths**: Aim for chapters between 3-15 minutes for optimal navigation
- **Natural Breaks**: Place chapter boundaries at logical content breaks
- **Consistent Titling**: Use a consistent naming scheme across all chapters
- **Prelude Chapters**: Consider adding short introductory chapters for branding

### Export Optimization
- **Format Selection**:
  - MP3 with CHAP/CTOC for podcast compatibility
  - M4B for audiobook players and iOS devices
  - FLAC for archival purposes
- **Quality Settings**: 128k for spoken word, 192k-320k for music
- **Loudness Normalization**: Always enable for consistent playback levels

### Performance Tips
- **SSD Storage**: Use solid-state drives for temporary files and processing
- **Sufficient RAM**: Allocate at least 4GB RAM for large projects
- **Background Processing**: Use the watcher system for automatic processing
- **Regular Maintenance**: Clean temporary files periodically to maintain performance

## 8. Glossary of Terms

**Chapter Marker**: A timestamp in an audio file that indicates the start of a named section

**ID3v2 CHAP**: The ID3v2 frame format used to store chapter information in MP3 files

**CTOC Frame**: The Container Table Of Contents frame that organizes chapters hierarchically

**LUFS**: Loudness Units Full Scale - standardized measurement of audio loudness

**Waveform**: Visual representation of audio amplitude over time

**Sample Rate**: Number of audio samples per second (e.g., 44.1kHz, 48kHz)

**Bitrate**: Amount of data processed per second of audio (e.g., 128k, 192k, 320k)

---

*ChapterForge 1.0.0 User Guide - Where Accessibility Meets Professional Power*
