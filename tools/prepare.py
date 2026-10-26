"""Préparation de la construction :
1) icônes (.ico / .icns / .png) tirées du logo intégré au script ;
2) image de démarrage (build/splash.png), affichée dès le double-clic sur Bev, avant même le chargement de l'application ;
3) numéro de version + dépôt GitHub inscrits dans le script (bouton « Mise à jour »), et build/version.txt pour l'installateur."""
import ast
import base64
import io
import os
import re

from PIL import Image, ImageDraw, ImageFont

SRC = "broadcast_tool_qt.py"
os.makedirs("build", exist_ok=True)
src = open(SRC, encoding="utf-8").read()


def font(size, bold=True):
    for f in (("segoeuib.ttf" if bold else "segoeui.ttf"), ("arialbd.ttf" if bold else "arial.ttf"),
              "/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        for base in ("", "C:/Windows/Fonts/"):
            try:
                return ImageFont.truetype(base + f, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


# 1) icônes
logo = None
for node in ast.parse(open("bev_assets.py", encoding="utf-8").read()).body:     # le logo est rangé avec les polices
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "_ICON_B64" for t in node.targets):
        v = ast.literal_eval(node.value)
        logo = Image.open(io.BytesIO(base64.b64decode("".join(v) if not isinstance(v, str) else v))).convert("RGBA")
        logo.save("build/icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        logo.resize((512, 512), Image.LANCZOS).save("build/icon.icns")
        logo.save("build/icon.png")
        print("Icônes prêtes.")
        break
else:
    print("Logo introuvable dans le script : construction sans icône.")

# 2) image de démarrage (même ambiance que l'application : bleu marine du phare, ambre des ondes)
W, H = 460, 270
im = Image.new("RGB", (W, H), (11, 31, 58))
d = ImageDraw.Draw(im)
for y in range(H):                                   # léger dégradé vers la mer
    t = y / H
    d.line([(0, y), (W, y)], fill=(int(11 + 6 * t), int(31 + 14 * t), int(58 + 22 * t)))
if logo is not None:
    lg = logo.resize((132, 132), Image.LANCZOS)
    im.paste(lg, (36, 58), lg)
d.text((196, 66), "Bev", font=font(64), fill=(255, 255, 255))
d.text((200, 146), "BROADCAST TOOL", font=font(15, False), fill=(255, 210, 122))
d.text((200, 176), "Démarrage…", font=font(15, False), fill=(170, 186, 210))
d.rectangle([0, 0, W - 1, H - 1], outline=(40, 66, 104), width=2)
im.save("build/splash.png")
# mieux : la toute première image de l'animation de démarrage de Bev (même dessin, même taille) : l'image affichée dès le
# double-clic et l'animation qui prend le relais ne font plus qu'une
try:
    import subprocess
    import sys
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    subprocess.run([sys.executable, SRC, "--render-splash", os.path.abspath("build/splash.png")], env=env, timeout=120, check=True)
    print("Image de démarrage prête (première image de l'animation).")
except Exception as ex:
    print("Image de démarrage prête (version simple : %s)." % ex)

# 3) version et dépôt (seulement pour une version publiée : tag v1.2.3)
tag = os.environ.get("TAG", "")
repo = os.environ.get("REPO", "")
if re.match(r"^v?\d+(\.\d+)*$", tag):
    src = re.sub(r'^VERSION = ".*?"', f'VERSION = "{tag.lstrip("v")}"', src, count=1, flags=re.M)
if repo:
    src = re.sub(r'^UPDATE_REPO = ".*?"', f'UPDATE_REPO = "{repo}"', src, count=1, flags=re.M)
open(SRC, "w", encoding="utf-8").write(src)
ver = re.search(r'^VERSION = "(.*?)"', src, re.M).group(1)
open("build/version.txt", "w").write(ver)
print("Version :", ver, "(publiée)" if tag else "(non publiée)", "· dépôt :", repo or "(aucun)")
