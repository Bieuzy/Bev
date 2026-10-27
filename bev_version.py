# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev - version, dépôt des mises à jour et état de la mise à jour express.
Lu en tout premier (avant l'interface) : broadcast_tool_qt.py en a besoin pour choisir entre la version installée
et un code express plus récent. tools/prepare.py et tools/express.py y inscrivent la version et le dépôt."""
import json
import os
import re
import sys
import time


# ======================================================================================================================
# VERSION ET MISE À JOUR EXPRESS
# La plupart des versions de Bev ne changent que son code (ses fichiers .py). Plutôt que de télécharger et d'exécuter un nouvel
# installateur de 190 Mo (non signé : Smart App Control, SmartScreen et certains antivirus le bloquent), Bev télécharge
# seulement le nouveau code (~1 Mo), vérifie son empreinte SHA-256, puis redémarre dessus. L'exécutable installé, lui, ne
# change pas : rien de nouveau à « exécuter » pour Windows, pas de droits administrateur, pas de pare-feu à convaincre.
# Garde-fous : le code express n'est utilisé que s'il est plus récent que la version installée, prévu pour le même « socle »
# (RUNTIME : exécutable, Python et bibliothèques), intact (empreinte), et s'il démarre bien ; après deux démarrages ratés,
# Bev revient tout seul à la version installée. Le moteur audio (processus séparé) suit toujours le code de l'interface.
# RUNTIME est à augmenter quand le socle change (nouvelle bibliothèque, nouvelle version de Python, de PySide6, de ffmpeg…) :
# les versions concernées passent alors par l'installateur complet.
# ======================================================================================================================
VERSION = "1.3.0"
RUNTIME = 1
UPD_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser(
    "~/Library/Application Support" if sys.platform == "darwin" else "~/.local/share"), "Bev", "maj")
UPD_STATE = os.path.join(UPD_DIR, "actuel.json")


def _ver_tuple(s):
    return tuple(int(n) for n in re.findall(r"\d+", str(s).split("-")[0])[:4]) or (0,)


def express_log(msg):
    try:
        os.makedirs(UPD_DIR, exist_ok=True)
        with open(os.path.join(UPD_DIR, "journal.txt"), "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def express_state(update=None):
    """État de la mise à jour express (actuel.json) ; update : champs à modifier (écriture atomique)."""
    try:
        with open(UPD_STATE, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        st = {}
    if update:
        st.update(update)
        try:
            os.makedirs(UPD_DIR, exist_ok=True)
            with open(UPD_STATE + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(st, fh)
            os.replace(UPD_STATE + ".tmp", UPD_STATE)
        except OSError:
            pass
    return st


UPDATE_REPO = ""  # "compte/depot" GitHub où sont publiées les Releases (vide = vérification désactivée)
# Clé PUBLIQUE de signature des mises à jour (64 caractères hexadécimaux, produite par « python tools/signer.py cle »).
# Renseignée, Bev n'accepte plus que des versions dont le manifeste (bev-maj.json) est signé par la clé privée de
# l'auteur, gardée hors de GitHub : un compte GitHub piraté ne suffit plus à envoyer du code aux radios.
UPDATE_PUBKEY = ""


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
