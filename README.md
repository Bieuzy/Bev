# Bev

Diffusion radio multi-sorties (Internet, FM, DAB+, enregistrement), playlist de secours, cartoucheur, monitoring.
Portée par des radios associatives de Bretagne.

## Télécharger
Page de téléchargement : **https://bieuzy.github.io/Bev/**

Onglet **Releases** de ce dépôt : `Bev-Setup-x.y.z.exe` (installateur Windows : menu Démarrer, raccourci, désinstallation, mises à jour depuis l'appli) ou `Bev-macOS.dmg` (Mac à puce Apple).

Premier lancement sur Mac : clic droit sur Bev > **Ouvrir** (l'application n'est pas signée par Apple).
Sous Windows, si SmartScreen s'affiche : **Informations complémentaires** > **Exécuter quand même**.

## Mises à jour
Depuis la 1.1.1, la plupart des versions s'installent **en express** depuis Bev : seul le code change (~1 Mo, empreinte vérifiée), Bev redémarre en quelques secondes, sans installateur, sans droits administrateur, sans rien que Smart App Control ou l'antivirus aient à bloquer. Quand une version change les bibliothèques (le « socle », `RUNTIME` dans le code), Bev propose l'installateur complet.

### Mises à jour signées
Bev télécharge et exécute le code des nouvelles versions : il doit être sûr qu'il vient de l'auteur, et pas seulement de GitHub. Le manifeste de chaque version (`bev-maj.json`, avec les empreintes du code et des installateurs) est donc signé **sur l'ordinateur de l'auteur**, avec une clé privée qui ne va jamais sur GitHub (`tools/signer.py`, signature Ed25519). Dès que la clé publique est inscrite dans `UPDATE_PUBKEY` (bev_version.py), Bev refuse toute version non signée ou mal signée.

1. Une seule fois : `python tools/signer.py cle`, recopier la clé publique affichée dans `UPDATE_PUBKEY`, et **sauvegarder la clé privée** (clé USB rangée à part).
2. À chaque Release, une fois la construction terminée : `python tools/signer.py signer v1.2.3`, puis joindre `bev-maj.json.sig` à la Release.

Signature de code (recommandée pour l'installateur complet) : voir l'en-tête de `.github/workflows/build.yml` (Azure Artifact Signing, activé automatiquement dès que les secrets sont renseignés).

## Le code
- `broadcast_tool_qt.py` : point d'entrée (mise à jour express, fenêtre unique, écran de démarrage, selftest).
- `bev_version.py` : version, dépôt des mises à jour, état de la mise à jour express.
- Interface (Qt / PySide6), un module par grande partie, chacun reprenant les noms du précédent : `bev_ui.py` (thème, widgets de base) → `bev_widgets.py` (entrée audio, décors, navigation, vumètres) → `bev_alertes.py` → `bev_maj.py` (mises à jour) → `bev_gael.py` (Gaël, animations) → `bev_secours.py` (playlist de secours) → `bev_dialogues.py` → `bev_cartoucheur.py` → `bev_pages.py` (Réglages, Enregistrement, À propos, Processeur) → `bev_monitoring.py` → `bev_assistant.py` (Gaël assistant) → `bev_sos.py` (Réseau, SOS) → `bev_bandeau.py` (annuler/rétablir, bulles, bandeaux) → `bev_diffusion.py` (page Diffusion, playlist de secours) → `bev_antenne.py` (flux, démarrage/arrêt, moteur, boucle d'affichage) → `bev_miseajour.py` (mises à jour vues de la fenêtre) → `bev_support.py` (prise en main, « Signaler un problème », erreurs et plantages) → `bev_fenetre.py` (fenêtre principale : construction, en-tête, profils).
- `bev_core.py` : cœur sans interface — moteur audio (capture, mixage, playlist de secours, cartouches, processeur d'antenne), sorties (Internet, FM, DAB+, enregistrement), réseau, processus moteur séparé. N'importe jamais Qt.
- `bev_assets.py` : polices et logo intégrés.
- `tools/` : préparation de la construction (`prepare.py`), banc de mesure de la fluidité (`perf.py`), fichier de mise à jour express (`express.py`, qui réunit tous les modules en un seul fichier) et signature des mises à jour (`signer.py`, sur l'ordinateur de l'auteur).
- `tests/` : tests automatiques (`python -m pytest tests`), lancés par GitHub à chaque envoi de code, avant toute publication.

## Licence
Bev est un logiciel libre : vous pouvez le redistribuer et le modifier selon les termes de la **GNU General Public License version 3** (ou, à votre choix, toute version ultérieure). Voir [LICENSE](LICENSE).
Bev est livré avec des composants d'autres auteurs (FFmpeg, Qt / PySide6, polices Inter et Space Grotesk…) : leurs licences et leurs sources sont indiquées dans [licences/MENTIONS-TIERCES.txt](licences/MENTIONS-TIERCES.txt).

## Signaler une faille
Une faille de sécurité ? Merci de ne pas la publier dans une issue : utilisez « Report a vulnerability » (onglet Security du dépôt).
