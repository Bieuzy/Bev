# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - cartoucheur (façon Farrago) : tuiles, cartouche en cours, page et logique."""
from bev_dialogues import *  # noqa: F401,F403

# ------------------------------------------------------------------ cartoucheur façon Farrago
# Grille de tuiles (titre en couleur, forme d'onde, temps écoulé · touche · durée), inspecteur à droite :
# grande forme d'onde où l'on place la tête de lecture (même pendant la lecture), points d'entrée / sortie,
# retour / lecture-pause / fondu, volume, fondus, couleur, boucle, solo, pause autorisée, « tant que j'appuie ».
def wave_resample(bins, n):
    """Réduit une forme d'onde à n barres (maximum de chaque tranche)."""
    m = len(bins)
    if not m or n <= 0:
        return []
    if m <= n:
        return list(bins)
    return [max(bins[int(i * m / n):max(int(i * m / n) + 1, int((i + 1) * m / n))]) for i in range(n)]


def cart_col(d):
    return QColor(CART_COLORS.get(d.get("color"), CART_COLORS["Bleu"]))


def cart_span(d, dur):
    """(début, fin) en secondes dans le fichier ; fin = durée totale si aucun point de sortie."""
    try:
        a = max(0.0, float(d.get("start") or 0))
    except (TypeError, ValueError):
        a = 0.0
    try:
        b = float(d.get("end") or 0)
    except (TypeError, ValueError):
        b = 0.0
    if dur and (b <= a + .08 or b > dur):
        b = dur
    if dur and a >= b:
        a = 0.0
    return a, b


class FTile(QWidget):
    """Tuile du cartoucheur. L'état de lecture vient du moteur :
    (position, durée, boucle, écoute, fondu, crête, pause, point d'entrée)."""
    pressed = Signal(object)
    released = Signal(object)
    menu = Signal(object, object)

    def __init__(self, d, cid, parent=None):
        super().__init__(parent)
        self.d, self.cid, self.idx = d, cid, 0
        self.st, self.sel, self.hov, self.cue = None, False, False, None
        self.bins, self.dur, self._wv = [], 0.0, None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(110, 70)
        self.setToolTip("Clic : lancer · clic droit : options · Maj + clic : au casque")
        self.fx_kind, self.fx_k = None, 1.0              # retour visuel d'un clic (arrêt, pause, reprise)
        self.fx = QVariantAnimation(self)
        self.fx.setStartValue(0.0)
        self.fx.setEndValue(1.0)
        self.fx.setDuration(560)
        self.fx.valueChanged.connect(lambda v: (setattr(self, "fx_k", float(v)), self.update()))
        self.fx.finished.connect(lambda: (setattr(self, "fx_kind", None), self.update()))

    def flash(self, kind):
        """Petite animation qui confirme le clic : « stop » (carré), « pause » (deux barres) ou « play » (triangle)."""
        self.fx_kind = kind
        self.fx.stop()
        if ANIM:
            self.fx.start()
        else:                                            # sans animation : le symbole reste affiché un instant
            self.fx_k = .35
            self.update()
            QTimer.singleShot(450, lambda: (setattr(self, "fx_kind", None), self.update()))

    def paint_fx(self, p, w, h):
        k = self.fx_k
        a = 1.0 - ss(k)                                  # s'efface
        grow = .72 + .38 * back_out(min(1.0, k * 1.6))   # le symbole « saute » puis se pose
        r = QRectF(1, 1, w - 2, h - 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#000000", int(70 * a)))           # la tuile s'assombrit un instant
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 10, 10)
        c = QPointF(w / 2, h / 2 + 2)
        if self.fx_kind == "stop":                       # onde qui s'élargit : « c'est coupé »
            ring = 20 + 26 * ss(k)
            p.setPen(QPen(qc("#ffffff", int(150 * a)), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, ring, ring)
        R = 19 * grow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#0b0f17", int(185 * a)))
        p.drawEllipse(c, R, R)
        p.setBrush(qc("#ffffff", int(255 * a)))
        s_ = 8.5 * grow
        if self.fx_kind == "stop":
            p.drawRoundedRect(QRectF(c.x() - s_, c.y() - s_, 2 * s_, 2 * s_), 2.5, 2.5)
        elif self.fx_kind == "pause":
            p.drawRoundedRect(QRectF(c.x() - s_, c.y() - s_, s_ * .7, 2 * s_), 1.5, 1.5)
            p.drawRoundedRect(QRectF(c.x() + s_ * .3, c.y() - s_, s_ * .7, 2 * s_), 1.5, 1.5)
        else:
            path = QPainterPath(QPointF(c.x() - s_ * .7, c.y() - s_))
            path.lineTo(QPointF(c.x() + s_, c.y()))
            path.lineTo(QPointF(c.x() - s_ * .7, c.y() + s_))
            path.closeSubpath()
            p.drawPath(path)

    def set_state(self, st):
        if st != self.st:
            self.st = st
            self.update()

    def set_sel(self, on):
        if on != self.sel:
            self.sel = on
            self.update()

    def enterEvent(self, e):
        self.hov = True
        self.update()

    def leaveEvent(self, e):
        self.hov = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.pressed.emit(self)
        elif e.button() == Qt.MouseButton.RightButton:
            self.menu.emit(self, e.globalPosition().toPoint())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.released.emit(self)

    def resizeEvent(self, e):
        self._wv = None

    def paintEvent(self, e):
        p = new_painter(self)
        w, h = self.width(), self.height()
        d, st = self.d, self.st
        col = cart_col(d)
        playing = st is not None
        paused = playing and len(st) > 6 and st[6]
        fading = playing and st[4]
        a, b = cart_span(d, self.dur)
        r = QRectF(1, 1, w - 2, h - 2)
        p.setPen(QPen(col, 2) if self.sel else QPen(mixc(LINE, col, .35), 1))
        p.setBrush(mixc(PANEL, col, (.20 if playing else .08) + (.04 if self.hov else 0)))
        p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 10, 10)
        # titre
        tf = QFont(self.font())
        tf.setPointSizeF(9.6)
        tf.setWeight(QFont.Weight.Bold)
        p.setFont(tf)
        tcol = col.darker(118) if LIGHT else col.lighter(150)
        p.setPen(tcol)
        name = d.get("name") or os.path.basename(d.get("file") or "") or "Tuile vide"
        p.drawText(QRectF(10, 6, w - 20 - (14 if playing else 0), 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(tf).elidedText(name, Qt.TextElideMode.ElideRight, int(w - 22 - (14 if playing else 0))))
        if playing:                                  # pastille : rouge = à l'antenne, turquoise = écoute au casque
            c = QColor("#e0a800") if paused else QColor("#2fb5a3" if st[3] else "#ff3b4e")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            if paused:
                p.drawRoundedRect(QRectF(w - 19, 10, 3, 10), 1, 1)
                p.drawRoundedRect(QRectF(w - 14, 10, 3, 10), 1, 1)
            else:
                p.drawEllipse(QPointF(w - 15, 15), 4, 4)
            if fading:                                   # arrêt demandé : le son baisse jusqu'au silence
                ff = QFont(self.font())
                ff.setPointSizeF(7.6)
                ff.setBold(True)
                p.setFont(ff)
                p.setPen(QColor("#e0a800"))
                p.drawText(QRectF(w - 80, 7, 58, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "fondu…")
                p.setFont(tf)
        # forme d'onde
        wy0, wy1 = 27, h - 22
        mid, amp = (wy0 + wy1) / 2, (wy1 - wy0) / 2
        x0, x1 = 10, w - 10
        n = max(8, int((x1 - x0) / 3))
        if self._wv is None or len(self._wv) != n:
            self._wv = wave_resample(self.bins, n)
        bins = self._wv
        T = self.dur or 0.0
        pos = (st[7] + st[0]) if playing and len(st) > 7 else (self.cue if self.cue is not None else a)
        fr = pos / T if T else (st[0] / st[1] if playing and st[1] else 0.0)
        bw = (x1 - x0) / max(1, len(bins))
        p.setPen(Qt.PenStyle.NoPen)
        groups = ([], [], [])                        # hors du passage joué · déjà joué · reste : un appel de dessin par couleur
        nb = len(bins)
        ta, tb = (a / T, b / T) if T else (0.0, 1.0)
        bw1 = max(1.0, bw - 1)
        for i, v in enumerate(bins):
            t = (i + .5) / nb
            hh = max(1.0, v * amp)
            g = 0 if (T and not ta <= t <= tb) else (1 if (playing and t <= fr) else 2)
            groups[g].append(QRectF(x0 + i * bw, mid - hh, bw1, hh * 2))
        cn = col.name()
        for g, c in zip(groups, (qc(cn, 50), (col.lighter(125) if not LIGHT else col), qc(cn, 135 if playing else 165))):
            if g:
                p.setBrush(c)
                p.drawRects(g)
        if playing or self.cue is not None:
            x = x0 + (x1 - x0) * max(0.0, min(1.0, fr))
            p.setPen(ppen("#e0a800" if fading else ("#ffffff" if not LIGHT else "#20242c"), 1.6))
            p.drawLine(QPointF(x, wy0 - 1), QPointF(x, wy1 + 1))
        # bas : écoulé · touche · durée
        bf = QFont(self.font())
        bf.setPointSizeF(8.2)
        p.setFont(bf)
        yb = QRectF(10, h - 20, w - 20, 16)
        el = max(0.0, pos - a) if (playing or self.cue is not None) else 0.0
        p.setPen(QColor("#e0a800") if paused else QColor(TXT if playing else MUT))
        p.drawText(yb, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, fmt_cs(el))
        p.setPen(QColor(MUT))
        tot = (b - a) if T else (st[1] if playing else 0)
        p.drawText(yb, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   ("∞ " if d.get("loop") else "") + (fmt_cs(tot) if tot else "–"))
        key = d.get("key", "")
        if key:
            kf = QFont(bf)
            kf.setWeight(QFont.Weight.Bold)
            p.setFont(kf)
            kw = QFontMetrics(kf).horizontalAdvance(key) + 12
            kr = QRectF((w - kw) / 2, h - 19, kw, 14)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(col.name(), 150))
            p.drawRoundedRect(kr, 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(kr, Qt.AlignmentFlag.AlignCenter, key)
        if self.fx_kind:
            self.paint_fx(p, w, h)


class CartNow(QWidget):
    """Cartouche en cours, dans l'en-tête : pastille de la couleur de la tuile, nom, temps restant et barre de progression.
    Un clic la coupe en fondu. Invisible (et sans largeur) quand rien ne joue."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        self.setMinimumWidth(250)
        self.setMaximumWidth(330)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.items, self.n = [], 0
        self.setToolTip("Clic : arrêter la cartouche (fondu)")
        self.hide()

    def set_items(self, items):
        """items : [(nom, couleur, position, durée, boucle, écoute, fondu, pause)], la plus récente en dernier."""
        sig = [(a, b, round(c, 1), d, e, f, g, h) for a, b, c, d, e, f, g, h in items]
        if sig == self.items:
            return
        self.items = sig
        if self.isHidden() == bool(items):
            self.setVisible(bool(items))
            cb = getattr(self, "on_shown", None)
            if cb:
                cb()                                  # le bandeau se réorganise (place pour la cartouche)
        self.update()

    def mouseReleaseEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        if not self.items:
            return
        p = new_painter(self)
        name, col, pos, dur, loop, pre, fading, paused = self.items[-1]
        col = QColor(col)
        w, h = self.width(), self.height()
        r = QRectF(.5, .5, w - 1, h - 1)
        p.setPen(QPen(mixc(LINE, col, .5), 1))
        p.setBrush(mixc(PANEL, col, .16))
        p.drawRoundedRect(r, 12, 12)
        # pastille de lecture
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(8, 8, 4, h - 16), 2, 2)
        f = QFont(self.font())
        f.setPointSizeF(10)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        tag = "PAUSE" if paused else ("FONDU" if fading else ("CASQUE" if pre else "ANTENNE"))
        tc = QColor("#e0a800" if paused or fading else ("#2fb5a3" if pre else "#ff5a6a"))
        fm = QFontMetrics(f)
        tf = QFont(f)
        tf.setPointSizeF(7.4)
        tw = QFontMetrics(tf).horizontalAdvance(tag) + 4
        rem = ("∞" if loop else "−" + fmt_cs(max(0.0, dur - pos)))
        rw = QFontMetrics(f).horizontalAdvance(rem) + 2
        p.setPen(QColor(TXT))
        extra = f"  +{len(self.items) - 1}" if len(self.items) > 1 else ""
        p.drawText(QRectF(20, 5, w - 20 - rw - 14, 18), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(name, Qt.TextElideMode.ElideRight, int(w - 20 - rw - 20 - fm.horizontalAdvance(extra))) + extra)
        p.setPen(QColor(MUT if not paused else "#e0a800"))
        p.drawText(QRectF(w - rw - 12, 5, rw, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, rem)
        # étiquette + progression
        p.setFont(tf)
        p.setPen(tc)
        p.drawText(QRectF(20, 25, tw + 8, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tag)
        bx0, bx1 = 20 + tw + 8, w - 14
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(TXT, 40))
        p.drawRoundedRect(QRectF(bx0, 30, bx1 - bx0, 4), 2, 2)
        fr = 1.0 if loop else (min(1.0, pos / dur) if dur else 0.0)
        p.setBrush(tc if (paused or fading) else col.lighter(125))
        p.drawRoundedRect(QRectF(bx0, 30, max(4.0, (bx1 - bx0) * fr), 4), 2, 2)


class CartWave(QWidget):
    """Grande forme d'onde de l'inspecteur : cliquer / glisser place la tête de lecture ;
    les deux poignées du bas règlent l'entrée et la sortie du son."""
    seek = Signal(float)
    trim = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(96)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.bins, self._wv, self.dur, self.col = [], None, 0.0, QColor(ACC)
        self.a, self.b, self.pos, self.playing, self.fading = 0.0, 0.0, None, False, False
        self.hx, self.drag, self._last = None, None, 0.0

    def set_data(self, bins, dur, col, a, b):
        self.bins, self.dur, self.col, self.a, self.b, self._wv = bins or [], dur or 0.0, col, a, b, None
        self.update()

    def set_pos(self, pos, playing, fading=False):
        if (pos, playing, fading) != (self.pos, self.playing, self.fading):
            self.pos, self.playing, self.fading = pos, playing, fading
            self.update()

    def resizeEvent(self, e):
        self._wv = None

    def geo(self):
        return 8.0, self.width() - 8.0

    def x2t(self, x):
        x0, x1 = self.geo()
        return max(0.0, min(1.0, (x - x0) / max(1.0, x1 - x0))) * self.dur

    def t2x(self, t):
        x0, x1 = self.geo()
        return x0 + (x1 - x0) * (t / self.dur if self.dur else 0.0)

    def handle_at(self, x, y):
        if not self.dur or y < self.height() - 26:
            return None
        da, db = abs(x - self.t2x(self.a)), abs(x - self.t2x(self.b))
        if min(da, db) > 9:
            return None
        return "a" if da <= db else "b"

    def mousePressEvent(self, e):
        if not self.dur or e.button() != Qt.MouseButton.LeftButton:
            return
        x, y = e.position().x(), e.position().y()
        hd = self.handle_at(x, y)
        self.drag = hd or "seek"
        if self.drag == "seek":
            self.seek.emit(max(self.a, min(self.b - .05, self.x2t(x))))
            self._last = time.time()

    def mouseMoveEvent(self, e):
        x, y = e.position().x(), e.position().y()
        self.hx = x
        if self.drag == "seek":
            if time.time() - self._last > .045:        # pas plus de ~20 sauts par seconde : pas de friture
                self._last = time.time()
                self.seek.emit(max(self.a, min(self.b - .05, self.x2t(x))))
        elif self.drag in ("a", "b"):
            t = self.x2t(x)
            if self.drag == "a":
                self.a = max(0.0, min(t, self.b - .2))
            else:
                self.b = min(self.dur, max(t, self.a + .2))
        else:
            self.setCursor(Qt.CursorShape.SizeHorCursor if self.handle_at(x, y) else Qt.CursorShape.IBeamCursor)
        self.update()

    def mouseReleaseEvent(self, e):
        if self.drag == "seek":
            self.seek.emit(max(self.a, min(self.b - .05, self.x2t(e.position().x()))))
        elif self.drag in ("a", "b"):
            self.trim.emit(self.a, self.b)
        self.drag = None

    def leaveEvent(self, e):
        self.hx = None
        self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        w, h = self.width(), self.height()
        col = self.col
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, mixc(PANEL, col, .26))
        g.setColorAt(1, mixc(PANEL, col, .12))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)
        x0, x1 = self.geo()
        if not self.bins:
            p.setPen(QColor(MUT))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "Forme d'onde en préparation…" if self.dur == 0 and self.col else "")
            return
        n = max(20, int((x1 - x0) / 2.5))
        if self._wv is None or len(self._wv) != n:
            self._wv = wave_resample(self.bins, n)
        mid, amp = (h - 18) / 2 + 2, (h - 24) / 2
        bw = (x1 - x0) / len(self._wv)
        T = self.dur or 1.0
        fr = (self.pos / T) if self.pos is not None else -1
        bright = QColor("#ffffff") if not LIGHT else col.darker(130)
        for i, v in enumerate(self._wv):
            t = (i + .5) / len(self._wv)
            inside = self.a / T <= t <= self.b / T
            if not inside:
                c = qc(bright.name(), 45)
            elif self.playing and t <= fr:
                c = bright
            else:
                c = qc(bright.name(), 150)
            hh = max(1.0, v * amp)
            p.setBrush(c)
            p.drawRect(QRectF(x0 + i * bw, mid - hh, max(1.0, bw - .8), hh * 2))
        # points d'entrée / sortie (poignées en bas)
        for t in (self.a, self.b):
            x = self.t2x(t)
            p.setPen(ppen(qc(bright.name(), 200), 1.2))
            p.drawLine(QPointF(x, 4), QPointF(x, h - 14))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bright)
            tri = QPainterPath(QPointF(x, h - 15))
            tri.lineTo(QPointF(x - 6, h - 4))
            tri.lineTo(QPointF(x + 6, h - 4))
            tri.closeSubpath()
            p.drawPath(tri)
        # tête de lecture
        if self.pos is not None:
            x = self.t2x(self.pos)
            c = QColor("#e0a800") if self.fading else QColor(ACC)
            p.setPen(ppen(c, 2))
            p.drawLine(QPointF(x, 2), QPointF(x, h - 16))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(x, 5), 4, 4)
        if self.hx is not None and self.drag is None and x0 <= self.hx <= x1:
            p.setPen(ppen(qc(bright.name(), 90), 1))
            p.drawLine(QPointF(self.hx, 4), QPointF(self.hx, h - 16))
            f = QFont(self.font())
            f.setPointSizeF(7.8)
            p.setFont(f)
            txt = fmt_cs(self.x2t(self.hx))
            tw = QFontMetrics(f).horizontalAdvance(txt) + 10
            rx = min(w - tw - 2, max(2, self.hx + 4))
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawRoundedRect(QRectF(rx, 4, tw, 15), 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(QRectF(rx, 4, tw, 15), Qt.AlignmentFlag.AlignCenter, txt)


class TBtn(QAbstractButton):
    """Bouton de transport : icône dessinée + petit libellé dessous (Retour, Lecture, Fondu)."""

    def __init__(self, kind, text, parent=None, size=None):
        super().__init__(parent)
        self.kind = kind
        self.setText(text)
        self.setFixedSize(*(size or (66, 50)))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def set_kind(self, kind, text):
        if (kind, text) != (self.kind, self.text()):
            self.kind = kind
            self.setText(text)
            self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        w = self.width()
        on = self.isEnabled()
        hov = self.underMouse() and on
        c = QColor(ACC) if on else QColor(MUT)
        if hov:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(mixc(PANEL, TXT, .06))
            p.drawRoundedRect(QRectF(0, 0, w, self.height()), 10, 10)
        cx, cy = w / 2, (17 if self.text() else self.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        if self.kind == "stop":
            p.drawRoundedRect(QRectF(cx - 7, cy - 7, 14, 14), 2.5, 2.5)
        elif self.kind == "back":
            p.drawRect(QRectF(cx - 9, cy - 7, 2.6, 14))
            tri = QPainterPath(QPointF(cx + 8, cy - 7))
            tri.lineTo(QPointF(cx - 5, cy))
            tri.lineTo(QPointF(cx + 8, cy + 7))
            tri.closeSubpath()
            p.drawPath(tri)
        elif self.kind == "play":
            tri = QPainterPath(QPointF(cx - 6, cy - 9))
            tri.lineTo(QPointF(cx + 9, cy))
            tri.lineTo(QPointF(cx - 6, cy + 9))
            tri.closeSubpath()
            p.drawPath(tri)
        elif self.kind == "pause":
            p.drawRoundedRect(QRectF(cx - 7, cy - 8, 4.5, 16), 1.5, 1.5)
            p.drawRoundedRect(QRectF(cx + 2.5, cy - 8, 4.5, 16), 1.5, 1.5)
        elif self.kind == "fade":
            path = QPainterPath(QPointF(cx - 11, cy - 7))
            path.cubicTo(QPointF(cx - 2, cy - 7), QPointF(cx + 2, cy + 7), QPointF(cx + 11, cy + 7))
            p.setPen(ppen(c, 2.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        if self.text():
            f = QFont(self.font())
            f.setPointSizeF(8)
            p.setFont(f)
            p.setPen(QColor(TXT if on else MUT))
            p.drawText(QRectF(0, 32, w, 16), Qt.AlignmentFlag.AlignCenter, self.text())


class ColorDots(QWidget):
    """Pastilles de couleur de la tuile."""
    picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.names, self.cur = list(CART_COLORS), ""
        self.setFixedSize(20 * len(self.names), 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set(self, name):
        self.cur = name
        self.update()

    def mouseReleaseEvent(self, e):
        k = int(e.position().x() // 20)
        if 0 <= k < len(self.names):
            self.cur = self.names[k]
            self.update()
            self.picked.emit(self.cur)

    def paintEvent(self, e):
        p = new_painter(self)
        for k, n in enumerate(self.names):
            cx = 10 + k * 20
            if n == self.cur:
                p.setPen(ppen(TXT, 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, 12), 8.6, 8.6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(CART_COLORS[n]))
            p.drawEllipse(QPointF(cx, 12), 6, 6)




# ------------------------------------------------------------------ page et logique
class CartMixin:
    def _page_cart(self):
        self.cart_sel, self.cart_cue, self._hold = None, {}, set()
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        # barre du haut : recherche · volume général · tout en pause / fondu / arrêter · pré-écoute · options
        bar = Card()
        bar.lay.setContentsMargins(14, 8, 14, 8)
        h = QHBoxLayout()
        h.setSpacing(10)
        self.ed_cq = QLineEdit()
        self.ed_cq.setPlaceholderText("Rechercher")
        self.ed_cq.setClearButtonEnabled(True)
        self.ed_cq.setMinimumWidth(60)
        self.ed_cq.setStyleSheet("border-radius:14px;padding:4px 12px;")
        self.ed_cq.textChanged.connect(lambda *_: self.refresh_tiles())
        h.addWidget(lab("Volume", "mut"))
        self.sl_master = Slider(Qt.Orientation.Horizontal)
        self.sl_master.setRange(0, 150)
        self.sl_master.setFixedWidth(110)
        self.sl_master.setToolTip("Volume général de toutes les tuiles")
        self.sl_master.setValue(int(self.prof["carts"].get("master", 100)))
        self.l_master = lab("", "")
        self.l_master.setFixedWidth(40)
        self.sl_master.valueChanged.connect(self.master_changed)
        h.addWidget(self.sl_master)
        h.addWidget(self.l_master)
        h.addStretch(1)
        for kind, tip, fn in (("stop", "Tout arrêter (fondu) · Maj : arrêt net", self.stop_all_btn),
                              ("play", "Reprendre tout ce qui est en pause", lambda: self.pause_all(False)),
                              ("pause", "Tout mettre en pause", lambda: self.pause_all(True))):
            b = TBtn(kind, "", size=(40, 34))
            b.setToolTip(tip)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addSpacing(8)
        self.cb_cdev = QComboBox()
        self.cb_cdev.hide()                              # liste réelle des sorties (le bouton ci-dessous l'affiche en menu)
        self.cb_cdev.activated.connect(self.cart_dev_changed)
        # même sélecteur que la source audio de Diffusion (une ligne par carte, liste relue à chaque ouverture)
        self.b_cdev = DevicePicker(mode="out", height=40, role="Sortie audio", none_label="Aucune sortie")
        self.b_cdev.setToolTip("Sortie audio du cartoucheur")
        self.b_cdev.setMinimumWidth(220)
        self.b_cdev.setMaximumWidth(300)
        self.b_cdev.picked.connect(self.cdev_pick)
        self.b_cdev.refresh.connect(self.set_cart_devices)
        h.addWidget(self.b_cdev)
        self.cb_route = QComboBox()
        self.cb_route.addItems(ROUTES)
        self.cb_route.hide()                              # toujours à l'antenne
        ob = btn("Options")
        om = QMenu(ob)
        box = QWidget()
        bl = QGridLayout(box)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.setHorizontalSpacing(10)
        bl.setVerticalSpacing(6)
        bl.addWidget(lab("Quand j'arrête un son", "mut"), 0, 0, 1, 3)
        bl.addWidget(lab("Durée du fondu", ""), 1, 0)
        self.sl_fc = Slider(Qt.Orientation.Horizontal)
        self.sl_fc.setRange(0, 100)
        self.sl_fc.setFixedWidth(130)
        self.sl_fc.valueChanged.connect(self.fc_changed)
        bl.addWidget(self.sl_fc, 1, 1)
        self.l_fc = lab("", "")
        self.l_fc.setFixedWidth(46)
        bl.addWidget(self.l_fc, 1, 2)
        self.sw_solo = Switch("Un seul son à la fois")
        self.sw_solo.setToolTip("Lancer une tuile arrête toutes les autres")
        self.sw_solo.toggled.connect(lambda on: self.prof["carts"].__setitem__("solo", on))
        bl.addWidget(self.sw_solo, 2, 0, 1, 3)
        wa = QWidgetAction(om)
        wa.setDefaultWidget(box)
        om.addAction(wa)
        ob.setMenu(om)
        ob.setMinimumWidth(ob.fontMetrics().horizontalAdvance("Options") + 52)
        h.addWidget(ob)
        bar.lay.addLayout(h)
        v.addWidget(bar)
        # corps : sets · grille · inspecteur
        body = QHBoxLayout()
        body.setSpacing(12)
        side = Card()
        side.setFixedWidth(170)
        side.lay.addWidget(self.ed_cq)
        side.lay.addWidget(lab("SETS", "mut"))
        self.lw_sets = QListWidget()
        self.lw_sets.currentRowChanged.connect(self.pick_set)
        self.lw_sets.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lw_sets.customContextMenuRequested.connect(self.sets_menu)
        side.lay.addWidget(self.lw_sets, 1)
        self.lw_sets.itemDoubleClicked.connect(lambda *_: self.rename_set())
        self.lw_sets.setToolTip("Double-clic : renommer · clic droit : renommer ou supprimer")
        side.lay.addWidget(btn("+ Nouveau set", "", self.new_set))
        body.addWidget(side)
        mid = QVBoxLayout()
        mid.setSpacing(8)
        self.sa = QScrollArea()
        self.sa.setWidgetResizable(True)
        self.sa.setFrameShape(QFrame.Shape.NoFrame)
        self.tile_host = QWidget()
        self.tile_host.setObjectName("page")
        self.flow = Flow(self.tile_host, gap=8)
        self.flow.tw, self.flow.ratio, self.flow.th_min = 142, .56, 74
        self.sa.setWidget(self.tile_host)
        mid.addWidget(self.sa, 1)
        hb = QHBoxLayout()
        hb.addWidget(btn("+ Ajouter des sons", "primary", self.add_sounds))
        hb.addStretch(1)
        self.l_midi = lab("", "mut")
        self.l_midi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.l_midi.mouseReleaseEvent = lambda e: self.midi_click()
        hb.addWidget(self.l_midi)
        mid.addLayout(hb)
        body.addLayout(mid, 1)
        self.cart_ins = self._cart_inspector()
        body.addWidget(self.cart_ins)
        self._cart = (body, side, mid, self.cart_ins)
        v.addLayout(body, 1)
        self.setAcceptDrops(True)
        return w

    def _cart_inspector(self):
        ins = Card()
        ins.setFixedWidth(300)
        L = ins.lay
        L.setSpacing(7)
        self.ci_empty = lab("Clique sur une tuile pour la régler ici : tête de lecture, entrée et sortie, volume, fondus…", "mut", True)
        L.addWidget(self.ci_empty)
        self.ci_box = QWidget()
        b = QVBoxLayout(self.ci_box)
        b.setContentsMargins(0, 0, 0, 0)
        b.setSpacing(7)
        self.ci_name = QLineEdit()
        self.ci_name.setPlaceholderText("Nom de la tuile")
        self.ci_name.textEdited.connect(lambda t: self.ci_set("name", t))
        b.addWidget(self.ci_name)
        tr = QHBoxLayout()
        tr.setSpacing(4)
        tr.addStretch(1)
        self.ci_back = TBtn("back", "Retour")
        self.ci_back.clicked.connect(self.ci_rewind)
        self.ci_play = TBtn("play", "Lecture")
        self.ci_play.clicked.connect(self.ci_playpause)
        self.ci_fade = TBtn("fade", "Fondu")
        self.ci_fade.clicked.connect(self.ci_fadeout)
        for x in (self.ci_back, self.ci_play, self.ci_fade):
            tr.addWidget(x)
        tr.addStretch(1)
        b.addLayout(tr)
        self.ci_wave = CartWave()
        self.ci_wave.setFixedHeight(104)
        self.ci_wave.seek.connect(self.ci_seek)
        self.ci_wave.trim.connect(self.ci_trim)
        b.addWidget(self.ci_wave)
        tm = QHBoxLayout()
        self.ci_tin, self.ci_trem, self.ci_tout = lab("", "mut"), lab("", ""), lab("", "mut")
        self.ci_trem.setStyleSheet("font-weight:700;")
        self.ci_trem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ci_tout.setAlignment(Qt.AlignmentFlag.AlignRight)
        for x in (self.ci_tin, self.ci_trem, self.ci_tout):
            tm.addWidget(x, 1)
        b.addLayout(tm)
        self.ci_seg = Segmented(["Réglages", "Notes"], w=104, h=28)
        self.ci_seg.changed.connect(lambda k: self.ci_stack.setCurrentIndex(k))
        sg = QHBoxLayout()
        sg.addStretch(1)
        sg.addWidget(self.ci_seg)
        sg.addStretch(1)
        b.addLayout(sg)
        self.ci_stack = QStackedWidget()
        pg = QWidget()
        g = QGridLayout(pg)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(4)
        self.ci_sl = {}
        for row, (k, text, hi) in enumerate((("vol", "Volume", 150), ("fade_in", "Fondu d'entrée", 50), ("fade_out", "Fondu de sortie", 50))):
            g.addWidget(lab(text, "mut"), row, 0)
            s = Slider(Qt.Orientation.Horizontal)
            s.setRange(0, hi)
            s.setMinimumWidth(90)
            vl = lab("", "")
            vl.setFixedWidth(40)
            vl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            s.valueChanged.connect(lambda val, k=k: self.ci_slider(k, val))
            g.addWidget(s, row, 1)
            g.addWidget(vl, row, 2)
            self.ci_sl[k] = (s, vl)
        g.addWidget(lab("Couleur", "mut"), 3, 0)
        self.ci_col = ColorDots()
        self.ci_col.picked.connect(lambda n: self.ci_set("color", n))
        g.addWidget(self.ci_col, 3, 1, 1, 2, Qt.AlignmentFlag.AlignRight)
        ck = QGridLayout()
        ck.setContentsMargins(0, 4, 0, 0)
        ck.setHorizontalSpacing(8)
        ck.setVerticalSpacing(2)
        ck.setColumnStretch(0, 1)
        ck.setColumnStretch(1, 1)
        g.addLayout(ck, 4, 0, 1, 3)
        self.ci_ck = {}
        for n, (k, text, tip) in enumerate((("loop", "Boucle", "Recommence au point d'entrée jusqu'à l'arrêt"),
                                            ("solo", "Solo", "Coupe les autres tuiles quand celle-ci part"),
                                            ("pausable", "Clic = pause", "Un clic pendant la lecture met en pause au lieu d'arrêter"),
                                            ("hold", "Tant que j'appuie", "Ne joue que tant que le bouton ou la touche reste enfoncé"))):
            c = CheckLine(text)
            c.setToolTip(tip)
            c.toggled.connect(lambda on, k=k: self.ci_set(k, on))
            ck.addWidget(c, n // 2, n % 2)
            self.ci_ck[k] = c
        g.setColumnStretch(1, 1)
        self.ci_stack.addWidget(pg)
        self.ci_notes = QPlainTextEdit()
        self.ci_notes.setPlaceholderText("Notes pour l'animateur : quand passer ce son, à qui il appartient…")
        self.ci_notes.textChanged.connect(lambda: self.ci_set("notes", self.ci_notes.toPlainText(), quiet=True))
        self.ci_stack.addWidget(self.ci_notes)
        b.addWidget(self.ci_stack)
        fr = QHBoxLayout()
        self.ci_file = lab("", "mut")
        self.ci_file.setMinimumWidth(40)
        fr.addWidget(self.ci_file, 1)
        fr.addWidget(btn("Plus…", "", lambda: self.ci_more()))
        b.addLayout(fr)
        L.addWidget(self.ci_box, 1)
        L.addStretch(0)
        self.ci_box.hide()
        self._ci_loading = False
        return ins

    # ---- sets
    def carts(self):
        return self.prof["carts"]["pages"]

    def cid(self, si, i):
        return si * CID + i

    def refresh_sets(self):
        c = self.prof["carts"]
        self.lw_sets.blockSignals(True)
        self.lw_sets.clear()
        for n in c["names"]:
            self.lw_sets.addItem(n)
        self.cur_set = min(self.cur_set, len(c["names"]) - 1)
        self.lw_sets.setCurrentRow(self.cur_set)
        self.lw_sets.blockSignals(False)
        if hasattr(self, "sl_master"):
            self.sl_master.blockSignals(True)
            self.sl_master.setValue(int(c.get("master", 100)))
            self.sl_master.blockSignals(False)
            self.l_master.setText(f"{self.sl_master.value()} %")
        self.refresh_tiles()

    def pick_set(self, i):
        if i >= 0:
            self.cur_set = i
            self.refresh_tiles()

    def sets_menu(self, pos):
        m = QMenu(self)
        m.addAction("Renommer…", self.rename_set)
        m.addAction("Supprimer le set", self.del_set)
        m.exec(self.lw_sets.mapToGlobal(pos))

    def new_set(self):
        n, ok = QInputDialog.getText(self, "Nouveau set", "Nom du set :")
        if ok and n.strip():
            c = self.prof["carts"]
            c["pages"].append([])
            c["names"].append(n.strip())
            c["locks"].append("")
            self.cur_set = len(c["names"]) - 1
            self.refresh_sets()

    def rename_set(self):
        c = self.prof["carts"]
        n, ok = QInputDialog.getText(self, "Renommer", "Nom du set :", text=c["names"][self.cur_set])
        if ok and n.strip():
            c["names"][self.cur_set] = n.strip()
            self.refresh_sets()

    def del_set(self):
        c = self.prof["carts"]
        if len(c["names"]) < 2:
            return
        if QMessageBox.question(self, "Supprimer", f"Supprimer le set « {c['names'][self.cur_set]} » et ses tuiles ?") != QMessageBox.StandardButton.Yes:
            return
        for k in ("pages", "names", "locks"):
            del c[k][self.cur_set]
        self.cur_set = 0
        self.refresh_sets()

    # ---- tuiles
    def refresh_tiles(self):
        for t in self.tiles:
            t.setParent(None)
            t.hide()
            t.deleteLater()
        self.tiles = []
        while self.flow.count():
            self.flow.takeAt(0)
        q = self.ed_cq.text().strip().lower() if hasattr(self, "ed_cq") else ""
        for i, d in enumerate(self.carts()[self.cur_set]):
            if q and q not in (d.get("name", "") + " " + os.path.basename(d.get("file", ""))).lower():
                continue
            t = FTile(d, self.cid(self.cur_set, i), self.tile_host)
            t.idx = i
            t.pressed.connect(self.tile_press)
            t.released.connect(self.tile_release)
            t.menu.connect(self.tile_menu)
            w = self.waves.want(d["file"]) if d.get("file") else None
            if w:
                t.bins, t.dur = w
            t.cue = self.cart_cue.get(t.cid)
            t.set_sel(self.cart_sel == t.cid)
            t.show()
            self.flow.addItem(_WItem(t))
            self.tiles.append(t)
        self.resize_tiles()
        self.ci_load()

    def resize_tiles(self):
        w = self.sa.viewport().width()
        h = self.flow.heightForWidth(w)
        self.tile_host.setMinimumHeight(h)
        self.tile_host.setFixedWidth(w)
        self.flow.setGeometry(QRect(0, 0, w, h))

    def wave_ready(self, path, bins, dur):
        for t in self.tiles:
            if t.d.get("file") == path:
                t.bins, t.dur, t._wv = bins, dur, None
                t.update()
        d = self.ci_cart()
        if d and d.get("file") == path:
            self.ci_load()

    def add_sounds(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Ajouter des sons", "", "Audio (*.mp3 *.wav *.flac *.ogg *.opus *.m4a *.aac);;Tous (*)")
        self.add_files(fs)

    def add_files(self, fs):
        pg = self.carts()[self.cur_set]
        cols = list(CART_COLORS)
        for f in fs:
            c = new_cart()
            c.update(file=f, name=os.path.splitext(os.path.basename(f))[0], color=cols[len(pg) % (len(cols) - 1)])
            pg.append(c)
        if fs:
            self.refresh_tiles()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if self.page_key == 'cart':
            self.add_files([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile() and os.path.isfile(u.toLocalFile())])

    def tile_menu(self, t, gp):
        self.select_tile(t.cid)
        m = QMenu(self)
        m.addAction("Modifier…", lambda: self.tile_edit(t))
        cm = m.addMenu("Couleur")
        for n in CART_COLORS:
            cm.addAction(n, lambda n=n: self.ci_set("color", n))
        m.addSeparator()
        m.addAction("Supprimer la tuile", lambda: self.tile_delete(t.idx))
        m.exec(gp)

    def tile_delete(self, i):
        pg = self.carts()[self.cur_set]
        if 0 <= i < len(pg):
            if self.engine:
                self.engine.stop_cart(self.cid(self.cur_set, i), 0.04)
            del pg[i]
            self.cart_sel = None
            self.refresh_tiles()

    def tile_edit(self, t):
        pg = self.carts()[self.cur_set]
        i = t.idx
        d = CartDialog(self, f"Tuile · {self.prof['carts']['names'][self.cur_set]}", pg[i])
        d.exec()
        if d.result == "delete":
            del pg[i]
            self.cart_sel = None
            self.refresh_tiles()
        elif d.result is not None:
            pg[i] = fill(d.result, new_cart())
            self.refresh_tiles()

    def select_tile(self, cid):
        if cid != self.cart_sel:
            self.cart_sel = cid
            for t in self.tiles:
                t.set_sel(t.cid == cid)
            self.ci_load()

    def tile_press(self, t):
        self.select_tile(t.cid)
        if not t.d.get("file"):
            return self.tile_edit(t)
        if t.d.get("hold"):
            self._hold.add(t.cid)
            e = self.engine
            if not (e and e.cart_playing(t.cid)):
                self.trigger(t.d, t.cid)
            return
        self.trigger(t.d, t.cid)

    def tile_release(self, t):
        if t.cid in self._hold:
            self._hold.discard(t.cid)
            if self.engine:
                self.engine.stop_cart(t.cid)

    def cart_engine(self, pre):
        """Moteur prêt pour jouer une tuile (lance le moteur hors antenne au besoin). None si impossible."""
        dev = self.prof["carts"].get("device", "")
        if pre and not dev:
            QMessageBox.information(self, "Carte son", "Choisis d'abord la sortie audio du cartoucheur (en haut à droite) : "
                                    "c'est là que les sons se jouent hors antenne.")
            return None
        e = self.ensure_engine()
        if e is not None and dev and e.cmon.label != dev:
            e.cmon.set_device(dev)
        return e

    def voice_state(self, cid):
        e = self.engine
        return e.cart_status()[0].get(cid) if e else None

    def trigger(self, d, cid, force_play=False):
        """Clic sur une tuile (ou sa touche) : lance, met en pause / reprend, ou arrête."""
        shift = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        st = self.voice_state(cid)
        e = self.engine
        if st is not None and e:
            if st[6]:                                 # en pause : on reprend
                self.tile_flash(cid, "play")
                return e.pause_cart(cid, False)
            if d.get("pausable") and not shift and not force_play:
                self.tile_flash(cid, "pause")
                return e.pause_cart(cid, True)
            self.tile_flash(cid, "stop")                  # retour visuel : le clic a bien été pris en compte
            return e.stop_cart(cid, fade=0.05 if shift else None)
        e = self.cart_engine((not self.on_air) or shift)
        if not e:
            return
        if self.prof["carts"].get("solo"):
            e.stop_cart()
        at = self.cart_cue.pop(cid, None)
        for t in self.tiles:
            if t.cid == cid:
                t.cue = None
        e.play_cart(cid, d, (not self.on_air) or shift, at=at)

    def tile_flash(self, cid, kind):
        for t in self.tiles:
            if t.cid == cid:
                t.flash(kind)

    def pause_all(self, on):
        if self.engine:
            self.engine.pause_cart(None, bool(on))

    def stop_all_btn(self):
        shift = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.stop_all(0.04 if shift else None)

    def stop_all(self, fade=None):
        for t in self.tiles:
            if t.st is not None:
                t.flash("stop")
        if self.engine:
            self.engine.pause_cart(None, False)
            self.engine.stop_cart(None, fade)

    def cdev_label(self):
        p = self.b_cdev
        p.set_devices(getattr(self, "_cart_outs", None) or [self.cb_cdev.itemData(i) for i in range(self.cb_cdev.count()) if self.cb_cdev.itemData(i)])
        p.set_current(self.cb_cdev.currentData() or "")
        p.setToolTip("Sortie audio du cartoucheur : " + (out_name(self.cb_cdev.currentData()) if self.cb_cdev.currentData() else "aucune choisie"))

    def cdev_pick(self, label):
        i = self.cb_cdev.findData(label or "")
        if i < 0:
            self.cb_cdev.addItem(label, label)
            i = self.cb_cdev.count() - 1
        self.cb_cdev.setCurrentIndex(i)
        self.cart_dev_changed(i)

    def master_changed(self, v):
        self.prof["carts"]["master"] = v
        self.l_master.setText(f"{v} %")
        if self.engine:
            self.engine.prof_update("carts", master=v)

    # ---- inspecteur
    def ci_cart(self):
        if self.cart_sel is None:
            return None
        si, i = divmod(self.cart_sel, CID)
        try:
            return self.carts()[si][i]
        except (IndexError, TypeError):
            return None

    def ci_tile(self):
        return next((t for t in self.tiles if t.cid == self.cart_sel), None)

    def ci_load(self):
        if not hasattr(self, "ci_box"):
            return
        d = self.ci_cart()
        self.ci_box.setVisible(d is not None)
        self.ci_empty.setVisible(d is None)
        if d is None:
            return
        self._ci_loading = True
        try:
            if self.ci_name.text() != d.get("name", ""):
                self.ci_name.setText(d.get("name", ""))
            w = self.waves.want(d["file"]) if d.get("file") else None
            bins, dur = w if w else ([], 0.0)
            a, b = cart_span(d, dur)
            self.ci_wave.set_data(bins, dur, cart_col(d), a, b)
            for k, (s, vl) in self.ci_sl.items():
                try:
                    val = int(d.get("vol", 100)) if k == "vol" else int(round(float(d.get(k) or 0) * 10))
                except (TypeError, ValueError):
                    val = 100 if k == "vol" else 0
                s.setValue(val)
                self.ci_slider_label(k, s.value())
            self.ci_col.set(d.get("color", "Bleu"))
            for k, c in self.ci_ck.items():
                c.setChecked(bool(d.get(k)))
            if self.ci_notes.toPlainText() != d.get("notes", ""):
                self.ci_notes.setPlainText(d.get("notes", ""))
            fn = os.path.basename(d.get("file", ""))
            self.ci_file.setText(self.ci_file.fontMetrics().elidedText(fn, Qt.TextElideMode.ElideMiddle, 200))
            self.ci_file.setToolTip(d.get("file", ""))
        finally:
            self._ci_loading = False
        self.ci_tick()

    def ci_slider_label(self, k, v):
        self.ci_sl[k][1].setText(f"{v} %" if k == "vol" else f"{v / 10:.1f} s".replace(".", ","))

    def ci_slider(self, k, v):
        self.ci_slider_label(k, v)
        if self._ci_loading:
            return
        if k == "vol":
            self.ci_set("vol", v)
            if self.engine:
                self.engine.set_cart_live(self.cart_sel, vol=v / 100)
        else:
            self.ci_set(k, v / 10)
            if k == "fade_out" and self.engine:
                self.engine.set_cart_live(self.cart_sel, fo=v / 10)

    def ci_set(self, k, val, quiet=False):
        if self._ci_loading:
            return
        d = self.ci_cart()
        if d is None:
            return
        d[k] = val
        if k == "loop" and self.engine:
            self.engine.set_cart_live(self.cart_sel, loop=val)
        if k == "color":
            self.ci_col.set(val)
            self.ci_wave.col = cart_col(d)
            self.ci_wave.update()
        t = self.ci_tile()
        if t and not quiet:
            t.update()

    def ci_seek(self, sec):
        """Tête de lecture déplacée dans l'inspecteur : saute pendant la lecture, sinon point de départ du prochain clic."""
        cid = self.cart_sel
        e = self.engine
        if e and e.cart_playing(cid):
            e.seek_cart(cid, sec)
        else:
            self.cart_cue[cid] = sec
            t = self.ci_tile()
            if t:
                t.cue = sec
                t.update()
        self.ci_tick()

    def ci_trim(self, a, b):
        d = self.ci_cart()
        if d is None:
            return
        dur = self.ci_wave.dur
        self.ci_wave.a, self.ci_wave.b = a, b
        self.ci_wave.update()
        d["start"] = round(a, 2) if a > .02 else 0.0
        d["end"] = 0.0 if dur and b >= dur - .02 else round(b, 2)
        cue = self.cart_cue.get(self.cart_sel)
        if cue is not None and not a <= cue < b:
            self.cart_cue.pop(self.cart_sel, None)
        t = self.ci_tile()
        if t:
            t.cue = self.cart_cue.get(self.cart_sel)
            t.update()
        self.ci_tick()

    def ci_rewind(self):
        d, cid = self.ci_cart(), self.cart_sel
        if d is None:
            return
        e = self.engine
        if e and e.cart_playing(cid):
            e.seek_cart(cid, cart_span(d, self.ci_wave.dur)[0])
        else:
            self.cart_cue.pop(cid, None)
            t = self.ci_tile()
            if t:
                t.cue = None
                t.update()
        self.ci_tick()

    def ci_playpause(self):
        d, cid = self.ci_cart(), self.cart_sel
        if d is None or not d.get("file"):
            return
        st = self.voice_state(cid)
        if st is not None and self.engine:
            self.engine.pause_cart(cid, not st[6])
        else:
            self.trigger(d, cid, force_play=True)

    def ci_fadeout(self):
        d, cid = self.ci_cart(), self.cart_sel
        if d is None or not self.engine:
            return
        try:
            fo = float(d.get("fade_out") or 0)
        except (TypeError, ValueError):
            fo = 0.0
        self.engine.stop_cart(cid, fade=fo if fo > 0 else None)

    def ci_more(self):
        t = self.ci_tile()
        if t:
            self.tile_edit(t)

    def ci_tick(self, st=None):
        """Temps et tête de lecture de l'inspecteur (appelé à chaque image sur la page Cartoucheur)."""
        d = self.ci_cart()
        if d is None or not self.ci_box.isVisible():
            return
        if st is None:
            st = self.voice_state(self.cart_sel)
        dur = self.ci_wave.dur
        a, b = self.ci_wave.a, self.ci_wave.b
        if not dur:
            a, b = cart_span(d, 0)
        if st is not None:
            pos = st[7] + st[0]
            self.ci_wave.set_pos(pos, True, st[4])
            self.ci_play.set_kind("play" if st[6] else "pause", "Reprendre" if st[6] else "Pause")
        else:
            pos = self.cart_cue.get(self.cart_sel)
            self.ci_wave.set_pos(pos, False)
            self.ci_play.set_kind("play", "Lecture")
            pos = a if pos is None else pos
        self.ci_fade.setEnabled(st is not None)
        tin = f"Entrée {fmt_cs(a)}"
        tout = f"Sortie {fmt_cs(b)}" if b else "Sortie –"
        trem = f"−{fmt_cs(max(0.0, b - pos))}" if b else "–"
        for l_, t_ in ((self.ci_tin, tin), (self.ci_trem, trem), (self.ci_tout, tout)):
            if l_.text() != t_:
                l_.setText(t_)

    def cart_now_update(self, st):
        items = []
        for cid, v in st.items():
            si, i = divmod(cid, CID)
            try:
                d = self.carts()[si][i]
            except (IndexError, TypeError):
                continue
            items.append((d.get("name") or os.path.basename(d.get("file", "")), CART_COLORS.get(d.get("color"), CART_COLORS["Bleu"]),
                          v[0], v[1], v[2], v[3], v[4], len(v) > 6 and v[6]))
        self.cart_now.set_items(items)

    def cart_strip(self, e, st):
        """Appelé par la boucle d'affichage : état des tuiles + inspecteur."""
        for t in self.tiles:
            t.set_state(st.get(t.cid))
        self.ci_tick(st.get(self.cart_sel) if self.cart_sel is not None else None)

    # ---- raccourcis clavier et MIDI
    def find_key(self, tok, field="key"):
        for si, pg in enumerate(self.carts()):
            for i, c in enumerate(pg):
                if c.get(field) == tok:
                    return si, i
        return None

    def cart_key(self, e):
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox)) or (isinstance(fw, QComboBox) and fw.isEditable()):
            return False
        tok = qt_key_token(e)
        if not tok:
            return False
        if e.isAutoRepeat():
            return self.find_key(tok) is not None
        now = time.time()
        kt = self.__dict__.setdefault("_ktime", {})
        if now - kt.get(tok, 0) < .35:
            return True
        kt[tok] = now
        ref = self.find_key(tok)
        if ref is None and re.fullmatch(r"F\d{1,2}", tok) and self.data.get("settings", {}).get("fkeys", True):
            n = int(tok[1:]) - 1
            pg = self.carts()[self.cur_set]
            if 0 <= n < min(CART_PER, len(pg)) and not pg[n].get("key"):
                ref = (self.cur_set, n)
        if ref:
            self.cart_click_ref(ref, press=True)
            return True
        return False

    def keyReleaseEvent(self, e):
        if not e.isAutoRepeat():
            tok = qt_key_token(e)
            ref = self.find_key(tok) if tok else None
            if ref:
                cid = self.cid(*ref)
                if cid in self._hold:
                    self._hold.discard(cid)
                    if self.engine:
                        self.engine.stop_cart(cid)
                    return
        super().keyReleaseEvent(e)

    def cart_click_ref(self, ref, press=True):
        si, i = ref
        d, cid = self.carts()[si][i], self.cid(si, i)
        if si == self.cur_set:
            self.select_tile(cid)
        if not d.get("file"):
            return
        if d.get("hold"):
            self._hold.add(cid)
            if not (self.engine and self.engine.cart_playing(cid)):
                self.trigger(d, cid)
            return
        self.trigger(d, cid)

    def midi_start(self):
        if not (have_module("mido") and have_module("rtmidi")):
            return False
        if getattr(self, "midi", None) is None:
            self.midi = MidiListener(lambda tok: self.ui(self.midi_msg, tok))
        n = self.midi.start()
        if n:
            self.log(f"MIDI : {n} entrée(s) à l'écoute.")
        return bool(n)

    def midi_msg(self, tok):
        cb = getattr(self, "midi_learn", None)
        if cb:
            self.midi_learn = None
            return cb(tok)
        ref = self.find_key(tok, "midi")
        if ref:
            d = self.carts()[ref[0]][ref[1]]
            if d.get("hold"):                            # MIDI : pas de relâchement connu, la tuile joue normalement
                return self.trigger(d, self.cid(*ref))
            return self.cart_click_ref(ref)

    def midi_label_update(self):
        ok = have_module("mido") and have_module("rtmidi")
        n = len(self.midi.ports) if getattr(self, "midi", None) else 0
        self.l_midi.setText(f"MIDI : {n} entrée(s)" if n else "MIDI : activer" if ok else "MIDI : installer")

    def midi_click(self):
        if have_module("mido") and have_module("rtmidi"):
            self.midi_start()
            return self.midi_label_update()
        self.install("mido")
        self.install("python-rtmidi")


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
