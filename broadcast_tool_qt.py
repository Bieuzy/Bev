#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (« direct » en breton) - diffusion radio multi-sorties (Internet / FM / DAB+ /
enregistrement), playlist de secours, cartoucheur, monitoring et outils SOS.

Prérequis : Python 3.9+ avec PySide6 et ffmpeg dans le PATH.
Optionnel : sounddevice (sortie FM sur carte son), PyAudioWPatch (capture du
son de l'ordinateur sous Windows), odr-audioenc (DAB+).
"""
import base64
import hashlib
import importlib.util
import json
import math
import os
import platform
import random
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from array import array
from collections import deque

# ======================================================================================================================
# ORGANISATION DU CODE
#   broadcast_tool_qt.py  ce fichier : démarrage (mise à jour express, fenêtre unique, écran de démarrage) et selftest
#   bev_version.py        version, dépôt des mises à jour, état de la mise à jour express (lu en tout premier)
#   bev_core.py           cœur sans interface : moteur audio, sorties, réseau, processus moteur (n'importe jamais Qt)
#   bev_assets.py         polices et logo intégrés
#   Interface (Qt), chaque module reprenant tous les noms du précédent, dans cet ordre :
#   bev_ui → bev_widgets → bev_alertes → bev_maj → bev_gael → bev_secours → bev_dialogues → bev_cartoucheur →
#   bev_pages → bev_monitoring → bev_assistant → bev_sos → bev_bandeau → bev_diffusion → bev_antenne →
#   bev_miseajour → bev_support → bev_fenetre (fenêtre principale, qui hérite des parties définies dans les modules
#   précédents)
# Ajouter un module d'interface : l'insérer dans cette chaîne (et dans MODULES de tools/express.py).
# ======================================================================================================================
from bev_version import *  # noqa: E402,F401,F403


def _express_boot():
    """Au lancement de l'application empaquetée : passe sur le code express s'il est valide (sinon : version installée)."""
    if not getattr(sys, "frozen", False) or globals().get("_BEV_EXPRESS") or "--selftest" in sys.argv:
        return
    code = os.environ.get("BEV_CODE")               # moteur audio lancé par l'interface : exactement le même code qu'elle
    worker = "--bev-engine" in sys.argv
    if not code:
        if worker:
            return
        st = express_state()
        f = os.path.join(UPD_DIR, os.path.basename(str(st.get("file") or "")))
        if not (st.get("file") and _ver_tuple(st.get("version")) > _ver_tuple(VERSION) and st.get("runtime") == RUNTIME):
            os.environ["BEV_CODE"] = "builtin"
            return
        if int(st.get("fails", 0)) >= 2:            # deux démarrages ratés : on reste sur la version installée
            express_log(f"Code express {st.get('version')} écarté (démarrages ratés) : version installée {VERSION}.")
            os.environ["BEV_CODE"] = "builtin"
            return
        try:
            import hashlib as _h
            with open(f, "rb") as fh:
                ok = _h.sha256(fh.read()).hexdigest() == st.get("sha256")
        except OSError:
            ok = False
        if not ok:
            express_log(f"Code express {st.get('version')} absent ou abîmé : version installée {VERSION}.")
            os.environ["BEV_CODE"] = "builtin"
            return
        express_state({"fails": int(st.get("fails", 0)) + 1})   # remis à zéro quand Bev a bien démarré
        code = f
    if code == "builtin" or not os.path.isfile(code):
        return
    os.environ["BEV_CODE"] = code
    ns = {"__name__": "__bev_express__", "__file__": code, "_BEV_EXPRESS": code, "__builtins__": __builtins__}
    try:
        with open(code, "rb") as fh:
            exec(compile(fh.read(), code, "exec"), ns)
    except SystemExit:
        raise
    except BaseException as ex:                      # (module introuvable, erreur…) : la version installée prend le relais
        express_log(f"Code express inutilisable ({type(ex).__name__}: {ex}) : version installée {VERSION}.")
        os.environ["BEV_CODE"] = "builtin"
        if not worker:
            express_state({"fails": 2})
        return
    sys.exit((ns["_engine_worker_main"] if worker else ns["main"])() or 0)


_express_boot()


# Tous les modules de Bev sont importés APRÈS _express_boot() : une mise à jour express fournit ses propres versions.
from bev_core import *  # noqa: E402,F403
from bev_core import _cover_extract, _engine_worker_main  # noqa: E402

if WORKER_ARG in sys.argv and __name__ in ("__main__", "__mp_main__"):   # processus moteur : jamais de Qt
    _engine_worker_main()

from bev_fenetre import *  # noqa: E402,F401,F403  (toute l'interface, voir ORGANISATION DU CODE)


def load_fonts():
    """Polices intégrées au fichier (Inter, Space Grotesk) : même rendu partout, sans rien installer."""
    import zlib
    fams = []
    for name, parts in _FONT_BLOB.items():
        try:
            raw = zlib.decompress(base64.b64decode("".join(parts)))
            i = QFontDatabase.addApplicationFontFromData(raw)
            if i >= 0:
                fams += QFontDatabase.applicationFontFamilies(i)
        except Exception:
            pass
    return fams


def win_timer_1ms():
    """Windows cadence ses minuteurs par pas de 15,6 ms par défaut : un rendu « 60 i/s » y tombe souvent à 30-40. On
    demande la précision d'1 ms (comme les navigateurs et lecteurs vidéo) pendant que l'application tourne."""
    if SYS == "Windows":
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass


def close_boot_splash():
    """Ferme l'image de démarrage affichée par l'exécutable dès le double-clic (avant même que Python ne démarre)."""
    if "_PYI_SPLASH_IPC" not in os.environ or globals().get("_SPLASH_DONE"):
        return
    globals()["_SPLASH_DONE"] = True
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass


_INSTANCE_MUTEX = None


def main():
    try:
        sys.setswitchinterval(0.002)  # le moteur audio reprend la main plus vite que l'interface
    except Exception:
        pass
    if "--after" in sys.argv:          # relance (Apparence, mise à jour…) : on attend la fermeture complète de l'ancienne fenêtre
        try:
            wait_pid_gone(int(sys.argv[sys.argv.index("--after") + 1]), 20)
        except (ValueError, IndexError):
            pass
    win_timer_1ms()
    selftest = "--selftest" in sys.argv
    if SYS == "Windows":
        try:
            import ctypes
            global _INSTANCE_MUTEX
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("fr.radio.bev")
            if not selftest:           # l'installateur attend la fermeture de Bev grâce à ce repère
                _INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "BevRadioApp")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setStyle("Fusion")
    if "--render-splash" in sys.argv:              # construction : image de démarrage = 1re image de l'animation
        load_fonts()
        render_splash(sys.argv[sys.argv.index("--render-splash") + 1])
        return
    srv = None
    if not selftest:                   # une seule fenêtre Bev : un second lancement ramène simplement la fenêtre ouverte
        try:
            from PySide6.QtNetwork import QLocalServer, QLocalSocket
            name = "bev-" + hashlib.md5(os.path.expanduser("~").encode("utf-8", "replace")).hexdigest()[:12]
            sock = QLocalSocket()
            sock.connectToServer(name)
            if sock.waitForConnected(500):
                sock.write(b"show")
                sock.waitForBytesWritten(500)
                sock.disconnectFromServer()
                close_boot_splash()
                return
            QLocalServer.removeServer(name)
            srv = QLocalServer()
            srv.listen(name)
        except Exception:
            srv = None
    load_fonts()
    try:
        pm = QPixmap()
        pm.loadFromData(base64.b64decode("".join(_ICON_B64) if not isinstance(_ICON_B64, str) else _ICON_B64))
        if not pm.isNull():
            app.setWindowIcon(QIcon(pm))
    except Exception:
        pass
    sp = None
    if not selftest:                   # l'animation prend le relais de l'image de démarrage, au même endroit, sans saut
        try:
            sp = Splash()
            sp.show()
            sp.repaint()
            QApplication.processEvents()
            close_boot_splash()
            Splash.current = sp
            sp.spin(250)
        except Exception:
            sp = None
    close_boot_splash()
    app.setStyleSheet(qss())
    errs = []
    prev_crash = ""
    win = []
    if selftest:                       # vérification automatique (construction GitHub) : tout ouvrir, puis quitter
        import traceback
        sys.excepthook = lambda *a: errs.append("".join(traceback.format_exception(*a)))
    else:
        # Support : un plantage brutal est noté (et signalé au lancement suivant) ; une erreur inattendue est notée avec tous
        # ses détails dans le journal technique, et Gaël propose de la signaler. L'antenne continue dans tous les cas.
        prev_crash = crash_watch("interface")

        def on_error(et, ex, tb):
            sm = trace_exc("interface", et, ex, tb)
            sys.__excepthook__(et, ex, tb)
            if sm and win:
                QTimer.singleShot(0, lambda: win[0].on_internal_error(sm))
        sys.excepthook = on_error
        threading.excepthook = lambda a: trace_exc("interface (fil " + str(getattr(a.thread, "name", "?")) + ")",
                                                   a.exc_type, a.exc_value, a.exc_traceback)
    w = MainWindow()
    win.append(w)
    if prev_crash.strip():
        QTimer.singleShot(4500, lambda: w.crash_greet(prev_crash))
    Splash.current = None
    if sp is not None:
        try:
            sp.spin(120)
            sp.close()
        except Exception:
            pass
    w.show()
    if srv is not None:
        def front():
            c = srv.nextPendingConnection()
            if c is not None:
                c.close()
            if w.isMinimized():
                w.showNormal()
            w.show()
            w.raise_()
            w.activateWindow()
        srv.newConnection.connect(front)
    if selftest:
        for k, key in enumerate(PAGE_KEYS):
            QTimer.singleShot(1500 + k * 500, lambda key=key: w.go_tab(key))

        def done():
            rep = [f"{APP} {VERSION} · Python {platform.python_version()} · {platform.platform()}",
                   "ffmpeg : " + (shutil.which("ffmpeg") or "INTROUVABLE"), "ffprobe : " + (shutil.which("ffprobe") or "INTROUVABLE"),
                   "numpy : " + ("oui" if np is not None else "non"), "sounddevice : " + ("oui" if have_module("sounddevice") else "non"),
                   "psutil : " + ("oui" if have_module("psutil") else "non"),
                   "capture son de l'ordinateur : " + ("oui" if have_loopback() else ("non" if SYS == "Windows" else "sans objet")),
                   "moteur audio séparé : " + (("oui (pid %s)" % w.engine.pid) if (isinstance(w.engine, EngineProxy) and w.engine.alive())
                                               else ("non (moteur dans l'application)" if w.engine is not None else "non (pas lancé)")),
                   "chiffrement des mots de passe : " + _selftest_secrets(errs),
                   "signature des mises à jour : " + ("clé publique présente" if UPDATE_PUBKEY else "pas encore de clé publique"),
                   f"erreurs : {len(errs)}"] + errs
            try:
                with open("selftest.txt", "w", encoding="utf-8") as fh:
                    fh.write("\n".join(rep) + "\n")
            except OSError:
                pass
            bad = bool(errs) or ((SYS == "Windows" or getattr(sys, "frozen", False)) and not shutil.which("ffmpeg"))   # (Mac aussi : ffmpeg est fourni)
            w._closing = True
            app.exit(1 if bad else 0)
        QTimer.singleShot(1500 + len(PAGE_KEYS) * 500 + 2500, done)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

