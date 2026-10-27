# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Banc de mesure de la fluidité de l'interface : python tools/perf.py [--ecran] [--profil]
Ouvre Bev avec des réglages neufs (rien de personnel, rien n'est diffusé) et mesure, en millisecondes :
  - le changement de chaque onglet : premier clic, clic suivant, et premier clic juste après un redimensionnement ;
  - le redimensionnement : temps par image pendant qu'on tire le bord de la fenêtre ;
  - la charge au repos : part du temps où l'interface est occupée (animations comprises).
Par défaut sans rien afficher (hors écran) ; --ecran : dans une vraie fenêtre (plus proche de l'usage, sous Windows
surtout). --profil : en plus, les fonctions de Bev qui coûtent le plus.
Repère : pour 30 images/s, chaque image dispose de 33 ms en tout. Envoyez le résultat complet pour comparer."""
import os
import platform
import statistics
import sys
import tempfile
import time

if "--ecran" not in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["HOME"] = os.environ.get("BEV_PERF_HOME") or tempfile.mkdtemp()      # réglages neufs, rien de personnel
os.environ["USERPROFILE"] = os.environ["HOME"]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PROFILE = "--profil" in sys.argv
sys.argv = [os.path.join(ROOT, "broadcast_tool_qt.py"), "--selftest"]   # pas de fenêtre unique ni d'écran de démarrage

import broadcast_tool_qt as bev  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

BUDGET = 33.0


def main():
    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    bev.load_fonts()
    app.setStyleSheet(bev.qss())

    def idle(sec):
        end = time.perf_counter() + sec
        while time.perf_counter() < end:
            app.processEvents()
            time.sleep(0.002)

    def flush():
        for _ in range(4):
            app.processEvents()

    def tour():
        out = {}
        for k in bev.PAGE_KEYS:
            t0 = time.perf_counter()
            w.go_tab(k)
            flush()
            out[k] = (time.perf_counter() - t0) * 1000
            idle(0.15)
        return out

    t0 = time.perf_counter()
    w = bev.MainWindow()
    w.resize(1536, 864)
    w.show()
    flush()
    opened = (time.perf_counter() - t0) * 1000
    idle(3.5)                                        # comme un utilisateur : on ne clique pas dans la première seconde
    prof = None
    if PROFILE:
        import cProfile
        prof = cProfile.Profile()
        prof.enable()
    first = tour()
    w.go_tab("diff")
    idle(0.3)
    regular = [tour() for _ in range(3)]
    w.go_tab("diff")
    idle(0.3)
    w.resize(1366, 728)                              # on change la taille de la fenêtre, puis on reprend les onglets
    idle(2.5)
    after = tour()
    w.resize(1536, 864)
    idle(2.5)
    frames, by_page = [], {}
    widths = [1536 - 14 * i for i in range(30)] + [1116 + 14 * i for i in range(30)]
    for k in bev.PAGE_KEYS:
        w.go_tab(k)
        idle(0.2)
        fr = []
        for W in widths:
            t0 = time.perf_counter()
            w.resize(W, 864 - (1536 - W) // 6)
            flush()
            fr.append((time.perf_counter() - t0) * 1000)
        by_page[k] = fr
        frames += fr
        w.resize(1536, 864)
        idle(1.2)
    w.go_tab("diff")
    idle(1.0)
    busy, t_end = 0.0, time.perf_counter() + 5
    while time.perf_counter() < t_end:
        a = time.perf_counter()
        app.processEvents()
        busy += time.perf_counter() - a
        time.sleep(0.002)
    if prof:
        prof.disable()

    med = {k: statistics.median([r[k] for r in regular]) for k in bev.PAGE_KEYS}
    out = [f"Bev {bev.VERSION} · Python {platform.python_version()} · {platform.platform()} · "
           f"{'fenêtre réelle' if os.environ.get('QT_QPA_PLATFORM') != 'offscreen' else 'hors écran'}",
           f"Ouverture de la fenêtre : {opened:.0f} ms", "",
           "Changement d'onglet (ms)   1er clic   clics suivants   1er clic après redimensionnement"]
    for k in bev.PAGE_KEYS:
        out.append(f"  {bev.PAGE_TITLES[k]:16s} {first[k]:8.1f} {med[k]:13.1f} {after[k]:18.1f}")
    worst = max(list(first.values()) + list(med.values()) + list(after.values()))
    out.append(f"  pire : {worst:.0f} ms " + ("(fluide)" if worst <= BUDGET else f"(au-delà de {BUDGET:.0f} ms : saccade visible)"))
    out += ["", "Redimensionnement (ms par image)   médiane   pire"]
    for k in bev.PAGE_KEYS:
        out.append(f"  {bev.PAGE_TITLES[k]:16s} {statistics.median(by_page[k]):16.1f} {max(by_page[k]):7.1f}")
    over = sum(1 for x in frames if x > BUDGET)
    out.append(f"  toutes pages : médiane {statistics.median(frames):.1f} ms, {over} image(s) sur {len(frames)} au-delà de {BUDGET:.0f} ms")
    out += ["", f"Au repos (Diffusion, animations comprises) : interface occupée {busy / 5 * 100:.0f} % du temps"]
    if prof:
        import io
        import pstats
        s = io.StringIO()
        pstats.Stats(prof, stream=s).sort_stats("cumulative").print_stats(40)
        out += ["", "Fonctions de Bev les plus coûteuses (temps cumulé) :"]
        out += [ln for ln in s.getvalue().splitlines() if ("bev_" in ln or "broadcast_tool_qt" in ln or "ncalls" in ln)][:30]
    print("\n".join(out), flush=True)
    w._closing = True
    os._exit(0)


if __name__ == "__main__":
    main()
