#define AppName "TTDL 2"

[Setup]
AppId=electblake.TTDL2
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=electblake
DefaultDirName={localappdata}\Programs\TTDL2
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\{#AppVersion}
OutputBaseFilename=TTDL2-{#AppVersion}-windows-x64-Setup
SetupIconFile=..\assets\purple\ttdl2-icon-purple.ico
UninstallDisplayIcon={app}\app\assets\purple\ttdl2-icon-purple.ico
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
SetupLogging=yes

[Files]
Source: "..\build\bootstrap\uv\uv.exe"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\build\bootstrap\LICENSE-*"; DestDir: "{app}\tools\licenses"; Flags: ignoreversion
Source: "..\tiktok_downloader\*.py"; DestDir: "{app}\app\tiktok_downloader"; Flags: ignoreversion
Source: "..\assets\purple\ttdl2-icon-purple.ico"; DestDir: "{app}\app\assets\purple"; Flags: ignoreversion
Source: "..\pyproject.toml"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\uv.lock"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "install-runtime.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\runtime\venv\Scripts\pythonw.exe"; Parameters: "-I -m tiktok_downloader"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\purple\ttdl2-icon-purple.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\runtime\venv\Scripts\pythonw.exe"; Parameters: "-I -m tiktok_downloader"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\purple\ttdl2-icon-purple.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\venv\Scripts\pythonw.exe"; Parameters: "-I -m tiktok_downloader"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent; Check: DependenciesInstalled

[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime"

[Code]
var
  DependencyExitCode: Integer;
  DependencyLog: TNewMemo;

procedure InitializeWizard;
begin
  DependencyLog := TNewMemo.Create(WizardForm);
  DependencyLog.Parent := WizardForm.InstallingPage;
  DependencyLog.SetBounds(0, ScaleY(100), WizardForm.InstallingPage.Width,
    WizardForm.InstallingPage.Height - ScaleY(100));
  DependencyLog.ReadOnly := True;
  DependencyLog.ScrollBars := ssVertical;
end;

procedure DependencyOutput(const S: String; const Error, FirstLine: Boolean);
begin
  Log(S);
  DependencyLog.Lines.Add(S);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    WizardForm.StatusLabel.Caption := 'Installing Python, dependencies, and Chromium...';
    ExecAndLogOutput('pwsh.exe',
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\scripts\install-runtime.ps1') + '"',
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, DependencyExitCode, @DependencyOutput);
    Log('Dependency setup exit code: ' + IntToStr(DependencyExitCode));
  end;
end;

function DependenciesInstalled: Boolean;
begin
  Result := DependencyExitCode = 0;
end;

function GetCustomSetupExitCode: Integer;
begin
  Result := DependencyExitCode;
end;
