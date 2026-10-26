"""Titre en cours reçu d'un automate de diffusion (fichier ou réseau)."""
import json
import os
import socket
import threading
import time
import urllib.parse
import urllib.request

import bev_core as bc


def test_formats():
    p = bc.auto_parse
    assert p("Alan Stivell - Tri Martolod") == {"artist": "Alan Stivell", "title": "Tri Martolod", "album": "", "cover": ""}
    assert p(b"\xef\xbb\xbfDenez Prigent \xe2\x80\x93 Gortoz a ran\r\n")["title"] == "Gortoz a ran"
    assert p("Jingle station")["title"] == "Jingle station"
    js = p(json.dumps({"now": {"Artist": "Nolwenn Leroy", "Title": "Brest", "artwork": "https://x/y.jpg"}}))
    assert (js["artist"], js["title"], js["cover"]) == ("Nolwenn Leroy", "Brest", "https://x/y.jpg")
    x = p("<nowplaying><artist>Tri Yann</artist><title>La Jument de Michao</title><album>Best of</album></nowplaying>")
    assert (x["artist"], x["title"], x["album"]) == ("Tri Yann", "La Jument de Michao", "Best of")
    a = p('<Song title="Ar Soudarded" artist="Dan Ar Braz"/>')
    assert (a["artist"], a["title"]) == ("Dan Ar Braz", "Ar Soudarded")
    q = p("artist=Gilles%20Servat&title=La%20blanche%20hermine")
    assert (q["artist"], q["title"]) == ("Gilles Servat", "La blanche hermine")
    assert bc.auto_text({"artist": "A", "title": "B"}) == "A - B"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_fichier_et_reseau(tmp_path):
    got = []
    ev = threading.Event()
    a = bc.AutomateMeta(lambda info: (got.append(info), ev.set()))
    try:
        cover = tmp_path / "pochette.png"
        cover.write_bytes(b"\x89PNG fausse image")
        f = tmp_path / "nowplaying.txt"
        f.write_text("Alan Stivell - Brian Boru", encoding="utf-8")
        port = free_port()
        a.configure({"on": True, "file": str(f), "net": True, "port": port})
        assert ev.wait(5), "fichier non lu"
        assert got[-1]["text"] == "Alan Stivell - Brian Boru" and got[-1]["source"] == "fichier"
        ev.clear()
        f.write_text('{"artist": "Tri Yann", "title": "Les Prisons de Nantes", "cover": "pochette.png"}', encoding="utf-8")
        assert ev.wait(5)
        assert got[-1]["cover"] == str(cover)                # pochette relative au fichier de l'automate
        ev.clear()
        q = urllib.parse.urlencode({"artist": "Denez", "title": "Gortoz a ran"})
        for _ in range(20):
            try:
                r = urllib.request.urlopen(f"http://127.0.0.1:{port}/?{q}", timeout=3).read().decode()
                break
            except OSError:
                time.sleep(0.1)
        assert r.startswith("ok"), r
        assert ev.wait(3) and got[-1]["text"] == "Denez - Gortoz a ran" and got[-1]["source"] == "réseau"
        ev.clear()
        rq = urllib.request.Request(f"http://127.0.0.1:{port}/", data=json.dumps({"title": "Ar Men"}).encode(),
                                    headers={"Content-Type": "application/json"})
        assert urllib.request.urlopen(rq, timeout=3).read().decode().startswith("ok")
        assert ev.wait(3) and got[-1]["title"] == "Ar Men"
        n = len(got)
        urllib.request.urlopen(rq, timeout=3).read()        # même titre : pas de doublon
        time.sleep(0.3)
        assert len(got) == n
    finally:
        a.stop()
