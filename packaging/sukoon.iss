; Inno Setup script for Sukoon (ADR-0001, ADR-0038). Build on Windows, after PyInstaller:
;   pyinstaller packaging\sukoon.spec
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\sukoon.iss
; The installer is unsigned (ADR-0038 section 12): Windows shows "Windows protected your PC";
; choose More info > Run anyway.

#define AppVersion "1.0.0"

[Setup]
AppId={{8E0B2F4C-2C7B-4F3C-9D55-5B1D0E7A6C31}
AppName=Sukoon
AppVersion={#AppVersion}
AppPublisher=Sukoon
DefaultDirName={autopf}\Sukoon
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=Sukoon-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Sukoon
CloseApplications=no

[Tasks]
Name: "desktopicon"; Description: "Put a Sukoon shortcut on the desktop"

[Files]
Source: "..\dist\Sukoon\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "install-sukoon.ps1"; DestDir: "{app}\setup"; Flags: ignoreversion
Source: "uninstall-sukoon.ps1"; DestDir: "{app}\setup"; Flags: ignoreversion
Source: "restore-backup.ps1"; DestDir: "{app}\setup"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Sukoon"; Filename: "{app}\Sukoon.exe"
Name: "{autodesktop}\Sukoon"; Filename: "{app}\Sukoon.exe"; Tasks: desktopicon

[Run]
; The server set-up script runs from [Code] (CurStepChanged), not here: [Run] ignores exit codes,
; and the first real install reported success after the script had failed.
Filename: "{app}\Sukoon.exe"; Description: "Open Sukoon now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup\uninstall-sukoon.ps1"""; \
  Flags: runhidden waituntilterminated; RunOnceId: "SukoonUninstall"

[Code]
function QuietFlag(Param: String): String;
begin
  { /SILENT or /VERYSILENT: the install script must not open a dialog nobody can close. }
  if WizardSilent then Result := '-Quiet' else Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Params: String;
begin
  if CurStep <> ssPostInstall then Exit;
  Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\setup\install-sukoon.ps1') +
            '" -AppDir "' + ExpandConstant('{app}') + '" ' + QuietFlag('');
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, '',
              SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    ResultCode := -1;
  Log('install-sukoon.ps1 finished with exit code ' + IntToStr(ResultCode));
  { 0: done. 10: done, with problems the script has already shown and logged. Anything else,
    including PowerShell's own failure exit of 1: it did not finish, and Sukoon will not run. }
  if (ResultCode <> 0) and (ResultCode <> 10) then
    SuppressibleMsgBox('Sukoon''s files are installed, but setting up its server did not finish, ' +
      'so Sukoon will not run yet.' + #13#10#13#10 + 'The reason is in ' +
      ExpandConstant('{commonappdata}') + '\Sukoon\install.log', mbError, MB_OK, IDOK);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { An upgrade replaces files the running server holds open. Pause the task first, so its
    five-minute watchdog can't start the server again halfway through the copy; the install
    script re-enables it. }
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/Change /TN "Sukoon Server" /DISABLE', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "Sukoon Server"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM sukoon-server.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Sukoon.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    SuppressibleMsgBox('Sukoon has been removed. The shop''s data was kept in ' +
      ExpandConstant('{commonappdata}') + '\Sukoon.', mbInformation, MB_OK, IDOK);
end;
