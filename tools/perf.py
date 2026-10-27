# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Banc de mesure de la fluidité de l'interface (sans écran : QT_QPA_PLATFORM=offscreen).
Utilisation : python tools/perf.py [--profil]
Mesure, en millisecondes : l'ouverture de la fenêtre, le changement de chaque onglet (première visite puis visites
suivantes), le redimensionnement (temps par image pendant qu'on tire le bord de la fenêtre) et le coût d'une image au
repos sur chaque onglet. Avec --profil : les 25 fonctions qui coûtent le plus pendant ces mesures.
Repère : à 30 i/s, une image dispose de 33 ms en tout (dessin compris)."""
import os
import statistics
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = os.environ.get("BEV_PERF_HOME") or tempfile.mkdtemp()      # réglages neufs, rien de personnel
os.environ["USERPROFILE"] = os.environ["HOME"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PROFILE = "--profil" in sys.argv
sys.argv = [os.path.join(ROOT, "broadcast_tool_qt.py"), "--selftest"]

import broadcast_tool_qt as bev  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


def ms(t0):
    return (time.perf_counter() - t0) * 1000


def settle(app, n=3):
    for _ in range(n):
        app.processEvents()


def main():
    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    bev.load_fonts()
    app.setStyleSheet(bev.qss())
    prof = None
    if PROFILE:
        import cProfile
        prof = cProfile.Profile()
    t0 = time.perf_counter()
    w = bev.MainWindow()
    w.resize(1536, 864)
    w.show()
    settle(app)
    w.repaint()
    out = [f"Bev {bev.VERSION} · ouverture de la fenêtre : {ms(t0):.0f} ms"]
    for _ in range(20):                          # le temps que les pages différées se construisent
        settle(app)
        time.sleep(0.05)
    if prof:
        prof.enable()
    first, again = {}, {}
    for k in bev.PAGE_KEYS:
        t0 = time.perf_counter()
        w.go_tab(k)
        settle(app, 2)
        w.repaint()
        first[k] = ms(t0)
    for rnd in range(3):
        for k in bev.PAGE_KEYS:
            t0 = time.perf_counter()
            w.go_tab(k)
            settle(app, 2)
            w.repaint()
            again.setdefault(k, []).append(ms(t0))
    out.append("\nChangement d'onglet (1re visite · visites suivantes, médiane) :")
    for k in bev.PAGE_KEYS:
        out.append(f"  {k:6s} {first[k]:7.1f}  ·  {statistics.median(again[k]):6.1f}")
    out.append(f"  total des visites suivantes : {sum(statistics.median(v) for v in again.values()):.0f} ms")
    out.append("\nRedimensionnement (temps par image, médiane · pire) :")
    widths = [1536 - 14 * i for i in range(30)] + [1116 + 14 * i for i in range(30)]
    tot = []
    for k in bev.PAGE_KEYS:
        w.go_tab(k)
        settle(app)
        w.repaint()
        fr = []
        for W in widths:
            t0 = time.perf_counter()
            w.resize(W, 864 - (1536 - W) // 6)
            settle(app, 1)
            w.repaint()
            fr.append(ms(t0))
        tot += fr
        out.append(f"  {k:6s} {statistics.median(fr):6.1f}  ·  {max(fr):6.1f}")
    out.append(f"  toutes pages : médiane {statistics.median(tot):.1f} ms, {sum(1 for x in tot if x > 33)} images sur {len(tot)} au-delà de 33 ms")
    w.resize(1536, 864)
    settle(app)
    out.append("\nImage au repos (boucle d'affichage + dessin, médiane) :")
    for k in bev.PAGE_KEYS:
        w.go_tab(k)
        settle(app)
        fr = []
        for _ in range(40):
            t0 = time.perf_counter()
            w.tick()
            settle(app, 1)
            w.repaint()
            fr.append(ms(t0))
        out.append(f"  {k:6s} {statistics.median(fr):6.1f}")
    if prof:
        prof.disable()
        import io
        import pstats
        s = io.StringIO()
        pstats.Stats(prof, stream=s).sort_stats("tottime").print_stats(25)
        out.append("\n" + "\n".join(ln for ln in s.getvalue().splitlines() if ln.strip())[:6000])
    print("\n".join(out), flush=True)
    w._closing = True
    try:
        w.close()
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()
