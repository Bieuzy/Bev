"""Tests de l'interface (nécessitent PySide6 ; ignorés sinon)."""
import threading

import pytest

pytest.importorskip("PySide6")
import broadcast_tool_qt as bev  # noqa: E402


def test_gael_historique_apres_panne():
    class Bridge:
        class call:
            @staticmethod
            def emit(fn):
                fn()

    class G(bev.GaelLLM):
        def __init__(s):
            s.app = type("A", (), {"bridge": Bridge, "data": {"settings": {"gael_key": "k"}}})()
            s.bot = type("B", (), {})()
            s.l_st = type("L", (), {"setText": lambda *a: None})()
            s.calls, s.done, s.failed = 0, threading.Event(), None

        def llm_state(s):
            return "état"

        def stream_bubble(s):
            return None

        def on_ui(s, fn):
            return fn()

        def llm_tool(s, n, i):
            return "ok"

        def llm_done(s, b):
            s.done.set()

        def llm_fail(s, q, msg, b):
            s.failed = msg
            s.done.set()

        def llm_call(s, *a):
            s.calls += 1
            if s.calls == 1:
                return [{"type": "tool_use", "id": "t1", "name": "get_state", "input": {}}], "tool_use"
            raise RuntimeError("coupure réseau")
    g = G()
    g.llm_ask("quel est l'état ?")
    assert g.done.wait(5) and g.failed == "coupure réseau"
    assert g.history == []


def test_alertes_chaque_panne_et_nouvel_essai(monkeypatch):
    """Deux pannes coup sur coup : deux messages ; un envoi raté (Internet coupé) est retenté puis arrive."""
    import time as _t

    class App:
        data = {"alerts": {"url": "https://exemple.invalid/hook", "kind": "Discord", "mail_on": True, "mail_to": "a@b.c",
                           "sms_on": False, "sound": False}}
        logs = []

        def log(self, m):
            self.logs.append(m)

        def ui(self, fn, *a):
            pass
    monkeypatch.setattr(bev.Alerts, "RETRY_S", 0.2)
    a = bev.Alerts(App())
    fails = {"n": 2}

    def post(kind, url, text):
        if fails["n"] > 0:                         # les 2 premiers essais échouent
            fails["n"] -= 1
            return False
        return True
    a.post = post
    a.mail = lambda text: True
    for _ in range(2):
        a.send("Pas de son en entrée depuis 10 s", "silence")
        a.send("Le son est revenu en entrée", "silence-ok")
    t0 = _t.time()
    while _t.time() - t0 < 10 and sum(1 for s in a.sent if s[1] == "msg" and s[3]) < 4:
        _t.sleep(0.1)
    msgs = [s for s in a.sent if s[1] == "msg" and s[3]]
    mails = [s for s in a.sent if s[1] == "mail" and s[3]]
    assert len(msgs) == 4, a.sent                  # aucune panne perdue, malgré les échecs
    assert len(mails) == 4, a.sent                 # silence : aussi par mail (urgent)
    a.send("flux en erreur", "out-net-down")
    a.send("flux en erreur", "out-net-down")       # alerte ordinaire répétée : toujours filtrée 2 min
    _t.sleep(1.5)
    assert sum(1 for s in a.sent if "flux en erreur" in s[2]) == 1
