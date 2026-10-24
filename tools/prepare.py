"""Préparation de la construction : icônes (.ico / .icns) tirées du logo intégré au script, et numéro de version
+ dépôt GitHub inscrits dans le script (pour le bouton « Mise à jour »)."""
import ast
import base64
import io
import os
import re
import sys

from PIL import Image

SRC = "broadcast_tool_qt.py"
os.makedirs("build", exist_ok=True)
src = open(SRC, encoding="utf-8").read()

# 1) icônes
for node in ast.parse(src).body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_ICON_B64" for t in node.targets):
        v = ast.literal_eval(node.value)
        img = Image.open(io.BytesIO(base64.b64decode("".join(v) if not isinstance(v, str) else v))).convert("RGBA")
        img.save("build/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        img.resize((512, 512), Image.LANCZOS).save("build/icon.icns")
        img.save("build/icon.png")
        print("Icônes prêtes.")
        break
else:
    print("Logo introuvable dans le script : construction sans icône.")

# 2) version et dépôt (seulement pour une version publiée : tag v1.2.3)
tag = os.environ.get("TAG", "")
repo = os.environ.get("REPO", "")
if re.match(r"^v?\d+(\.\d+)*$", tag):
    src = re.sub(r'^VERSION = ".*?"', f'VERSION = "{tag.lstrip("v")}"', src, count=1, flags=re.M)
if repo:
    src = re.sub(r'^UPDATE_REPO = ".*?"', f'UPDATE_REPO = "{repo}"', src, count=1, flags=re.M)
open(SRC, "w", encoding="utf-8").write(src)
print("Version :", tag or "(non publiée)", "· dépôt :", repo or "(aucun)")
