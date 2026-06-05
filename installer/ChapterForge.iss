; Inno Setup script for ChapterForge
; Packages the PyInstaller one-folder output (dist\ChapterForge) into a single
; installer. One-folder is used so the app never extracts to a temp directory
; at launch (which is the failure mode of PyInstaller one-file builds).
;
; The installer supports two modes selectable by the user:
;   Standard  - installs to Program Files, adds Start Menu and desktop shortcuts
;   Portable  - extracts to any folder the user picks (USB drive, network, etc.)
;               No Start Menu, no uninstaller, no registry entries.
;
; Build steps:
;   1. pyinstaller ChapterForge.spec            -> dist\ChapterForge\
;   2. iscc installer\ChapterForge.iss          -> installer_output\ChapterForge-Setup.exe

#define AppName "ChapterForge"
#define AppVersion "1.90"
#define AppPublisher "Blind Information Technology Solutions (BITS)"
#define AppExeName "ChapterForge.exe"
#define CliExeName "chapterforge-cli.exe"

[Setup]
AppId={{B4D8E8E2-2C2E-4C7E-9E2A-CHAPTERFORGE01}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableDirPage=no
DisableProgramGroupPage=no
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

[Types]
Name: "standard"; Description: "Standard installation (recommended)"
Name: "portable"; Description: "Portable - extract to any folder, no installation required"

[Components]
Name: "main"; Description: "{#AppName} application"; Types: standard portable; Flags: fixed

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Components: main; Check: IsStandardInstall

[Files]
; All PyInstaller output into the chosen folder.
Source: "..\dist\{#AppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Check: IsStandardInstall
Name: "{group}\{#AppName} (Watch in tray)"; Filename: "{app}\{#AppExeName}"; Parameters: "--watch"; Comment: "Run the background folder watcher in the system tray"; Check: IsStandardInstall
Name: "{group}\{#AppName} Command Line"; Filename: "{app}\{#CliExeName}"; Comment: "Open ChapterForge command-line help"; Check: IsStandardInstall
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"; Check: IsStandardInstall
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function IsStandardInstall: Boolean;
begin
  Result := WizardSetupType(False) = 'standard';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  UninstKeyPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    if not IsStandardInstall then
    begin
      // Portable mode: remove any uninstaller registry key that Inno Setup wrote
      UninstKeyPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
                       '{B4D8E8E2-2C2E-4C7E-9E2A-CHAPTERFORGE01}_is1';
      RegDeleteKeyIncludingSubkeys(HKEY_LOCAL_MACHINE, UninstKeyPath);
      RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, UninstKeyPath);
    end;
  end;
end;
