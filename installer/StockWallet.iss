; Inno Setup script for Stock Wallet.
; Build locally:  ISCC.exe installer\StockWallet.iss
; (CI passes the tag as version:  ISCC.exe /DAppVersion=v0.7.0 installer\StockWallet.iss)
; Requires dist\StockWallet.exe to exist (build it with PyInstaller first).

#define AppName "Stock Wallet"
#ifndef AppVersion
  #define AppVersion "0.7.0"
#endif

[Setup]
AppId={{8A9C2E1F-4B6D-4A3E-9F70-1C2D3E4F5A6B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Stock Wallet
DefaultDirName={autopf}\Stock Wallet
DefaultGroupName=Stock Wallet
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\StockWallet.exe
OutputDir=Output
OutputBaseFilename=StockWallet-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 需 64-bit Windows
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\StockWallet.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Stock Wallet"; Filename: "{app}\StockWallet.exe"
Name: "{group}\Uninstall Stock Wallet"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Stock Wallet"; Filename: "{app}\StockWallet.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\StockWallet.exe"; Description: "{cm:LaunchProgram,Stock Wallet}"; Flags: nowait postinstall skipifsilent
