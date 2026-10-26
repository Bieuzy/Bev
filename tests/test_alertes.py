"""Alertes de panne : chaque panne d'une session est signalée (début et fin), au délai de la playlist de secours."""
import os
import shutil
import subprocess
import time

import pytest

import bev_core as bc

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")


def make_engine(tmp_path, playlist_src="sine=f=440:d=60", delay="1", rec="0.4"):
    f = str(tmp_path / "secours.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", playlist_src, "-ac", "2", f], check=True)
    prof = bc.default_profile()
    prof["source"] = {"device": ""}                    # pas d'entrée : silence (sauf tonalité de test)
    prof["outputs"] = []
    prof["fallback"].update(enabled=True, playlist=[f], silence_s=delay, threshold="-50", recover_s=rec)
    alerts = []
    e = bc.Engine(prof, lambda m: None, lambda text, key=None: alerts.append((round(time.time(), 1), key, text)))
    e.start()
    e.set_air(True)
    return e, alerts


def wait_for(alerts, key, n=1, timeout=12.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if sum(1 for a in alerts if a[1] == key) >= n:
            return True
        time.sleep(0.1)
    return False


@needs_ffmpeg
def test_plusieurs_silences_dans_la_meme_session(tmp_path):
    e, alerts = make_engine(tmp_path)
    try:
        for i in range(1, 4):                          # trois coupures d'affilée, à quelques secondes d'intervalle
            assert wait_for(alerts, "silence", i), alerts
            e.tone = True                              # le son revient
            assert wait_for(alerts, "silence-ok", i), alerts
            e.tone = False
        keys = [a[1] for a in alerts if a[1].startswith("silence")]
        assert keys == ["silence", "silence-ok"] * 3, keys
        assert "playlist de secours a pris le relais" in next(a[2] for a in alerts if a[1] == "silence")
    finally:
        e.set_air(False)
        e.stop()


@needs_ffmpeg
def test_silence_sans_secours_signale_quand_meme(tmp_path):
    e, alerts = make_engine(tmp_path)
    e.prof_update("fallback", enabled=False)
    try:
        assert wait_for(alerts, "silence"), alerts
        assert "désactivée" in next(a[2] for a in alerts if a[1] == "silence")
        assert not e.backup
    finally:
        e.set_air(False)
        e.stop()


@needs_ffmpeg
def test_playlist_de_secours_muette(tmp_path):
    e, alerts = make_engine(tmp_path, playlist_src="anullsrc=r=44100:cl=stereo:d=60")
    try:
        assert wait_for(alerts, "silence"), alerts
        assert wait_for(alerts, "fallback-silent", timeout=15), alerts
        e.tone = True                                  # le direct revient : fin du secours, fin du silence
        assert wait_for(alerts, "fallback-silent-ok", timeout=15), alerts
        assert wait_for(alerts, "silence-ok"), alerts
    finally:
        e.set_air(False)
        e.stop()


def test_sorties_une_alerte_par_panne(monkeypatch):
    e = bc.Engine(bc.default_profile(), lambda m: None)
    got = []
    e.alert = lambda text, key=None: got.append(key)
    e.air = True
    o = bc.Output({"id": "abcd1234", "type": "internet", "name": "Web", "enabled": True}, e)
    e.outputs = [o]
    p = e.fb_params()
    clock = [1000.0]
    monkeypatch.setattr(bc.time, "time", lambda: clock[0])

    def at(state, dt=1.0):
        o.state, o.detail = state, "refusé"
        clock[0] += dt
        e.watch_incidents(p, True, False)
    at("error")
    for _ in range(5):                                 # reconnexions intermittentes : toujours la même panne
        at("connecting")
        at("live", 3)
        at("error")
    assert got == ["out-abcd1234"]
    at("live")
    at("live", 20)                                     # 20 s stables en ligne : rétablie
    assert got == ["out-abcd1234", "out-abcd1234-ok"]
    at("error")                                        # 2e panne, juste après : signalée aussi
    at("live")
    at("live", 20)
    assert got == ["out-abcd1234", "out-abcd1234-ok"] * 2
    e.watch_incidents(p, False, False)                 # fin d'antenne : rien n'est « rétabli »
    assert e.inc == {}
