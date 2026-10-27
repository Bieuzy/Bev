# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - annuler / rétablir, bulles et bandeaux de la fenêtre principale, petits widgets d'en-tête."""
from bev_sos import *  # noqa: F401,F403

# ------------------------------------------------------------------ Annuler / rétablir (Ctrl+Z / Ctrl+Y)
# L'historique suit la configuration (flux, playlist et dossiers du secours, cartoucheur, alertes, monitoring…) :
# toutes les 0,6 s on compare un instantané léger ; chaque changement devient une étape annulable.
# Les opérations sur les fichiers d'enregistrement (corbeille, déplacement, renommage) sont aussi annulables.
class Toast(QLabel):
    """Petit message flottant en bas de la fenêtre (« Annulé : … »)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet(f"background:{mixc(PANEL, TXT, .12).name()};color:{TXT};border:1px solid {LINE};border-radius:16px;"
                           "padding:9px 18px;font-weight:600;")
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self.fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fx)
        self.an = QVariantAnimation(self)
        self.an.setDuration(260)
        self.an.valueChanged.connect(lambda v: self.fx.setOpacity(float(v)))
        self.an.finished.connect(lambda: self.hide() if self.fx.opacity() < .05 else None)
        self.tm = QTimer(self)
        self.tm.setSingleShot(True)
        self.tm.timeout.connect(self.fade_out)
        self.hide()

    def show_msg(self, text, ms=3200):
        self.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 26)
        self.show()
        self.raise_()
        self.an.stop()
        self.an.setStartValue(self.fx.opacity() if self.isVisible() else 0.0)
        self.an.setEndValue(1.0)
        self.an.start()
        self.tm.start(ms)

    def fade_out(self):
        self.an.stop()
        self.an.setStartValue(1.0)
        self.an.setEndValue(0.0)
        self.an.start()


class UndoMixin:
    UNDO_MAX = 80

    def undo_init(self):
        from PySide6.QtGui import QShortcut
        self.undo_stack, self.redo_stack, self._undoing = [], [], False
        self.toast_w = Toast(self.centralWidget())
        self._snap = self.undo_snapshot()
        self._undo_tm = QTimer(self)
        self._undo_tm.timeout.connect(self.undo_watch)
        self._undo_tm.start(600)
        for seq, fn in ((QKeySequence.StandardKey.Undo, self.undo), (QKeySequence.StandardKey.Redo, self.redo), (QKeySequence("Ctrl+Y"), self.redo)):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.WindowShortcut)
            sc.activated.connect(fn)

    def toast(self, text, ms=3200):
        try:
            self.toast_w.show_msg(text, ms)
        except Exception:
            pass

    # --- instantanés
    def undo_snapshot(self):
        try:
            p = json.loads(json.dumps(self.collect_profile()))
        except Exception:
            return getattr(self, "_snap", "{}")
        p.get("fallback", {}).pop("counts", None)
        return json.dumps({"prof": p, "alerts": self.data.get("alerts", {}), "mon": self.data.get("monitor", {}).get("streams", [])},
                          sort_keys=True, ensure_ascii=False)

    @staticmethod
    def undo_label(a, b):
        try:
            A, B = json.loads(a), json.loads(b)
        except ValueError:
            return "modification"
        pa, pb = A["prof"], B["prof"]
        oa, ob = pa.get("outputs", []), pb.get("outputs", [])
        if len(ob) < len(oa):
            gone = [o["name"] for o in oa if o["id"] not in {x["id"] for x in ob}]
            return "suppression du flux « " + ", ".join(gone) + " »" if gone else "suppression de flux"
        if len(ob) > len(oa):
            return "ajout d'un flux"
        if oa != ob:
            return "modification d'un flux"
        fa, fb = pa.get("fallback", {}), pb.get("fallback", {})
        if fa.get("playlist") != fb.get("playlist"):
            d = len(fb.get("playlist", [])) - len(fa.get("playlist", []))
            return f"retrait de {-d} titre(s) de la playlist de secours" if d < 0 else (f"ajout de {d} titre(s) à la playlist de secours" if d > 0 else "ordre de la playlist de secours")
        if fa.get("folders") != fb.get("folders") or fa.get("folder_of") != fb.get("folder_of"):
            return "dossiers de la playlist de secours"
        if fa.get("off") != fb.get("off"):
            return "rotation de la playlist de secours"
        if fa != fb:
            return "réglages de la playlist de secours"
        if pa.get("carts") != pb.get("carts"):
            return "cartoucheur"
        for k, lb in (("meta", "titre affiché"), ("gain", "gain d'entrée"), ("delay", "retard de sécurité"), ("source", "entrée audio"), ("cover", "pochette")):
            if pa.get(k) != pb.get(k):
                return lb
        if A.get("alerts") != B.get("alerts"):
            return "alertes de panne"
        if A.get("mon") != B.get("mon"):
            return "monitoring"
        return "modification"

    def undo_watch(self):
        if self._undoing or not self.isVisible():
            return
        snap = self.undo_snapshot()
        if snap != self._snap:
            self.undo_stack.append(("state", self._snap, self.undo_label(self._snap, snap)))
            del self.undo_stack[:-self.UNDO_MAX]
            self.redo_stack.clear()
            self._snap = snap

    def undo_push_files(self, moves, label):
        """moves : [(chemin actuel, chemin d'origine)] pour pouvoir remettre les fichiers en place."""
        if moves:
            self.undo_watch()                  # d'abord les réglages en attente, pour que l'opération fichiers soit bien la dernière
            self.undo_stack.append(("files", moves, label))
            del self.undo_stack[:-self.UNDO_MAX]
            self.redo_stack.clear()

    # --- application
    def undo_restore(self, snap):
        self._undoing = True
        try:
            d = json.loads(snap)
            before = {c["id"]: c for c in self.outputs_cfg}
            self.apply_profile(d["prof"])
            self.data["alerts"].clear()
            self.data["alerts"].update(d.get("alerts", {}))
            ms = self.data.setdefault("monitor", {}).setdefault("streams", [])
            ms[:] = d.get("mon", [])
            self.mon_streams = ms
            self.rebuild_mon()
            self.alert_summary()
            if self.on_air:                    # garder l'antenne en phase : flux retirés / ajoutés / modifiés
                after = {c["id"]: c for c in self.outputs_cfg}
                for oid in before:
                    if oid not in after:
                        self.live_remove(oid)
                for oid, c in after.items():
                    if before.get(oid) != c:
                        self.apply_live(c) if c.get("enabled", True) else self.live_remove(oid)
            self._snap = self.undo_snapshot()
        finally:
            self._undoing = False

    def undo_files(self, moves):
        back, errs = [], 0
        for cur, orig in moves:
            try:
                os.makedirs(os.path.dirname(orig), exist_ok=True)
                shutil.move(cur, orig)
                back.append((orig, cur))
            except OSError:
                errs += 1
        if hasattr(self, "rec_files"):
            self.rec_files()
        return back, errs

    def undo(self):
        self.undo_watch()
        if not self.undo_stack:
            return self.toast("Rien à annuler")
        kind, data, label = self.undo_stack.pop()
        if kind == "state":
            cur = self.undo_snapshot()
            self.undo_restore(data)
            self.redo_stack.append(("state", cur, label))
        else:
            back, errs = self.undo_files(data)
            self.redo_stack.append(("files", back, label))
            if errs:
                label += f" ({errs} fichier(s) introuvable(s))"
        self.toast(f"Annulé : {label}   ·   Ctrl+Y pour rétablir")
        self.log(f"Annulé : {label}")

    def redo(self):
        if not self.redo_stack:
            return self.toast("Rien à rétablir")
        kind, data, label = self.redo_stack.pop()
        if kind == "state":
            cur = self.undo_snapshot()
            self.undo_restore(data)
            self.undo_stack.append(("state", cur, label))
        else:
            back, _ = self.undo_files(data)
            self.undo_stack.append(("files", back, label))
        self.toast(f"Rétabli : {label}")
        self.log(f"Rétabli : {label}")

# ------------------------------------------------------------------ fenêtre principale




class FitPage(QWidget):
    pass




class BotButton(QWidget):
    """Gaël (petit format) cliquable dans la barre du haut."""
    clicked = Signal()

    def __init__(self, w=34, h=44):
        super().__init__()
        self.setFixedSize(w, h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Gaël · ton assistant d'antenne (onglet SOS)")
        self.blink, self.talk, self.air = False, 0, False

    def mouseReleaseEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        p = new_painter(self)
        paint_bot(p, 4, 6, 26, self.blink, self.talk, self.air)




class OnAirPill(CLabel):
    """Voyant « EN ANTENNE » façon studio : pastille rouge pleine, texte blanc bien lisible, point qui pulse et halo doux.
    Orange si un flux est HS, jaune quand la playlist de secours est à l'antenne, ambre pendant la connexion, rouge sombre si
    aucun flux ne passe, discret (gris) hors antenne. Largeur fixe : les noms des flux sont dans l'infobulle."""

    NAMES_W = 210                         # zone des indicatifs des flux (défilent s'ils ne tiennent pas)

    def __init__(self):
        super().__init__("Hors antenne", color=MUT)
        self.mode, self.t = "off", 0.0
        self.names, self.t_names = "", 0.0
        self.setMinimumHeight(36)
        f = self.font()
        f.setBold(True)
        f.setPixelSize(14)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
        self.setFont(f)
        self.nfont = QFont(f)
        self.nfont.setBold(False)
        self.nfont.setWeight(QFont.Weight.DemiBold)
        self.nfont.setPixelSize(13)
        self.nfont.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100)
        Ticker.add(self, self.step, 60)

    def set_mode(self, mode):
        if mode != self.mode:
            self.mode = mode
            self.update()

    def sizeHint(self):
        sh = super().sizeHint()
        return QSize(max(sh.width(), getattr(self, "wide", 0)), sh.height())

    def minimumSizeHint(self):
        return QSize(self.minimumWidth(), super().minimumSizeHint().height())

    def set_names(self, names):
        """Indicatifs des flux à l'antenne (« Radio Breizh Web · FM 99.1 · DAB+ ») : le défilement repart du début à chaque
        changement, pour qu'on lise toujours le premier nom en premier."""
        names = names or ""
        if names != self.names:
            self.names, self.t_names = names, self.t
            self.setToolTip(("À l'antenne : " + names) if names else "")
            self.update()

    def step(self, t, dt):
        self.t = t
        return self.mode in ("air", "wait", "secours", "partial")

    def _names_layer(self, w, h, col):
        """Indicatifs dans une bande de w px : immobiles s'ils tiennent, sinon défilement continu et doux (pause de lecture
        au début de chaque tour), bords fondus pour une entrée et une sortie élégantes."""
        dpr = self.devicePixelRatioF()
        img = QImage(int(w * dpr), int(h * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)
        q = QPainter(img)
        q.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        q.setFont(self.nfont)
        q.setPen(col)
        fm = QFontMetricsF(self.nfont)
        tw = fm.horizontalAdvance(self.names)
        fade = 14.0
        if tw <= w - 4:
            q.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.names)
            q.end()
            return img
        gap, speed, pause = 46.0, 30.0, 1.8 if ANIM else 0.0
        cyc = pause + (tw + gap) / speed
        ph = ((self.t - self.t_names) % cyc) if ANIM else 0.0
        off = 0.0 if ph < pause else (ph - pause) * speed
        k = min(1.0, max(0.0, ph - pause) / 0.6)
        ease = off if k >= 1 else off * (k * k * (3 - 2 * k))       # départ en douceur (pas d'à-coup)
        for x in (fade - ease, fade - ease + tw + gap):
            q.drawText(QRectF(x, 0, tw + 4, h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.names)
        # point de séparation entre deux tours
        q.setPen(Qt.PenStyle.NoPen)
        dc = QColor(col)
        dc.setAlphaF(.55)
        q.setBrush(dc)
        q.drawEllipse(QPointF(fade - ease + tw + gap / 2, h / 2), 2.2, 2.2)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        g = QLinearGradient(0, 0, w, 0)
        g.setColorAt(0, qc("#000000", 0))
        g.setColorAt(fade / w, qc("#000000", 255))
        g.setColorAt(1 - fade / w, qc("#000000", 255))
        g.setColorAt(1, qc("#000000", 0))
        q.fillRect(QRectF(0, 0, w, h), QBrush(g))
        q.end()
        return img

    def paintEvent(self, e):
        p = new_painter(self)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        rad = r.height() / 2
        t, m = self.t, self.mode
        if m == "air":
            br = (math.sin(t * 2.6) + 1) / 2 if ANIM else .5
            glow = QColor(ONAIR_RED)
            for i in range(3):                                   # halo doux autour de la pastille
                glow.setAlphaF(.10 + .10 * br - i * .03)
                p.setPen(QPen(glow, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(-1 - i, -1 - i, 1 + i, 1 + i), rad + 1 + i, rad + 1 + i)
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor(ONAIR_RED))
            g.setColorAt(1, QColor(ONAIR_RED2))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(r, rad, rad)
            fg, dot = QColor("#ffffff"), qc("#ffffff", int(255 * (.55 + .45 * br)))
        elif m in ("secours", "partial"):
            br = (math.sin(t * 2.6) + 1) / 2 if ANIM else .5
            c1, c2, fg = (("#ffd23f", "#f2b705", QColor("#2a2000")) if m == "secours" else ("#ff8a2a", "#e8590c", QColor("#ffffff")))
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor(c1))
            g.setColorAt(1, QColor(c2))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(r, rad, rad)
            dot = QColor(fg)
            dot.setAlphaF(.55 + .45 * br)
        elif m == "wait":
            p.setPen(QPen(QColor("#ffb020"), 1.6))
            p.setBrush(qc("#ffb020", 30))
            p.drawRoundedRect(r, rad, rad)
            k = (math.sin(t * 5) + 1) / 2 if ANIM else .5
            fg, dot = QColor("#ffc04d"), qc("#ffb020", int(255 * (.35 + .65 * k)))
        elif m == "bad":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#7a1426"))
            p.drawRoundedRect(r, rad, rad)
            fg, dot = QColor("#ffd5da"), QColor(ONAIR_RED)
        elif m == "preview":
            p.setPen(QPen(QColor(ACC), 1.4))
            p.setBrush(qc(ACC, 26))
            p.drawRoundedRect(r, rad, rad)
            fg, dot = QColor(ACCT), QColor(ACC)
        else:
            p.setPen(QPen(QColor(LINE), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, rad, rad)
            fg, dot = QColor(MUT), None
        p.setFont(self.font())
        fm = QFontMetrics(self.font())
        txt = self.text()
        tw = fm.horizontalAdvance(txt) + (16 if dot is not None else 0)
        names = self.names if m == "air" else ""
        nw = min(self.NAMES_W, r.width() - tw - 48) if names else 0
        if nw < 60:
            nw, names = 0, ""
        x = r.center().x() - (tw + (nw + 22 if names else 0)) / 2
        if dot is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot)
            p.drawEllipse(QPointF(x + 4.5, r.center().y()), 4.5, 4.5)
            x += 16
        p.setPen(fg)
        p.drawText(QRectF(x, r.top(), tw, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, txt)
        if names:                                   # séparateur fin, puis les indicatifs des flux
            x += tw - 16 + 11
            sc = QColor(fg)
            sc.setAlphaF(.45)
            p.setPen(QPen(sc, 1.2))
            p.drawLine(QPointF(x, r.top() + 9), QPointF(x, r.bottom() - 9))
            x += 11
            nc = QColor(fg)
            nc.setAlphaF(.92)
            p.drawImage(QPointF(x, r.top()), self._names_layer(nw, r.height(), nc))


class SpeechBubble(QFrame):
    """Bulle de BD de Gaël (mises à jour) : elle jaillit de Gaël (petit rebond depuis la pointe), contour franc, pointe
    courbe qui va jusqu'à sa tête. tail = « left » (Gaël dans le menu de gauche) ou « top » (petit Gaël en haut à droite)."""

    def __init__(self, parent, tail="left"):
        super().__init__(parent)
        self.tail = tail
        self.tip = QPointF(0, 0)                  # pointe de la queue, en coordonnées de la bulle
        self.k = 1.0                              # 0 -> 1 : apparition
        self.lay = QVBoxLayout(self)
        m = {"left": (34, 12, 24, 20), "top": (16, 30, 24, 20), "bottom": (14, 12, 17, 34)}[tail]
        self.lay.setContentsMargins(*m)
        self.lay.setSpacing(8)
        self.anim = QVariantAnimation(self)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setDuration(340 if ANIM else 1)
        ec = QEasingCurve(QEasingCurve.Type.OutBack)
        ec.setOvershoot(.9)                       # léger rebond (la bulle déborde à peine de sa taille finale)
        self.anim.setEasingCurve(ec)
        self.anim.valueChanged.connect(self._k)
        self.anim.finished.connect(lambda: self._kids(True))
        self.hide_t = QTimer(self)
        self.hide_t.setSingleShot(True)

    def _kids(self, on):
        for w in self.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
            w.setVisible(on and not getattr(w, "_off", False))     # (_off : élément masqué exprès, ex. barre inutile)

    def _k(self, v):
        self.k = float(v)
        self.update()

    def pop(self):
        """Apparition façon BD : la bulle grossit depuis la bouche de Gaël, puis le texte apparaît."""
        self._kids(False)
        self.k = 0.0
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.start()

    def body(self):
        if self.tail == "bottom":
            return QRectF(self.rect()).adjusted(2, 2, -5, -24)
        return QRectF(self.rect()).adjusted(22 if self.tail == "left" else 2, 20 if self.tail == "top" else 2, -11, -11)

    def paintEvent(self, e):
        p = new_painter(self)
        r = self.body()
        k = max(0.0, self.k)
        if k < 1.0 or abs(k - 1.0) > 1e-3:            # mise à l'échelle autour de la pointe (effet « pop »)
            p.translate(self.tip)
            p.scale(k, k)
            p.translate(-self.tip)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        tail = QPainterPath()
        tp = self.tip
        if self.tail == "left":
            y0 = min(max(tp.y() - 4, r.top() + 14), r.bottom() - 30)
            a1, a2 = QPointF(r.left() + 2, y0), QPointF(r.left() + 2, y0 + 20)
            tail.moveTo(a1)
            tail.quadTo(QPointF(r.left() - 4, y0 + 4), tp)
            tail.quadTo(QPointF(r.left() - 2, y0 + 16), a2)
        elif self.tail == "bottom":
            x0 = min(max(tp.x() - 10, r.left() + 18), r.right() - 34)
            a1, a2 = QPointF(x0, r.bottom() - 2), QPointF(x0 + 20, r.bottom() - 2)
            tail.moveTo(a1)
            tail.quadTo(QPointF(x0 + 4, r.bottom() + 4), tp)
            tail.quadTo(QPointF(x0 + 16, r.bottom() + 2), a2)
        else:
            x0 = min(max(tp.x() - 14, r.left() + 18), r.right() - 34)
            a1, a2 = QPointF(x0, r.top() + 2), QPointF(x0 + 20, r.top() + 2)
            tail.moveTo(a1)
            tail.quadTo(QPointF(x0 + 6, r.top() - 4), tp)
            tail.quadTo(QPointF(x0 + 16, r.top() - 2), a2)
        tail.closeSubpath()
        path = path.united(tail)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#000000", 70))
        p.drawPath(path.translated(2, 3))
        p.setBrush(QColor(mixc(PANEL, "#ffffff", .06)))
        p.setPen(QPen(QColor(mixc(TXT, ACC, .25)), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)


class UpdBar(QWidget):
    """Barre de progression de la bulle de Gaël : remplissage doux, reflet qui glisse ; -1 = en cours (durée inconnue)."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(10)
        self.v, self.shown, self.t = 0.0, 0.0, 0.0
        self.hide()
        Ticker.add(self, self.step, 60)

    def set(self, v):
        self.v = float(v)
        self.update()

    def step(self, t, dt):
        self.t = t
        if self.v >= 0:
            self.shown += (self.v - self.shown) * min(1.0, dt * 10)
        return True

    def paintEvent(self, e):
        p = new_painter(self)
        r = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        rad = r.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(r, rad, rad)
        if self.v < 0:                                  # en cours, sans durée connue : segment qui va et vient
            u = (math.sin(self.t * 3) + 1) / 2
            w = r.width() * .3
            fr = QRectF(r.left() + u * (r.width() - w), r.top(), w, r.height())
        else:
            fr = QRectF(r.left(), r.top(), max(r.height(), r.width() * min(1.0, self.shown)), r.height())
        g = QLinearGradient(fr.topLeft(), fr.topRight())
        g.setColorAt(0, QColor(ACC))
        g.setColorAt(1, QColor(ACC2))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(fr, rad, rad)
        if self.v >= 0 and ANIM:                         # reflet qui glisse sur la partie remplie
            x = fr.left() + ((self.t * .6) % 1.0) * (fr.width() + 40) - 20
            sh = QLinearGradient(x - 18, 0, x + 18, 0)
            sh.setColorAt(0, qc("#ffffff", 0))
            sh.setColorAt(.5, qc("#ffffff", 90))
            sh.setColorAt(1, qc("#ffffff", 0))
            p.save()
            p.setClipRect(fr)
            p.setBrush(QBrush(sh))
            p.drawRoundedRect(fr, rad, rad)
            p.restore()


class Banner(QLabel):
    """Bandeau d'alerte (rupture de flux…) : la couleur qui pulse est peinte directement, sans feuille de style."""

    def __init__(self):
        super().__init__("")
        self.setStyleSheet("font-weight:800;font-size:14px;padding:6px 10px;")
        self.setWordWrap(True)                      # fenêtre étroite (écran vertical) : le texte passe à la ligne
        self.bg, self.fg = QColor("#c4263a"), QColor("white")

    def set_colors(self, bg, fg):
        bg, fg = QColor(bg), QColor(fg)
        if (bg.rgb(), fg.rgb()) != (self.bg.rgb(), self.fg.rgb()):
            self.bg, self.fg = bg, fg
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.bg)
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        p.setFont(self.font())
        p.setPen(self.fg)
        p.drawText(QRectF(self.rect()).adjusted(10, 2, -10, -2), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.text())


class AlertFrame(QWidget):
    """Cadre d'alerte posé PAR-DESSUS toute la fenêtre (le menu latéral le cachait à gauche) : bordure tout autour et ligne
    de démarcation rouge entre le menu et le contenu. Transparent aux clics ; caché hors alerte (aucun coût)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.col = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()

    def set_color(self, col):
        self.col = col
        self.setVisible(bool(col))
        if col:
            self.raise_()
            self.update()

    def paintEvent(self, e):
        if not self.col:
            return
        p = QPainter(self)
        c = QColor(self.col)
        p.setPen(QPen(c, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5))
        w = self.window()
        nav = getattr(w, "nav_w", None)
        if nav is not None and nav.isVisible():
            r = QRect(nav.mapTo(self, QPoint(0, 0)), nav.size())
            p.setPen(QPen(c, 2))
            if NAVTOP:
                p.drawLine(QPointF(0, r.bottom() + 1), QPointF(self.width(), r.bottom() + 1))
            else:
                p.drawLine(QPointF(r.right() + 1, 0), QPointF(r.right() + 1, self.height()))


class RootWidget(QWidget):
    """Fond de la fenêtre. En cas de rupture, un cadre coloré est peint ici : avant, une feuille de style posée sur la
    fenêtre entière forçait Qt à recalculer le style de TOUS les widgets (gel visible au début et à la fin d'une alerte)."""

    def __init__(self):
        super().__init__()
        self.border = None
        self.frame = AlertFrame(self)

    def set_border(self, col):
        if col != self.border:
            self.border = col
            self.frame.set_color(col)
            self.update()

    def resizeEvent(self, e):
        self.frame.setGeometry(self.rect())

    def paintEvent(self, e):
        if not self.border:
            return
        p = QPainter(self)
        p.fillRect(e.rect(), mixc(PAGE, self.border, .08))
        p.setPen(QPen(QColor(self.border), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5))


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
