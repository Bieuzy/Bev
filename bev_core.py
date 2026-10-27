# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev - cœur sans interface : moteur audio (capture, mixage, playlist de secours, cartouches, processeur
d'antenne), sorties (Internet, FM, DAB+, enregistrement), réseau, et processus moteur séparé.

Ce module n'importe jamais Qt : le processus moteur (--bev-engine) le charge seul, démarre vite et reste léger.
Lancé directement (python bev_core.py --bev-engine …), il fait tourner le moteur audio.
"""
import base64
import hashlib
import importlib.util
import json
import math
import os
import platform
import queue
import random
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
from array import array
from collections import deque
from urllib.parse import quote, urlencode

try:  # (présent dans toutes les versions installées ; facultatif pour que la mise à jour express reste possible)
    from hmac import compare_digest
except ImportError:
    def compare_digest(a, b):
        return hashlib.sha256(a).digest() == hashlib.sha256(b).digest()

try:  # calcul audio rapide (installé automatiquement si absent)
    import numpy as np
except Exception:
    np = None

APP = "Bev"
CONF = os.path.expanduser("~/.broadcast_tool.json")
SYS = platform.system()

# --- App empaquetée : ffmpeg / ffplay / icône cherchés d'abord à côté de l'application ---
APP_DIR = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
_EXE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else APP_DIR
for _d in (os.path.join(_EXE_DIR, "bin"), _EXE_DIR, os.path.join(APP_DIR, "bin"), APP_DIR):
    if os.path.isdir(_d) and any(os.path.isfile(os.path.join(_d, n)) for n in ("ffmpeg", "ffmpeg.exe")):
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
        break
if SYS == "Windows":
    try:  # icône propre dans la barre des tâches (et non celle de Python)
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("fr.radio.bev")   # (même identifiant que main())
    except Exception:
        pass
SR = 44100
CH = 3528  # 20 ms de PCM 44,1 kHz, stéréo, 16 bits
DEFAULT_DEVICE = {"Windows": "Microphone", "Darwin": "0"}.get(SYS, "default")

# nom: (options codec, muxer, content-type, fréquence d'échantillonnage)
FORMATS = {
    "MP3": (["-c:a", "libmp3lame", "-id3v2_version", "0", "-write_xing", "0"],
            "mp3", "audio/mpeg", 44100),
    "AAC": (["-c:a", "aac"], "adts", "audio/aac", 44100),
    "Ogg Opus": (["-c:a", "libopus"], "ogg", "application/ogg", 48000),
    "Ogg Vorbis": (["-c:a", "libvorbis"], "ogg", "application/ogg", 44100),
    "FLAC": (["-c:a", "flac"], "ogg", "application/ogg", 44100),
}
SHOUT_FORMATS = ["MP3", "AAC"]
BITRATES = ["32", "48", "64", "96", "128", "160", "192", "256", "320"]

PROCESSING = {
    "Aucun": "",
    "Limiteur doux": "alimiter=limit=0.95:level=0",
    "Voix (compresseur + limiteur)":
        "highpass=f=80,acompressor=threshold=0.1:ratio=4:attack=5:release=150:makeup=2,"
        "alimiter=limit=0.9:level=0",
    "Radio FM (filtre 15 kHz + compresseur + limiteur)":
        "highpass=f=30,lowpass=f=15000,"
        "acompressor=threshold=0.125:ratio=3:attack=20:release=250:makeup=2,"
        "alimiter=limit=0.89:level=0",
    "Normalisation EBU R128": "loudnorm=I=-16:TP=-1.5:LRA=11",
}
# ======================================================================================================================
# PROCESSEUR D'ANTENNE : traitement du son temps réel, calculé dans le moteur bloc par bloc (20 ms), appliqué à tout ce
# qui part à l'antenne (flux, FM, DAB+, enregistrement, écoute casque). Architecture des processeurs de diffusion
# haut de gamme (Optimod, Omnia, Stereo Tool) :
#   coupe-bas + égalisation à phase linéaire (sans coloration de phase)
#   -> AGC large bande lente, à fenêtre et à porte (le niveau ne remonte pas dans les silences) + AGC des graves
#   -> compresseur-limiteur 5 bandes : crossover à phase linéaire à reconstruction parfaite, couplage inter-bandes,
#      porte par bande, limiteur de crête par bande, niveau de sortie de chaque bande (le « son » de la station)
#   -> stéréo : élargissement par bande à ratio côté/milieu plafonné, graves en mono
#   -> écrêteur doux suréchantillonné x2 (anti-repliement)
#   -> limiteur final à anticipation avec détection des crêtes vraies (x4, esprit ITU-R BS.1770) : plafond garanti
# Mesures : AGC, réduction de gain par bande, limiteur, écrêteur, sonie LUFS (court terme 3 s et momentanée 400 ms).
# Contournement (bypass) par fondu de 60 ms entre son traité et son brut retardé d'autant : aucune coupure, aucun saut.
# ======================================================================================================================
P_N = 4096                       # taille FFT du crossover (overlap-save)
P_L = 3071                       # longueur des noyaux à phase linéaire
P_D = (P_L - 1) // 2             # retard du crossover (échantillons)
P_B = CH // 4                    # 882 échantillons par bloc de 20 ms
P_SUB = 63                       # sous-bloc de calcul des gains (1,43 ms) : 14 par bloc
P_NS = P_B // P_SUB
P_XO = (120.0, 420.0, 1700.0, 6200.0)      # fréquences de coupure des 5 bandes
P_HB = 127                       # passe-bas 20 kHz de l'écrêteur suréchantillonné (x2)
P_TP = 129                       # filtre d'interpolation des crêtes vraies (x4)
P_TPD = (P_TP - 1) // 2 // 4     # retard correspondant (16 échantillons)
BAND_NAMES = ("Graves", "Bas-médium", "Médium", "Présence", "Aigus")


def _fir_lp(n, cutoff, beta):
    k = np.arange(n) - (n - 1) / 2
    h = np.sinc(2 * cutoff * k) * np.kaiser(n, beta)
    return h / h.sum()


def _kweight_mag(nfft=1024):
    """Pondération K (ITU-R BS.1770) : module au carré de la réponse, pour la mesure de sonie (LUFS)."""
    f = np.fft.rfftfreq(nfft, 1.0 / SR)
    z = np.exp(-1j * 2 * np.pi * f / SR)

    def biquad(b, a):
        return (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)
    G, Q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    A = 10 ** (G / 40)
    w0 = 2 * np.pi * fc / SR
    al, cw, sA = np.sin(w0) / (2 * Q), np.cos(w0), np.sqrt(A)
    h1 = biquad([A * ((A + 1) + (A - 1) * cw + 2 * sA * al), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - 2 * sA * al)],
                [(A + 1) - (A - 1) * cw + 2 * sA * al, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - 2 * sA * al])
    Q, fc = 0.5003270373238773, 38.13547087602444
    w0 = 2 * np.pi * fc / SR
    al, cw = np.sin(w0) / (2 * Q), np.cos(w0)
    h2 = biquad([1.0, -2.0, 1.0], [1 + al, -2 * cw, 1 - al])
    return np.abs(h1 * h2) ** 2


class _Fir:
    """Filtre RIF en flux continu (historique conservé d'un bloc à l'autre), sur 2 canaux."""

    def __init__(self, h):
        self.h = np.asarray(h, dtype=float)
        self.z = np.zeros((2, len(h) - 1))

    def __call__(self, x):
        xs = np.concatenate((self.z, x), axis=1)
        self.z = xs[:, x.shape[1]:]
        return np.stack((np.convolve(xs[0], self.h, "valid"), np.convolve(xs[1], self.h, "valid")))


# --- réglages ----------------------------------------------------------------------------------------------------------
#  lm         MOINS <-> PLUS (1-10, comme sur un Optimod) : densité et volume perçu, à partir du préréglage
#  hpf        coupe-bas (Hz, 0 = sans) ; bass / presence / air : égalisation (dB)
#  agc        AGC marche / arrêt ; agc_speed : vitesse de remontée (dB/s) ; agc_gate : seuil de porte (dBFS)
#  bass_agc   AGC des graves (correction maximale, dB)
#  mb_drive   attaque du multibande (dB) ; ratio ; mb_release (ms) ; coupling (%) ; mix : niveau de sortie des 5 bandes (dB)
#  width      élargissement stéréo (%) ; bass_mono : graves en mono ; mono : sortie mono
#  clip       écrêteur (0-100 %) ; ceiling : plafond (dB crête vraie) ; fm15 : bande limitée à 15 kHz (émetteur FM)
PROC_BASE = dict(lm=5.0, hpf=35, bass=0.0, presence=0.0, air=0.0,
                 agc=True, agc_speed=2.0, agc_gate=-44.0, agc_target=-18.0, agc_max=15.0, agc_window=1.5, bass_agc=3.0,
                 mb_on=True, mb_drive=6.0, mb_thr=(-26.0, -26.0, -26.0, -28.0, -30.0), ratio=4.0,
                 mb_attack=(40.0, 22.0, 12.0, 7.0, 4.0), mb_release=250.0, coupling=40,
                 mix=(0.0, 0.0, 0.0, 0.0, 0.0), makeup=0.0, blim=-4.0,
                 width=0, bass_mono=True, mono=False,
                 clip=20, ceiling=-1.0, lim_release=120.0, fm15=False)

PROC_PRESETS = {
    "Généraliste": dict(bass=1.0, presence=0.5, air=1.0, mb_drive=6.0, ratio=4.0, mb_release=250.0, coupling=40, makeup=2.0,
                        mix=(0.5, 0.0, 0.0, 0.5, 1.0), width=25, clip=25, lim_release=120.0),
    "Talk-show": dict(hpf=70, bass=-0.5, presence=2.0, air=1.0, agc_speed=3.0, agc_gate=-40.0, mb_drive=7.0, ratio=5.0,
                      mb_release=180.0, coupling=60, mix=(-1.5, 0.0, 0.5, 1.0, 0.5), width=0, clip=15, lim_release=100.0),
    "Info (news)": dict(hpf=90, bass=-2.0, presence=3.0, air=0.5, agc_speed=4.0, agc_gate=-38.0, agc_window=0.8,
                        mb_drive=9.0, ratio=8.0, mb_release=120.0, coupling=70, mix=(-3.0, -0.5, 1.0, 1.5, 0.0),
                        width=0, clip=20, lim_release=80.0, bass_agc=0.0, blim=-5.0),
    "Classique": dict(hpf=20, agc_speed=0.6, agc_gate=-52.0, agc_target=-21.0, agc_max=10.0, agc_window=4.0, bass_agc=0.0,
                      mb_drive=1.0, ratio=1.8, mb_release=900.0, coupling=85, makeup=-1.2, blim=-1.5,
                      width=10, bass_mono=False, clip=0, ceiling=-1.5, lim_release=250.0),
    "Jazz & acoustique": dict(hpf=25, bass=0.5, air=0.5, agc_speed=1.0, agc_gate=-50.0, agc_target=-20.0, agc_window=3.0,
                              mb_drive=3.0, ratio=2.5, mb_release=600.0, coupling=70, mix=(0.0, 0.0, 0.0, 0.0, 0.5),
                              makeup=0.7, blim=-2.5, width=15, bass_mono=False, clip=5, lim_release=180.0),
    "Pop / Hits": dict(bass=1.5, presence=1.0, air=2.0, agc_speed=2.5, mb_drive=8.0, ratio=5.0, mb_release=160.0,
                       coupling=35, mix=(1.0, -0.5, 0.0, 1.0, 1.5), makeup=3.0, width=35, clip=40, lim_release=90.0),
    "Rock": dict(bass=1.0, presence=1.5, air=1.0, agc_speed=2.5, mb_drive=8.0, ratio=5.0, mb_release=200.0,
                 coupling=40, mix=(0.5, 0.0, 0.5, 1.5, 0.5), makeup=3.0, width=30, clip=40, lim_release=100.0),
    "Urbain": dict(hpf=28, bass=2.5, presence=0.5, air=1.5, agc_speed=2.5, mb_drive=8.0, ratio=5.0, mb_release=180.0,
                   coupling=35, mix=(2.0, 0.0, -0.5, 0.5, 1.0), makeup=3.0, width=30, clip=35, lim_release=100.0, bass_agc=4.0),
    "Loud": dict(bass=1.5, presence=1.5, air=2.0, agc_speed=3.0, mb_drive=11.0, ratio=10.0, mb_release=90.0,
                 coupling=25, mix=(1.0, 0.0, 0.0, 1.0, 1.5), makeup=3.5, blim=-5.5, width=40, clip=70, lim_release=60.0),
    "Protection seule": dict(hpf=0, agc=False, mb_on=False, width=0, bass_mono=False, clip=0, lim_release=150.0),
}
PROC_ORDER = list(PROC_PRESETS)
PROC_DEFAULT = "Généraliste"


def proc_params(name=PROC_DEFAULT, **over):
    d = dict(PROC_BASE)
    d.update(PROC_PRESETS.get(name, {}))
    d.update(over)
    d["preset"] = name if name in PROC_PRESETS else PROC_DEFAULT
    return d


class AirProcessor:
    """Processeur d'antenne temps réel : process(bloc de 20 ms, int16 stéréo) -> bloc traité de même taille, latence fixe
    (LAT échantillons, ~38 ms). update(réglages) et set_bypass(on) peuvent venir d'un autre fil : pris en compte au bloc
    suivant, sans clic (filtres changés par fondu, contournement par fondu)."""
    LAT = P_D + (P_HB - 1) // 2 + P_TPD + P_SUB

    def __init__(self, params=None, bypass=False):
        self.lk = threading.Lock()
        self.hist = np.zeros((2, P_N))                # historique M/S du crossover
        self.K = self.K_old = None
        self.shape_sig = None
        self.agc_db = self.bagc_db = 0.0
        self.agc_pow = 1e-4
        self.gr = np.zeros(5)                         # réduction de gain des compresseurs de bande (dB)
        self.gl = np.zeros(5)                         # réduction de gain des limiteurs de bande (dB)
        self.g_prev = None                            # gains de bande au dernier nœud
        self.w_prev = np.ones(5)                      # largeur stéréo appliquée par bande
        hb = _fir_lp(P_HB, 20500.0 / (2 * SR), 9.0)  # passe-bas 20,5 kHz à 88,2 kHz : rien au-dessus de 20 kHz
        self.up2, self.dn2 = _Fir(2 * hb), _Fir(hb)
        self.tp = _Fir(4 * _fir_lp(P_TP, 0.122, 8.0))
        self.tpd = np.zeros((2, P_TPD))
        self.lim_buf = np.zeros((2, P_SUB))
        self.lim_req_prev = 1.0
        self.lim_g = 1.0
        self.dry = np.zeros((2, self.LAT + P_B))
        self.bypass = bool(bypass)
        self.mix_g = 0.0 if bypass else 1.0
        self.kw = _kweight_mag()
        self.ms_hist = np.zeros(150)
        self.ms_i = 0
        self.clip_acc = 0.0
        self.meter = {"agc": 0.0, "bagc": 0.0, "gr": [0.0] * 5, "lim": 0.0, "clip": 0.0, "lufs": -70.0, "lufs_m": -70.0,
                      "in": -90.0, "out": -90.0, "bypass": self.bypass, "ms": 0.0, "gate": False}
        self.p = self.q = None
        self.update(params or proc_params())

    # --- réglages (depuis n'importe quel fil)
    def set_bypass(self, on):
        self.bypass = bool(on)

    def update(self, params):
        p = proc_params(params.get("preset", PROC_DEFAULT)) if params else proc_params()
        p.update({k: v for k, v in (params or {}).items() if k in PROC_BASE})
        num = lambda k: float(p.get(k, PROC_BASE[k]))
        lm = max(1.0, min(10.0, num("lm")))
        T = P_SUB / SR
        q = {"drive": num("mb_drive") + (lm - 5.0) * 1.3,                      # MOINS <-> PLUS
             "clip_drive": max(0.0, min(100.0, num("clip"))) / 100.0 * 3.5 + max(0.0, lm - 5.0) * 0.3,
             "clip_amt": max(0.0, min(100.0, num("clip"))) / 100.0,
             "ceil": 10 ** (max(-6.0, min(-0.1, num("ceiling"))) / 20),
             "thr": np.array(p["mb_thr"], dtype=float), "ratio": max(1.0, num("ratio")),
             "mix": np.array(p["mix"], dtype=float), "makeup": num("makeup") + (lm - 5.0) * 0.5,
             "a_att": 1 - np.exp(-T / (np.array(p["mb_attack"], dtype=float) / 1000.0)),
             "a_rel": 1 - np.exp(-T / (num("mb_release") / 1000.0 * np.array((1.6, 1.25, 1.0, 0.8, 0.65)))),
             "a_lrel": 1 - np.exp(-T / np.array((0.12, 0.08, 0.06, 0.05, 0.04))),
             "blim": num("blim") - (lm - 5.0) * 0.2,
             "coup": max(0.0, min(1.0, num("coupling") / 100.0)),
             "gate": num("agc_gate"), "mb_on": bool(p.get("mb_on", True)), "agc": bool(p.get("agc", True)),
             "agc_target": num("agc_target") + (lm - 5.0) * 0.4, "agc_speed": max(0.1, num("agc_speed")),
             "agc_max": num("agc_max"), "agc_win": max(0.0, num("agc_window")), "bagc_max": max(0.0, num("bass_agc")),
             "mono": bool(p.get("mono")),
             "lim_rel": 1 - math.exp(-T / max(0.01, num("lim_release") / 1000.0))}
        wd = max(0.0, min(200.0, num("width"))) / 100.0
        q["width"] = np.array((0.0 if p.get("bass_mono") else 1.0, 1 + wd * .5, 1 + wd, 1 + wd, 1 + wd * .7))
        sig = (num("hpf"), num("bass"), num("presence"), num("air"), bool(p.get("fm15")))
        K = self.design(*sig) if sig != self.shape_sig else None
        with self.lk:
            self.p, self.q = p, q
            if K is not None:
                self.K_old, self.K, self.shape_sig = self.K, K, sig

    @staticmethod
    def design(hpf, bass, presence, air, fm15):
        """Noyaux à phase linéaire des 5 bandes, égalisation et coupe-bas compris. Leur somme est exactement le filtre de
        mise en forme : le découpage en bandes n'ajoute aucune coloration."""
        nd = 1 << 16
        f = np.fft.rfftfreq(nd, 1.0 / SR)
        fz = np.maximum(f, 0.5)
        S = 1 / np.sqrt(1 + (12.0 / fz) ** 4)                       # toujours : protection infra-basse / continu
        if hpf > 0:                                                 # coupe-bas Butterworth d'ordre 4 (module)
            S = S / np.sqrt(1 + (hpf / fz) ** 8)
        if abs(bass) > .05:                                         # plateau grave (90 Hz)
            A2, x = 10 ** (bass / 10), (90.0 / fz) ** 2
            S = S * np.sqrt((1 + A2 * x) / (1 + x))
        if abs(presence) > .05:                                     # présence (cloche large à 3,2 kHz)
            S = S * 10 ** (presence / 20 * np.exp(-(np.log2(fz / 3200.0) / 0.8) ** 2))
        if abs(air) > .05:                                          # air (plateau aigu à 11 kHz)
            A2, x = 10 ** (air / 10), (fz / 11000.0) ** 2
            S = S * np.sqrt((1 + A2 * x) / (1 + x))
        if fm15:                                                    # FM : rien au-dessus de 15 kHz (pilote 19 kHz protégé)
            u = np.clip((f - 14700.0) / 1000.0, 0, 1)
            S = S * np.cos(u * np.pi / 2) ** 2
        lx = np.log2(fz)
        lps = [np.cos(np.clip(lx - math.log2(fc) + .5, 0, 1) * np.pi / 2) ** 2 for fc in P_XO]   # transitions d'une octave
        bands = [lps[0]] + [lps[i] - lps[i - 1] for i in range(1, 4)] + [1 - lps[3]]
        win = np.kaiser(P_L, 8.0)
        K = np.zeros((5, P_N // 2 + 1), dtype=complex)
        for i, b in enumerate(bands):
            h = np.roll(np.fft.irfft(b * S, nd), P_D)[:P_L] * win
            K[i] = np.fft.rfft(h, P_N)
        return K

    # --- un bloc
    def process(self, blk):
        t0 = time.perf_counter()
        x = np.frombuffer(blk, dtype="<i2").astype(np.float64).reshape(-1, 2).T * (1 / 32768.0)
        with self.lk:
            q, K, Ko = self.q, self.K, self.K_old
            self.K_old = None
        d = self.dry                                                 # son brut, retardé comme le son traité
        d[:, :-P_B] = d[:, P_B:]
        d[:, -P_B:] = x
        dry = d[:, :P_B].copy()
        # --- milieu / côté, crossover à phase linéaire (overlap-save : une FFT, cinq bandes)
        h = self.hist
        h[:, :-P_B] = h[:, P_B:]
        h[0, -P_B:] = (x[0] + x[1]) * .5
        h[1, -P_B:] = (x[0] - x[1]) * .5
        X = np.fft.rfft(h, axis=-1)
        bands = np.fft.irfft(X[None] * K[:, None], P_N, axis=-1)[..., -P_B:]           # (5, 2, B)
        if Ko is not None:                                                             # nouveaux filtres : fondu d'un bloc
            old = np.fft.irfft(X[None] * Ko[:, None], P_N, axis=-1)[..., -P_B:]
            bands = old + (bands - old) * np.linspace(0, 1, P_B)
        M, S = bands[:, 0], bands[:, 1]
        a = np.abs(M) + np.abs(S)                                     # = max(|gauche|, |droite|) de chaque bande
        sub = a.reshape(5, P_NS, P_SUB)
        lev = 10 * np.log10(np.mean(sub * sub, axis=-1) + 1e-12) + 3.0              # dB (sinus pleine échelle = 0 dB)
        pk = 20 * np.log10(np.max(sub, axis=-1) + 1e-9)
        tot = a.sum(axis=0)
        p_all = float(np.mean(tot * tot))
        lin = 10 * math.log10(p_all + 1e-12) + 3.0
        # --- AGC large bande : lente, à fenêtre (immobile près de la cible), figée sous le seuil de porte
        gated = True
        if q["agc"]:
            self.agc_pow += (p_all - self.agc_pow) * 0.055                            # ≈ 0,35 s
            lvl = 10 * math.log10(self.agc_pow + 1e-12) + 3.0
            if lvl > q["gate"]:
                gated = False
                err = q["agc_target"] - (lvl + self.agc_db)
                win = q["agc_win"]
                if err < -win:                                                         # trop fort : descente (~1 s)
                    self.agc_db += max((err + win) * 0.02 / 0.9, -0.02 * 12.0)
                elif err > win:                                                        # trop faible : remontée lente
                    self.agc_db += min((err - win) * 0.02 / 1.5, 0.02 * q["agc_speed"])
                self.agc_db = max(-14.0, min(q["agc_max"], self.agc_db))
                if q["bagc_max"] > 0:                                                  # AGC des graves
                    e2 = (float(np.mean(lev[1:3])) - 3.0) - (float(np.mean(lev[0])) + self.bagc_db)
                    if abs(e2) > 2.0:
                        self.bagc_db += max(-0.02 * 3.0, min(0.02 * 1.0, (e2 - math.copysign(2.0, e2)) * 0.02 / 2.0))
                    self.bagc_db = max(-q["bagc_max"], min(q["bagc_max"], self.bagc_db))
        else:
            self.agc_db *= 0.95
            self.bagc_db *= 0.95
        base = np.full(5, self.agc_db + q["drive"])
        base[0] += self.bagc_db
        # --- compresseur-limiteur 5 bandes : gains calculés toutes les 1,43 ms, interpolés à l'échantillon
        nodes = np.empty((5, P_NS + 1))
        gr, gl = self.gr, self.gl
        thr, att, rel, lrel = q["thr"], q["a_att"], q["a_rel"], q["a_lrel"]
        slope = 1 - 1 / q["ratio"]
        out_off = q["mix"] + q["makeup"] - thr - 20.0                 # niveau de sortie : seuil ramené vers -20 dB
        coup, blim = q["coup"], q["blim"]
        bgate = q["gate"] - q["drive"] - 8.0 - (thr - thr.max())     # porte par bande
        grmax = np.zeros(5)
        if q["mb_on"]:
            for j in range(P_NS):
                li = lev[:, j] + base
                over = li - thr
                tgt = np.where(over > 4, over * slope, np.where(over > -4, (over + 4) ** 2 / 16 * slope, 0.0))   # genou de 8 dB
                k = np.where(tgt > gr, att, np.where(lev[:, j] + self.agc_db < bgate, rel * 0.02, rel))
                gr += (tgt - gr) * k
                gc = gr + coup * (gr.mean() - gr)                      # couplage : les bandes ne s'écartent pas trop
                g = base - gc + out_off
                lt = np.maximum(0.0, pk[:, j] + g - gl * 0 - blim)    # limiteur de crête par bande (en sortie)
                gl = np.where(lt > gl, lt, gl + (lt - gl) * lrel)
                g = g - gl
                grmax = np.maximum(grmax, gc + gl)
                nodes[:, j + 1] = g
        else:
            nodes[:, 1:] = self.agc_db
        self.gr, self.gl = gr, gl
        nodes = 10 ** (nodes / 20)
        nodes[:, 0] = nodes[:, 1] if self.g_prev is None else self.g_prev
        self.g_prev = nodes[:, -1].copy()
        ramp = np.arange(P_SUB) * (1.0 / P_SUB)
        G = (nodes[:, :-1, None] + (nodes[:, 1:] - nodes[:, :-1])[:, :, None] * ramp).reshape(5, P_B)
        # --- stéréo : élargissement par bande, côté plafonné à 85 % du milieu (image pleine, jamais trouée), graves mono
        Mg, Sg = M * G, S * G
        em = np.einsum("ij,ij->i", Mg, Mg) + 1e-12
        es = np.einsum("ij,ij->i", Sg, Sg) + 1e-12
        wt = q["width"].copy()
        cap = 0.85 * np.sqrt(em / es)
        wt[1:] = np.where(wt[1:] > 1, np.maximum(1.0, np.minimum(wt[1:], cap[1:])), wt[1:])
        w0 = self.w_prev
        w1 = w0 + (wt - w0) * 0.12
        self.w_prev = w1
        W = w0[:, None] + (w1 - w0)[:, None] * np.linspace(0, 1, P_B)
        m = Mg.sum(axis=0)
        s = np.einsum("ij,ij->j", Sg, W) if not q["mono"] else np.zeros(P_B)
        y = np.vstack((m + s, m - s))
        # --- écrêteur doux x2, puis limiteur à anticipation sur les crêtes vraies
        y = self.clipper(y, q)
        y = self.limiter(y, q)
        # --- contournement : fondu de 60 ms entre traité et brut
        want = 0.0 if self.bypass else 1.0
        g0 = self.mix_g
        g1 = g0 if want == g0 else (min(1.0, g0 + 1 / 3) if want > g0 else max(0.0, g0 - 1 / 3))
        self.mix_g = g1
        if g0 < 1.0 or g1 < 1.0:
            y = dry + (y - dry) * (g0 + (g1 - g0) * np.linspace(0, 1, P_B))
        out = np.clip(np.rint(y.T.reshape(-1) * 32767.0), -32768, 32767).astype("<i2").tobytes()
        # --- mesures
        self.loud(y)
        mt = self.meter
        mt["agc"], mt["bagc"], mt["gate"] = self.agc_db, self.bagc_db, gated
        mt["gr"] = [round(float(v), 2) for v in grmax]
        mt["in"] = lin
        mt["bypass"] = self.bypass
        mt["out"] = float(20 * np.log10(np.max(np.abs(y)) + 1e-9))
        mt["ms"] = mt["ms"] * .9 + (time.perf_counter() - t0) * 100
        return out

    def clipper(self, y, q):
        """Écrêteur doux suréchantillonné x2 : arrondit les crêtes isolées (volume perçu) sans repliement audible."""
        y = y * 10 ** (q["clip_drive"] / 20)
        u = np.empty((2, 2 * P_B))
        u[:, 0::2], u[:, 1::2] = y, 0.0
        u = self.up2(u)
        thr = q["ceil"] * 1.06                                        # (le limiteur final rattrape le reste)
        k = (0.9 - 0.3 * q["clip_amt"]) * thr                        # genou : bas si l'on écrête, presque invisible sinon
        au = np.abs(u)
        over = au > k
        n = int(np.count_nonzero(over))
        if n:
            r = thr - k
            u = np.where(over, np.sign(u) * (k + r * np.tanh((au - k) / r)), u)
        self.clip_acc = max(self.clip_acc * 0.85, n / u.size * 100)
        self.meter["clip"] = self.clip_acc
        return self.dn2(u)[:, 0::2]

    def limiter(self, y, q):
        """Limiteur final : crêtes vraies (x4), anticipation d'un sous-bloc, attaque sans dépassement, retour réglable."""
        c = q["ceil"] * 0.977                                         # 0,2 dB de marge : plafond tenu en crête vraie
        u = np.zeros((2, 4 * P_B))
        u[:, 0::4] = y
        pk = np.abs(self.tp(u)).reshape(2, P_B, 4).max(axis=(0, 2))   # (retard de P_TPD échantillons)
        pk = np.maximum(pk, np.concatenate((pk[1:], pk[-1:])))         # marge d'un échantillon (alignement)
        yd = np.concatenate((self.tpd, y), axis=1)
        self.tpd = yd[:, -P_TPD:]
        y = yd[:, :P_B]
        req = (c / np.maximum(pk, c)).reshape(P_NS, P_SUB).min(axis=1)
        nodes = np.empty(P_NS + 1)
        nodes[0] = g = self.lim_g
        prev, rel = self.lim_req_prev, q["lim_rel"]
        for j in range(P_NS):
            t = req[j] if req[j] < prev else prev
            g = t if t < g else g + (t - g) * rel
            nodes[j + 1] = g
            prev = req[j]
        self.lim_req_prev, self.lim_g = prev, g
        ramp = np.arange(P_SUB) * (1.0 / P_SUB)
        Gl = (nodes[:-1, None] + (nodes[1:] - nodes[:-1])[:, None] * ramp).reshape(P_B)
        buf = np.concatenate((self.lim_buf, y), axis=1)
        self.lim_buf = buf[:, -P_SUB:]
        self.meter["lim"] = float(-20 * math.log10(max(1e-6, float(nodes.min()))))
        return np.clip(buf[:, :P_B] * Gl, -c, c)

    def loud(self, y):
        """Sonie (LUFS, pondération K) : court terme (3 s) et momentanée (400 ms)."""
        X = np.fft.rfft(y, 1024, axis=-1)
        ms = float(np.sum((X.real ** 2 + X.imag ** 2) * self.kw)) * 2 / (1024 * P_B)
        self.ms_hist[self.ms_i % 150] = ms
        self.ms_i += 1
        n = min(self.ms_i, 150)
        st = float(np.mean(self.ms_hist[:n]))
        idx = (self.ms_i - 1 - np.arange(min(20, self.ms_i))) % 150
        mm = float(np.mean(self.ms_hist[idx]))
        self.meter["lufs"] = -0.691 + 10 * math.log10(st + 1e-12)
        self.meter["lufs_m"] = -0.691 + 10 * math.log10(mm + 1e-12)


# --- état partagé interface <-> moteur : quatre banques de réglages du processeur (A, B, C, D), contournement (bypass)
# et banque affichée dans l'onglet (ses mesures). Chaque flux choisit sa banque, ou le son brut : plusieurs traitements
# tournent en même temps (ex. Internet sur A, FM sur B avec le filtre 15 kHz, enregistrement en brut).
BANKS = ("A", "B", "C", "D")
RAW = "brut"
FX = {"banks": {b: proc_params() for b in BANKS}, "bypass": False, "edit": "A"}
FX_ON = "Son traité (processeur)"                  # (anciennes valeurs, migrées vers une banque)
FX_NONE = "Son brut (sans traitement)"


def out_bank(cfg):
    """Banque de traitement de ce flux (« A » à « D ») ou « brut ». Ancien réglage : traité -> A, brut -> brut."""
    b = cfg.get("fx")
    if b in BANKS or b == RAW:
        return b
    m = cfg.get("fxmode") or ""
    return RAW if (m == FX_NONE or m == "Aucun traitement") else "A"


def out_processed(cfg):
    """Ce flux reçoit-il le son du processeur d'antenne ?"""
    return out_bank(cfg) != RAW


FM_PROC = "Radio FM (filtre 15 kHz + compresseur + limiteur)"

KINDS = {"internet": ("", "Internet"), "fm": ("", "FM"),
         "dab": ("", "DAB+"), "record": ("", "Enregistrement")}
METER_W = 300
MINI_W = 176
NODEV = "(aucune sortie choisie)"
ROUTES = ["Antenne", "Antenne + carte son", "Sortie audio seulement"]
CART_PER = 12                        # F1 à F12 : les 12 premières tuiles du set affiché
CID = 1000                           # identifiant de lecture d'une tuile = set * 1000 + rang
CART_MODES = {"Par-dessus": "Par-dessus (baisse l'antenne)",
              "Remplace": "Remplace l'antenne (coupe le direct)",
              "Mixé": "Mixé (sans baisser l'antenne)"}
CART_COLORS = {"Bleu": "#4f63f0", "Vert": "#12a678", "Orange": "#f26a35", "Rouge": "#e5485a",
               "Violet": "#8650e0", "Turquoise": "#1aa9bd", "Rose": "#d63f7c", "Gris": "#4b5568"}


# ------------------------------------------------------------------ outils
def popen(cmd, **kw):
    if SYS == "Windows":
        kw.setdefault("creationflags", 0x08000000)  # pas de fenêtre console
    return subprocess.Popen(cmd, **kw)


def stop_proc(p):
    """Arrête un processus sans bloquer ; un encodeur bloqué sur un tube plein est tué après 1 s."""
    try:
        if p.poll() is not None:
            return
        p.terminate()
    except Exception:
        return

    def reap():
        try:
            p.wait(1.0)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
                p.wait(3.0)
            except Exception:
                pass
    threading.Thread(target=reap, daemon=True).start()


def run(cmd, timeout=15):
    kw = {"creationflags": 0x08000000} if SYS == "Windows" else {}
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, **kw)
    return r.stdout + "\n" + r.stderr


_SECRET_RE = re.compile(r"((?:icecast|https?|rtmps?|srt|udp|tcp|ftp)://[^:/@\s]*:)[^@\s]+@", re.I)
_SECRET_Q_RE = re.compile(r"\b((?:pass|password|passwd|pwd|key|token)=)[^&\s]+", re.I)


def redact(text):
    """Masque les mots de passe d'une ligne avant de l'afficher, de l'écrire ou de l'envoyer : ffmpeg recopie l'adresse
    complète du serveur (icecast://source:MOTDEPASSE@hôte…) dans ses messages d'erreur, qui finissaient dans le journal,
    les alertes Discord / mail / SMS et la conversation avec Gaël."""
    t = str(text)
    if "://" in t or "=" in t:
        t = _SECRET_Q_RE.sub(r"\1***", _SECRET_RE.sub(r"\1***@", t))
    return t


# ------------------------------------------------------------------ signature Ed25519 (RFC 8032), en Python pur
# Sert à vérifier que les mises à jour viennent bien de l'auteur de Bev (et pas seulement de GitHub) : la clé privée
# reste sur l'ordinateur de l'auteur (tools/signer.py), seule la clé publique est dans Bev. Python pur, sans
# bibliothèque à installer : la mise à jour express reste possible sur les Bev déjà installés.
_ED_P = 2 ** 255 - 19
_ED_L = 2 ** 252 + 27742317777372353535851937790883648493
_ED_D = -121665 * pow(121666, _ED_P - 2, _ED_P) % _ED_P
_ED_I = pow(2, (_ED_P - 1) // 4, _ED_P)


def _ed_xrecover(y):
    xx = (y * y - 1) * pow(_ED_D * y * y + 1, _ED_P - 2, _ED_P)
    x = pow(xx, (_ED_P + 3) // 8, _ED_P)
    if (x * x - xx) % _ED_P:
        x = x * _ED_I % _ED_P
    if (x * x - xx) % _ED_P:
        raise ValueError("point invalide")
    return x


def _ed_base():
    y = 4 * pow(5, _ED_P - 2, _ED_P) % _ED_P
    x = _ed_xrecover(y)
    if x & 1:
        x = _ED_P - x
    return x, y, 1, x * y % _ED_P


def _ed_add(P, Q):
    p = _ED_P
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C = 2 * P[3] * Q[3] * _ED_D % p
    D = 2 * P[2] * Q[2] % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return E * F % p, G * H % p, F * G % p, E * H % p


def _ed_mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _ed_add(Q, P)
        P = _ed_add(P, P)
        s >>= 1
    return Q


_ED_B = _ed_base()


def _ed_eq(P, Q):
    p = _ED_P
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _ed_enc(P):
    zi = pow(P[2], _ED_P - 2, _ED_P)
    x, y = P[0] * zi % _ED_P, P[1] * zi % _ED_P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _ed_dec(b):
    if len(b) != 32:
        raise ValueError("point invalide")
    y = int.from_bytes(b, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    if y >= _ED_P:
        raise ValueError("point invalide")
    x = _ed_xrecover(y)
    if x == 0 and sign:
        raise ValueError("point invalide")
    if (x & 1) != sign:
        x = _ED_P - x
    return x, y, 1, x * y % _ED_P


def _ed_h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _ed_secret(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed25519_public(seed):
    """Clé publique (32 octets) d'une clé privée (graine de 32 octets)."""
    return _ed_enc(_ed_mul(_ed_secret(seed)[0], _ED_B))


def ed25519_sign(seed, msg):
    """Signature (64 octets) de msg avec la clé privée seed (32 octets)."""
    a, prefix = _ed_secret(seed)
    A = _ed_enc(_ed_mul(a, _ED_B))
    r = _ed_h(prefix + msg) % _ED_L
    R = _ed_enc(_ed_mul(r, _ED_B))
    s = (r + _ed_h(R + A + msg) * a) % _ED_L
    return R + int.to_bytes(s, 32, "little")


def ed25519_verify(pub, msg, sig):
    """True si sig (64 octets) est une signature valide de msg pour la clé publique pub (32 octets)."""
    try:
        if len(pub) != 32 or len(sig) != 64:
            return False
        A, R = _ed_dec(pub), _ed_dec(sig[:32])
        s = int.from_bytes(sig[32:], "little")
        if s >= _ED_L:
            return False
        k = _ed_h(sig[:32] + pub + msg) % _ED_L
        return _ed_eq(_ed_mul(s, _ED_B), _ed_add(R, _ed_mul(k, A)))
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ journal technique des erreurs « silencieuses »
# Beaucoup d'erreurs sont rattrapées pour que l'antenne continue (c'est voulu), mais elles disparaissaient sans trace,
# ce qui rendait certains bugs introuvables. Elles vont désormais dans un petit journal technique (dossier des
# journaux de Bev « Bev_journaux », bev-erreurs.log, 512 Ko au plus), sans encombrer le journal d'antenne. Une même erreur au même
# endroit n'est notée qu'une fois par minute.
TRACE_FILE = os.path.join(os.path.expanduser("~"), "Bev_journaux", "bev-erreurs.log")
_TRACE_SEEN = {}
_TRACE_LK = threading.Lock()


def trace(where, ex=None):
    try:
        now = time.time()
        key = (where, type(ex).__name__)
        with _TRACE_LK:
            if now - _TRACE_SEEN.get(key, 0) < 60:
                return
            _TRACE_SEEN[key] = now
            os.makedirs(os.path.dirname(TRACE_FILE), exist_ok=True)
            if os.path.isfile(TRACE_FILE) and os.path.getsize(TRACE_FILE) > 512 * 1024:
                os.replace(TRACE_FILE, TRACE_FILE + ".1")
            with open(TRACE_FILE, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{os.getpid()}] {where} : "
                         f"{redact(f'{type(ex).__name__}: {ex}') if ex is not None else ''}\n")
    except Exception:
        pass                                   # (le journal technique ne doit jamais gêner l'antenne)


def trace_exc(where, etype, ex, tb):
    """Erreur inattendue (non rattrapée) : notée AVEC sa pile d'appels complète dans le journal technique, pour pouvoir la
    corriger. Même règle qu'ailleurs : une même erreur au même endroit, une fois par minute. Renvoie le résumé d'une ligne."""
    try:
        import traceback
        txt = redact("".join(traceback.format_exception(etype, ex, tb)))
        last = traceback.extract_tb(tb)[-1] if tb else None
        sig = (where, etype.__name__, last.filename if last else "", last.lineno if last else 0)
        now = time.time()
        with _TRACE_LK:
            if now - _TRACE_SEEN.get(sig, 0) < 60:
                return None
            _TRACE_SEEN[sig] = now
            os.makedirs(os.path.dirname(TRACE_FILE), exist_ok=True)
            if os.path.isfile(TRACE_FILE) and os.path.getsize(TRACE_FILE) > 512 * 1024:
                os.replace(TRACE_FILE, TRACE_FILE + ".1")
            with open(TRACE_FILE, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{os.getpid()}] {where} : ERREUR NON RATTRAPÉE (version "
                         f"{_bev_version()})\n{txt}\n")
        place = f" ({os.path.basename(last.filename)}, ligne {last.lineno})" if last else ""
        return redact(f"{etype.__name__}: {ex}")[:160] + place
    except Exception:
        return None


def _bev_version():
    try:
        return sys.modules["bev_version"].VERSION
    except Exception:
        return "?"


CRASH_FILE = os.path.join(os.path.expanduser("~"), "Bev_journaux", "bev-plantage.log")
_CRASH_FH = []


def crash_watch(who="interface"):
    """Plantage brutal (fermeture sans message : erreur grave dans Qt, mémoire…) : Python écrit alors l'endroit du plantage
    dans bev-plantage.log. Ce fichier reste vide si tout se passe bien. Renvoie le rapport d'un plantage PRÉCÉDENT, s'il y
    en a un (et le met de côté dans bev-plantage-precedent.log), sinon ""."""
    prev = ""
    f = CRASH_FILE if who == "interface" else CRASH_FILE.replace(".log", f"-{who}.log")
    try:
        os.makedirs(os.path.dirname(f), exist_ok=True)
        if os.path.isfile(f) and os.path.getsize(f) > 0:
            with open(f, encoding="utf-8", errors="replace") as fh:
                prev = fh.read()[-20000:]
            os.replace(f, f.replace(".log", "-precedent.log"))
        import faulthandler
        fh = open(f, "w", encoding="utf-8")
        faulthandler.enable(fh)
        _CRASH_FH.append(fh)                    # (le fichier doit rester ouvert tant que Bev tourne)
    except Exception as ex:
        trace("crash_watch", ex)
    return prev


def have_module(name):
    try:
        if importlib.util.find_spec(name) is not None:
            return True
    except Exception:
        pass
    if getattr(sys, "frozen", False):  # application empaquetée : on essaie vraiment d'importer
        try:
            importlib.import_module(name)
            return True
        except Exception:
            return False
    return False


def fine_timer():
    """Windows : horloge système à 1 ms (sinon time.sleep arrondit à ~16 ms)."""
    if SYS == "Windows":
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass


def peak_db(chunk):
    """Niveau crête (dBFS) des canaux gauche et droit d'un bloc PCM."""
    if np is not None:
        n = len(chunk) // 4 * 4
        a = np.frombuffer(chunk, dtype="<i2", count=n // 2).reshape(-1, 2)
        if not len(a):
            return [-90.0, -90.0]
        p = np.abs(a.astype(np.int32)).max(axis=0)
        return [20 * math.log10(v / 32768) if v else -90.0 for v in p]
    a = array("h")
    a.frombytes(chunk[:len(chunk) // 4 * 4])
    res = []
    for ch in (0, 1):
        s = a[ch::2]
        p = max(map(abs, s)) if s else 0
        res.append(20 * math.log10(p / 32768) if p else -90.0)
    return res


def mix_blocks(a, b, g0, g1):
    """Fondu enchaîné à puissance constante : g=0 -> a seul, g=1 -> b seul."""
    h = math.pi / 2
    l0, l1 = math.cos(g0 * h), math.cos(g1 * h)
    p0, p1 = math.sin(g0 * h), math.sin(g1 * h)
    if np is not None:
        x = np.frombuffer(a, dtype="<i2").astype(np.float32)
        y = np.frombuffer(b, dtype="<i2").astype(np.float32)
        r = np.arange(len(x), dtype=np.float32) / len(x)
        out = x * (l0 + (l1 - l0) * r) + y * (p0 + (p1 - p0) * r)
        return np.clip(out, -32768, 32767).astype("<i2").tobytes()
    x, y = array("h"), array("h")
    x.frombytes(a)
    y.frombytes(b)
    n = len(x)
    dl, dp = (l1 - l0) / n, (p1 - p0) / n
    out = array("h", (max(-32768, min(32767, int(u * (l0 + dl * i) + v * (p0 + dp * i))))
                      for i, (u, v) in enumerate(zip(x, y))))
    return out.tobytes()


def gain_mix(a, b, g0, g1):
    """a * gain (g0 -> g1 sur le bloc) + b."""
    if np is not None:
        x = np.frombuffer(a, dtype="<i2").astype(np.float32)
        y = np.frombuffer(b, dtype="<i2").astype(np.float32)
        r = np.arange(len(x), dtype=np.float32) / len(x)
        return np.clip(x * (g0 + (g1 - g0) * r) + y, -32768, 32767).astype("<i2").tobytes()
    x, y = array("h"), array("h")
    x.frombytes(a)
    y.frombytes(b)
    n = len(x)
    d = (g1 - g0) / n
    out = array("h", (max(-32768, min(32767, int(u * (g0 + d * i) + v)))
                      for i, (u, v) in enumerate(zip(x, y))))
    return out.tobytes()


def tone_block(phase, freq=1000.0, amp=0.125):
    n = CH // 4
    inc = 2 * math.pi * freq / SR
    a = array("h", bytes(CH))
    for i in range(n):
        v = int(32767 * amp * math.sin(phase + inc * i))
        a[2 * i] = v
        a[2 * i + 1] = v
    return a.tobytes(), (phase + inc * n) % (2 * math.pi)


def trim(buf, hi=50, lo=10):
    """Limite un tampon PCM en gardant les `lo` derniers blocs."""
    if len(buf) > hi * CH:
        del buf[:(len(buf) - lo * CH) // CH * CH]


def track_info(path):
    """(titre affichable, durée en secondes) d'un fichier audio."""
    base, dur = os.path.splitext(os.path.basename(path))[0], 0.0
    if shutil.which("ffprobe"):
        try:
            out = run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_entries",
                       "format=duration:format_tags", path], timeout=8)
            fmt = json.loads(out[:out.rindex("}") + 1])["format"]
            dur = float(fmt.get("duration") or 0)
            tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
            if tags.get("title"):
                base = (tags["artist"] + " - " if tags.get("artist") else "") + tags["title"]
        except Exception as _ex:
            trace("track_info", _ex)
    return base, dur


def track_title(path):
    return track_info(path)[0]


def _ff_png(src, size, extra=(), data=None, err=None):
    """Image (fichier, ou octets `data` sur l'entrée standard) réduite en PNG ; `err` (liste) reçoit le message d'erreur de ffmpeg."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin" if data is None else "-y", "-loglevel", "error", *extra, "-i", src, "-an",
             "-map", "0:v:0?", "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease,format=rgba",
             "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
            input=data, capture_output=True, stdin=subprocess.DEVNULL if data is None else None, timeout=20,
            creationflags=0x08000000 if SYS == "Windows" else 0)
        if r.stdout[:4] == b"\x89PNG":
            return r.stdout
        if err is not None:
            err.append((r.stderr or b"").decode("utf-8", "replace").strip()[-300:] or "aucune image dans le fichier")
    except Exception as ex:
        if err is not None:
            err.append(str(ex))
    return None


def _ogg_picture(path):
    """Pochette des .ogg / .opus / .oga (étiquette METADATA_BLOCK_PICTURE, que ffmpeg n'extrait pas) : octets de l'image ou None."""
    import base64
    import struct
    try:
        out = run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_entries", "stream_tags:format_tags", path], timeout=15)
        js = json.loads(out[:out.rindex("}") + 1])
        tags = dict(js.get("format", {}).get("tags", {}))
        for st in js.get("streams", []):
            tags.update(st.get("tags", {}))
        raw = next((v for k, v in tags.items() if k.lower() == "metadata_block_picture"), None)
        if not raw:
            return None
        b = base64.b64decode(raw)
        o = 4  # type
        n = struct.unpack(">I", b[o:o + 4])[0]
        o += 4 + n  # type MIME
        n = struct.unpack(">I", b[o:o + 4])[0]
        o += 4 + n  # description
        o += 16  # largeur, hauteur, profondeur, couleurs
        n = struct.unpack(">I", b[o:o + 4])[0]
        return b[o + 4:o + 4 + n]
    except Exception:
        return None


def _cover_extract(path, size=96, err=None):
    png = _ff_png(path, size, err=err)
    if png:
        return png
    if path.lower().endswith((".ogg", ".opus", ".oga")):
        img = _ogg_picture(path)
        if img:
            png = _ff_png("pipe:0", size, extra=("-f", "image2pipe"), data=img, err=err)
            if png:
                return png
    try:  # image du dossier : cover / folder / front / album… ; ou l'unique image du dossier
        d = os.path.dirname(path)
        imgs = [f for f in os.listdir(d) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp"))]
        low = {f.lower(): f for f in imgs}
        pick = None
        for stem in ("cover", "folder", "front", "album", "albumart", "artwork", "albumartsmall", "thumb"):
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                if stem + ext in low:
                    pick = low[stem + ext]
                    break
            if pick:
                break
        if not pick:
            pick = next((f for f in imgs if any(k in f.lower() for k in ("cover", "front", "folder", "album", "pochette"))), None)
        if not pick and len(imgs) == 1:
            pick = imgs[0]
        if pick:
            return _ff_png(os.path.join(d, pick), size, err=err)
    except Exception as _ex:
        trace("_cover_extract", _ex)
    return None


def cover_png(path, size=96):
    """Pochette d'un fichier avec cache disque (~/.broadcast_tool_covers) : instantanée aux lancements suivants."""
    try:
        stt = os.stat(path)
        key = hashlib.sha1(f"v3|{path}|{stt.st_mtime_ns}|{stt.st_size}|{size}".encode("utf-8", "replace")).hexdigest()
        d = os.path.expanduser("~/.broadcast_tool_covers")
        fp = os.path.join(d, key + ".png")
        if os.path.isfile(fp):
            with open(fp, "rb") as fh:
                b = fh.read()
            if b[:4] == b"\x89PNG":
                return b
            # fichier vide = « pas de pochette » : on ne s'y fie que 10 min (un échec ponctuel ne doit pas masquer la pochette)
            if time.time() - os.path.getmtime(fp) < 600:
                return None
    except OSError:
        fp = None
    if not shutil.which("ffmpeg"):
        return None                     # sans ffmpeg on ne conclut rien : on réessaiera plus tard
    png = _cover_extract(path, size)
    if not png:
        png = _cover_extract(path, size)          # un second essai : un échec isolé (disque occupé, délai) ne doit pas masquer la pochette
    if fp and png:                                # on ne mémorise jamais un échec
        try:
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "wb") as fh:
                fh.write(png or b"")
        except OSError:
            pass
    return png


def scale_pcm(chunk, g):
    if np is not None:
        a = np.frombuffer(chunk, dtype="<i2").astype(np.float32) * g
        return np.clip(a, -32768, 32767).astype("<i2").tobytes()
    a = array("h")
    a.frombytes(chunk)
    return array("h", (max(-32768, min(32767, int(x * g))) for x in a)).tobytes()


def pcm_process(pcm, trim=False, maxi=False):
    """Cartouche : coupe les blancs de début/fin et/ou amène le pic à -1 dBFS."""
    if not pcm or not (trim or maxi):
        return pcm
    margin, thr = 220, 80  # 5 ms de marge ; seuil d'environ -52 dB
    if np is not None:
        a = np.frombuffer(pcm, dtype="<i2").reshape(-1, 2)
        if trim:
            idx = np.flatnonzero(np.abs(a.astype(np.int32)).max(axis=1) > thr)
            if len(idx):
                a = a[max(0, idx[0] - margin): idx[-1] + margin + 1]
        if maxi and len(a):
            pk = int(np.abs(a.astype(np.int32)).max())
            g = min(16.0, 29200 / pk) if pk else 1.0
            if g > 1.02:
                a = np.clip(a.astype(np.float32) * g, -32768, 32767).astype("<i2")
        return a.tobytes()
    s = array("h")
    s.frombytes(pcm)
    if trim:
        n = len(s) // 2
        i = 0
        while i < n and abs(s[2 * i]) <= thr and abs(s[2 * i + 1]) <= thr:
            i += 1
        if i < n:
            j = n - 1
            while j > i and abs(s[2 * j]) <= thr and abs(s[2 * j + 1]) <= thr:
                j -= 1
            s = s[2 * max(0, i - margin): 2 * min(n, j + margin + 1)]
    if maxi and s:
        pk = max(max(s), -min(s))
        g = min(16.0, 29200 / pk) if pk else 1.0
        if g > 1.02:
            s = array("h", (max(-32768, min(32767, int(x * g))) for x in s))
    return s.tobytes()


def wave_bins(pcm, n=240):
    """Forme d'onde : n valeurs de 0 à 1 (crête de chaque tranche)."""
    if not pcm:
        return [0.0] * n
    if np is not None:
        a = np.abs(np.frombuffer(pcm, dtype="<i2")[::6].astype(np.int32))
        if len(a) < n:
            a = np.pad(a, (0, n - len(a)))
        return [float(c.max()) / 32768 for c in np.array_split(a, n)]
    s = array("h")
    s.frombytes(pcm)
    L = max(1, len(s) // n)
    out = []
    for k in range(n):
        seg = s[k * L:(k + 1) * L:8]
        out.append(max(map(abs, seg)) / 32768 if seg else 0.0)
    return out


def fmt_ms(sec):
    """Durée courte : MM:SS, ou H:MM:SS pour les émissions de plus d'une heure."""
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60:02d}:{sec % 60:02d}"


def fmt_cs(sec):
    """Temps de cartouche à la Farrago : 0:04.8 (dixièmes de seconde)."""
    sec = max(0.0, float(sec))
    t = int(sec * 10 + .5)
    return f"{t // 600}:{t // 10 % 60:02d}.{t % 10}"


def fmt_dur(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


# --------------------------------------------------- périphériques d'entrée
def dev_short_name(device):
    """Nom lisible d'une entrée (« loopback:Haut-parleurs » -> « Son de l'ordinateur (Haut-parleurs) »)."""
    d = str(device or "")
    if d == "loopback:default":
        return "Son de l'ordinateur"
    if d.startswith("loopback:"):
        return f"Son de l'ordinateur ({d[9:]})"
    if d.startswith("lavfi:"):
        return "Générateur de test"
    return d or "(aucune)"


def input_args(device):
    if str(device).startswith("lavfi:"):          # générateur de test (diagnostic, essais sans carte son)
        return ["-re", "-f", "lavfi", "-i", device[6:]]
    if SYS == "Windows":
        return ["-f", "dshow", "-i", f"audio={device}"]
    if SYS == "Darwin":
        return ["-f", "avfoundation", "-i", f":{device}"]
    return ["-f", "pulse", "-i", device]


def have_loopback():
    return SYS == "Windows" and have_module("pyaudiowpatch")


def loopback_devices():
    """Entrées « son de l'ordinateur » (WASAPI loopback), Windows uniquement."""
    if not have_loopback():
        return []
    import pyaudiowpatch as pa
    pa_inst = pa.PyAudio()
    try:
        devs = [("Son de l'ordinateur (sortie par défaut)", "loopback:default")]
        for d in pa_inst.get_loopback_device_info_generator():
            devs.append((f"Son de l'ordinateur : {d['name']}", "loopback:" + d["name"]))
        return devs
    finally:
        pa_inst.terminate()


def list_devices():
    """Retourne (liste de (libellé, valeur ffmpeg), texte brut de diagnostic)."""
    devs, raw = [], ""
    if SYS == "Linux":
        if shutil.which("ffmpeg"):
            raw = run(["ffmpeg", "-hide_banner", "-sources", "pulse"])
            for line in raw.splitlines():
                m = re.match(r"\s*\*?\s*(\S+)\s+\[(.*)\]\s*$", line)
                if m:
                    devs.append((m.group(2), m.group(1)))
        if not devs and shutil.which("pactl"):
            raw = run(["pactl", "list", "short", "sources"])
            for line in raw.splitlines():
                p = line.split("\t")
                if len(p) > 1:
                    devs.append((p[1], p[1]))
        return devs, raw
    fmt = "dshow" if SYS == "Windows" else "avfoundation"
    raw = run(["ffmpeg", "-hide_banner", "-f", fmt, "-list_devices", "true",
               "-i", "dummy" if SYS == "Windows" else ""])
    section = None
    for line in raw.splitlines():
        if "audio devices" in line:
            section = "audio"
        elif "video devices" in line:
            section = "video"
        elif "Alternative name" in line:
            continue
        elif SYS == "Windows":
            m = re.search(r'"([^"]+)"(?:\s+\(([^)]*)\))?', line)
            if m and ("audio" in (m.group(2) or "") or
                      (m.group(2) is None and section == "audio")):
                devs.append((m.group(1), m.group(1)))
        elif section == "audio":
            m = re.search(r"\[(\d+)\]\s+(.+)$", line)
            if m:
                devs.append((m.group(2).strip(), m.group(1)))
    if SYS == "Windows":
        try:
            devs = loopback_devices() + devs
        except Exception as e:
            raw += f"\nCapture du son de l'ordinateur indisponible : {e}"
    return devs, raw


_SD_STREAMS = []          # flux sounddevice ouverts dans CE processus (on ne réinitialise pas PortAudio sous leurs pieds)
_SD_SCAN = [0.0]
SDLIST_ARG = "--bev-sd-list"


def sd_track(st):
    _SD_STREAMS[:] = [x for x in _SD_STREAMS if not getattr(x, "closed", True)] + [st]
    return st


def sd_rescan(force=False):
    """PortAudio ne relit la liste des cartes son qu'à son démarrage : une carte débranchée restait affichée pendant des
    jours. On le redémarre (rapide) pour relire les cartes réellement branchées, sauf si un son joue dans ce processus."""
    import sounddevice as sd
    if any(not getattr(x, "closed", True) for x in _SD_STREAMS):
        return False
    if not force and time.time() - _SD_SCAN[0] < 2.0:
        return True
    try:
        sd._terminate()
        sd._initialize()
        _SD_SCAN[0] = time.time()
        return True
    except Exception:
        return False


def _sd_query():
    import sounddevice as sd
    apis = sd.query_hostapis()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] >= 2:
            out.append((f"{d['name']} [{apis[d['hostapi']]['name']}]", i))
    return out


def list_output_devices(fresh=True):
    """Cartes son de sortie : [(libellé, index)]. fresh : liste relue (cartes débranchées retirées, nouvelles ajoutées)."""
    if fresh and not sd_rescan():
        # un son joue dans ce processus : la liste fraîche est lue par un petit processus à part (libellés seulement)
        try:
            import tempfile
            fn = os.path.join(tempfile.gettempdir(), f"bev-sd-{os.getpid()}.json")
            subprocess.run(worker_cmd() + [SDLIST_ARG, fn], timeout=12, env=clean_env(False, False),
                           creationflags=0x08000000 if SYS == "Windows" else 0, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with open(fn, encoding="utf-8") as fh:
                labels = json.load(fh)
            os.remove(fn)
            known = dict(_sd_query())
            return [(l, known.get(l, -1)) for l in labels]
        except Exception as _ex:
            trace("list_output_devices", _ex)
    return _sd_query()


if SDLIST_ARG in sys.argv and __name__ in ("__main__", "__mp_main__"):
    try:
        _fn = sys.argv[sys.argv.index(SDLIST_ARG) + 1]
        with open(_fn, "w", encoding="utf-8") as _fh:
            json.dump([l for l, _ in _sd_query()], _fh)
    except Exception:
        pass
    os._exit(0)


def out_name(label):
    """« Haut-parleurs (Realtek) [Windows WASAPI] » -> « Haut-parleurs (Realtek) »."""
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", label or "").strip() or (label or "")


def out_choices(labels, keep=""):
    """Une seule ligne par carte son : Windows liste chaque carte 3 ou 4 fois (MME, DirectSound, WASAPI, WDM-KS). On
    garde la version WASAPI (la plus fiable et la plus réactive) ; ailleurs, tout reste. `keep` (choix enregistré) reste
    toujours visible."""
    labels = list(labels)
    if SYS == "Windows":
        best = [l for l in labels if l.endswith("[Windows WASAPI]")] or [l for l in labels if l.endswith("[MME]")] or labels
    else:
        best = labels
    seen, out = set(), []
    for l in best:
        n = out_name(l).lower()
        if n not in seen:
            seen.add(n)
            out.append(l)
    if keep and keep not in out:
        out.append(keep)
    return out


# ---------------------------------------------------------- Shoutcast v1
def shoutcast_connect(c):
    """Protocole source Shoutcast v1/ICY : port du serveur + 1 par défaut."""
    port = int(c.get("sc_port") or int(c["port"]) + 1)
    s = socket.create_connection((c["host"], port), timeout=10)
    s.sendall(c["password"].encode() + b"\n")
    if b"OK" not in s.recv(1024):
        s.close()
        raise RuntimeError("Mot de passe refusé par le serveur Shoutcast")
    ctype = FORMATS[c["format"]][2]
    hdr = (f"content-type:{ctype}\r\nicy-name:{c['name']}\r\n"
           f"icy-genre:{c['genre']}\r\nicy-br:{c['bitrate']}\r\n"
           f"icy-pub:0\r\nicy-description:{c['desc']}\r\n\r\n")
    s.sendall(hdr.encode("utf-8", "replace"))
    s.settimeout(None)
    return s


# ------------------------------------------------------- modèle de données
def listen_url(c):
    """Adresse que les auditeurs utilisent pour écouter une sortie Internet."""
    host, port = (c.get("host") or "").strip(), str(c.get("port") or "").strip()
    scheme = "https" if port in ("443", "8443") else "http"
    base = f"{scheme}://{host}" + ("" if port in ("", "80", "443") else f":{port}")
    if c.get("protocol") == "Shoutcast":
        return base + "/;"
    return base + "/" + (c.get("mount") or "").lstrip("/")


def slugify(text):
    t = "".join(ch for ch in unicodedata.normalize("NFD", str(text).lower()) if unicodedata.category(ch) != "Mn")
    t = re.sub(r"[^a-z0-9._/-]+", "-", t).strip("-/")
    return re.sub(r"-{2,}", "-", t)


def new_output(kind, name=None):
    o = {"id": uuid.uuid4().hex[:8], "type": kind, "enabled": True,
         "name": name or KINDS[kind][1], "reconnect": True, "processing": "Aucun"}
    if kind == "internet":
        o.update(protocol="Icecast", host="localhost", port="8000", sc_port="",
                 mount="/live", user="source", password="", tls=False, format="MP3",
                 bitrate="128", channels="2", genre="Various", desc="")
    elif kind == "fm":
        o.update(device="", processing=FM_PROC, rds=False, ps="RADIO",
                 rds_mode="Fichier / pipe", rds_target="",
                 rds_template="PS {PS}\\nRT {RT}\\n")
    elif kind == "dab":
        o.update(mode="ODR-AudioEnc", odr_path="odr-audioenc",
                 dest="tcp://127.0.0.1:9000", bitrate="96", profile="HE-AAC (SBR)",
                 extra="", dls_file="", net_url="udp://127.0.0.1:5004",
                 net_format="mpegts", processing="Limiteur doux")
    elif kind == "record":
        o.update(folder=os.path.join(os.path.expanduser("~"), "Enregistrements radio"),
                 format="MP3", bitrate="192", rotate="60", keep_days="0",
                 prefix="", stamp="2026-10-23_16h30", pige="0", date="1")
    return o


def hist_path():
    return os.path.join(os.path.dirname(CONF), "broadcast_history.csv")


def new_cart():
    return {"name": "", "file": "", "color": "Bleu", "mode": "Par-dessus", "loop": False, "vol": 100,
            "trim": False, "maximize": False, "fade": 0.0, "fade_in": None, "fade_out": None, "fade_click": None, "group": 0,
            "start": 0.0, "end": 0.0, "emoji": "", "key": "", "midi": "", "notes": "",
            "solo": False, "pausable": False, "hold": False}


def default_profile():
    return {
        "source": {"device": DEFAULT_DEVICE},
        "fallback": {"enabled": False, "shuffle": False, "threshold": "-50",
                     "silence_s": "10", "recover_s": "2", "fade_in": "0.5", "fade_out": "1.2", "playlist": [], "off": [],
                     "jingle": {"enabled": False, "every": "15", "files": []}},
        "outputs": [],
        "meta": {"text": "", "follow": True},
        "delay": "0", "gain": "0", "cover": "",
        "carts": {"duck": 70, "fade_click": 2.5, "master": 100, "device": "", "route": ROUTES[0], "solo": False, "pages": [[], []],
                  "names": ["Set 1", "Set 2"], "locks": ["", ""]},
    }


def norm_carts(c):
    """Sets de tuiles : nombre libre de sets nommés (verrouillables), nombre libre de sons par set.
    Ancien format (4 pages de 12 touches A à D) : converti, touches vides retirées."""
    c.setdefault("duck", 70)
    c.setdefault("fade_click", 2.5)
    c.setdefault("master", 100)
    pages = c.get("pages") if isinstance(c.get("pages"), list) else []
    pages = [pg if isinstance(pg, list) else [] for pg in pages] or [[]]
    legacy = not isinstance(c.get("names"), list)
    for pg in pages:
        pg[:] = [fill(x, new_cart()) for x in pg if isinstance(x, dict) and x.get("file")]
        for x in pg:
            f = x.get("fade") or 0
            for k in ("fade_in", "fade_out"):
                if x.get(k) is None:
                    x[k] = f
    if legacy:
        while len(pages) > 1 and not pages[-1]:
            pages.pop()
    names = [str(n) for n in c.get("names") or []] if not legacy else [f"Page {chr(65 + k)}" for k in range(len(pages))]
    locks = [str(n) for n in c.get("locks") or []] if not legacy else []
    c["pages"] = pages
    c["names"] = (names + [f"Set {k + 1}" for k in range(len(names), len(pages))])[:len(pages)]
    c["locks"] = (locks + [""] * len(pages))[:len(pages)]
    return c


def upgrade(p):
    """Profil v2 (Extras + Planning) -> v3 (titre, retard, cartoucheur)."""
    c = p.get("carts")
    if isinstance(c, dict):  # réglages d'édition globaux (ancienne version) -> propres à chaque cartouche
        for pg in c.get("pages") or []:
            for cart in pg if isinstance(pg, list) else []:
                if isinstance(cart, dict):
                    for k in ("trim", "maximize"):
                        cart.setdefault(k, bool(c.get(k, False)))
    j = (p.get("fallback") or {}).get("jingle")
    if isinstance(j, dict) and "files" not in j:  # un seul jingle -> liste de jingles
        j["files"] = [j["file"]] if j.get("file") else []
    if isinstance(j, dict):
        j.pop("file", None)
    ex = p.pop("extras", None)
    p.pop("schedule", None)
    if ex:
        m = ex.get("meta", {})
        p.setdefault("meta", {"text": m.get("text", ""),
                              "follow": m.get("mode") == "Suivre la playlist de secours"})
        p.setdefault("delay", str(ex.get("delay", "0")))
        old = [j for j in ex.get("jingles", []) if j.get("file")]
        if old and "carts" not in p:
            page = [dict(new_cart(), name=j.get("name", ""), file=j["file"],
                         mode=j.get("mode") if j.get("mode") in CART_MODES else "Par-dessus")
                    for j in old]
            p["carts"] = {"duck": 70, "pages": [page]}
    fill(p, default_profile())
    norm_carts(p["carts"])
    return p


def fill(d, defaults):
    """Complète d avec les clés manquantes de defaults (récursif)."""
    for k, v in defaults.items():
        if k not in d:
            d[k] = json.loads(json.dumps(v))
        elif isinstance(v, dict) and isinstance(d[k], dict):
            fill(d[k], v)
    return d


def migrate_preset(old):
    """Ancien réglage à plat (v1) -> profil v2 avec une sortie Internet."""
    p = default_profile()
    p["source"]["device"] = old.get("device", DEFAULT_DEVICE)
    fb = p["fallback"]
    fb["enabled"] = bool(old.get("fallback", False))
    for k in ("shuffle", "threshold", "silence_s", "recover_s", "fade_in", "fade_out", "playlist"):
        if k in old:
            fb[k] = old[k]
    if old.get("host") or old.get("password"):
        o = new_output("internet", old.get("name") or "Internet")
        for k in ("protocol", "host", "port", "mount", "user", "password", "format",
                  "bitrate", "channels", "genre", "desc", "reconnect"):
            if k in old:
                o[k] = old[k]
        p["outputs"].append(o)
    return p


# ------------------------------------------------------------------ secrets du fichier de réglages
# Mots de passe des serveurs, mot de passe mail, clé SMS, clé de Gaël, adresse de webhook (qui vaut mot de passe) :
# sous Windows, chiffrés dans le fichier par DPAPI (fonction de Windows, sans bibliothèque à installer) : lisibles
# seulement par CE compte Windows sur CET ordinateur. Copier le fichier de réglages ailleurs ne livre plus les
# mots de passe. En mémoire, dans Bev, ils restent en clair (le moteur et les flux en ont besoin).
SECRET_KEYS = {"password", "gael_key", "mail_pw", "sms_key"}
SECRET_PREFIX = "dpapi:"
SECRETS_LOST = []                 # secrets illisibles au chargement (réglages venus d'un autre PC / compte Windows)


def _dpapi(data, protect):
    try:
        import ctypes
    except ImportError:
        raise OSError("ctypes absent")

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data, len(data))
    src, out = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):   # 0x1 : jamais de fenêtre
        raise OSError("DPAPI a refusé")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _protect_on():
    """Chiffrer à l'enregistrement ? Seulement l'application INSTALLÉE (≥ 1.2.1) qui tourne sur son propre code : si une
    mise à jour express échoue, Bev repart sur la version installée, qui doit savoir relire ces mots de passe. Depuis
    le code source (tests), rien n'est chiffré : une version installée plus ancienne lit le même fichier."""
    return SYS == "Windows" and bool(getattr(sys, "frozen", False)) and os.environ.get("BEV_CODE") == "builtin"


def _walk_secrets(d, fn, path=""):
    if isinstance(d, dict):
        for k, v in d.items():
            p = f"{path}.{k}" if path else str(k)
            if isinstance(v, str) and v and (k in SECRET_KEYS or p == "alerts.url"):
                d[k] = fn(v, p)
            elif isinstance(v, (dict, list)):
                _walk_secrets(v, fn, p)
    elif isinstance(d, list):
        for i, v in enumerate(d):
            _walk_secrets(v, fn, f"{path}[{i}]")


def reveal_secrets(d):
    """Déchiffre (sur place) les secrets lus dans le fichier. Illisible : vidé, et noté dans SECRETS_LOST."""
    def dec(v, p):
        if not v.startswith(SECRET_PREFIX):
            return v
        try:
            return _dpapi(base64.b64decode(v[len(SECRET_PREFIX):]), False).decode("utf-8")
        except Exception:
            SECRETS_LOST.append(p)
            return ""
    _walk_secrets(d, dec)
    return d


def protect_secrets(d):
    """Copie de d avec les secrets chiffrés (d n'est pas modifié). En cas d'échec de DPAPI : en clair, comme avant."""
    d = json.loads(json.dumps(d))

    def enc(v, p):
        if v.startswith(SECRET_PREFIX):
            return v
        try:
            return SECRET_PREFIX + base64.b64encode(_dpapi(v.encode("utf-8"), True)).decode("ascii")
        except Exception:
            return v
    _walk_secrets(d, enc)
    return d


def load_data():
    try:
        with open(CONF, encoding="utf-8") as f:
            d = json.load(f)
        reveal_secrets(d)
        if "profiles" not in d:  # ancien format
            bak = CONF + ".v1.bak"
            if not os.path.exists(bak):
                shutil.copy(CONF, bak)
            old = d.get("presets") or {"Défaut": d}
            d = {"last": d.get("last", "Défaut"),
                 "profiles": {n: migrate_preset(v) for n, v in old.items()},
                 "monitor": d.get("monitor", {})}
        if not d["profiles"]:
            d["profiles"] = {"Défaut": default_profile()}
        for n in d["profiles"]:
            upgrade(d["profiles"][n])
        d.setdefault("monitor", {})
        d.setdefault("alerts", {})
        d.setdefault("counts", {})
        if d.get("last") not in d["profiles"]:
            d["last"] = next(iter(d["profiles"]))
        return d
    except Exception as ex:
        # Réglages illisibles (fichier abîmé par une coupure de courant, modifié à la main…) : on les met de côté AVANT de
        # repartir des réglages par défaut. Sans cela, le premier enregistrement écrasait tous les profils, flux et
        # playlists de la radio, sans retour possible.
        if os.path.exists(CONF) and not isinstance(ex, FileNotFoundError):
            try:
                shutil.copy2(CONF, CONF + time.strftime(".illisible-%Y%m%d-%H%M%S.bak"))
            except OSError:
                pass
        return {"last": "Défaut", "profiles": {"Défaut": default_profile()},
                "monitor": {}, "alerts": {}, "counts": {}}


def save_data(d):
    tmp = CONF + ".tmp"
    if _protect_on():
        d = protect_secrets(d)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.flush()
        try:
            os.fsync(f.fileno())                # coupure de courant juste après : le fichier n'est pas vide
        except OSError:
            pass
    if SYS != "Windows":
        try:
            os.chmod(tmp, 0o600)                # mots de passe des serveurs, clés : lisibles par cet utilisateur seulement
        except OSError:
            pass
    os.replace(tmp, CONF)

# ------------------------------------------------------------------ moteur
class CartMonitor:
    """Envoie le son des cartouches vers une carte son locale (casque, pré-écoute)."""

    def __init__(self, log):
        self.log, self.label, self.stream = log, "", None
        self.buf, self.lk, self.primed = bytearray(), threading.Lock(), False

    def set_device(self, label):
        if label == self.label:
            return
        self.close()
        self.label = label
        if label:
            threading.Thread(target=self.open, args=(label,), daemon=True).start()

    def open(self, label):
        try:
            import sounddevice as sd
            idx = dict(list_output_devices()).get(label)
            if idx is None or idx < 0:
                raise RuntimeError("carte son introuvable (débranchée ?)")

            def cb(outdata, frames, t, status):
                need = frames * 4
                with self.lk:
                    if not self.primed and len(self.buf) >= 6 * CH:
                        self.primed = True
                    chunk = bytes(self.buf[:need]) if self.primed else b""
                    del self.buf[:len(chunk)]
                    if self.primed and not self.buf:
                        self.primed = False
                outdata[:need] = chunk + bytes(need - len(chunk))
            extra = sd.WasapiSettings(auto_convert=True) if "WASAPI" in label else None
            st = sd_track(sd.RawOutputStream(samplerate=SR, channels=2, dtype="int16", device=idx,
                                             callback=cb, latency="low", extra_settings=extra))
            st.start()
            if self.label != label:
                return st.close()
            self.stream = st
            self.log(f"Cartoucheur : carte son « {label} » prête.")
        except ImportError:
            self.log("Cartoucheur : module sounddevice manquant (onglet SOS > Installer).")
        except Exception as e:
            self.log(f"Cartoucheur : carte son indisponible ({e}).")

    def push(self, block):
        if self.stream:
            with self.lk:
                self.buf += block
                if len(self.buf) > 60 * CH:
                    del self.buf[:len(self.buf) - 14 * CH]

    def close(self):
        st, self.stream, self.label = self.stream, None, ""
        with self.lk:
            self.buf.clear()
            self.primed = False
        if st:
            try:
                st.stop()
                st.close()
            except Exception:
                pass


class Engine:
    """Moteur audio PERMANENT (sans interface) : il démarre avec l'application et ne s'arrête qu'à sa fermeture.
    Cartoucheur, contrôle d'entrée et antenne sont trois états de ce même moteur, qui ne se gênent jamais :
      - cartouches : toujours jouables (casque hors antenne, antenne pendant la diffusion) ;
      - capture de l'entrée : ouverte seulement quand on regarde l'entrée (monitor) ou pendant l'antenne (air) ;
      - antenne (air) : flux de sortie, détection de silence, playlist de secours, retard de sécurité.
    Démarrer / arrêter la diffusion ne coupe donc plus les cartouches, et le contrôle d'entrée ne touche à rien d'autre."""

    def __init__(self, prof, log, alert=None, standalone=False):
        self.prof, self.log, self.standalone = prof, log, False
        self.alert = alert or (lambda text, key=None: None)
        self.lock = threading.Lock()
        self.air_lk = threading.RLock()
        self.ev = threading.Event()
        self.running = False
        self.started = 0.0
        self.air = self.monitor = self.listen = False
        self.src_dev = (prof.get("source") or {}).get("device", "")
        self.cap_gen, self.cap_wake = 0, threading.Event()
        self.cap_state, self.cap_err, self.cap_t = "off", "", 0.0
        self.fb_ver, self._fbp, self._fbp_ver = 0, None, -1
        self.counts_ver = 0
        self.fb_note = ""
        self.live_buf, self.pl_buf = bytearray(), bytearray()
        self.pl_marks, self.pl_in, self.pl_out = deque(), 0, 0
        self.backup = self.manual = self.mute = self.tone = self.pl_active = False
        self.pl_pause = False                 # playlist de secours en pause (reprend exactement où elle s'était arrêtée)
        self.pl_stop = False                  # playlist de secours arrêtée à la main (pas de relève auto avant le retour du son)
        self.silent_ms = self.loud_ms = 0
        self.pl_silent_ms = 0                 # playlist de secours à l'antenne mais muette (ms)
        self.inc = {}                         # pannes en cours déjà signalées : clé -> instant du début
        self.mix_g, self.rec_ms = 0.0, 2000.0
        self.peak = [-90.0, -90.0]
        self.track, self.meta = "", ""
        self.meta_manual = prof["meta"].get("text", "")
        self.delay_blocks = self.to_blocks(prof.get("delay", "0"))
        self.delay_q = deque()
        self.voices, self.loading, self.duck_g = [], set(), 1.0
        self.pcm_cache = {}
        self.pcm_lk = threading.Lock()         # le cache est rempli par plusieurs fils (préchargement, tuiles lancées)
        self.in_peak, self.clip_t, self.pl_cur = [-90.0, -90.0], 0.0, None
        self.proc_ms, self.late, self.late_t = 0.0, 0, 0.0
        self.late_hist = []
        self.next_file, self.pl_skip = None, False
        self.gain = 1.0
        self.set_gain(prof.get("gain", "0"))
        self.cmon = CartMonitor(self.log)
        # processeur d'antenne : une instance par banque UTILISÉE (par un flux, ou affichée dans l'onglet), créée à la demande
        self.procs, self.proc_used = {}, {}    # banque -> AirProcessor ; banque -> dernier instant où elle a servi
        self.proc_making = set()
        self.proc_ok = np is not None          # passe à False si le processeur échoue (le son part alors brut)
        self.pm = {}                           # mesures de la banque affichée (AGC, réduction de gain par bande, LUFS…)
        self.pm_main = {}                      # mesures de la banque principale (celle du 1er flux traité) : sonie d'antenne
        self.main_bank = "A"
        self.cap_proc = self.pl_proc = None
        self.cap_stream = None
        self.outputs = []                      # flux : créés seulement à la mise à l'antenne

    # --- démarrage / arrêt du moteur (= ouverture / fermeture de l'application)
    def start(self):
        self.running = True
        self.ev.clear()
        c = self.prof["carts"]
        self.cmon.set_device(c.get("device", ""))
        for fn in (self.capture_loop, self.playlist_loop, self.feeder_loop, self.meta_loop,
                   self.preload_carts, self.jingle_loop):
            threading.Thread(target=fn, daemon=True).start()
        self.prewarm()

    def prewarm(self):
        """Prépare à l'avance les processeurs des banques qui vont servir (sinon les premiers dixièmes de seconde
        d'antenne partiraient en son brut, le temps de calculer les filtres)."""
        if not self.proc_ok:
            return
        want = {FX.get("edit") if FX.get("edit") in BANKS else "A"}
        want |= {out_bank(c) for c in self.prof.get("outputs", []) if c.get("enabled", True)}
        for b in want - {RAW}:
            if b not in self.procs:
                self._proc_make(b)

    def stop(self):
        self.running = False
        self.ev.set()
        self.cap_wake.set()
        self.cmon.close()
        for o in self.outputs:
            o.stop()
        self._cap_kill()
        if self.pl_proc:
            stop_proc(self.pl_proc)

    # --- antenne : marche / arrêt (le moteur, lui, continue : cartouches et casque ne sont jamais coupés)
    def set_air(self, on, prof=None):
        with self.air_lk:
            if on:
                if prof is not None:
                    self.set_prof(prof)
                for o in self.outputs:              # (sécurité) anciens flux encore présents
                    threading.Thread(target=o.stop, daemon=True).start()
                with self.lock:
                    self.pl_buf.clear()
                    self.pl_marks.clear()
                    self.pl_in = self.pl_out = 0
                self.backup = self.manual = self.mute = self.tone = self.pl_active = self.pl_pause = self.pl_stop = False
                self.silent_ms = self.loud_ms = 0
                self.mix_g, self.track, self.pl_cur, self.next_file, self.pl_skip = 0.0, "", None, None, False
                self.delay_q.clear()
                self.meta = ""
                self.late, self.late_hist = 0, []
                self.started = time.time()
                self.outputs = [make_output(c, self) for c in self.prof.get("outputs", [])]
                self.prewarm()
                self.air = True
                self._cap_kick()
                for o in self.outputs:
                    if o.cfg.get("enabled", True):
                        o.start()
                p = self.fb_params()
                if p["enabled"] and p["files"]:
                    self.log(f"Bascule automatique activée : seuil {p['thr']:g} dB, délai {p['delay'] / 1000:g} s, "
                             f"{len(p['files'])} titre(s) dans la playlist de secours.")
                elif p["enabled"]:
                    self.log("Playlist de secours activée mais vide : ajoute des titres pour que la relève puisse se faire.")
                else:
                    self.log("Bascule automatique désactivée : en cas de silence, rien ne prendra le relais.")
            else:
                if not self.air:
                    return
                self.air = False
                outs, self.outputs = self.outputs, []
                for o in outs:
                    o.stop()
                self.backup = self.manual = self.mute = self.tone = self.pl_active = self.pl_pause = self.pl_stop = False
                self.silent_ms = self.loud_ms = 0
                self.track, self.pl_cur = "", None
                if self.pl_proc:
                    stop_proc(self.pl_proc)
                self.delay_q.clear()
                self._cap_kick()

    def set_prof(self, prof):
        """Nouveau profil complet (mise à l'antenne, changement de profil hors antenne)."""
        counts = self.prof.get("fallback", {}).get("counts")
        self.prof = prof
        if counts and isinstance(prof.get("fallback"), dict):
            prof["fallback"].setdefault("counts", {}).update({k: max(v, prof["fallback"]["counts"].get(k, 0)) for k, v in counts.items()})
        self.meta_manual = prof.get("meta", {}).get("text", "")
        self.delay_blocks = self.to_blocks(prof.get("delay", "0"))
        self.set_gain(prof.get("gain", "0"))
        self.fb_ver += 1
        self.set_source((prof.get("source") or {}).get("device", ""))
        self.cmon.set_device(prof.get("carts", {}).get("device", ""))

    def set_monitor(self, on):
        """Contrôle d'entrée : ouvre (ou ferme) la capture sans rien diffuser."""
        self.monitor = bool(on)
        self._cap_kick()

    def set_listen(self, on):
        """Écoute de l'antenne au casque (carte son du cartoucheur)."""
        self.listen = bool(on)

    def set_source(self, dev):
        dev = dev or ""
        if dev != self.src_dev:
            self.src_dev = dev
            self.prof.setdefault("source", {})["device"] = dev
            self._cap_kick()

    def capture_wanted(self):
        return self.running and (self.air or self.monitor) and not self.ev.is_set()

    def _cap_kick(self):
        """Relance (ou ferme) la capture : nouvelle entrée, début / fin d'antenne, contrôle d'entrée."""
        self.cap_gen += 1
        self.cap_wake.set()
        self._cap_kill()

    def _cap_kill(self):
        p, st = self.cap_proc, self.cap_stream
        if st is not None:
            try:
                st.stop_stream()
            except Exception:
                pass
        if p is not None:
            try:
                if p.stdin:
                    p.stdin.close()
            except Exception:
                pass
            stop_proc(p)

    # --- réglages du secours : relus à chaud (toute modification compte tout de suite, même pendant l'antenne)
    def fb_params(self):
        if self._fbp is not None and self._fbp_ver == self.fb_ver:
            return self._fbp
        fb = self.prof.get("fallback", {})

        def num(k, d, lo, hi):
            try:
                return max(lo, min(hi, float(str(fb.get(k, d)).replace(",", ".").strip() or d)))
            except (TypeError, ValueError):
                return d
        off = set(fb.get("off") or [])
        files = [f for f in (fb.get("playlist") or []) if f not in off]
        p = {"enabled": bool(fb.get("enabled")), "thr": num("threshold", -50.0, -90.0, -1.0),
             "delay": num("silence_s", 10.0, 1.0, 3600.0) * 1000, "rec": num("recover_s", 2.0, 0.2, 600.0) * 1000,
             "fi": num("fade_in", 0.5, 0.05, 30.0), "fo": num("fade_out", 1.2, 0.05, 30.0),
             "shuffle": bool(fb.get("shuffle")), "files": files}
        self._fbp, self._fbp_ver = p, self.fb_ver
        return p

    def output(self, oid):
        return next((o for o in self.outputs if o.cfg["id"] == oid), None)

    # --- pannes : UN message quand une panne commence, UN quand elle se termine, pour chaque panne de la session.
    # (Avant : un délai anti-répétition de 2 min par type d'alerte faisait sauter la 2e panne si elle suivait de près la 1re,
    # et une sortie qui se reconnectait par intermittence envoyait « en erreur » sans jamais « rétablie », ou l'inverse.)
    OUT_OK_S = 15.0                           # une sortie est « rétablie » après 15 s en ligne sans interruption

    def incident(self, key, on, text):
        """Ouvre (on=True) ou ferme une panne ; n'envoie que les changements d'état."""
        if on and key not in self.inc:
            self.inc[key] = time.time()
            self.alert(text, key)
        elif not on and key in self.inc:
            dur = time.time() - self.inc.pop(key)
            self.alert(f"{text} (après {fmt_dur(dur)})", key + "-ok")

    def watch_incidents(self, p, air, cap):
        if not air:
            self.inc.clear()                      # fin d'antenne : ce n'est pas une panne, rien à « rétablir »
            return
        delay = p["delay"]
        # 1) pas d'audio en entrée depuis le délai de la playlist de secours (même délai, même seuil)
        if cap and not self.mute and self.silent_ms >= delay and "silence" not in self.inc:
            why = f" ({self.cap_err})" if getattr(self, "cap_state", "") == "error" and self.cap_err else ""
            if self.backup:
                tail = "la playlist de secours a pris le relais."
            elif p["enabled"] and not p["files"]:
                tail = "la playlist de secours est vide : rien ne prend le relais !"
            elif not p["enabled"]:
                tail = "la playlist de secours est désactivée : rien ne prend le relais !"
            else:
                tail = "rien ne prend encore le relais."
            self.incident("silence", True, f"Pas de son en entrée depuis {delay / 1000:g} s{why} : {tail}")
        elif "silence" in self.inc and (self.loud_ms >= p["rec"] or not cap or self.mute):
            self.incident("silence", False, "Le son est revenu en entrée")
        # 2) playlist de secours à l'antenne, mais sans son (fichiers silencieux, illisibles, clé USB débranchée…)
        if self.pl_silent_ms >= delay:
            self.incident("fallback-silent", True, f"La playlist de secours est à l'antenne mais sans son depuis {delay / 1000:g} s "
                          "(fichier silencieux ou illisible, dossier débranché ?) : silence à l'antenne !")
        elif "fallback-silent" in self.inc and (self.pl_silent_ms == 0):
            self.incident("fallback-silent", False, "La playlist de secours a retrouvé du son" if self.backup
                          else "Fin du silence de la playlist de secours (retour au direct)")
        # 3) sorties : en erreur / rétablies (une fois par panne, et « rétablie » après 15 s stables en ligne)
        now = time.time()
        ids = set()
        for o in list(self.outputs):
            if not o.cfg.get("enabled", True):
                continue
            k = "out-" + o.cfg["id"]
            ids.add(k)
            if o.state == "error":
                o._ok_since = None
                self.incident(k, True, f"Sortie « {o.name} » en erreur : {o.detail or '?'}")
            elif o.state == "live":
                o._ok_since = getattr(o, "_ok_since", None) or now
                if k in self.inc and now - o._ok_since >= self.OUT_OK_S:
                    self.incident(k, False, f"Sortie « {o.name} » rétablie")
            else:
                o._ok_since = None
        for k in [k for k in self.inc if k.startswith("out-") and k not in ids]:
            self.inc.pop(k, None)                 # sortie retirée ou désactivée

    # --- traitement du son : chaque banque utilisée traite chaque bloc UNE fois ; chaque flux reçoit le son de sa banque
    # ou le son brut. Changer un réglage, une banque ou passer en bypass ne touche jamais aux encodeurs.
    def apply_fx(self):
        """Réglages des banques / bypass modifiés (FX) : appliqués aux processeurs en marche, au bloc suivant."""
        banks = FX.get("banks") or {}
        for b, pr in list(self.procs.items()):
            try:
                pr.update(banks.get(b) or proc_params())
                pr.set_bypass(bool(FX.get("bypass")))
            except Exception as ex:
                self.log(f"Processeur d'antenne (banque {b}) : réglage refusé ({ex})")

    def set_processor(self, params=None, bypass=None, bank=None):
        """(compatibilité) réglages d'une banque (A par défaut) et/ou bypass."""
        if params is not None:
            FX.setdefault("banks", {})[bank or FX.get("edit") or "A"] = params
        if bypass is not None:
            FX["bypass"] = bool(bypass)
        self.apply_fx()

    def _proc_make(self, b):
        """Crée le processeur d'une banque dans un autre fil (le calcul des filtres prend quelques dizaines de ms : pas de
        trou dans l'antenne). En attendant, ce flux reçoit le son de la banque principale, ou le son brut."""
        if b in self.proc_making or not self.proc_ok:
            return
        self.proc_making.add(b)

        def work():
            try:
                pr = AirProcessor((FX.get("banks") or {}).get(b) or proc_params(), bool(FX.get("bypass")))
                self.procs[b] = pr
            except Exception as ex:
                self.proc_ok = False
                self.log(f"Processeur d'antenne indisponible ({ex}) : le son part sans traitement.")
            finally:
                self.proc_making.discard(b)
        threading.Thread(target=work, daemon=True).start()

    def banks_needed(self, air):
        """Banques à faire tourner : celles des flux actifs (à l'antenne) et celle affichée dans l'onglet."""
        need = []
        if air:
            for o in self.outputs:
                b = out_bank(o.cfg)
                if b != RAW and o.cfg.get("enabled", True) and b not in need:
                    need.append(b)
        main = need[0] if need else None
        ed = FX.get("edit") if FX.get("edit") in BANKS else "A"
        if ed not in need:
            need.append(ed)
        return need, main or ed

    def distribute(self, outs, raw):
        """Bloc de 20 ms vers les sorties : le son de leur banque, ou le son brut."""
        for o in self.outputs:
            b = out_bank(o.cfg)
            o.push(raw if b == RAW else outs.get(b, outs.get(self.main_bank, raw)))

    def set_out_fx(self, modes):
        """Banque (ou son brut) choisie flux par flux : prise en compte au bloc suivant, sans redémarrer l'encodeur."""
        for o in list(self.outputs):
            m = modes.get(o.cfg.get("id"))
            if m is not None:
                o.cfg["fx"] = m if (m in BANKS or m == RAW) else out_bank({"fxmode": m})

    def remove_output(self, oid):
        """Retire une sortie de l'antenne en cours (elle s'arrête en arrière-plan)."""
        o = self.output(oid)
        if o:
            self.outputs = [x for x in self.outputs if x is not o]
            threading.Thread(target=o.stop, daemon=True).start()

    def prof_update(self, section, **kw):
        """Réglage modifié à chaud (volume du cartoucheur, secours, titre…) : pris en compte immédiatement."""
        _merge(self.prof.setdefault(section, {}), kw)
        if section == "fallback":
            self.fb_ver += 1
        elif section == "source" and "device" in kw:
            self.set_source(kw["device"])
        elif section == "carts" and "device" in kw:
            self.cmon.set_device(kw["device"] or "")

    def swap_output(self, cfg):
        """Ajoute ou remplace une sortie en cours d'antenne (nouveau plateau, adresse modifiée)."""
        if not self.air:
            return
        old = self.output(cfg["id"])
        new = make_output(cfg, self)
        self.outputs = [o for o in self.outputs if o is not old] + [new]
        if old:
            old.stop()
        if self.running and self.air and cfg.get("enabled", True):
            new.start()

    # --- commandes à chaud
    @staticmethod
    def to_blocks(sec):
        try:
            return max(0, min(2000, int(float(sec) * 50)))
        except ValueError:
            return 0

    def set_gain(self, db):
        try:
            self.gain = 10 ** (max(-24.0, min(24.0, float(db))) / 20)
        except (TypeError, ValueError):
            self.gain = 1.0

    def set_delay(self, sec):
        self.delay_blocks = self.to_blocks(sec)

    def dump_delay(self):
        """Vide le retard de sécurité : le son retenu n'est jamais diffusé."""
        self.delay_q.clear()
        self.log("DUMP : audio retenu supprimé, le retard se reconstitue en silence.")

    def play_now(self, path):
        """Joue tout de suite ce morceau / cette émission de la playlist de secours."""
        if not self.air:
            return
        self.next_file, self.pl_skip, self.pl_active, self.manual = path, True, True, True
        self.log("Lecture choisie : " + os.path.basename(path))

    def set_manual(self, on):
        if not self.air:
            return
        self.manual = bool(on)
        if not on:
            self.log("Retour manuel au direct demandé.")

    # --- métadonnées (titre en cours)
    def desired_meta(self):
        if self.backup and self.prof["meta"].get("follow") and self.track:
            return self.track
        return self.meta_manual

    def meta_loop(self):
        while not self.ev.is_set():
            try:
                text = self.desired_meta() if self.air else None
            except Exception:
                text = None
            if text is not None and text != self.meta:
                self.meta = text
                self.push_meta()
            self.ev.wait(1)

    def push_meta(self):
        for o in self.outputs:
            threading.Thread(target=o.send_meta, args=(self.meta,), daemon=True).start()

    def history(self, kind, name, path):
        """Ajoute une ligne à l'historique des diffusions (CSV lisible dans Excel)."""
        try:
            p = hist_path()
            new = not os.path.exists(p)
            with open(p, "a", encoding="utf-8-sig", newline="") as f:
                if new:
                    f.write("Date;Heure;Type;Titre;Fichier\n")
                clean = lambda x: str(x).replace(";", ",").replace("\n", " ")
                f.write(";".join((time.strftime("%d/%m/%Y"), time.strftime("%H:%M:%S"), kind, clean(name), clean(path))) + "\n")
        except OSError:
            pass

    def counts(self):
        return self.prof["fallback"].setdefault("counts", {})

    def least_played(self, files, rnd=False):
        """Parmi les fichiers, un des moins lus (à égalité : le premier de la liste, ou au hasard)."""
        c = self.counts()
        low = min(c.get(f, 0) for f in files)
        cand = [f for f in files if c.get(f, 0) == low]
        return random.choice(cand) if rnd else cand[0]

    def count_play(self, f, title=None):
        c = self.counts()
        c[f] = c.get(f, 0) + 1
        self.counts_ver += 1
        self.history("Secours", title or os.path.splitext(os.path.basename(f))[0], f)

    JINGLE_WORDS = ("jingle", "virgule", "habillage", "pub", "annonce", "promo", "id station", "liner")

    def avoid_repeat(self, files, fb):
        """Pas deux fois d'affilée le même titre, ni deux jingles du même dossier à la suite (dossier « Jingles »,
        « Virgules », « Habillage »…). S'il n'y a pas d'autre choix, la liste reste telle quelle."""
        prev = getattr(self, "pl_prev", None)
        if not prev or len(files) < 2:
            return files
        fo = fb.get("folder_of") or {}
        fold = fo.get(prev, "")
        jing = self.is_jingle(prev, fb)
        out = [f for f in files if f != prev and not (jing and (fo.get(f, "") == fold or self.is_jingle(f, fb)))]
        return out or [f for f in files if f != prev] or files

    def is_jingle(self, f, fb):
        """Fichier de la liste des jingles du secours, ou rangé dans un dossier de jingles de la playlist."""
        if not f:
            return False
        if f in (fb.get("jingle") or {}).get("files", []):
            return True
        fold = (fb.get("folder_of") or {}).get(f, "").lower()
        return bool(fold) and any(w in fold for w in self.JINGLE_WORDS)

    def jingle_loop(self):
        """Pendant le secours, signale qu'un jingle est dû à intervalle régulier. Il ne coupe jamais la musique : la playlist
        le place ENTRE deux morceaux (juste après le titre en cours), tant pis s'il passe un peu après l'heure prévue."""
        since = None
        while not self.ev.wait(1):
            j = self.prof["fallback"].get("jingle", {})
            files = [f for f in j.get("files", []) if os.path.exists(f)] if (self.air and self.backup and j.get("enabled")) else []
            if not (j.get("enabled") and files and self.backup and self.air):
                since, self.jingle_due = None, False
                continue
            now = time.time()
            since = since or now
            if getattr(self, "jingle_at", 0.0) > since:        # un jingle vient de passer : le compte repart de là
                since = self.jingle_at
            try:
                every = max(0.01, float(j.get("every", 15))) * 60
            except (TypeError, ValueError):
                every = 900.0
            if now - since >= every:
                self.jingle_due = True

    def next_jingle(self, fb):
        """Le jingle à placer entre deux morceaux (le moins lu ; jamais le même deux fois d'affilée)."""
        j = fb.get("jingle", {})
        files = [f for f in j.get("files", []) if os.path.isfile(f)]
        if not (j.get("enabled") and files):
            return None
        last = getattr(self, "last_jingle", None)
        cand = [f for f in files if f != last] or files
        return self.least_played(cand, True)

    # --- cartoucheur
    def get_pcm(self, path, trim=False, maxi=False):
        """Décode un fichier en PCM (cache ; coupe des blancs / maximisation selon les options)."""
        trim, maxi = bool(trim), bool(maxi)
        try:
            key = (path, os.path.getmtime(path), trim, maxi)
        except OSError:
            return None
        with self.pcm_lk:
            hit = self.pcm_cache.get(key)
        if hit is not None:
            return hit
        try:
            pcm = subprocess.run(
                ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", path,
                 "-vn", "-t", "300", "-ar", str(SR), "-ac", "2", "-f", "s16le", "pipe:1"],
                capture_output=True, stdin=subprocess.DEVNULL, timeout=90,
                creationflags=0x08000000 if SYS == "Windows" else 0).stdout
        except Exception:
            return None
        pcm = pcm[:len(pcm) // 4 * 4]
        if not pcm:
            return None
        pcm = pcm_process(pcm, trim, maxi) or pcm
        with self.pcm_lk:   # (sans verrou : « dictionary changed size during iteration » et la tuile ne partait pas)
            for k in [k for k in self.pcm_cache if k[0] == path]:
                del self.pcm_cache[k]
            if sum(len(v) for v in self.pcm_cache.values()) + len(pcm) > 400e6:
                self.pcm_cache.clear()  # garde la mémoire raisonnable
            self.pcm_cache[key] = pcm
        return pcm

    def preload_carts(self):
        """Prépare les cartouches en arrière-plan pour qu'elles partent instantanément."""
        for page in self.prof["carts"]["pages"]:
            for c in page:
                if self.ev.is_set():
                    return
                if c.get("file"):
                    self.get_pcm(c["file"], c.get("trim"), c.get("maximize"))

    def play_cart(self, cid, cart, pre=False, at=None):
        """at : position de départ en secondes dans le fichier (tête de lecture placée à la main), sinon le point d'entrée."""
        if cid in self.loading:
            return
        self.loading.add(cid)

        def work():
            try:
                pcm = self.get_pcm(cart["file"], cart.get("trim"), cart.get("maximize"))
                if not pcm:
                    return self.log(f"Cartouche illisible : {os.path.basename(cart['file'])}")
                try:
                    vol = max(0, min(150, int(cart.get("vol", 100)))) / 100
                except (TypeError, ValueError):
                    vol = 1.0
                def fd(k):
                    try:
                        v = cart.get(k)
                        return max(0.0, min(10.0, float(cart.get("fade", 0) if v is None else v) or 0))
                    except (TypeError, ValueError):
                        return 0.0
                fi, fo = fd("fade_in"), fd("fade_out")
                grp = int(cart.get("group", 0) or 0)
                with self.lock:
                    if cart.get("solo"):  # tuile « solo » : coupe tout le reste en fondu
                        for o in self.voices:
                            if o["id"] != cid and not o["stopping"]:
                                o["stopping"] = True
                                o["sfade"] = min(self.fade_click(), 0.6)
                    if grp:  # groupe exclusif : lancer une touche arrête les autres du groupe
                        for o in self.voices:
                            if o.get("group") == grp and o["id"] != cid and not o["stopping"]:
                                o["stopping"] = True
                                o["sfade"] = self.fade_click()
                    try:
                        st0 = int(max(0.0, float(cart.get("start", 0) or 0)) * 176400) // 4 * 4
                    except (TypeError, ValueError):
                        st0 = 0
                    if st0 >= len(pcm) - 3528:
                        st0 = 0
                    try:
                        en = int(max(0.0, float(cart.get("end", 0) or 0)) * 176400) // 4 * 4
                    except (TypeError, ValueError):
                        en = 0
                    if en <= st0 + 3528 or en > len(pcm):
                        en = len(pcm)
                    p0 = st0
                    if at is not None:
                        try:
                            p0 = int(max(0.0, float(at)) * 176400) // 4 * 4
                        except (TypeError, ValueError):
                            p0 = st0
                        if not st0 <= p0 < en - 3528:
                            p0 = st0
                    try:
                        own = cart.get("fade_click")
                        own = None if own in (None, "") else max(0.0, min(10.0, float(own)))
                    except (TypeError, ValueError):
                        own = None
                    self.voices.append({"id": cid, "pcm": pcm, "pos": p0, "paused": False, "vol": vol, "g": 0.0, "st0": st0, "end": en,
                                        "fi": fi, "fo": fo, "group": grp, "own_stop": own, "pk": 0.0,
                                        "loop": bool(cart.get("loop")), "stopping": False, "pre": pre,
                                        "mode": cart.get("mode", "Par-dessus"),
                                        "name": cart.get("name") or os.path.basename(cart["file"])})
                self.log(f"Cartouche : {self.voices[-1]['name']}")
                if not pre:
                    self.history("Cartouche", self.voices[-1]["name"], cart["file"])
            finally:
                self.loading.discard(cid)
        threading.Thread(target=work, daemon=True).start()

    def slow_now(self):
        """Vrai seulement si l'audio a eu au moins 3 trous de plus de 80 ms ces 30 dernières secondes."""
        now = time.time()
        return sum(1 for x in list(self.late_hist) if now - x < 30) >= 3

    def fade_click(self):
        try:
            return max(0.0, min(10.0, float(self.prof["carts"].get("fade_click", 2.5))))
        except (TypeError, ValueError, KeyError):
            return 2.5

    def stop_cart(self, cid=None, fade=None):
        """Arrête une cartouche (ou toutes) avec un fondu : celui du réglage « Fondu au clic » (2,5 s par défaut)."""
        base = self.fade_click()
        with self.lock:
            for v in self.voices:
                if (cid is None or v["id"] == cid) and not v["stopping"]:
                    v["stopping"] = True
                    v["sfade"] = fade if fade is not None else (v["own_stop"] if v.get("own_stop") is not None else base)

    def cart_master(self):
        try:
            return max(0.0, min(1.5, float(self.prof["carts"].get("master", 100)) / 100))
        except (TypeError, ValueError, KeyError):
            return 1.0

    def seek_cart(self, cid, sec):
        """Déplace la tête de lecture d'une cartouche en cours (secondes dans le fichier), avec un micro-fondu anti-clic."""
        with self.lock:
            for v in self.voices:
                if v["id"] == cid and not v["stopping"]:
                    lim = v.get("end") or len(v["pcm"])
                    # demande de saut appliquée par le mélangeur lui-même, au bloc suivant : avant, le mélangeur pouvait
                    # réécrire l'ancienne position juste après le saut (la lecture ne suivait pas la tête déplacée)
                    v["seek_to"] = max(v.get("st0", 0), min(lim - 4, int(max(0.0, sec) * 176400) // 4 * 4))
                    return True
        return False

    def pause_cart(self, cid=None, on=None):
        """Met en pause / reprend une cartouche (ou toutes). Renvoie le nouvel état de la première trouvée."""
        res = None
        with self.lock:
            for v in self.voices:
                if (cid is None or v["id"] == cid) and not v["stopping"]:
                    nv = (not v.get("paused")) if on is None else bool(on)
                    if res is None:
                        res = nv
                    if cid is None and on is None:
                        nv = res
                    if v.get("paused") and not nv:
                        v["fi"] = 0.03
                    v["paused"] = nv
        return res

    def set_cart_live(self, cid, **kw):
        """Volume / boucle modifiés pendant la lecture."""
        with self.lock:
            for v in self.voices:
                if v["id"] == cid:
                    if "vol" in kw:
                        v["vol"] = max(0.0, min(1.5, kw["vol"]))
                    if "loop" in kw:
                        v["loop"] = bool(kw["loop"])
                    if "fo" in kw:
                        v["fo"] = kw["fo"]

    def cart_playing(self, cid):
        return any(v["id"] == cid and not v["stopping"] for v in list(self.voices))

    def cart_status(self):
        """{id: (position_s, durée_s, boucle, écoute, en_fondu)} des cartouches en cours, + ids en chargement."""
        st = {v["id"]: (max(0.0, (v["pos"] - v.get("st0", 0)) / 176400), (v.get("end", len(v["pcm"])) - v.get("st0", 0)) / 176400,
                        v["loop"], bool(v["pre"]), bool(v["stopping"]), v.get("pk", 0.0), bool(v.get("paused")),
                        v.get("st0", 0) / 176400)
              for v in list(self.voices)}
        return st, set(self.loading)

    # --- capture de l'entrée
    @staticmethod
    def drain(p, store):
        """Vide la sortie d'erreur d'un processus (sinon il peut se bloquer)."""
        try:
            for line in p.stderr:
                store.append(line.decode("utf-8", "replace").strip())
        except Exception as _ex:
            trace("drain", _ex)

    def pump(self, proc, store):
        """Lit la sortie d'erreur de ffmpeg (sans l'afficher ligne à ligne : une entrée en panne ne doit pas inonder le journal)."""
        buf = b""
        while True:
            try:
                chunk = proc.stderr.read(1024)
            except Exception:
                break
            if not chunk:
                break
            parts = re.split(rb"[\r\n]+", buf + chunk)
            buf = parts.pop()
            for p in parts:
                line = p.decode("utf-8", "replace").strip()
                if line:
                    store.append(line)

    def open_loopback(self, device):
        """Capture du son de l'ordinateur (WASAPI loopback, PyAudioWPatch) ;
        ffmpeg convertit le flux en PCM 44,1 kHz stéréo."""
        import pyaudiowpatch as pa
        pa_inst = pa.PyAudio()
        proc = None
        try:
            name = device[len("loopback:"):]
            info = next((d for d in pa_inst.get_loopback_device_info_generator()
                         if d["name"] == name), None) or pa_inst.get_default_wasapi_loopback()
            rate, ch = int(info["defaultSampleRate"]), int(info["maxInputChannels"])
            proc = popen(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "s16le",
                 "-ar", str(rate), "-ac", str(ch), "-i", "pipe:0", "-ar", "44100",
                 "-ac", "2", "-flush_packets", "1", "-f", "s16le", "pipe:1"],
                bufsize=0, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

            wl = threading.Lock()
            last = [time.perf_counter()]

            def cb(data, frames, t, status):
                last[0] = time.perf_counter()
                try:
                    with wl:
                        proc.stdin.write(data)
                except (OSError, ValueError):
                    return (None, pa.paAbort)
                return (None, pa.paContinue)

            def filler():
                # WASAPI loopback n'envoie AUCUN bloc quand rien ne joue : on injecte du silence
                # pour que l'entrée reste « vivante » (sinon plus de signal, ni de niveau, ni de bascule propre).
                blk = bytes(int(rate * 0.02) * ch * 2)
                nxt = time.perf_counter()
                while proc.poll() is None and not self.ev.is_set():
                    nxt += 0.02
                    d = nxt - time.perf_counter()
                    if d > 0:
                        time.sleep(d)
                    else:
                        nxt = time.perf_counter()
                    if time.perf_counter() - last[0] > 0.06:
                        try:
                            with wl:
                                proc.stdin.write(blk)
                        except (OSError, ValueError):
                            return
            threading.Thread(target=filler, daemon=True).start()

            stream = pa_inst.open(format=pa.paInt16, channels=ch, rate=rate, input=True,
                                  input_device_index=info["index"],
                                  frames_per_buffer=1024, stream_callback=cb)
            return proc, pa_inst, stream
        except Exception:
            if proc and proc.poll() is None:
                proc.terminate()
            pa_inst.terminate()
            raise

    def capture_loop(self):
        """Lit l'entrée audio (PCM) dans un tampon, seulement quand elle sert (antenne ou contrôle d'entrée).
        Changement d'entrée, début ou fin d'antenne : la capture est relancée aussitôt. En cas de panne, nouvel essai
        toutes les 2 s ; l'état (active / en panne + raison) est visible dans l'interface, le journal n'est pas inondé."""
        last_log = 0.0
        while not self.ev.is_set():
            if not self.capture_wanted():
                self.cap_state, self.cap_err = "off", ""
                with self.lock:
                    self.live_buf.clear()
                self.cap_wake.wait(0.25)
                self.cap_wake.clear()
                continue
            gen, device = self.cap_gen, self.src_dev
            stream = pa_inst = p = None
            err = deque(maxlen=8)
            got = 0
            t0 = time.time()
            self.cap_state = "starting"
            try:
                if not device:
                    raise RuntimeError("aucune entrée choisie")
                if device.startswith("loopback:"):
                    p, pa_inst, stream = self.open_loopback(device)
                    self.cap_stream = stream
                else:
                    p = popen(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error"] +
                              input_args(device) +
                              ["-ar", "44100", "-ac", "2", "-f", "s16le", "pipe:1"],
                              bufsize=0, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
                self.cap_proc = p
                threading.Thread(target=self.pump, args=(p, err), daemon=True).start()
                with self.lock:
                    self.live_buf.clear()
                carry = b""
                while gen == self.cap_gen and self.capture_wanted():
                    data = p.stdout.read(CH)
                    if not data:
                        break
                    data = carry + data
                    n = len(data) // 4 * 4
                    data, carry = data[:n], data[n:]
                    if not data:
                        continue
                    got += len(data)
                    if got > CH * 10 and self.cap_state != "ok":
                        if self.cap_state == "error" or last_log:
                            self.log("Entrée audio rétablie : " + dev_short_name(device))
                            last_log = 0.0
                        self.cap_state, self.cap_err, self.cap_t = "ok", "", time.time()
                    if self.gain != 1.0:
                        data = scale_pcm(data, self.gain)
                    lv = peak_db(data)  # niveau d'entrée mesuré dès l'arrivée du son
                    for ch in (0, 1):
                        self.in_peak[ch] = max(self.in_peak[ch], lv[ch])
                    with self.lock:
                        self.live_buf += data
                        trim(self.live_buf)
            except ImportError:
                err.append("module PyAudioWPatch manquant (onglet SOS > Installer)")
            except Exception as e:
                err.append(str(e) or e.__class__.__name__)
            finally:
                self.cap_stream = None
                try:
                    if stream:
                        stream.stop_stream()
                        stream.close()
                    if pa_inst:
                        pa_inst.terminate()
                except Exception:
                    pass
                if p:
                    stop_proc(p)
                self.cap_proc = None
            with self.lock:
                self.live_buf.clear()
            if self.ev.is_set():
                break
            if gen != self.cap_gen or not self.capture_wanted():
                continue                                   # relance voulue (nouvelle entrée, fin d'antenne…) : pas une panne
            time.sleep(0.15)                               # laisse ffmpeg écrire sa dernière ligne d'erreur
            why = next((re.sub(r"^(\[[^\]]*\]\s*)+", "", l) for l in reversed(list(err)) if l and "Error opening input file" not in l), "") or (
                "l'entrée s'est arrêtée" if got else "entrée introuvable ou occupée par un autre logiciel")
            self.cap_state, self.cap_err = "error", why[:160]
            now = time.time()
            if now - last_log > 60:
                last_log = now
                self.log(f"Entrée audio « {dev_short_name(device)} » indisponible : {why[:160]} · nouvel essai automatique toutes les 2 s.")
            if time.time() - t0 < 2:
                self.cap_wake.wait(2)
                self.cap_wake.clear()

    # --- playlist de secours
    def playlist_loop(self):
        """Décode la playlist de secours plus vite que le temps réel (5 s d'avance). Les réglages et la liste des titres
        sont relus à chaque titre : un ajout ou une modification pendant l'antenne compte tout de suite."""
        missing = set()
        while not self.ev.is_set():
            fb = self.prof.get("fallback", {})
            full = list(fb.get("playlist") or [])
            off = set(fb.get("off") or [])
            files = [x for x in full if x not in off and x not in missing]
            if not (self.air and self.pl_active and files):
                if not self.pl_active:
                    missing.clear()                       # un fichier revenu (clé USB rebranchée) sera réessayé
                self.ev.wait(0.1)
                continue
            jf = (self.next_jingle(fb) if (getattr(self, "jingle_due", False) and not self.next_file
                                           and not self.is_jingle(getattr(self, "pl_prev", None), fb)) else None)
            if jf:                                          # jingle dû : il passe entre le morceau qui finit et le suivant
                f = jf
                self.jingle_due, self.jingle_at, self.last_jingle = False, time.time(), jf
            elif self.next_file and self.next_file in full:  # morceau / émission choisi(e)
                f, self.next_file = self.next_file, None
                with self.lock:  # le saut demandé est pris en compte : on repart d'un tampon vide
                    if self.pl_skip:
                        self.pl_buf.clear()
                        self.pl_marks.clear()
                        self.pl_in = self.pl_out = 0
                        self.pl_skip = False
            else:
                f = self.least_played(self.avoid_repeat(files, fb), fb.get("shuffle"))  # les moins lus d'abord
            self.pl_prev = f
            if not os.path.isfile(f):
                missing.add(f)
                self.log(f"Playlist de secours : fichier introuvable, ignoré : {f}")
                continue
            title, dur = track_info(f)
            self.count_play(f, title)
            got, p, err = False, None, deque(maxlen=10)
            try:
                p = self.pl_proc = popen(
                    ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error",
                     "-i", f, "-map", "0:a:0?", "-vn", "-ar", "44100", "-ac", "2",
                     "-f", "s16le", "pipe:1"],
                    bufsize=0, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                threading.Thread(target=self.drain, args=(p, err), daemon=True).start()
                with self.lock:
                    self.pl_marks.append((self.pl_in, title, full.index(f) if f in full else -1, f, dur))
                while self.air and self.pl_active and not self.ev.is_set() and not self.pl_skip:
                    if len(self.pl_buf) > 250 * CH:
                        self.ev.wait(0.02)
                        continue
                    data = p.stdout.read(8 * CH)
                    if not data:
                        break
                    got = True
                    with self.lock:
                        self.pl_buf += data
                        self.pl_in += len(data)
                stop_proc(p)
            except OSError as e:
                err.append(str(e))
            with self.lock:
                cut = len(self.pl_buf) % 4
                if cut:
                    del self.pl_buf[len(self.pl_buf) - cut:]
                    self.pl_in -= cut
                skipped, self.pl_skip = self.pl_skip, False
                if skipped or not self.pl_active or not self.air:
                    self.pl_buf.clear()
                    self.pl_marks.clear()
                    self.pl_in = self.pl_out = 0
                if not self.pl_active or not self.air:
                    self.track, self.pl_cur = "", None
            if not got and not skipped:
                if self.pl_active and self.air and not self.ev.is_set():
                    missing.add(f)
                    self.log(f"Lecture impossible : {os.path.basename(f)} "
                             + " ".join(list(err)[-2:]) + " · titre suivant.")
                self.ev.wait(0.3)

    # --- horloge du moteur
    def feeder_loop(self):
        """Toutes les 20 ms : prend l'entrée, détecte le silence, choisit direct ou secours avec un fondu enchaîné,
        ajoute les cartouches, applique mute / retard, puis distribue le bloc aux flux (pendant l'antenne) et au casque.
        Les réglages du secours (seuil, délais, fondus, marche/arrêt) sont relus à chaque bloc."""
        zero = bytes(CH)
        starved = live_ok = False
        g, phase = 0.0, 0.0  # g : 0 = direct, 1 = playlist de secours
        loud_run = quiet_run = 0
        by_hand = False                         # la playlist en cours a été lancée à la main
        was_air = False
        empty_warned = False
        nxt = time.perf_counter()
        tick = 0
        while not self.ev.is_set():
            nxt += 0.02
            wait = nxt - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            elif wait < -1:
                nxt = time.perf_counter()
            if wait < -0.02:
                self.late += 1
                self.late_t = time.time()
                if wait < -0.08:                  # un vrai trou (80 ms et plus), pas une simple gigue
                    self.late_hist = [x for x in self.late_hist if self.late_t - x < 30] + [self.late_t]
            t0 = time.perf_counter()
            p = self.fb_params()
            air = self.air
            if air != was_air:                      # début / fin d'antenne : on repart du direct, compteurs à zéro
                was_air = air
                g, starved, loud_run, quiet_run, empty_warned, by_hand = 0.0, False, 0, 0, False, False
            self.rec_ms = p["rec"]
            live, pl = zero, zero
            cap = self.capture_wanted()
            with self.lock:
                if not live_ok and len(self.live_buf) >= 4 * CH:
                    live_ok = True  # réserve de 80 ms contre les irrégularités de capture
                if live_ok:
                    if len(self.live_buf) >= CH:
                        live = bytes(self.live_buf[:CH])
                        del self.live_buf[:CH]
                    else:
                        live_ok = False
                if air and (self.backup or g > 0) and not self.pl_pause:
                    if len(self.pl_buf) >= CH * (10 if starved else 1):
                        pl = bytes(self.pl_buf[:CH])
                        del self.pl_buf[:CH]
                        self.pl_out += CH
                        starved = False
                        while self.pl_marks and self.pl_marks[0][0] <= self.pl_out:
                            m = self.pl_marks.popleft()
                            self.track = m[1]
                            self.pl_cur = {"i": m[2], "path": m[3], "start": m[0], "dur": m[4]}
                    else:
                        starved = True  # attend 200 ms d'avance avant de reprendre
            if self.tone and air:
                live, phase = tone_block(phase)
            if air and self.backup and g >= 0.99 and not self.pl_pause:     # playlist de secours seule à l'antenne
                if max(peak_db(pl)) > p["thr"]:
                    self.pl_silent_ms = 0
                else:
                    self.pl_silent_ms += 20
            else:
                self.pl_silent_ms = 0
            # --- détection du signal (seulement quand l'entrée est ouverte)
            if cap:
                lv = peak_db(live)
                if max(lv) > p["thr"]:
                    loud_run += 1
                    quiet_run = 0
                    if loud_run >= 3:               # un vrai retour du son (60 ms), pas un simple clic
                        self.silent_ms = 0
                    self.loud_ms += 20
                else:
                    quiet_run += 1
                    loud_run = 0
                    self.silent_ms += 20
                    if quiet_run >= 25:             # 0,5 s de silence : le retour au direct repart de zéro
                        self.loud_ms = 0
            else:
                self.silent_ms = self.loud_ms = 0
            # --- bascule direct / secours (antenne seulement)
            if air:
                has = bool(p["files"])
                if self.pl_stop:                    # « Stop » : retour au direct, et pas de relève automatique tant que
                    if self.backup or self.manual:  # le son n'est pas revenu (ou qu'on n'a pas relancé la playlist)
                        self.backup = self.manual = by_hand = False
                        self.pl_pause = False
                        self.log("Playlist de secours arrêtée : retour au direct.")
                    if self.loud_ms >= p["rec"]:
                        self.pl_stop = False
                elif self.manual:
                    by_hand = True
                if self.pl_stop:
                    pass
                elif self.manual and not self.backup:
                    if has:
                        self.backup = True
                        self.log("Bascule manuelle sur la playlist de secours.")
                    else:
                        self.manual = False
                        self.log("Playlist de secours vide : rien à lancer.")
                elif self.backup and not self.manual and by_hand:   # fin du lancement manuel
                    by_hand = False
                    if p["enabled"] and has and self.silent_ms >= p["delay"]:
                        self.log("Toujours pas de son en entrée : la playlist de secours continue (retour automatique dès que le son revient).")
                    else:
                        self.backup = False
                elif (p["enabled"] and has and not self.manual and not self.backup and self.silent_ms >= p["delay"]):
                    self.backup = True
                    self.log(f"Aucun signal depuis {p['delay'] / 1000:g} s : la playlist de secours prend le relais.")
                elif self.backup and not self.manual and (self.loud_ms >= p["rec"] or not p["enabled"] or not has):
                    self.backup = False
                    if not has:
                        self.log("Playlist de secours vidée : retour au direct.")
                    elif not p["enabled"]:
                        self.log("Playlist de secours désactivée : retour au direct.")
                    else:
                        self.log("Signal retrouvé : retour au direct (fondu).")
                if p["enabled"] and not has and self.silent_ms >= p["delay"] and not empty_warned:
                    empty_warned = True
                    self.log("⚠ Silence à l'antenne, mais la playlist de secours est vide : rien ne peut prendre le relais.")
                elif self.silent_ms < p["delay"]:
                    empty_warned = False
                self.pl_active = has and (self.backup or self.manual or g > 0 or
                                          (p["enabled"] and self.silent_ms >= max(p["delay"] * 0.3, p["delay"] - 3000)))
            else:
                self.backup = self.manual = self.pl_active = False
            target = 1.0 if (air and self.backup) else 0.0
            g0 = g
            if g < target:
                g = min(target, g + 0.02 / p["fi"])
            elif g > target:
                g = max(target, g - 0.02 / p["fo"])
            self.mix_g = g
            if g0 == 0.0 and g == 0.0:
                prog = live if air else zero      # hors antenne : rien ne part, seules les cartouches jouent (casque)
            elif g0 == 1.0 and g == 1.0:
                prog = pl
            else:
                prog = mix_blocks(live, pl, g0, g)
            prog, pre = self.apply_carts(prog, zero)
            if self.mute and air:
                prog = zero
            dq = self.delay_q
            if air:
                dq.append(prog)
                n = self.delay_blocks
                while len(dq) > n + 1:
                    dq.popleft()
                out = dq.popleft() if len(dq) > n else zero
            else:
                out = prog
            raw = out
            outs = {}
            if self.proc_ok and (air or cap):           # processeur d'antenne (hors antenne : mesures sur l'entrée seulement)
                need, main = self.banks_needed(air)
                self.main_bank = main
                now_ = time.time()
                src = out if air else live
                for b in need:
                    pr = self.procs.get(b)
                    if pr is None:
                        self._proc_make(b)
                        continue
                    self.proc_used[b] = now_
                    try:
                        outs[b] = pr.process(src)
                    except Exception as ex:
                        self.procs.pop(b, None)
                        self.log(f"Processeur d'antenne (banque {b}) arrêté ({ex}) : son de la banque principale ou brut.")
                for b in [b for b in self.procs if now_ - self.proc_used.get(b, 0) > 10 and b not in need]:
                    self.procs.pop(b, None)             # banque plus utilisée depuis 10 s : libérée
                ed = FX.get("edit") if FX.get("edit") in BANKS else "A"
                self.pm = self.procs[ed].meter if ed in self.procs and ed in outs else {}
                self.pm_main = self.procs[main].meter if main in self.procs and main in outs else {}
                if air and main in outs:
                    out = outs[main]                    # (antenne écoutée, crêtes, voyant : la banque principale)
            elif self.pm or self.pm_main:
                self.pm, self.pm_main = {}, {}
            lv = peak_db(out)
            if max(lv) > -0.3:
                self.clip_t = time.time()
            for ch in (0, 1):
                self.peak[ch] = max(self.peak[ch], lv[ch])
            if air:
                self.distribute(outs, raw)
            if self.cmon.stream:                   # casque : antenne écoutée (si demandé) + pré-écoute des cartouches
                parts = []
                if self.listen and air:
                    parts.append(np.frombuffer(out, dtype="<i2").astype(np.float32) if np is not None else array("h", out))
                parts += pre
                if parts:
                    self.cmon.push(self.clip_mix(parts))
            self.proc_ms += ((time.perf_counter() - t0) * 1000 - self.proc_ms) * 0.05
            tick += 1
            if tick % 25 == 0:                       # toutes les 0,5 s : pannes à signaler
                try:
                    self.watch_incidents(p, air, cap)
                except Exception as ex:
                    self.log(f"Surveillance des pannes : {ex}")

    @staticmethod
    def clip_mix(parts):
        if np is not None:  # limiteur doux : plusieurs tuiles en même temps ne saturent plus
            s = np.sum(parts, axis=0)
            m = np.abs(s)
            if float(m.max()) > 24000.0:
                s = np.where(m > 24000.0, np.sign(s) * (24000.0 + 8767.0 * np.tanh((m - 24000.0) / 8767.0)), s)
            return np.clip(s, -32768, 32767).astype("<i2").tobytes()
        return array("h", (max(-32768, min(32767, int(sum(c)))) for c in zip(*parts))).tobytes()

    def apply_carts(self, prog, zero):
        """Mélange les cartouches en cours sur l'antenne (sauf sortie audio seule) et baisse le direct ;
        tout part aussi vers la carte son du cartoucheur si elle est choisie."""
        with self.lock:
            voices = list(self.voices)
        duck = 1.0
        air, dev = [], []
        listen = self.listen and self.air
        master = self.cart_master()
        for v in voices:
            sk = v.pop("seek_to", None)
            if sk is not None:                   # saut demandé (tête de lecture déplacée) : micro-fondu anti-clic
                v["pos"], v["g"], v["fi"] = sk, 0.0, 0.015
            if v.get("paused") and v["g"] <= 0.0:
                continue                         # en pause : la tête de lecture ne bouge plus
            pcm, pos, chunk = v["pcm"], v["pos"], b""
            lim = v.get("end") or len(pcm)
            while len(chunk) < CH and pos < lim:
                piece = pcm[pos:min(lim, pos + CH - len(chunk))]
                chunk += piece
                pos += len(piece)
                if pos >= lim and v["loop"] and not v["stopping"]:
                    pos = v.get("st0", 0)
            ended = len(chunk) < CH
            if ended:
                chunk += bytes(CH - len(chunk))
            v["pos"] = pos
            g0 = v["g"]
            fi, fo = v.get("fi", 0.0), v.get("fo", 0.0)
            g1 = (max(0.0, g0 - 0.02 / max(v.get("sfade", fo), 0.03)) if v["stopping"]
                  else max(0.0, g0 - 0.02 / 0.04) if v.get("paused")
                  else min(1.0, g0 + 0.02 / (fi if fi > 0 else 0.01)))
            if fo > 0 and not v["loop"]:  # fondu de sortie sur la fin du son
                g1 = min(g1, max(0.0, (lim - pos) / 176400 / fo))
            v["g"] = g1
            k0, k1 = g0 * v["vol"] * master, g1 * v["vol"] * master
            if np is not None:
                a = np.frombuffer(chunk, dtype="<i2").astype(np.float32)
                sc = a * (k0 + (k1 - k0) * np.arange(len(a), dtype=np.float32) / len(a))
            else:
                a = array("h")
                a.frombytes(chunk)
                d = (k1 - k0) / len(a)
                sc = [x * (k0 + d * i) for i, x in enumerate(a)]
            try:
                pk = (float(np.abs(sc).max()) if np is not None else max((abs(x) for x in sc), default=0.0)) / 32768.0
            except Exception:
                pk = 0.0
            v["pk"] = max(pk, v.get("pk", 0.0) * 0.8)
            if not (listen and v["pre"] is False):
                dev.append(sc)                   # casque : toutes les tuiles, ou seulement la pré-écoute si on écoute l'antenne
            if not v["pre"]:
                air.append(sc)
                if v["mode"] == "Remplace":
                    t = 0.0
                elif v["mode"] == "Mixé":
                    t = 1.0
                else:
                    t = 1.0 - self.duck_amount()
                duck = min(duck, 1.0 - (1.0 - t) * max(g0, g1) if t < 1 else 1.0)
            if ended or (v["stopping"] and g1 == 0.0):
                with self.lock:
                    if v in self.voices:
                        self.voices.remove(v)
        g0 = self.duck_g
        step = 0.02 / (0.15 if duck < g0 else 0.6)
        g = max(duck, g0 - step) if duck < g0 else min(duck, g0 + step)
        self.duck_g = g
        if not air and g0 == 1.0 and g == 1.0:
            return prog, dev
        if not air:
            return gain_mix(prog, zero, g0, g), dev
        return gain_mix(prog, self.clip_mix(air), g0, g), dev

    def duck_amount(self):
        try:
            return max(0.0, min(1.0, float(self.prof["carts"].get("duck", 70)) / 100))
        except (TypeError, ValueError):
            return 0.7

# ------------------------------------------------------------------ sorties
class Output:
    """Une destination : chaque sortie a son propre encodeur et sa reconnexion."""

    def __init__(self, cfg, eng):
        self.cfg, self.eng = cfg, eng
        self.q = queue.Queue(maxsize=300)
        self.state, self.detail = "stopped", ""
        self.stop_ev = threading.Event()
        self.thread = None
        self.procs = []
        self.err = deque(maxlen=12)
        self.t_live = 0.0
        self.had_error = False
        self.meta_note = ""

    @property
    def name(self):
        return self.cfg.get("name") or self.cfg["type"]

    def describe(self):
        return ""

    def status_text(self):
        if self.state == "live":
            return "● En ligne depuis " + fmt_dur(time.time() - self.t_live)
        if self.state == "connecting":
            return "◌ Connexion en cours…"
        if self.state == "error":
            return "✕ Problème : " + (self.detail or "?")[:80]
        return "○ Arrêté"

    # --- cycle de vie
    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_ev = threading.Event()
        self.state, self.detail = "connecting", ""
        self.thread = threading.Thread(target=self.supervise, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_ev.set()
        self.state, self.detail = "stopped", ""
        threading.Thread(target=self.kill, daemon=True).start()

    def kill(self):
        """Ferme les encodeurs proprement (fin de flux), puis force si besoin."""
        procs, self.procs = list(self.procs), []
        for p in procs:
            try:
                if p.stdin:
                    p.stdin.close()
            except Exception:
                pass
        t0 = time.time()
        while time.time() - t0 < 1.5 and any(p.poll() is None for p in procs):
            time.sleep(0.05)
        for p in procs:
            stop_proc(p)

    def set_state(self, state, detail=""):
        old = self.state
        self.state, self.detail = state, detail
        if state == "live":
            self.t_live = time.time()
        if old == state:
            return
        if state == "error":
            self.had_error = True
            self.eng.log(f"[{self.name}] erreur : {detail}")      # (l'alerte est envoyée par Engine.watch_incidents)
        elif state == "live":
            self.eng.log(f"[{self.name}] en direct")
            self.had_error = False
            threading.Thread(target=self.send_meta, args=(self.eng.meta,), daemon=True).start()

    def supervise(self):
        stop = self.stop_ev
        fails = 0
        while not stop.is_set():
            self.set_state("connecting")
            self.err.clear()
            t_start = time.time()
            try:
                self.run_once()
            except Exception as e:
                self.err.append(redact(e))
            self.kill()
            if stop.is_set():
                break
            fails = 0 if self.t_live >= t_start else fails + 1
            self.set_state("error", self.last_error() or "arrêt inattendu")
            if not self.cfg.get("reconnect", True):
                break
            for _ in range(min(300, 50 + 50 * fails)):  # 5 s, puis +5 s par échec (30 s max)
                if stop.is_set():
                    break
                time.sleep(0.1)

    def last_error(self):
        for line in reversed(self.err):
            if line and not re.match(r"(size=|video:|audio:|\[out#|Exiting)", line):
                return line[:120]
        return ""

    # --- audio
    def push(self, blk):
        if not self.thread or not self.thread.is_alive():
            return
        try:
            self.q.put_nowait(blk)
        except queue.Full:
            try:
                self.q.get_nowait()
                self.q.put_nowait(blk)
            except (queue.Empty, queue.Full):
                pass

    def drain_q(self):
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    def filters(self):
        # son traité par le processeur d'antenne : pas de second traitement dans l'encodeur (il recompresserait)
        if getattr(self.eng, "proc_ok", False) and out_processed(self.cfg):
            return []
        f = PROCESSING.get(self.cfg.get("processing", "Aucun"), "")
        return ["-af", f] if f else []

    @staticmethod
    def pcm_in():
        return ["-hide_banner", "-nostdin", "-f", "s16le", "-ar", str(SR), "-ac", "2",
                "-i", "pipe:0"]

    def spawn(self, cmd, stdout=None, stdin=None, ffmpeg=True):
        p = popen(cmd, bufsize=0, stdin=subprocess.PIPE if stdin is None else stdin,
                  stdout=subprocess.DEVNULL if stdout is None else stdout,
                  stderr=subprocess.PIPE)
        self.procs.append(p)
        threading.Thread(target=self.read_err, args=(p, ffmpeg), daemon=True).start()
        if stdin is None:
            threading.Thread(target=self.feed, args=(p,), daemon=True).start()
        return p

    def read_err(self, p, ffmpeg):
        buf = b""
        while True:
            chunk = p.stderr.read(1024)
            if not chunk:
                break
            parts = re.split(rb"[\r\n]+", buf + chunk)
            buf = parts.pop()
            for raw in parts:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                if ffmpeg and "time=" in line:
                    if self.state == "connecting":
                        self.set_state("live")
                else:
                    self.err.append(redact(line))

    def feed(self, p):
        stop = self.stop_ev
        while not stop.is_set() and p.poll() is None:
            try:
                blk = self.q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                p.stdin.write(blk)
            except (OSError, ValueError):
                break
        try:
            p.stdin.close()
        except Exception:
            pass

    def wait_all(self, live_after=None):
        """Attend que la sortie s'arrête (processus terminé ou arrêt demandé)."""
        t0 = time.time()
        while not self.stop_ev.is_set():
            if any(p.poll() is not None for p in self.procs):
                break
            if live_after and self.state == "connecting" and time.time() - t0 > live_after:
                self.set_state("live")
            self.tick()
            time.sleep(0.2)

    def tick(self):
        pass

    def run_once(self):
        raise NotImplementedError

    def send_meta(self, text):
        pass


class InternetOutput(Output):
    def describe(self):
        c = self.cfg
        d = f"{c['protocol']} {c['host']}:{c['port']}"
        return d + c["mount"] if c["protocol"] == "Icecast" else d

    def run_once(self):
        c = self.cfg
        shout = c["protocol"] == "Shoutcast"
        fmt = c["format"] if c["format"] in FORMATS else "MP3"
        if shout and fmt not in SHOUT_FORMATS:
            fmt = "MP3"
        codec, muxer, ctype, rate = FORMATS[fmt]
        out = ["-ar", str(rate), "-ac", str(c["channels"])] + codec
        if fmt != "FLAC":
            out += ["-b:a", f"{c['bitrate']}k"]
        sock = None
        try:
            if shout:
                sock = shoutcast_connect({**c, "format": fmt})
                out += ["-f", muxer, "pipe:1"]
            else:
                url = "icecast://{}:{}@{}:{}/{}".format(
                    quote(c["user"], safe=""), quote(c["password"], safe=""),
                    c["host"], c["port"], c["mount"].lstrip("/"))
                if c.get("tls"):                   # connexion chiffrée : le mot de passe ne circule plus en clair
                    out += ["-tls", "1"]
                out += ["-content_type", ctype, "-ice_name", c["name"],
                        "-ice_genre", c["genre"], "-ice_description", c["desc"],
                        "-f", muxer, url]
            self.drain_q()
            p = self.spawn(["ffmpeg"] + self.pcm_in() + self.filters() + out,
                           stdout=subprocess.PIPE if shout else None)
            if shout:
                threading.Thread(target=self.forward, args=(p, sock), daemon=True).start()
            self.wait_all()
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

    def forward(self, p, sock):
        try:
            while True:
                data = p.stdout.read(4096)
                if not data:
                    break
                sock.sendall(data)
        except OSError as e:
            self.err.append(f"Connexion Shoutcast perdue : {e}")
            if p.poll() is None:
                p.terminate()

    def send_meta(self, text):
        c = self.cfg
        if self.state != "live" or not text:
            return
        try:
            if c["protocol"] == "Icecast":
                url = (f"{'https' if c.get('tls') else 'http'}://{c['host']}:{c['port']}/admin/metadata?" + urlencode(
                    {"mount": "/" + c["mount"].lstrip("/"), "mode": "updinfo",
                     "song": text, "charset": "UTF-8"}))
                req = urllib.request.Request(url)
                tok = base64.b64encode(f"{c['user']}:{c['password']}".encode()).decode()
                req.add_header("Authorization", "Basic " + tok)
            else:
                url = (f"http://{c['host']}:{c['port']}/admin.cgi?" + urlencode(
                    {"pass": c["password"], "mode": "updinfo", "song": text}))
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            urllib.request.urlopen(req, timeout=5).read()
            self.meta_note = "Titre envoyé"
        except Exception as e:
            self.meta_note = f"Titre non envoyé : {e}"
            self.eng.log(f"[{self.name}] {self.meta_note}")


def split_hostport(s):
    host, _, port = s.rpartition(":")
    return host.strip("[]") or "127.0.0.1", int(port)


class FMOutput(Output):
    """Sortie FM : son (avec traitement) vers une carte son reliée à l'émetteur,
    et texte RDS (PS / RT) envoyé à l'encodeur RDS."""

    def describe(self):
        return self.cfg.get("device") or "(carte son à choisir)"

    def run_once(self):
        if not have_module("sounddevice"):
            raise RuntimeError("module sounddevice manquant (onglet SOS > Installer)")
        import sounddevice as sd
        label = self.cfg.get("device", "")
        idx = dict(list_output_devices()).get(label)
        if idx is None or idx < 0:
            raise RuntimeError("carte son de sortie introuvable : choisis-la dans la sortie")
        buf, lk = bytearray(), threading.Lock()
        hi, lo = int(1.6 * SR) * 4, int(0.9 * SR) * 4      # le traitement livre parfois le son par paquets de 0,5 s

        def add(data):
            with lk:
                buf.extend(data)
                if len(buf) > hi:  # dérive d'horloge : on rattrape en douceur
                    del buf[:(len(buf) - lo) // 4 * 4]

        def cb(outdata, frames, t, status):
            need = frames * 4
            with lk:
                chunk = bytes(buf[:need])
                del buf[:need]
            outdata[:need] = chunk + bytes(need - len(chunk))

        self.drain_q()
        use_ff = bool(self.filters())
        if use_ff:
            p = self.spawn(["ffmpeg"] + self.pcm_in() + self.filters() +
                           ["-ar", str(SR), "-ac", "2", "-f", "s16le", "pipe:1"],
                           stdout=subprocess.PIPE)

            def reader():
                while True:
                    data = p.stdout.read(CH)
                    if not data:
                        break
                    add(data)
            threading.Thread(target=reader, daemon=True).start()
        else:
            def pump():
                while not self.stop_ev.is_set():
                    try:
                        add(self.q.get(timeout=0.2))
                    except queue.Empty:
                        continue
            threading.Thread(target=pump, daemon=True).start()
        extra = None
        if "WASAPI" in label:
            extra = sd.WasapiSettings(auto_convert=True)
        stream = sd_track(sd.RawOutputStream(samplerate=SR, channels=2, dtype="int16", device=idx,
                                             callback=cb, latency="high", extra_settings=extra))
        try:
            t0 = time.time()
            while len(buf) < int(0.6 * SR) * 4 and time.time() - t0 < 10:
                time.sleep(0.02)
            stream.start()
            self.set_state("live")
            while not self.stop_ev.is_set():
                if use_ff and self.procs and self.procs[0].poll() is not None:
                    break
                time.sleep(0.2)
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    def send_meta(self, text):
        c = self.cfg
        target = (c.get("rds_target") or "").strip()
        if not c.get("rds") or not target or self.state != "live":
            return
        tpl = (c.get("rds_template") or "PS {PS}\\nRT {RT}\\n")
        tpl = tpl.replace("\\r", "\r").replace("\\n", "\n")
        data = tpl.replace("{PS}", (c.get("ps") or "")[:8]).replace("{RT}", (text or "")[:64])
        try:
            mode = c.get("rds_mode", "")
            if mode == "UDP":
                host, port = split_hostport(target)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.sendto(data.encode("utf-8", "replace"), (host, port))
            elif mode == "TCP":
                host, port = split_hostport(target)
                with socket.create_connection((host, port), timeout=3) as s:
                    s.sendall(data.encode("utf-8", "replace"))
            elif SYS != "Windows" and os.path.exists(target) and stat.S_ISFIFO(os.stat(target).st_mode):
                fd = os.open(target, os.O_WRONLY | os.O_NONBLOCK)
                try:
                    os.write(fd, data.encode("utf-8", "replace"))
                finally:
                    os.close(fd)
            else:
                with open(target, "w", encoding="utf-8") as f:
                    f.write(data)
            self.meta_note = "RDS envoyé"
        except Exception as e:
            self.meta_note = f"RDS non envoyé : {e}"
            self.eng.log(f"[{self.name}] {self.meta_note}")


class DABOutput(Output):
    """Sortie DAB+ : vers ODR-AudioEnc (puis ODR-DabMux) ou AAC sur le réseau."""

    def describe(self):
        c = self.cfg
        return c["dest"] if c.get("mode", "").startswith("ODR") else c.get("net_url", "")

    def run_once(self):
        c = self.cfg
        br = str(c["bitrate"])
        prof = c.get("profile", "HE-AAC (SBR)")
        ff = ["ffmpeg"] + self.pcm_in() + self.filters() + ["-ar", "48000", "-ac", "2"]
        self.drain_q()
        if c.get("mode", "").startswith("ODR"):
            exe = c.get("odr_path") or "odr-audioenc"
            if not (shutil.which(exe) or os.path.isfile(exe)):
                raise RuntimeError("odr-audioenc introuvable (indique son chemin complet)")
            flag = {"AAC-LC": "--aaclc", "HE-AAC v2 (SBR+PS)": "--ps"}.get(prof, "--sbr")
            enc = [exe, "-i", "-", "-f", "raw", "-r", "48000", "-c", "2", "-b", br, flag,
                   "-o", c["dest"]] + shlex.split(c.get("extra", ""), posix=(SYS != "Windows"))
            p1 = self.spawn(ff + ["-f", "s16le", "pipe:1"], stdout=subprocess.PIPE)
            p2 = popen(enc, stdin=p1.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self.procs.append(p2)
            threading.Thread(target=self.read_err, args=(p2, False), daemon=True).start()
            p1.stdout.close()
            self.wait_all(live_after=2)
        else:
            codec = {"AAC-LC": ["-c:a", "aac"],
                     "HE-AAC (SBR)": ["-c:a", "libfdk_aac", "-profile:a", "aac_he"],
                     "HE-AAC v2 (SBR+PS)": ["-c:a", "libfdk_aac", "-profile:a", "aac_he_v2"]
                     }.get(prof, ["-c:a", "aac"])
            self.spawn(ff + codec + ["-b:a", f"{br}k", "-f", c.get("net_format", "mpegts"),
                                     c["net_url"]])
            self.wait_all()

    def send_meta(self, text):
        f = (self.cfg.get("dls_file") or "").strip()
        if not f:
            return
        try:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(text or "")
            self.meta_note = "Texte DLS écrit"
        except OSError as e:
            self.meta_note = f"DLS non écrit : {e}"
            self.eng.log(f"[{self.name}] {self.meta_note}")


class RecordOutput(Output):
    """Enregistrement local du programme, découpé en fichiers horaires."""
    CODECS = {"MP3": (["-c:a", "libmp3lame"], ".mp3", True),
              "FLAC": (["-c:a", "flac"], ".flac", False),
              "Ogg Opus": (["-c:a", "libopus"], ".ogg", True),
              "WAV": (["-c:a", "pcm_s16le"], ".wav", False)}
    STAMPS = ("%Y-%m-%d_%Hh%M", "%Y-%m-%d_%Hh", "%d-%m-%Y %Hh%M", "%Y%m%d-%H%M%S")     # tous les noms datés que Bev crée

    def __init__(self, cfg, eng):
        super().__init__(cfg, eng)
        self.last_clean = 0.0

    def describe(self):
        return self.cfg.get("folder", "")

    def name_re(self):
        """Fichiers créés par Bev dans ce dossier : [préfixe] + date (un des formats proposés) + [_2, _3…] + extension
        d'enregistrement. Avant, seul « 2026-10-23_16h30.mp3 » (sans préfixe) était reconnu : la pige (préfixe « Pige_ »,
        fichiers « …_16h.mp3 ») n'était jamais purgée et finissait par remplir le disque. Tout autre fichier du dossier
        (interview, montage…) n'est jamais touché."""
        conv = {"%Y": r"\d{4}", "%m": r"\d{2}", "%d": r"\d{2}", "%H": r"\d{2}", "%M": r"\d{2}", "%S": r"\d{2}"}
        stamps = "|".join(re.sub(r"%[YmdHMS]", lambda m: conv[m.group(0)], re.escape(s).replace(r"\%", "%"))
                          for s in self.STAMPS)
        pre = re.sub(r'[\\/:*?"<>|]', "_", self.cfg.get("prefix", "") or "")
        pres = {"", pre, pre.strip("_- ")} | ({pre + "_"} if pre and pre[-1] not in "_- " else set())
        pres = "|".join(re.escape(p) for p in sorted(pres, key=len, reverse=True))
        exts = "|".join(re.escape(v[1]) for v in self.CODECS.values())
        return re.compile(rf"^(?:{pres})(?:{stamps})(?:_\d+)?(?:{exts})$", re.I)

    def cleanup(self):
        self.last_clean = time.time()
        try:
            days = float(str(self.cfg.get("keep_days") or 0).replace(",", "."))
        except ValueError:
            days = 0
        if days <= 0:
            return
        folder = self.cfg["folder"]
        name_re = self.name_re()
        for n in os.listdir(folder) if os.path.isdir(folder) else []:
            p = os.path.join(folder, n)
            try:
                if name_re.match(n) and os.path.isfile(p) and os.path.getmtime(p) < time.time() - days * 86400:
                    os.remove(p)
                    self.eng.log(f"[{self.name}] ancien fichier supprimé : {n}")
            except OSError:
                pass

    def tick(self):
        if time.time() - self.last_clean > 3600:
            self.cleanup()

    def run_once(self):
        c = self.cfg
        folder = c["folder"]
        os.makedirs(folder, exist_ok=True)
        codec, ext, has_br = self.CODECS.get(c.get("format", "MP3"), self.CODECS["MP3"])
        try:
            minutes = max(1, int(float(c.get("rotate") or 60)))
        except ValueError:
            minutes = 60
        self.cleanup()
        self.drain_q()
        pige = c.get("pige") == "1"
        raw_prefix = re.sub(r'[\\/:*?"<>|]', "_", c.get("prefix", "") or "")
        br = ["-b:a", f"{c['bitrate']}k"] if has_br else []
        if pige:  # pige : un fichier toutes les N minutes, calé sur l'horloge (60 min = à l'heure pile)
            stamp = "%Y-%m-%d_%Hh" if minutes == 60 else "%Y-%m-%d_%Hh%M"
            prefix = raw_prefix.replace("%", "%%")
            if prefix and prefix[-1] not in "_- ":
                prefix += "_"
            pattern = os.path.join(folder, prefix + stamp + ext)
            self.spawn(["ffmpeg"] + self.pcm_in() + self.filters() + codec + br +
                       ["-f", "segment", "-segment_time", str(minutes * 60),
                        "-segment_atclocktime", "1", "-reset_timestamps", "1",
                        "-strftime", "1", pattern])
        else:  # enregistrement simple : un seul fichier par démarrage (date facultative dans le nom)
            stamp = REC_STAMPS.get(c.get("stamp"), "%Y-%m-%d_%Hh%M")
            name = raw_prefix
            if c.get("date", "1") != "0":
                if name and name[-1] not in "_- ":
                    name += "_"
                name += time.strftime(stamp)
            name = name.strip("_- ") or "Enregistrement"
            path, n = os.path.join(folder, name + ext), 1
            while os.path.exists(path):  # jamais d'écrasement : _2, _3...
                n += 1
                path = os.path.join(folder, f"{name}_{n}{ext}")
            self.spawn(["ffmpeg"] + self.pcm_in() + self.filters() + codec + br + [path])
        self.wait_all()


REC_STAMPS = {"2026-10-23_16h30": "%Y-%m-%d_%Hh%M", "2026-10-23_16h (à l'heure)": "%Y-%m-%d_%Hh",
              "23-10-2026 16h30": "%d-%m-%Y %Hh%M", "20261023-163000": "%Y%m%d-%H%M%S"}

OUTPUT_CLASSES = {"internet": InternetOutput, "fm": FMOutput, "dab": DABOutput,
                  "record": RecordOutput}


def make_output(cfg, eng):
    return OUTPUT_CLASSES[cfg["type"]](cfg, eng)

# ------------------------------------------------- accès Internet (réseau)
VIRTUAL = ("loopback", "vethernet", "vmware", "virtualbox", "vbox", "docker", "veth", "br-",
           "bluetooth", "tailscale", "zerotier", "hyper-v", "wsl", "utun", "awdl", "llw",
           "bridge", "vpn", "tun", "tap", "virbr")
KIND_TXT = {"ethernet": "RJ45", "wifi": "Wi-Fi", "mobile": "4G/5G"}


def guess_kind(name):
    n = name.lower()
    if any(k in n for k in ("wi-fi", "wifi", "wlan", "wireless", "sans fil")) or n.startswith("wl"):
        return "wifi"
    if (any(k in n for k in ("rndis", "usb", "mobile", "cellul", "wwan", "ppp", "4g", "5g",
                             "lte", "huawei", "modem")) or n.startswith("ww")):
        return "mobile"
    return "ethernet"


def list_links():
    """Connexions réseau actives avec une adresse IPv4 : [{name, ip, up, kind}]."""
    import psutil
    stats, out = psutil.net_if_stats(), []
    for name, addrs in psutil.net_if_addrs().items():
        if any(v in name.lower() for v in VIRTUAL):
            continue
        a4 = next((a for a in addrs if a.family == socket.AF_INET and not a.address.startswith(("127.", "169.254."))), None)
        ip = a4.address if a4 else None
        if ip:
            st = stats.get(name)
            mac = next((a.address for a in addrs if getattr(a.family, "name", "") == "AF_LINK" or a.family == getattr(psutil, "AF_LINK", -1)), "")
            out.append({"name": name, "ip": ip, "up": bool(st and st.isup), "kind": guess_kind(name),
                        "mask": a4.netmask or "", "mac": mac, "speed": int(st.speed) if st else 0,
                        "mtu": int(st.mtu) if st else 0, "v6": sum(1 for a in addrs if a.family == socket.AF_INET6)})
    order = {"ethernet": 0, "wifi": 1, "mobile": 2}
    return sorted(out, key=lambda l: order[l["kind"]])


def default_route_ip():
    """Adresse IP du lien que Windows/Linux utilise réellement pour sortir sur Internet."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def parse_targets(txt):
    out = []
    for part in re.split(r"[,; ]+", txt or ""):
        if ":" in part:
            h, _, p = part.rpartition(":")
            if p.isdigit():
                out.append((h, int(p)))
    return out or [("1.1.1.1", 443), ("8.8.8.8", 443)]


def probe_link(name, ip, targets, n=5):
    """Mesure latence / gigue / perte en ouvrant des connexions TCP depuis ce lien."""
    lats, fails = [], 0
    for k in range(n):
        host, port = targets[k % len(targets)]
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        try:
            if SYS == "Linux":
                try:
                    s.setsockopt(socket.SOL_SOCKET, 25, name.encode() + b"\0")  # SO_BINDTODEVICE
                except OSError:
                    pass
            s.bind((ip, 0))
            t0 = time.perf_counter()
            s.connect((host, port))
            lats.append((time.perf_counter() - t0) * 1000)
        except OSError:
            fails += 1
        finally:
            s.close()
        time.sleep(0.15)
    lat = sum(lats) / len(lats) if lats else None
    jit = (sum(abs(a - b) for a, b in zip(lats, lats[1:])) / (len(lats) - 1)) if len(lats) > 1 else 0.0
    return {"lat": lat, "jit": jit, "loss": 100 * fails / n, "t": time.time()}


def quality(st):
    """(libellé, couleur, utilisable) d'après latence, gigue et perte."""
    if not st or st.get("lat") is None:
        return "Coupée", "#c0392b", False
    lat, jit, loss = st["lat"], st["jit"], st["loss"]
    if loss == 0 and lat < 80 and jit < 25:
        return "Excellente", "#1e8e3e", True
    if loss <= 10 and lat < 200 and jit < 80:
        return "Bonne", "#27ae60", True
    if loss <= 30 and lat < 500:
        return "Moyenne", "#e67e22", True
    return "Mauvaise", "#c0392b", False


def speed_test(ip):
    """Débit descendant / montant (Mbit/s) via Cloudflare, depuis ce lien. Retourne (down, up)."""
    import http.client
    down = up = None
    try:
        c = http.client.HTTPSConnection("speed.cloudflare.com", timeout=20, source_address=(ip, 0))
        t0 = time.perf_counter()
        c.request("GET", "/__down?bytes=4000000")
        n = len(c.getresponse().read())
        down = n * 8 / 1e6 / (time.perf_counter() - t0)
        c.close()
    except Exception:
        pass
    try:
        c = http.client.HTTPSConnection("speed.cloudflare.com", timeout=20, source_address=(ip, 0))
        body = bytes(1500000)
        t0 = time.perf_counter()
        c.request("POST", "/__up", body=body, headers={"Content-Type": "application/octet-stream"})
        c.getresponse().read()
        up = len(body) * 8 / 1e6 / (time.perf_counter() - t0)
        c.close()
    except Exception:
        pass
    return down, up


def prefer_link(name):
    """Fait de ce lien la sortie Internet par défaut du système. Retourne (ok, message)."""
    try:
        if SYS == "Windows":
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                return False, "droits administrateur requis (lance l'application en administrateur)"
            links = [l["name"] for l in list_links()]
            for n in links:
                r = subprocess.run(["netsh", "interface", "ipv4", "set", "interface", n,
                                    "metric=" + ("5" if n == name else "0")],
                                   capture_output=True, text=True, creationflags=0x08000000)
                if r.returncode != 0 and n == name:
                    return False, (r.stdout + r.stderr).strip()[:200] or "netsh a échoué"
            return True, ""
        if SYS == "Linux":
            for n in [l["name"] for l in list_links() if l["name"] != name]:
                subprocess.run(["ip", "route", "del", "default", "dev", n, "metric", "5"],
                               capture_output=True)
            out = run(["ip", "-4", "route", "show", "default", "dev", name])
            m = re.search(r"default via (\S+)", out)
            if not m:
                return False, "passerelle introuvable pour ce lien"
            r = subprocess.run(["ip", "route", "replace", "default", "via", m.group(1), "dev", name,
                                "metric", "5"], capture_output=True, text=True)
            return (r.returncode == 0), (r.stderr.strip()[:200] or "droits root requis")
    except Exception as e:
        return False, str(e)
    return False, "système non pris en charge : change de connexion à la main"




def wifi_info(name):
    """Nom du réseau Wi-Fi (SSID) et force du signal, quand le système les donne."""
    try:
        if SYS == "Windows":
            out = run(["netsh", "wlan", "show", "interfaces"])
            blocks = re.split(r"\n\s*\n", out)
            for b in blocks:
                if name.lower() in b.lower() or len(blocks) == 1:
                    ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", b, re.M)
                    sig = re.search(r"(?:Signal)\s*:\s*(\d+)\s*%", b)
                    band = re.search(r"(?:Bande|Band)\s*:\s*(.+)$", b, re.M)
                    if ssid:
                        return {"ssid": ssid.group(1).strip(), "signal": sig.group(1) + " %" if sig else "",
                                "band": band.group(1).strip() if band else ""}
        elif SYS == "Darwin":
            out = run(["/usr/sbin/networksetup", "-getairportnetwork", name])
            m = re.search(r":\s*(.+)$", out.strip())
            if m and "not" not in out.lower():
                return {"ssid": m.group(1).strip(), "signal": "", "band": ""}
        else:
            out = run(["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,FREQ", "dev", "wifi"])
            for line in out.splitlines():
                p = line.split(":")
                if p and p[0] == "yes":
                    return {"ssid": p[1] if len(p) > 1 else "", "signal": (p[2] + " %") if len(p) > 2 else "",
                            "band": p[3] if len(p) > 3 else ""}
    except Exception as _ex:
        trace("wifi_info", _ex)
    return {}


def public_info(ip):
    """Adresse publique, opérateur, ville et pays vus depuis ce lien (service ipinfo.io)."""
    import http.client
    try:
        c = http.client.HTTPSConnection("ipinfo.io", timeout=6, source_address=(ip, 0))
        c.request("GET", "/json", headers={"User-Agent": "studio-radio"})
        d = json.loads(c.getresponse().read().decode("utf-8", "replace"))
        c.close()
        return {"pub": d.get("ip", ""), "org": re.sub(r"^AS\d+\s+", "", d.get("org", "")), "city": d.get("city", ""),
                "country": d.get("country", "")}
    except Exception:
        return {}

# ------------------------------------------------- métadonnées d'un automate de diffusion (Radiologik, RadioDJ, Rivendell…)
AUTO_PORT = 8765
AUTO_KEYS = {"title": ("title", "titre", "song", "track", "name"), "artist": ("artist", "artiste", "interprete", "performer"),
             "album": ("album",), "cover": ("cover", "artwork", "art", "image", "picture", "pochette", "coverurl", "cover_url")}


def auto_parse(raw, ctype=""):
    """Titre en cours envoyé ou écrit par un automate -> {"artist", "title", "album", "cover"} (valeurs vides si absentes).
    Accepte : JSON, XML (balises ou attributs), formulaire / adresse « artist=…&title=… », ou texte « Artiste - Titre »."""
    if isinstance(raw, bytes):
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                raw = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    t = (raw or "").strip().lstrip("﻿")
    out = {"artist": "", "title": "", "album": "", "cover": ""}

    def take(d):
        low = {str(k).lower().replace("-", "_"): v for k, v in d.items()}
        for field, names in AUTO_KEYS.items():
            for n in names:
                v = low.get(n)
                if isinstance(v, list):
                    v = v[0] if v else ""
                if isinstance(v, (str, int, float)) and str(v).strip():
                    out[field] = str(v).strip()
                    break
    if not t:
        return out
    if t[:1] in "{[":
        try:
            js = json.loads(t)
            if isinstance(js, list):
                js = js[0] if js else {}
            if isinstance(js, dict):
                for k in ("now", "nowplaying", "now_playing", "current", "track", "song"):  # {"now": {...}}
                    if isinstance(js.get(k), dict):
                        js = {**js, **js[k]}
                take(js)
                return out
        except ValueError:
            pass
    if t.startswith("<"):
        # XML lu sans bibliothèque XML (absente du socle des versions déjà installées : la mise à jour express reste
        # possible) : balises <title>…</title> et attributs title="…", premières occurrences
        import html as _html
        d = {}
        for tag, txt in re.findall(r"<(?:[\w.-]+:)?([\w.-]+)[^>]*>([^<]+)</", t):
            if txt.strip():
                d.setdefault(tag.lower(), _html.unescape(txt.strip()))
        for k, v in re.findall(r"([\w.-]+)\s*=\s*\"([^\"]*)\"", t):
            d.setdefault(k.lower(), _html.unescape(v))
        if d:
            take(d)
            return out
    if "=" in t and ("&" in t or t.split("=", 1)[0].lower() in sum(AUTO_KEYS.values(), ())) and "\n" not in t:
        take(urllib.parse.parse_qs(t.lstrip("?"), keep_blank_values=False))
        if out["title"] or out["artist"]:
            return out
    line = next((ln.strip() for ln in t.splitlines() if ln.strip()), "")
    if " - " in line:
        out["artist"], out["title"] = [x.strip() for x in line.split(" - ", 1)]
    elif " – " in line:
        out["artist"], out["title"] = [x.strip() for x in line.split(" – ", 1)]
    else:
        out["title"] = line
    return out


def auto_text(info):
    a, t = (info.get("artist") or "").strip(), (info.get("title") or "").strip()
    return f"{a} - {t}" if a and t else (t or a)


class AutomateMeta:
    """Reçoit le titre en cours d'un automate de deux façons (au choix, ou les deux) :
      - FICHIER : l'automate écrit le titre dans un fichier (texte, XML ou JSON) ; Bev le relit dès qu'il change ;
      - RÉSEAU : l'automate appelle une adresse de Bev à chaque titre, par ex.
        http://127.0.0.1:8765/?artist=…&title=…&cover=… (GET), ou envoie du JSON / un formulaire / du texte (POST).
    La pochette peut être une adresse web (téléchargée) ou un fichier image. on_change(info) est appelé à chaque nouveau titre,
    info = {"artist", "title", "album", "cover" (fichier local ou ""), "text", "source", "t"}."""

    def __init__(self, on_change, log=lambda m: None):
        self.on_change, self.log = on_change, log
        self.cfg = {}
        self.last, self.last_sig = None, None
        self.srv = None
        self.port_err = ""
        self.stop_ev = threading.Event()
        self.cover_dir = os.path.join(os.path.expanduser("~"), ".broadcast_tool_covers", "automate")
        threading.Thread(target=self._watch_file, daemon=True).start()

    # --- réglages : {"on": bool, "file": chemin, "net": bool, "port": int, "lan": bool}
    def configure(self, cfg):
        cfg = dict(cfg or {})
        old = self.cfg
        self.cfg = cfg
        want = bool(cfg.get("on") and cfg.get("net"))
        key = (want, int(cfg.get("port") or AUTO_PORT), bool(cfg.get("lan")))
        if key != getattr(self, "_srv_key", None):
            self._srv_key = key
            self._stop_server()
            if want:
                self._start_server(key[1], key[2])
        if cfg.get("file") != old.get("file"):
            self._fsig = None

    def stop(self):
        self.stop_ev.set()
        self._stop_server()

    def url(self, host="127.0.0.1"):
        return f"http://{host}:{int(self.cfg.get('port') or AUTO_PORT)}/"

    # --- fichier
    def _watch_file(self):
        self._fsig = None
        while not self.stop_ev.wait(1.0):
            f = (self.cfg.get("file") or "").strip()
            if not (self.cfg.get("on") and f):
                continue
            try:
                stt = os.stat(f)
                sig = (stt.st_mtime_ns, stt.st_size)
                if sig == self._fsig:
                    continue
                self._fsig = sig
                time.sleep(0.15)                          # l'automate finit d'écrire
                with open(f, "rb") as fh:
                    raw = fh.read(65536)
                self.receive(auto_parse(raw), "fichier", base=os.path.dirname(f))
            except OSError:
                continue

    # --- réseau
    @staticmethod
    def _local_ip(ip, lan):
        """Adresse autorisée : cet ordinateur, et (option) le réseau local (10/8, 172.16/12, 192.168/16, fe80::, fc00::/7)."""
        ip = ip.split("%")[0].lower()
        if ip in ("127.0.0.1", "::1") or ip.startswith("127.") or ip.startswith("::ffff:127."):
            return True
        if not lan:
            return False
        ip = ip[7:] if ip.startswith("::ffff:") else ip
        if ip.startswith(("10.", "192.168.", "fe80:", "fc", "fd")):
            return True
        m = re.match(r"^172\.(\d+)\.", ip)
        return bool(m and 16 <= int(m.group(1)) <= 31)

    def _start_server(self, port, lan):
        """Petit serveur HTTP (socket seulement, sans http.server : absent du socle des versions déjà installées, ce qui
        aurait imposé l'installateur complet au lieu de la mise à jour express)."""
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0" if lan else "127.0.0.1", port))
            srv.listen(16)
            srv.settimeout(0.5)
        except OSError as ex:
            self.srv, self.port_err = None, f"port {port} indisponible ({ex.strerror or ex})"
            self.log(f"Automate : {self.port_err}.")
            return
        self.srv, self.port_err = srv, ""
        slots = threading.BoundedSemaphore(16)      # 16 échanges à la fois au plus : un flot de connexions ne sature pas Bev

        def client(c, ip):
            try:
                self._client(c, ip, lan)
            finally:
                slots.release()

        def serve():
            while self.srv is srv and not self.stop_ev.is_set():
                try:
                    c, addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not slots.acquire(blocking=False):
                    try:
                        c.close()
                    except OSError:
                        pass
                    continue
                threading.Thread(target=client, args=(c, addr[0]), daemon=True).start()
            try:
                srv.close()
            except OSError:
                pass
        threading.Thread(target=serve, daemon=True).start()
        self.log(f"Automate : réception des titres sur le port {port}" + (" (réseau local)." if lan else " (cet ordinateur)."))

    def _client(self, c, ip, lan):
        def answer(code, text):
            body = (text + "\n").encode("utf-8")
            head = (f"HTTP/1.0 {code} {'OK' if code == 200 else 'Refus'}\r\nContent-Type: text/plain; charset=utf-8\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode("ascii")
            try:
                c.sendall(head + body)
            except OSError:
                pass
        try:
            c.settimeout(5)
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 16384:
                part = c.recv(4096)
                if not part:
                    break
                data += part
            head, _, body = data.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            meth, path = (lines[0].split(" ") + ["", ""])[:2]
            hdr = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in lines[1:])}
            n = min(int(hdr.get("content-length") or 0), 65536)
            while len(body) < n:
                part = c.recv(4096)
                if not part:
                    break
                body += part
            if not self._local_ip(ip, lan):
                return answer(403, "refusé : adresse hors du réseau local")
            q = urllib.parse.urlsplit(path).query
            # Code secret (token) : obligatoire pour les autres postes du réseau (si exigé dans les réglages), et pour
            # toute demande venue d'un NAVIGATEUR (une page web ouverte sur ce PC ne doit pas pouvoir changer le titre à
            # l'antenne ; les automates n'envoient pas ces en-têtes de navigateur).
            tok = str(self.cfg.get("token") or "")
            given = (urllib.parse.parse_qs(q).get("token") or [""])[0] or hdr.get("x-bev-token", "")
            tok_ok = bool(tok) and compare_digest(given.encode("utf-8", "replace"), tok.encode("utf-8"))
            remote = not self._local_ip(ip, False)
            browser = any(k in hdr for k in ("origin", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest"))
            if browser and not tok_ok:
                return answer(403, "refusé : demande venue d'un navigateur sans le code secret (token=…)")
            if remote and self.cfg.get("lan_token") and not tok_ok:
                return answer(403, "refusé : code secret absent ou faux (token=…, voir l'adresse donnée par Bev)")
            raw = body[:n] if (meth.upper() == "POST" and body[:n].strip()) else q.encode()
            if not raw.strip():
                return answer(200, "Bev : prêt à recevoir le titre en cours (?artist=…&title=…&cover=…)")
            info = auto_parse(raw, hdr.get("content-type", ""))
            if not (info["title"] or info["artist"]):
                return answer(400, "aucun titre reçu (paramètres attendus : artist, title, cover)")
            self.receive(info, "réseau", local_ok=not remote)
            answer(200, "ok : " + auto_text(info))
        except (OSError, ValueError, IndexError):
            pass
        finally:
            try:
                c.close()
            except OSError:
                pass

    def _stop_server(self):
        srv, self.srv = self.srv, None             # (la boucle d'accueil s'arrête d'elle-même et ferme la prise)
        if srv is not None:
            try:
                srv.close()
            except OSError:
                pass

    # --- titre reçu
    def receive(self, info, source, base="", local_ok=True):
        if not (info.get("title") or info.get("artist")):
            return
        sig = (info.get("artist"), info.get("title"), info.get("album"), info.get("cover"))
        if sig == self.last_sig:
            return
        self.last_sig = sig
        cov = self.fetch_cover(info.get("cover") or "", base, local_ok)
        res = {**info, "cover": cov, "text": auto_text(info), "source": source, "t": time.time()}
        self.last = res
        try:
            self.on_change(res)
        except Exception as ex:
            self.log(f"Automate : titre non affiché ({ex})")

    def fetch_cover(self, ref, base="", local_ok=True):
        """Pochette : fichier local (chemin, éventuellement relatif au fichier de l'automate, ou file://), ou adresse web
        téléchargée (2 Mo au plus) dans un petit cache. Renvoie un chemin de fichier, ou ""."""
        ref = (ref or "").strip()
        if not ref:
            return ""
        if ref.lower().startswith("file://"):
            ref = urllib.parse.unquote(urllib.parse.urlsplit(ref).path)
            if SYS == "Windows" and re.match(r"^/[A-Za-z]:", ref):
                ref = ref[1:]
        if not ref.lower().startswith(("http://", "https://")):
            if not local_ok:                         # (un autre poste ne désigne pas les fichiers de cet ordinateur)
                return ""
            p = ref if os.path.isabs(ref) else os.path.join(base or "", ref)
            return p if os.path.isfile(p) else ""
        try:
            os.makedirs(self.cover_dir, exist_ok=True)
            fn = os.path.join(self.cover_dir, hashlib.sha1(ref.encode("utf-8")).hexdigest()[:16] + ".img")
            if not os.path.isfile(fn):
                rq = urllib.request.Request(ref, headers={"User-Agent": "Bev"})
                with urllib.request.urlopen(rq, timeout=6) as r:
                    data = r.read(2_000_001)
                if len(data) > 2_000_000 or not data:
                    return ""
                with open(fn + ".tmp", "wb") as fh:
                    fh.write(data)
                os.replace(fn + ".tmp", fn)
                for old in sorted(os.listdir(self.cover_dir), key=lambda n: os.path.getmtime(os.path.join(self.cover_dir, n)))[:-60]:
                    try:
                        os.remove(os.path.join(self.cover_dir, old))       # cache borné aux 60 dernières pochettes
                    except OSError:
                        pass
            return fn
        except Exception as ex:
            self.log(f"Automate : pochette non récupérée ({redact(ex)})")
            return ""


# ============================================================ INTERFACE Qt (PySide6)
# ------------------------------------------------------------------ moteur audio dans un processus séparé
# Le moteur (capture, mixage, cartouches, encodeurs) tourne dans son propre processus Python : il a son propre cœur de
# processeur et son propre verrou d'interpréteur (GIL). L'interface ne peut plus jamais faire décrocher l'antenne, et
# l'antenne ne fait plus ramer l'interface. Le processus est préparé à l'avance (démarrage instantané) ; s'il ne peut pas
# être lancé, le moteur tourne comme avant dans l'application (repli automatique, rien ne change pour l'utilisateur).
WORKER_ARG = "--bev-engine"
SNAP_S = 0.025                         # 40 états par seconde envoyés à l'interface


def _merge(dst, kv):
    for k, v in kv.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            dst[k].update(v)
        else:
            dst[k] = v


class EngineWorker:
    """Côté processus moteur : reçoit les commandes de l'interface, renvoie l'état 40 fois par seconde."""

    def __init__(self, conn):
        self.conn, self.eng, self.out_q = conn, None, queue.Queue()
        self.cfg_sig, self.done = None, threading.Event()
        self.counts_sent = 0
        self.ps = None
        try:
            import psutil
            self.ps = psutil.Process()
        except Exception:
            pass

    def log(self, msg):
        self.out_q.put(("log", msg))

    def alert(self, text, key=None):
        self.out_q.put(("alert", text, key))

    def snap(self):
        e = self.eng
        pin, pout = list(e.in_peak), list(e.peak)
        e.in_peak[:] = [-90.0, -90.0]
        e.peak[:] = [-90.0, -90.0]
        st, loading = e.cart_status()
        outs = list(e.outputs)
        sig = tuple((o.cfg.get("id"), id(o.cfg)) for o in outs)
        if sig != self.cfg_sig:                    # configuration des sorties : envoyée seulement quand elle change
            self.cfg_sig = sig
            self.out_q.put(("outcfg", [json.loads(json.dumps(o.cfg)) for o in outs]))
        if e.counts_ver != self.counts_sent:       # nombre de lectures des titres du secours (affiché dans la liste)
            self.counts_sent = e.counts_ver
            self.out_q.put(("counts", dict(e.counts())))
        return {"t": time.time(), "running": e.running, "started": e.started, "backup": e.backup, "manual": e.manual,
                "pl_pause": e.pl_pause, "pl_stop": e.pl_stop, "air": e.air, "monitor": e.monitor, "listen": e.listen, "cap_state": e.cap_state, "cap_err": e.cap_err,
                "src_dev": e.src_dev,
                "mute": e.mute, "tone": e.tone, "silent_ms": e.silent_ms, "loud_ms": e.loud_ms, "rec_ms": e.rec_ms,
                "track": e.track, "meta": e.meta, "meta_manual": e.meta_manual, "pl_cur": dict(e.pl_cur) if e.pl_cur else None,
                "pl_out": e.pl_out, "in_peak": pin, "peak": pout, "clip_t": e.clip_t, "proc_ms": e.proc_ms, "late": e.late,
                "slow": e.slow_now(), "mix_g": e.mix_g, "carts": st, "loading": set(loading),
                "voices": [(v["id"], bool(v["stopping"])) for v in list(e.voices)],
                "outs": [(o.cfg.get("id"), o.state, o.detail, o.t_live) for o in outs], "cmon": e.cmon.label,
                "pm": dict(e.pm) if e.pm else {}, "pm_main": dict(e.pm_main) if e.pm_main else {}}

    def sender(self):
        """Seul fil qui écrit vers l'interface (une connexion ne supporte pas deux écritures simultanées)."""
        nxt = time.perf_counter()
        while not self.done.is_set():
            e = self.eng
            busy = e is None or e.air or e.monitor or bool(e.voices) or bool(e.loading)
            nxt += SNAP_S if busy else 0.1            # au repos (rien ne joue) : 10 états par seconde suffisent
            d = nxt - time.perf_counter()
            if d > 0:
                time.sleep(d)
            else:
                nxt = time.perf_counter()
            try:
                if self.eng is not None:
                    self.out_q.put(("snap", self.snap()))
                while True:
                    try:
                        m = self.out_q.get_nowait()
                    except queue.Empty:
                        break
                    self.conn.send(m)
                if self.eng is not None and not self.eng.running:
                    self.done.set()
            except (EOFError, OSError, BrokenPipeError):
                self.done.set()
            except Exception as ex:                 # une erreur d'état ne doit jamais couper l'antenne
                try:
                    self.conn.send(("log", f"Moteur : état non transmis ({ex})"))
                except Exception:
                    self.done.set()

    def handle(self, m):
        k = m[0]
        e = self.eng
        if k == "start":
            _, prof, standalone, alerts, fx = m
            FX.update(fx)
            self.eng = Engine(prof, self.log, self.alert if alerts else None)
            self.eng.start()
        elif e is None:
            return
        elif k == "fx":
            FX.update(m[1])
            e.apply_fx()
        elif k == "call":
            getattr(e, m[1])(*m[2], **m[3])
        elif k == "set":
            setattr(e, m[1], m[2])
        elif k == "prof":
            e.prof_update(m[1], **m[2])
        elif k == "out":
            o = e.output(m[1])
            if o:
                o.start() if m[2] == "start" else o.stop()
        elif k == "cmon":
            e.cmon.set_device(m[1])
        elif k == "stop":
            e.stop()

    def run(self):
        threading.Thread(target=self.sender, daemon=True).start()
        self.conn.send(("ready", os.getpid()))
        while not self.done.is_set():
            try:
                if not self.conn.poll(0.2):
                    continue
                m = self.conn.recv()
            except (EOFError, OSError):
                break                               # l'interface a disparu : on arrête proprement l'antenne
            try:
                self.handle(m)
            except Exception as ex:
                self.log(f"Moteur : commande « {m[0]} » impossible ({ex})")
            if m[0] == "stop":
                break
        if self.eng is not None and self.eng.running:
            try:
                self.eng.stop()
            except Exception as _ex:
                trace("run", _ex)
        if self.eng is not None:
            time.sleep(1.8)                         # les encodeurs se ferment proprement (fin de fichier, fin de flux)
        time.sleep(SNAP_S * 3)                      # dernier état (arrêt) transmis
        self.done.set()


def _engine_worker_main():
    try:
        sys.setswitchinterval(0.002)
    except Exception:
        pass
    crash_watch("moteur")                           # plantage brutal du moteur : noté pour le rapport de support
    threading.excepthook = lambda a: trace_exc("moteur (fil " + str(getattr(a.thread, "name", "?")) + ")",
                                               a.exc_type, a.exc_value, a.exc_traceback)
    if SYS == "Windows":                            # priorité « supérieure à la normale » : l'antenne passe avant le reste
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00008000)
            ctypes.windll.winmm.timeBeginPeriod(1)  # blocs de 20 ms réguliers (pas de 15,6 ms par défaut sous Windows)
            globals()["_ENGINE_MUTEX"] = ctypes.windll.kernel32.CreateMutexW(None, False, "BevRadioEngine")  # vu par l'installateur
        except Exception:
            pass
    try:
        from multiprocessing.connection import Client
        i = sys.argv.index(WORKER_ARG)
        conn = Client(sys.argv[i + 1], authkey=bytes.fromhex(sys.argv[i + 2]))
    except Exception:
        os._exit(3)
    try:
        EngineWorker(conn).run()
    finally:
        try:
            conn.close()
        except Exception:
            pass
        os._exit(0)


if WORKER_ARG in sys.argv and __name__ in ("__main__", "__mp_main__"):
    _engine_worker_main()


def clean_env(splash=True, reset=True):
    """Environnement propre pour relancer Bev (ou son moteur). Une application PyInstaller « un seul fichier » transmet sinon
    à l'enfant le dossier temporaire où elle s'est décompressée, effacé à sa fermeture : l'application relancée plantait
    (bug du redémarrage après un réglage d'Apparence)."""
    env = dict(os.environ)
    if not splash:
        env.pop("QT_QPA_PLATFORM", None)
    if reset:                                   # (le moteur, lui, réutilise le dossier de l'application qui le lance)
        for k in list(env):
            if k.startswith("_PYI_") or k == "_MEIPASS2":
                env.pop(k, None)
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    if not splash:
        env["PYINSTALLER_SUPPRESS_SPLASH_SCREEN"] = "1"
    return env


def relaunch_self(fresh=False):
    """Relance l'application (après un réglage d'Apparence, une réinitialisation…) : la nouvelle fenêtre attend que
    l'ancienne soit complètement fermée avant de s'ouvrir (--after <pid>). fresh : repart du code le plus récent
    (mise à jour express) au lieu de rester sur celui qui tourne."""
    args, skip = [], False
    for a in (sys.argv[1:] if getattr(sys, "frozen", False) or "__compiled__" in globals() else sys.argv[1:]):
        if skip:
            skip = False
            continue
        if a == "--after":
            skip = True
            continue
        if a in ("--selftest", WORKER_ARG):
            continue
        args.append(a)
    base = [sys.executable] if (getattr(sys, "frozen", False) or "__compiled__" in globals()) else [sys.executable, os.path.abspath(sys.argv[0])]
    kw = {"creationflags": 0x00000008 | 0x00000200} if SYS == "Windows" else {"start_new_session": True}
    env = clean_env(True)
    if fresh:
        env.pop("BEV_CODE", None)
    subprocess.Popen(base + args + ["--after", str(os.getpid())], env=env, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)


def wait_pid_gone(pid, timeout=20.0):
    """Attend la fin d'un processus (l'ancienne fenêtre lors d'un redémarrage, l'application lors d'une mise à jour)."""
    t0 = time.time()
    try:
        import psutil
        try:
            psutil.Process(pid).wait(timeout)
        except psutil.NoSuchProcess:
            pass
        except Exception:
            pass
        return
    except ImportError:
        pass
    while time.time() - t0 < timeout:
        try:
            if SYS == "Windows":
                import ctypes
                h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
                if not h:
                    return
                r = ctypes.windll.kernel32.WaitForSingleObject(h, 250)
                ctypes.windll.kernel32.CloseHandle(h)
                if r == 0:
                    return
            else:
                os.kill(pid, 0)
                time.sleep(0.2)
        except Exception:
            return


def worker_cmd():
    """Commande qui relance cette même application en mode « moteur seul » (script, exécutable PyInstaller ou Nuitka)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    if "__compiled__" in globals():
        return [os.path.abspath(sys.argv[0])]
    return [sys.executable, os.path.abspath(__file__)]


class WorkerSlot:
    """Un processus moteur lancé à l'avance, connecté et en attente : « Démarrer » est instantané."""

    def __init__(self):
        self.proc = self.conn = None
        self.pid, self.error = None, ""
        self.ready = threading.Event()
        threading.Thread(target=self._spawn, daemon=True).start()

    def _spawn(self):
        lst = None
        try:
            from multiprocessing.connection import Listener
            key = os.urandom(16)
            lst = Listener(authkey=key)
            env = clean_env(splash=False, reset=False)   # pas d'écran de démarrage pour le moteur (processus invisible)
            lp = os.path.join(os.path.expanduser("~"), ".bev_moteur.log")
            try:
                if os.path.getsize(lp) > 5e6:           # journal d'erreurs du moteur : gardé sous 5 Mo (il grossissait sans fin)
                    os.replace(lp, lp + ".1")
            except OSError:
                pass
            try:
                log = open(lp, "ab")
            except OSError:
                log = subprocess.DEVNULL
            try:
                self.proc = popen(worker_cmd() + [WORKER_ARG, lst.address, key.hex()], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=log, env=env)
            finally:
                if log is not subprocess.DEVNULL:
                    log.close()                         # (le moteur a sa propre copie ; celle-ci restait ouverte à chaque relance)
            box = {}

            def acc():
                try:
                    box["c"] = lst.accept()
                except Exception as ex:
                    box["e"] = ex
            th = threading.Thread(target=acc, daemon=True)
            th.start()
            th.join(25)
            c = box.get("c")
            if c is None:
                raise RuntimeError(str(box.get("e") or "le processus moteur ne répond pas"))
            if not c.poll(10):
                raise RuntimeError("le processus moteur ne s'est pas présenté")
            m = c.recv()
            if not (isinstance(m, tuple) and m and m[0] == "ready"):
                raise RuntimeError("réponse inattendue du processus moteur")
            self.conn, self.pid = c, m[1]
        except Exception as ex:
            self.error = str(ex) or ex.__class__.__name__
            if self.proc is not None and self.proc.poll() is None:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        finally:
            try:
                if lst is not None:
                    lst.close()
            except Exception:
                pass
            self.ready.set()

    def alive(self):
        return self.conn is not None and self.proc is not None and self.proc.poll() is None

    def close(self):
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass


class _OutProxy:
    """Une sortie vue depuis l'interface (l'encodeur réel tourne dans le processus moteur)."""

    def __init__(self, eng, cfg):
        self.eng, self.cfg = eng, cfg
        self.state, self.detail, self.t_live = "stopped", "", 0.0

    @property
    def name(self):
        return self.cfg.get("name") or self.cfg.get("type", "")

    def status_text(self):
        if self.state == "live":
            return "● En ligne depuis " + fmt_dur(time.time() - self.t_live)
        if self.state == "connecting":
            return "◌ Connexion en cours…"
        if self.state == "error":
            return "✕ Problème : " + (self.detail or "?")[:80]
        return "○ Arrêté"

    def start(self):
        if self.state in ("stopped", "error"):
            self.state, self.detail = "connecting", ""
            self.eng._hold_out[self.cfg.get("id")] = time.time()
        self.eng._send(("out", self.cfg.get("id"), "start"))

    def stop(self):
        self.state, self.detail = "stopped", ""
        self.eng._hold_out[self.cfg.get("id")] = time.time()
        self.eng._send(("out", self.cfg.get("id"), "stop"))


class _CmonProxy:
    def __init__(self, eng):
        self.eng, self.label = eng, ""

    def set_device(self, label):
        self.label = label
        self.eng._send(("cmon", label))


class EngineProxy:
    """Le moteur vu depuis l'interface : mêmes attributs et mêmes commandes qu'Engine, mais le travail se fait dans le
    processus moteur. Les valeurs changées ici (coupure, tonalité…) sont prises en compte tout de suite à l'écran."""
    SETTABLE = ("tone", "mute", "meta_manual", "manual", "pl_pause", "pl_stop")
    HOLD = 0.8

    def __init__(self, slot, prof, log, alert=None, standalone=False, on_dead=None):
        d = self.__dict__
        d["_slot"], d["_conn"], d["log"], d["alert"] = slot, slot.conn, log, alert
        d["prof"], d["standalone"], d["_on_dead"] = prof, standalone, on_dead
        d["_lk"], d["_wlk"] = threading.Lock(), threading.Lock()
        d["_hold"], d["_hold_out"], d["_pred_load"] = {}, {}, {}
        d["_stopping"], d["_fx"] = False, None
        d["cmon"] = _CmonProxy(self)
        d["outputs"] = []
        d["counts_in"] = None
        d["_fbp"], d["_fbp_ver"], d["fb_ver"] = None, -1, 0
        d["_s"] = {"t": time.time(), "running": True, "started": time.time(), "backup": False, "manual": False, "pl_pause": False, "pl_stop": False, "mute": False,
                   "tone": False, "silent_ms": 0, "loud_ms": 0, "rec_ms": 2000.0, "track": "", "meta": "",
                   "meta_manual": prof.get("meta", {}).get("text", ""), "pl_cur": None, "pl_out": 0, "clip_t": 0.0,
                   "proc_ms": 0.0, "late": 0, "slow": False, "mix_g": 0.0, "carts": {}, "loading": set(), "voices": [],
                   "air": False, "monitor": False, "listen": False, "cap_state": "off", "cap_err": "",
                   "src_dev": (prof.get("source") or {}).get("device", ""), "pm": {}, "pm_main": {}}
        d["in_peak"], d["peak"] = [-90.0, -90.0], [-90.0, -90.0]
        d["pid"] = slot.pid

    # --- état
    def __getattr__(self, k):
        s = self.__dict__.get("_s")
        if s is not None and k in s:
            h = self.__dict__["_hold"].get(k)
            if h and time.time() - h[1] < self.HOLD:
                return h[0]
            return s[k]
        raise AttributeError(k)

    def __setattr__(self, k, v):
        if k in self.SETTABLE:
            self._hold[k] = (v, time.time())
            self._s[k] = v
            self._send(("set", k, v))
        elif k == "outputs":
            keep = {id(o) for o in v}
            for o in list(self.outputs):
                if id(o) not in keep:
                    self.remove_output(o.cfg.get("id"))
        else:
            self.__dict__[k] = v

    def _send(self, m):
        if FX != self._fx:                         # traitement du son modifié dans l'interface : le moteur suit
            self.__dict__["_fx"] = json.loads(json.dumps(FX))
            self._raw_send(("fx", self._fx))
        self._raw_send(m)

    def _raw_send(self, m):
        try:
            with self._wlk:
                self._conn.send(m)
        except Exception as _ex:
            trace("_raw_send", _ex)

    def _reader(self):
        conn = self._conn
        while True:
            try:
                m = conn.recv()
            except Exception:
                break
            try:
                k = m[0]
                if k == "snap":
                    self._apply(m[1])
                elif k == "log":
                    self.log(m[1])
                elif k == "alert":
                    if self.alert:
                        self.alert(m[1], m[2])
                elif k == "outcfg":
                    self._outcfg(m[1])
                elif k == "counts":
                    self.__dict__["counts_in"] = m[1]
            except Exception as _ex:
                trace("_reader", _ex)
        s = self._s
        was = s.get("running")
        s["running"] = False
        self._slot.close()
        if was and not self._stopping and self._on_dead:
            self._on_dead(self)

    def _outcfg(self, cfgs):
        with self._lk:
            cur = {o.cfg.get("id"): o for o in self.outputs}
            new = []
            for c in cfgs:
                o = cur.get(c.get("id"))
                if o is None:
                    o = _OutProxy(self, c)
                else:
                    o.cfg = c
                new.append(o)
            self.__dict__["outputs"] = new

    def _apply(self, s):
        now = time.time()
        for i in (0, 1):
            self.in_peak[i] = max(self.in_peak[i], s["in_peak"][i])
            self.peak[i] = max(self.peak[i], s["peak"][i])
        st = dict(self._s)
        st.update(s)
        for k, (v, t0) in list(self._hold.items()):
            if now - t0 < self.HOLD and s.get(k) != v:
                st[k] = v
            elif now - t0 >= self.HOLD:
                self._hold.pop(k, None)
        for cid, t0 in list(self._pred_load.items()):
            if cid in s["carts"] or now - t0 > 1.5:
                self._pred_load.pop(cid, None)
        self.__dict__["_s"] = st
        self.cmon.label = s.get("cmon", self.cmon.label)
        by = {o.cfg.get("id"): o for o in self.outputs}
        for oid, state, detail, t_live in s["outs"]:
            o = by.get(oid)
            if o is None:
                continue
            h = self._hold_out.get(oid)
            if h and now - h < self.HOLD:
                continue
            self._hold_out.pop(oid, None)
            o.state, o.detail, o.t_live = state, detail, t_live

    def start(self):
        self.__dict__["_fx"] = json.loads(json.dumps(FX))
        self._raw_send(("start", self.prof, False, True, self._fx))
        threading.Thread(target=self._reader, daemon=True).start()

    def _hold_set(self, k, v):
        self._hold[k] = (v, time.time())
        self._s[k] = v

    def set_air(self, on, prof=None):
        """Antenne marche / arrêt : l'écran change tout de suite, le moteur suit (sans couper les cartouches)."""
        on = bool(on)
        with self._lk:
            if on:
                if prof is not None:
                    self.__dict__["prof"] = prof
                outs = []
                for c in self.prof.get("outputs", []):
                    o = _OutProxy(self, c)
                    if c.get("enabled", True):
                        o.state = "connecting"
                        self._hold_out[c.get("id")] = time.time()
                    outs.append(o)
                self.__dict__["outputs"] = outs
                for k, v in (("started", time.time()), ("backup", False), ("manual", False), ("pl_pause", False), ("pl_stop", False), ("mute", False), ("tone", False),
                             ("silent_ms", 0), ("loud_ms", 0), ("track", ""), ("pl_cur", None)):
                    self._s[k] = v
            else:
                self.__dict__["outputs"] = []
                for k in ("backup", "manual", "mute", "tone", "pl_pause", "pl_stop"):
                    self._hold_set(k, False)
            self._hold_set("air", on)
        self._call("set_air", on, prof if on else None)

    def set_monitor(self, on):
        self._hold_set("monitor", bool(on))
        self._call("set_monitor", bool(on))

    def set_listen(self, on):
        self._hold_set("listen", bool(on))
        self._call("set_listen", bool(on))

    def set_source(self, dev):
        self._hold_set("src_dev", dev or "")
        self.prof.setdefault("source", {})["device"] = dev or ""
        self._call("set_source", dev or "")

    def set_prof(self, prof):
        self.__dict__["prof"] = prof
        self._hold_set("src_dev", (prof.get("source") or {}).get("device", ""))
        self._call("set_prof", prof)

    def fb_params(self):
        return Engine.fb_params(self)

    def stop(self):
        self.__dict__["_stopping"] = True
        self._s["running"] = False
        for o in self.outputs:
            o.state, o.detail = "stopped", ""
        self._raw_send(("stop",))

        def bye(slot=self._slot):
            time.sleep(4)                          # le moteur ferme ses encodeurs proprement, puis s'en va
            slot.close()
        threading.Thread(target=bye, daemon=True).start()

    def alive(self):
        return self._slot.alive()

    # --- commandes
    def _call(self, name, *a, **kw):
        self._send(("call", name, a, kw))

    def output(self, oid):
        return next((o for o in self.outputs if o.cfg.get("id") == oid), None)

    def swap_output(self, cfg):
        with self._lk:
            old = self.output(cfg.get("id"))
            new = _OutProxy(self, cfg)
            if self.running and cfg.get("enabled", True):
                new.state = "connecting"
                self._hold_out[cfg.get("id")] = time.time()
            self.__dict__["outputs"] = [o for o in self.outputs if o is not old] + [new]
        self._call("swap_output", cfg)

    def remove_output(self, oid):
        with self._lk:
            self.__dict__["outputs"] = [o for o in self.outputs if o.cfg.get("id") != oid]
        self._call("remove_output", oid)

    def prof_update(self, section, **kw):
        _merge(self.prof.setdefault(section, {}), kw)
        if section == "fallback":
            self.__dict__["fb_ver"] = self.fb_ver + 1
        self._send(("prof", section, kw))

    def slow_now(self):
        return bool(self._s.get("slow"))

    def cart_status(self):
        s = self._s
        dt = max(0.0, time.time() - s["t"])
        out = {}
        sk = self.__dict__.get("_seek") or {}
        now = time.time()
        for cid, v in s["carts"].items():
            h = sk.get(cid)
            if h is not None and now - h[1] > .5:
                sk.pop(cid, None)
                h = None
            if h is not None:                                    # saut tout juste demandé : on part de la nouvelle position
                v = (h[0] + (0.0 if v[6] else now - h[1]),) + tuple(v[1:])
            elif not v[6]:                                       # en lecture (ou en fondu) : la position avance d'elle-même
                pos = v[0] + dt
                if not v[2]:
                    pos = min(pos, v[1])
                elif v[1] > 0:
                    pos = pos % v[1]
                v = (pos,) + tuple(v[1:])
            out[cid] = v
        return out, set(s["loading"]) | set(self._pred_load)

    @property
    def voices(self):
        return [{"id": i, "stopping": stp} for i, stp in self._s["voices"]]

    def cart_playing(self, cid):
        return any(i == cid and not stp for i, stp in self._s["voices"])

    def play_cart(self, cid, cart, pre=False, at=None):
        self._pred_load[cid] = time.time()
        self._call("play_cart", cid, cart, pre, at)

    def stop_cart(self, cid=None, fade=None):
        self._call("stop_cart", cid, fade)

    def pause_cart(self, cid=None, on=None):
        res = None
        carts = dict(self._s["carts"])
        for k, v in carts.items():
            if (cid is None or k == cid) and not v[4]:
                nv = (not v[6]) if on is None else bool(on)
                if res is None:
                    res = nv
                if cid is None and on is None:
                    nv = res
                carts[k] = tuple(v[:6]) + (nv,) + tuple(v[7:])
        self._s["carts"] = carts
        self._call("pause_cart", cid, on)
        return res

    def seek_cart(self, cid, sec):
        v = self._s["carts"].get(cid)
        if v is None or v[4]:
            return False
        # la tête affichée part tout de suite de la nouvelle position (les mesures du moteur encore en route sont ignorées
        # un court instant, sinon elle revenait en arrière avant de sauter)
        self.__dict__.setdefault("_seek", {})[cid] = (max(0.0, sec - (v[7] if len(v) > 7 else 0.0)), time.time())
        self._call("seek_cart", cid, sec)
        return True

    def set_cart_live(self, cid, **kw):
        self._call("set_cart_live", cid, **kw)

    def apply_fx(self):
        """Banques du processeur / bypass modifiés (FX) : envoyés tout de suite au moteur (appliqués au bloc suivant)."""
        self._send(("noop",))

    def set_processor(self, params=None, bypass=None, bank=None):
        if params is not None:
            FX.setdefault("banks", {})[bank or FX.get("edit") or "A"] = params
        if bypass is not None:
            FX["bypass"] = bool(bypass)
        self._send(("noop",))

    def set_out_fx(self, modes):
        for o in self.outputs:
            m = modes.get(o.cfg.get("id"))
            if m is not None:
                o.cfg["fx"] = m
        self._call("set_out_fx", modes)

    def set_manual(self, on):
        self._hold["manual"] = (bool(on), time.time())
        self._call("set_manual", on)

    def set_gain(self, db):
        self._call("set_gain", db)

    def set_delay(self, sec):
        self._call("set_delay", sec)

    def dump_delay(self):
        self._call("dump_delay")

    def play_now(self, path):
        self._hold["manual"] = (True, time.time())
        self._call("play_now", path)
