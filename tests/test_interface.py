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
