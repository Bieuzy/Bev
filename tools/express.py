"""Mise à jour express : prépare les deux fichiers joints à chaque Release GitHub.
  dist-express/bev-x.y.z.py   le code de Bev de cette version, en UN seul fichier (voir plus bas)
  dist-express/bev-maj.json   le manifeste : version, socle (RUNTIME), empreinte SHA-256, taille, modules nécessaires
Bev déjà installé télécharge ce fichier (~1 Mo) au lieu de l'installateur complet, vérifie l'empreinte et que tous les
modules nécessaires sont présents dans son socle, puis redémarre dessus. Sinon, il propose l'installateur complet.

Le code de Bev est réparti en plusieurs modules (broadcast_tool_qt.py, bev_core.py, bev_assets.py). Le fichier express les
réunit : un court préambule, puis le texte de chaque module. Au lancement, le préambule
  - installe bev_core et bev_assets de CETTE version (et non ceux de l'exécutable installé, plus anciens) ;
  - garde le code compilé en cache (dossier « cache » à côté) : Bev et son moteur audio ne recompilent plus 1 Mo de code
    à chaque démarrage ;
  - pour le moteur audio (--bev-engine), ne charge que bev_core : ni interface, ni Qt.
Un seul fichier : les Bev déjà installés (même en 1.1.1, avant ce découpage) savent l'utiliser tel quel.

Utilisation (GitHub Actions) : TAG=v1.2.3 REPO=compte/depot python tools/express.py"""
import ast
import hashlib
import json
import os
import re
import sys

SRC = "broadcast_tool_qt.py"
MODULES = ("bev_core", "bev_assets")          # modules de Bev livrés DANS le fichier express
OUT = "dist-express"
WINDOWS_ONLY = {"pyaudiowpatch", "winreg", "msvcrt", "winsound"}    # n'existent (et ne servent) que sous Windows

PREAMBLE = '''# Bev {ver} : mise à jour express (fichier produit par tools/express.py, ne pas modifier à la main).
# Contient tout le code de Bev : modules {mods} puis le programme principal.
import hashlib as _bh
import importlib.util as _bi
import marshal as _bm
import os as _bo
import sys as _bs
import types as _bt


def _bev_code(name, src):
    """Code compilé de ce module : lu dans le cache s'il existe (démarrage rapide), sinon compilé puis mis en cache."""
    fn = _bo.path.join(_bo.path.dirname(_bo.path.abspath(__file__)), name + ".py")
    key = _bh.sha256(src.encode("utf-8")).hexdigest()[:16] + "-" + _bi.MAGIC_NUMBER.hex()
    d = _bo.path.join(_bo.path.dirname(_bo.path.abspath(__file__)), "cache")
    f = _bo.path.join(d, name + "-" + key + ".bin")
    try:
        with open(f, "rb") as fh:
            return _bm.load(fh)
    except Exception:
        pass
    code = compile(src, fn, "exec")
    try:
        _bo.makedirs(d, exist_ok=True)
        for old in _bo.listdir(d):                              # anciennes versions de ce module : retirées
            if old.startswith(name + "-") and old != name + "-" + key + ".bin":
                try:
                    _bo.remove(_bo.path.join(d, old))
                except OSError:
                    pass
        with open(f + ".tmp", "wb") as fh:
            _bm.dump(code, fh)
        _bo.replace(f + ".tmp", f)
    except OSError:
        pass
    return code


def _bev_module(name):
    m = _bt.ModuleType(name)
    m.__file__ = _bo.path.join(_bo.path.dirname(_bo.path.abspath(__file__)), name + ".py")
    _bs.modules[name] = m
    exec(_bev_code(name, _BEV_SRC[name]), m.__dict__)
    return m


_BEV_SRC = {sources}
_bev_core = _bev_module("bev_core")
if "--bev-engine" in _bs.argv:                                  # moteur audio : le cœur seul, sans interface ni Qt
    _engine_worker_main = _bev_core._engine_worker_main
else:
    _bev_module("bev_assets")
    exec(_bev_code("broadcast_tool_qt", _BEV_SRC["broadcast_tool_qt"]), globals())
'''


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
    return mods


def build(tag="", repo=""):
    """Le fichier express (texte) et la liste des modules du socle dont il a besoin."""
    srcs = {"broadcast_tool_qt": stamped(open(SRC, encoding="utf-8").read(), tag, repo)}
    for m in MODULES:
        srcs[m] = open(m + ".py", encoding="utf-8").read()
    mods = set()
    for name, s in srcs.items():
        compile(s, name + ".py", "exec")                   # chaque module doit être correct
        mods |= required_modules(ast.parse(s))
    mods = sorted(m for m in mods if m.split(".")[0] not in MODULES)
    ver = re.search(r'^VERSION = "(.*?)"', srcs["broadcast_tool_qt"], re.M).group(1)
    runtime = int(re.search(r"^RUNTIME = (\d+)", srcs["broadcast_tool_qt"], re.M).group(1))
    order = {m: srcs[m] for m in (*MODULES, "broadcast_tool_qt")}
    body = "{\n" + "".join(f"    {k!r}: {v!r},\n" for k, v in order.items()) + "}"
    text = PREAMBLE.format(ver=ver, mods=", ".join(MODULES), sources=body)
    compile(text, "bev-express.py", "exec")
    return text, ver, runtime, mods


def main():
    text, ver, runtime, mods = build(os.environ.get("TAG", ""), os.environ.get("REPO", ""))
    os.makedirs(OUT, exist_ok=True)
    name = f"bev-{ver}.py"
    data = text.encode("utf-8")
    with open(os.path.join(OUT, name), "wb") as fh:
        fh.write(data)
    man = {"app": "Bev", "version": ver, "runtime": runtime, "file": name, "size": len(data),
           "sha256": hashlib.sha256(data).hexdigest()}
    man["modules"] = [m for m in mods if m.split(".")[0] not in WINDOWS_ONLY]
    man["windows_modules"] = [m for m in mods if m.split(".")[0] in WINDOWS_ONLY]
    with open(os.path.join(OUT, "bev-maj.json"), "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, ensure_ascii=False)
    print(f"Mise à jour express prête : {name} ({len(data) // 1024} Ko), socle {runtime}, {len(man['modules'])} modules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
