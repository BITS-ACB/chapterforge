; Inno Setup script for ChapterForge
; Packages the PyInstaller one-folder output (dist\ChapterForge) into a single
; installer. One-folder is used so the app never extracts to a temp directory
; at launch (which is the failure mode of PyInstaller one-file builds).
;
; Build steps:
;   1. pyinstaller ChapterForge.spec            -> dist\ChapterForge\
;   2. iscc installer\ChapterForge.iss          -> installer_output\ChapterForge-Setup.exe

#define AppName "ChapterForge"
#define AppVersion "1.7.0"
#define AppPublisher "Blind Information Technology Specialists (BITS)"
#define AppExeName "ChapterForge.exe"
#define CliExeName "chapterforge-cli.exe"

[Setup]
AppId={{B4D8E8E2-2C2E-4C7E-9E2A-CHAPTERFORGE01}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\installer_output
OutputBaseFilename={#AppName}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Accessible installer: keep a setup log so issues can be diagnosed.
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
; The entire PyInstaller one-folder output, including bundled ffmpeg in bin\.
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} (Watch in tray)"; Filename: "{app}\{#AppExeName}"; Parameters: "--watch"; Comment: "Run the background folder watcher in the system tray"
Name: "{group}\{#AppName} Command Line"; Filename: "{app}\{#CliExeName}"; Comment: "Open ChapterForge command-line help"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
