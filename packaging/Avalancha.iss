#define MyAppName "Avalancha"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Antisimetría SpA"
#define MyAppExeName "Avalancha.exe"

[Setup]
SetupArchitecture=x64
AppId=BE6AA14A-2F55-5EAD-8AF9-067C70318BF2
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion=0.1.0.0
DefaultDirName={localappdata}\Programs\Avalancha
DefaultGroupName=Avalancha
PrivilegesRequired=lowest
UsePreviousAppDir=yes
UsePreviousGroup=yes
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Avalancha_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
Uninstallable=yes
CreateUninstallRegKey=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Avalancha"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Avalancha"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Avalancha"; Flags: nowait postinstall skipifsilent
