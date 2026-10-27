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
