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
SIZES = [(1440, 860), (1366, 728)]        # écran 1440x900 et portable 1366x768, fenêtre agrandie
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
        QTimer.singleShot(900, lambda: shoot(i))

    def shoot(i):
        W, H, k, state = jobs[i]
        if state is not None:                      # état simulé, dessiné juste avant la capture
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
        print("capture", name, flush=True)
        QTimer.singleShot(50, lambda: step(i + 1))

    QTimer.singleShot(2500, step)
    return app.exec()


PAGE_KEYS_IDX = {k: i for i, k in enumerate(bev.PAGE_KEYS)}

if __name__ == "__main__":
    sys.exit(main())
