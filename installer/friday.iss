; Friday Windows 安装包 — Inno Setup 6
; 构建：scripts/build-installer.ps1（会先准备 installer/stage/Friday）

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName "星期五"
#define MyAppNameEn "Friday"
#define MyAppPublisher "Friday"
#define MyAppExeName "Friday.exe"
#define MyAppId "{{A7B3C9D1-4E2F-5A6B-8C9D-0E1F2A3B4C5D}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=Friday-Setup-{#MyAppVersion}
SetupIconFile=..\assets\friday.ico
UninstallDisplayIcon={app}\app.ico
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
LanguageDetectionMethod=locale
ShowLanguageDialog=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} - AI 电脑管家
VersionInfoProductName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: unchecked

[Files]
Source: "stage\Friday\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{code:GetFridayExePath}"; WorkingDir: "{code:GetFridayWorkingDir}"; IconFilename: "{app}\app.ico"; Comment: "星期五 - AI 电脑管家"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{code:GetFridayExePath}"; Tasks: desktopicon; WorkingDir: "{code:GetFridayWorkingDir}"; IconFilename: "{app}\app.ico"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-ChildItem -LiteralPath '{app}' -Recurse -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"""; Flags: runhidden; StatusMsg: "正在解除文件锁定…"
Filename: "{code:GetFridayExePath}"; Parameters: "--install-launch"; WorkingDir: "{code:GetFridayWorkingDir}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent; Check: FridayExeExists

[UninstallDelete]
; 仅删除程序目录内容，不触碰 %APPDATA%\Friday 用户数据（无额外 UninstallDelete 规则）

[Code]
// 安装目录应直接包含 Friday.exe（不要选 ZIP 解压后的「外层」文件夹）。
// ZIP 解压是 父目录/Friday/Friday.exe；安装包则是 安装目录/Friday.exe。

function AllowSetForegroundWindow(dwProcessId: DWORD): BOOL;
  external 'AllowSetForegroundWindow@user32.dll stdcall';

function PrepareToRun(const Setup: Boolean; const ApplicationName, ApplicationPath, ApplicationParams, ApplicationDir: String): Boolean;
begin
  AllowSetForegroundWindow($FFFFFFFF);
  Result := True;
end;

function FindFridayExePath(const Base: String): String;
var
  Candidates: array[0..3] of String;
  I: Integer;
begin
  Candidates[0] := Base + '\Friday.exe';
  Candidates[1] := Base + '\星期五.exe';
  Candidates[2] := Base + '\Friday\Friday.exe';
  Candidates[3] := Base + '\Friday\星期五.exe';
  for I := 0 to 3 do
  begin
    if FileExists(Candidates[I]) then
    begin
      Result := Candidates[I];
      Exit;
    end;
  end;
  Result := Candidates[0];
end;

function GetFridayExePath(Param: String): String;
begin
  Result := FindFridayExePath(ExpandConstant('{app}'));
end;

function GetFridayWorkingDir(Param: String): String;
begin
  Result := ExtractFileDir(FindFridayExePath(ExpandConstant('{app}')));
end;

function FridayExeExists: Boolean;
var
  ExePath, AppDir, Msg: String;
begin
  AppDir := ExpandConstant('{app}');
  ExePath := FindFridayExePath(AppDir);
  Result := FileExists(ExePath);
  if not Result then
  begin
    Msg :=
      '安装已完成，但未找到主程序 Friday.exe。' + #13#10 + #13#10 +
      '安装目录：' + AppDir + #13#10 +
      '尝试路径：' + ExePath + #13#10 + #13#10 +
      '建议：' + #13#10 +
      '1. 卸载后重新安装，目录选默认（无需管理员）：' + #13#10 +
      '   %LOCALAPPDATA%\Programs\Friday' + #13#10 +
      '2. 或选空文件夹，确保安装后该文件夹内直接有 Friday.exe' + #13#10 +
      '   （不要选 ZIP 解压后的外层目录）' + #13#10 +
      '3. 检查杀毒软件是否隔离了 Friday.exe';
    MsgBox(Msg, mbError, MB_OK);
  end;
end;

procedure InitializeWizard();
begin
  WizardForm.DirEdit.Text := ExpandConstant('{localappdata}\Programs\Friday');
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then
  begin
    WizardForm.SelectDirLabel.Caption :=
      '请选择安装位置。安装完成后，该文件夹内将直接包含 Friday.exe（与 ZIP 解压的「Friday 子文件夹」不同）。' + #13#10 +
      '推荐保持默认路径，无需管理员权限。';
  end;
end;
