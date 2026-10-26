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

Signature de code (recommandée pour l'installateur complet) : voir l'en-tête de `.github/workflows/build.yml` (Azure Artifact Signing, activé automatiquement dès que les secrets sont renseignés).

## Le code
- `broadcast_tool_qt.py` : point d'entrée et interface (Qt / PySide6), version, mise à jour express.
- `bev_core.py` : cœur sans interface — moteur audio (capture, mixage, playlist de secours, cartouches, processeur d'antenne), sorties (Internet, FM, DAB+, enregistrement), réseau, processus moteur séparé. N'importe jamais Qt.
- `bev_assets.py` : polices et logo intégrés.
- `tools/` : préparation de la construction (`prepare.py`) et fichier de mise à jour express (`express.py`, qui réunit tous les modules en un seul fichier).
- `tests/` : tests automatiques (`python -m pytest tests`), lancés par GitHub à chaque envoi de code, avant toute publication.
