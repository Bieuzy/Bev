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
SIZES = [(1440, 900), (1180, 760)]
PAGES = [k for k in bev.PAGE_KEYS]


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
        for state in getattr(w, "CAPTURE_STATES", ()):
            jobs.append((W, H, "diff", state))

    def step(i=0):
        if i >= len(jobs):
            w._closing = True
            app.exit(0)
            return
        W, H, k, state = jobs[i]
        w.resize(W, H)
        w.go_tab(k)
        if state is not None:
            w.capture_state(state)
        QTimer.singleShot(900, lambda: shoot(i))

    def shoot(i):
        W, H, k, state = jobs[i]
        name = f"{W}x{H}-{PAGE_KEYS_IDX[k]:02d}-{k}" + (f"-{state}" if state else "") + ".png"
        w.grab().save(os.path.join(out, name))
        print("capture", name, flush=True)
        if state is not None:
            w.capture_state(None)
        QTimer.singleShot(50, lambda: step(i + 1))

    QTimer.singleShot(2500, step)
    return app.exec()


PAGE_KEYS_IDX = {k: i for i, k in enumerate(bev.PAGE_KEYS)}

if __name__ == "__main__":
    sys.exit(main())
