; installer.iss
; ==============
; Inno Setup script for ESP32 Multi Flash Manager.
;
; Expects the PyInstaller onefile build to already exist at
; dist\ESP32MultiFlashManager.exe (see packaging/windows/build_installer.ps1,
; which runs both steps in order). Produces a single Setup.exe that:
;
;   - Shows a license agreement page (LICENSE, MIT) before install.
;   - Lets the user choose "install for me only" (no admin needed) or
;     "install for all users" (requires admin elevation) — the modern
;     Inno Setup 6 recommended pattern, via PrivilegesRequiredOverridesAllowed.
;   - Installs under Program Files (or the per-user equivalent), with a
;     Start Menu group (app, uninstall, README, LICENSE, website links) and
;     an optional Desktop shortcut.
;   - Registers the .emfm extension so double-clicking a project file
;     launches the app directly with that project pre-loaded (handled by
;     _project_path_from_argv() in app/main.py). The older .efmproj
;     extension is also registered and opens the same way for backward
;     compatibility -- the app itself then requires a Save As into the
;     new .emfm format rather than silently resaving in the old one.
;   - Gives .emfm (and legacy .efmproj) files their own icon and a
;     friendly "ESP32 Multi Flash Manager Project" file type name in
;     Explorer.
;   - Shows a clean, fully-populated entry in "Apps & features" / Control
;     Panel > Programs (name, publisher, version, icon, support/website
;     links, estimated size) via Inno Setup's standard Uninstall registry
;     entries, composed automatically from the [Setup] keys below.
;   - Detects and prompts to close a running instance before
;     upgrading/reinstalling, and supports clean silent upgrades from a
;     previous version (same AppId, so Setup replaces in place rather than
;     installing side-by-side).
;   - Installs a clean uninstaller (Add/Remove Programs + Start Menu entry)
;     that also removes the file association and Start Menu group.
;   - After installation, offers a "View what's new" checkbox (unchecked
;     by default) on the final wizard page. There is no bundled changelog
;     file -- checking it just opens the GitHub Releases page in the
;     user's browser, since that's always the authoritative, up-to-date
;     changelog. Handled by the [Run] entry below.
;   - Drops a small install_marker.txt file next to the exe so a frozen
;     build can tell it was installed (vs. run as a bare portable exe).
;     app/utilities/update_checker.py reads this at runtime to decide
;     whether "Check for Updates" should offer the installer asset or the
;     portable asset for the next release.
;
; AppVersion is passed in from CI via /DAppVersion=x.y.z so it never drifts
; from the git tag; it defaults to app/utilities/constants.py's APP_VERSION
; for manual/local builds. Keep that default in sync if you bump it there.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

#define AppName "ESP32 Multi Flash Manager"
#define AppExeName "ESP32MultiFlashManager.exe"
#define AppPublisher "Somangshu Das"
#define AppURL "https://github.com/SomangshuDas/esp32-multi-flash-manager"
#define AppSupportURL "https://github.com/SomangshuDas/esp32-multi-flash-manager/issues"
#define AppReleasesURL "https://github.com/SomangshuDas/esp32-multi-flash-manager/releases"
#define ProjectExt ".emfm"
#define ProjectExtLegacy ".efmproj"
#define ProgId "ESP32MultiFlashManager.Project"

[Setup]
AppId={{DAFF0E90-494F-4FF8-84F2-600F9CFA05B6}
AppName={#AppName}
AppVerName={#AppName} {#AppVersion}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppSupportURL}
AppUpdatesURL={#AppURL}
AppContact={#AppPublisher}
AppCopyright=Copyright (C) {#AppPublisher}
; Modern per-user/per-machine choice: no admin needed unless the user
; explicitly picks "install for all users" on the Select Destination page.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\ESP32MultiFlashManager
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist\installer
OutputBaseFilename=ESP32MultiFlashManagerSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\..\resources\icons\app_icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
WizardStyle=modern
; Qt6/PySide6 requires Windows 10 or later.
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible arm64
; Close a running instance automatically (with confirmation) before an
; upgrade/reinstall instead of failing with a file-in-use error.
CloseApplications=yes
RestartApplications=yes
CloseApplicationsFilter=*.exe
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"
Name: "associate"; Description: "Open .emfm project files with {#AppName}"; GroupDescription: "File association:"

[Files]
Source: "..\..\dist\ESP32MultiFlashManager.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\resources\icons\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion; DestName: "README.txt"
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion; DestName: "LICENSE.txt"
Source: "install_marker.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Launch {#AppName}"
Name: "{group}\README"; Filename: "{app}\README.txt"; Comment: "Open the README"
Name: "{group}\License (MIT)"; Filename: "{app}\LICENSE.txt"; Comment: "View the MIT license"
Name: "{group}\{#AppName} on GitHub"; Filename: "{#AppURL}"; Comment: "Project homepage and source code"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"; Comment: "Remove {#AppName} from this computer"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; File association for .emfm -> our ProgId, only when the "associate"
; task is checked. Written under HKCU so it needs no elevation beyond what
; the installer already has, and is cleanly removed on uninstall — this
; also means the association is per-user, matching the per-user/per-machine
; install choice above.
Root: HKCU; Subkey: "Software\Classes\{#ProjectExt}"; ValueType: string; ValueName: ""; ValueData: "{#ProgId}"; Flags: uninsdeletevalue; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "ESP32 Multi Flash Manager Project"; Flags: uninsdeletekey; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\app_icon.ico"; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: associate
; Legacy .efmproj extension -> the SAME ProgId, so double-clicking an old
; project file still opens the app (which then forces a Save As into the
; new .emfm format instead of resaving in place -- see
; ProjectController.open_project's legacy handling).
Root: HKCU; Subkey: "Software\Classes\{#ProjectExtLegacy}"; ValueType: string; ValueName: ""; ValueData: "{#ProgId}"; Flags: uninsdeletevalue; Tasks: associate
; Explorer "new file type" friendliness — shows our icon/name in the
; "Open with" picker even before a file has been associated.
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExeName}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExeName}\SupportedTypes"; ValueType: string; ValueName: "{#ProjectExt}"; ValueData: ""; Tasks: associate
Root: HKCU; Subkey: "Software\Classes\Applications\{#AppExeName}\SupportedTypes"; ValueType: string; ValueName: "{#ProjectExtLegacy}"; ValueData: ""; Tasks: associate

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\README.txt"; Description: "View the README"; Flags: postinstall shellexec skipifsilent unchecked
Filename: "{#AppReleasesURL}"; Description: "View what's new"; Flags: postinstall shellexec skipifsilent unchecked

[UninstallDelete]
Type: files; Name: "{app}\app_icon.ico"
Type: files; Name: "{app}\LICENSE.txt"
Type: files; Name: "{app}\README.txt"
Type: files; Name: "{app}\install_marker.txt"

[Code]
{ Explorer needs a nudge to notice a new/changed file association right
  away, otherwise .emfm/.efmproj icons/behavior won't refresh until next login. }
procedure SHChangeNotify(wEventId: Longint; uFlags: Longint; dwItem1: Longint; dwItem2: Longint);
external 'SHChangeNotify@shell32.dll stdcall';

const
  SHCNE_ASSOCCHANGED = $08000000;
  SHCNF_IDLIST = $0000;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0);
end;

// ------------------------------------------------------------------------
// Uninstall: user data (logs, firmware profiles, settings.json, recent
// projects, the "keep" defaults, everything) lives entirely under
// %APPDATA%\ESP32MultiFlashManager -- never in the registry and never
// inside the app folder -- precisely so it can be offered as a choice
// here instead of being silently deleted (or silently orphaned) alongside
// the program files. [UninstallDelete] above only ever touches files
// under {app}.
// ------------------------------------------------------------------------
function AppDataFolder(): String;
begin
  Result := ExpandConstant('{userappdata}\ESP32MultiFlashManager');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataFolder: String;
  KeepData: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataFolder := AppDataFolder();
    if DirExists(DataFolder) then
    begin
      KeepData := MsgBox(
        'Keep your logs, firmware profiles, settings, and recent-projects list?' + #13#10 + #13#10 +
        'Choose Yes to leave that data in place (e.g. for a future reinstall).' + #13#10 +
        'Choose No to remove it too, deleting the entire ' + DataFolder + ' folder.',
        mbConfirmation, MB_YESNO);
      if KeepData = IDNO then
        DelTree(DataFolder, True, True, True);
    end;
  end;
end;
