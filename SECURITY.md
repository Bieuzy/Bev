# Sécurité de Bev

## Signaler une faille
Merci de **ne pas publier** une faille dans une issue publique : des radios utilisent Bev à l'antenne.
Utilisez « Report a vulnerability » dans l'onglet **Security** de ce dépôt (signalement privé). Nous répondons dès que possible.

## Versions suivies
Seule la dernière version publiée reçoit des correctifs. Bev propose lui-même la mise à jour.

## Ce que Bev protège
- **Mises à jour** : le manifeste de chaque version est signé (Ed25519) sur l'ordinateur de l'auteur ; Bev refuse une version non signée ou mal signée, et vérifie l'empreinte du code et de l'installateur avant de les utiliser.
- **Mots de passe** (serveurs, mail, SMS, clé de Gaël) : chiffrés dans le fichier de réglages sous Windows (DPAPI, liés au compte Windows), masqués dans les journaux et les alertes.
- **Automate de diffusion** : serveur désactivé par défaut, limité à l'ordinateur ; code secret exigé des autres postes du réseau local ; demandes venues d'un navigateur refusées sans ce code.
- **Construction** : FFmpeg en version figée et vérifiée, actions GitHub figées, droits d'écriture limités aux tâches qui publient.
