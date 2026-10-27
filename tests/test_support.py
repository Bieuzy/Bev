"""Prise en main et support : « Prêt pour l'antenne ? », guide, rapport « Signaler un problème », erreurs et plantages."""
import os
import sys
import time

import pytest

import bev_core as bc


def _boom():
    return {"a": 1}["b"]


def test_trace_exc_pile_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "TRACE_FILE", str(tmp_path / "bev-erreurs.log"))
    res = []
    for _ in range(2):
        try:
            _boom()
        except KeyError:
            res.append(bc.trace_exc("essai", *sys.exc_info()))
    assert res[0] and res[0].startswith("KeyError") and "test_support.py" in res[0]
    assert res[1] is None                                            # même erreur au même endroit : une fois par minute
    txt = (tmp_path / "bev-erreurs.log").read_text(encoding="utf-8")
    assert "ERREUR NON RATTRAPÉE" in txt and "Traceback" in txt and '["b"]' in txt


def test_plantage_precedent(tmp_path, monkeypatch):
    f = tmp_path / "bev-plantage.log"
    monkeypatch.setattr(bc, "CRASH_FILE", str(f))
    monkeypatch.setattr(bc, "_CRASH_FH", [])
    assert bc.crash_watch() == ""                                   # rien avant : rien à signaler
    for fh in bc._CRASH_FH:
        fh.close()
    import faulthandler
    faulthandler.disable()
    f.write_text("Fatal Python error: Segmentation fault\n  File bev_ui.py, line 42\n", encoding="utf-8")
    prev = bc.crash_watch()
    assert "Segmentation fault" in prev
    assert (tmp_path / "bev-plantage-precedent.log").exists() and f.stat().st_size == 0
    for fh in bc._CRASH_FH:
        fh.close()
    faulthandler.disable()


bev = pytest.importorskip("broadcast_tool_qt")


def test_scrub_retire_le_personnel():
    home = os.path.expanduser("~")
    t = bev.scrub(f"icecast://source:hackme@radio.bzh:8000/live · mail à contact@rbg.bzh · SMS 06 12 34 56 78 · "
                  f"+33612345678 · https://discord.com/api/webhooks/123/abc · {os.path.join(home, 'Musique', 'a.mp3')} · "
                  "Python 3.12.4 · 192.168.1.20:8765 · 2026-10-27 10:41:00")
    for secret in ("hackme", "contact@rbg.bzh", "06 12 34 56 78", "+33612345678", "webhooks/123/abc", home):
        assert secret not in t, secret
    assert "radio.bzh:8000" in t and "3.12.4" in t and "192.168.1.20:8765" in t and "2026-10-27 10:41:00" in t


@pytest.fixture(scope="module")
def win(tmp_path_factory):
    from PySide6.QtWidgets import QApplication
    home = tmp_path_factory.mktemp("home")
    old = os.environ.get("HOME"), os.environ.get("USERPROFILE"), bc.CONF
    os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
    bc.CONF = str(home / ".broadcast_tool.json")      # jamais les vrais réglages de la radio (tests lancés sur son poste)
    bc.WIN_SOUNDS_BAK = str(home / "sons-windows.json")  # ni les sons de Windows de ce poste
    app = QApplication.instance() or QApplication([sys.argv[0]])
    w = bev.MainWindow()
    w.resize(1366, 768)
    w.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    yield w
    w._closing = True
    try:
        w.close()                                     # (moteur audio arrêté : rien ne tourne pendant les tests suivants)
    except Exception:
        w.hide()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    os.environ["HOME"], os.environ["USERPROFILE"] = old[0] or "", old[1] or ""
    bc.CONF = old[2]


def test_pret_pour_l_antenne(win):
    keys = {r[1]: r[0] for r in win.readiness()}
    assert keys.get("flux") == "bloque"                               # réglages neufs : aucun flux
    assert keys.get("secours-off") == "conseil"
    assert not win.ready_check(ask=False)                            # démarrage automatique : rien ne s'ouvre, rien ne part
    assert any("Démarrage automatique impossible" in l for l in win.log_lines)
    out = bev.new_output("internet")
    out.update(name="Internet", host="radio.bzh", password="")
    win.outputs_cfg.append(out)
    keys = {r[1]: r[0] for r in win.readiness()}
    assert "flux" not in keys and keys.get("mdp") == "bloque"
    out["password"] = "hackme"
    keys = {r[1]: r[0] for r in win.readiness()}
    assert "mdp" not in keys
    win.outputs_cfg.remove(out)


def test_rapport_de_support_sans_donnees_personnelles(win):
    out = bev.new_output("internet")
    out.update(name="Radio Internet", host="stream.radio.bzh", port="8000", password="hackme-SECRET")
    win.outputs_cfg.append(out)
    win.collect_profile()
    win.data["profiles"][win.data["last"]] = win.prof
    win.data["alerts"].update(mail_to="tresorier@rbg.bzh", mail_pw="mdp-mail", sms_to="0612345678", sms_key="cle-sms",
                              url="https://discord.com/api/webhooks/99/xyz", mail_on=True)
    win.data.setdefault("settings", {})["gael_key"] = "sk-ant-SECRET"
    win.log("Mail d'alerte envoyé à tresorier@rbg.bzh")
    r = win.support_report("Le flux s'est coupé à 10 h, appelez-moi au 06 12 34 56 78")
    for secret in ("hackme-SECRET", "tresorier@rbg.bzh", "mdp-mail", "0612345678", "06 12 34 56 78", "cle-sms",
                   "webhooks/99/xyz", "sk-ant-SECRET"):
        assert secret not in r, secret
    for useful in ("=== Rapport Bev", "Le flux s'est coupé à 10 h", "stream.radio.bzh:8000", "mot de passe renseigné",
                   "Alertes : mail, message", "Journal d'antenne", "Prêt pour l'antenne"):
        assert useful in r, useful
    win.outputs_cfg.remove(out)


def test_guide_premier_lancement(win):
    S = win.data.setdefault("settings", {})
    S.pop("guide_done", None)
    win.guide_start()
    assert getattr(win, "_guide_on", False) and win._upd_mode == "guide"
    first = win.upd_bubble.t.text()
    assert "étape" in first.lower()
    win.guide_stop(done=True)
    assert S.get("guide_done") and win.upd_bubble is None
    win.guide_start()                                                 # « Ne plus afficher » : plus jamais de guide
    assert not getattr(win, "_guide_on", False)


# ------------------------------------------------------------------ sons de Windows (registre simulé)
class _FakeWinreg:
    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ, REG_EXPAND_SZ = 1, 2, 1, 2

    def __init__(self):
        self.vals = {r"AppEvents\Schemes": (".Default", 1),
                     r"AppEvents\Schemes\Apps\.Default\SystemAsterisk\.Current": (r"%SystemRoot%\media\Windows Background.wav", 2),
                     r"AppEvents\Schemes\Apps\.Default\Notification.Default\.Current": (r"C:\Sons\ding.wav", 1)}

    class _K:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, base, path, *a):
        if not isinstance(base, int):
            path = base.path + "\\" + path
        if not any(k == path or k.startswith(path + "\\") for k in self.vals):
            raise OSError(path)
        return self._K(path)

    def EnumKey(self, k, i):
        kids = sorted({p[len(k.path) + 1:].split("\\")[0] for p in self.vals if p.startswith(k.path + "\\")})
        if i >= len(kids):
            raise OSError("fin")
        return kids[i]

    def QueryValueEx(self, k, name):
        if k.path not in self.vals:
            raise OSError(k.path)
        return self.vals[k.path]

    def SetValueEx(self, k, name, _r, typ, val):
        self.vals[k.path] = (val, typ)


def test_sons_windows_coupes_puis_retablis(tmp_path, monkeypatch):
    fake = _FakeWinreg()
    before = dict(fake.vals)
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(bc, "SYS", "Windows")
    monkeypatch.setattr(bc, "WIN_SOUNDS_BAK", str(tmp_path / "sons-windows.json"))
    assert bc.win_sounds_mute()
    ev = [v for k, v in fake.vals.items() if k.endswith(".Current")]
    assert ev and all(v[0] == "" for v in ev) and fake.vals[r"AppEvents\Schemes"][0] == ".None"
    assert bc.win_sounds_mute()                       # deuxième coupure (après un plantage) : la sauvegarde d'origine reste
    assert bc.win_sounds_restore()
    assert fake.vals == before                        # tout revient exactement (type REG_EXPAND_SZ compris)
    assert not (tmp_path / "sons-windows.json").exists()
    assert not bc.win_sounds_restore()                # rien à rétablir


# ------------------------------------------------------------------ voyant « Prévenir en cas de panne »
def test_voyant_vert_seulement_apres_un_envoi_reussi(win):
    a = win.alerts
    win.data["alerts"].update(mail_on=True, mail_to="radio@exemple.bzh", mail_host="smtp.exemple.bzh", url="", sms_on=False)
    win.data["alerts"].pop("verified", None)
    win.alert_summary()
    assert a.chan_status("mail") == "a_tester" and "envoie un test" in win.al_head.text()
    assert not win.al_phone.ok                        # pas de téléphone « vert » sans preuve
    win.alert_result("mail", False, True)             # le test échoue
    assert a.chan_status("mail") == "echec" and "échoué" in win.al_head.text() and not win.al_phone.ok
    win.alert_result("mail", True, True)              # le test réussit
    assert a.chan_status("mail") == "ok" and win.al_phone.ok and "Tu seras prévenu" in win.al_head.text()
    win.data["alerts"]["mail_host"] = "smtp.autre.bzh"   # réglages modifiés : il faut retester
    win.alert_summary()
    assert a.chan_status("mail") == "a_tester" and not win.al_phone.ok
    win.data["alerts"].update(mail_on=False)
    win.alert_summary()


def test_alertes_reseau_allegees(win, monkeypatch):
    sent = []
    monkeypatch.setattr(win.alerts, "send", lambda text, key=None, **k: sent.append(key))
    now = [1000.0]
    monkeypatch.setattr(bev.time, "time", lambda: now[0])
    win._net_bad_since, win._net_alert_t = None, {}
    for _ in range(10):                              # Wi-Fi faible pendant 4 min : rien ne part
        win.net_alert("Internet : Wi-Fi faible", "out-net-down")
        now[0] += 24
    assert sent == []
    now[0] += 120                                    # au-delà de 5 min : un message
    win.net_alert("Internet : Wi-Fi faible", "out-net-down")
    assert sent == ["out-net-down"]
    for _ in range(20):                              # puis plus rien pendant une heure
        now[0] += 60
        win.net_alert("Internet : Wi-Fi faible", "out-net-down")
    assert sent == ["out-net-down"]


def test_animations_de_gael():
    names = [a.name for a in bev.G_ANIMS]
    assert "casque" not in names
    for n in ("goeland", "bagad", "mixage", "fierte", "antenne"):
        assert n in names
    from PySide6.QtGui import QImage, QPainter
    gp = bev.GaelPainter()
    img = QImage(300, 300, QImage.Format.Format_ARGB32)
    for a in bev.G_ANIMS:                            # chaque animation se dessine du début à la fin sans erreur
        for i in range(12):
            t = a.dur * i / 11
            p = QPainter(img)
            p.translate(150, 260)
            P = a.pose(t, dict(bev.POSE0))
            a.back(p, t, gp, P)
            gp.draw(p, P, t=t, hand_r=a.hand_r(t), hand_l=a.hand_l(t))
            a.front(p, t, gp, P)
            p.end()


def test_minutage_secours_et_rupture(win, monkeypatch):
    class Out:
        def __init__(s, oid, state):
            s.cfg, s.state = {"id": oid, "name": "Internet", "enabled": True}, state

    class Eng:
        running, air, monitor, mute, silent_ms, backup = True, True, False, False, 0, True
        outputs = []

        def fb_params(s):
            return {"enabled": True, "files": ["a.mp3"], "delay": 10000}
    e = Eng()
    old = win.engine
    now = [10_000.0]
    monkeypatch.setattr(bev.time, "time", lambda: now[0])
    try:
        win.engine = e
        win.alert_kind, win._out_down, win._alert_since = None, {}, None
        win.rupture_ui(e, 1, 1)
        assert win.banner.text().startswith("PLAYLIST DE SECOURS À L'ANTENNE depuis")
        now[0] += 192
        win.rupture_ui(e, 1, 1)
        assert "(3 min 12 s)" in win.banner.text()
        e.backup = False
        e.outputs = [Out("o1", "error")]
        win.rupture_ui(e, 0, 1)                      # le flux vient de tomber : pas encore une rupture (6 à 15 s)
        assert any("Fin de la playlist de secours" in l and "(3 min 12 s)" in l for l in win.log_lines)
        now[0] += 20
        win.rupture_ui(e, 0, 1)
        assert win.banner.text().startswith("⚠  RUPTURE DE FLUX depuis") and "(20 s)" in win.banner.text()
        e.outputs[0].state = "live"
        now[0] += 40
        win.rupture_ui(e, 1, 1)
        assert any("Antenne rétablie : rupture de flux de" in l and "(1 min 00 s)" in l for l in win.log_lines)
    finally:
        win.engine = old
        win.alert_kind = None
        win.centralWidget().set_border(None)
        win.banner.setVisible(False)
