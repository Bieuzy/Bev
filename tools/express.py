"""Mise à jour express : prépare les deux fichiers joints à chaque Release GitHub.
  dist-express/bev-x.y.z.py   le code de Bev de cette version (numéro de version et dépôt inscrits, comme dans l'application)
  dist-express/bev-maj.json   le manifeste : version, socle (RUNTIME), empreinte SHA-256, taille, modules nécessaires
Bev déjà installé télécharge ces ~1 Mo au lieu de l'installateur complet, vérifie l'empreinte et que tous les modules
nécessaires sont présents dans son socle, puis redémarre dessus. Sinon, il propose l'installateur complet.

Utilisation (GitHub Actions) : TAG=v1.2.3 REPO=compte/depot python tools/express.py"""
import ast
import hashlib
import json
import os
import re
import sys

SRC = "broadcast_tool_qt.py"
OUT = "dist-express"
WINDOWS_ONLY = {"pyaudiowpatch", "winreg", "msvcrt", "winsound"}    # n'existent (et ne servent) que sous Windows


def stamped(src, tag, repo):
    """Exactement les mêmes inscriptions que tools/prepare.py (le code express doit être identique à celui de l'exécutable)."""
    if re.match(r"^v?\d+(\.\d+)*$", tag):
        src = re.sub(r'^VERSION = ".*?"', f'VERSION = "{tag.lstrip("v")}"', src, count=1, flags=re.M)
    if repo:
        src = re.sub(r'^UPDATE_REPO = ".*?"', f'UPDATE_REPO = "{repo}"', src, count=1, flags=re.M)
    return src


def required_modules(tree):
    """Modules importés par le code, sauf ceux importés « à l'essai » (dans un try qui rattrape l'erreur d'import) :
    ceux-là sont facultatifs (propres à un système, ou remplacés s'ils manquent)."""
    optional_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            catches = False
            for h in node.handlers:
                names = []
                if h.type is None:
                    catches = True
                elif isinstance(h.type, ast.Tuple):
                    names = [getattr(e, "id", "") for e in h.type.elts]
                else:
                    names = [getattr(h.type, "id", "")]
                if set(names) & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
                    catches = True
            if catches:
                for b in node.body:
                    for sub in ast.walk(b):
                        optional_nodes.add(id(sub))
    mods = set()
    for node in ast.walk(tree):
        if id(node) in optional_nodes:
            continue
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods.add(node.module)
    return sorted(mods)


def main():
    tag = os.environ.get("TAG", "")
    repo = os.environ.get("REPO", "")
    src = stamped(open(SRC, encoding="utf-8").read(), tag, repo)
    tree = ast.parse(src)
    compile(src, SRC, "exec")
    ver = re.search(r'^VERSION = "(.*?)"', src, re.M).group(1)
    runtime = int(re.search(r"^RUNTIME = (\d+)", src, re.M).group(1))
    os.makedirs(OUT, exist_ok=True)
    name = f"bev-{ver}.py"
    data = src.encode("utf-8")
    with open(os.path.join(OUT, name), "wb") as fh:
        fh.write(data)
    man = {"app": "Bev", "version": ver, "runtime": runtime, "file": name, "size": len(data),
           "sha256": hashlib.sha256(data).hexdigest()}
    mods = required_modules(tree)
    man["modules"] = [m for m in mods if m.split(".")[0] not in WINDOWS_ONLY]
    man["windows_modules"] = [m for m in mods if m.split(".")[0] in WINDOWS_ONLY]
    with open(os.path.join(OUT, "bev-maj.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, ensure_ascii=False)
    print(f"Mise à jour express prête : {name} ({len(data) // 1024} Ko), socle {runtime}, {len(man['modules'])} modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
