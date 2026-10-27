# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Signature des mises à jour de Bev — à lancer sur l'ORDINATEUR DE L'AUTEUR, jamais sur GitHub.

Pourquoi : Bev télécharge et exécute le code des nouvelles versions. Si quelqu'un prenait le contrôle du compte GitHub,
il pourrait envoyer son propre code à toutes les radios. Avec la signature, Bev exige en plus une preuve que seule la
clé privée de l'auteur peut produire. Cette clé reste sur cet ordinateur : elle n'est jamais envoyée à GitHub.

1) Une seule fois : créer la clé
       python tools/signer.py cle
   -> crée la clé privée (dossier .bev-signature de ton dossier personnel) et affiche la clé PUBLIQUE, à recopier dans
      bev_version.py, ligne UPDATE_PUBKEY = "...". SAUVEGARDE la clé privée (clé USB rangée à part) : perdue,
      il faudrait repasser toutes les radios par l'installateur complet avec une nouvelle clé.

2) À chaque Release publiée, quand GitHub a fini de construire (coche verte dans « Actions ») :
       python tools/signer.py signer v1.2.1
   -> télécharge le manifeste de cette version, vérifie qu'il est bien celui de cette version, le signe et crée
      bev-maj.json.sig dans le dossier courant. Il reste à le glisser dans la Release (Modifier > zone des fichiers
      joints > Update release). Les Bev la proposent alors aux radios.

   Variante sans Internet : python tools/signer.py signer chemin/vers/bev-maj.json
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bev_core import ed25519_public, ed25519_sign, ed25519_verify  # noqa: E402

REPO = "Bieuzy/Bev"
KEY_DIR = os.path.join(os.path.expanduser("~"), ".bev-signature")
KEY_FILE = os.path.join(KEY_DIR, "cle-privee.txt")


def load_key():
    try:
        with open(KEY_FILE, encoding="ascii") as fh:
            seed = bytes.fromhex(fh.read().strip())
        if len(seed) != 32:
            raise ValueError
        return seed
    except (OSError, ValueError):
        sys.exit(f"Clé privée introuvable ou abîmée ({KEY_FILE}). Crée-la avec : python tools/signer.py cle")


def cmd_key():
    if os.path.exists(KEY_FILE):
        seed = load_key()
        print("Une clé existe déjà (elle n'est pas remplacée, pour ne pas casser les mises à jour).")
    else:
        os.makedirs(KEY_DIR, exist_ok=True)
        seed = os.urandom(32)
        fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(seed.hex() + "\n")
        print(f"Clé privée créée : {KEY_FILE}")
        print("  -> fais-en TOUT DE SUITE une copie sur une clé USB rangée à part. Ne la mets jamais sur GitHub.")
    print("\nClé PUBLIQUE à recopier dans bev_version.py :")
    print(f'UPDATE_PUBKEY = "{ed25519_public(seed).hex()}"')


def fetch(url):
    rq = urllib.request.Request(url, headers={"User-Agent": "Bev-signer"})
    with urllib.request.urlopen(rq, timeout=30) as r:
        return r.read(4_000_000)


def cmd_sign(what):
    seed = load_key()
    if os.path.isfile(what):
        with open(what, "rb") as fh:
            raw = fh.read()
        tag, out = "", what + ".sig"
    else:
        tag = what if what.lower().startswith("v") else "v" + what
        raw = fetch(f"https://github.com/{REPO}/releases/download/{tag}/bev-maj.json")
        out = "bev-maj.json.sig"
    man = json.loads(raw.decode("utf-8"))
    if man.get("app") != "Bev":
        sys.exit("Ce fichier n'est pas un manifeste de Bev : rien n'a été signé.")
    if tag and str(man.get("version")) != tag.lstrip("vV"):
        sys.exit(f"Le manifeste annonce la version {man.get('version')}, pas {tag} : rien n'a été signé.")
    print(f"Bev {man.get('version')} · code {man.get('file')} · empreinte {str(man.get('sha256'))[:16]}…")
    for name, h in (man.get("installers") or {}).items():
        print(f"  installateur {name} · {str(h)[:16]}…")
    if not man.get("installers"):
        print("  (attention : aucun installateur dans ce manifeste ; seule la mise à jour express sera proposée)")
    sig = ed25519_sign(seed, raw)
    if not ed25519_verify(ed25519_public(seed), raw, sig):
        sys.exit("Échec de la vérification de la signature : rien n'a été écrit.")
    with open(out, "w", encoding="ascii") as fh:
        fh.write(sig.hex() + "\n")
    print(f"\nSignature créée : {os.path.abspath(out)}")
    if tag:
        print(f"Glisse ce fichier dans la Release {tag} sur GitHub (Modifier la release > fichiers joints > Update release).")


def main(argv):
    if len(argv) >= 2 and argv[1] == "cle":
        return cmd_key()
    if len(argv) >= 3 and argv[1] == "signer":
        return cmd_sign(argv[2])
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv) or 0)
