# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Captures d'écran de Bev (sans écran : QT_QPA_PLATFORM=offscreen), pour vérifier l'interface à chaque modification.
Utilisation : python tools/captures.py [dossier]   -> un PNG par onglet et par taille de fenêtre.
Les états de l'antenne (flux en ligne, flux en panne, playlist de secours) sont simulés pour la page Diffusion."""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = os.environ.get("BEV_CAPTURES_HOME") or tempfile.mkdtemp()     # réglages neufs, rien de personnel
os.environ["USERPROFILE"] = os.environ["HOME"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
sys.argv = [os.path.join(ROOT, "broadcast_tool_qt.py"), "--selftest"]   # pas de fenêtre unique, pas d'écran de démarrage

import broadcast_tool_qt as bev  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT = os.path.abspath(_ARGS[0] if _ARGS else "captures")
# portable 1920x1080 à 125 % (le plus courant) : plein écran et fenêtre agrandie ; écran 1440x900 ; portable 1366x768
SIZES = [(1536, 864), (1536, 793), (1440, 860), (1366, 728)]
PAGES = [k for k in bev.PAGE_KEYS]
STATES = ("air", "partial", "secours", "bad")
REPORT = []


def main():
    out = OUT
    os.makedirs(out, exist_ok=True)
    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    bev.load_fonts()
    app.setStyleSheet(bev.qss())
    w = bev.MainWindow()
    w.show()
    jobs = []
    for (W, H) in SIZES:
        for k in PAGES:
            jobs.append((W, H, k, None))
        for state in STATES:
            jobs.append((W, H, "diff", state))
        if (W, H) == SIZES[0]:                    # processeur : mesures en direct et chaque onglet de réglages
            for state in ("live", "tab1", "tab2", "tab3"):
                jobs.append((W, H, "son", state))

    def step(i=0):
        if i >= len(jobs):
            with open(os.path.join(out, "rapport.txt"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(REPORT) + "\n")
            print("\n".join(REPORT), flush=True)
            w._closing = True
            app.exit(0)
            return
        W, H, k, state = jobs[i]
        w.resize(W, H)
        w.go_tab(k)
        if k == "son":                            # onglet de réglages, le temps que sa pastille glisse
            w.proc_tab(int(state[3:]) if state and state.startswith("tab") else 0)
        # une cartouche en lecture dans le bandeau (cas le plus chargé) sur le Cartoucheur ; le moteur absent la
        # remettrait à zéro à chaque tic : on fige l'affichage le temps de la capture
        cn = w.cart_now
        orig = type(cn).set_items
        cn.set_items = lambda *_a: None
        orig(cn, [("02 - Hold On", "#5b6cff", 9.9, 111.8, False, True, False, False)] if k == "cart" else [])
        QTimer.singleShot(900, lambda: shoot(i))

    def shoot(i):
        W, H, k, state = jobs[i]
        if k == "son" and state is not None:      # processeur : mesures simulées (l'onglet est choisi avant l'attente)
            if state == "live":
                w.proc_meters.set({"agc": 3.4, "bagc": 1.0, "gr": [4.2, 2.8, 3.5, 5.1, 2.2], "lim": 1.6, "clip": 0.9,
                                   "lufs": -15.8, "lufs_m": -14.6, "out": -1.1}, "air")
                w.proc_meters.set = lambda *_a: None          # (le moteur absent ne l'efface plus)
        elif state is not None and k != "son":                    # état simulé, dessiné juste avant la capture
            text = {"air": "EN ANTENNE  01:12:09", "partial": "1 FLUX HS  01:12:09", "secours": "SECOURS  01:12:09",
                    "bad": "Aucun flux en ligne", "wait": "Connexion des flux…"}[state]
            w.l_air.set_mode(state)
            w.set_label(w.l_air, text, bev.TXT)
            w.loud.set(-16.4, -14.9, True, "ANTENNE")
        name = f"{W}x{H}-{PAGE_KEYS_IDX[k]:02d}-{k}" + (f"-{state}" if state else "") + ".png"
        w.grab().save(os.path.join(out, name))
        if state is None:                          # la page tient-elle sans défilement ?
            pgw = w.stack.currentWidget()
            sc = pgw if isinstance(pgw, bev.QScrollArea) else (pgw.findChildren(bev.QScrollArea) or [None])[0]
            over = 0
            if sc is not None and sc.widget() is not None:
                over = sc.widget().height() - sc.viewport().height()
            line = f"{W}x{H}  {k:6s}  " + (f"DÉFILE ({over} px de trop)" if over > 2 else "tient sur l'écran")
            REPORT.append(line)
            for msg in overlaps(w):
                REPORT.append("      CHEVAUCHEMENT " + msg)
            if over > 2:                           # diagnostic : page entière, et hauteur minimale de chaque carte
                sc.widget().grab().save(os.path.join(out, name.replace(".png", "-page.png")))
                for c in sc.widget().findChildren(bev.Card):
                    if c.isVisible():
                        t = (c.findChildren(bev.QLabel) or [None])[0]
                        REPORT.append(f"      carte « {t.text()[:28] if t else '?'} » : hauteur {c.height()}, minimum "
                                      f"{c.minimumSizeHint().height()}")
        print("capture", name, flush=True)
        QTimer.singleShot(50, lambda: step(i + 1))

    QTimer.singleShot(2500, step)
    return app.exec()


PAGE_KEYS_IDX = {k: i for i, k in enumerate(bev.PAGE_KEYS)}


def _name(wd):
    t = (wd.findChildren(bev.QLabel) or [None])[0]
    return (t.text()[:26] if t is not None and t.text() else type(wd).__name__)


def overlaps(w):
    """Éléments qui se chevauchent : cartes de la page affichée, éléments du bandeau « en lecture », et cartes plus basses
    que leur minimum (Qt les fait alors déborder sur la suivante)."""
    from PySide6.QtCore import QRect
    out = []
    pgw = w.stack.currentWidget()
    cards = [c for c in pgw.findChildren(bev.Card) if c.isVisible() and not isinstance(c.parentWidget(), bev.Card)]

    def glob(wd):
        return QRect(wd.mapTo(w, wd.rect().topLeft()), wd.size())
    for i, a in enumerate(cards):
        ra = glob(a)
        if a.height() + 1 < a.minimumSizeHint().height():
            out.append(f"carte « {_name(a)} » écrasée : {a.height()} px pour {a.minimumSizeHint().height()} px minimum")
        for b in cards[i + 1:]:
            if a.isAncestorOf(b) or b.isAncestorOf(a):
                continue
            inter = ra.intersected(glob(b))
            if inter.width() > 2 and inter.height() > 2:
                out.append(f"« {_name(a)} » / « {_name(b)} » ({inter.width()}x{inter.height()} px)")
    band = getattr(w, "band", None)
    if band is not None:
        kids = [c for c in band.findChildren(bev.QWidget) if c.parentWidget() is band and c.isVisible()]
        for i, a in enumerate(kids):
            for b in kids[i + 1:]:
                inter = glob(a).intersected(glob(b))
                if inter.width() > 2 and inter.height() > 2:
                    out.append(f"bandeau : {type(a).__name__} / {type(b).__name__} ({inter.width()} px)")
    return out

if __name__ == "__main__":
    sys.exit(main())
