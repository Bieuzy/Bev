; Installateur Windows de Bev (Inno Setup 6)
; Construit automatiquement par GitHub (.github/workflows/build.yml) : ISCC /DMyAppVersion=1.2.3 installer\bev.iss
; - installation sans droits administrateur (dans le profil de l'utilisateur), ou pour tous les utilisateurs si on le choisit ;
; - menu Démarrer, raccourci bureau (au choix), désinstallation propre ;
; - mise à jour : la nouvelle version s'installe par-dessus l'ancienne, réglages conservés ;
;   lancée depuis Bev (bouton « Installer »), elle attend que Bev soit fermé puis le rouvre toute seule.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.3"
#endif

[Setup]
AppId={{8F4C2A61-5B7E-4E2B-9A3D-B3E1C0D7F2A9}
AppName=Bev
AppVersion={#MyAppVersion}
AppVerName=Bev {#MyAppVersion}
AppPublisher=Radios associatives de Bretagne
AppComments=Bev (« direct » en breton) : diffusion radio, playlist de secours, cartoucheur, monitoring.
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName=Bev
DefaultDirName={autopf}\Bev
DefaultGroupName=Bev
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableReadyPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UsePreviousAppDir=yes
UsePreviousTasks=yes
UsePreviousPrivileges=yes
OutputDir=..\dist-installer
OutputBaseFilename=Bev-Setup-{#MyAppVersion}
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\Bev.exe
UninstallDisplayName=Bev
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
SetupMutex=BevRadioSetup

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; anciennes bibliothèques retirées avant la copie de la nouvelle version (pas de mélange de versions)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Bev\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Bev"; Filename: "{app}\Bev.exe"; Comment: "Diffusion radio"
Name: "{autodesktop}\Bev"; Filename: "{app}\Bev.exe"; Tasks: desktopicon

[Run]
; installation normale : case « Lancer Bev » à la fin
Filename: "{app}\Bev.exe"; Description: "{cm:LaunchProgram,Bev}"; Flags: nowait postinstall skipifsilent
; mise à jour lancée depuis Bev (mode silencieux) : Bev se rouvre tout seul
; (sauf /NORELAUNCH=1 : mise à jour installée à la fermeture de Bev, qu'on a fermé exprès)
Filename: "{app}\Bev.exe"; Flags: nowait runasoriginaluser; Check: WizardSilent and Relaunch

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function Relaunch(): Boolean;
begin
  Result := ExpandConstant('{param:NORELAUNCH|0}') <> '1';
end;

function BevRunning(): Boolean;
begin
  Result := CheckForMutexes('BevRadioApp') or CheckForMutexes('BevRadioEngine');
end;

function InitializeSetup(): Boolean;
var
  i: Integer;
begin
  Result := True;
  { mise à jour depuis Bev : on laisse à Bev (et à son moteur audio) le temps de se fermer proprement }
  i := 0;
  while BevRunning() and (i < 80) do
  begin
    Sleep(250);
    i := i + 1;
  end;
  if WizardSilent() then
    exit;   { en silencieux, le Gestionnaire de redémarrage ferme ce qui resterait ouvert }
  while BevRunning() do
  begin
    if MsgBox('Bev est encore ouvert. Ferme-le (arrête la diffusion si besoin), puis clique sur OK pour continuer.',
              mbInformation, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
      exit;
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  while BevRunning() do
  begin
    if MsgBox('Ferme Bev avant de le désinstaller, puis clique sur OK.', mbInformation, MB_OKCANCEL) = IDCANCEL then
    begin
      Result := False;
      exit;
    end;
  end;
end;
