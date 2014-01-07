; -- MapMbTiles.iss --
;

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{51E692DF-521D-4F83-B021-B0D2C4BFA25C}
AppName=MapMbTiles
AppVerName=MapMbTiles version 1.0 alpha3
AppPublisher=Petr Pridal - Klokan
AppPublisherURL=http://www.mapmbtiles.com/
AppSupportURL=http://help.mapmbtiles.org/
AppUpdatesURL=http://www.mapmbtiles.org/
DefaultDirName={pf}\MapMbTiles
DefaultGroupName=MapMbTiles
LicenseFile=resources\license\LICENSE.txt
OutputBaseFilename=mapmbtiles-1.0-alpha3-setup
Compression=lzma
SolidCompression=yes
UninstallDisplayIcon={app}\mapmbtiles.exe

[Files]
Source: "dist\*"; DestDir: "{app}"
Source: "dist\proj\*"; DestDir: "{app}\proj\"
Source: "dist\gdal\*"; DestDir: "{app}\gdal\"
Source: "dist\gdalplugins\*"; DestDir: "{app}\gdalplugins\"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Icons]
Name: "{group}\MapMbTiles 1.0 alpha3"; Filename: "{app}\mapmbtiles.exe"; WorkingDir: "{app}"
Name: "{group}\{cm:ProgramOnTheWeb,MapMbTiles}"; Filename: "http://www.mapmbtiles.org/"
Name: "{group}\Uninstall MapMbTiles"; Filename: "{uninstallexe}"
Name: "{commondesktop}\MapMbTiles"; Filename: "{app}\mapmbtiles.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\mapmbtiles.exe"; Description: "{cm:LaunchProgram,MapMbTiles}"; Flags: nowait postinstall skipifsilent
