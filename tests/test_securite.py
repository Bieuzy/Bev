"""Sécurité et solidité (1.2.1) : signature des mises à jour, secrets du fichier de réglages, code secret de l'automate,
reconnexion d'un flux Internet après une coupure du serveur."""
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time

import pytest

import bev_core as bc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------ signature Ed25519
def test_ed25519_vecteurs_officiels():
    """Vecteurs de test de la RFC 8032 (section 7.1) : l'implémentation est conforme au standard."""
    cases = [
        ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
         "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
         "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
        ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
         "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
         "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ]
    for sk, pk, msg, sig in cases:
        sk, pk, msg, sig = (bytes.fromhex(x) for x in (sk, pk, msg, sig))
        assert bc.ed25519_public(sk) == pk
        assert bc.ed25519_sign(sk, msg) == sig
        assert bc.ed25519_verify(pk, msg, sig)
        assert not bc.ed25519_verify(pk, msg + b"!", sig)
        bad = bytearray(sig)
        bad[5] ^= 1
        assert not bc.ed25519_verify(pk, msg, bytes(bad))
    assert not bc.ed25519_verify(b"court", b"", b"\0" * 64)


def _release(raw, sig=None):
    files = {"https://x/bev-maj.json": raw}
    assets = [{"name": "bev-maj.json", "browser_download_url": "https://x/bev-maj.json"}]
    if sig is not None:
        files["https://x/bev-maj.json.sig"] = sig
        assets.append({"name": "bev-maj.json.sig", "browser_download_url": "https://x/bev-maj.json.sig"})
    return assets, files.__getitem__


def test_manifeste_signe():
    bev = pytest.importorskip("broadcast_tool_qt")
    seed = bytes(range(32))
    pub = bc.ed25519_public(seed).hex()
    raw = json.dumps({"app": "Bev", "version": "9.9.9", "sha256": "0" * 64}).encode()
    good = bc.ed25519_sign(seed, raw).hex().encode()
    # sans clé publique dans Bev : comportement d'avant (lu sans contrôle d'auteur)
    man, why = bev.signed_manifest(*_release(raw), pubkey="")
    assert why is None and man["version"] == "9.9.9"
    # avec la clé : signature obligatoire et valide
    assert bev.signed_manifest(*_release(raw), pubkey=pub) == (None, "version pas encore signée par l'auteur")
    man, why = bev.signed_manifest(*_release(raw, good), pubkey=pub)
    assert why is None and man["version"] == "9.9.9"
    pirate = raw.replace(b"9.9.9", b"6.6.6")                 # manifeste modifié après signature
    man, why = bev.signed_manifest(*_release(pirate, good), pubkey=pub)
    assert man is None and "signature invalide" in why
    autre = bc.ed25519_sign(bytes(32), raw).hex().encode()    # signé par une autre clé
    assert bev.signed_manifest(*_release(raw, autre), pubkey=pub)[0] is None
    assert bev.signed_manifest(*_release(raw, b"pas-de-l-hexa"), pubkey=pub)[0] is None


def test_outil_de_signature(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import signer
    monkeypatch.setattr(signer, "KEY_DIR", str(tmp_path / "cle"))
    monkeypatch.setattr(signer, "KEY_FILE", str(tmp_path / "cle" / "cle-privee.txt"))
    signer.cmd_key()
    seed = signer.load_key()
    first = (tmp_path / "cle" / "cle-privee.txt").read_text()
    signer.cmd_key()                                          # une clé existante n'est jamais remplacée
    assert (tmp_path / "cle" / "cle-privee.txt").read_text() == first
    m = tmp_path / "bev-maj.json"
    m.write_text(json.dumps({"app": "Bev", "version": "1.2.3", "file": "bev-1.2.3.py", "sha256": "a" * 64,
                             "installers": {"Bev-Setup-1.2.3.exe": "b" * 64}}), encoding="utf-8")
    signer.cmd_sign(str(m))
    sig = bytes.fromhex((tmp_path / "bev-maj.json.sig").read_text().strip())
    assert bc.ed25519_verify(bc.ed25519_public(seed), m.read_bytes(), sig)
    (tmp_path / "autre.json").write_text('{"app": "Autre"}', encoding="utf-8")
    with pytest.raises(SystemExit):
        signer.cmd_sign(str(tmp_path / "autre.json"))


def test_manifeste_contient_les_installateurs(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import express
    for f in os.listdir(ROOT):
        if f.endswith(".py") and (f.startswith("bev_") or f == "broadcast_tool_qt.py"):
            shutil.copy(os.path.join(ROOT, f), tmp_path / f)
    (tmp_path / "dist-installers").mkdir()
    (tmp_path / "dist-installers" / "Bev-Setup-1.2.3.exe").write_bytes(b"installateur")
    (tmp_path / "dist-installers" / "selftest.txt").write_text("ok")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TAG", "v1.2.3")
    monkeypatch.setenv("REPO", "Bieuzy/Bev")
    assert express.main() == 0
    man = json.loads((tmp_path / "dist-express" / "bev-maj.json").read_text(encoding="utf-8"))
    assert man["installers"] == {"Bev-Setup-1.2.3.exe": __import__("hashlib").sha256(b"installateur").hexdigest()}


# ------------------------------------------------------------------ secrets du fichier de réglages
def _fake_dpapi(data, protect):
    """DPAPI simulé (les tests tournent sous Linux) : réversible, et refuse ce qui n'a pas été chiffré « ici »."""
    if protect:
        return b"ICI" + data[::-1]
    if not data.startswith(b"ICI"):
        raise OSError("autre ordinateur")
    return data[3:][::-1]


def test_secrets_chiffres_et_relus(tmp_path, monkeypatch):
    conf = tmp_path / "bev.json"
    monkeypatch.setattr(bc, "CONF", str(conf))
    monkeypatch.setattr(bc, "_dpapi", _fake_dpapi)
    monkeypatch.setattr(bc, "_protect_on", lambda: True)
    monkeypatch.setattr(bc, "SECRETS_LOST", [])
    d = bc.load_data()
    out = bc.new_output("internet")
    out["password"] = "hackme-é"
    d["profiles"]["Défaut"]["outputs"] = [out]
    d["settings"] = {"gael_key": "sk-ant-123", "station": "Radio Bro Gwened"}
    d["alerts"] = {"mail_pw": "mdp", "sms_key": "cle", "url": "https://discord.com/api/webhooks/1/abc", "mail_to": "a@b.c"}
    bc.save_data(d)
    txt = conf.read_text(encoding="utf-8")
    for secret in ("hackme", "sk-ant-123", '"mdp"', '"cle"', "webhooks/1/abc"):
        assert secret not in txt, secret
    assert "Radio Bro Gwened" in txt and "a@b.c" in txt          # le reste reste lisible
    assert d["settings"]["gael_key"] == "sk-ant-123"            # la copie en mémoire n'est pas touchée
    back = bc.load_data()
    assert back["profiles"]["Défaut"]["outputs"][0]["password"] == "hackme-é"
    assert back["settings"]["gael_key"] == "sk-ant-123"
    assert back["alerts"] == d["alerts"]
    assert bc.SECRETS_LOST == []
    # fichier copié sur un autre ordinateur : secrets vidés (pas de texte chiffré envoyé au serveur), et signalés
    monkeypatch.setattr(bc, "_dpapi", lambda data, protect: (_ for _ in ()).throw(OSError("autre PC")))
    other = bc.load_data()
    assert other["profiles"]["Défaut"]["outputs"][0]["password"] == ""
    assert "alerts.mail_pw" in bc.SECRETS_LOST


def test_secrets_en_clair_hors_application_installee(tmp_path, monkeypatch):
    """Depuis le code source (ou une version express sur une version installée plus ancienne) : rien n'est chiffré,
    pour qu'une version installée plus ancienne relise toujours le même fichier."""
    conf = tmp_path / "bev.json"
    monkeypatch.setattr(bc, "CONF", str(conf))
    monkeypatch.setattr(bc, "_dpapi", _fake_dpapi)
    d = bc.load_data()
    d["settings"] = {"gael_key": "sk-ant-123"}
    bc.save_data(d)
    assert "sk-ant-123" in conf.read_text(encoding="utf-8")
    assert not bc._protect_on()


# ------------------------------------------------------------------ automate : code secret et navigateurs
def _ask(a, ip, path, headers=()):
    s1, s2 = socket.socketpair()
    req = f"GET {path} HTTP/1.1\r\nHost: x\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers) + "\r\n"
    s1.sendall(req.encode())
    t = threading.Thread(target=a._client, args=(s2, ip, True))
    t.start()
    t.join(5)
    data = s1.recv(4096).decode("utf-8", "replace")
    s1.close()
    return data.split("\r\n", 1)[0], data.rsplit("\r\n\r\n", 1)[-1]


def test_automate_code_secret(tmp_path):
    got = []
    a = bc.AutomateMeta(got.append)
    try:
        a.cfg = {"on": True, "net": True, "token": "s3cret", "lan_token": True}
        q = "?artist=Tri%20Yann&title=Kalonkadour"
        st, _ = _ask(a, "192.168.1.20", "/" + q)                          # autre poste, sans code
        assert "403" in st and not got
        st, _ = _ask(a, "192.168.1.20", "/" + q + "&token=faux")
        assert "403" in st and not got
        st, body = _ask(a, "192.168.1.20", "/" + q + "&token=s3cret")
        assert "200" in st and got[-1]["title"] == "Kalonkadour", body
        st, _ = _ask(a, "127.0.0.1", "/?title=Page%20web", [("Origin", "https://site.example"), ("Sec-Fetch-Site", "cross-site")])
        assert "403" in st and got[-1]["title"] == "Kalonkadour"         # une page web ne change pas le titre
        st, _ = _ask(a, "127.0.0.1", "/?title=Automate%20local")          # automate sur ce PC : comme avant
        assert "200" in st and got[-1]["title"] == "Automate local"
        a.cfg["lan_token"] = False                                        # réglage d'avant la 1.2.1 conservé
        st, _ = _ask(a, "192.168.1.30", "/?title=Ancien%20reglage")
        assert "200" in st and got[-1]["title"] == "Ancien reglage"
        st, _ = _ask(a, "8.8.8.8", "/?title=Internet&token=s3cret")      # hors réseau local : toujours refusé
        assert "403" in st
    finally:
        a.stop()


def test_automate_pochette_locale_refusee_depuis_un_autre_poste(tmp_path):
    img = tmp_path / "secret.png"
    img.write_bytes(b"x")
    a = bc.AutomateMeta(lambda i: None)
    try:
        assert a.fetch_cover(str(img)) == str(img)
        assert a.fetch_cover(str(img), local_ok=False) == ""
    finally:
        a.stop()


# ------------------------------------------------------------------ SMS Free Mobile
def test_sms_adresse_personnalisee(monkeypatch):
    bev = pytest.importorskip("broadcast_tool_qt")
    urls = []

    class R:
        def read(self):
            return b""
    monkeypatch.setattr(bev.urllib.request, "urlopen", lambda req, timeout=0: (urls.append(req.full_url), R())[1])

    class App:
        data = {"alerts": {"sms_user": "123", "sms_key": "k", "sms_to": "06", "sms_url": "https://relais.example/sms"}}
        log = staticmethod(lambda m: None)
        ui = staticmethod(lambda *a: None)
    a = bev.Alerts(App())
    assert a.sms("Panne")
    assert urls[-1].startswith("https://relais.example/sms?") and "user=123" in urls[-1] and "pass=k" in urls[-1]
    App.data["alerts"]["sms_url"] = ""
    assert a.sms("Panne")
    assert urls[-1].startswith("https://smsapi.free-mobile.fr/sendmsg?user=123")


# ------------------------------------------------------------------ reconnexion d'un flux Internet
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")
def test_flux_internet_se_reconnecte(tmp_path):
    """Le serveur Icecast coupe la connexion : Bev se reconnecte tout seul, avec le bon mot de passe, et repasse en direct."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)
    port = srv.getsockname()[1]
    conns, auths = [], []

    def server():
        while len(conns) < 2:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            conns.append(c)
            c.settimeout(10)
            head = b""
            while b"\r\n\r\n" not in head:
                part = c.recv(4096)
                if not part:
                    break
                head += part
            for ln in head.decode("latin-1").split("\r\n"):
                if ln.lower().startswith("authorization: basic "):
                    auths.append(base64.b64decode(ln.split()[-1]).decode())
            c.sendall(b"HTTP/1.1 200 OK\r\n\r\n")
            t_end = time.time() + (2.5 if len(conns) == 1 else 30)
            while time.time() < t_end:
                try:
                    if not c.recv(65536):
                        break
                except OSError:
                    break
            if len(conns) == 1:
                c.close()                                          # coupure côté serveur
    threading.Thread(target=server, daemon=True).start()
    tone = str(tmp_path / "tone.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=f=440:d=60", "-ac", "2", tone], check=True)
    prof = bc.default_profile()
    prof["source"] = {"device": ""}
    out = bc.new_output("internet")
    out.update(host="127.0.0.1", port=str(port), mount="/live", password="hackme", format="MP3", bitrate="64")
    prof["outputs"] = [out]
    prof["fallback"].update(enabled=True, playlist=[tone], silence_s="1", threshold="-50")
    logs = []
    e = bc.Engine(prof, logs.append)
    e.start()
    try:
        e.set_air(True)
        deadline = time.time() + 30
        while time.time() < deadline and not (len(conns) >= 2 and e.outputs[0].state == "live"):
            time.sleep(0.2)
        assert len(conns) >= 2, logs                               # reconnecté après la coupure
        assert e.outputs[0].state == "live", logs
        assert auths and set(auths) == {"source:hackme"}, auths
        assert not any("hackme" in str(m) for m in logs), logs     # mot de passe jamais dans le journal
    finally:
        e.set_air(False)
        time.sleep(1)
        e.stop()
        srv.close()
        for c in conns:
            try:
                c.close()
            except OSError:
                pass
