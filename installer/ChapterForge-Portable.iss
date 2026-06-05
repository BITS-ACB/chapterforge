; Inno Setup script for ChapterForge - Portable Edition
; Produces a self-extracting portable archive that can be run from any folder
; (USB drive, network share, etc.) without installing to Program Files.
;
; Build steps:
;   1. pyinstaller ChapterForge.spec          -> dist\ChapterForge\
;   2. iscc installer\ChapterForge-Portable.iss -> installer_output\ChapterForge-Portable.exe

#define AppName "ChapterForge"
#define AppVersion "1.81"
#define AppPublisher "Blind Information Technology Specialists (BITS)"
#define AppExeName "ChapterForge.exe"
#define CliExeName "chapterforge-cli.exe"

[Setup]
AppId={{B4D8E8E2-2C2E-4C7E-9E2A-CHAPTERFORGE02}}
AppName={#AppName} (Portable)
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
; Default to the folder the user selects - no Program Files assumption
DefaultDirName={sd}\{#AppName}
DefaultGroupName={#AppName}
; Portable: no Start Menu group, no uninstaller, no registry writes
DisableProgramGroupPage=yes
CreateUninstallRegKey=no
UpdateUninstallLogAppName=no
Uninstallable=no
; Drop all files flat into the chosen folder
DisableDirPage=no
OutputDir=..\installer_output
OutputBaseFilename={#AppName}-Portable
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; All PyInstaller output into the chosen folder.
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
