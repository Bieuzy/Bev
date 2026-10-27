# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - fenêtre principale : annuler / rétablir, en-tête, boucle d'affichage, diffusion, réglages."""
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
        m = (34, 12, 24, 20) if tail == "left" else (16, 30, 24, 20)
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


class MainWindow(UndoMixin, CartMixin, PagesMixin1, PagesMixin2, PagesMixin3, PagesMixin4, QMainWindow):
    def __init__(self):
        super().__init__()
        self.root = self
        self.data = load_data()
        S = self.data.setdefault("settings", {})
        st = (S.get("station") or "").strip()
        self.setWindowTitle((st + " · " if st else "") + APP)
        self.resize(1360, 880)
        self.setMinimumSize(640, 600)   # écran vertical (portrait) compris : les pages se réorganisent en une colonne
        self.cur = self.data["last"]
        self.prof = upgrade(json.loads(json.dumps(self.data["profiles"][self.cur])))
        norm_carts(self.prof["carts"])
        self.engine = None
        self._out_down, self._air_beeped = {}, set()
        self.bridge = Bridge()
        self.bridge.logged.connect(self.add_log)
        self.bridge.call.connect(lambda fn: fn())
        self.alerts = Alerts(self)
        self.auto_info = None
        self.automate = AutomateMeta(lambda info: self.ui(self.automate_got, info), self.log)
        self.log_lines, self.log_rec = [], []
        self.waves = WaveLoader()
        self.waves.done.connect(self.wave_ready)
        self.cur_set = 0
        self.tiles = []
        self.cart_flash = {}
        self.page_key = "diff"
        self.mon_state, self.mon_stats, self.mon_started = {}, {}, {}
        self.mon_running = set()
        self.sem = threading.Semaphore(4)
        self.cover_cache, self.cover_shown, self.cover_pm = {}, "?", None
        self.pl_info, self.pl_cov, self.pl_cov_raw = {}, {}, {}
        self.playlist, self.pl_off, self.pl_folders, self.pl_folder, self.pl_view, self.jingles = [], set(), [], {}, None, []
        self.dev_map, self.cover_path = {}, ""
        self.bot_t, self.bot_talk, self.upd_info, self.upd_bubble = 0, 0, None, None
        self._closing = False
        self._proc_off, self.slot = False, None
        self._boot_t0 = time.time()
        self._build()
        self.apply_profile(self.prof)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.start(Gov.ivl(16))           # 30 i/s visés ; si la machine ne suit pas, le régulateur (Gov) allège les décors
        Gov.reg(self.timer, 16)
        Ticker.drive()
        self._live_any, self._pk = False, ([-90.0, -90.0], [-90.0, -90.0], 0.0)
        self.slow_n = 0
        self.bot_timer = QTimer(self)
        self.bot_timer.timeout.connect(self.bot_tick)
        self.bot_timer.start(140)
        self.setAcceptDrops(True)
        self.add_log("Mat eo ! Bienvenue.")
        self.go_tab(S.get("start_tab", "diff") if S.get("start_tab") in PAGE_KEYS else "diff")
        QTimer.singleShot(400, self.automate_apply)        # automate de diffusion (titre en cours), s'il est relié
        self.apply_settings(first=True)
        self.undo_init()
        self.props_init()
        QTimer.singleShot(0, self.apply_compact)
        self.midi, self.midi_learn = None, None
        QTimer.singleShot(1500, lambda: (self.midi_start(), self.midi_label_update()))
        QTimer.singleShot(400, self.refresh_devices)
        QTimer.singleShot(0, self.prewarm)                 # processus moteur prêt avant le premier « Démarrer »
        QTimer.singleShot(60, self.core_boot)              # moteur permanent : cartouches et Démarrer instantanés
        if self.data.get("autostart"):
            QTimer.singleShot(2500, lambda: None if self.on_air else self.start())
        if (UPDATE_REPO or S.get("update_repo")) and S.get("update_check", True):
            QTimer.singleShot(4000, lambda: self.update_start(False))
            self.upd_tm = QTimer(self)                        # puis toutes les 6 h (Bev reste souvent ouvert des jours entiers)
            self.upd_tm.timeout.connect(lambda: self.update_start(False))
            self.upd_tm.start(6 * 3600 * 1000)
        QTimer.singleShot(2600, self.after_update_greet)
        QTimer.singleShot(20000, self.express_settle)
        if not self.data.get("np_tried") and np is None:
            self.data["np_tried"] = True
            QTimer.singleShot(4000, lambda: self.install("numpy"))

    # ------------------------------------------------------------ construction
    def _build(self):
        root = RootWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        S = self.data.get("settings", {})
        if NAVTOP:
            outer = QVBoxLayout(root)
        else:
            outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.rail = TopNav() if NAVTOP else Rail()
        self.nav_w = self.rail
        self.rail.selected.connect(self.go_tab)
        self.rail.set_title(S.get("station", ""))
        self.bot_btn = None
        if NAVTOP:
            nb = QWidget()
            nb.setStyleSheet(f"background:{RAIL};")
            nh = QHBoxLayout(nb)
            nh.setContentsMargins(0, 0, 10, 0)
            nh.setSpacing(6)
            nh.addWidget(self.rail, 1)
            self.bot_btn = BotButton()
            self.bot_btn.clicked.connect(lambda: self.go_tab("sos"))
            nh.addWidget(self.bot_btn)
            if MINI:                                      # minimaliste : plus de robot
                self.bot_btn.hide()
            ck = QVBoxLayout()
            ck.setSpacing(0)
            ck.setContentsMargins(0, 3, 0, 2)
            self.l_clock = lab("", "")
            self.l_clock.setStyleSheet("font-size:19px;font-weight:700;")
            self.l_clock.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.l_date = lab("", "mut")
            self.l_date.setStyleSheet(f"font-size:11px;color:{MUT};")
            self.l_date.setAlignment(Qt.AlignmentFlag.AlignRight)
            ck.addWidget(self.l_clock)
            ck.addWidget(self.l_date)
            nh.addLayout(ck)
            outer.addWidget(nb)
        else:
            self.rail.bot_clicked.connect(lambda: self.go_tab("sos"))
            outer.addWidget(self.rail)
        shell = QVBoxLayout()
        shell.setContentsMargins(22, 4 if NAVTOP else 10, 18, 8)
        shell.setSpacing(8)
        outer.addLayout(shell, 1)
        self.banner = Banner()
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setMinimumHeight(34)
        self.banner.hide()
        shell.addWidget(self.banner)
        self.alert_on = False
        # ---- en-tête
        hd = QHBoxLayout()
        hd.setSpacing(8)
        tl = QVBoxLayout()
        tl.setSpacing(0)
        self.l_title = lab("Diffusion", "")
        self.l_title.setStyleSheet("font-size:24px;font-weight:800;")
        self.l_beta = lab("BÊTA", "")
        self.l_beta.setStyleSheet(f"background:{qc(HUE['son'] if PSYCHE else ACC, 46).name(QColor.NameFormat.HexArgb)};color:{HUE['son'] if PSYCHE else ACCT};"
                                  "font-size:10px;font-weight:800;letter-spacing:1px;border-radius:9px;padding:2px 8px;")
        self.l_beta.setToolTip("Fonction en cours de mise au point : tes retours sont les bienvenus.")
        self.l_beta.hide()
        if not NAVTOP:
            trow = QHBoxLayout()
            trow.setSpacing(10)
            trow.addWidget(self.l_title)
            trow.addWidget(self.l_beta, 0, Qt.AlignmentFlag.AlignVCenter)
            trow.addStretch(1)
            tl.addLayout(trow)
            if PSYCHE:
                tl.addWidget(AuroraBar())
            elif OCEAN:
                tl.addWidget(WaveBar(120, 8))
            hd.addLayout(tl)
        hd.addSpacing(10)
        self.cb_prof = QComboBox()                       # liste réelle des profils (cachée) : le bouton ci-dessous la présente en menu
        self.cb_prof.addItems(list(self.data["profiles"]))
        self.cb_prof.setCurrentText(self.cur)
        self.cb_prof.hide()
        self.btn_prof = btn("")
        self.btn_prof.setMinimumWidth(130)
        self.btn_prof.setMaximumWidth(230)
        self.m_prof = QMenu(self.btn_prof)
        self.m_prof.aboutToShow.connect(self.prof_menu)
        self.btn_prof.setMenu(self.m_prof)
        hd.addWidget(self.btn_prof)
        self.prof_label()
        hd.addStretch(1)

        if not NAVTOP:
            ck = QVBoxLayout()
            ck.setSpacing(0)
            self.l_clock = lab("", "")
            self.l_clock.setStyleSheet("font-size:24px;font-weight:700;")
            self.l_clock.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.l_date = lab("", "mut")
            self.l_date.setStyleSheet(f"font-size:12px;color:{MUT};")
            self.l_date.setAlignment(Qt.AlignmentFlag.AlignRight)
            ck.addWidget(self.l_clock)
            ck.addWidget(self.l_date)
            hd.addLayout(ck)
        self.steady_labels()
        QTimer.singleShot(0, self.fit_air_label)
        self.air_fx = AirWaves()
        hd.addWidget(self.air_fx)
        self.l_air = OnAirPill()
        self.l_air.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.fit_air_label()
        hd.addWidget(self.l_air)
        self.steady_labels()
        self.btn_full = btn("Plein écran", "", self.toggle_fullscreen)
        hd.addWidget(self.btn_full)
        self.btn_start = btn("Démarrer", "primary", self.toggle)
        self.btn_start.setMinimumSize(130, 40)
        self.btn_start.setStyleSheet("font-size:14px;")
        hd.addWidget(self.btn_start)
        shell.addLayout(hd)
        # ---- bandeau « en lecture »
        bar = Card()
        bar.lay.setContentsMargins(10, 5, 14, 5)
        bh = QHBoxLayout()
        bh.setSpacing(12)
        self.mini_lbl = QLabel("♪")
        self.mini_lbl.setFixedSize(38, 38)
        self.mini_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mini_lbl.setStyleSheet("background:#1a1f2b;color:#566074;font-size:18px;border-radius:8px;")
        bh.addWidget(self.mini_lbl)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.now_main = CLabel("○ Rien en lecture", color=MUT)
        self.now_main.setStyleSheet("font-weight:700;")
        self.now_sub = lab("", "")
        self.now_sub.setStyleSheet(f"color:{ACCT};")
        col.addWidget(self.now_main)
        col.addWidget(self.now_sub)
        bh.addLayout(col, 1)
        self.cart_now = CartNow()
        self.cart_now.clicked.connect(lambda: self.engine and self.engine.stop_cart())
        self.cart_now.on_shown = lambda: QTimer.singleShot(0, self.fit_band)
        bh.addWidget(self.cart_now)
        # sonie de sortie, visible sur tous les onglets (les flux à l'antenne sont déjà dans le voyant EN ANTENNE)
        self.loud = LoudChip()
        self.loud.mouseReleaseEvent = lambda _e: self.go_tab("son")
        bh.addWidget(self.loud)
        self.l_net = lab("Réseau : détection…", "")
        self.l_net.setStyleSheet(f"background:{FIELD};color:{MUT};font-weight:700;border-radius:12px;padding:4px 14px;")
        self.l_net.setCursor(Qt.CursorShape.PointingHandCursor)
        self.l_net.setMinimumWidth(170)
        self.l_net.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.l_net.mouseReleaseEvent = lambda _e: self.go_tab("net")
        bh.addWidget(self.l_net)
        self.mini_in = MiniMeter(MINI_W, "ENTRÉE")
        self.mini_out = MiniMeter(MINI_W, "ANTENNE")
        bh.addWidget(self.mini_in)
        bh.addWidget(self.mini_out)
        bar.lay.addLayout(bh)
        self.band = bar
        shell.addWidget(bar)
        # ---- pages
        self.stack = QStackedWidget()
        shell.addWidget(self.stack, 1)
        builders = {"diff": self._page_diffusion, "son": self._page_son, "cart": self._page_cart, "rec": self._page_record,
                    "mon": self._page_mon, "net": self._page_net, "sos": self._page_sos, "set": self._page_settings, "about": self._page_about}
        for k in PAGE_KEYS:
            self.stack.addWidget(builders[k]())
            sp_ = Splash.current               # écran de démarrage encore affiché (voir main)
            if sp_ is not None:                          # l'écran de démarrage continue d'émettre ses ondes
                sp_.tick()
        for v in self.findChildren(QTableWidget) + self.findChildren(QListWidget):   # même surbrillance de ligne partout
            style_table(v)
        if hasattr(self.rail, "gael"):
            self.rail.gael.app = self

    def go_tab(self, key):
        if key not in PAGE_KEYS:
            return
        self.page_key = key
        self.stack.setCurrentIndex(PAGE_KEYS.index(key))
        self.rail.select(key)
        self.l_title.setText({"son": "Processeur", "mon": "Monitoring"}.get(key, PAGE_TITLES[key]) if NAVTOP else PAGE_TITLES[key])
        self.compact_header()
        self.l_title.setMinimumWidth(self.l_title.fontMetrics().horizontalAdvance(self.l_title.text()) + 6)
        if key == "rec":
            self.rec_visit = time.time()
            self.rec_sig = None
            QTimer.singleShot(0, self.rec_tick)
        if key == "cart":
            QTimer.singleShot(0, self.resize_tiles)

    # ------------------------------------------------------------ utilitaires
    def log(self, msg):
        self.bridge.logged.emit(msg)

    def ui(self, fn, *args):
        self.bridge.call.emit(lambda: fn(*args))

    def add_log(self, msg):
        msg = redact(msg)
        line = f"{time.strftime('%H:%M:%S')}  {msg}"
        if self.data.get("settings", {}).get("daily_log"):
            self.daily_log(line)
        self.log_lines.append(line)
        del self.log_lines[:-2000]
        ts, cls = time.strftime("%H:%M:%S"), log_class(msg)
        self.log_rec.append((ts, msg, cls))
        del self.log_rec[:-2000]
        if hasattr(self, "logbox2"):
            if self.journal_pass(ts, msg, cls):
                self.logbox2.append(log_html(ts, msg))
            if cls == "bad":
                self.l_jcount.setText("⚠")
        if hasattr(self, "l_last"):
            self.l_last.setText(msg[:140])

    @property
    def on_air(self):
        e = self.engine
        return bool(e and e.running and e.air)

    @property
    def preview(self):
        """Contrôle d'entrée (hors antenne)."""
        e = self.engine
        return bool(e and e.running and not e.air and e.monitor)

    @property
    def standalone(self):
        """Hors antenne et sans contrôle d'entrée (le cartoucheur reste jouable au casque)."""
        return not (self.on_air or self.preview)

    def device_name(self):
        return self.cur_device

    # ------------------------------------------------------------ horloge, Radiobot
    def clock_tick(self):
        t = time.localtime()
        s = time.strftime("%H:%M:%S", t)
        if s != getattr(self, "_clk", ""):
            self._clk = s
            self.l_clock.setText(s)
            hi = "Noz vat" if (t.tm_hour >= 22 or t.tm_hour < 5) else "Demat"
            self.l_date.setText(f"{hi} · {JOURS[t.tm_wday]} {t.tm_mday} {MOIS[t.tm_mon - 1]}")

    def bot_tick(self):
        self.bot_t += 1
        if self.bot_talk > 0:
            self.bot_talk -= 1
        if calm() or not self.isVisible():
            return
        blink = self.bot_t % 22 in (0, 1)
        air = bool(self.on_air)
        for w in (self.nav_w, self.bot_btn):
            if w is None:
                continue
            if (w.bot_blink if hasattr(w, "bot_blink") else w.blink, w.air) != (blink, air) or getattr(w, "talk", None) != self.bot_talk:
                if hasattr(w, "bot_blink"):
                    w.bot_blink = blink                  # le menu ne dessine pas le petit robot : pas de repeint pour un clin d'œil
                    if w.air == air:
                        continue
                    w.air = air
                else:
                    w.blink, w.air, w.talk = blink, air, self.bot_talk
                w.update()

    def fit_air_label(self, text=""):
        """Largeur de « EN ANTENNE 00:00:00 » mesurée avec la vraie police (après feuille de style, mise à l'échelle Windows
        comprise) ; elle ne fait que grandir si besoin, jamais rétrécir : le texte n'est plus coupé et la ligne ne bouge pas."""
        l = self.l_air
        l.ensurePolished()
        fm = l.fontMetrics()
        f = QFont(l.font())
        f.setBold(True)
        fmb = QFontMetrics(f)
        need = max(max(fm.horizontalAdvance(t), fmb.horizontalAdvance(t)) for t in
                   ("EN ANTENNE  88:88:88", "SECOURS  88:88:88", "8 FLUX HS  88:88:88", "Contrôle d'entrée",
                    "Connexion des flux…", "Aucun flux en ligne", text)) + 16 + 34
        if need > l.minimumWidth():                   # largeur juste nécessaire, fixe : la pastille ne déborde plus et ne
            l.setFixedWidth(need)                     # bouge pas (les noms des flux sont dans l'infobulle)
            l.wide = need
            l.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            l.updateGeometry()

    def steady_labels(self):
        """Horloge, date et état d'antenne à largeur fixe et chiffres tabulaires : plus rien ne bouge à chaque seconde."""
        for l in (self.l_clock, self.l_date, getattr(self, "l_air", None)):
            if l is None:
                continue
            f = l.font()
            try:
                f.setFeature(QFont.Tag("tnum"), 1)
            except Exception:
                pass
            l.setFont(f)
        fm = QFontMetrics(QFont(self.l_clock.font().family(), 1))
        big = QFont(self.l_clock.font())
        big.setPixelSize(24 if not NAVTOP else 19)
        big.setBold(True)
        self.l_clock.setFixedWidth(QFontMetrics(big).horizontalAdvance("00:00:00") + 10)
        small = QFont(self.l_date.font())
        small.setPixelSize(12 if not NAVTOP else 11)
        self.l_date.setFixedWidth(QFontMetrics(small).horizontalAdvance("Noz vat · mercredi 30 septembre") + 8)

    def toggle_fullscreen(self):
        full = not self.isFullScreen()
        self.showFullScreen() if full else self.showNormal()
        self.btn_full.setText("Quitter le plein écran" if full else "Plein écran")

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_F11:
            return self.toggle_fullscreen()
        if e.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                return self.toggle_fullscreen()
            if self.engine:
                self.engine.stop_cart()
            return
        if hasattr(self, "cart_key") and self.cart_key(e):
            return
        super().keyPressEvent(e)

    def fit_band(self):
        """Bandeau « en lecture » : chaque élément garde sa largeur, rien ne se chevauche. Quand la place manque (cartouche
        en lecture, fenêtre de portable), on range d'abord l'état du réseau, puis le vumètre d'entrée (l'antenne reste)."""
        bar = getattr(self, "band", None)
        if bar is None:
            return
        m = bar.lay.contentsMargins()
        avail = bar.width() - m.left() - m.right()
        sp = 12
        need = self.mini_lbl.width() + sp + 150 + self.loud.width() + sp + self.mini_out.width() + sp   # 150 : « Hors antenne »
        if self.cart_now.isVisibleTo(bar):
            need += self.cart_now.minimumWidth() + sp
        net = max(self.l_net.minimumWidth(), self.l_net.sizeHint().width()) + sp
        mi = self.mini_in.width() + sp
        narrow = bool(getattr(self, "_narrow", False))
        show_net = not narrow and need + net + mi <= avail
        show_in = need + mi + (net if show_net else 0) <= avail
        if self.l_net.isVisibleTo(bar) != show_net:
            self.l_net.setVisible(show_net)
        if self.mini_in.isVisibleTo(bar) != show_in:
            self.mini_in.setVisible(show_in)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.fit_band)
        RZ[0] = time.time() + .3
        QTimer.singleShot(0, self.place_upd_bubble)
        if hasattr(self, "l_beta"):
            self.compact_header()
        QTimer.singleShot(0, self.apply_compact)
        QTimer.singleShot(0, self.diff_fit)

    NARROW_W = 1180

    def apply_narrow(self):
        """Fenêtre étroite (écran vertical, demi-écran) : menu réduit aux icônes, en-tête allégé, et chaque page passe sur une
        seule colonne qui défile. Au-delà de 1180 px de large, la disposition habituelle revient."""
        on = self.width() < self.NARROW_W
        if hasattr(self.rail, "set_compact"):         # écran vertical de 1080 px : on garde le menu complet (et Gaël)
            self.rail.set_compact(self.width() < 980)
        if on == getattr(self, "_narrow", None):
            return
        self._narrow = on
        self.l_date.setVisible(not on)
        QTimer.singleShot(0, self.fit_band)
        self.btn_prof.setMaximumWidth(170 if on else 230)
        self.btn_prof.setMinimumWidth(110 if on else 130)
        self.prof_label()
        self.l_title.setStyleSheet("font-size:%dpx;font-weight:800;" % (19 if on else 24))
        for pg in self.findChildren(Page):
            regrid(pg.grid, on)
        if hasattr(self, "net_gd"):
            regrid(self.net_gd, on, 2)
        d = getattr(self, "_diff", None)
        if d:
            h, left, right, src, fb, outf, air, facts = d
            for wdg in (src, fb, outf, air, facts):
                left.removeWidget(wdg)
                right.removeWidget(wdg)
            if on:
                h.setDirection(QHBoxLayout.Direction.TopToBottom)
                for wdg, st in ((src, 0), (outf, 0), (fb, 1), (air, 0), (facts, 0)):
                    left.addWidget(wdg, st)
                h.setStretch(0, 1)
                h.setStretch(1, 0)
                fb.setMinimumHeight(440)
                outf.setMinimumHeight(210)
            else:
                h.setDirection(QHBoxLayout.Direction.LeftToRight)
                left.addWidget(src)
                left.addWidget(fb, 1)
                right.addWidget(outf, 1)
                right.addWidget(air)
                right.addWidget(facts)
                h.setStretch(0, 1)
                h.setStretch(1, 1)
                fb.setMinimumHeight(0)
                outf.setMinimumHeight(0)
        c = getattr(self, "_cart", None)
        if c:
            body, side, mid, ins = c
            if on:
                body.removeWidget(ins)
                mid.insertWidget(1, ins)
                ins.setMinimumWidth(0)
                ins.setMaximumWidth(16777215)
                side.setFixedWidth(140)
            else:
                mid.removeWidget(ins)
                body.addWidget(ins)
                ins.setFixedWidth(300)
                side.setFixedWidth(170)
            QTimer.singleShot(0, self.resize_tiles)
        sk = getattr(self, "_sk", None)
        if sk:                                           # À propos : raccourcis sur une colonne (plus de texte coupé)
            grid, labels = sk
            for l in labels:
                grid.removeWidget(l)
            for i, l in enumerate(labels):
                grid.addWidget(l, i, 0)                  # (une colonne : la carte est à côté des nouveautés)
        sl = getattr(self, "_sos_lay", None)
        if sl:                                           # SOS : téléphone replié, boutons sous le texte, interrupteurs empilés
            h, bt, trg = sl
            D = QHBoxLayout.Direction
            h.setDirection(D.TopToBottom if on else D.LeftToRight)
            bt.setDirection(D.LeftToRight if on else D.TopToBottom)
            trg.setDirection(D.TopToBottom if on else D.LeftToRight)
            trg.setSpacing(6 if on else 16)
            h.setSpacing(10 if on else 22)
            self.al_phone.setVisible(not on and not MINI)
        self.compact_header()

    def air_min(self):
        """Hauteur minimale de « 4 · À l'antenne » recalculée à chaque changement de compacité (elle restait figée à sa
        taille d'origine : la page Diffusion défilait sur les écrans de portable)."""
        d = getattr(self, "_diff", None)
        if d:
            air = d[6]
            air.setMinimumHeight(0)
            air.setMinimumHeight(air.minimumSizeHint().height())

    def apply_compact(self):
        """Adapte toutes les pages à la hauteur disponible : en dessous de 720 px de page, cartes plus serrées et
        sous-titres masqués ; en dessous de 600 px, on range aussi les éléments décoratifs (anecdote, forme d'onde…)."""
        if not hasattr(self, "stack"):
            return
        self.apply_narrow()
        avail = self.stack.height()
        lvl = 0 if avail >= 720 else (1 if avail >= 600 else 2)
        if lvl == getattr(self, "_compact_lvl", -1):
            return
        self._compact_lvl = lvl
        for c in self.findChildren(Card):
            c.set_compact(lvl >= 1)
        if getattr(self, "facts", None) is not None:
            self.facts.set_mini(lvl >= 1)
            self.facts.setVisible(not MINI)
            QTimer.singleShot(0, self.diff_fit)
        if hasattr(self, "wave"):
            self.wave.setVisible(lvl < 2 and not MINI)
        if hasattr(self, "al_phone"):
            self.al_phone.set_small(lvl >= 1)
            self.al_sub.setVisible(lvl < 1)
        if hasattr(self, "assistant"):
            self.assistant.chips_compact(lvl >= 1)
        if hasattr(self, "eqc"):                        # (onglet Processeur : tout tient sur un écran)
            self.eqc.setMinimumHeight(110 if lvl < 1 else 92)
        if hasattr(self, "proc_meters"):
            self.proc_meters.setMinimumHeight(150 if lvl < 1 else 128)
        QTimer.singleShot(0, self.air_min)

    def compact_header(self):
        """Fenêtre étroite : on replie l'antenne décorative et « Plein écran » (F11 reste dispo) pour que l'en-tête ne se chevauche jamais."""
        wide = self.width() >= 1320
        self.l_beta.setVisible(False)
        self.air_fx.setVisible(wide and not MINI)
        self.btn_full.setVisible(wide or self.isFullScreen())
        if hasattr(self, "sa") and self.page_key == "cart":
            QTimer.singleShot(0, self.resize_tiles)

    # ------------------------------------------------------------ profils
    def collect_profile(self):
        fb = self.prof["fallback"]
        e = self.fb_ed
        self.prof.update({
            "source": {"device": self.cur_device.strip()},
            "fallback": {"enabled": self.sw_fb.isChecked(), "shuffle": self.sw_shuf.isChecked(), "threshold": e["threshold"].text().strip(),
                         "silence_s": e["silence_s"].text().strip(), "recover_s": e["recover_s"].text().strip(), "fade_in": e["fade_in"].text().strip(),
                         "fade_out": e["fade_out"].text().strip(), "playlist": list(self.playlist), "off": sorted(self.pl_off),
                         "folders": list(self.pl_folders), "folder_of": dict(self.pl_folder), "counts": self.data.setdefault("counts", {}),
                         "jingle": {"enabled": self.sw_jingle.isChecked(), "every": str(self.sp_jevery.value()), "files": list(self.jingles)}},
            "meta": {"text": self.ed_meta.text(), "follow": self.sw_follow.isChecked()},
            "delay": str(self.sp_delay.value()), "gain": str(self.sl_gain.value()), "cover": self.cover_path})
        c = self.prof["carts"]
        c.update(duck=int(self.sl_duck.value()), fade_click=self.sl_fc.value() / 10, device="" if self.cb_cdev.currentText() == NODEV else self.cb_cdev.currentText(),
                 route=ROUTES[0], solo=self.sw_solo.isChecked())
        return self.prof

    def apply_profile(self, p):
        p = upgrade(json.loads(json.dumps(p)))
        self.prof = p
        norm_carts(p["carts"])
        fb = p["fallback"]
        self._loading = True
        try:
            self.cur_device = p["source"]["device"]
            self.sync_device_selection()
            self.sw_fb.setChecked(bool(fb["enabled"]))
            self.sw_shuf.setChecked(bool(fb["shuffle"]))
            for k in ("threshold", "silence_s", "recover_s"):
                self.fb_ed[k].setText(str(fb[k]))
            self.fb_ed["fade_in"].setText(str(fb.get("fade_in", "0.5")))
            self.fb_ed["fade_out"].setText(str(fb.get("fade_out", "1.2")))
            self.sw_jingle.setChecked(bool(fb["jingle"]["enabled"]))
            try:
                self.sp_jevery.setValue(int(float(fb["jingle"]["every"])))
            except (TypeError, ValueError):
                self.sp_jevery.setValue(15)
            self.jingles = list(fb["jingle"]["files"])
            self.playlist = list(fb["playlist"])
            self.pl_off = set(fb.get("off", []))
            self.pl_folders = list(fb.get("folders", []))
            self.pl_folder = {k: v for k, v in dict(fb.get("folder_of", {})).items() if v in self.pl_folders}
            self.pl_view = None
            self.ed_meta.setText(p["meta"]["text"])
            self.sw_follow.setChecked(bool(p["meta"]["follow"]))
            try:
                self.sp_delay.setValue(int(float(p["delay"])))
            except (TypeError, ValueError):
                self.sp_delay.setValue(0)
            try:
                self.sl_gain.setValue(int(float(p["gain"])))
            except (TypeError, ValueError):
                self.sl_gain.setValue(0)
            self.cover_path = p["cover"]
            c = p["carts"]
            self.cb_route.setCurrentText(ROUTES[0])          # choix de route retiré : le cartoucheur joue à l'antenne (Maj + clic = sortie audio seule)
            self.sw_solo.setChecked(bool(c["solo"]))
            self.sl_duck.setValue(int(c["duck"]))
            try:
                self.sl_fc.setValue(int(round(float(c.get("fade_click", 2.5)) * 10)))
            except (TypeError, ValueError):
                self.sl_fc.setValue(25)
        finally:
            self._loading = False
        self.live_gain()
        self.pl_refresh()
        self.refresh_outputs()
        self.cur_set = 0
        self.refresh_sets()
        self.fb_summary()
        self.sync_cart_device()
        self.cover_shown = "?"
        e = self.engine
        if e is not None and e.running and not e.air:     # profil changé hors antenne : le moteur suit (cartouches, entrée…)
            e.set_prof(json.loads(json.dumps(self.collect_profile())))

    def save_all(self):
        self.collect_profile()
        self.data["profiles"][self.cur] = self.prof
        self.data["last"] = self.cur
        self.data["autostart"] = self.sw_auto.isChecked()
        self.sync_net()
        self.sync_alerts()
        try:
            save_data(self.data)
        except OSError as e:
            self.log(f"Enregistrement des réglages impossible : {e}")

    def save_all_raw(self):
        try:
            save_data(self.data)
        except OSError:
            pass

    def prof_label(self):
        t = self.cb_prof.currentText() or self.cur
        short = t if len(t) <= 16 else t[:15] + "…"
        self.btn_prof.setText(short if getattr(self, "_narrow", False) else "Profil · " + short)
        self.btn_prof.setToolTip("Profil de réglages : " + t)

    def prof_menu(self):
        m = self.m_prof
        m.clear()
        for n in self.data["profiles"]:
            a = m.addAction(n)
            a.setCheckable(True)
            a.setChecked(n == self.cur)
            a.triggered.connect(lambda _=False, n=n: (self.cb_prof.setCurrentText(n), self.on_profile()))
        m.addSeparator()
        m.addAction("Nouveau profil à partir de celui-ci…", self.new_profile)
        m.addAction("Renommer…", self.rename_profile)
        m.addAction("Enregistrer", self.save_profile)
        m.addAction("Supprimer", self.delete_profile)

    def new_profile(self):
        n, ok = QInputDialog.getText(self, "Nouveau profil", "Nom du profil :")
        if ok and n.strip():
            self.cb_prof.setEditable(True)
            self.cb_prof.setCurrentText(n.strip())
            self.save_profile()

    def rename_profile(self):
        n, ok = QInputDialog.getText(self, "Renommer le profil", "Nouveau nom :", text=self.cur)
        n = n.strip()
        if not (ok and n) or n == self.cur or self.on_air:
            return
        self.collect_profile()
        self.data["profiles"][n] = self.data["profiles"].pop(self.cur)
        self.cur = n
        self.cb_prof.blockSignals(True)
        self.cb_prof.clear()
        self.cb_prof.addItems(list(self.data["profiles"]))
        self.cb_prof.setCurrentText(n)
        self.cb_prof.blockSignals(False)
        self.data["last"] = n
        self.prof_label()

    def on_profile(self, *_):
        if self.on_air:
            self.cb_prof.setCurrentText(self.cur)
            return info(self, "Profil", "Arrête la diffusion avant de changer de profil.")
        name = self.cb_prof.currentText()
        if name not in self.data["profiles"]:
            return
        self.collect_profile()
        self.data["profiles"][self.cur] = self.prof
        self.cur = name
        self.apply_profile(self.data["profiles"][name])
        self.data["last"] = name
        self.prof_label()

    def save_profile(self):
        name = self.cb_prof.currentText().strip()
        if not name:
            return info(self, "Profil", "Donne un nom au profil.")
        self.cur = name
        self.save_all()
        self.cb_prof.blockSignals(True)
        self.cb_prof.clear()
        self.cb_prof.addItems(list(self.data["profiles"]))
        self.cb_prof.setCurrentText(name)
        self.cb_prof.blockSignals(False)
        self.prof_label()
        self.log(f"Profil « {name} » enregistré.")

    def delete_profile(self):
        name = self.cb_prof.currentText()
        if name not in self.data["profiles"] or self.on_air:
            return
        if not yes(self, "Supprimer", f"Supprimer le profil « {name} » ?"):
            return
        del self.data["profiles"][name]
        if not self.data["profiles"]:
            self.data["profiles"]["Défaut"] = default_profile()
        self.cur = next(iter(self.data["profiles"]))
        self.cb_prof.blockSignals(True)
        self.cb_prof.clear()
        self.cb_prof.addItems(list(self.data["profiles"]))
        self.cb_prof.setCurrentText(self.cur)
        self.cb_prof.blockSignals(False)
        self.apply_profile(self.data["profiles"][self.cur])

    # ------------------------------------------------------------ page Diffusion
    def _page_diffusion(self):
        w = FitPage()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 4, 0)
        h.setSpacing(12)
        left, right = QVBoxLayout(), QVBoxLayout()
        left.setSpacing(10)
        right.setSpacing(10)
        h.addLayout(left, 1)
        h.addLayout(right, 1)
        # --- source
        src = Card("1 · Source audio", "Entrée captée et niveau de modulation")
        r = QHBoxLayout()
        r.setSpacing(8)
        self.dev_pick = DevicePicker()
        self.dev_pick.picked.connect(self.on_dev_select)
        self.dev_pick.refresh.connect(self.refresh_devices)
        r.addWidget(self.dev_pick, 1)
        rb = self.btn_devref = IconButton("refresh", "Actualiser la liste des entrées")
        rb.clicked.connect(self.refresh_devices)
        r.addWidget(rb, 0, Qt.AlignmentFlag.AlignVCenter)
        src.lay.addLayout(r)
        self.l_devst = lab("Recherche...", "mut")
        self.l_devst.setTextFormat(Qt.TextFormat.RichText)
        self.l_devst.setWordWrap(False)                  # (une ligne : pas de hauteur dépendant de la largeur)
        self.l_devst.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.l_devst.setMinimumWidth(40)
        src.lay.addWidget(self.l_devst)
        mr = QHBoxLayout()
        self.meter_in = LevelMeter("ENTRÉE")
        mr.addWidget(self.meter_in)
        side = QVBoxLayout()
        self.btn_prev = btn("Voir l'entrée", "", self.toggle_preview)
        side.addWidget(self.btn_prev)
        gr = QHBoxLayout()
        gr.addWidget(lab("Gain d'entrée", ""))
        self.l_gain = lab("0 dB", "mut")
        self.l_gain.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        gr.addWidget(self.l_gain, 1)
        g0 = QPushButton("0")
        g0.setToolTip("Remettre le gain à 0 dB")
        g0.setFixedSize(30, 26)
        g0.setCursor(Qt.CursorShape.PointingHandCursor)
        g0.setStyleSheet("padding:0;border-radius:9px;font-size:11px;")
        g0.clicked.connect(lambda: self.sl_gain.setValue(0))
        gr.addWidget(g0)
        side.addLayout(gr)
        self.sl_gain = Slider(Qt.Orientation.Horizontal)
        self.sl_gain.setRange(-12, 12)
        self.sl_gain.valueChanged.connect(lambda *_: self.live_gain())
        side.addWidget(self.sl_gain)
        side.addStretch(1)
        mr.addLayout(side, 1)
        src.lay.addLayout(mr)
        self.btn_loop = btn("Activer la capture du son de l'ordinateur", "", lambda: self.enable_loopback())
        if SYS == "Windows" and not have_loopback():
            src.lay.addWidget(self.btn_loop, 0, Qt.AlignmentFlag.AlignLeft)
        left.addWidget(src)
        # --- secours
        fb = Card("3 · Playlist de secours", "Relève automatique en cas de silence")
        hd = QHBoxLayout()
        self.sw_fb = Switch("Prendre le relais après 10 s de silence")
        self.sw_fb.toggled.connect(lambda *_: self.live_fb())
        hd.addWidget(self.sw_fb)
        hd.addStretch(1)
        self.btn_adv = btn("Options", "", self.toggle_fb_adv)
        hd.addWidget(self.btn_adv)
        fb.lay.addLayout(hd)
        self.build_fb_dialog()
        lib = QHBoxLayout()                       # bibliothèque : dossiers à gauche, titres à droite
        lib.setSpacing(10)
        self.pl_bar = FolderBar(self)
        lib.addWidget(self.pl_bar, 0)
        rc = QVBoxLayout()
        rc.setSpacing(6)
        r2 = QHBoxLayout()
        self.l_plview = lab("Tous les titres", "")
        self.l_plview.setStyleSheet("font-size:15px;font-weight:800;")
        r2.addWidget(self.l_plview)
        self.l_plc = lab("", "mut")
        r2.addWidget(self.l_plc)
        r2.addStretch(1)
        self.ed_plq = QLineEdit()
        self.ed_plq.setPlaceholderText("Rechercher")
        self.ed_plq.setClearButtonEnabled(True)
        self.ed_plq.setMaximumWidth(150)
        self.ed_plq.setStyleSheet("border-radius:14px;padding:4px 12px;")
        self.ed_plq.textChanged.connect(lambda *_: self.pl_refresh())
        r2.addWidget(self.ed_plq)
        rc.addLayout(r2)
        self.l_plsel = lab("", "")
        self.l_plsel.setStyleSheet(f"color:{ACCT};font-weight:700;font-size:12px;")
        self.l_plsel.hide()
        self.pl_tv = TrackList(self.pl_toggle, self.pl_play, self.pl_menu, self.pl_remove)
        self.pl_tv.cb_s = self.pl_sel_changed
        self.pl_tv.cb_drop = self.pl_drop
        rc.addWidget(self.pl_tv, 1)
        lib.addLayout(rc, 1)
        fb.lay.addLayout(lib, 1)
        r3 = QHBoxLayout()
        mb = btn("＋ Ajouter")
        mb.setMinimumWidth(mb.fontMetrics().horizontalAdvance("＋ Ajouter") + 58)
        mm = QMenu(mb)
        mm.addAction("Des fichiers…", self.pl_add)
        mm.addAction("Un dossier…", self.pl_add_dir)
        mm.addSeparator()
        mm.addAction("Remettre les compteurs à zéro", self.pl_reset_counts)
        mb.setMenu(mm)
        r3.addWidget(mb)
        self.btn_plrem = btn("Retirer", "", self.pl_remove)
        r3.addWidget(self.btn_plrem)
        r3.addStretch(1)
        self.btn_playsel = btn("Jouer la sélection", "", self.pl_play_sel)
        r3.addWidget(self.btn_playsel)
        # transport de la playlist de secours : lecture / pause, et stop (retour au direct)
        self.btn_plpause = TBtn("play", "", size=(40, 34))
        self.btn_plpause.setToolTip("Lancer la playlist de secours à l'antenne")
        self.btn_plpause.clicked.connect(self.pl_play_pause)
        r3.addWidget(self.btn_plpause)
        self.btn_plstop = TBtn("stop", "", size=(40, 34))
        self.btn_plstop.setToolTip("Arrêter la playlist de secours : retour au direct (pas de relève automatique avant le retour du son)")
        self.btn_plstop.clicked.connect(self.pl_stop_btn)
        r3.addWidget(self.btn_plstop)
        self.btn_manual = btn("Lancer la playlist", "", self.toggle_manual)
        self.btn_manual.hide()                           # remplacé par lecture / pause / stop
        fb.lay.addLayout(r3)
        left.addWidget(fb, 1)
        # --- flux
        outf = Card("2 · Flux", "Destinations de diffusion")
        self.tb_out = QTableWidget(0, 5)
        self.tb_out.setHorizontalHeaderLabels(["ACTIF", "TYPE", "NOM", "DESTINATION", "ÉTAT"])
        style_table(self.tb_out, check_col=0)
        hh = self.tb_out.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tb_out.verticalHeader().hide()
        self.tb_out.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tb_out.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tb_out.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tb_out.setShowGrid(False)
        self.tb_out.setMinimumHeight(64)
        self.tb_out.cellClicked.connect(self.on_tree_click)
        self.tb_out.doubleClicked.connect(lambda *_: self.edit_output())
        outf.lay.addWidget(self.tb_out, 1)
        self.l_flux = CLabel("", "mut", False, MUT)      # une ligne, texte complet en infobulle (l'état de chaque flux
        self.l_flux.elide = True                         # est déjà dans le tableau)
        self.l_flux.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.l_flux.setMinimumWidth(40)
        outf.lay.addWidget(self.l_flux)
        r = QHBoxLayout()
        mb = btn("＋ Flux     ")
        mm = QMenu(mb)
        for k, label in (("internet", " Internet (Icecast / Shoutcast)"), ("fm", " FM (carte son + RDS)"), ("dab", " DAB+")):
            mm.addAction(KINDS[k][0] + label, lambda kk=k: self.add_output(kk))
        mm.addSeparator()
        mm.addAction("Plateau extérieur (nouvelle adresse)…", self.new_plateau)
        mm.addAction("Changer l'adresse du flux choisi…", self.rename_mount)
        mb.setMenu(mm)
        r.addWidget(mb)
        for t, fn in (("Modifier", self.edit_output), ("Dupliquer", self.dup_output), ("Supprimer", self.del_output)):
            b = btn(t, "", fn)
            b.setMinimumWidth(b.fontMetrics().horizontalAdvance(t) + 30)
            self.flux_btns = getattr(self, "flux_btns", []) + [b]
            r.addWidget(b)
        r.addStretch(1)
        self.btn_run_out = btn("Marche/arrêt", "", self.toggle_selected)
        self.btn_run_out.setMinimumWidth(self.btn_run_out.fontMetrics().horizontalAdvance("Marche/arrêt") + 30)
        r.addWidget(self.btn_run_out)
        outf.lay.addLayout(r)
        right.addWidget(outf, 1)
        # --- antenne
        air = Card("4 · À l'antenne", "Signal diffusé et métadonnées")
        r = QHBoxLayout()
        self.cover_lbl = QLabel()
        self.cover_lbl.setFixedSize(96, 96)
        self.cover_lbl.setStyleSheet("background:#222;border-radius:12px;")
        r.addWidget(self.cover_lbl)
        col = QVBoxLayout()
        self.meter = LevelMeter("ANTENNE")
        col.addWidget(self.meter)
        self.l_sig = CLabel("Signal : -", "mut", False, MUT)
        self.l_now = CLabel("Titre : -", "mut", False, MUT)
        for l_ in (self.l_sig, self.l_now):
            l_.elide = True
            l_.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            l_.setMinimumWidth(40)
            col.addWidget(l_)
        r.addLayout(col, 1)
        air.lay.addLayout(r)
        self.wave = Wave(28)
        air.lay.addWidget(self.wave)
        mt = QHBoxLayout()
        mt.addWidget(lab("Titre affiché", ""))
        self.ed_meta = QLineEdit()
        self.ed_meta.returnPressed.connect(self.send_meta_now)
        mt.addWidget(self.ed_meta, 1)
        mt.addWidget(btn("Envoyer", "", self.send_meta_now))
        mt.addWidget(btn("Image…", "", self.pick_cover))
        air.lay.addLayout(mt)
        at = QHBoxLayout()                       # titre en cours reçu d'un automate de diffusion (Radiologik…)
        self.l_auto = CLabel("Automate : non relié", "mut", False, MUT)
        self.l_auto.elide = True
        self.l_auto.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.l_auto.setMinimumWidth(40)
        at.addWidget(self.l_auto, 1)
        at.addWidget(btn("Automate…", "", self.automate_dialog,
                         "Récupérer titre, artiste et pochette depuis un automate de diffusion (Radiologik, RadioDJ…)"))
        air.lay.addLayout(at)
        self.sw_follow = Switch("Pendant la playlist, afficher le titre du morceau joué")
        self.sw_follow.toggled.connect(lambda *_: self.live_meta())
        air.lay.addWidget(self.sw_follow)
        lr = QHBoxLayout()
        self.btn_listen = btn("Écouter l'antenne au casque", "", self.toggle_listen,
                              "Entends au casque ce qui part vraiment à l'antenne (direct, playlist de secours, cartouches), "
                              "sur la carte son choisie dans le cartoucheur.")
        lr.addWidget(self.btn_listen)
        lr.addStretch(1)
        air.lay.addLayout(lr)
        self.l_last = lab("", "mut")
        self.l_last.setCursor(Qt.CursorShape.PointingHandCursor)
        self.l_last.mouseReleaseEvent = lambda _e: self.go_tab("sos")
        self.l_last.hide()                     # le dernier message reste lisible dans SOS > Journal (gain de place)
        right.addWidget(air)
        self.facts = FactCard()
        right.addWidget(self.facts)
        self._diff = (h, left, right, src, fb, outf, air, self.facts)
        QTimer.singleShot(0, self.air_min)               # jamais écrasée par la carte « Flux »
        self.cur_device = ""
        self.show_cover(None)
        sa = FitScroll()                         # fenêtre basse : la page défile au lieu de se chevaucher
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        w.setObjectName("page")
        sa.setWidget(w)
        self._diff_sa = sa
        self.facts.on_text = lambda: QTimer.singleShot(0, self.diff_fit)
        return sa

    def diff_fit(self):
        """Diffusion : la colonne de droite (Flux, À l'antenne, Le saviez-vous) doit tenir dans la hauteur visible. Qt ne
        sait pas réduire une carte sous son minimum : il la faisait déborder sur la suivante (anecdote par-dessus « À
        l'antenne »). On choisit donc l'anecdote complète, puis resserrée (3 lignes), puis rangée si la place manque."""
        d = getattr(self, "_diff", None)
        sa = getattr(self, "_diff_sa", None)
        if not d or sa is None or MINI:
            return
        h, left, right, src, fb, outf, air, facts = d
        if getattr(self, "_narrow", False):          # une seule colonne qui défile : tout reste affiché
            facts.setVisible(True)
            return
        avail = sa.viewport().height() - 4
        sp = right.spacing()
        width = max(200, air.width() or (self.width() // 2))

        def eff(c):                                  # hauteur que la colonne réserve vraiment à la carte
            m = c.minimumSizeHint().height()
            return max(m, c.heightForWidth(width)) if c.hasHeightForWidth() else m
        base = eff(outf) + eff(air) + 2 * sp

        def need(mini):
            facts.set_mini(mini)
            facts.layout().activate()
            return eff(facts)
        lvl = getattr(self, "_compact_lvl", 0)
        if lvl < 1 and base + need(False) <= avail:
            facts.setVisible(True)
        elif base + need(True) <= avail:
            facts.setVisible(True)
        else:
            facts.set_mini(lvl >= 1)
            facts.setVisible(False)

    # --- options du secours
    def build_fb_dialog(self):
        d = self.fb_win = QDialog(self)
        d.setWindowTitle("Options de la playlist de secours")
        f = QFormLayout(d)
        f.setContentsMargins(20, 16, 20, 16)
        expl = lab("Quand l'entrée reste plus basse que le seuil pendant le délai, la playlist de secours prend le relais "
                   "avec un fondu. Dès que le son revient (pendant la durée indiquée), l'antenne repasse au direct.\n"
                   "Chaque changement s'applique immédiatement, même pendant la diffusion.", "mut", True)
        expl.setMaximumWidth(420)
        f.addRow(expl)
        self.fb_ed = {}
        from PySide6.QtGui import QDoubleValidator
        for k, t, lo, hi, tip in (("threshold", "Seuil de silence (dB)", -90, -1, "En dessous de ce niveau, l'entrée est considérée comme silencieuse (par défaut -50)."),
                                  ("silence_s", "Délai avant bascule (s)", 1, 3600, "Durée de silence avant que la playlist prenne le relais (par défaut 10 s)."),
                                  ("recover_s", "Retour au direct après (s)", 0.2, 600, "Durée pendant laquelle le son doit être revenu pour repasser au direct (par défaut 2 s)."),
                                  ("fade_in", "Fondu vers la playlist (s)", 0.05, 30, "Durée du fondu enchaîné direct → playlist."),
                                  ("fade_out", "Fondu retour direct (s)", 0.05, 30, "Durée du fondu enchaîné playlist → direct.")):
            e = QLineEdit()
            e.setMaximumWidth(90)
            v = QDoubleValidator(lo, hi, 2, e)
            v.setNotation(QDoubleValidator.Notation.StandardNotation)
            from PySide6.QtCore import QLocale
            v.setLocale(QLocale.c())                     # point décimal (0.5), comme dans le reste des réglages
            e.setValidator(v)
            e.setToolTip(tip)
            e.textChanged.connect(lambda *_: (self.fb_summary(), self.live_fb()))
            self.fb_ed[k] = e
            f.addRow(t, e)
        self.sw_shuf = Switch("Lecture aléatoire")
        self.sw_shuf.toggled.connect(lambda *_: self.live_fb())
        f.addRow("", self.sw_shuf)
        jr = QHBoxLayout()
        self.sw_jingle = Switch("Jingle toutes les")
        self.sw_jingle.toggled.connect(lambda *_: self.live_fb())
        self.sp_jevery = QSpinBox()
        self.sp_jevery.setRange(1, 240)
        self.sp_jevery.valueChanged.connect(lambda *_: self.live_fb())
        jr.addWidget(self.sw_jingle)
        jr.addWidget(self.sp_jevery)
        jr.addWidget(lab("min", "mut"))
        self.btn_jfile = btn("Choisir les jingles…", "", self.pick_fb_jingle)
        jr.addWidget(self.btn_jfile)
        f.addRow(jr)
        f.addRow(btn("Fermer", "primary", d.hide))

    def toggle_fb_adv(self):
        self.fb_win.show()
        self.fb_win.raise_()

    def fb_summary(self):
        if not hasattr(self, "sw_fb") or not hasattr(self, "fb_ed"):
            return
        sec = self.fb_ed['silence_s'].text().strip() or "10"
        self.sw_fb.setText(f"Prendre le relais après {sec} s de silence" if self.sw_fb.isChecked() else "Playlist de secours désactivée")
        self.sw_fb.updateGeometry()
        self.sw_fb.update()
        n = len(self.jingles)
        self.btn_jfile.setText(f"{n} jingle{'s' if n > 1 else ''}…" if n else "Choisir les jingles…")

    def pick_fb_jingle(self):
        r = JingleDialog(self, self.jingles)
        if r.exec() and r.result is not None:
            self.jingles = r.result
            if r.result:
                self.sw_jingle.setChecked(True)
            self.live_fb()

    def live_fb(self):
        """Tout réglage de la playlist de secours est envoyé au moteur immédiatement (marche/arrêt, seuil, délais, fondus,
        aléatoire, jingles) : il compte tout de suite, même pendant l'antenne."""
        self.fb_summary()
        if self.engine and not getattr(self, "_loading", False):
            e = self.fb_ed
            self.engine.prof_update("fallback", enabled=self.sw_fb.isChecked(), shuffle=self.sw_shuf.isChecked(),
                                    threshold=e["threshold"].text().strip(), silence_s=e["silence_s"].text().strip(),
                                    recover_s=e["recover_s"].text().strip(),
                                    jingle=dict(enabled=self.sw_jingle.isChecked(), every=str(self.sp_jevery.value()),
                                                files=list(self.jingles)),
                                    fade_in=e["fade_in"].text().strip(), fade_out=e["fade_out"].text().strip())

    # --- entrées audio
    def refresh_devices(self):
        self.dev_status("Recherche des entrées…", ACC2)

        def scan():
            if SYS != "Linux" and not shutil.which("ffmpeg"):
                return self.ui(self.apply_devices, [], "", "ffmpeg introuvable")
            try:
                devs, raw = list_devices()
                self.ui(self.apply_devices, devs, raw, "")
            except Exception as e:
                self.ui(self.apply_devices, [], str(e), "erreur de détection")
        threading.Thread(target=scan, daemon=True).start()

    def dev_status(self, text, col):
        self._dev_scan = (text, col)
        self.source_state(self.engine)

    def source_state(self, e):
        """État de l'entrée, en clair : active, en panne (avec la raison), ou résultat de la détection des entrées."""
        if not hasattr(self, "l_devst"):
            return
        st = getattr(e, "cap_state", "off") if (e and (self.on_air or self.preview)) else "off"
        if st == "ok":
            text, col = f"Entrée active : {dev_short_name(self.cur_device)}", OKC
        elif st == "error":
            text, col = f"Entrée indisponible : {getattr(e, 'cap_err', '') or '?'} · nouvel essai automatique toutes les 2 s", BADC
        elif st == "starting":
            text, col = "Ouverture de l'entrée…", ACC2
        else:
            text, col = getattr(self, "_dev_scan", ("Recherche des entrées…", ACC2))
        key = (text, col)
        if key != getattr(self, "_devst_key", None):
            self._devst_key = key
            esc = str(text).replace("&", "&amp;").replace("<", "&lt;")
            self.l_devst.setText(f"<span style='color:{col}'>●</span>&nbsp;&nbsp;<span style='color:{MUT if st == 'off' else col}'>{esc}</span>")

    def listen_state(self, e):
        b = getattr(self, "btn_listen", None)
        if b is None:
            return
        on = bool(e and getattr(e, "listen", False))
        self.set_kind(b, "■ Arrêter l'écoute" if on else "Écouter l'antenne au casque", "primary" if on else "")

    def toggle_listen(self):
        """Écoute de contrôle : ce qui part à l'antenne (direct, playlist de secours, cartouches) au casque du cartoucheur."""
        e = self.ensure_engine()
        if e is None:
            return
        if not e.listen and not self.prof["carts"].get("device"):
            self.set_cart_devices()
            m = QMenu(self)
            m.addSection("Écouter sur quelle carte son ?")
            for l in out_choices([self.cb_cdev.itemData(i) for i in range(1, self.cb_cdev.count())]):
                m.addAction(dev_icon_pm(out_kind(l), MUT), "  " + out_name(l), lambda l=l: (self.cdev_pick(l), self.toggle_listen()))
            if self.cb_cdev.count() <= 1:
                return info(self, "Écoute", "Aucune carte son de sortie trouvée (module sounddevice requis, voir SOS).")
            return m.exec(QCursor.pos())
        e.set_listen(not e.listen)
        if e.listen:
            self.log("Écoute de l'antenne au casque : " + (self.prof["carts"].get("device") or "?") +
                     ("" if self.on_air else " (le son arrivera dès le démarrage de la diffusion)"))
        self.listen_state(e)

    def apply_devices(self, devs, raw, err_):
        self.dev_list = devs
        self.dev_map = {l: v for l, v in devs}
        self.dev_pick.set_devices(list(self.dev_map))
        loop = any(v.startswith("loopback:") for _, v in devs)
        self.dev_pick.extra = ([("Activer la capture…", self.enable_loopback)]
                               if SYS == "Windows" and not loop else [])
        if hasattr(self, "btn_loop"):
            self.btn_loop.setVisible(SYS == "Windows" and not loop)
        if devs:
            n = len(devs)
            cur = (self.cur_device or "").strip()
            if cur and cur not in self.dev_map.values() and not cur.startswith("lavfi:"):
                self.dev_status(f"L'entrée enregistrée « {dev_short_name(cur)} » n'existe pas sur cet ordinateur : choisis-en une dans la liste", BADC)
            elif not cur:
                self.dev_status(f"{n} entrée{'s' if n > 1 else ''} détectée{'s' if n > 1 else ''} · choisis celle à diffuser", ACC2)
            else:
                self.dev_status(f"{n} entrée{'s' if n > 1 else ''} détectée{'s' if n > 1 else ''}", OKC)
            self.sync_device_selection()
            self.set_cart_devices()
            return
        self.dev_status((err_ or "Aucune entrée détectée") + " · vérifie le branchement puis actualise", BADC)
        self.sync_device_selection()
        if raw.strip():
            self.log("Sortie de ffmpeg : " + " | ".join(raw.strip().splitlines()[-6:]))

    def enable_loopback(self):
        """Capture du son de l'ordinateur (WASAPI loopback) : installe le module si besoin, puis met la liste à jour sans redémarrer."""
        if have_loopback():
            return self.refresh_devices()

        def done():
            importlib.invalidate_caches()
            self.refresh_devices()
            QTimer.singleShot(2500, lambda: self.dev_pick.popup() if any(v.startswith("loopback:") for v in self.dev_map.values()) else
                              self.log("Capture du son de l'ordinateur : le module est installé mais aucune sortie n'est détectée (voir SOS)."))
        self.dev_status("Installation de la capture du son de l'ordinateur…", ACC2)
        self.install("PyAudioWPatch", done)

    def sync_device_selection(self):
        cur = self.cur_device
        lbl = next((k for k, v in self.dev_map.items() if v == cur), None)
        self.dev_pick.set_current(lbl or cur)

    def on_dev_select(self, txt=""):
        txt = (txt or "").strip()
        if txt:
            new = self.dev_map.get(txt, txt)
            changed = new != self.cur_device
            self.cur_device = new
            if self.engine is not None:
                self.engine.set_source(new)               # changement d'entrée immédiat, même pendant l'antenne
            if changed:
                self.prof.setdefault("source", {})["device"] = new
                self._devst_key = None
                n = len(self.dev_map)
                self.dev_status(f"{n} entrée{'s' if n > 1 else ''} détectée{'s' if n > 1 else ''}" if n else "Entrée choisie", OKC)
                if self.on_air:
                    self.log(f"Entrée changée pendant l'antenne : {dev_short_name(new)}")

    def live_gain(self):
        g = self.sl_gain.value()
        self.l_gain.setText(f"{g:+d} dB" if g else "0 dB")
        if self.engine:
            self.engine.set_gain(str(g))

    def live_meta(self):
        if self.engine:
            self.engine.prof_update("meta", follow=self.sw_follow.isChecked())

    def send_meta_now(self):
        if self.engine:
            self.engine.meta_manual = self.ed_meta.text()
            self.log("Titre envoyé : " + (self.ed_meta.text() or "(vide)"))
        else:
            self.log("Titre enregistré : il sera envoyé au démarrage.")

    # --- automate de diffusion : titre, artiste et pochette
    def automate_cfg(self):
        c = self.data.setdefault("automate", {})
        c.setdefault("on", False)
        c.setdefault("file", "")
        c.setdefault("net", True)
        c.setdefault("port", AUTO_PORT)
        c.setdefault("lan", False)
        if not c.get("token"):
            c["token"] = uuid.uuid4().hex[:12]        # code secret de l'adresse (voir AutomateMeta._client)
        if "lan_token" not in c:                      # automate déjà relié par le réseau local : rien ne change pour lui ;
            c["lan_token"] = not c.get("lan")         # sinon, code secret exigé des autres postes
        return c

    def automate_apply(self):
        self.automate.configure(self.automate_cfg())
        self.automate_label()

    def automate_got(self, info):
        """Nouveau titre de l'automate : affiché ici, envoyé aux flux (titre Icecast / RDS / DLS), pochette affichée."""
        if not self.automate_cfg().get("on"):
            return
        self.auto_info = info
        txt = info["text"]
        self.ed_meta.setText(txt)
        if self.engine:
            self.engine.meta_manual = txt
        self.log(f"Automate : « {txt} »" + ("" if self.on_air else " (sera envoyé à l'antenne)"))
        self.automate_label()

    def automate_label(self):
        l = getattr(self, "l_auto", None)
        if l is None:
            return
        c = self.automate_cfg()
        ai = self.auto_info
        if not c.get("on"):
            txt, col = "Automate : non relié", MUT
        elif self.automate.port_err and c.get("net"):
            txt, col = f"Automate : {self.automate.port_err}", BADC
        elif ai:
            age = time.time() - ai["t"]
            when = time.strftime("%H:%M", time.localtime(ai["t"]))
            alb = f"  ·  {ai['album']}" if ai.get("album") else ""
            txt, col = f"● Automate ({ai['source']}, {when}) : {ai['text']}{alb}", (OKC if age < 3600 else ACC2)
        else:
            txt, col = "Automate : en attente d'un premier titre…", ACC2
        if l.text() != txt:
            self.set_label(l, txt, col)

    def automate_dialog(self):
        c = dict(self.automate_cfg())
        d = QDialog(self)
        d.setWindowTitle("Titre en cours depuis un automate")
        d.setMinimumWidth(560)
        v = QVBoxLayout(d)
        v.setContentsMargins(22, 18, 22, 16)
        t = lab("Automate de diffusion", "")
        t.setStyleSheet("font-size:18px;font-weight:700;")
        v.addWidget(t)
        v.addWidget(lab("Bev peut récupérer le titre, l'artiste et la pochette depuis votre automate (Radiologik, RadioDJ, "
                        "Rivendell, mAirList…), les afficher dans « 4 · À l'antenne » et les envoyer à vos flux.", "mut", True))
        sw_on = Switch("Utiliser l'automate")
        sw_on.setChecked(bool(c["on"]))
        v.addWidget(sw_on)
        f = QFormLayout()
        f.setVerticalSpacing(8)
        ed_f = QLineEdit(c["file"])
        ed_f.setPlaceholderText("(facultatif) fichier écrit par l'automate : texte, XML ou JSON")
        rowf = QHBoxLayout()
        rowf.addWidget(ed_f, 1)
        rowf.addWidget(btn("…", "", lambda: ed_f.setText(QFileDialog.getOpenFileName(d, "Fichier du titre en cours", ed_f.text())[0] or ed_f.text())))
        f.addRow("Fichier", rowf)
        sw_net = Switch("Recevoir les titres par le réseau (l'automate appelle une adresse de Bev)")
        sw_net.setChecked(bool(c["net"]))
        f.addRow("", sw_net)
        sp = QSpinBox()
        sp.setRange(1024, 65535)
        sp.setValue(int(c["port"] or AUTO_PORT))
        sp.setMaximumWidth(110)
        f.addRow("Port", sp)
        sw_lan = Switch("Accepter les autres ordinateurs du réseau local (automate sur un autre poste)")
        sw_lan.setChecked(bool(c["lan"]))
        f.addRow("", sw_lan)
        sw_tok = Switch("Exiger le code secret des autres postes (recommandé)")
        sw_tok.setChecked(bool(c.get("lan_token", True)))
        f.addRow("", sw_tok)
        v.addLayout(f)
        ex = QPlainTextEdit()
        ex.setReadOnly(True)
        ex.setMaximumHeight(118)
        v.addWidget(ex)

        def explain(*_):
            host = "127.0.0.1"
            if sw_lan.isChecked():
                try:
                    host = default_route_ip() or host
                except Exception:
                    pass
            base = f"http://{host}:{sp.value()}/"
            sw_tok.setVisible(sw_lan.isChecked())
            tk = f"token={c['token']}&" if (sw_lan.isChecked() and sw_tok.isChecked()) else ""
            ex.setPlainText(f"Adresse à indiquer dans l'automate (envoi à chaque titre) :\n{base}?{tk}artist=ARTISTE&title=TITRE&cover=ADRESSE_POCHETTE\n\n"
                            "Dans Radiologik : réglages de publication du titre en cours (Now Playing), envoi par adresse web, en "
                            "remplaçant ARTISTE, TITRE et ADRESSE_POCHETTE par les balises correspondantes de Radiologik. "
                            "Bev accepte aussi un envoi POST (JSON, formulaire ou texte « Artiste - Titre »), ou un fichier.")
        for w_ in (sw_lan, sw_tok, sp):
            (w_.toggled if isinstance(w_, Switch) else w_.valueChanged).connect(explain)
        explain()
        h = QHBoxLayout()
        h.addWidget(btn("Copier l'adresse", "", lambda: self.copy_text(ex.toPlainText().splitlines()[1], "Adresse")))
        h.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        h.addWidget(bb)
        v.addLayout(h)
        if d.exec():
            cfg = self.automate_cfg()
            cfg.update(on=sw_on.isChecked(), file=ed_f.text().strip(), net=sw_net.isChecked(), port=sp.value(), lan=sw_lan.isChecked(),
                       lan_token=sw_tok.isChecked())
            if not cfg["on"]:
                self.auto_info = None
            self.save_settings()
            self.automate_apply()
            self.log("Automate : " + ("relié." if cfg["on"] else "désactivé."))

    def pick_cover(self):
        f, _ = QFileDialog.getOpenFileName(self, "Pochette par défaut (logo de la radio)", "", "Images (*.png *.jpg *.jpeg *.gif *.bmp);;Tous (*)")
        if f:
            self.cover_path = f
            self.cover_shown = "?"

    # --- pochettes
    def set_cover(self, path):
        if path == self.cover_shown:
            return
        self.cover_shown = path
        if not path:
            return self.show_cover(None)
        if path in self.cover_cache:
            return self.show_cover(self.cover_cache[path])
        threading.Thread(target=lambda: self.ui(self.got_cover, path, cover_png(path)), daemon=True).start()

    def got_cover(self, path, data):
        pm = None
        if data:
            pm = QPixmap()
            if not pm.loadFromData(data):
                pm = None
        if pm is None and os.path.isfile(path) and path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
            pm = QPixmap(path)
            if pm.isNull():
                pm = None
        if len(self.cover_cache) > 60:
            self.cover_cache.clear()
        self.cover_cache[path] = pm
        if self.cover_shown == path:
            self.show_cover(pm)

    def show_cover(self, pm):
        if pm is None:
            if self.cover_pm is None:
                self.cover_pm = default_cover_pm(96)
            pm = self.cover_pm
        self.cover_lbl.setPixmap(pm.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.mini_lbl.setPixmap(pm.scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    # ------------------------------------------------------------ playlist
    def pl_now_idx(self):
        e = self.engine
        cur = e.pl_cur if (e and e.backup) else None
        return cur["i"] if cur else -1

    def pl_img(self, f):
        if f in self.pl_cov:
            return self.pl_cov[f]
        img = self.pl_cov_raw.get(f, 0)
        if img == 0:
            return None
        pm = QPixmap.fromImage(img) if img is not None else None
        self.pl_cov[f] = pm
        return pm

    def pl_rows(self):
        cnt = self.data.get("counts", {})
        q = norm_txt(self.ed_plq.text().strip())
        rows = []
        for i, f in enumerate(self.playlist):
            fo = self.pl_folder.get(f, "")
            if self.pl_view is not None and fo != self.pl_view:
                continue
            inf = self.pl_info.get(f) or {}
            title, dur = inf.get("title") or os.path.splitext(os.path.basename(f))[0], inf.get("dur", 0)
            artist = inf.get("artist", "")
            if not artist and " - " in title:
                artist, title = title.split(" - ", 1)
            if q and q not in norm_txt(title + " " + artist + " " + inf.get("album", "") + " " + fo):
                continue
            rows.append({"i": i, "title": title, "artist": artist, "album": inf.get("album", ""), "dur": dur, "n": cnt.get(f, 0), "off": f in self.pl_off,
                         "folder": fo if self.pl_view is None else "", "img": self.pl_img(f)})
        rows.sort(key=lambda r: (r["off"], r["n"], r["i"]))
        return rows

    def pl_chips_build(self):
        n_of = {}
        for f in self.playlist:
            n_of[self.pl_folder.get(f, "")] = n_of.get(self.pl_folder.get(f, ""), 0) + 1
        items = [("Tous", None, len(self.playlist))] + [(n, n, n_of.get(n, 0)) for n in self.pl_folders]
        if n_of.get("", 0) and self.pl_folders:
            items.append(("Sans dossier", "", n_of[""]))
        self.pl_bar.set_items(items, self.pl_view)
        self.l_plview.setText({None: "Tous les titres", "": "Sans dossier"}.get(self.pl_view, self.pl_view or ""))

    def pl_set_view(self, k):
        self.pl_view = k
        QTimer.singleShot(0, self.pl_refresh)

    def pl_new_folder(self, move=None):
        name = (ask_text(self, "Nouveau dossier", "Nom du dossier (par exemple Jingles, Musique, Émissions) :") or "").strip()
        if not name:
            return None
        if name not in self.pl_folders:
            self.pl_folders.append(name)
        for i in (move or []):
            self.pl_folder[self.playlist[i]] = name
        self.pl_view = name if not move else self.pl_view
        self.pl_refresh()
        return name

    def pl_folder_menu(self, name, pos):
        m = QMenu(self)
        m.addAction("Renommer…", lambda: self.pl_rename_folder(name))
        files = [f for f in self.playlist if self.pl_folder.get(f) == name]
        allout = bool(files) and all(f in self.pl_off for f in files)
        m.addAction("Remettre tout le dossier dans la rotation" if allout else "Exclure tout le dossier de la rotation",
                    lambda: self.pl_folder_rotation(name, allout))
        m.addAction("Supprimer le dossier (garde les titres)", lambda: self.pl_del_folder(name))
        m.exec(pos)

    def pl_rename_folder(self, name):
        new = (ask_text(self, "Renommer", "Nouveau nom :", name) or "").strip()
        if new and new != name and new not in self.pl_folders:
            self.pl_folders[self.pl_folders.index(name)] = new
            self.pl_folder = {f: (new if v == name else v) for f, v in self.pl_folder.items()}
            if self.pl_view == name:
                self.pl_view = new
            self.pl_refresh()

    def pl_folder_rotation(self, name, include):
        for f in self.playlist:
            if self.pl_folder.get(f) == name:
                (self.pl_off.discard if include else self.pl_off.add)(f)
        self.pl_refresh()

    def pl_del_folder(self, name):
        self.toast(f"Dossier « {name} » supprimé (les titres sont gardés)   ·   Ctrl+Z pour annuler")
        if name in self.pl_folders:
            self.pl_folders.remove(name)
        self.pl_folder = {f: v for f, v in self.pl_folder.items() if v != name}
        if self.pl_view == name:
            self.pl_view = None
        self.pl_refresh()

    def pl_move(self, idx, name):
        for i in idx:
            if name:
                self.pl_folder[self.playlist[i]] = name
            else:
                self.pl_folder.pop(self.playlist[i], None)
        self.pl_refresh()

    def pl_refresh(self):
        if not hasattr(self, "pl_tv"):
            return
        todo = [f for f in self.playlist if f not in self.pl_info or f not in self.pl_cov_raw]
        idx = self.pl_now_idx()
        self.pl_sig = (idx, tuple(self.data.get("counts", {}).get(f, 0) for f in self.playlist))
        self.pl_chips_build()
        rows = self.pl_rows()
        self.pl_tv.set(rows, idx)
        tot = sum(r["dur"] for r in rows)
        hh, mn = int(tot // 3600), int(tot // 60 % 60)
        self._plc_txt = f"{len(rows)} titre{'s' if len(rows) > 1 else ''}" + (f" · {hh} h {mn:02d} min" if hh else f" · {mn} min" if tot else "")
        self.l_plc.setText(self._plc_txt)
        self.live_pl()
        if todo and not getattr(self, "_pl_busy", False):
            self._pl_busy = True

            def one(f):
                try:
                    tags, img = track_meta(f, 96)
                    if img is None and shutil.which("ffmpeg"):          # même recherche directe que « Chercher la pochette… »
                        png = _cover_extract(f, 96)
                        q = QImage()
                        if png and q.loadFromData(png):
                            img = square_image(q, 96)
                    if f not in self.pl_info:
                        title, dur = track_info(f) if shutil.which("ffprobe") else (tags.get("title") or "", 0.0)
                        inf = dict(tags)
                        inf["dur"] = dur
                        if not inf.get("title"):
                            if " - " in title and not inf.get("artist"):
                                inf["artist"], inf["title"] = title.split(" - ", 1)
                            else:
                                inf["title"] = title or os.path.splitext(os.path.basename(f))[0]
                        self.pl_info[f] = inf
                    self.pl_cov_raw[f] = img
                except Exception:
                    self.pl_cov_raw.setdefault(f, None)
                    self.pl_info.setdefault(f, {"title": os.path.splitext(os.path.basename(f))[0], "dur": 0})

            def work():
                from concurrent.futures import ThreadPoolExecutor
                try:
                    with ThreadPoolExecutor(4) as ex:
                        for k in range(0, len(todo), 12):
                            list(ex.map(one, todo[k:k + 12]))
                            self.ui(self.pl_redraw_covers)
                finally:
                    self._pl_busy = False
                    self.ui(self.pl_refresh)
            threading.Thread(target=work, daemon=True).start()

    def pl_redraw_covers(self):
        try:
            self.pl_tv.set(self.pl_rows(), self.pl_now_idx())
        except Exception as _ex:
            trace("pl_redraw_covers", _ex)

    def pl_cover_diag(self, i):
        f = self.playlist[i]

        def work():
            er = []
            _, img = track_meta(f, 96)
            if img is None:
                png = _cover_extract(f, 96, err=er)
                if png:
                    q = QImage()
                    img = square_image(q, 96) if q.loadFromData(png) else None
            self.pl_cov_raw[f] = img
            self.pl_cov.pop(f, None)
            if img is not None:
                self.ui(lambda: (self.pl_tv.set(self.pl_rows(), self.pl_now_idx()), info(self, "Pochette", "Pochette trouvée et affichée.")))
            else:
                why = (er[-1] if er else "aucune image trouvée") + ("" if shutil.which("ffmpeg") else "\n(ffmpeg est introuvable dans le PATH)")
                self.ui(lambda: info(self, "Pochette", "Aucune pochette trouvée pour :\n" + os.path.basename(f) + "\n\nDétail : " + why
                                     + "\n\nAstuce : place une image cover.jpg ou folder.jpg dans le dossier du morceau."))
        threading.Thread(target=work, daemon=True).start()

    def pl_infos(self, i):
        f = self.playlist[i]
        inf = dict(self.pl_info.get(f) or {})
        inf["folder"] = self.pl_folder.get(f, "")
        img = self.pl_cov_raw.get(f) or None
        if img is not None:                       # pochette en grand : on la relit à pleine définition
            tags, big = track_meta(f, 300)
            img = big or img
        TrackInfoDialog(self, f, inf, img, self.data.get("counts", {}).get(f, 0)).exec()

    def pl_toggle(self, i):
        sel = self.pl_tv.selection()
        idx = sel if (i in sel and len(sel) > 1) else [i]
        if self.playlist[i] in self.pl_off:
            self.pl_off.difference_update(self.playlist[j] for j in idx)
        else:
            self.pl_off.update(self.playlist[j] for j in idx)
        self.pl_refresh()

    def pl_sel_changed(self, n):
        tot = len(self.pl_tv.rows)
        base = f"{tot} titre{'s' if tot > 1 else ''}"
        self.l_plc.setText(f"{n} sur {tot} sélectionné{'s' if n > 1 else ''}" if n else getattr(self, "_plc_txt", base))
        self.pl_tv.setToolTip("Glisse la sélection sur un dossier pour la ranger · clic droit pour plus d'options" if n else "")

    def pl_menu(self, i, pos):
        m = QMenu(self)
        m.addAction("Jouer maintenant à l'antenne", lambda: self.pl_play(i))
        m.addAction("Pré-écouter au casque", lambda: self.pl_prelisten(i))
        m.addAction("Infos…", lambda: self.pl_infos(i))
        m.addAction("Chercher la pochette…", lambda: self.pl_cover_diag(i))
        m.addAction("Tout sélectionner", lambda: self.pl_tv.select_all(True))
        sel = self.pl_tv.selection() or [i]
        nsel = len(sel) if i in sel else 1
        m.addAction(("Exclure de la rotation" if self.playlist[i] not in self.pl_off else "Remettre dans la rotation")
                    + (f"  ({nsel} titres)" if nsel > 1 else ""), lambda: self.pl_toggle(i))
        mv = m.addMenu("Ranger dans…")
        for n in self.pl_folders:
            mv.addAction(n, lambda n=n: self.pl_move(sel, n))
        if self.pl_folders:
            mv.addSeparator()
        mv.addAction("Nouveau dossier…", lambda: self.pl_new_folder(sel))
        mv.addAction("Aucun dossier", lambda: self.pl_move(sel, ""))
        m.addAction("Retirer de la liste" + (f"  ({len(sel)} titres)" if len(sel) > 1 else ""), self.pl_remove)
        m.exec(pos)

    def pl_drop(self, files):
        n0 = len(self.playlist)
        for p in files:
            if os.path.isdir(p):
                self.pl_import_folder(p, [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith(AUDIO_EXTS)])
                continue
            new = [q for q in ([p] if p.lower().endswith(AUDIO_EXTS) else []) if q not in self.playlist]
            self.playlist += new
            if self.pl_view:
                for q in new:
                    self.pl_folder[q] = self.pl_view
        if len(self.playlist) > n0:
            self.log(f"{len(self.playlist) - n0} titre(s) ajouté(s) à la playlist de secours.")
        self.pl_refresh()

    def live_pl(self):
        if self.engine:
            self.engine.prof_update("fallback", playlist=list(self.playlist), off=sorted(self.pl_off), folder_of=dict(self.pl_folder))

    def pl_play_sel(self):
        sel = self.pl_tv.selection()
        if not sel:
            return info(self, "Playlist", "Clique d'abord sur un morceau de la liste (ou double-clique dessus pour le jouer).")
        self.pl_play(sel[0])

    def pl_play(self, i):
        if not self.on_air:
            return self.pl_prelisten(i)            # hors antenne : double-clic = pré-écoute au casque
        self.live_pl()
        self.engine.pl_stop = False
        self.engine.pl_pause = False
        self.engine.play_now(self.playlist[i])

    def pl_prelisten(self, i):
        """Pré-écoute d'un titre de la playlist de secours au casque (carte son du cartoucheur), sans rien diffuser."""
        f = self.playlist[i]
        e = self.cart_engine(True)
        if e is None:
            return
        inf = self.pl_info.get(f) or {}
        name = "Pré-écoute · " + (inf.get("title") or os.path.splitext(os.path.basename(f))[0])
        if e.cart_playing(-2):
            e.stop_cart(-2, 0.05)
            QTimer.singleShot(120, lambda: e.play_cart(-2, {"file": f, "name": name, "mode": "Par-dessus", "vol": 100, "loop": False}, True))
        else:
            e.play_cart(-2, {"file": f, "name": name, "mode": "Par-dessus", "vol": 100, "loop": False}, True)
        self.log(f"Pré-écoute au casque : {os.path.basename(f)} (Échap ou clic sur la pastille en haut pour arrêter)")

    def pl_import_folder(self, d, paths):
        name = os.path.basename(d.rstrip("/\\")) or d
        new = [q for q in paths if q not in self.playlist]
        if not new:
            return
        if name not in self.pl_folders:
            self.pl_folders.append(name)
        self.playlist += new
        for q in new:
            self.pl_folder[q] = name
        self.pl_view = name
        self.pl_refresh()

    def pl_add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Choisir des fichiers audio", "", "Audio (*.mp3 *.wav *.flac *.ogg *.opus *.m4a *.aac);;Tous (*)")
        new = [f for f in files if f not in self.playlist]
        self.playlist += new
        if self.pl_view:
            for f in new:
                self.pl_folder[f] = self.pl_view
        self.pl_refresh()

    def pl_add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if d:
            paths = [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith(AUDIO_EXTS)]
            self.pl_import_folder(d, paths)

    def pl_reset_counts(self):
        if yes(self, "Compteurs", "Remettre à zéro le nombre de lectures de tous les titres et jingles ?"):
            self.data.setdefault("counts", {}).clear()
            self.pl_refresh()

    def pl_remove(self):
        sel = self.pl_tv.selection()
        for i in sorted(sel, reverse=True):
            self.pl_folder.pop(self.playlist[i], None)
            del self.playlist[i]
        self.pl_refresh()
        if sel:
            self.toast(f"{len(sel)} titre(s) retiré(s) de la playlist   ·   Ctrl+Z pour annuler")

    # ------------------------------------------------------------ flux de sortie
    def refresh_outputs(self):
        if hasattr(self, "fx_rows"):
            self.fx_flux_rows()
        if not hasattr(self, "tb_out"):
            return
        r0 = self.tb_out.currentRow()
        self.tb_out.setRowCount(len(self.outputs_cfg))
        for r, c in enumerate(self.outputs_cfg):
            ico, l = KINDS[c["type"]]
            vals = ("", f"{ico} {l}".strip(), c["name"], self.describe(c), "○ Arrêté")
            for k, t in enumerate(vals):
                it = QTableWidgetItem(t)
                it.setData(Qt.ItemDataRole.UserRole, c["id"])
                if k == 0:
                    it.setData(CHECK_ROLE, bool(c.get("enabled", True)))
                    it.setToolTip("Actif : ce flux part au démarrage de la diffusion")
                self.tb_out.setItem(r, k, it)
        if 0 <= r0 < len(self.outputs_cfg):
            self.tb_out.selectRow(r0)

    def sel_output(self):
        r = self.tb_out.currentRow()
        return self.outputs_cfg[r] if 0 <= r < len(self.outputs_cfg) else None

    def select_output_id(self, oid):
        for r, c in enumerate(self.outputs_cfg):
            if c["id"] == oid:
                self.tb_out.selectRow(r)

    def on_tree_click(self, r, col):
        if col == 0 and 0 <= r < len(self.outputs_cfg):
            c = self.outputs_cfg[r]
            c["enabled"] = not c.get("enabled", True)
            self.tb_out.item(r, 0).setData(CHECK_ROLE, c["enabled"])
            self.live_enable(c)

    def add_output(self, kind):
        d = OutputDialog(self, new_output(kind))
        if d.exec() and d.result:
            self.outputs_cfg.append(d.result)
            self.refresh_outputs()
            self.select_output_id(d.result["id"])
            if self.apply_live(d.result):
                self.log(f"« {d.result['name']} » ajouté et lancé tout de suite.")

    def edit_output(self):
        c = self.sel_output()
        if not c:
            return
        d = OutputDialog(self, c)
        if d.exec() and d.result:
            self.outputs_cfg[self.outputs_cfg.index(c)] = d.result
            self.refresh_outputs()
            self.select_output_id(d.result["id"])
            if self.apply_live(d.result):
                self.log(f"« {d.result['name']} » : réglages appliqués tout de suite (reconnexion du flux).")

    @staticmethod
    def mount_ext(c):
        m = os.path.splitext(c.get("mount", ""))[1]
        if m:
            return m
        f = str(c.get("format", "")).lower()
        return next((e for k, e in (("mp3", ".mp3"), ("aac", ".aac"), ("ogg", ".ogg"), ("opus", ".opus")) if k in f), "")

    def free_mount(self, mount, skip=None):
        used = {c.get("mount") for c in self.outputs_cfg if c["type"] == "internet" and c is not skip}
        base, ext = os.path.splitext(mount)
        m, i = mount, 2
        while m in used:
            m, i = f"{base}-{i}{ext}", i + 1
        return m

    def new_plateau(self):
        base = next((c for c in self.outputs_cfg if c["type"] == "internet" and c.get("protocol") != "Shoutcast"), None)
        if not base:
            return info(self, "Plateau extérieur", "Crée d'abord un flux Internet (Icecast) : le plateau en reprend le serveur, le mot de passe et le format.")
        name = ask_text(self, "Nouveau plateau", "Nom du plateau (par exemple : Festival scène 2) :")
        if not name or not name.strip() or not slugify(name):
            return
        n = json.loads(json.dumps(base))
        n["id"], n["name"] = uuid.uuid4().hex[:8], "Plateau · " + name.strip()
        n["mount"] = self.free_mount("/" + slugify(name) + self.mount_ext(base))
        self.outputs_cfg.append(n)
        self.refresh_outputs()
        self.select_output_id(n["id"])
        live = self.apply_live(n)
        self.log(f"Plateau créé : {n['name']} → {listen_url(n)}" + (" (lancé tout de suite)" if live else ""))
        self.show_address(n)

    def rename_mount(self):
        c = self.sel_output()
        if not c or c["type"] != "internet" or c.get("protocol") == "Shoutcast":
            return info(self, "Adresse", "Choisis d'abord un flux Internet (Icecast) dans la liste.")
        new = ask_text(self, "Changer l'adresse", "Nouveau nom de l'adresse (point de montage) :", c.get("mount", "/live").lstrip("/"))
        if not new or not slugify(new):
            return
        c["mount"] = self.free_mount("/" + slugify(new), skip=c)
        self.refresh_outputs()
        self.select_output_id(c["id"])
        live = self.apply_live(c)
        self.log(f"Adresse de « {c['name']} » : {listen_url(c)}" + (" (appliquée tout de suite)" if live else ""))
        self.show_address(c)

    def apply_live(self, c):
        if self.on_air and self.engine and not self.preview:
            cfg = json.loads(json.dumps(c))
            threading.Thread(target=lambda: self.engine.swap_output(cfg), daemon=True).start()
            return True
        return False

    def show_address(self, c):
        url = listen_url(c)
        d = QDialog(self)
        d.setWindowTitle("Adresse d'écoute")
        v = QVBoxLayout(d)
        v.setContentsMargins(22, 18, 22, 16)
        t = lab(c["name"], "")
        t.setStyleSheet("font-size:17px;font-weight:700;")
        v.addWidget(t)
        m = lab("Donne cette adresse aux auditeurs. Le flux part dès qu'il est connecté au serveur : tant qu'il est arrêté, l'adresse répond « 404 ».", "mut", True)
        m.setMinimumWidth(520)
        v.addWidget(m)
        e = QLineEdit(url)
        e.setReadOnly(True)
        v.addWidget(e)
        v.addWidget(lab("Le serveur doit accepter ce nom d'adresse avec le mot de passe source (c'est le cas d'un Icecast standard).", "mut", True))
        h = QHBoxLayout()
        h.addWidget(btn("Copier l'adresse", "primary", lambda: self.copy_text(url, "Adresse")))
        h.addWidget(btn("Ajouter au monitoring", "", lambda: (self.mon_add(c["name"], url), d.accept())))
        h.addStretch(1)
        h.addWidget(btn("Fermer", "", d.accept))
        v.addLayout(h)
        d.exec()

    def dup_output(self):
        c = self.sel_output()
        if c:
            n = json.loads(json.dumps(c))
            n["id"], n["name"] = uuid.uuid4().hex[:8], c["name"] + " (copie)"
            self.outputs_cfg.append(n)
            self.refresh_outputs()

    def del_output(self):
        c = self.sel_output()
        if c and yes(self, "Supprimer", f"Supprimer le flux « {c['name']} » ?"):
            self.outputs_cfg.remove(c)
            self.live_remove(c["id"])
            self.refresh_outputs()
            self.update_ui(self.engine)
            self.toast(f"Flux « {c['name']} » supprimé   ·   Ctrl+Z pour annuler")

    def live_remove(self, oid):
        """Retire tout de suite un flux de l'antenne en cours : bandeau, compteurs et alertes sont à jour immédiatement."""
        e = self.engine
        if not (e and self.on_air):
            return
        o = e.output(oid)
        if o:
            e.remove_output(oid)
            self.prob_since = {k: v for k, v in getattr(self, "prob_since", {}).items() if k != "out-" + oid}
            self.log(f"Flux « {o.cfg['name']} » retiré de l'antenne.")

    def live_enable(self, c):
        """Case « Actif » cochée / décochée pendant l'antenne : le flux démarre ou s'arrête sans attendre."""
        e = self.engine
        if not (e and self.on_air):
            return
        if c.get("enabled", True):
            self.apply_live(c)
            self.log(f"Flux « {c['name']} » activé : connexion…")
        else:
            self.live_remove(c["id"])

    def toggle_selected(self):
        c = self.sel_output()
        if not (c and self.on_air):
            return info(self, "Flux", "Sélectionne un flux pendant la diffusion.")
        o = self.engine.output(c["id"])
        if o:
            o.stop() if o.state != "stopped" else o.start()

    # ------------------------------------------------------------ démarrage / arrêt
    def toggle(self):
        if self.on_air:
            if self.data.get("settings", {}).get("confirm_stop") and not yes(self, "Arrêter l'antenne", "Arrêter la diffusion maintenant ?"):
                return
            self.stop()
        else:
            self.start()

    def start(self):
        prof = json.loads(json.dumps(self.collect_profile()))
        if not shutil.which("ffmpeg"):
            return err(self, "ffmpeg", "ffmpeg est introuvable (voir onglet SOS).")
        outs = [o for o in prof["outputs"] if o.get("enabled", True)]
        if not outs:
            return info(self, "Flux", "Ajoute et coche (Actif) au moins un flux dans « 2 · Flux ».")
        for o in outs:
            if o["type"] == "internet" and not o["password"]:
                return info(self, "Mot de passe", f"Renseigne le mot de passe de « {o['name']} » (bouton Modifier).")
        if prof["fallback"]["enabled"] and not [f for f in prof["fallback"]["playlist"] if f not in set(prof["fallback"].get("off") or [])]:
            return info(self, "Playlist de secours", "La relève automatique est activée mais la playlist de secours est vide : "
                                                     "ajoute des titres (bouton ＋ Ajouter), ou désactive la relève.")
        dev = (prof["source"].get("device") or "").strip()
        if not dev:
            return info(self, "Entrée audio", "Choisis d'abord l'entrée audio à diffuser dans « 1 · Source audio ».")
        known = set(self.dev_map.values())
        if known and dev not in known and not dev.startswith("lavfi:"):
            if not yes(self, "Entrée audio introuvable",
                       f"L'entrée « {dev_short_name(dev)} » n'existe pas sur cet ordinateur (ou elle est débranchée).\n\n"
                       "Sans elle, les flux partiront en silence. Choisis la bonne entrée dans « 1 · Source audio ».\n\n"
                       "Démarrer quand même ?"):
                return
        self.save_all()
        e = self.ensure_engine()
        if e is None:
            return err(self, "Moteur audio", "Le moteur audio n'a pas pu démarrer (voir SOS > Journal).")
        self._out_down, self._air_beeped = {}, set()
        if e.monitor:                                   # pendant l'antenne l'entrée est affichée de toute façon
            e.set_monitor(False)
        e.set_air(True, prof)
        self.log(f"Diffusion démarrée ({len(outs)} flux). Mat eo, bonne émission !")
        self.update_ui(e)

    def stop(self):
        e = self.engine
        if e and self.on_air:
            e.set_air(False)
            self.log("Diffusion arrêtée. Kenavo !")
            self.update_ui(e)

    # ------------------------------------------------------------ moteur audio (permanent, dans un processus séparé)
    def prewarm(self):
        """Prépare en arrière-plan le processus moteur (lancé une seule fois, au démarrage de l'application)."""
        if self._closing or self._proc_off or not self.data.get("settings", {}).get("engine_proc", True):
            return
        if getattr(self, "slot", None) is None or (self.slot.ready.is_set() and not self.slot.alive()):
            self.slot = WorkerSlot()

    def take_slot(self, wait=10):
        sl = getattr(self, "slot", None)
        if sl is None:
            self.prewarm()
            sl = self.slot
        if sl is None:
            return None
        if not sl.ready.is_set():
            t0 = time.time()
            while not sl.ready.is_set() and time.time() - t0 < wait:       # premier lancement juste après l'ouverture
                QApplication.processEvents()
                sl.ready.wait(.03)
        self.slot = None
        if sl.alive():
            return sl
        sl.close()
        self._proc_fail = getattr(self, "_proc_fail", 0) + 1
        why = sl.error or ("toujours en préparation" if not sl.ready.is_set() else "arrêté")
        self._proc_off = True
        self.log(f"Moteur audio séparé indisponible ({why}) : le moteur tourne dans l'application pour cette session.")
        return None

    def make_engine(self, prof, alert, standalone=False):
        if self.data.get("settings", {}).get("engine_proc", True) and not self._proc_off:
            sl = self.take_slot()
            if sl is not None:
                return EngineProxy(sl, prof, self.log, alert, False, on_dead=lambda p: self.ui(self.engine_died, p))
        return Engine(prof, self.log, alert)

    def ensure_engine(self):
        """Le moteur permanent (créé au premier besoin s'il n'est pas déjà là)."""
        e = self.engine
        if e is not None and e.running:
            return e
        if self._closing:
            return None
        prof = json.loads(json.dumps(self.collect_profile()))
        e = self.make_engine(prof, self.alerts.send)
        self.engine = e
        e.start()
        return e

    def core_boot(self):
        """Au lancement : dès que le processus moteur est prêt, le moteur démarre (Démarrer et cartouches sont instantanés)."""
        if self.engine is not None or self._closing:
            return
        sl = getattr(self, "slot", None)
        if sl is not None and not sl.ready.is_set() and time.time() - self._boot_t0 < 25:
            QTimer.singleShot(150, self.core_boot)
            return
        self.ensure_engine()

    def worker_pids(self):
        pids = set()
        e, sl = self.engine, getattr(self, "slot", None)
        if isinstance(e, EngineProxy) and e.pid:
            pids.add(e.pid)
        if sl is not None and sl.pid:
            pids.add(sl.pid)
        if sl is not None and sl.proc is not None:
            pids.add(sl.proc.pid)
        return pids

    def engine_died(self, p, why="arrêté brutalement"):
        """Le processus moteur a disparu (ou ne répond plus) : on le remplace aussitôt (moteur dans l'application), et si
        l'antenne était en cours, elle repart tout de suite pour ne pas laisser les auditeurs sans son."""
        if self.engine is not p:
            return
        s = getattr(p, "_s", None) or {}
        air = bool(s.get("air", getattr(p, "air", False)))
        mon = bool(s.get("monitor", getattr(p, "monitor", False)))
        lis = bool(s.get("listen", getattr(p, "listen", False)))
        try:
            p._slot.close()
        except Exception:
            pass
        try:
            p.stop()
        except Exception:
            pass
        self.engine = None
        self._proc_off = True
        if self._closing:
            return
        e = self.ensure_engine()
        if e is None:
            return
        if mon:
            e.set_monitor(True)
        if lis:
            e.set_listen(True)
        if air:
            self.log(f"⚠ Le moteur audio s'est {why} : redémarrage immédiat de l'antenne.")
            self.alerts.send(f"Moteur audio {why} : antenne relancée automatiquement.", "engine-crash", sound=True)
            self._out_down = {}
            e.set_air(True, json.loads(json.dumps(self.collect_profile())))
        else:
            self.log(f"Le moteur audio s'est {why} : il a été relancé.")

    def toggle_preview(self):
        if self.on_air:
            return info(self, "Contrôle d'entrée", "Pendant la diffusion, l'entrée est déjà affichée en permanence.")
        e = self.ensure_engine()
        if e is None:
            return
        on = not e.monitor
        e.set_monitor(on)
        self.log("Contrôle d'entrée : le niveau s'affiche, rien n'est diffusé." if on else "Contrôle d'entrée arrêté.")
        self.update_ui(e)

    def start_cart_engine(self):
        return self.ensure_engine()

    def pl_play_pause(self):
        """Lecture : lance la playlist de secours (ou la reprend si elle est en pause). Pause : la fige à l'antenne."""
        e = self.engine
        if not (e and self.on_air):
            return info(self, "Playlist de secours", "Démarre d'abord la diffusion.")
        if not self.playlist:
            return info(self, "Playlist de secours", "Ajoute au moins un morceau à la playlist de secours.")
        if e.backup and not e.pl_pause:
            e.pl_pause = True
            self.log("Playlist de secours en pause.")
        elif e.backup:
            e.pl_pause = False
            self.log("Playlist de secours : reprise.")
        else:
            e.pl_stop = False
            e.pl_pause = False
            e.set_manual(True)

    def pl_stop_btn(self):
        e = self.engine
        if not (e and self.on_air):
            return
        e.pl_pause = False
        e.pl_stop = True
        e.manual = False

    def toggle_manual(self):
        e = self.engine
        if not (e and self.on_air and self.playlist):
            return info(self, "Playlist de secours", "Démarre la diffusion avec au moins un fichier dans la playlist.")
        e.set_manual(not e.manual)

    # ------------------------------------------------------------ Cartoucheur : réglages généraux
    def set_cart_devices(self):
        try:
            outs = list_output_devices()
        except Exception:
            outs = []
        cur = self.prof["carts"].get("device", "")
        self._cart_outs = [l for l, _ in outs]             # cartes réellement branchées (la carte choisie peut être débranchée)
        self.cb_cdev.blockSignals(True)
        self.cb_cdev.clear()
        self.cb_cdev.addItem(NODEV, "")
        for l, _ in outs:
            self.cb_cdev.addItem(l, l)
        i = self.cb_cdev.findData(cur)
        if i < 0 and cur:
            self.cb_cdev.addItem(cur, cur)
            i = self.cb_cdev.count() - 1
        self.cb_cdev.setCurrentIndex(max(0, i))
        self.cb_cdev.blockSignals(False)
        if hasattr(self, "b_cdev"):
            self.cdev_label()

    def sync_cart_device(self):
        d = self.prof["carts"].get("device", "")
        i = self.cb_cdev.findData(d)
        if i < 0 and d:
            self.cb_cdev.addItem(d, d)
            i = self.cb_cdev.count() - 1
        self.cb_cdev.blockSignals(True)
        self.cb_cdev.setCurrentIndex(max(0, i))
        self.cb_cdev.blockSignals(False)
        if hasattr(self, "b_cdev"):
            self.cdev_label()

    def cart_dev_changed(self, i):
        self.prof["carts"]["device"] = self.cb_cdev.currentData() or ""
        if self.engine:
            self.engine.cmon.set_device(self.prof["carts"]["device"])
        self.cdev_label()

    def fc_changed(self, v):
        self.prof["carts"]["fade_click"] = v / 10.0
        self.l_fc.setText("direct" if v == 0 else f"{v / 10:.1f} s".replace(".", ","))
        if self.engine:
            self.engine.prof_update("carts", fade_click=v / 10.0)

    # ------------------------------------------------------------ boucle d'affichage
    def tick(self):
        if hasattr(self, "res"):
            self.res.frame()
        Gov.frame(self.isVisible() and not self.isMinimized())
        Ticker.get().tick()
        e = self.engine
        if e and not e.running:
            if not self._closing:
                QTimer.singleShot(0, lambda e=e: self.engine_died(e))
            e = None
        self.slow_n += 1
        pin, pout, clip = [-90.0, -90.0], [-90.0, -90.0], False
        now = time.time()
        if e:
            pin, pout = list(e.in_peak), list(e.peak)
            e.in_peak[:] = [-90.0, -90.0]
            e.peak[:] = [-90.0, -90.0]
            clip = now - e.clip_t < 3
            # à 60 i/s, une image peut tomber entre deux blocs audio (20 ms) : on garde alors la dernière mesure
            if max(pin + pout) <= -90 and now - self._pk[2] < .06:
                pin, pout = list(self._pk[0]), list(self._pk[1])
            elif max(pin + pout) > -90:
                self._pk = (list(pin), list(pout), now)
        if not self._live_any:                  # crête-mètre antenne : seulement si un flux est vraiment en ligne
            pout, clip = [-90.0, -90.0], False
        try:
            thr = float(self.fb_ed["threshold"].text())
        except ValueError:
            thr = None
        thr = thr if self.sw_fb.isChecked() else None
        self.mini_in.set(pin, thr)
        self.mini_out.set(pout, None, clip)
        if self.page_key == "diff":
            self.meter_in.set(pin, thr)
            self.meter.set(pout, None, clip)
            if self.slow_n % 3 == 0:
                self.wave.push(max(pout))
        if self.slow_n % 6 == 0:
            self.clock_tick()
            self.update_ui(e)
        elif self.slow_n % 6 == 3:              # seconde moitié des mises à jour, décalée : pas de pic sur une seule image
            self.update_ui2(self.engine)
        if self.slow_n % 2 == 0:                               # cartouche lue (en-tête) et cartoucheur : 30 i/s
            st = e.cart_status()[0] if e else {}
            self.cart_now_update(st)
            if self.page_key == "cart":
                self.cart_strip(e, st)
            elif self.page_key == "son":
                self.son_tick(e)

    def update_ui(self, e):
        if isinstance(e, EngineProxy) and e.running and not e._stopping and time.time() - e._s["t"] > 6:
            self.engine_died(e, "bloqué (plus de nouvelles depuis 6 s)")
            return
        n_live = n_all = 0
        if self.on_air and e:
            outs = [o for o in e.outputs if o.cfg.get("enabled", True)]
            n_all = len(outs)
            n_live = sum(1 for o in outs if o.state == "live")
        self._live_any = bool(self.on_air and n_live > 0)
        note = "" if self._live_any else ("aucun flux en ligne" if self.on_air else ("rien n'est diffusé" if self.preview else ""))
        self.meter.note = note
        self.mini_out.note = note
        self.nav_w.set_air(n_live > 0)
        if self.bot_btn:
            self.bot_btn.air = n_live > 0
        if self.on_air:
            # couleur selon l'état : rouge = tous les flux passent ; orange = un flux (ou plus) est HS ;
            # jaune = la playlist de secours est à l'antenne ; rouge sombre = aucun flux ne passe
            live_names = [o.cfg.get("name") or "flux" for o in outs if o.state == "live"]
            hs = [o.cfg.get("name") or "flux" for o in outs if o.state == "error"]
            dur = fmt_dur(time.time() - e.started)
            if n_live and e.backup:
                head, mode = f"SECOURS  {dur}", "secours"
            elif n_live and hs:
                head, mode = f"{len(hs)} FLUX HS  {dur}", "partial"
            elif n_live:
                head, mode = f"EN ANTENNE  {dur}", "air"
            elif any(o.state == "connecting" for o in e.outputs):
                head, mode = "Connexion des flux…", "wait"
            else:
                head, mode = "Aucun flux en ligne", "bad"
            tip = ("À l'antenne : " + (", ".join(live_names) or "aucun flux")) + (("\nHS : " + ", ".join(hs)) if hs else "") + \
                  ("\nLa playlist de secours est à l'antenne." if e.backup else "")
            if self.l_air.toolTip() != tip:
                self.l_air.setToolTip(tip)
            self.l_air.set_mode(mode)
            self.set_label(self.l_air, head, TXT)
            if self.l_air.fontMetrics().horizontalAdvance(head) + 12 > self.l_air.width():
                self.fit_air_label(head)
            self.set_kind(self.btn_start, "Arrêter", "stop")
        else:
            self.l_air.set_mode("preview" if self.preview else "off")
            if self.l_air.toolTip():
                self.l_air.setToolTip("")
            self.set_label(self.l_air, "Contrôle d'entrée" if self.preview else "Hors antenne", MUT)
            self.set_kind(self.btn_start, "Démarrer", "primary")
        if self.on_air:
            self.btn_prev.setText("● Entrée affichée")
            self.btn_prev.setEnabled(False)
        else:
            self.btn_prev.setText("■ Arrêter le contrôle" if self.preview else "Voir l'entrée")
            self.btn_prev.setEnabled(True)
        self.source_state(e)
        self.listen_state(e)
        for r, c in enumerate(self.outputs_cfg):
            if r >= self.tb_out.rowCount():
                break
            o = e.output(c["id"]) if (e and not self.preview) else None
            st = o.state if o else "stopped"
            cfg_on = c.get("enabled", True)
            txt = o.status_text() if o else ("○ Arrêté" if cfg_on else "— Désactivé")
            if o is None and not cfg_on:
                st = "off"
            it = self.tb_out.item(r, 4)
            if it is not None:
                if it.text() != txt:
                    it.setText(txt)
                col = {"live": OKC, "error": "#e5485a", "connecting": ACC2, "stopped": "#7f8c8d", "off": "#566074"}.get(st, TXT)
                if it.foreground().color().name() != QColor(col).name():
                    it.setForeground(QColor(col))
        self.flux_summary(e)
        self.rupture_ui(e, n_live, n_all)
        self.update_nowbar(e)
        if not e:
            self.set_label(self.l_sig, "Signal : -", MUT)
            self.set_label(self.l_now, "Titre : -", MUT)
            self.btn_manual.setText("Lancer la playlist")
            return
        self.btn_manual.setText("Revenir au direct" if (e.manual and self.on_air) else "Lancer la playlist")
        playing = bool(e.backup and self.on_air and not getattr(e, "pl_pause", False))
        k = "pause" if playing else "play"
        if self.btn_plpause.kind != k:
            self.btn_plpause.kind = k
            self.btn_plpause.setToolTip("Mettre la playlist de secours en pause" if playing else
                                        ("Reprendre la playlist de secours" if e.backup else "Lancer la playlist de secours à l'antenne"))
            self.btn_plpause.update()
        p = e.fb_params()
        covered = bool(p["enabled"] and p["files"])
        cap = getattr(e, "cap_state", "ok")
        if not (self.on_air or self.preview):
            self.set_label(self.l_sig, "Signal : entrée fermée (clique « Voir l'entrée » pour la contrôler)", MUT)
        elif cap == "error":
            self.set_label(self.l_sig, "✕ Entrée audio indisponible : voir « 1 · Source audio »", BADC)
        elif e.backup and self.on_air:
            if e.manual:
                txt = "Playlist de secours lancée à la main · « Revenir au direct » pour reprendre l'entrée"
            elif e.silent_ms < 1000 and e.loud_ms > 0:
                txt = f"Playlist de secours · le son revient : retour au direct dans {max(0.0, e.rec_ms - e.loud_ms) / 1000:.0f} s"
            else:
                txt = "Playlist de secours à l'antenne · retour au direct dès que le son revient"
            self.set_label(self.l_sig, txt, ACCT)
        elif e.silent_ms >= 1000:
            sec = e.silent_ms // 1000
            if not self.on_air:
                txt = f"● Aucun signal depuis {sec} s"
            elif covered:
                left = max(0, int(math.ceil((p["delay"] - e.silent_ms) / 1000)))
                txt = f"● Aucun signal depuis {sec} s · la playlist de secours prend le relais dans {left} s"
            elif p["enabled"]:
                txt = f"● Aucun signal depuis {sec} s · playlist de secours vide : rien ne prendra le relais"
            else:
                txt = f"● Aucun signal depuis {sec} s · relève automatique désactivée"
            self.set_label(self.l_sig, txt, BADC)
        else:
            self.set_label(self.l_sig, "● Signal détecté" + ("" if not self.on_air else
                           (f" · relève après {p['delay'] / 1000:g} s de silence" if covered else " · pas de relève automatique")), OKC)
        flags = ("  MUTE" if e.mute else "") + ("  TON" if e.tone else "")
        self.set_label(self.l_now, ("Titre : " + (e.meta or "-")) + flags, TXT)
        self.automate_label()
        if self.slow_n % 20 == 0 and self.page_key == "rec":
            self.rec_tick()
        elif self.slow_n % 20 == 0 and self.on_air:
            self.rec_tick()

    def update_ui2(self, e):
        if e:
            self.check_outages(e)
            ci = getattr(e, "counts_in", None) if isinstance(e, EngineProxy) else (dict(e.counts()) if self.on_air else None)
            if ci and ci is not getattr(self, "_counts_seen", None):
                self._counts_seen = ci
                d = self.data.setdefault("counts", {})
                for k, v in ci.items():
                    if v > d.get(k, 0):
                        d[k] = v
        self.update_playlist_visuals(e)
        self.update_enabled(e)
        self.update_health(e)

    @staticmethod
    def en(w, on, why=""):
        """Active / grise un contrôle (sans retoucher s'il est déjà dans le bon état), avec la raison en infobulle."""
        on = bool(on)
        if w.isEnabled() != on:
            w.setEnabled(on)
            if why or on:
                w.setProperty("_tip", w.property("_tip") if w.property("_tip") is not None else w.toolTip())
                w.setToolTip(w.property("_tip") if on else why)

    def update_enabled(self, e):
        """Grise ce qu'on ne peut pas modifier dans la situation présente."""
        air = self.on_air
        self.en(self.btn_prof, not air, "Arrête la diffusion pour changer de profil")
        sel = self.sel_output() is not None
        for b in getattr(self, "flux_btns", []):
            self.en(b, sel, "Choisis d'abord un flux dans la liste")
        self.en(self.btn_run_out, sel and air, "Pendant la diffusion, choisis un flux pour le couper ou le relancer")
        has_sel = bool(self.pl_tv.sel)
        self.en(self.btn_plrem, has_sel, "Sélectionne des titres à retirer")
        self.en(self.btn_playsel, has_sel and air, "Démarre la diffusion et sélectionne un titre")
        self.en(self.btn_manual, air and bool(self.playlist), "Démarre la diffusion avec au moins un titre dans la playlist de secours")
        self.en(self.btn_plpause, air and bool(self.playlist), "Démarre la diffusion avec au moins un titre dans la playlist de secours")
        self.en(self.btn_plstop, air and bool(e and (e.backup or e.manual)), "La playlist de secours n'est pas à l'antenne")
        if hasattr(self, "al_testb"):
            self.en(self.al_testb, bool(self.alerts.channels()), "Configure d'abord un mail, un SMS ou un message")
        if hasattr(self, "btn_lstop"):
            self.en(self.btn_lstop, self.listen_proc is not None, "Aucune écoute en cours")
        if hasattr(self, "gray_net"):
            ok = self.net_sel() is not None
            for b in self.gray_net:
                self.en(b, ok, "Choisis d'abord une connexion dans la liste")

    @staticmethod
    def set_label(l, text, color):
        if l.text() != text:
            l.setText(text)
        if isinstance(l, CLabel):
            l.set_color(color)
            return
        ss = f"color:{color};" + ("font-weight:700;" if l.objectName() == "" and l.styleSheet().find("font-weight:700") >= 0 else "")
        if l.property("_c") != color:
            l.setProperty("_c", color)
            l.setStyleSheet(ss)

    @staticmethod
    def set_kind(b, text, kind):
        if b.text() != text:
            b.setText(text)
        if b.property("kind") != kind:
            b.setProperty("kind", kind)
            b.style().unpolish(b)
            b.style().polish(b)

    def rupture_ui(self, e, n_live, n_all):
        """Deux alertes bien distinctes, stables (pas de clignotement, un seul bip par panne) :
        ROUGE = rupture de flux (un flux actif n'est plus en ligne depuis 6 s : les auditeurs ne reçoivent plus l'antenne) ;
        ORANGE = silence à l'antenne (plus de son en entrée et rien ne prend le relais) ;
        JAUNE = la playlist de secours est à l'antenne : cadre jaune autour de l'application, comme le rouge, sans bip."""
        now = time.time()
        bad, silent = [], None
        down = self._out_down
        if self.on_air and e:
            ids = set()
            for o in e.outputs:
                if not o.cfg.get("enabled", True):
                    continue
                oid = o.cfg.get("id")
                ids.add(oid)
                seen = self._air_beeped                     # (on y range aussi les flux déjà passés en ligne)
                if o.state == "live":
                    down.pop(oid, None)
                    seen.add("live-" + oid)
                elif now - down.setdefault(oid, now) >= (6 if "live-" + oid in seen else 15):
                    bad.append(o.cfg.get("name") or "flux")   # 6 s après une coupure ; 15 s pour la toute première connexion
            for k in [k for k in down if k not in ids]:
                down.pop(k, None)
            p = e.fb_params()
            covered = bool(p["enabled"] and p["files"])
            if e.backup:
                silent = "backup"
            elif not e.mute and e.silent_ms >= 5000 and (not covered or e.silent_ms >= p["delay"] + 4000):
                silent = "dead"
        else:
            down.clear()
        kind = "flux" if bad else ("son" if silent == "dead" else ("secours" if silent == "backup" else None))
        if kind:
            if kind == "flux":
                c, fg = "#c4263a", "white"
                hs = ", ".join(bad[:4]) + (f" (+{len(bad) - 4})" if len(bad) > 4 else "")
                ok_n = [o.cfg.get("name") or "flux" for o in e.outputs if o.cfg.get("enabled", True) and o.state == "live"]
                txt = (f"⚠  RUPTURE DE FLUX  ·  HS : {hs}  ·  " +
                       (f"toujours à l'antenne : {', '.join(ok_n[:3])}" + (" …" if len(ok_n) > 3 else "") if ok_n
                        else "plus aucun flux ne part : les auditeurs n'entendent plus l'antenne") +
                       "  ·  reconnexion automatique en cours")
                if silent == "dead":
                    txt += "  ·  et pas de son en entrée"
            elif kind == "son":
                c, fg = "#e8640f", "white"
                p = e.fb_params()
                why = ("la playlist de secours est désactivée" if not p["enabled"] else
                       "la playlist de secours est vide" if not p["files"] else "la playlist de secours n'a pas pu démarrer")
                txt = f"⚠  SILENCE À L'ANTENNE  ·  aucun son en entrée depuis {e.silent_ms // 1000} s  ·  {why}"
            else:
                c, fg = SECOURS_Y, "#2a2200"
                txt = "PLAYLIST DE SECOURS À L'ANTENNE"
            self.banner.set_colors(c, fg)
            if self.banner.text() != txt:
                self.banner.setText(txt)
        if kind != getattr(self, "alert_kind", None):
            prev = getattr(self, "alert_kind", None)
            self.alert_kind = kind
            self.banner.setVisible(bool(kind))
            border = {"flux": "#ff4d5e", "son": "#ff7a1a", "secours": SECOURS_Y}.get(kind)
            self.centralWidget().set_border(border)
            if kind in ("flux", "son"):
                if kind not in self._air_beeped:            # un seul bip par panne (la sirène, si elle est cochée, répète)
                    self._air_beeped.add(kind)
                    if self.data.get("alerts", {}).get("sound", True):
                        self.alerts.beep()
                self.log("⚠ Rupture de flux : " + ", ".join(bad) if kind == "flux" else
                         f"⚠ Silence à l'antenne depuis {e.silent_ms // 1000} s : rien ne prend le relais.")
            elif prev in ("flux", "son"):
                self.log("Antenne rétablie.")
            if kind not in ("flux", "son"):
                self._air_beeped.difference_update({"flux", "son"})
        self.alert_on = kind == "flux"
        self.onair_chip(e, bad)
        air = bool(self.on_air)                           # hors antenne : le phare reste éteint et immobile
        mode = (kind if kind in ("flux", "son", "secours") else False) if air else False
        self.air_fx.set(bool(air and n_live > 0), mode)
        if hasattr(self.nav_w, "set_alert"):
            self.nav_w.set_alert(mode if (air and (n_live > 0 or mode)) else False)

    def onair_chip(self, e, bad):
        """Bandeau : sonie de sortie (banque principale à l'antenne ; entrée traitée pendant le contrôle d'entrée)."""
        w = getattr(self, "loud", None)
        if w is None:
            return
        pm = {}
        if e is not None and (self.on_air or self.preview):
            pm = (getattr(e, "pm_main", None) or getattr(e, "pm", None) or {}) if self.on_air else (getattr(e, "pm", None) or {})
        what = "" if not pm else ("ANTENNE" if self.on_air else "ENTRÉE")
        w.set(pm.get("lufs"), pm.get("lufs_m"), bool(pm), what)

    def update_playlist_visuals(self, e):
        cur = e.pl_cur if (e and e.backup) else None
        idx = cur["i"] if cur else -1
        cnt = self.data.get("counts", {})
        sig = (idx, tuple(cnt.get(f, 0) for f in self.playlist))
        if sig != getattr(self, "pl_sig", None):
            self.pl_sig = sig
            self.pl_tv.set(self.pl_rows(), idx)
        if cur and cur["dur"]:
            self.pl_tv.set_prog(max(0.0, (e.pl_out - cur["start"]) / 176400) / cur["dur"])
        else:
            self.pl_tv.set_prog(0.0)
        ai = self.auto_info if (self.auto_info and (self.data.get("automate") or {}).get("on")) else None
        self.set_cover(cur["path"] if cur else ((ai or {}).get("cover") or self.cover_path or None))

    def update_nowbar(self, e):
        if not e or not (self.on_air or self.preview):
            self.set_label(self.now_main, "○ Hors antenne" if e else "○ Rien en lecture", MUT)
            self.now_sub.setText("")
            return
        if self.preview:
            ok = getattr(e, "cap_state", "") == "ok"
            self.set_label(self.now_main, "Contrôle d'entrée (rien n'est diffusé)", ACCT if ok else BADC)
            self.now_sub.setText("" if ok else "entrée indisponible : voir Source audio")
            return
        if getattr(e, "cap_state", "ok") == "error" and not e.backup:
            self.set_label(self.now_main, "✕ ENTRÉE AUDIO INDISPONIBLE", "#ff6b5e")
            self.now_sub.setText("voir « 1 · Source audio »")
            return
        if e.mute:
            txt, col = "ANTENNE COUPÉE", "#ff6b5e"
        elif e.tone:
            txt, col = "Tonalité 1 kHz à l'antenne", "#5dade2"
        elif e.backup:
            txt, col = ("PLAYLIST DE SECOURS EN PAUSE · " if getattr(e, "pl_pause", False) else "PLAYLIST DE SECOURS · ") + (e.track or ""), "#f5b041"
        elif e.silent_ms >= 1000:
            txt, col = f"● Direct : aucun signal depuis {e.silent_ms // 1000} s", "#ff6b5e"
        else:
            txt, col = "DIRECT" + (" · " + e.meta if e.meta else ""), "#58d68d"
        self.set_label(self.now_main, txt, col)
        self.now_sub.setText("audio ralenti (voir SOS)" if e.slow_now() else "")

    def flux_summary(self, e):
        live, bad, wait, off = [], [], [], []
        for c in self.outputs_cfg:
            o = e.output(c["id"]) if (e and not self.preview) else None
            if not c.get("enabled", True):
                off.append(c["name"])
            elif o is None:
                continue
            elif o.state == "live":
                live.append(c["name"])
            elif o.state == "error":
                bad.append(c["name"])
            elif o.state == "connecting":
                wait.append(c["name"])
        if not (e and self.on_air):
            act = [c["name"] for c in self.outputs_cfg if c.get("enabled", True)]
            txt = ("Prêts à démarrer : " + ", ".join(act)) if act else "Aucun flux actif : ajoute-en un, ou coche « Actif »."
            if off:
                txt += "   ·   Désactivés : " + ", ".join(off)
            fg = MUT
        else:
            parts = []
            if live:
                parts.append("● En ligne : " + ", ".join(live))
            if wait:
                parts.append("◌ Connexion : " + ", ".join(wait))
            if bad:
                parts.append("✕ Problème : " + ", ".join(bad))
            if off:
                parts.append("— Désactivés : " + ", ".join(off))
            txt = "   ·   ".join(parts) or "Aucun flux actif."
            fg = BADC if (bad or not live) else (ACC2 if wait else OKC)
        self.set_label(self.l_flux, txt, fg)

    # ------------------------------------------------------------ mises à jour + bulle de Radiobot
    def update_start(self, manual=False):
        st = self.data.setdefault("settings", {})
        repo = UPDATE_REPO or st.get("update_repo")      # (version empaquetée : toujours le dépôt officiel)
        if not repo:
            if not manual:
                return
            txt, ok = QInputDialog.getText(self, "Mise à jour", "Dépôt GitHub où sont publiées les versions (compte/depot) :\n"
                                           "(rempli automatiquement dans la version téléchargée depuis GitHub)")
            if not ok or not txt.strip():
                return
            repo = txt.strip()
            st["update_repo"] = repo
            self.save_settings()

        def work():
            r = check_update(repo)
            self.ui(self.update_result, r, manual)
        if manual:
            self.log("Recherche de mises à jour…")
        threading.Thread(target=work, daemon=True).start()

    def update_result(self, r, manual):
        first = not getattr(self, "_upd_greeted", False)
        self._upd_greeted = True
        if not r or r.get("error"):
            if manual:
                self.gael_bubble("Je n'ai pas pu vérifier les mises à jour.", (r or {}).get("error") or "Recherche impossible.", hide_after=9000)
            return
        newer = parse_ver(r["tag"]) > parse_ver(VERSION)
        st = express_state()
        if r.get("express") and _ver_tuple(st.get("version")) == _ver_tuple(r["tag"]):
            if int(st.get("fails", 0)) >= 2:          # ce code express n'a pas démarré ici : installateur complet
                r["express"], r["express_why"] = None, "la mise à jour express n'a pas démarré sur cet ordinateur"
            elif os.environ.get("BEV_CODE") not in (None, "", "builtin"):
                newer = False                          # (déjà sur cette version)
            else:
                self._upd_express_ready = r["tag"]     # déjà téléchargée : il ne reste qu'à redémarrer
        if newer:
            if manual or self.upd_bubble is None or getattr(self, "_upd_mode", "") == "info":
                if getattr(self, "upd_pending", None) and getattr(self, "_upd_pending_tag", "") == r["tag"]:
                    return self.update_ready_bubble(r)
                self.update_bubble(r)
        elif (manual or first) and not getattr(self, "_just_updated", False):   # au lancement : Gaël dit bonjour, tout est à jour
            self.gael_bubble("Demat ! Bev est à jour." if not manual else "Bev est à jour.", f"Version {VERSION}", hide_after=6000)

    def gael_bubble(self, title, line="", buttons=(), hide_after=0, mode="info", one_line=False, progress=None):
        """Bulle de BD qui sort de Gaël. buttons : [(texte, type, fonction)]. hide_after : disparaît seule (ms).
        progress : None (pas de barre) ou 0-1 (barre de progression ; -1 = en cours, durée inconnue).
        La bulle a une largeur bornée (le texte passe à la ligne) et reste toujours dans la fenêtre."""
        self.update_bubble_close()
        self._upd_mode = mode
        self.bot_talk = 40
        b = SpeechBubble(self.centralWidget(), tail="top" if NAVTOP else "left")
        b.t = lab("", "", True)
        b.t.setStyleSheet("font-weight:800;font-size:13px;")
        b.lay.addWidget(b.t)
        b.l_line = lab("", "mut", True)
        b.l_line.setStyleSheet(f"color:{MUT};font-size:12px;")
        b.lay.addWidget(b.l_line)
        b.bar = UpdBar()
        b.lay.addWidget(b.bar)
        b.btns = QWidget()
        b.btn_l = QHBoxLayout(b.btns)
        b.btn_l.setContentsMargins(0, 2, 0, 0)
        b.btn_l.setSpacing(6)
        b.lay.addWidget(b.btns)
        self.upd_bubble = b
        b.bar._off = b.btns._off = True
        self.bubble_set(title, line, buttons or [], progress)
        b.pop()
        if hide_after:
            b.hide_t.timeout.connect(lambda b=b: self.update_bubble_close() if self.upd_bubble is b else None)
            b.hide_t.start(hide_after)
        g = getattr(self.rail, "gael", None)
        if g is not None and g.isVisible():
            try:
                if g.anim is not G_MAJ:
                    g.play(G_HELLO)
                g.say(min(3.0, .9 + len(title) / 30))
            except Exception:
                pass
        return b

    BUBBLE_W = 330

    def bubble_set(self, title=None, line=None, buttons=None, progress="keep"):
        """Fait évoluer la bulle en place (titre, texte, barre, boutons) : pas de clignotement, pas de nouvelle bulle."""
        b = self.upd_bubble
        if b is None:
            return
        cw = self.centralWidget()
        wmax = max(220, min(self.BUBBLE_W, cw.width() - (self.rail.width() if not NAVTOP else 0) - 40))
        for l in (b.t, b.l_line):
            l.setMaximumWidth(wmax)
            l.setMinimumWidth(min(wmax, 230))
        if title is not None:
            b.t.setText(title)
        anim = b.anim.state() == QVariantAnimation.State.Running

        def vis(w, on):
            w._off = not on
            if not anim:
                w.setVisible(on)
        if line is not None:
            b.l_line.setText(line)
            vis(b.l_line, bool(line))
        if progress != "keep":
            vis(b.bar, progress is not None)
            if progress is not None:
                b.bar.set(progress)
        if buttons is not None:
            while b.btn_l.count():
                it = b.btn_l.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            for txt, kind, fn in buttons:
                bt = btn(txt, kind, fn)
                bt.setMinimumHeight(30)
                b.btn_l.addWidget(bt)
            b.btn_l.addStretch(1)
            vis(b.btns, bool(buttons))
        b.lay.activate()
        b.adjustSize()
        self.place_upd_bubble()

    def place_upd_bubble(self):
        b = getattr(self, "upd_bubble", None)
        if b is None:
            return
        b.adjustSize()
        cw = self.centralWidget()
        W, H = cw.width(), cw.height()
        if NAVTOP:
            bb = self.bot_btn
            if bb is not None and bb.isVisible():
                c = bb.mapTo(cw, QPointF(bb.width() / 2, bb.height() - 4))
            else:
                c = QPointF(W - 40, TopNav.H - 4)
            x = int(max(8, min(c.x() - b.width() + 46, W - b.width() - 8)))
            y = int(min(c.y() + 6, H - b.height() - 8))
            b.move(x, y)
            b.tip = QPointF(c.x() - x, 0)
        else:
            g = getattr(self.rail, "gael", None)
            if g is not None and g.isVisible():                  # la pointe touche la tête de Gaël
                hp = g.mapTo(cw, g.head_point())
            else:                                                # Gaël caché (fenêtre basse) : la bulle part du bas du menu
                hp = QPointF(self.rail.width() - 8, H - 60)
            x = int(min(hp.x() + 4, W - b.width() - 8))
            y = int(max(8, min(hp.y() - b.height() * .55, H - b.height() - 8)))
            b.move(x, y)
            b.tip = QPointF(hp.x() - x, hp.y() - y)
        b.raise_()
        b.update()

    def gael_maj(self, state=None, k=None):
        """Animation de mise à jour de Gaël (colis, carton, saut de joie) ; state=None : arrêt."""
        g = getattr(self.rail, "gael", None)
        if g is None:
            return
        if state is None:
            if g.anim is G_MAJ:
                g.anim = None
                g.update()
            return
        G_MAJ.set(state, k)
        if g.anim is not G_MAJ:
            G_MAJ.k = 0.0 if k is None else G_MAJ.k
            g.play(G_MAJ)

    # ------------------------------------------------------------ mise à jour : annonce
    def upd_title(self, r):
        """« 1.1.0 → 1.1.1 » suivi du titre de la version s'il apporte quelque chose (« Processeur d'antenne »)."""
        new = r.get("tag", "").lstrip("vV")
        t = re.sub(r"(?i)^\s*bev\s*", "", r.get("title", "")).strip()
        t = re.sub(r"(?i)^v?\d+(\.\d+)*\s*", "", t).strip(" ·:-–")
        t = re.sub(r"(?i)\b(available|disponible)\b", "", t).strip(" ·:-–")
        return f"{VERSION}  →  {new}" + (f"  ·  {t}" if t else "")

    def express_settle(self):
        """Bev tourne depuis 20 s sur le code express : il a bien démarré (le compteur de démarrages ratés repart à zéro)."""
        code = os.environ.get("BEV_CODE")
        if code and code != "builtin":
            st = express_state()
            if st.get("fails"):
                express_state({"fails": 0})

    def after_update_greet(self):
        """Premier lancement après une mise à jour : Gaël l'annonce, avec un accès direct aux nouveautés."""
        if SECRETS_LOST:
            self.log("Mots de passe illisibles (réglages venus d'un autre ordinateur ou compte Windows) : à ressaisir pour "
                     + ", ".join(SECRETS_LOST[:6]))
        S = self.data.setdefault("settings", {})
        seen = S.get("seen_version")
        S["seen_version"] = VERSION
        self.save_settings()
        if not seen or parse_ver(seen) >= parse_ver(VERSION):
            return
        self._just_updated = True
        self.log(f"Bev est passé de la version {seen} à la version {VERSION}.")
        self.gael_maj("done")
        self.gael_bubble(f"Bev est passé en {VERSION} !", f"Mise à jour réussie (tu avais la {seen}). Tes réglages sont tous là.",
                         [("Voir les nouveautés", "primary", lambda: (self.close_maj(), self.go_tab("about"))), ("OK", "", self.close_maj)],
                         hide_after=20000, mode="info")
        QTimer.singleShot(3500, lambda: self.gael_maj(None) if self._upd_mode != "dl" else None)

    def update_bubble(self, r):
        """Nouvelle version : ce qu'elle apporte (titre), comment elle s'installe (express ou complète), et 3 boutons."""
        self.upd_info = r
        new = r.get("tag", "").lstrip("vV")
        ex = r.get("express")
        news = ("Nouveautés", "", lambda: self.news_dialog(r))
        later = ("Plus tard", "", self.update_bubble_close)
        if ex:
            line = (f"{self.upd_title(r)}\nMise à jour express : {fmt_size(ex['size'])}, sans installateur ni droits "
                    "administrateur. Tes réglages, playlists et cartouches restent en place.")
            btns = [("Mettre à jour", "primary", lambda: self.express_install(r)), news, later]
        elif SYS == "Windows" and "setup" in str(r.get("asset_name", "")).lower() and installed_copy():
            line = (f"{self.upd_title(r)}\nCette version renouvelle les bibliothèques de Bev : elle passe par "
                    f"l'installateur complet ({fmt_size(r.get('size', 0))}).")
            btns = [("Télécharger et installer", "primary", lambda: self.full_install(r)), news, later]
        else:
            line = f"{self.upd_title(r)}\nTélécharge la nouvelle version depuis la page des versions."
            btns = [("Télécharger", "primary", lambda: (self.update_bubble_close(), webbrowser.open(r.get("asset") or r["url"]))),
                    news, later]
        self.gael_bubble(f"Bev {new} est disponible !", line, btns, mode="new")

    def update_ready_bubble(self, r):
        """Mise à jour déjà téléchargée (express ou installateur) : on rappelle simplement comment l'appliquer."""
        if getattr(self, "_upd_express_ready", "") == r.get("tag"):
            return self.express_ready(r)
        self.gael_maj("done")
        self.gael_bubble("Mise à jour prête ✓", "Elle s'installera quand tu fermeras Bev : le direct n'est pas coupé.",
                         [("OK", "", self.update_bubble_close)], hide_after=12000, mode="ready")

    def news_dialog(self, r=None):
        """Nouveautés d'une version (notes de la Release GitHub), dans une fenêtre lisible."""
        notes = (r or {}).get("notes") or NEWS.get(VERSION, "")
        ver = ((r or {}).get("tag") or VERSION).lstrip("vV")
        d = QDialog(self)
        d.setWindowTitle(f"Nouveautés de Bev {ver}")
        d.resize(620, 560)
        v = QVBoxLayout(d)
        tx = QTextEdit()
        tx.setReadOnly(True)
        tx.setHtml(md_html(notes) or "<p>Pas de notes pour cette version.</p>")
        v.addWidget(tx, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        d.exec()

    # ------------------------------------------------------------ mise à jour express (code seul, ~1 Mo)
    def express_install(self, r):
        ex = r.get("express") or {}
        new = r.get("tag", "").lstrip("vV")
        self.gael_maj("dl", 0.0)
        self.gael_bubble(f"Je récupère Bev {new}…", f"0 Ko sur {fmt_size(ex.get('size', 0))}", progress=0.0, mode="dl")
        dst = os.path.join(UPD_DIR, ex["file"])

        def prog(got, total):
            if self._upd_mode != "dl" or self.upd_bubble is None:
                return
            k = got / total if total else -1
            self.gael_maj("dl", max(0.0, k))
            self.bubble_set(line=f"{fmt_size(got)} sur {fmt_size(total)}" if total else fmt_size(got), progress=k)

        def work():
            res = {}
            try:
                os.makedirs(UPD_DIR, exist_ok=True)
                data, sha = download(ex["url"], dst + ".part", lambda g, t: self.ui(prog, g, t), size=ex.get("size", 0))
                if sha != ex["sha256"]:
                    raise RuntimeError("le fichier reçu est abîmé (empreinte différente) : rien n'a été changé")
                with open(dst + ".part", "rb") as fh:
                    compile(fh.read(), dst, "exec")         # code lisible par ce Bev (sinon : on ne l'active pas)
                os.replace(dst + ".part", dst)
                express_state({"version": ex["version"], "runtime": RUNTIME, "file": ex["file"], "sha256": ex["sha256"],
                               "fails": 0, "from": VERSION, "notes": (r.get("notes") or "")[:20000]})
                # anciens codes express : supprimés, SAUF celui qui tourne en ce moment. Le moteur audio est relancé avec ce
                # même fichier (BEV_CODE) s'il redémarre avant Bev : effacé, il repartait sur la version installée, plus
                # ancienne, différente de l'interface (antenne en panne jusqu'au redémarrage de Bev).
                busy = os.path.basename(os.environ.get("BEV_CODE") or "")
                for f in os.listdir(UPD_DIR):
                    if f.startswith("bev-") and f.endswith(".py") and f not in (ex["file"], busy):
                        try:
                            os.remove(os.path.join(UPD_DIR, f))
                        except OSError:
                            pass
                res["ok"] = True
            except Exception as e:
                res["err"] = friendly_dl_error(e)
                try:
                    os.remove(dst + ".part")
                except OSError:
                    pass
            self.ui(self.express_done, r, res)
        threading.Thread(target=work, daemon=True).start()

    def express_done(self, r, res):
        new = r.get("tag", "").lstrip("vV")
        if not res.get("ok"):
            self.gael_maj("err")
            self.log(f"Mise à jour express {new} impossible : {res.get('err')}")
            btns = [("Réessayer", "primary", lambda: self.express_install(r))]
            if SYS == "Windows" and "setup" in str(r.get("asset_name", "")).lower() and installed_copy():
                btns.append(("Installateur complet", "", lambda: self.full_install(r)))
            self.gael_bubble("Le téléchargement n'a pas abouti.", f"{res.get('err')}\nRien n'a changé : Bev continue normalement.",
                             btns + [("Fermer", "", self.close_maj)], mode="err")
            return
        self._upd_express_ready = r.get("tag")
        self.log(f"Mise à jour express {new} téléchargée et vérifiée.")
        self.express_ready(r)

    def express_ready(self, r):
        new = r.get("tag", "").lstrip("vV")
        self.gael_maj("done")
        if self.on_air:
            self.gael_bubble(f"Bev {new} est prêt ✓", "Il s'appliquera au prochain démarrage de Bev : le direct n'est pas touché.",
                             [("Parfait", "primary", self.close_maj)], mode="ready")
        else:
            self.gael_bubble(f"Bev {new} est prêt ✓", "Il ne reste qu'à redémarrer Bev : quelques secondes, et tout est "
                             "conservé (réglages, playlists, cartouches).",
                             [("Redémarrer maintenant", "primary", self.express_restart), ("Au prochain lancement", "", self.close_maj)],
                             mode="ready")

    def express_restart(self):
        if self.on_air:
            return self.express_ready(self.upd_info or {})
        self.gael_maj("restart")
        self.bubble_set(title="À tout de suite !", line="Bev redémarre dans sa nouvelle version…", buttons=[], progress=-1)
        self.log("Redémarrage sur la nouvelle version (mise à jour express).")

        def go():
            try:
                self.save_all()
            except Exception as _ex:
                trace("go", _ex)
            relaunch_self(fresh=True)
            self._closing = True
            self.close()
        QTimer.singleShot(900, go)

    def close_maj(self):
        self.gael_maj(None)
        self.update_bubble_close()

    # ------------------------------------------------------------ installateur complet (quand le socle change)
    def full_install(self, r):
        url = r.get("asset") or ""
        if not url:
            return webbrowser.open(r.get("url") or "")
        new = r.get("tag", "").lstrip("vV")
        # dans le dossier de Bev (et non le dossier temporaire de Windows) : un programme qui dépose un .exe dans %TEMP% puis
        # le lance, c'est exactement ce que guettent Defender et les antivirus, d'où des suppressions « pour virus »
        dst = os.path.join(UPD_DIR, os.path.basename(r.get("asset_name") or "Bev-Setup.exe"))
        self.gael_maj("dl", 0.0)
        self.gael_bubble(f"Je télécharge l'installateur de Bev {new}…", "Préparation…", progress=0.0, mode="dl")
        t0 = time.time()

        def prog(got, total):
            if self._upd_mode != "dl" or self.upd_bubble is None:
                return
            k = got / total if total else -1
            el = max(.5, time.time() - t0)
            sp = got / el
            rest = (total - got) / sp if (total and sp > 0) else 0
            eta = f"  ·  encore {int(rest // 60)} min {int(rest % 60):02d} s" if rest >= 60 else (f"  ·  encore {int(rest)} s" if rest >= 2 else "")
            self.gael_maj("dl", max(0.0, k))
            self.bubble_set(line=f"{fmt_size(got)} sur {fmt_size(total)}  ·  {fmt_size(sp)}/s{eta}" if total else fmt_size(got),
                            progress=k)

        def work():
            res = {}
            try:
                os.makedirs(UPD_DIR, exist_ok=True)
                _, sha = download(url, dst + ".part", lambda g, t: self.ui(prog, g, t), size=r.get("size", 0))
                dg = r.get("digest", "")
                if dg.startswith("sha256:") and dg[7:].lower() != sha:
                    raise RuntimeError("le fichier reçu est abîmé (empreinte différente)")
                want = r.get("installer_sha256", "")
                if UPDATE_PUBKEY and want != sha:
                    raise RuntimeError("l'installateur reçu ne correspond pas à la version signée par l'auteur : rien n'a été lancé")
                if os.path.exists(dst):
                    os.remove(dst)
                os.replace(dst + ".part", dst)
                if UPDATE_PUBKEY:                         # installateur vérifié par signature : la marque « téléchargé
                    try:                                  # d'Internet » est retirée ; sinon Windows garde son contrôle
                        os.remove(dst + ":Zone.Identifier")
                    except OSError:
                        pass
                # Defender analyse le fichier juste après son enregistrement et peut le supprimer quelques secondes plus
                # tard : on vérifie qu'il est toujours là (et lisible) avant d'annoncer « Installateur prêt »
                time.sleep(2.0)
                with open(dst, "rb") as fh:
                    fh.read(4096)
                res["ok"] = True
            except FileNotFoundError:
                res["err"], res["av"] = AV_GONE, True
            except Exception as e:
                res["err"] = friendly_dl_error(e)
                res["av"] = res["err"] == AV_GONE
            if not res.get("ok"):
                try:
                    os.remove(dst + ".part")
                except OSError:
                    pass
            self.ui(self.full_downloaded, r, dst, res)
        threading.Thread(target=work, daemon=True).start()

    def full_downloaded(self, r, dst, res):
        new = r.get("tag", "").lstrip("vV")
        if not res.get("ok"):
            self.gael_maj("err")
            self.log(f"Installateur de Bev {new} : {res.get('err')}")
            if res.get("av"):                     # réessayer ne servirait à rien : Defender le supprimerait encore
                return self.full_blocked(res["err"], "av")
            self.gael_bubble("Le téléchargement n'a pas abouti.", f"{res.get('err')}\nRien n'a changé : Bev continue normalement.",
                             [("Réessayer", "primary", lambda: self.full_install(r)),
                              ("Page des versions", "", lambda: (self.close_maj(), webbrowser.open(r.get("url") or "")))], mode="err")
            return
        self.upd_pending, self._upd_pending_tag = dst, r.get("tag", "")
        self.gael_maj("done")
        if self.on_air:
            self.log(f"Installateur de Bev {new} prêt : il s'installera à la fermeture de Bev.")
            self.gael_bubble("Installateur prêt ✓", "Il s'installera quand tu fermeras Bev : le direct n'est pas coupé.",
                             [("Parfait", "primary", self.close_maj)], mode="ready")
            return
        self.gael_bubble("Installateur prêt ✓", f"L'installateur de Bev {new} va s'ouvrir et Bev se fermera : suis ses "
                         "étapes (Suivant, Installer). Tes réglages sont conservés.",
                         [("Installer maintenant", "primary", self.full_launch_now), ("À la fermeture de Bev", "", self.close_maj)],
                         mode="ready")

    def full_launch_now(self):
        """Lance l'installateur, et ne ferme Bev que lorsqu'il a vraiment démarré : si Windows (Smart App Control,
        SmartScreen) ou un antivirus le bloque, Bev reste ouvert et explique quoi faire, au lieu de disparaître."""
        self.bubble_set(title="Ouverture de l'installateur…", line="Si Windows demande une confirmation, accepte-la.", buttons=[], progress=-1)
        p, why = self.update_launch(relaunch=True)
        if p is None:
            return self.full_blocked(why, getattr(self, "_upd_block", ""))

        def check(n=0):
            rc = p.poll()
            if rc is None and n < 6:
                return QTimer.singleShot(400, lambda: check(n + 1))
            if rc not in (None, 0):
                return self.full_blocked(f"l'installateur s'est arrêté tout de suite (code {rc})")
            self.log("Installateur de la mise à jour ouvert : Bev se ferme pour le laisser faire.")
            self._closing = True
            self.close()
        QTimer.singleShot(400, check)

    def full_blocked(self, why, kind=""):
        """L'installateur n'a pas pu s'ouvrir. kind : "sac" (Smart App Control), "av" (Defender / antivirus), "policy"
        (stratégie de l'ordinateur) ou "" (autre). Dans les trois premiers cas, Windows refusera de nouveau : on ne
        réessaie PAS à la fermeture de Bev (avant, chaque fermeture redéclenchait le blocage) et on explique quoi faire."""
        self.gael_maj("err")
        self.upd_pending = None if kind in ("sac", "av", "policy") else getattr(self, "_upd_last_dst", None)
        self.log(f"Mise à jour bloquée : {why}")
        r = self.upd_info or {}
        page = ("Page des versions", "", lambda: (self.close_maj(), webbrowser.open(r.get("url") or "")))
        fermer = ("Fermer", "", self.close_maj)
        if kind == "sac":
            line = ("Smart App Control n'accepte que les programmes signés, et l'installateur de Bev ne l'est pas encore. "
                    "Bev continue normalement dans sa version actuelle ; les prochaines mises à jour passeront en express, "
                    "sans installateur. Le mieux est d'attendre une version signée plutôt que de désactiver Smart App Control (avant "
                    "Windows 11 25H2, il ne peut plus être réactivé ensuite).")
            btns = [page, fermer]
        elif kind == "av":
            line = ("C'est une fausse alerte, fréquente pour les logiciels libres non signés. Bev continue normalement. "
                    "Pour installer quand même : Sécurité Windows > Protection contre les virus et menaces > Historique de "
                    "protection > Autoriser, puis télécharge l'installateur depuis la page des versions.")
            btns = [page, fermer]
        elif kind == "policy":
            line = ("Une règle de cet ordinateur (gérée par l'informatique de la structure) interdit les programmes non "
                    "signés. Bev continue normalement ; demande à la personne qui gère l'ordinateur d'installer la mise à jour.")
            btns = [page, fermer]
        else:
            line = ("Rien n'a changé : Bev continue normalement. Ouvre le dossier et double-clique sur l'installateur "
                    "(Windows peut proposer « Exécuter quand même »), ou installe depuis la page des versions.")
            btns = [("Ouvrir le dossier", "primary", self.open_installer_folder), page, fermer]
        self.gael_bubble(why[:1].upper() + why[1:] + ".", line, btns, mode="err")

    def open_installer_folder(self):
        """Montre l'installateur téléchargé dans l'Explorateur : un double-clic le lance (Windows peut alors proposer
        « Exécuter quand même »)."""
        dst = getattr(self, "_upd_last_dst", None)
        self.close_maj()
        try:
            if dst and os.path.isfile(dst) and SYS == "Windows":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(dst)])
            elif dst:
                webbrowser.open("file://" + os.path.dirname(dst))
        except Exception as ex:
            self.log(f"Ouverture du dossier impossible : {ex}")

    def update_launch(self, relaunch):
        """Lance l'installateur téléchargé NORMALEMENT (assistant d'installation visible, comme un double-clic) : c'est le
        plus sûr, Windows peut poser ses questions et l'on voit ce qui se passe. Bev se rouvre via la case « Lancer Bev »
        de fin d'installation. Renvoie (processus, None) ou (None, raison)."""
        dst = getattr(self, "upd_pending", None)
        self._upd_block = ""
        if not dst or not os.path.isfile(dst):
            self.upd_pending = None
            if dst:                                   # téléchargé, puis disparu : Defender l'a mis en quarantaine
                self._upd_block = "av"
                return None, AV_GONE
            return None, "installateur introuvable"
        self._upd_last_dst = dst
        try:
            kw = {"creationflags": 0x00000008 | 0x00000200} if SYS == "Windows" else {}
            args = [dst, "/LOG=" + os.path.join(os.path.dirname(dst), "Bev-mise-a-jour.log")]
            env = clean_env(True)
            env.pop("BEV_CODE", None)
            p = subprocess.Popen(args, env=env, close_fds=True, **kw)
            self.upd_pending = None
            return p, None
        except OSError as ex:
            w = getattr(ex, "winerror", None)
            why = {4551: "Smart App Control (Windows) a bloqué l'installateur", 1260: "une stratégie de Windows bloque l'installateur",
                   225: AV_GONE, 226: AV_GONE, 5: "Windows a refusé l'accès à l'installateur"}.get(w, f"lancement impossible ({ex})")
            self._upd_block = {4551: "sac", 1260: "policy", 225: "av", 226: "av"}.get(w, "")
            self.log(f"Impossible de lancer la mise à jour : {ex}")
            return None, why
        except Exception as ex:
            self.log(f"Impossible de lancer la mise à jour : {ex}")
            return None, f"lancement impossible ({ex})"

    def update_bubble_close(self):
        if self.upd_bubble is not None:
            self.upd_bubble.hide()
            self.upd_bubble.deleteLater()
            self.upd_bubble = None
        self._upd_mode = ""

    # ------------------------------------------------------------ fermeture
    def closeEvent(self, ev):
        if self.on_air and not self._closing:
            if not yes(self, "Quitter Bev", "La diffusion est en cours : quitter coupera l'antenne.\n\nQuitter quand même ?"):
                ev.ignore()
                return
        self._closing = True
        try:
            os.remove(self.MARK)                  # fermeture normale : pas de reprise automatique au prochain lancement
        except OSError:
            pass
        try:
            self.save_all()
        except Exception as _ex:
            trace("closeEvent", _ex)
        try:
            self.mon_listen_stop()
        except Exception:
            pass
        try:
            self.mon_stop_all()
        except Exception:
            pass
        try:
            if self.engine:
                self.engine.stop()
        except Exception:
            pass
        try:
            if self.slot is not None:
                self.slot.close()
        except Exception:
            pass
        try:
            self.automate.stop()
        except Exception:
            pass
        if getattr(self, "upd_pending", None):     # mise à jour téléchargée pendant le direct : elle s'installe maintenant
            self.update_launch(relaunch=False)
        super().closeEvent(ev)


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
