"""Tests du cœur de Bev (sans interface) : python -m pytest tests"""
import os
import shutil
import stat
import subprocess
import sys
import threading
import time

import pytest

import bev_core as bc

HAS_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg absent")


def test_redact_masque_les_mots_de_passe():
    assert bc.redact("Error opening output icecast://source:hackme@radio.bzh:8000/live") == \
        "Error opening output icecast://source:***@radio.bzh:8000/live"
    assert "SECRET" not in bc.redact("https://smsapi.free-mobile.fr/sendmsg?user=1&pass=SECRET&msg=x")
    assert bc.redact("Lecture choisie : morceau.mp3") == "Lecture choisie : morceau.mp3"


def test_reglages_illisibles_mis_de_cote(tmp_path, monkeypatch):
    conf = tmp_path / "bev.json"
    monkeypatch.setattr(bc, "CONF", str(conf))
    conf.write_text('{"profiles": {"Ma radio": {tronqué', encoding="utf-8")
    d = bc.load_data()
    assert list(d["profiles"]) == ["Défaut"]
    baks = [p for p in tmp_path.iterdir() if ".illisible-" in p.name]
    assert len(baks) == 1 and "Ma radio" in baks[0].read_text(encoding="utf-8")
    bc.save_data(d)
    assert bc.load_data()["profiles"].keys() == d["profiles"].keys()
    if os.name != "nt":
        assert stat.S_IMODE(conf.stat().st_mode) == 0o600


def test_purge_des_enregistrements(tmp_path):
    names = ["Pige_2026-01-01_10h.mp3", "Pige_2026-01-01_10h30.mp3", "2026-01-01_10h30.mp3", "Pige_2026-01-01_10h_2.flac",
             "Mon interview.mp3", "Pige_notes.txt", "Enregistrement.mp3"]
    old = time.time() - 40 * 86400
    for n in names:
        p = tmp_path / n
        p.write_bytes(b"")
        os.utime(p, (old, old))
    recent = tmp_path / "Pige_2026-10-01_10h.mp3"
    recent.write_bytes(b"")
    cfg = bc.new_output("record")
    cfg.update(folder=str(tmp_path), keep_days="30", prefix="Pige_", pige="1")

    class Eng:
        log = staticmethod(lambda m: None)
    bc.RecordOutput(cfg, Eng()).cleanup()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        ["Mon interview.mp3", "Pige_notes.txt", "Enregistrement.mp3", recent.name])


@pytest.mark.skipif(bc.np is None, reason="numpy absent")
def test_processeur_d_antenne():
    np = bc.np
    t = np.arange(882 * 150) / 44100
    sig = 0.5 * np.sin(2 * np.pi * 220 * t)
    pcm = (np.stack([sig, sig], 1) * 32767).astype("<i2").tobytes()
    for name in bc.PROC_ORDER:
        ap = bc.AirProcessor(bc.proc_params(name), False)
        outs, t0 = [], time.perf_counter()
        for i in range(0, len(pcm), bc.CH):
            o = ap.process(pcm[i:i + bc.CH])
            assert len(o) == bc.CH
            outs.append(o)
        per_block = (time.perf_counter() - t0) / len(outs)
        a = np.frombuffer(b"".join(outs), "<i2")
        assert per_block < 0.015, f"{name} : {per_block * 1000:.1f} ms par bloc de 20 ms"
        assert np.abs(a[-4410:]).max() > 3000, name


@needs_ffmpeg
def test_cache_des_cartouches_multi_fils(tmp_path):
    f = str(tmp_path / "a.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=300:d=2", "-ac", "2", f], check=True)
    e = bc.Engine(bc.default_profile(), lambda m: None)
    errs = []

    def w(i):
        try:
            for k in range(5):
                assert e.get_pcm(f, trim=(i + k) % 2, maxi=k % 2)
        except Exception as ex:
            errs.append(repr(ex))
    ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errs == []


@needs_ffmpeg
def test_antenne_silence_puis_secours_enregistre(tmp_path):
    tone = str(tmp_path / "tone.mp3")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=20", "-ac", "2", tone], check=True)
    prof = bc.default_profile()
    prof["source"] = {"device": ""}                         # aucune entrée : silence
    rec = bc.new_output("record")
    rec.update(folder=str(tmp_path / "rec"))
    prof["outputs"] = [rec]
    prof["fallback"].update(enabled=True, playlist=[tone], silence_s="1", threshold="-50")
    logs = []
    e = bc.Engine(prof, logs.append)
    e.start()
    try:
        e.set_air(True)
        deadline = time.time() + 15
        while time.time() < deadline and not (e.backup and e.track):
            time.sleep(0.2)
        time.sleep(2)
        assert e.backup and e.track == "tone", logs
        assert e.outputs[0].state == "live", logs
    finally:
        e.set_air(False)
        time.sleep(1.5)
        e.stop()
    files = list((tmp_path / "rec").iterdir())
    assert files and files[0].stat().st_size > 10000, logs


def test_fichier_express(tmp_path):
    """Le fichier express réunit tous les modules ; le moteur audio s'y lance sans charger Qt."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
    import express
    cwd = os.getcwd()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        text, ver, runtime, mods = express.build("v9.8.7", "compte/depot")
    finally:
        os.chdir(cwd)
    assert ver == "9.8.7" and 'UPDATE_REPO = "compte/depot"' in text
    assert not any(m.split(".")[0] in ("bev_core", "bev_assets") for m in mods)
    f = tmp_path / "bev-9.8.7.py"
    f.write_text(text, encoding="utf-8")
    probe = (
        "import sys; sys.argv.append('--bev-engine'); code = sys.argv[1]\n"
        "ns = {'__name__': '__bev_express__', '__file__': code, '_BEV_EXPRESS': code, '__builtins__': __builtins__}\n"
        "exec(compile(open(code, 'rb').read(), code, 'exec'), ns)\n"
        "assert callable(ns['_engine_worker_main'])\n"
        "assert not any(k.startswith('PySide6') for k in sys.modules), 'Qt chargé dans le moteur'\n"
        "print('ok')\n")
    for _ in range(2):                                  # 2e passage : depuis le cache de code compilé
        r = subprocess.run([sys.executable, "-I", "-c", probe, str(f)], capture_output=True, text=True, timeout=60)
        assert r.stdout.strip() == "ok", r.stderr
    assert any(n.startswith("bev_core-") for n in os.listdir(tmp_path / "cache"))
