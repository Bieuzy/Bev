# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - choix de l'entrée audio, décors (logo, phare, vagues), navigation, vumètres et forme d'onde."""
from bev_ui import *  # noqa: F401,F403

# ------------------------------------------------------------------ choix de l'entrée audio
def dev_kind(label):
    l = (label or "").lower()
    if "loopback" in l or "ordinateur" in l or "stereo mix" in l or "mixage" in l or "what u hear" in l or "monitor of" in l:
        return "pc"
    if any(k in l for k in ("line", "ligne", "aux")):
        return "line"
    if any(k in l for k in ("usb", "interface", "scarlett", "focusrite", "mixer", "table", "behringer", "yamaha", "rode", "zoom")):
        return "usb"
    return "mic"


def dev_short(label):
    """Nom affiché sans répéter le type (« Son de l'ordinateur : Haut-parleurs » → « Haut-parleurs »)."""
    l = label or ""
    for pre in ("Son de l'ordinateur : ", "Son de l'ordinateur ", "Monitor of ", "Moniteur de "):
        if l.startswith(pre):
            l = l[len(pre):].strip()
            break
    l = l.strip("() ")
    return (l[:1].upper() + l[1:]) if l else label


DEV_KIND_LABEL = {"pc": "Son de l'ordinateur", "line": "Entrée ligne", "usb": "Interface ou table de mixage", "mic": "Micro / entrée audio",
                  "phones": "Casque", "speaker": "Haut-parleurs", "screen": "Écran ou télévision (HDMI)", "none": ""}


def out_kind(label):
    l = (label or "").lower()
    if not l:
        return "none"
    if any(k in l for k in ("casque", "headphone", "headset", "écouteur", "ecouteur", "airpods", "buds")):
        return "phones"
    if any(k in l for k in ("hdmi", "displayport", "display audio", "nvidia", "amd high definition", "tv", "écran", "ecran", "monitor")):
        return "screen"
    if any(k in l for k in ("usb", "interface", "scarlett", "focusrite", "mixer", "table", "behringer", "yamaha", "rode", "zoom", "motu", "steinberg")):
        return "usb"
    return "speaker"


def draw_dev_icon(p, kind, cx, cy, col, s=1.0):
    p.save()
    p.translate(cx, cy)
    p.scale(s, s)
    p.setPen(ppen(col, 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "pc":
        p.drawRoundedRect(QRectF(-9, -7, 18, 12), 2.5, 2.5)
        p.drawLine(QPointF(-4, 9), QPointF(4, 9))
        p.drawLine(QPointF(0, 5), QPointF(0, 9))
    elif kind == "line":
        p.drawRoundedRect(QRectF(-3, -9, 6, 8), 2, 2)
        p.drawLine(QPointF(0, -1), QPointF(0, 4))
        path = QPainterPath(QPointF(0, 4))
        path.cubicTo(QPointF(0, 10), QPointF(8, 10), QPointF(8, 4))
        p.drawPath(path)
    elif kind == "phones":
        p.drawArc(QRectF(-8, -9, 16, 16), 0, 180 * 16)
        p.drawRoundedRect(QRectF(-9.5, -1, 5, 9), 2, 2)
        p.drawRoundedRect(QRectF(4.5, -1, 5, 9), 2, 2)
    elif kind == "speaker":
        path = QPainterPath(QPointF(-8, -3.5))
        path.lineTo(QPointF(-4, -3.5))
        path.lineTo(QPointF(1, -8))
        path.lineTo(QPointF(1, 8))
        path.lineTo(QPointF(-4, 3.5))
        path.lineTo(QPointF(-8, 3.5))
        path.closeSubpath()
        p.drawPath(path)
        p.drawArc(QRectF(-1, -5, 8, 10), -50 * 16, 100 * 16)
        p.drawArc(QRectF(-2, -9, 13, 18), -50 * 16, 100 * 16)
    elif kind == "screen":
        p.drawRoundedRect(QRectF(-9.5, -8, 19, 13), 2.5, 2.5)
        p.drawLine(QPointF(-5, 9), QPointF(5, 9))
        p.drawLine(QPointF(-6, -3), QPointF(-2, -3))
    elif kind == "none":
        p.drawEllipse(QRectF(-8, -8, 16, 16))
        p.drawLine(QPointF(-5.5, 5.5), QPointF(5.5, -5.5))
    elif kind == "usb":
        for dx, ky in ((-6, -2), (0, 3), (6, -4)):
            p.drawLine(QPointF(dx, -8), QPointF(dx, 8))
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(dx, ky), 2.2, 2.2)
            p.setBrush(Qt.BrushStyle.NoBrush)
    else:
        p.drawRoundedRect(QRectF(-3.5, -9, 7, 11), 3.5, 3.5)
        p.drawArc(QRectF(-7, -5, 14, 12), 180 * 16, 180 * 16)
        p.drawLine(QPointF(0, 7), QPointF(0, 9.5))
    p.restore()


def dev_icon_pm(kind, col, size=20):
    dpr = QApplication.primaryScreen().devicePixelRatio() if QApplication.primaryScreen() else 1.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_dev_icon(p, kind, size / 2, size / 2, col, size / 22)
    p.end()
    return QIcon(pm)


class DevicePicker(QWidget):
    """Sélecteur de carte son façon macOS : icône, nom, type, chevron ; le menu liste les cartes détectées. Le même pour
    les entrées (Diffusion) et les sorties (pré-écoute du cartoucheur, écoute du monitoring) : mode « in » ou « out ».
    En sortie, chaque carte n'apparaît qu'une fois (nom lisible, sans la technologie Windows entre crochets)."""
    picked = Signal(str)
    refresh = Signal()

    def __init__(self, parent=None, mode="in", height=54, role="", none_label="Aucune"):
        super().__init__(parent)
        self.devs, self.cur, self.hov, self.lift = [], "", False, 0.0
        self.mode, self.role, self.none_label = mode, role, none_label
        self.extra = []                     # [(libellé, fonction)] : entrées spéciales (ex. activer la capture du son de l'ordinateur)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.an = QVariantAnimation(self)
        self.an.setDuration(140)
        self.an.valueChanged.connect(lambda v: (setattr(self, "lift", float(v)), self.update()))

    def set_devices(self, labels):
        self.devs = list(labels)
        self.update()

    def set_current(self, label):
        self.cur = label or ""
        self.update()

    def _anim(self, on):
        self.an.stop()
        self.an.setStartValue(self.lift)
        self.an.setEndValue(1.0 if on else 0.0)
        self.an.start()

    def enterEvent(self, e):
        self._anim(True)

    def leaveEvent(self, e):
        self._anim(False)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Down):
            return self.popup()
        super().keyPressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.popup()

    def kind(self, l):
        return out_kind(l) if self.mode == "out" else dev_kind(l)

    def name(self, l):
        return out_name(l) if self.mode == "out" else dev_short(l)

    def popup(self):
        if self.mode == "out":                  # sorties : liste relue à chaque ouverture (cartes débranchées retirées)
            self.refresh.emit()
            return self.popup_out()
        m = QMenu(self)
        m.setMinimumWidth(self.width())
        ins = [l for l in self.devs if dev_kind(l) != "pc"]
        pcs = [l for l in self.devs if dev_kind(l) == "pc"]
        for title, group in (("ENTRÉES AUDIO", ins), ("SON DE L'ORDINATEUR", pcs)):
            if not group and not (title.startswith("SON") and self.extra):
                continue
            hd = m.addAction(title)
            hd.setEnabled(False)
            for l in group:
                a = m.addAction(dev_icon_pm(dev_kind(l), ACCT if l == self.cur else MUT), "  " + dev_short(l))
                a.setCheckable(True)
                a.setChecked(l == self.cur)
                a.setToolTip(l)
                a.triggered.connect(lambda _=False, l=l: self._pick(l))
            if title.startswith("SON"):
                for lb, fn in self.extra:
                    m.addAction(dev_icon_pm("pc", ACCT), "  " + lb, fn)
        if not self.devs:
            na = m.addAction("Aucune entrée détectée")
            na.setEnabled(False)
        m.addSeparator()
        m.addAction("Saisir le nom d'une entrée…", self._manual)
        m.addAction("Actualiser la liste", self.refresh.emit)
        m.exec(self.mapToGlobal(QPoint(0, self.height() + 4)))

    def popup_out(self):
        m = QMenu(self)
        m.setMinimumWidth(self.width())
        hd = m.addAction(self.role.upper() if self.role else "SORTIES AUDIO")
        hd.setEnabled(False)
        a = m.addAction(dev_icon_pm("none", ACCT if not self.cur else MUT), "  " + self.none_label)
        a.setCheckable(True)
        a.setChecked(not self.cur)
        a.triggered.connect(lambda _=False: self._pick(""))
        for l in out_choices(self.devs, self.cur):
            gone = l not in self.devs
            a = m.addAction(dev_icon_pm(out_kind(l), ACCT if l == self.cur else MUT), "  " + out_name(l) + ("  (débranchée)" if gone else ""))
            a.setCheckable(True)
            a.setChecked(l == self.cur)
            a.setToolTip(l)
            a.triggered.connect(lambda _=False, l=l: self._pick(l))
        if not self.devs:
            na = m.addAction("Aucune sortie audio détectée (branche-la puis rouvre ce menu)")
            na.setEnabled(False)
        m.exec(self.mapToGlobal(QPoint(0, self.height() + 4)))

    def _manual(self):
        t, ok = QInputDialog.getText(self, "Entrée audio", "Nom exact de l'entrée (tel que le système l'affiche) :", text=self.cur)
        if ok and t.strip():
            self._pick(t.strip())

    def _pick(self, l):
        self.cur = l
        self.update()
        self.picked.emit(l)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        if not self.isEnabled():
            p.setOpacity(.45)
        W, H = self.width(), self.height()
        r = QRectF(1, 1, W - 2, H - 2)
        p.setPen(QPen(mixc(LINE, ACC, .5 * self.lift) if not self.hasFocus() else QColor(ACC), 1))
        p.setBrush(mixc(FIELD, TXT, .035 * self.lift))
        p.drawRoundedRect(r, 14, 14)
        kind = self.kind(self.cur)
        pad = 9 if H >= 50 else 6
        ic = QRectF(pad, pad, H - 2 * pad, H - 2 * pad)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mixc(FIELD, ACC, .20))
        p.drawRoundedRect(ic, 10 if H >= 50 else 8, 10 if H >= 50 else 8)
        draw_dev_icon(p, kind, ic.center().x(), ic.center().y(), ACCT if self.cur else MUT, 1.0 if H >= 50 else .85)
        x0 = ic.right() + (12 if H >= 50 else 10)
        sm = H < 50
        f = QFont(self.font())
        f.setPointSizeF(10.5 if not sm else 9.8)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(TXT if self.cur else MUT))
        fm = QFontMetrics(f)
        if self.mode == "out":
            ph, sub = self.none_label, (self.role + " · " if self.role else "") + DEV_KIND_LABEL.get(kind, "")
            if not self.cur:
                sub = self.role or "Choisir une sortie audio"
        else:
            ph = "Choisir une entrée audio"
            sub = DEV_KIND_LABEL[kind] if self.cur else "Micro, table de mixage ou son de l'ordinateur"
        name = fm.elidedText(self.name(self.cur) if self.cur else ph, Qt.TextElideMode.ElideRight, int(W - x0 - 36))
        y1, y2 = (8, 27) if not sm else (H / 2 - 17, H / 2 - 1)
        p.drawText(QRectF(x0, y1, W - x0 - 36, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
        f2 = QFont(self.font())
        f2.setPointSizeF(8.8 if not sm else 8.2)
        p.setFont(f2)
        p.setPen(QColor(MUT))
        sub = QFontMetrics(f2).elidedText(sub.rstrip(" ·"), Qt.TextElideMode.ElideRight, int(W - x0 - 36))
        p.drawText(QRectF(x0, y2, W - x0 - 36, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, sub)
        cx, cy = W - 22, H / 2
        p.setPen(ppen(mixc(MUT, TXT, .4 * self.lift), 1.8))
        p.drawPolyline([QPointF(cx - 4, cy - 3), QPointF(cx, cy - 7), QPointF(cx + 4, cy - 3)])
        p.drawPolyline([QPointF(cx - 4, cy + 3), QPointF(cx, cy + 7), QPointF(cx + 4, cy + 3)])


class Stepper(QWidget):
    """Réglage numérique compact « −  12 s  + » (remplace la boîte à flèches, dont les deux petits boutons s'affichaient en
    carrés noirs). Clic sur − / +, maintien = répétition, molette, flèches du clavier. Même interface que QSpinBox."""
    valueChanged = Signal(int)

    def __init__(self, lo=0, hi=99, suffix="", parent=None):
        super().__init__(parent)
        self.lo, self.hi, self.v, self.suffix, self.hov = lo, hi, lo, suffix, 0
        self.setFixedHeight(34)
        self.setMinimumWidth(112)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.rep = QTimer(self)
        self.rep.timeout.connect(lambda: (self.rep.setInterval(70), self.step(self._dir)))
        self._dir = 0

    def setRange(self, lo, hi):
        self.lo, self.hi = lo, hi
        self.setValue(self.v)

    def setSuffix(self, s_):
        self.suffix = s_
        self.update()

    def value(self):
        return self.v

    def setValue(self, v):
        v = int(max(self.lo, min(self.hi, int(v))))
        if v != self.v:
            self.v = v
            self.update()
            self.valueChanged.emit(v)

    def step(self, d):
        if d:
            self.setValue(self.v + d)

    def zone(self, x):
        return -1 if x < 34 else (1 if x > self.width() - 34 else 0)

    def mousePressEvent(self, e):
        d = self.zone(e.position().x())
        if e.button() == Qt.MouseButton.LeftButton and d:
            self._dir = d
            self.step(d)
            self.rep.start(380)

    def mouseReleaseEvent(self, e):
        self.rep.stop()
        self._dir = 0

    def mouseMoveEvent(self, e):
        h = self.zone(e.position().x())
        if h != self.hov:
            self.hov = h
            self.setCursor(Qt.CursorShape.PointingHandCursor if h else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self.hov = 0
        self.update()

    def wheelEvent(self, e):
        self.step(1 if e.angleDelta().y() > 0 else -1)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Right, Qt.Key.Key_Plus):
            return self.step(1)
        if e.key() in (Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Minus):
            return self.step(-1)
        super().keyPressEvent(e)

    def paintEvent(self, e):
        p = new_painter(self)
        W, H = self.width(), self.height()
        r = QRectF(.5, .5, W - 1, H - 1)
        p.setPen(QPen(QColor(ACC) if self.hasFocus() else QColor(LINE), 1))
        p.setBrush(QColor(FIELD))
        p.drawRoundedRect(r, H / 2, H / 2)
        for d, cx in ((-1, 17.0), (1, W - 17.0)):
            can = (self.v > self.lo) if d < 0 else (self.v < self.hi)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(mixc(FIELD, TXT, .16 if self.hov == d and can else .07))
            p.drawEllipse(QPointF(cx, H / 2), 12, 12)
            col = QColor(TXT if can else MUT)
            if not can:
                col.setAlphaF(.4)
            p.setPen(ppen(col, 1.8))
            p.drawLine(QPointF(cx - 4.5, H / 2), QPointF(cx + 4.5, H / 2))
            if d > 0:
                p.drawLine(QPointF(cx, H / 2 - 4.5), QPointF(cx, H / 2 + 4.5))
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(10.5)
        p.setFont(f)
        p.setPen(QColor(TXT))
        p.drawText(QRectF(32, 0, W - 64, H), Qt.AlignmentFlag.AlignCenter, f"{self.v}{self.suffix}")


class IconButton(QWidget):
    """Petit bouton rond à icône dessinée (actualiser…)."""
    clicked = Signal()

    def __init__(self, kind="refresh", tip="", size=36, parent=None):
        super().__init__(parent)
        self.kind, self.lift, self.spin = kind, 0.0, 0.0
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tip:
            self.setToolTip(tip)
        self.an = QVariantAnimation(self)
        self.an.setDuration(140)
        self.an.valueChanged.connect(lambda v: (setattr(self, "lift", float(v)), self.update()))
        self.sp = QVariantAnimation(self)
        self.sp.setDuration(520)
        self.sp.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.sp.setStartValue(0.0)
        self.sp.setEndValue(360.0)
        self.sp.valueChanged.connect(lambda v: (setattr(self, "spin", float(v)), self.update()))

    def enterEvent(self, e):
        self.an.stop()
        self.an.setStartValue(self.lift)
        self.an.setEndValue(1.0)
        self.an.start()

    def leaveEvent(self, e):
        self.an.stop()
        self.an.setStartValue(self.lift)
        self.an.setEndValue(0.0)
        self.an.start()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()) and self.isEnabled():
            self.sp.stop()
            self.sp.start()
            self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(.35)
        W = self.width()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mixc(FIELD, TXT, .08 * self.lift))
        p.drawEllipse(QRectF(1, 1, W - 2, W - 2))
        p.translate(W / 2, W / 2)
        p.rotate(self.spin)
        col = mixc(MUT, TXT, .5 + .5 * self.lift)
        p.setPen(ppen(col, 1.9))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(-7, -7, 14, 14), 60 * 16, 290 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        tri = QPainterPath(QPointF(3.2, -9.6))
        tri.lineTo(QPointF(8.6, -6.2))
        tri.lineTo(QPointF(2.6, -3.4))
        tri.closeSubpath()
        p.drawPath(tri)


class Slider(QSlider):
    """Curseur dessiné à la main : jamais rogné (hauteur fixe), poignée qui grossit au survol / à la prise,
    clic n'importe où = la poignée y va, glissement continu ; repeint seulement sa propre zone."""

    def __init__(self, orient=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orient, parent)
        self.setFixedHeight(28)
        self.setMinimumWidth(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.lift, self.drag = 0.0, False
        self.an = QVariantAnimation(self)
        self.an.setDuration(140)
        self.an.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.an.valueChanged.connect(lambda v: (setattr(self, "lift", float(v)), self.update()))

    def _to(self, on):
        self.an.stop()
        self.an.setStartValue(self.lift)
        self.an.setEndValue(1.0 if on else 0.0)
        self.an.start()

    def enterEvent(self, e):
        self._to(True)

    def leaveEvent(self, e):
        if not self.drag:
            self._to(False)

    def _geo(self):
        m = 11
        return m, self.width() - m

    def _val_at(self, x):
        a, b = self._geo()
        f = _cl((x - a) / max(1, b - a))
        if self.invertedAppearance():
            f = 1 - f
        return round(self.minimum() + f * (self.maximum() - self.minimum()))

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or not self.isEnabled():
            return
        self.drag = True
        self.setSliderDown(True)
        self.setValue(self._val_at(e.position().x()))
        self._to(True)

    def mouseMoveEvent(self, e):
        if self.drag:
            self.setValue(self._val_at(e.position().x()))

    def mouseReleaseEvent(self, e):
        if self.drag:
            self.drag = False
            self.setSliderDown(False)
            if not self.rect().contains(e.position().toPoint()):
                self._to(False)

    def wheelEvent(self, e):
        if self.isEnabled():
            self.setValue(self.value() + (1 if e.angleDelta().y() > 0 else -1) * max(1, self.singleStep()))
        e.accept()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(.4)
        a, b = self._geo()
        cy = self.height() / 2
        rng = max(1, self.maximum() - self.minimum())
        f = (self.value() - self.minimum()) / rng
        if self.invertedAppearance():
            f = 1 - f
        x = a + f * (b - a)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(FIELD) if not LIGHT else QColor("#dfe3ec"))
        p.drawRoundedRect(QRectF(a - 3, cy - 3, b - a + 6, 6), 3, 3)
        if x > a - 2:
            g = QLinearGradient(a, 0, b, 0)
            g.setColorAt(0, QColor(ACC))
            g.setColorAt(1, QColor("#ff5fa2" if PSYCHE else ACC2))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(QRectF(a - 3, cy - 3, x - a + 6, 6), 3, 3)
        r = 7.5 + 1.8 * self.lift
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QPointF(x, cy + 1.2), r + .6, r + .6)
        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor(LINE), 1))
        p.drawEllipse(QPointF(x, cy), r, r)
        if self.lift > .05:
            c = QColor(ACC)
            c.setAlphaF(.9 * self.lift)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(x, cy), 2.6 * self.lift, 2.6 * self.lift)



class FolderChip(QWidget):
    """Dossier affiché clairement : icône, nom du dossier en gras, chemin parent en dessous (abrégé au milieu)."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path, self.extra, self.lift = "", "", 0.0
        self.setFixedHeight(52)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Cliquer pour choisir un autre dossier")

    def set_path(self, p, extra=""):
        self.path, self.extra = p or "", extra
        self.setToolTip((p or "") + "\nCliquer pour choisir un autre dossier")
        self.update()

    def enterEvent(self, e):
        self.lift = 1.0
        self.update()

    def leaveEvent(self, e):
        self.lift = 0.0
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        p = new_painter(self)
        W, H = self.width(), self.height()
        p.setPen(QPen(mixc(LINE, ACC, .5 * self.lift), 1))
        p.setBrush(mixc(FIELD, TXT, .03 * self.lift))
        p.drawRoundedRect(QRectF(1, 1, W - 2, H - 2), 14, 14)
        ic = QRectF(9, 9, 34, 34)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mixc(FIELD, ACC, .2))
        p.drawRoundedRect(ic, 10, 10)
        cx, cy = ic.center().x(), ic.center().y()
        p.setPen(ppen(ACCT, 1.7))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(cx - 8, cy + 6))
        path.lineTo(cx - 8, cy - 5)
        path.lineTo(cx - 3, cy - 5)
        path.lineTo(cx - 1, cy - 3)
        path.lineTo(cx + 8, cy - 3)
        path.lineTo(cx + 8, cy + 6)
        path.closeSubpath()
        p.drawPath(path)
        name = os.path.basename(self.path.rstrip("/\\")) or self.path or "Aucun dossier choisi"
        parent = os.path.dirname(self.path.rstrip("/\\"))
        home = os.path.expanduser("~")
        if parent.startswith(home):
            parent = "~" + parent[len(home):]
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(TXT))
        x0 = ic.right() + 12
        p.drawText(QRectF(x0, 7, W - x0 - 12, 20), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f).elidedText(name, Qt.TextElideMode.ElideRight, int(W - x0 - 14)))
        f2 = QFont(self.font())
        f2.setPointSizeF(8.6)
        p.setFont(f2)
        p.setPen(QColor(MUT))
        sub = ("dans " + parent if parent else "") + (("   ·   " + self.extra) if self.extra else "")
        p.drawText(QRectF(x0, 27, W - x0 - 12, 18), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(f2).elidedText(sub, Qt.TextElideMode.ElideMiddle, int(W - x0 - 14)))

# ------------------------------------------------------------------ décors : logo, icônes, navigation, ambiances
RZ = [0.0]  # instant jusqu'auquel la fenêtre se redimensionne : animations en pause


def calm():
    return time.time() < RZ[0]


GSTOPS = [ACC, "#ff5fa2", "#a76bff", "#4cc9f0"] if PSYCHE else [ACC, ACC2]
ICON_C, LABEL_C, SECT_C = ("#6b7488", "#3a4152", "#8a93a8") if LIGHT else ("#aeb6c6", "#c4cad8", "#6c7589")
HOVER_C, IND_C = ("#eef0f5", "#e6e9f1") if LIGHT else ("#181d29", "#242a3a")
HUE = {"diff": "#ff5fa2", "son": "#a76bff", "cart": "#4cc9f0", "rec": "#ff6b6b", "mon": "#35d49a", "net": "#4cc9f0",
       "sos": "#ffb347", "set": "#a76bff", "about": "#ff5fa2"}
AA = RenderHint = QPainter.RenderHint.Antialiasing


class Gov:
    """Régulateur de fluidité : mesure la cadence réelle de l'interface et, si la machine n'arrive pas à tenir 60 i/s,
    passe à 30 i/s réguliers (palier 1), puis supprime les effets décoratifs coûteux (palier 2) pour ne jamais descendre
    sous 30. Il remonte tout seul d'un palier quand la machine suit de nouveau."""
    tier, ema, last, since, good, ups, timers, hooks = 1, .033, 0.0, 0.0, 0.0, 0, [], []     # objectif : 30 i/s réguliers
    need, t_up = 10, 0.0         # secondes de bonne tenue avant de retenter 60 i/s (doublé à chaque échec, 2 min au plus)

    @classmethod
    def ivl(cls, base=16):
        return base if cls.tier == 0 else max(base, 33)

    @classmethod
    def reg(cls, tm, base=16):
        if not any(t is tm for t, _ in cls.timers):
            cls.timers.append((tm, base))
        return tm

    @classmethod
    def frame(cls, active=True):
        now = time.perf_counter()
        if cls.last and now - cls.last < .5 and active and not calm():
            cls.ema += (now - cls.last - cls.ema) * .08
        cls.last = now
        if now - cls.since < 2.0:
            return
        cls.since = now
        target = .0167 if cls.tier == 0 else .0334
        if cls.ema > target * 1.45 and cls.tier < 2:
            if cls.tier == 0 and now - cls.t_up < 8:      # 60 i/s retenté puis raté tout de suite : on attendra plus longtemps
                cls.need = min(120, cls.need * 2)
            cls.set(cls.tier + 1)
        elif cls.ema < target * 1.12 and cls.tier > 1:
            cls.good += 2
            if cls.good >= cls.need:                         # la machine suit de nouveau : on remonte (sans limite de tentatives)
                cls.t_up = now
                cls.set(cls.tier - 1)
        else:
            cls.good = 0
        if cls.tier == 0 and now - cls.t_up > 60:
            cls.need = 10

    @classmethod
    def set(cls, tier):
        cls.tier, cls.good = tier, 0
        cls.ema = .033
        cls.timers = [(t, b) for t, b in cls.timers if _alive(t)]
        for t, b in cls.timers:
            try:
                t.setInterval(cls.ivl(b))
            except RuntimeError:
                pass
        for fn in cls.hooks:
            try:
                fn(tier)
            except Exception:
                pass


def _alive(o):
    try:
        o.objectName()
        return True
    except RuntimeError:
        return False


def grad(t, stops=None):
    st = stops or GSTOPS
    t = max(0.0, min(1.0, t))
    n = len(st) - 1
    i = min(n - 1, int(t * n))
    return mixc(st[i], st[i + 1], t * n - i)


def ppen(col, w=2, cap=Qt.PenCapStyle.RoundCap):
    return QPen(QColor(col), w, Qt.PenStyle.SolidLine, cap, Qt.PenJoinStyle.RoundJoin)


from PySide6.QtGui import QPolygonF
PH_NAVY, PH_AMBER, PH_RED, PH_SEA, PH_WHITE = "#0b1f3a", "#ffb03b", "#e5483f", "#5b7fa8", "#f5f7fb"
if MINI:                                        # mode minimaliste : logo en gris, aucune couleur décorative
    PH_NAVY, PH_AMBER, PH_RED, PH_SEA, PH_WHITE = "#202022", "#9a9aa0", "#5c5c62", "#46464b", "#d8d8dc"


def draw_logo(p, cx, cy, r, cols=None, width=3, rot=0.0, tile=True, sea=None, pulse=None):
    """Le phare de Bev (logo). Carré de côté 2r centré en (cx, cy). `rot` (radians) fait respirer les ondes ; à 0 le dessin est fixe."""
    p.save()
    k = 2.0 * r / 560.0
    p.translate(cx - r, cy - r)
    p.scale(k, k)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if tile:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(PH_NAVY))
        p.drawRoundedRect(QRectF(0, 0, 560, 560), 125, 125)
    big = r >= 14 if sea is None else sea
    # ondes
    if pulse is None:
        pulse = .6 + .4 * math.sin(rot * 3) if rot else 1.0
    p.setBrush(Qt.BrushStyle.NoBrush)
    for sd in (-1, 1):
        for (ex, ey0, ey1, bulge, wd, al) in ((180, 44, 209, 40, 16, pulse), (213, 79, 176, 12, 16, 1.0)):
            c = QColor(PH_AMBER)
            c.setAlphaF(al)
            p.setPen(ppen(c, wd, Qt.PenCapStyle.RoundCap))
            x0 = 280 + sd * (280 - ex)
            off = sd * (bulge / .75)
            pa = QPainterPath(QPointF(x0, ey0))
            ym = (ey0 + ey1) / 2
            pa.cubicTo(QPointF(x0 + off, ey0 + (ym - ey0) * .75), QPointF(x0 + off, ey1 - (ey1 - ym) * .75), QPointF(x0, ey1))
            p.drawPath(pa)
    # tour
    p.setPen(Qt.PenStyle.NoPen)
    tower = QPainterPath(QPointF(243, 172))
    tower.lineTo(QPointF(317, 172))
    tower.lineTo(QPointF(336, 404))
    tower.lineTo(QPointF(224, 404))
    tower.closeSubpath()
    p.setBrush(QColor(PH_WHITE))
    p.drawPath(tower)
    p.save()
    p.setClipPath(tower)
    p.setBrush(QColor(PH_RED))
    p.drawRect(QRectF(200, 230, 160, 44))
    p.drawRect(QRectF(200, 319, 160, 45))
    p.restore()
    p.setBrush(QColor(PH_WHITE))
    p.drawRoundedRect(QRectF(235, 157, 90, 17), 6, 6)
    p.drawRoundedRect(QRectF(202, 403, 156, 23), 11, 11)
    p.setBrush(QColor(PH_AMBER))
    p.drawRoundedRect(QRectF(258, 101, 44, 56), 5, 5)
    p.setBrush(QColor(PH_WHITE))
    p.drawPolygon(QPolygonF([QPointF(280, 67), QPointF(314, 101), QPointF(247, 101)]))
    if big:                                   # mer
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(ppen(PH_SEA, 12, Qt.PenCapStyle.RoundCap))
        pa = QPainterPath(QPointF(65, 492))
        for i in range(1, 91):
            x = 65 + i * 5.02
            pa.lineTo(QPointF(x, 489 + 13 * math.sin((x + 280 - 437) * 2 * math.pi / 180)))
        p.drawPath(pa)
    p.restore()


draw_triskell = draw_logo      # ancien nom, conservé pour les appels existants
_LOGO_PM = {}


def draw_logo_fast(p, cx, cy, r, rot=0.0, tile=True, sea=None):
    """Même logo, recopié depuis une image pré-rendue (à la résolution réelle de l'écran) : la respiration des ondes est
    découpée en 40 niveaux, chacun dessiné une seule fois. ~10× moins coûteux que de retracer le phare à chaque image."""
    pulse = .6 + .4 * math.sin(rot * 3) if rot else 1.0
    q = int(round(pulse * 40))
    try:
        dpr = p.device().devicePixelRatioF()
    except Exception:
        dpr = 1.0
    k = (r, q, dpr, tile, sea)
    pm = _LOGO_PM.get(k)
    if pm is None:
        if len(_LOGO_PM) > 160:
            _LOGO_PM.clear()
        sz = int(math.ceil((2 * r + 2) * dpr))
        pm = QPixmap(sz, sz)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q2 = QPainter(pm)
        q2.setRenderHints(QPainter.RenderHint.Antialiasing)
        draw_logo(q2, r + 1, r + 1, r, None, 3, 0.0, tile, sea, pulse=q / 40.0)
        q2.end()
        _LOGO_PM[k] = pm
    p.drawPixmap(QPointF(cx - r - 1, cy - r - 1), pm)


def draw_ermine(p, x, y, col, s=1.0):
    """Hermine bretonne (x, y = pointe basse)."""
    ox, oy = x, y - 9 * s
    P = [(ox, oy - 7 * s), (ox - 3 * s, oy + 4 * s), (ox, oy + 9 * s), (ox + 3 * s, oy + 4 * s)]
    for _ in range(3):
        Q = []
        for i in range(len(P)):
            p0, p1 = P[i], P[(i + 1) % len(P)]
            Q += [(.75 * p0[0] + .25 * p1[0], .75 * p0[1] + .25 * p1[1]), (.25 * p0[0] + .75 * p1[0], .25 * p0[1] + .75 * p1[1])]
        P = Q
    from PySide6.QtGui import QPolygonF
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(col))
    p.drawPolygon(QPolygonF([QPointF(a, b) for a, b in P]))
    for dx, dy in ((-4, -9), (0, -12), (4, -9)):
        p.drawEllipse(QPointF(ox + dx * s, oy + dy * s), 1.4 * s, 1.4 * s)


def draw_icon(p, key, cx, cy, col):
    """Icônes au trait (même dessin que la version Tk)."""
    p.save()
    p.translate(cx, cy)
    p.setPen(ppen(col, 2))
    p.setBrush(Qt.BrushStyle.NoBrush)

    def L(*xy):
        path = QPainterPath(QPointF(xy[0], xy[1]))
        for i in range(2, len(xy), 2):
            path.lineTo(xy[i], xy[i + 1])
        p.drawPath(path)

    def E(r, dx=0, dy=0, fill=False, rx=None):
        if fill:
            p.setBrush(QColor(col))
            p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(dx, dy), rx or r, r)
        if fill:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(ppen(col, 2))
    if key == "diff":
        p.drawRoundedRect(QRectF(-4, -9, 8, 12), 4, 4)
        p.drawArc(QRectF(-8, -6, 16, 14), 180 * 16, 180 * 16)
        L(0, 8, 0, 11)
        L(-4, 11, 4, 11)
    elif key == "son":
        for dx, ky in ((-6, -2), (0, 3), (6, -5)):
            L(dx, -9, dx, 9)
            E(3, dx, ky)
    elif key == "cart":
        for dx in (-8, 1):
            for dy in (-8, 1):
                p.drawRoundedRect(QRectF(dx, dy, 7, 7), 3, 3)
    elif key == "mon":
        L(-9, 0, -4, 0, -1, -8, 3, 8, 6, 0, 9, 0)
    elif key == "net":
        E(9)
        E(9, rx=4)
        L(-9, 0, 9, 0)
    elif key == "rec":
        E(9)
        E(4, fill=True)
    elif key == "set":
        for dy, kx in ((-6, -3), (0, 4), (6, -1)):
            L(-9, dy, 9, dy)
            E(3, kx, dy)
    elif key == "about":
        E(9)
        L(0, -1, 0, 5)
        E(1.5, 0, -4.6, fill=True)
    elif key == "sos":
        E(9)
        E(4)
        for sx in (-1, 1):
            for sy in (-1, 1):
                L(sx * 4, sy * 4, sx * 8, sy * 8)
    p.restore()


def draw_blob(p, cx, cy, col, size=260, alpha=.26):
    g = QRadialGradient(cx, cy, size / 2)
    c = QColor(col)
    c.setAlphaF(alpha)
    g.setColorAt(0, c)
    c2 = QColor(col)
    c2.setAlphaF(0)
    g.setColorAt(1, c2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), size / 2, size / 2)


def soft_pill(p, rect, c1, c2, r=14):
    g = QLinearGradient(rect.topLeft(), rect.topRight())
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawRoundedRect(rect, r, r)


def paint_bot(p, x, y, width, blink=False, talk=0, on_air=False):
    """Petit Gaël (le Marin), en buste : même dessin que le grand, à l'échelle."""
    from bev_gael import GaelPainter, POSE0       # (défini plus loin, dans le module de Gaël)
    gp = globals().get("_BOT_GP")
    if gp is None:
        gp = globals()["_BOT_GP"] = GaelPainter()
    P = dict(POSE0)
    P.update(blink=1.0 if blink else 0.0, la1=14, ra1=14)
    sc = width / 64.0
    p.save()
    p.translate(x + width / 2, y + 128 * sc)
    p.scale(sc, sc)
    gp.draw(p, P, talk=min(1.0, talk / 20.0) if talk else 0.0, on_air=on_air, t=time.time() % 1000)
    p.restore()



class Ticker(QObject):
    """Horloge commune des décors animés : un seul minuteur à 60 i/s pour tous, et du temps réel (secondes) plutôt qu'un
    compteur d'images, pour un mouvement régulier même si une image saute. Un widget caché ne coûte rien."""
    _inst = None
    driven = False           # vrai quand la fenêtre principale fournit l'horloge (une seule cadence pour toute l'interface)

    def __init__(self):
        super().__init__()
        self.subs, self.clock = [], QElapsedTimer()
        self.clock.start()
        self.tm = QTimer(self)
        self.tm.setTimerType(Qt.TimerType.PreciseTimer)
        self.tm.timeout.connect(self.tick)
        self.last = 0.0

    @classmethod
    def get(cls):
        if cls._inst is None:
            cls._inst = Ticker()
        return cls._inst

    @classmethod
    def add(cls, w, fn, fps=60, always=False):
        """fn(t, dt) est appelée à chaque image tant que le widget est visible ; elle renvoie True s'il faut le repeindre.
        `fps` : cadence propre au décor (30 suffit pour ce qui dérive lentement : deux fois moins de dessin, aucune
        différence à l'œil)."""
        T = cls.get()
        T.subs.append([w, fn, 1.0 / max(1, fps) - .004, 0.0, always])
        if ANIM and not T.tm.isActive() and not cls.driven:
            T.tm.start(Gov.ivl(16))
            Gov.reg(T.tm, 16)

    @classmethod
    def drive(cls):
        """La boucle d'affichage principale prend le relais : décors, Gaël, forme d'onde… sont mis à jour dans le MÊME passage
        que les vumètres. Une seule peinture (et un seul envoi à l'écran) par image au lieu de plusieurs, décalées."""
        cls.driven = True
        cls.get().tm.stop()

    def now(self):
        return self.clock.elapsed() / 1000.0

    def tick(self):
        t = self.now()
        self.last = t
        if calm():
            return
        self.n = getattr(self, "n", 0) + 1
        if Gov.tier >= 2 and self.n % 2:         # palier 2 : les décors ne bougent qu'une image sur deux
            return
        alive = []
        win_min = {}
        for s in self.subs:
            w, fn, per, last, always = s
            try:
                if (ANIM or always) and t - last >= per:
                    top = w.window()
                    k = id(top)
                    if k not in win_min:
                        win_min[k] = bool(top) and top.isMinimized()
                    if w.isVisible() and not win_min[k]:
                        s[3] = t
                        if fn(t, min(.1, t - last) if last else .016):
                            w.update()
                alive.append(s)
            except RuntimeError:              # widget détruit
                pass
        self.subs = alive


class SeaScene(QWidget):
    """Décor de Bretagne maritime : phare au faisceau tournant, voilier, goélands, étoiles, vagues."""

    def __init__(self, w=214, h=120, bg=None, light_x=.78, parent=None):
        super().__init__(parent)
        self.bgc = bg or RAIL
        self.setFixedSize(w, h)
        self.air, self.t, self.n, self.lx = False, 0.0, 0, light_x
        self.mode = False                       # False (tout roule) / "secours" / "flux" / "son"
        rnd = random.Random(11)
        self.stars = [[rnd.uniform(8, w - 8), rnd.uniform(3, h * .38), 0] for _ in range(11)]
        self.sc = ["#3D6A92", "#6E9CC8", "#BFD7F2", "#2A4C6E"]
        self._star = 0.0
        Ticker.add(self, self.step, 30)

    def step(self, t, dt):
        self.t += dt
        if t - self._star > .6:
            self._star = t
            random.choice(self.stars)[2] = random.randrange(4)
        return True

    def wave(self, base, amp, k, ph, W):
        path = QPainterPath(QPointF(0, base + amp * math.sin(ph)))
        for x in range(6, W + 9, 6):
            path.lineTo(x, base + amp * math.sin(x * k + ph))
        return path

    def poly(self, p, col, *pts):
        from PySide6.QtGui import QPolygonF
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(col))
        p.drawPolygon(QPolygonF([QPointF(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]))

    def paintEvent(self, e):
        p = new_painter(self)
        w, h = self.width(), self.height()
        s, t = h / 110.0, self.t
        sea, lx = h * .66, w * self.lx
        p.fillRect(self.rect(), QColor(self.bgc))
        for x, y, k in self.stars:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self.sc[k]))
            p.drawEllipse(QRectF(x, y, 1.8, 1.8))
        mx, my = w * .13, h * .17
        p.setBrush(QColor("#E8F2FF"))
        p.drawEllipse(QPointF(mx, my), 8 * s, 8 * s)
        p.setBrush(QColor(self.bgc))
        p.drawEllipse(QRectF(mx - 3 * s, my - 10 * s, 14 * s, 16 * s))
        ly = sea - 54 * s - 5.5 * s
        mode = self.mode if self.air or self.mode else False
        ph = t * {"secours": 3.0, "flux": 0.0, "son": 0.6}.get(mode, 2.1 if self.air else 1.0)
        lit = True
        if mode == "flux":                       # rupture : le phare ne tourne plus, il lance des éclats rouges d'alarme
            k = (t / .9) % 1.0
            lit = k < .12 or .24 < k < .36
            beam = mixc(self.bgc, "#FF3150", .38 if lit else .06)
            for sg in (1, -1):
                hh = 7 * s
                self.poly(p, beam, lx, ly, lx + sg * w * .95, ly - hh, lx + sg * w * .95, ly + hh)
        else:
            beam = mixc(self.bgc, {"secours": "#FFD23F", "son": "#FF7A1A"}.get(mode, "#FFE9A8"),
                        {"secours": .34, "son": .12}.get(mode, .20))
            for sg in (1, -1):
                tip = lx + sg * w * .95 * math.cos(ph)
                hh = (2.5 + 9 * abs(math.sin(ph))) * s
                self.poly(p, beam, lx, ly, tip, ly - hh, tip, ly + hh)
        self.poly(p, "#1B2B3A", lx - 19 * s, h, lx - 14 * s, sea + 2 * s, lx - 7 * s, sea - 7 * s, lx + 6 * s, sea - 8 * s, lx + 14 * s, sea + 2 * s, lx + 20 * s, h)
        y0, y1 = sea - 6 * s, sea - 54 * s
        self.poly(p, "#EAF0F6", lx - 6 * s, y0, lx + 6 * s, y0, lx + 3.6 * s, y1, lx - 3.6 * s, y1)
        ya, yb = y0 - (y0 - y1) * .32, y0 - (y0 - y1) * .52
        wa, wb = 6 - 2.4 * .32, 6 - 2.4 * .52
        self.poly(p, "#C8452D", lx - wa * s, ya, lx + wa * s, ya, lx + wb * s, yb, lx - wb * s, yb)
        p.setBrush(QColor("#2A3A4A"))
        p.drawRect(QRectF(lx - 6 * s, y1 - 2 * s, 12 * s, 3 * s))
        if mode == "flux":
            lamp = "#FF5A6E" if lit else "#5A1A24"
        elif mode == "secours":
            lamp = "#FFF2B0" if abs(math.sin(ph)) > .7 else "#FFD23F"
        else:
            lamp = "#FFE08A" if abs(math.sin(ph)) > .7 else "#E0A93C"
        p.setBrush(QColor(lamp))
        p.drawRect(QRectF(lx - 3.6 * s, y1 - 9 * s, 7.2 * s, 7 * s))
        self.poly(p, "#2A3A4A", lx - 5 * s, y1 - 9 * s, lx + 5 * s, y1 - 9 * s, lx, y1 - 15 * s)
        W = int(w)

        def fill(path, col):
            path.lineTo(w, h)
            path.lineTo(0, h)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawPath(path)
        fill(self.wave(sea, 2.2 * s, .07, t * 1.2, W), "#14506E")
        bx = (t * 7) % (w + 60) - 30
        by = sea + 4 * s + math.sin(t * 1.7) * 1.6 * s
        self.poly(p, "#2B1E1A", bx - 11 * s, by - 3 * s, bx + 11 * s, by - 3 * s, bx + 7 * s, by + 3 * s, bx - 7 * s, by + 3 * s)
        p.setPen(ppen("#2B1E1A", 1))
        p.drawLine(QPointF(bx, by - 3 * s), QPointF(bx, by - 28 * s))
        self.poly(p, "#E9DFC8", bx + 1.5 * s, by - 26 * s, bx + 1.5 * s, by - 4 * s, bx + 10 * s, by - 4 * s)
        self.poly(p, "#D8553A", bx - 1.5 * s, by - 22 * s, bx - 1.5 * s, by - 4 * s, bx - 10 * s, by - 4 * s)
        p1 = self.wave(sea + 10 * s, 2.6 * s, .09, 1.3 - t * 1.5, W)
        p.setPen(ppen("#5FB4C8", 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(p1)
        fill(self.wave(sea + 10 * s, 2.6 * s, .09, 1.3 - t * 1.5, W), "#0F3E58")
        p.setPen(ppen("#5FB4C8", 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(self.wave(sea + 10 * s, 2.6 * s, .09, 1.3 - t * 1.5, W))
        fill(self.wave(sea + 22 * s, 3 * s, .06, t * .9 + 2, W), "#0A2D44")
        p.setPen(ppen("#DCE8F4", 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, (fy, v, ph0) in enumerate(((.14, 11.0, 5.0), (.27, 7.5, 31.0), (.21, 14.0, 18.0))):
            gx = (ph0 * 3 + t * v) % (w + 40) - 20
            gy = h * fy + math.sin(t * .7 + i * 2) * 3 * s
            f = math.sin(t * 5 + i * 1.7) * 3.2 * s
            path = QPainterPath(QPointF(gx - 7 * s, gy + f))
            path.quadTo(QPointF(gx - 3.5 * s, gy - 3 * s), QPointF(gx, gy))
            path.quadTo(QPointF(gx + 3.5 * s, gy - 3 * s), QPointF(gx + 7 * s, gy + f))
            p.drawPath(path)


class WaveBar(QWidget):
    """Fine bande de vagues animée ; option petit voilier."""

    def __init__(self, w=120, h=8, bg=None, boat=False, parent=None):
        super().__init__(parent)
        self.h, self.t, self.boat, self.bgc = h, 0.0, boat, bg
        self.setFixedHeight(h)
        if w > 12:
            self.setFixedWidth(w)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        Ticker.add(self, self.step, 30)

    def step(self, t, dt):
        self.t += dt
        return True

    def paintEvent(self, e):
        p = new_painter(self)
        W, h = max(24, self.width()), self.h
        if self.bgc:
            p.fillRect(self.rect(), QColor(self.bgc))
        for base, amp, k, ph, col in ((h * .42, h * .22, .085, self.t * 1.3, "#1B6A86"), (h * .64, h * .2, .12, 1 - self.t * 1.7, "#12506C")):
            path = QPainterPath(QPointF(0, base + amp * math.sin(ph)))
            for x in range(6, W + 9, 6):
                path.lineTo(x, base + amp * math.sin(x * k + ph))
            path.lineTo(W, h)
            path.lineTo(0, h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawPath(path)
        if self.boat:
            bx = (self.t * 9) % (W + 40) - 20
            by = h * .40 + math.sin(self.t * 1.7) * .8
            from PySide6.QtGui import QPolygonF
            p.setBrush(QColor("#E9DFC8"))
            p.drawPolygon(QPolygonF([QPointF(bx - 5, by - 1), QPointF(bx + 5, by - 1), QPointF(bx + 3, by + 2.5), QPointF(bx - 3, by + 2.5)]))
            p.setBrush(QColor("#D8553A"))
            p.drawPolygon(QPolygonF([QPointF(bx, by - h * .62), QPointF(bx, by - 1.5), QPointF(bx + 5, by - 1.5)]))


class AuroraBar(QWidget):
    """Fine barre de dégradé qui glisse lentement (soulignement du titre de page)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 6)
        self.off = 0.0
        Ticker.add(self, self.step, 30)

    def step(self, t, dt):
        self.off = (self.off + 28 * dt) % 360
        return True

    def paintEvent(self, e):
        p = new_painter(self)
        L = 360.0
        g = QLinearGradient(-self.off, 0, -self.off + L, 0)
        for i in range(13):
            u = i / 12
            g.setColorAt(u, grad(1 - abs(2 * u - 1)))
        g.setSpread(QLinearGradient.Spread.ReflectSpread)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(0, 1, 120, 4), 2, 2)


ONAIR_RED, ONAIR_RED2 = "#ff3150", "#e0123a"        # rouge « ON AIR » des studios : la couleur universelle de l'antenne
SECOURS_Y = "#ffd23f"                                # jaune « playlist de secours à l'antenne »


class AirWaves(QWidget):
    """Phare d'antenne : une animation par état, reconnaissable d'un coup d'œil, même de loin.
      - tout roule : ondes ambre émises calmement depuis la lanterne, halo qui respire ;
      - playlist de secours (jaune) : la lanterne tourne, son faisceau balaie l'horizon comme un vrai phare ;
      - flux coupés (rouge) : alarme, la lanterne flashe par paires, les ondes se brisent et grésillent ;
      - plus de son (orange) : les ondes reviennent vers la lanterne, comme si le phare tendait l'oreille.
    Éteint et immobile hors antenne."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(58, 54)
        self.on, self.bad, self.t = False, False, 0.0
        self.setToolTip("Phare d'antenne")
        Ticker.add(self, self.step, 60)

    def set(self, on, bad=False):
        if (on, bad) != (self.on, self.bad):
            self.on, self.bad = on, bad
            self.setToolTip("Phare d'antenne : " + ({"son": "pas de son en entrée", "flux": "rupture de flux",
                                                     "secours": "playlist de secours à l'antenne"}.get(bad, "panne") if bad
                                                    else ("à l'antenne, tout va bien" if on else "hors antenne")))
            self.update()

    def step(self, t, dt):
        self.t = t
        return self.on or bool(self.bad)

    @staticmethod
    def arc(p, cx, top, sd, dx, hh, bul):
        x0 = cx + sd * dx
        pa = QPainterPath(QPointF(x0, top - hh))
        pa.cubicTo(QPointF(x0 + sd * bul / .75, top - hh * .25), QPointF(x0 + sd * bul / .75, top + hh * .25), QPointF(x0, top + hh))
        p.drawPath(pa)

    def paintEvent(self, e):
        p = new_painter(self)
        t = self.t if ANIM else 0.0
        mode = self.bad or ("ok" if self.on else "off")
        act = mode != "off"
        col = QColor({"flux": ONAIR_RED, "son": "#ff7a1a", "secours": SECOURS_Y}.get(mode, "#ffb03b"))
        cx, top, base = 29.0, 13.0, 51.0
        dim = QColor("#4a5266" if not LIGHT else "#b4bac6")
        shake = 0.0
        lamp = 1.0
        if mode == "flux":                                   # alarme : double flash rouge toutes les 0,9 s, léger tremblement
            ph = (t / .9) % 1.0
            lamp = 1.0 if (ph < .12 or .24 < ph < .36) else .18
            shake = (math.sin(t * 61) * .55) if (ANIM and lamp > .5) else 0.0
        elif mode == "son":
            lamp = .45 + .35 * (math.sin(t * 2.2) + 1) / 2
        elif mode == "secours":
            lamp = .75 + .25 * abs(math.cos(t * 2.4))
        p.translate(shake, 0)
        # halo de la lanterne
        if act:
            rad = 13 if mode != "flux" else 17
            halo = QRadialGradient(cx, top, rad)
            br = (.55 + .45 * math.sin(t * 2.6) ** 2) if mode == "ok" else lamp
            halo.setColorAt(0, qc(col.name(), int(140 * br)))
            halo.setColorAt(1, qc(col.name(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(QPointF(cx, top), rad, rad)
        p.setBrush(Qt.BrushStyle.NoBrush)
        waves = ((9.5, 7.5, 2.4), (15.0, 11.0, 4.2), (20.5, 14.0, 5.6))
        if mode == "secours":
            # faisceau tournant : deux pinceaux de lumière qui balaient l'horizon (de face, il s'étale ; de profil, il s'affine)
            th = t * 2.4
            for sd in (1, -1):                                       # deux pinceaux opposés, comme une vraie lanterne
                k = abs(math.cos(th))
                L = 6 + 24 * k
                hw = 1.6 + 5.5 * (1 - k)
                near = (math.sin(th) * sd) > 0                        # celui qui nous fait face est plus lumineux
                al = int((235 if near else 120) * (.45 + .55 * k))
                g = QLinearGradient(cx, top, cx + sd * L, top)
                g.setColorAt(0, qc(col.name(), al))
                g.setColorAt(.7, qc(col.name(), int(al * .35)))
                g.setColorAt(1, qc(col.name(), 0))
                beam = QPainterPath(QPointF(cx, top - 1.8))
                beam.lineTo(QPointF(cx + sd * L, top - hw))
                beam.lineTo(QPointF(cx + sd * L, top + hw))
                beam.lineTo(QPointF(cx, top + 1.8))
                beam.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(g))
                p.drawPath(beam)
            # éclat quand le faisceau passe face à nous
            face = max(0.0, abs(math.sin(th)) - .92) / .08
            if face > 0:
                p.setBrush(qc("#ffffff", int(160 * face)))
                p.drawEllipse(QPointF(cx, top), 6 + 3 * face, 6 + 3 * face)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i, (dx, hh, bul) in enumerate(waves[:2]):            # ondes discrètes, immobiles
                pc = QColor(col)
                pc.setAlphaF(.22)
                p.setPen(ppen(pc, 1.8, Qt.PenCapStyle.RoundCap))
                for sd in (-1, 1):
                    self.arc(p, cx, top, sd, dx, hh, bul)
        else:
            for i, (dx, hh, bul) in enumerate(waves):
                if not act:
                    if i == 2:
                        continue
                    a, c = .35, dim
                elif mode == "ok":                                   # émission : de l'intérieur vers l'extérieur
                    d_ = ((t / 1.6) - i * .26) % 1.0
                    a = .2 + .8 * max(0.0, 1 - abs(d_ - .22) / .28) if d_ < .62 else .2
                    a *= (1.0, 1.0, .75)[i]
                    c = col
                elif mode == "son":                                  # retour : de l'extérieur vers la lanterne
                    d_ = ((t / 2.0) - (2 - i) * .26) % 1.0
                    a = .12 + .6 * max(0.0, 1 - abs(d_ - .22) / .28) if d_ < .62 else .12
                    c = col
                else:                                                # flux coupés : ondes brisées qui grésillent
                    fl = .5 + .5 * math.sin(t * 23 + i * 2.1) * math.sin(t * 7.3 + i)
                    a = (.25 + .65 * fl) * (1.0 if lamp > .5 else .55)
                    c = col
                pc = QColor(c)
                pc.setAlphaF(_cl(a))
                pen = ppen(pc, 2.1 if i == 0 else 2.0, Qt.PenCapStyle.RoundCap)
                if mode == "flux":
                    pen.setDashPattern([1.6, 1.4 + i * .6])
                    pen.setDashOffset(t * 9 * (1 if i % 2 else -1))
                p.setPen(pen)
                for sd in (-1, 1):
                    self.arc(p, cx, top, sd, dx, hh, bul)
        # tour : silhouette fine, deux bandes, lanterne
        body = QPainterPath(QPointF(cx - 3.6, 19))
        body.lineTo(QPointF(cx + 3.6, 19))
        body.lineTo(QPointF(cx + 6.4, base))
        body.lineTo(QPointF(cx - 6.4, base))
        body.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#eef1f6") if act else dim)
        p.drawPath(body)
        if act:
            p.save()
            p.setClipPath(body)
            p.setBrush(QColor(ONAIR_RED2))
            for y0 in (26, 37):
                p.drawRect(QRectF(cx - 8, y0, 16, 4.5))
            p.restore()
        lc = QColor(col) if act else mixc(dim, PAGE, .2)
        if act:
            lc = mixc(QColor("#3a2a10"), col, lamp)
        p.setBrush(lc)
        p.drawRoundedRect(QRectF(cx - 3.2, top - 3.2, 6.4, 6.4), 1.6, 1.6)
        p.setBrush(QColor("#2a3040") if act else dim)
        p.drawRoundedRect(QRectF(cx - 5.5, top + 3.4, 11, 2.4), 1.2, 1.2)
        dome = QPainterPath(QPointF(cx - 3.8, top - 3))
        dome.cubicTo(QPointF(cx - 3.4, top - 8), QPointF(cx + 3.4, top - 8), QPointF(cx + 3.8, top - 3))
        dome.closeSubpath()
        p.drawPath(dome)
        p.setBrush(QColor("#3a4152") if not LIGHT else QColor("#c9ced8"))
        p.drawRoundedRect(QRectF(cx - 11, base - 1, 22, 3.5), 1.7, 1.7)


class Segmented(QWidget):
    """Sélecteur segmenté façon macOS."""
    changed = Signal(int)

    def __init__(self, labels, w=56, h=32, parent=None):
        super().__init__(parent)
        f = QFont(self.font())                       # chaque segment est assez large pour son texte (« Problèmes »
        f.setBold(True)                              # dépassait de sa pastille)
        f.setPointSizeF(9.5)
        w = max(w, max(QFontMetrics(f).horizontalAdvance(t) for t in labels) + 20) if labels else w
        self.labels, self.w, self.h, self.val, self.pos = list(labels), w, h, 0, 0.0
        self.setFixedSize(w * len(labels) + 6, h + 6)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.an = QVariantAnimation(self)
        self.an.setDuration(140)
        self.an.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.an.valueChanged.connect(lambda v: (setattr(self, "pos", float(v)), self.update()))

    def setValue(self, k, emit=False):
        k = max(0, min(len(self.labels) - 1, k))
        self.val = k
        self.an.stop()
        if ANIM and self.isVisible():
            self.an.setStartValue(self.pos)
            self.an.setEndValue(float(k))
            self.an.start()
        else:
            self.pos = float(k)
            self.update()
        if emit:
            self.changed.emit(k)

    def mouseReleaseEvent(self, e):
        k = int((e.position().x() - 3) // self.w)
        if 0 <= k < len(self.labels) and k != self.val:
            self.setValue(k, True)

    def paintEvent(self, e):
        p = new_painter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#e3e6ee" if LIGHT else "#1a1f2b"))
        p.drawRoundedRect(QRectF(1, 1, self.w * len(self.labels) + 4, self.h + 4), (self.h + 4) / 2, (self.h + 4) / 2)
        x = 3 + self.pos * self.w
        r = QRectF(x, 3, self.w, self.h)
        if PSYCHE:
            soft_pill(p, r, ACC, mixc(ACC, "#c04bff", .5), self.h / 2)
        else:
            p.setBrush(QColor(ACC))
            p.drawRoundedRect(r, self.h / 2, self.h / 2)
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(9.5)
        p.setFont(f)
        for k, t in enumerate(self.labels):
            on = abs(k - self.pos) < .5
            p.setPen(QColor(ONACC if on else LABEL_C))
            p.drawText(QRectF(3 + k * self.w, 3, self.w, self.h), Qt.AlignmentFlag.AlignCenter, t)


# ------------------------------------------------------------------ navigation latérale / haute
class NavBase(QWidget):
    selected = Signal(str)
    bot_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.active, self.hover, self.air = "diff", None, False
        self.title_txt = (SET.get("station") or "Studio")[:18]
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bot_blink, self.bot_hint = False, False

    def set_air(self, on):
        if bool(on) != self.air:
            self.air = bool(on)
            self.update()

    def set_title(self, t):
        self.title_txt = (t or "Studio")[:18]
        self.update()

    def leaveEvent(self, e):
        self.set_hover(None)

    def set_hover(self, k):
        if k != self.hover:
            self.hover = k
            self.update()


class Rail(NavBase):
    BG_HZ = 12             # halos colorés (ambiance Psyché) : ils dérivent très lentement, 12 images/s sont invisibles à l'œil
    LAYOUT = (("sec", "Antenne"), ("diff", "Diffusion"), ("son", "Processeur"), ("cart", "Cartoucheur"), ("rec", "Enregistrement"),
              ("sec", "Contrôle"), ("mon", "Monitoring"), ("net", "Réseau"), ("sos", "SOS"),
              ("sec", "Application"), ("set", "Réglages"), ("about", "À propos"))
    W, RH = 214, 40
    W_COMPACT = 72

    def __init__(self):
        super().__init__()
        self.compact = False
        self.setFixedWidth(self.W)
        self.pos = {}
        y = 84
        for k, lab in self.LAYOUT:
            if k == "sec":
                y += 12
                self.pos[("sec", lab)] = y
                y += 22
            else:
                self.pos[k] = y
                y += self.RH + 3
        self.ind_y = float(self.pos["diff"])
        self.ang, self.spin, self.tick_n = 0.0, 0.0, 0
        self.rip = []
        self.sea = None
        self.erm = [(22 + q * 34 + (r % 2) * 17, 44 - r * 24 + 20, .13) for r in range(2) for q in range(6)]
        self.gl = QVariantAnimation(self)
        self.gl.setDuration(220)
        self.gl.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.gl.valueChanged.connect(lambda v: (setattr(self, "ind_y", float(v)), self.upd_items()))
        self.t_anim, self._erm_t = 0.0, 0.0
        Ticker.add(self, self.anim)
        if OCEAN:
            self.sea = SeaScene(self.W, 120, bg=RAIL, parent=self)
        self.badges = {}
        self.items_bottom = self.pos["about"] + self.RH
        from bev_gael import GaelView                # (défini plus loin, dans le module de Gaël)
        self.gael = GaelView("rail", self)
        self.gael.hide()

    def set_compact(self, on):
        """Fenêtre étroite (écran vertical) : menu réduit aux icônes (le nom de l'onglet s'affiche au survol)."""
        on = bool(on)
        if on == self.compact:
            return
        self.compact = on
        self.W = self.W_COMPACT if on else Rail.W
        self.setFixedWidth(self.W)
        self._it_sig = None
        self.resizeEvent(None)
        self.update()

    def resizeEvent(self, e):
        H = self.height()
        if self.compact:
            if self.sea:
                self.sea.hide()
            self.gael.hide()
            return
        sea = bool(self.sea) and H >= 695
        if self.sea:
            self.sea.move(0, H - 120)
            self.sea.setVisible(sea)
        top = self.items_bottom + 10
        bottom = H - (118 if sea else 6)
        avail = bottom - top
        if avail >= 128:
            h = min(262, avail)
            self.gael.setGeometry(10, bottom - h, self.W - 20, h)
            self.gael.show()
        else:
            self.gael.hide()

    def upd_items(self):
        """Seule la zone des onglets est repeinte (pas Gaël ni le décor en dessous) : changement d'onglet plus léger."""
        self.update(QRect(0, 76, self.W, self.items_bottom - 70))

    def set_hover(self, k):
        if k != self.hover:
            self.hover = k
            self.upd_items()

    def set_badge(self, key, color):
        if self.badges.get(key) != color:
            if color:
                self.badges[key] = color
            else:
                self.badges.pop(key, None)
            self.update(QRect(0, self.pos[key], self.W, self.RH))

    def set_air(self, on):
        super().set_air(on)
        self.gael.on_air = self.air
        if self.sea:
            self.sea.air = self.air

    def set_alert(self, mode):
        """État du phare du menu : tout roule, playlist de secours, flux coupés ou plus de son."""
        if self.sea and self.sea.mode != mode:
            self.sea.mode = mode
            self.sea.update()

    def key_at(self, y):
        for k, _ in self.LAYOUT:
            if k != "sec" and self.pos[k] <= y < self.pos[k] + self.RH:
                return k

    def mouseMoveEvent(self, e):
        k = self.key_at(e.position().y())
        self.set_hover(k)
        if self.compact:
            from PySide6.QtWidgets import QToolTip
            lbl = dict((kk, ll) for kk, ll in self.LAYOUT if kk != "sec").get(k)
            if lbl:
                QToolTip.showText(e.globalPosition().toPoint(), lbl, self)
            else:
                QToolTip.hideText()

    def mouseReleaseEvent(self, e):
        x, y = e.position().x(), e.position().y()
        if y < 80:
            self.spin += 14.0
            self.rip += [(time.time(), 0), (time.time() + .11, 1)]
            return
        k = self.key_at(y)
        if k:
            self.selected.emit(k)

    def fits_bot(self):
        return False

    def select(self, key):
        self.active = key
        tgt = float(self.pos[key])
        self.gl.stop()
        if ANIM:
            self.gl.setStartValue(self.ind_y)
            self.gl.setEndValue(tgt)
            self.gl.start()
        else:
            self.ind_y = tgt
        self.upd_items()

    def anim(self, t, dt):
        """60 i/s : logo, halos colorés, hermines. On ne repeint pas la zone de Gaël (il s'en charge)."""
        self.spin *= .94 ** (dt * 12.5)
        self.ang = (self.ang + ((1.8 if self.air else .55) + self.spin) * dt) % (2 * math.pi / 3)
        self.t_anim += dt
        if self.erm and t - self._erm_t > .48:
            self._erm_t = t
            i = random.randrange(len(self.erm))
            x, y, _ = self.erm[i]
            self.erm[i] = (x, y, random.choice((.07, .12, .20, .30)))
        bg_moves = PSYCHE and Gov.tier < 2 and int(self.t_anim * self.BG_HZ) != getattr(self, "_bg_key", (None,))[0]
        if not (bg_moves or self.rip or abs(self.spin) > .01):
            # seul le logo bouge, et seulement à l'antenne (hors antenne il est fixe : rien à repeindre) ; 30 i/s suffisent
            # pour la respiration des ondes
            if self.air and ANIM and t - getattr(self, "_logo_t", 0.0) >= .029:
                self._logo_t = t
                self.update(QRect(int(self.W / 2) - 25 if self.compact else 14, 20, 50, 50))
            return False
        if self.gael.isVisible():
            g = self.gael.geometry()
            self.update(QRect(0, 0, self.W, g.y()))
            self.update(QRect(0, g.y(), g.x(), g.height()))
            self.update(QRect(g.right() + 1, g.y(), self.W, g.height()))
            return False
        return True

    def _items_layer(self, dpr):
        """Icônes et libellés du menu, pré-rendus : redessinés seulement si le survol, l'onglet ou une pastille change."""
        w = self.W
        sig = (self.active, self.hover, tuple(sorted(self.badges.items())), dpr, w)
        if getattr(self, "_it_sig", None) == sig:
            return self._it_pm
        pm = QPixmap(int(w * dpr), int((self.items_bottom + 6) * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        sf = QFont(self.font())
        sf.setPointSizeF(8.5)
        sf.setBold(True)
        for k, lab in self.LAYOUT:
            if k == "sec":
                if self.compact:                            # menu réduit : un simple trait entre les groupes
                    y = self.pos[("sec", lab)]
                    p.setPen(QPen(QColor(SECT_C), 1))
                    p.drawLine(QPointF(22, y + 8), QPointF(w - 22, y + 8))
                    continue
                p.setFont(sf)
                p.setPen(QColor(SECT_C))
                y = self.pos[("sec", lab)]
                p.drawText(QRectF(26, y, w - 40, 16), Qt.AlignmentFlag.AlignVCenter, lab)
                continue
            y = self.pos[k]
            on, hv = k == self.active, k == self.hover and k != self.active
            if hv:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(HOVER_C))
                p.drawRoundedRect(QRectF(10 if self.compact else 12, y, w - (20 if self.compact else 24), self.RH), 14, 14)
            hu = HUE.get(k, ACC) if PSYCHE else ACC
            col = hu if on else (mixc(ICON_C, hu, .65) if hv else ICON_C)
            if self.compact:
                draw_icon(p, k, w / 2, y + self.RH / 2, col)
                bc = self.badges.get(k)
                if bc:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(bc))
                    p.drawEllipse(QPointF(w / 2 + 13, y + 9), 4, 4)
                continue
            draw_icon(p, k, 38 + (2 if hv else 0), y + self.RH / 2, col)
            lf = QFont(self.font())
            lf.setPointSizeF(10.5)
            lf.setBold(on)
            p.setFont(lf)
            p.setPen(QColor(TXT if (on or hv) else LABEL_C))
            tx = 62 + (3 if hv else 0)
            p.drawText(QRectF(tx, y, w - 70, self.RH), Qt.AlignmentFlag.AlignVCenter, lab)
            if k == "son":                                  # processeur d'antenne : en bêta
                bx = tx + QFontMetrics(lf).horizontalAdvance(lab) + 6
                bf = QFont(self.font())
                bf.setPointSizeF(6.4)
                bf.setBold(True)
                bf.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
                bw = QFontMetrics(bf).horizontalAdvance("BÊTA") + 9
                br = QRectF(bx, y + self.RH / 2 - 8, bw, 16)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc(HUE["son"] if PSYCHE else ACC, 46))
                p.drawRoundedRect(br, 8, 8)
                p.setFont(bf)
                p.setPen(QColor(HUE["son"] if PSYCHE else ACCT))
                p.drawText(br, Qt.AlignmentFlag.AlignCenter, "BÊTA")
            bc = self.badges.get(k)
            if bc:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(bc))
                p.drawEllipse(QPointF(w - 30, y + self.RH / 2), 4, 4)
        p.end()
        self._it_pm, self._it_sig = pm, sig
        return pm

    def paintEvent(self, e):
        p = new_painter(self)
        w, H = self.W, self.height()
        er = e.rect()
        if PSYCHE:
            # halos colorés : calculés 20 fois par seconde en basse définition puis agrandis UNE fois dans une image pleine taille ;
            # chaque image affichée (60 i/s, et les repeints derrière Gaël) ne fait plus qu'une simple copie
            dpr = self.devicePixelRatioF()
            key = (int(self.t_anim * self.BG_HZ), w, H, dpr)
            if getattr(self, "_bg_key", None) != key:
                q = 4
                small = QImage(max(1, w // q), max(1, H // q), QImage.Format.Format_RGB32)
                small.fill(QColor(RAIL))
                bp = QPainter(small)
                bp.scale(1 / q, 1 / q)
                t = key[0] / float(self.BG_HZ)
                for i, c in enumerate(("#ff5fa2", "#a76bff", "#4cc9f0")):
                    bx = 107 + math.sin(t * .35 + i * 2.1) * 70
                    by = H * (.12 + .38 * i) + math.cos(t * .27 + i * 1.7) * 40
                    draw_blob(bp, bx, by, c, 260, .26 if i == 0 else .20)
                bp.end()
                pm = QPixmap.fromImage(small.scaled(int(w * dpr), int(H * dpr), Qt.AspectRatioMode.IgnoreAspectRatio,
                                                    Qt.TransformationMode.SmoothTransformation))
                pm.setDevicePixelRatio(dpr)
                self._bg_pm, self._bg_key = pm, key
            p.drawPixmap(QRectF(er), self._bg_pm, QRectF(er.x() * dpr, er.y() * dpr, er.width() * dpr, er.height() * dpr))
        else:
            p.fillRect(er, QColor(RAIL))
        lx = w / 2 if self.compact else 38
        if er.intersects(QRect(int(lx) - 24, 20, 50, 50)):       # le logo n'est dessiné que si sa zone est à repeindre
            draw_logo_fast(p, lx, 42, 19, self.ang if self.air else 0.0)
        if er.top() < 70 and not self.compact:
            f = QFont(self.font())
            f.setPointSizeF(12.5)
            f.setBold(True)
            p.setFont(f)
            f.setPointSizeF(17)
            f.setWeight(QFont.Weight.ExtraBold)
            p.setFont(f)
            p.setPen(QColor(TXT))
            p.drawText(QRectF(66, 18, w - 74, 28), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, APP)
            f2 = QFont(self.font())
            f2.setPointSizeF(7.2)
            f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
            p.setFont(f2)
            p.setPen(QColor(MUT))
            p.drawText(QRectF(66, 46, w - 74, 16), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "BROADCAST TOOL")
        if not OCEAN and not PHARE and H > 60 and not self.gael.isVisible() and not self.compact:
            for x, y, a in self.erm:
                draw_ermine(p, x, H - y, mixc(RAIL, TXT, a), .95)
        now = time.time()
        self.rip = [(s_, i) for s_, i in self.rip if now - s_ < .5]
        for s_, i in self.rip:
            if now >= s_:
                k = (now - s_) / .45
                c = QColor(grad(.3 if i == 0 else .7))
                c.setAlphaF(max(0, 1 - k))
                p.setPen(QPen(c, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(38, 44), 46 * k, 46 * k)
        if er.top() >= self.items_bottom + 4:
            return
        hue = HUE.get(self.active, ACC) if PSYCHE else ACC
        r = QRectF(10, self.ind_y, w - 20, self.RH) if self.compact else QRectF(12, self.ind_y, w - 24, self.RH)
        if PSYCHE:
            soft_pill(p, r, mixc(RAIL, hue, .26), mixc(RAIL, hue, .08), 14)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(IND_C))
            p.drawRoundedRect(r, 14, 14)
        dpr = self.devicePixelRatioF()
        layer = self._items_layer(dpr)
        p.drawPixmap(QRectF(0, 0, w, layer.height() / dpr), layer, QRectF(layer.rect()))


class TopNav(NavBase):
    ITEMS = tuple(i for i in (("diff", "Diffusion"), ("son", "Processeur"), ("cart", "Cartoucheur"), ("rec", "Enregistrement"), ("mon", "Monitoring"),
                              ("net", "Réseau"), ("sos", "SOS"), ("set", "Réglages"), ("about", "À propos"))
                  if not MINI or i[0] in ("diff", "cart", "rec", "mon", "sos", "set"))
    H = 44

    def __init__(self):
        super().__init__()
        self.setFixedHeight(self.H)
        self.box, self.widths, self.x0, self.show_name = {}, {}, 56, True
        self.ux0 = self.ux1 = 0.0
        self.gl = QVariantAnimation(self)
        self.gl.setDuration(220)
        self.gl.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.gl.valueChanged.connect(self._glide)
        self.layout_items()

    def _glide(self, v):
        a, b = self.box[self.active]
        k = float(v)
        self.ux0, self.ux1 = self.g0 + (a - self.g0) * k, self.g1 + (b - self.g1) * k
        self.update()

    def layout_items(self):
        W = max(self.width(), 400)
        fm = QFontMetrics(QFont(self.font().family(), 10, QFont.Weight.Bold))
        nm = max(QFontMetrics(QFont(self.font().family(), 13, QFont.Weight.Bold)).horizontalAdvance(APP), QFontMetrics(QFont(self.font().family(), 8)).horizontalAdvance("BROADCAST TOOL") + 8)
        for name in (True, False):
            x0 = (58 + nm + 22) if name else 56
            full = {k: 36 + fm.horizontalAdvance(l) + 8 for k, l in self.ITEMS}
            allfull = sum(full.values()) + 4 * (len(full) - 1)
            widths = full if x0 + allfull <= W - 250 else {k: (full[k] if k == self.active else 40) for k, _ in self.ITEMS}
            if x0 + sum(widths.values()) + 4 * (len(widths) - 1) <= W - 250 or not name:
                break
        self.show_name, self.widths, self.x0 = name, widths, x0
        self.box, x = {}, x0
        for k, _ in self.ITEMS:
            self.box[k] = (x, x + widths[k])
            x += widths[k] + 4

    def resizeEvent(self, e):
        self.layout_items()
        self.ux0, self.ux1 = self.box[self.active]

    def key_at(self, x):
        for k, (a, b) in self.box.items():
            if a <= x < b:
                return k

    def mouseMoveEvent(self, e):
        self.set_hover(self.key_at(e.position().x()))

    def mouseReleaseEvent(self, e):
        k = self.key_at(e.position().x())
        if k:
            self.selected.emit(k)

    def select(self, key):
        self.g0, self.g1 = self.ux0, self.ux1
        self.active = key
        self.layout_items()
        self.gl.stop()
        if ANIM:
            self.gl.setStartValue(0.0)
            self.gl.setEndValue(1.0)
            self.gl.start()
        else:
            self.ux0, self.ux1 = self.box[key]
        self.update()

    def set_title(self, t):
        super().set_title(t)
        self.layout_items()

    def paintEvent(self, e):
        p = new_painter(self)
        p.fillRect(self.rect(), QColor(RAIL))
        cy = self.H // 2 - 1
        draw_logo_fast(p, 28, cy, 15, 0.0)
        if self.show_name:
            f = QFont(self.font())
            f.setPointSizeF(12)
            f.setBold(True)
            p.setFont(f)
            f.setPointSizeF(13)
            f.setWeight(QFont.Weight.ExtraBold)
            p.setFont(f)
            p.setPen(QColor(TXT))
            p.drawText(QRectF(52, 3, 300, 20), Qt.AlignmentFlag.AlignVCenter, APP)
            f2 = QFont(self.font())
            f2.setPointSizeF(6.6)
            f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.3)
            p.setFont(f2)
            p.setPen(QColor(MUT))
            p.drawText(QRectF(52, 22, 300, 17), Qt.AlignmentFlag.AlignVCenter, "BROADCAST TOOL")
        p.setPen(QColor(LINE))
        p.drawLine(0, self.H - 1, self.width(), self.H - 1)
        if self.air:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BADC))
            p.drawEllipse(QRectF(self.x0 - 14, cy - 3, 6, 6))
        for k, lab in self.ITEMS:
            a, b = self.box[k]
            on, hv = k == self.active, k == self.hover and k != self.active
            hue = HUE.get(k, ACC) if PSYCHE else ACC
            r = QRectF(a, cy - 17, b - a, 34)
            if on:
                if PSYCHE:
                    soft_pill(p, r, mixc(RAIL, hue, .30), mixc(RAIL, hue, .10), 12)
                else:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(IND_C))
                    p.drawRoundedRect(r, 12, 12)
            elif hv:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(HOVER_C))
                p.drawRoundedRect(r, 12, 12)
            col = hue if on else (mixc(ICON_C, hue, .65) if hv else ICON_C)
            if self.widths[k] > 46:
                draw_icon(p, k, a + 19, cy, col)
                f = QFont(self.font())
                f.setPointSizeF(9.5)
                f.setBold(on)
                p.setFont(f)
                p.setPen(QColor(TXT if (on or hv) else LABEL_C))
                p.drawText(QRectF(a + 35, cy - 17, b - a - 35, 34), Qt.AlignmentFlag.AlignVCenter, lab)
            else:
                draw_icon(p, k, (a + b) / 2, cy, col)
        hue = HUE.get(self.active, ACC) if PSYCHE else ACC
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(hue))
        p.drawRoundedRect(QRectF(self.ux0 + 6, self.H - 5, self.ux1 - self.ux0 - 12, 3), 1.5, 1.5)

# ------------------------------------------------------------------ vumètres, forme d'onde, liste de titres
SEGCOL = lambda t: (grad(t, ["#4cc9f0", "#a76bff", "#ff5fa2", "#ff5d6c"]) if PSYCHE else
                    (mixc("#35d49a", "#c9e85a", min(1, t / .6)) if t < .6 else mixc("#ffb03b", "#e5483f", (t - .6) / .4)))
TRACK = "#dfe3ec" if LIGHT else ("#12284a" if PHARE else "#1b2030")
_SEGC = {}


def segcols(n):
    """Couleurs des segments de vumètre, calculées une seule fois."""
    if n not in _SEGC:
        _SEGC[n] = [SEGCOL((k + .5) / n) for k in range(n)]
    return _SEGC[n]


def seg_strip(key, w, h, dpr, rows, x0, sw, seg, inset, gap, sh):
    """Image (mise en cache) de toutes les LEDs allumées d'un vumètre : chaque image affichée n'en recopie qu'une partie
    (un seul appel de dessin par barre au lieu d'un rectangle par segment)."""
    k = (key, w, h, dpr, rows, x0, sw, seg)
    pm = _SEGPM.get(k)
    if pm is None:
        if len(_SEGPM) > 24:
            _SEGPM.clear()
        pm = QPixmap(max(1, int(math.ceil(w * dpr))), max(1, int(math.ceil(h * dpr))))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.setPen(Qt.PenStyle.NoPen)
        sc = segcols(seg)
        for y in rows:
            for k2 in range(seg):
                q.setBrush(sc[k2])
                q.drawRect(QRectF(x0 + k2 * sw + inset, y, sw - gap, sh))
        q.end()
        _SEGPM[k] = pm
    return pm


_SEGPM = {}


class LevelMeter(QWidget):
    """Deux barres de niveau (G / D) en dégradé, avec crête et seuil. Repeint seulement quand ce qui est affiché change
    (nombre de LEDs, repère de crête, valeur en dB) ; les LEDs viennent d'une image pré-rendue."""
    SEG = 40

    def __init__(self, label=""):
        super().__init__()
        self.setFixedSize(300, 52)
        self.val, self.hold, self.ht = [-60.0, -60.0], [-60.0, -60.0], [0.0, 0.0]
        self.lamp_t, self.thr, self.note, self._t = 0.0, None, "", 0.0
        self._sig = None

    def x_of(self, db, w=None):
        w = w or self.width()
        return 22 + max(0.0, min(1.0, (db + 60) / 60)) * (w - 22 - 54)

    def _nseg(self, v):
        return int(max(0.0, min(1.0, (v + 60) / 60)) * self.SEG + .5)

    def set(self, peaks, thr=None, clip=False):
        now = time.time()
        dt = min(.1, now - self._t) if self._t else .016
        self._t = now
        if clip:
            self.lamp_t = now
        up, down = 1 - (1 - .55) ** (dt / .05), 1 - (1 - .14) ** (dt / .05)      # même réponse quelle que soit la cadence
        for i in (0, 1):
            tgt = max(peaks[i], -60.0)
            self.val[i] += (tgt - self.val[i]) * (up if tgt > self.val[i] else down)
            if self.val[i] >= self.hold[i] or now - self.ht[i] > 1.3:
                self.hold[i], self.ht[i] = self.val[i], now
        self.thr = thr
        if self.isVisible():
            W = self.width()
            sig = (self._nseg(self.val[0]), self._nseg(self.val[1]), int(self.x_of(self.hold[0], W)), int(self.x_of(self.hold[1], W)),
                   round(self.val[0]) if self.val[0] > -59 else None, round(self.val[1]) if self.val[1] > -59 else None,
                   thr, now - self.lamp_t < 2.5, self.note, W)
            if sig != self._sig:
                self._sig = sig
                self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        W = self.width()
        x0, x1 = 22, W - 54
        if self.note:
            p.setOpacity(.45)
        sw = (x1 - x0) / self.SEG
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        f.setBold(True)
        p.setFont(f)
        f2 = QFont(f)
        f2.setBold(False)
        strip = seg_strip("lv", W, 40, self.devicePixelRatioF(), (6, 26), x0, sw, self.SEG, .5, .5, 10)
        hold_pen = QPen(QColor("#ffffff" if not LIGHT else "#333333"), 2)
        for i, y in enumerate((4, 24)):
            p.setPen(QColor(MUT))
            p.drawText(QRectF(2, y, 16, 14), Qt.AlignmentFlag.AlignCenter, "LR"[i])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(TRACK))
            p.drawRoundedRect(QRectF(x0, y, x1 - x0, 14), 7, 7)
            n = self._nseg(self.val[i])
            if n:
                p.save()
                p.setClipRect(QRectF(x0, y, n * sw + .25, 14))
                p.drawPixmap(QPointF(0, 0), strip)
                p.restore()
            hx = self.x_of(self.hold[i], W)
            if hx > 25:
                p.setPen(hold_pen)
                p.drawLine(QPointF(hx, y + 1), QPointF(hx, y + 13))
            p.setPen(QColor(MUT))
            p.setFont(f2)
            t = f"{self.val[i]:.0f} dB" if self.val[i] > -59 else "-∞"
            p.drawText(QRectF(W - 52, y, 50, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, t)
            p.setFont(f)
        if self.thr is not None:
            tx = self.x_of(self.thr, W)
            p.setPen(QPen(QColor(ACC2), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(tx, 0), QPointF(tx, 40))
        f3 = QFont(f)
        f3.setPointSizeF(6.5)
        f3.setBold(False)
        p.setFont(f3)
        p.setPen(QColor("#566074"))
        for db in (-60, -40, -20, -6, 0):
            p.drawText(QRectF(self.x_of(db, W) - 14, 40, 28, 11), Qt.AlignmentFlag.AlignCenter, str(db))
        if time.time() - self.lamp_t < 2.5:
            p.setFont(f)
            p.setPen(QColor(BADC))
            p.drawText(QRectF(W - 54, 40, 50, 11), Qt.AlignmentFlag.AlignRight, "CLIP")
        if self.note:
            p.setOpacity(1)
            f4 = QFont(self.font())
            f4.setPointSizeF(8.5)
            f4.setBold(True)
            p.setFont(f4)
            fm = QFontMetrics(f4)
            tw = fm.horizontalAdvance(self.note) + 18
            r = QRectF((x0 + x1 - tw) / 2, 13, tw, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(PANEL))
            p.drawRoundedRect(r, 10, 10)
            p.setPen(QColor(MUT))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.note)


class LoudChip(QWidget):
    """Sonie de sortie, dans le bandeau (visible sur tous les onglets) : valeur court terme (3 s) en LUFS, et une échelle
    où la barre suit le court terme et le point la sonie instantanée (400 ms). Grise quand rien ne passe."""
    LO, HI = -36.0, -6.0

    def __init__(self):
        super().__init__()
        self.st, self.mo, self.on, self.what = None, None, False, ""
        self.setFixedSize(262, 38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Sonie de sortie (norme EBU R128) : court terme sur 3 s, et point = instantanée (400 ms).\n"
                        "Repères : −23 LUFS télévision, −16 LUFS flux Internet, −10 à −8 LUFS FM très traitée.\n"
                        "(clic : Processeur d'antenne)")

    def set(self, st, mo, on, what=""):
        st = None if st is None or st <= -69 else round(st, 1)
        mo = None if mo is None or mo <= -69 else round(mo, 1)
        if (st, mo, on, what) != (self.st, self.mo, self.on, self.what):
            self.st, self.mo, self.on, self.what = st, mo, on, what
            self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        r = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(FIELD))
        p.drawRoundedRect(r, 12, 12)
        live = self.on and self.st is not None
        f = QFont(self.font())
        f.setPixelSize(10)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        p.setFont(f)
        p.setPen(QColor(MUT))
        p.drawText(QRectF(12, 3, 128, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "SONIE" + (f" · {self.what}" if self.what else ""))
        f2 = QFont(self.font())
        f2.setPixelSize(15)
        f2.setBold(True)
        try:
            f2.setFeature(QFont.Tag("tnum"), 1)
        except Exception:
            pass
        p.setFont(f2)
        p.setPen(QColor(TXT if live else MUT))
        txt = (f"{self.st:+.1f}".replace(".", ",").replace("+", "") + " LUFS") if live else "— LUFS"
        p.drawText(QRectF(12, 17, 100, 19), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt.replace("-", "−"))
        # échelle
        x0, x1, y = 136.0, r.right() - 12, r.center().y() + 5
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(QRectF(x0, y - 3, x1 - x0, 6), 3, 3)
        k = lambda v: x0 + (x1 - x0) * max(0.0, min(1.0, (v - self.LO) / (self.HI - self.LO)))
        for v in (-23, -16):                                   # repères télévision / Internet
            p.setPen(QPen(qc(MUT, 150), 1))
            p.drawLine(QPointF(k(v), y - 6), QPointF(k(v), y + 6))
        p.setPen(Qt.PenStyle.NoPen)
        if live:
            g = QLinearGradient(x0, 0, x1, 0)
            g.setColorAt(0, QColor(ACC2))
            g.setColorAt(1, QColor(ACC))
            p.setBrush(QBrush(g))
            p.drawRoundedRect(QRectF(x0, y - 3, max(6.0, k(self.st) - x0), 6), 3, 3)
            if self.mo is not None:
                p.setBrush(QColor(TXT))
                p.drawEllipse(QPointF(k(self.mo), y), 4, 4)


class MiniMeter(QWidget):
    """Petits vumètres du bandeau. Repeints seulement quand l'affichage change (hors antenne : jamais)."""
    SEG = 28

    def __init__(self, W, label, ox=54):
        super().__init__()
        self.W, self.label, self.ox = W, label, ox
        self.setFixedSize(W, 27)
        self.shown, self.hold, self.ht = [-90.0, -90.0], [-90.0, -90.0], [0.0, 0.0]
        self.thr, self.clip, self.note, self._t = None, False, "", 0.0
        self._sig = None

    def _nseg(self, v):
        return int(max(0.0, min(1.0, (v + 60) / 60)) * self.SEG + .5)

    def _hx(self, i):
        span = self.W - self.ox - 4
        return int(self.ox + max(0.0, min(1.0, (self.hold[i] + 60) / 60)) * span) if self.hold[i] > -58 else None

    def set(self, peaks, thr=None, clip=False):
        now = time.time()
        dt = min(.1, now - self._t) if self._t else .016
        self._t = now
        for i in (0, 1):
            self.shown[i] = max(peaks[i], self.shown[i] - 28 * dt)
            if peaks[i] >= self.hold[i] or now - self.ht[i] > 1.2:
                self.hold[i], self.ht[i] = max(peaks[i], self.shown[i]), now
        self.thr, self.clip = thr, clip
        if self.isVisible():
            sig = (self._nseg(self.shown[0]), self._nseg(self.shown[1]), self._hx(0), self._hx(1), thr, clip, self.note)
            if sig != self._sig:
                self._sig = sig
                self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        ox, W = self.ox, self.W
        span = W - ox - 4
        sw = span / self.SEG
        f = QFont(self.font())
        f.setPointSizeF(7)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(MUT))
        p.drawText(QRectF(2, 0, ox - 4, 27), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label)
        if self.note:
            p.setOpacity(.4)
        strip = seg_strip("mini", W, 27, self.devicePixelRatioF(), (5, 15), ox, sw, self.SEG, .6, 1.2, 7)
        track = QColor("#d5d9e3" if LIGHT else "#252c3b")
        hold_pen = QPen(QColor("#ffffff" if not LIGHT else "#333"), 2)
        for i, y in enumerate((5, 15)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(track)
            p.drawRoundedRect(QRectF(ox - 1, y - 1, span + 2, 9), 4.5, 4.5)
            n = self._nseg(self.shown[i])
            if n:
                p.save()
                p.setClipRect(QRectF(ox, y, n * sw + .3, 7))
                p.drawPixmap(QPointF(0, 0), strip)
                p.restore()
            if self.hold[i] > -58:
                hx = ox + max(0.0, min(1.0, (self.hold[i] + 60) / 60)) * span
                p.setPen(hold_pen)
                p.drawLine(QPointF(hx, y - 1), QPointF(hx, y + 8))
        if self.thr is not None:
            tx = ox + (max(-60.0, min(0.0, self.thr)) + 60) / 60 * span
            p.setPen(QPen(QColor(ACC2), 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(tx, 1), QPointF(tx, 26))
        if self.clip:
            p.setPen(QColor(BADC))
            p.drawText(QRectF(W - 40, 0, 38, 27), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "CLIP")


class Wave(QWidget):
    """Forme d'onde défilante, fluide (60 i/s) : les niveaux arrivent ~20 fois par seconde et le défilement est interpolé
    entre deux mesures. Tout est dessiné d'un seul tracé rempli par un dégradé mis en cache : très peu coûteux."""
    PITCH, BAR = 4.0, 2.4

    def __init__(self, height=34, accent=None):
        super().__init__()
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.hist = [0.0] * 400
        self.t_push, self.dt, self.alive = 0.0, .05, -10.0
        self.accent = accent
        self._grad_w = None
        self.clock = QElapsedTimer()
        self.clock.start()
        self.on = False
        Ticker.add(self, self._tick, 60 if ANIM else 20, always=True)

    def push(self, db):
        now = self.clock.elapsed() / 1000.0
        v = max(0.0, min(1.0, (db + 60) / 60)) if db > -59 else 0.0
        if self.t_push:
            self.dt = self.dt * .8 + _cl(now - self.t_push, .01, .2) * .2
        self.t_push = now
        self.hist.append(v)
        del self.hist[0]
        if v > .02:
            self.alive = now
        # en silence (ou hors antenne), plus rien ne bouge au bout de 2,5 s : on ne relance pas l'animation pour rien
        if not self.on and self.isVisible() and now - self.alive <= 2.5:
            self.on = True

    def reset(self):
        self.hist = [0.0] * len(self.hist)
        self.update()

    def hideEvent(self, e):
        self.on = False

    def _tick(self, t, dt):
        if not self.on:
            return False
        now = self.clock.elapsed() / 1000.0
        if now - self.alive > 2.5 or now - self.t_push > .3:       # silence ou plus de données : on se met en veille
            self.on = False
        return True

    def resizeEvent(self, e):
        self._grad_w = None

    def brush(self):
        w = self.width()
        if self._grad_w != w:
            g = QLinearGradient(0, 0, w, 0)
            a = QColor(self.accent or (BLUE if PSYCHE else ACC2))
            g.setColorAt(0, mixc(PANEL, a, .12))
            g.setColorAt(.55, mixc(PANEL, ACC if not self.accent else a, .75))
            g.setColorAt(1, QColor(ACC2 if not self.accent else a).lighter(110))
            self._brush, self._grad_w = QBrush(g), w
        return self._brush

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        now = self.clock.elapsed() / 1000.0
        frac = _cl((now - self.t_push) / max(.01, self.dt)) if self.on else 0.0
        n = int(w / self.PITCH) + 2
        hist = self.hist
        L = len(hist)
        mid, amp = h / 2, h / 2 - 2
        rects = []
        bar, pitch = self.BAR, self.PITCH
        f1 = 1 - frac
        for i in range(min(n, L - 1)):
            k = L - 1 - i
            v = hist[k] * f1 + hist[k - 1] * frac
            a = v * amp
            if a < 1.0:
                a = 1.0
            rects.append(QRectF(w - (i + frac) * pitch - bar, mid - a, bar, a + a))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.brush())
        p.drawRects(rects)                      # un seul appel de dessin pour toutes les barres


BLUE = "#4cc9f0"


def pcm_peak_db(b):
    """Crête (dBFS) d'un bloc PCM 16 bits."""
    if not b:
        return -90.0
    try:
        if np is not None:
            a = np.frombuffer(b[:len(b) // 2 * 2], dtype="<i2")
            pk = int(np.abs(a.astype(np.int32)).max()) if len(a) else 0
        else:
            from array import array as _arr
            a = _arr("h")
            a.frombytes(b[:len(b) // 2 * 2])
            pk = max((abs(x) for x in a[::4]), default=0)
    except Exception:
        return -90.0
    return 20 * math.log10(pk / 32768.0) if pk > 0 else -90.0


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
