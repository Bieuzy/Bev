# Bev

Diffusion radio multi-sorties (Internet, FM, DAB+, enregistrement), playlist de secours, cartoucheur, monitoring.
Portée par des radios associatives de Bretagne.

## Télécharger
Page de téléchargement : **https://bieuzy.github.io/bev/**

Onglet **Releases** de ce dépôt : `Bev-Setup-x.y.z.exe` (installateur Windows : menu Démarrer, raccourci, désinstallation, mises à jour depuis l'appli) ou `Bev-macOS.dmg` (Mac à puce Apple).

Premier lancement sur Mac : clic droit sur Bev > **Ouvrir** (l'application n'est pas signée par Apple).
Sous Windows, si SmartScreen s'affiche : **Informations complémentaires** > **Exécuter quand même**.

## Mises à jour
Depuis la 1.1.1, la plupart des versions s'installent **en express** depuis Bev : seul le code change (~1 Mo, empreinte vérifiée), Bev redémarre en quelques secondes, sans installateur, sans droits administrateur, sans rien que Smart App Control ou l'antivirus aient à bloquer. Quand une version change les bibliothèques (le « socle », `RUNTIME` dans le code), Bev propose l'installateur complet.

Signature de code (recommandée pour l'installateur complet) : voir l'en-tête de `.github/workflows/build.yml` (Azure Artifact Signing, activé automatiquement dès que les secrets sont renseignés).
