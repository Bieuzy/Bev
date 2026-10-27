# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - imports Qt, thème (couleurs, ambiances, feuille de style), widgets de base et petits utilitaires de dialogue."""
import base64
import hashlib
import importlib.util
import json
import math
import os
import platform
import random
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from array import array
from collections import deque

from bev_version import *  # noqa: F401,F403
from bev_core import *  # noqa: F401,F403
from bev_core import _cover_extract, _engine_worker_main  # noqa: F401
from bev_assets import _FONT_BLOB, _ICON_B64  # noqa: F401

from PySide6.QtCore import (QEasingCurve, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal, QElapsedTimer)
from PySide6.QtGui import (QBrush, QColor, QCursor, QFont, QFontDatabase, QFontMetrics, QFontMetricsF, QIcon, QImage, QKeySequence,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QWidgetAction
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLayout, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QStackedWidget, QStyledItemDelegate, QWidgetItem as _WItem,
                               QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)


def _selftest_secrets(errs):
    """Selftest : chiffrement DPAPI des mots de passe (Windows) aller-retour, et vérification de signature Ed25519."""
    import bev_core as _bc
    try:
        seed = bytes(range(32))
        if not ed25519_verify(ed25519_public(seed), b"bev", ed25519_sign(seed, b"bev")):
            errs.append("signature Ed25519 : vérification en échec")
    except Exception as ex:
        errs.append(f"signature Ed25519 : {ex}")
    if SYS != "Windows":
        return "sans objet (Windows seulement)"
    try:
        d = {"profiles": {"t": {"outputs": [{"password": "essai-é"}]}}, "alerts": {"url": "https://exemple/x"}}
        enc = _bc.protect_secrets(d)
        if not enc["profiles"]["t"]["outputs"][0]["password"].startswith(SECRET_PREFIX):
            raise RuntimeError("non chiffré")
        _bc.reveal_secrets(enc)
        if enc != d:
            raise RuntimeError("relecture différente")
        return "oui (DPAPI)"
    except Exception as ex:
        errs.append(f"chiffrement des mots de passe : {ex}")
        return "ÉCHEC"


def _early_settings():
    try:
        with open(CONF, encoding="utf-8") as f:
            return json.load(f).get("settings", {}) or {}
    except Exception:
        return {}


SET = _early_settings()
ACCENTS = {"Phare": ("#ffb03b", "#ffd27a"), "Orange": ("#ff7a45", "#ffb347"), "Rose": ("#ff4f7b", "#ff9db5"), "Bleu": ("#3d8bff", "#86b8ff"),
           "Vert": ("#22c58b", "#7fe6bd"), "Violet": ("#9b6bff", "#c5a8ff"), "Hermine": ("#e9edf5", "#ffffff")}
MINI = bool(SET.get("mini"))        # mode minimaliste : austère, sans animation, centré sur la diffusion
NEWLOOK = SET.get("look_v") == 2          # tant que l'utilisateur n'a rien choisi, l'ambiance « Phare » (celle du logo) s'applique partout
MOOD = "sobre" if MINI else (SET.get("mood", "phare") if NEWLOOK else "phare")
if MOOD not in ("phare", "psyche", "sobre"):     # (l'ambiance « Océan » a été retirée : on revient à « Phare Ouest »)
    MOOD = "phare"
OCEAN, PSYCHE, PHARE = MOOD == "ocean", MOOD == "psyche", MOOD == "phare"
NAVTOP = SET.get("nav") == "top" or MINI
ANIM = not (SET.get("perf") or SET.get("reduce_anim") or MINI)
ACC, ACC2 = ACCENTS.get(SET.get("accent") if NEWLOOK else "Phare", ACCENTS["Phare"])
if MINI:
    ACC = ACC2 = "#d4d7de"
if OCEAN:
    ACC, ACC2 = "#2fd6c0", "#7cc7ff"
PSY = ("#ff5fa2", "#a76bff", "#4cc9f0", "#35d49a", "#ffb347")


def _is_light():
    th = SET.get("theme", "dark")
    if th == "light":
        return True
    if th != "auto":
        return False
    try:
        if SYS == "Windows":
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return bool(winreg.QueryValueEx(k, "AppsUseLightTheme")[0])
        if SYS == "Darwin":
            return "dark" not in run(["defaults", "read", "-g", "AppleInterfaceStyle"]).lower()
    except Exception:
        pass
    return False


LIGHT = _is_light() and not OCEAN and not MINI


def mixc(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(int(a.red() * (1 - t) + b.red() * t), int(a.green() * (1 - t) + b.green() * t), int(a.blue() * (1 - t) + b.blue() * t))


if LIGHT:
    PAGE, RAIL, PANEL, FIELD, LINE = "#f4f5f8", "#ffffff", "#ffffff", "#eceef3", "#dfe3ec"
    TXT, MUT = "#171a22", "#6b7488"
elif MINI:
    PAGE, RAIL, PANEL, FIELD, LINE = "#0f0f10", "#0f0f10", "#171718", "#202022", "#2d2d30"
    TXT, MUT = "#e6e6e8", "#8d8d93"
elif PHARE:
    PAGE, RAIL, PANEL, FIELD, LINE = "#0a1a30", "#081426", "#102442", "#173055", "#243f66"
    TXT, MUT = "#f3f6fb", "#8ea4c2"
elif OCEAN:
    PAGE, RAIL, PANEL, FIELD, LINE = "#0a1b2c", "#071522", "#0f2438", "#143049", "#1b3a56"
    TXT, MUT = "#e6f1fb", "#7f9bb5"
else:
    PAGE, RAIL, PANEL, FIELD, LINE = "#0e1119", "#0b0e15", "#151a25", "#1b2130", "#262c3a"
    TXT, MUT = "#eef1f7", "#8a93a8"
OKC, BADC = ("#13a56f", "#d6455d") if LIGHT else ("#35d49a", "#ff6b6b")
ACCT = mixc(ACC2, "#000000", .42).name() if LIGHT else ACC2
ONACC = "#0b1f3a" if (PHARE and ACC == "#ffb03b") else ("#1d0d03" if QColor(ACC).lightnessF() > .62 else "#ffffff")
FONT_FAMILY = "Inter"


def qss():
    return f"""
* {{ font-family: '{FONT_FAMILY}', 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif; font-size: 13px; }}
QWidget {{ color: {TXT}; }}
QMainWindow, QDialog, #page {{ background: {PAGE}; }}
QLabel {{ background: transparent; }}
QLabel#mut {{ color: {MUT}; }}
QLabel#title {{ font-size: 21px; font-weight: 700; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 6px 10px; selection-background-color: {ACC}; selection-color: {ONACC}; }}
QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-color: {ACC}; }}
QComboBox {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px 10px; min-height: 20px; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {FIELD}; border: 1px solid {LINE}; selection-background-color: {ACC}; selection-color: {ONACC}; outline: 0; }}
QPushButton {{ background: {FIELD}; border: none; border-radius: 11px; padding: 7px 14px; font-weight: 600; }}
QPushButton:hover {{ background: {mixc(FIELD, TXT, .10).name()}; }}
QPushButton:pressed {{ background: {mixc(FIELD, TXT, .18).name()}; }}
QPushButton:disabled {{ color: {mixc(MUT, PANEL, .35).name()}; background: {mixc(FIELD, PANEL, .45).name()}; }}
QPushButton[kind="primary"]:disabled {{ background: {mixc(FIELD, PANEL, .2).name()}; color: {mixc(MUT, PANEL, .3).name()}; }}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {mixc(MUT, PANEL, .3).name()};
    background: {mixc(FIELD, PANEL, .5).name()}; border-color: {mixc(LINE, PANEL, .4).name()}; }}
QSlider::sub-page:horizontal:disabled {{ background: {mixc(MUT, PANEL, .4).name()}; }}
QSlider::handle:horizontal:disabled {{ background: {mixc(MUT, PANEL, .2).name()}; }}
QPushButton[kind="primary"] {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACC},stop:1 {'#ff5fa2' if PSYCHE else ACC2}); color: {ONACC}; }}
QPushButton[kind="primary"]:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {mixc(ACC, '#ffffff', .12).name()},stop:1 {mixc('#ff5fa2' if PSYCHE else ACC2, '#ffffff', .12).name()}); }}
QPushButton[kind="danger"] {{ background: #e5485a; color: white; }}
QPushButton[kind="danger"]:hover {{ background: #f05a6c; }}
QPushButton[kind="danger"]:disabled {{ background: {mixc(FIELD, PANEL, .45).name()}; color: {mixc(MUT, PANEL, .35).name()}; }}
QPushButton[kind="stop"] {{ background: #2a3040; color: white; }}
QSlider::groove:horizontal {{ height: 6px; background: {FIELD}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {ACC},stop:1 {'#ff5fa2' if PSYCHE else ACC2}); border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; border: 1px solid {LINE}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {mixc(FIELD, TXT, .18).name()}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {mixc(FIELD, TXT, .18).name()}; border-radius: 4px; min-width: 30px; }}
QTableWidget, QListWidget {{ background: transparent; border: none; outline: 0; gridline-color: transparent; }}
QTableWidget::item {{ padding: 6px 6px 6px 10px; border: none; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: transparent; border: none; color: {TXT}; }}
QTableWidget::item:focus, QListWidget::item:focus {{ border: none; outline: 0; }}
QListWidget::item {{ padding: 8px 12px; border-radius: 10px; margin: 2px 4px; }}
QListWidget::item:hover {{ background: transparent; }}
QHeaderView {{ background: transparent; border: none; }}
QTableCornerButton::section {{ background: transparent; border: none; }}
QHeaderView::section {{ background: transparent; color: {MUT}; border: none; padding: 8px 6px; font-weight: 700; font-size: 11px; }}
QMenu {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 7px; }}
QMenu::item:selected {{ background: {ACC}; color: {ONACC}; }}
QToolTip {{ background: {FIELD}; color: {TXT}; border: 1px solid {LINE}; padding: 5px 8px; }}
QCheckBox {{ spacing: 8px; }}
"""

# ------------------------------------------------------------------ widgets Qt maison
def qc(c, a=255):
    c = QColor(c)
    c.setAlpha(a)
    return c


def set_ss(w, sheet):
    """Applique une feuille de style seulement si elle change (les mises à jour périodiques renvoient souvent la même :
    l'appliquer quand même relance le calcul du style du widget)."""
    if w.property("_ss") != sheet:
        w.setProperty("_ss", sheet)
        w.setStyleSheet(sheet)


def btn(text, kind="", fn=None, tip=""):
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if fn:
        b.clicked.connect(lambda *_: fn())
    if tip:
        b.setToolTip(tip)
    b.setMinimumWidth(b.fontMetrics().horizontalAdvance(text) + 42)
    return b


def lab(text="", name="", wrap=False):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


class Card(QFrame):
    """Panneau arrondi avec ombre légère, peint à la main (rapide à redimensionner)."""

    def __init__(self, title="", sub="", parent=None, accent=None):
        super().__init__(parent)
        self.accent = accent
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(18, 14, 18, 16)
        self.lay.setSpacing(10)
        if title:
            h = QHBoxLayout()
            self.head = QLabel(title)
            self.head.setStyleSheet("font-size:15px;font-weight:700;")
            h.addWidget(self.head)
            h.addStretch(1)
            self.hl = h
            self.lay.addLayout(h)
            if sub:
                # une ligne (« … » si la place manque, texte complet en infobulle) : un sous-titre qui passe à la ligne
                # donne à la carte une hauteur dépendant de sa largeur, et Qt lui réserve alors sa hauteur IDÉALE au lieu
                # de sa hauteur minimale : les cartes suivantes débordaient (Diffusion : anecdote sur « À l'antenne »)
                s = CLabel(sub, "mut", False, MUT)
                s.elide = True
                s.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                s.setMinimumWidth(40)
                s.setStyleSheet("font-size:12px;")
                self.sub = s
                self.lay.addWidget(s)
                self.lay.addSpacing(2)

    def set_compact(self, on):
        """Fenêtre basse : marges plus serrées et sous-titre masqué, pour que tout tienne sans défiler."""
        if getattr(self, "_compact", None) == on:
            return
        self._compact = on
        m = self.lay.contentsMargins()
        if not hasattr(self, "_m0"):
            self._m0 = (m.left(), m.top(), m.right(), m.bottom(), self.lay.spacing())
        l, t, r, b, sp = self._m0
        if on:
            self.lay.setContentsMargins(l, max(6, t - 6), r, max(6, b - 6))
            self.lay.setSpacing(max(5, sp - 4))
        else:
            self.lay.setContentsMargins(l, t, r, b)
            self.lay.setSpacing(sp)
        if getattr(self, "sub", None) is not None:
            self.sub.setVisible(not on)

    _NINE = {}
    C = 20                     # taille des coins (px logiques) de l'image modèle

    @classmethod
    def nine(cls, dpr):
        """Modèle du fond (ombre + panneau arrondi + liseré) dessiné UNE fois : chaque carte en recopie les coins et étire
        les bords. Le dessin ne dépend plus de la taille : redimensionner la fenêtre ne coûte presque rien."""
        pm = cls._NINE.get(dpr)
        if pm is None:
            C = cls.C
            S = 2 * C + 4
            pm = QPixmap(int(round(S * dpr)), int(round(S * dpr)))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            cls._bg_shape(q, QRectF(0, 0, S, S))
            q.end()
            cls._NINE[dpr] = pm
        return pm

    @staticmethod
    def _bg_shape(p, rect):
        r = QRectF(rect).adjusted(1, 1, -1, -2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#000000", 14 if not LIGHT else 8))
        p.drawRoundedRect(r.translated(0, 1.5), 16, 16)
        p.setBrush(QColor(PANEL))
        p.setPen(QPen(QColor(LINE), 1))
        p.drawRoundedRect(r, 16, 16)

    def paint_bg(self, p, er):
        dpr = self.devicePixelRatioF()
        pm = self.nine(dpr)
        C = self.C
        S = 2 * C + 4
        W, H = self.width(), self.height()
        if W < S or H < S:                       # très petite carte : dessin direct
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._bg_shape(p, QRectF(self.rect()))
            return
        d = dpr
        xs = ((0, C, 0, C), (C, W - C, C, C + 4), (W - C, W, C + 4, S))        # (x0, x1 cible, sx0, sx1 source)
        ys = ((0, C, 0, C), (C, H - C, C, C + 4), (H - C, H, C + 4, S))
        for tx0, tx1, sx0, sx1 in xs:
            for ty0, ty1, sy0, sy1 in ys:
                t = QRectF(tx0, ty0, tx1 - tx0, ty1 - ty0)
                if not er.intersects(t.toAlignedRect()):
                    continue
                p.drawPixmap(t, pm, QRectF(sx0 * d, sy0 * d, (sx1 - sx0) * d, (sy1 - sy0) * d))

    def paintEvent(self, e):
        p = QPainter(self)
        self.paint_bg(p, e.rect())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -2)
        if self.accent:
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            g.setColorAt(0, QColor(ACC))
            g.setColorAt(1, QColor("#ff5fa2" if PSYCHE else ACC2))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawRoundedRect(QRectF(r.left() + 16, r.top(), r.width() - 32, 3), 1.5, 1.5)


class Switch(QCheckBox):
    """Interrupteur façon iOS."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._t = 1.0 if self.isChecked() else 0.0
        self.an = QVariantAnimation(self)
        self.an.setDuration(120)
        self.an.valueChanged.connect(lambda v: (setattr(self, "_t", float(v)), self.update()))
        self.toggled.connect(self._go)

    def _go(self, on):
        self.an.stop()
        self.an.setStartValue(self._t)
        self.an.setEndValue(1.0 if on else 0.0)
        self.an.start()

    def setChecked(self, on):
        super().setChecked(on)
        self.an.stop()                       # changement par le programme : position finale tout de suite (pas d'animation)
        self._t = 1.0 if on else 0.0
        self.update()

    def sizeHint(self):
        return QSize(44 + (8 + self.fontMetrics().horizontalAdvance(self.text()) if self.text() else 0), 26)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(.4)
        t = self._t
        tr = QRectF(0, 3, 42, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mixc(FIELD if not LIGHT else "#c9ced9", ACC, t))
        p.drawRoundedRect(tr, 10, 10)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(2 + 20 * t, 5, 16, 16))
        if self.text():
            p.setPen(QColor(TXT))
            p.drawText(QRectF(52, 0, self.width() - 52, self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


class Chip(QWidget):
    """Pastille d'état (ex. HORS ANTENNE / À L'ANTENNE)."""
    clicked = Signal()

    def __init__(self, text="", color=MUT, parent=None):
        super().__init__(parent)
        self.text, self.col, self.pulse = text, color, 0.0
        self.setFixedHeight(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set(self, text, color, pulse=False):
        if (text, color) != (self.text, self.col):
            self.text, self.col = text, color
            self.updateGeometry()
        self.pulse = 1.0 if pulse else 0.0
        self.update()

    def sizeHint(self):
        return QSize(self.fontMetrics().horizontalAdvance(self.text) + 44, 30)

    def mouseReleaseEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(self.col, 36))
        p.drawRoundedRect(r, 15, 15)
        p.setBrush(QColor(self.col))
        p.drawEllipse(QRectF(12, 11, 8, 8))
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(9)
        p.setFont(f)
        p.setPen(QColor(self.col))
        p.drawText(r.adjusted(26, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)


class Meter(QWidget):
    """Vumètre stéréo horizontal (dBFS)."""

    def __init__(self, parent=None, lo=-60.0):
        super().__init__(parent)
        self.v, self.hold, self.lo = [-90.0, -90.0], [-90.0, -90.0], lo
        self.clip = False
        self.setMinimumHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(32)

    def set(self, v, clip=False):
        nv = [max(self.lo, x) for x in v]
        for i in (0, 1):
            self.hold[i] = max(nv[i], self.hold[i] - 1.2)
        if nv != self.v or clip != self.clip:
            self.v, self.clip = nv, clip
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bh = (h - 6) / 2
        p.setPen(Qt.PenStyle.NoPen)
        for i in (0, 1):
            y = i * (bh + 2)
            p.setBrush(QColor(FIELD))
            p.drawRoundedRect(QRectF(0, y, w, bh), bh / 2, bh / 2)
            fr = max(0.0, min(1.0, (self.v[i] - self.lo) / -self.lo))
            if fr > 0:
                g = QLinearGradient(0, 0, w, 0)
                g.setColorAt(0, QColor(OKC))
                g.setColorAt(.75, QColor("#ffc23d"))
                g.setColorAt(1, QColor("#ff4f5e"))
                p.setBrush(QBrush(g))
                p.setClipRect(QRectF(0, y, w * fr, bh))
                p.drawRoundedRect(QRectF(0, y, w, bh), bh / 2, bh / 2)
                p.setClipping(False)
            hf = max(0.0, min(1.0, (self.hold[i] - self.lo) / -self.lo))
            if hf > .02:
                p.setBrush(QColor(TXT))
                p.drawRect(QRectF(w * hf - 2, y, 2, bh))
        if self.clip:
            p.setBrush(QColor("#ff4f5e"))
            p.drawEllipse(QRectF(w - 10, h / 2 - 4, 8, 8))


class Flow(QLayout):
    """Mise en page « flux » pour les tuiles."""

    def __init__(self, parent=None, gap=12):
        super().__init__(parent)
        self.items, self.gap, self.tw, self.ratio, self.th_min = [], gap, 150, .64, 78

    def addItem(self, it):
        self.items.append(it)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._lay(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._lay(r, False)

    def sizeHint(self):
        return QSize(self.tw, 90)

    def minimumSize(self):
        return QSize(self.tw, 90)

    def _lay(self, r, test):
        g = self.gap
        W = max(1, r.width() - g)
        cols = max(1, int(W // (self.tw + g)))
        tw = (W - g * (cols - 1)) // cols
        th = max(self.th_min, int(tw * self.ratio))
        for k, it in enumerate(self.items):
            if not test:
                it.setGeometry(QRect(r.x() + g + (k % cols) * (tw + g), r.y() + g + (k // cols) * (th + g), tw, th))
        rows = (len(self.items) + cols - 1) // cols
        return g + rows * (th + g)


class WrapRow(QLayout):
    """Rangée de boutons qui passe à la ligne quand la fenêtre est étroite (écran vertical) au lieu de couper les boutons.
    S'utilise comme un QHBoxLayout : addWidget, addStretch (l'espace libre se place là quand tout tient sur une ligne),
    addSpacing, setSpacing."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self.items, self.sp, self.stretch_at, self.vsp = [], spacing, None, 6
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, it):
        self.items.append(it)

    def addWidget(self, w, stretch=0, alignment=None):
        super().addWidget(w)

    def addStretch(self, s=1):
        if self.stretch_at is None:
            self.stretch_at = len(self.items)

    def addSpacing(self, px):
        from PySide6.QtWidgets import QSpacerItem
        self.items.append(QSpacerItem(int(px), 1))

    def setSpacing(self, s):
        self.sp = s

    def spacing(self):
        return self.sp

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._lay(QRect(0, 0, w, 0), True)

    def _vis(self):
        return [it for it in self.items if not (it.widget() is not None and it.widget().isHidden())]

    def sizeHint(self):
        v = self._vis()
        w = sum(it.sizeHint().width() for it in v) + self.sp * max(0, len(v) - 1)
        h = max([it.sizeHint().height() for it in v] or [0])
        return QSize(w, h)

    def minimumSize(self):
        v = self._vis()
        return QSize(max([it.minimumSize().width() for it in v] or [0]), max([it.sizeHint().height() for it in v] or [0]))

    def setGeometry(self, r):
        super().setGeometry(r)
        self._lay(r, False)

    def _lay(self, r, test):
        v = self._vis()
        if not v:
            return 0
        sizes = [it.sizeHint() for it in v]
        lines, cur, cw = [], [], 0
        for it, sz in zip(v, sizes):
            w = sz.width()
            if cur and cw + self.sp + w > r.width():
                lines.append(cur)
                cur, cw = [], 0
            cw += (self.sp if cur else 0) + w
            cur.append((it, sz))
        lines.append(cur)
        y = r.y()
        for ln in lines:
            lh = max(sz.height() for _, sz in ln)
            used = sum(sz.width() for _, sz in ln) + self.sp * (len(ln) - 1)
            extra = max(0, r.width() - used) if (len(lines) == 1 and self.stretch_at is not None) else 0
            x = r.x()
            for it, sz in ln:
                idx = self.items.index(it)
                if extra and idx >= self.stretch_at:
                    x += extra
                    extra = 0
                if not test:
                    it.setGeometry(QRect(int(x), int(y + (lh - sz.height()) / 2), sz.width(), sz.height()))
                x += sz.width() + self.sp
            y += lh + self.vsp
        return y - r.y() - self.vsp


class WaveLoader(QObject):
    """Calcule la forme d'onde d'un fichier avec ffmpeg (thread), mise en cache en mémoire."""
    done = Signal(str, list, float)

    def __init__(self):
        super().__init__()
        self.cache, self.busy = {}, set()

    def want(self, path):
        if path in self.cache:
            return self.cache[path]
        if path not in self.busy:
            self.busy.add(path)
            threading.Thread(target=self._run, args=(path,), daemon=True).start()
        return None

    def _run(self, path):
        bins, dur = [], 0.0
        try:
            if shutil.which("ffmpeg"):
                import array
                r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "4000",
                                    "-f", "s16le", "pipe:1"], capture_output=True, timeout=60,
                                   creationflags=0x08000000 if SYS == "Windows" else 0)
                n = len(r.stdout) // 2
                if n:
                    a = array.array("h")
                    a.frombytes(r.stdout[:n * 2])
                    dur = n / 4000.0
                    k = 360                    # fine résolution : l'inspecteur du cartoucheur l'affiche en grand
                    step = max(1, n // k)
                    bins = [max((abs(x) for x in a[i * step:(i + 1) * step]), default=0) / 32768.0 for i in range(k)]
                    pk = max(bins) or 1.0
                    bins = [b / pk for b in bins]
        except Exception as _ex:
            trace("_run", _ex)
        if not bins:
            rnd = random.Random(path)
            bins = [.25 + .75 * abs(math.sin(i / 25.0 + rnd.random())) for i in range(360)]
        self.cache[path] = (bins, dur)
        self.busy.discard(path)
        self.done.emit(path, bins, dur)


class Tile(QWidget):
    """Tuile du cartoucheur : l'état de lecture vient du moteur (cart_status)."""
    clicked = Signal(object)
    edit = Signal(object)

    def __init__(self, d, cid, parent=None):
        super().__init__(parent)
        self.d, self.cid = d, cid
        self.st = None
        self.bins, self.dur = [], 0.0
        self.hov, self.lift = False, 0.0
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(110, 74)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(140)
        self.anim.valueChanged.connect(lambda v: (setattr(self, "lift", float(v)), self.update()))

    def color(self):
        return QColor(CART_COLORS.get(self.d.get("color"), CART_COLORS["Bleu"]))

    def set_state(self, st):
        if st != self.st:
            self.st = st
            self.update()

    def _hover(self, on):
        self.anim.stop()
        self.anim.setStartValue(self.lift)
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def enterEvent(self, e):
        self._hover(True)

    def leaveEvent(self, e):
        self._hover(False)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self)
        elif e.button() == Qt.MouseButton.RightButton:
            self.edit.emit(self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        f = max(.85, min(1.5, w / 150.0))
        st = self.st
        playing = st is not None
        fading = playing and st[4]
        pre = playing and st[3]
        loop = playing and st[2]
        pos, tot = (st[0], st[1]) if playing else (0, 0)
        col = self.color()
        if not self.d.get("file"):
            col = QColor(FIELD)
        elif playing:
            col = col.darker(125)
        elif self.lift:
            col = col.lighter(100 + int(8 * self.lift))
        r = QRectF(2, 2 - 2 * self.lift, w - 4, h - 4)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(5):
            p.setBrush(QColor(0, 0, 0, 14))
            p.drawRoundedRect(r.adjusted(-i, 2 + i, i, 3 + i), 14 * f, 14 * f)
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0, col.lighter(112))
        g.setColorAt(1, col)
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor(255, 255, 255, 150), 2) if playing else Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 14 * f, 14 * f)
        name = self.d.get("name") or os.path.basename(self.d.get("file") or "") or "+ Ajouter un son"
        p.setPen(QColor("white") if self.d.get("file") else QColor(MUT))
        font = QFont(self.font())
        font.setBold(True)
        fm = None
        for sz in (11, 10, 9):
            font.setPointSizeF(sz * f * .85)
            fm = QFontMetrics(font)
            if max((fm.horizontalAdvance(t) for t in name.split()), default=0) <= w - 70 * f:
                break
        p.setFont(font)
        avail = w - 62 * f
        words = []
        for wd in name.split():
            if fm.horizontalAdvance(wd) <= avail:
                words.append(wd)
                continue
            cur = ""
            for ch in wd:
                if cur and fm.horizontalAdvance(cur + ch + "-") > avail:
                    words.append(cur + "-")
                    cur = ""
                cur += ch
            words.append(cur)
        p.drawText(QRectF(12, 9 - 2 * self.lift, avail, 44 * f), Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop, " ".join(words))
        key = self.d.get("key", "")
        if key:
            kf = QFont(font)
            kf.setPointSizeF(8 * f * .9)
            p.setFont(kf)
            kw = QFontMetrics(kf).horizontalAdvance(key) + 12
            p.setBrush(QColor(0, 0, 0, 70))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(w - 10 - kw, 8, kw, 17 * f), 7, 7)
            p.setPen(QColor("white"))
            p.drawText(QRectF(w - 10 - kw, 8, kw, 17 * f), Qt.AlignmentFlag.AlignCenter, key)
        prog = min(1.0, pos / tot) if playing and tot > 0 else 0.0
        if self.bins and not (playing and h < 125):
            n = len(self.bins)
            bw = (w - 24) / n
            mid, amp = h * .62, 8 * f
            for i, v in enumerate(self.bins):
                a = max(1.5, v * amp)
                on = playing and i / n <= prog
                p.setPen(QPen(QColor(255, 255, 255, 255 if on else 100), max(1.2, bw * .62), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                x = 12 + i * bw + bw / 2
                p.drawLine(QPoint(int(x), int(mid - a)), QPoint(int(x), int(mid + a)))
        if playing:
            bh = max(5, int(7 * f))
            by1 = h - 12
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 90))
            p.drawRoundedRect(QRectF(12, by1 - bh, w - 24, bh), bh / 2, bh / 2)
            p.setBrush(QColor("#f4d03f") if fading else QColor("white"))
            if prog > 0:
                p.drawRoundedRect(QRectF(12, by1 - bh, (w - 24) * prog, bh), bh / 2, bh / 2)
            tf = QFont(font)
            tf.setPointSizeF(14 * f * .8)
            p.setFont(tf)
            p.setPen(QColor("white"))
            txt = ("∞ " + fmt_ms(pos)) if loop else "-" + fmt_ms(max(0, tot - pos))
            p.drawText(QRectF(12, by1 - bh - 28 * f, w * .5, 26 * f), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)
            bd = "FONDU" if fading else ("ÉCOUTE" if pre else "DIRECT")
            bc = {"DIRECT": "#ff3b4e", "ÉCOUTE": "#2f9e8f", "FONDU": "#e0a800"}[bd]
            bf = QFont(font)
            bf.setPointSizeF(7.5 * f * .9)
            bwid = QFontMetrics(bf).horizontalAdvance(bd) + 26
            br = QRectF(w - 12 - bwid, by1 - bh - 24 * f, bwid, 18 * f)
            p.setBrush(QColor(bc))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(br, 9, 9)
            if bd != "FONDU":
                p.setBrush(QColor("white"))
                p.drawEllipse(QRectF(br.left() + 8, br.center().y() - 3, 6, 6))
            p.setFont(bf)
            p.setPen(QColor("white"))
            p.drawText(br.adjusted(16, 0, 0, 0), Qt.AlignmentFlag.AlignCenter, bd)
        elif self.dur:
            tf = QFont(font)
            tf.setPointSizeF(10 * f * .85)
            tf.setBold(False)
            p.setFont(tf)
            p.setPen(QColor(255, 255, 255, 220))
            p.drawText(QRectF(12, h - 30 * f, w * .6, 22 * f), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, fmt_ms(self.dur))


class Bridge(QObject):
    """Pont thread -> interface : les threads du moteur appellent log(), le signal repasse dans le thread Qt."""
    logged = Signal(str)
    call = Signal(object)


# ------------------------------------------------------------------ lignes de tableau : surbrillance douce, case « Actif »
from PySide6.QtWidgets import QStyle, QStyleOptionViewItem

CHECK_ROLE = Qt.ItemDataRole.UserRole + 1
TINT_ROLE = Qt.ItemDataRole.UserRole + 2         # couleur de ligne mise en avant (ex. lien réseau actif)


def paint_check(p, cx, cy, on, hover=False, size=18):
    r = QRectF(cx - size / 2, cy - size / 2, size, size)
    p.setPen(Qt.PenStyle.NoPen)
    if on:
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(ACC))
        g.setColorAt(1, QColor("#ff5fa2" if PSYCHE else ACC2))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QPen(QColor(ONACC), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline([QPointF(cx - 4.2, cy + .2), QPointF(cx - 1.2, cy + 3.2), QPointF(cx + 4.4, cy - 3.4)])
    else:
        p.setBrush(QColor(FIELD))
        p.setPen(QPen(mixc(LINE, TXT, .35 if hover else .18), 1.4))
        p.drawRoundedRect(r.adjusted(.7, .7, -.7, -.7), 6, 6)


class RowDelegate(QStyledItemDelegate):
    """Sélection et survol peints sur toute la ligne (pastille arrondie + filet d'accent), sans cadre de focus."""

    def __init__(self, view, check_col=None):
        super().__init__(view)
        self.view, self.check_col = view, check_col
        self.hrow = -1
        view.setMouseTracking(True)
        view.viewport().installEventFilter(self)
        pal = view.palette()                       # la vue peint aussi un fond de ligne : on le neutralise
        for grp in (pal.ColorGroup.Active, pal.ColorGroup.Inactive):
            pal.setColor(grp, pal.ColorRole.Highlight, QColor(0, 0, 0, 0))
            pal.setColor(grp, pal.ColorRole.HighlightedText, QColor(TXT))
        view.setPalette(pal)
        if isinstance(view, QTableWidget):
            view.verticalHeader().setDefaultSectionSize(40)

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == ev.Type.MouseMove:
            r = self.view.indexAt(ev.position().toPoint()).row()
            if r != self.hrow:
                self.hrow = r
                obj.update()
        elif t == ev.Type.Leave:
            if self.hrow != -1:
                self.hrow = -1
                obj.update()
        return False

    check_from_selection = False

    def paint(self, p, opt, idx):
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        hov = idx.row() == self.hrow
        tint = idx.data(TINT_ROLE)
        if sel or hov or tint:
            vp = self.view.viewport()
            r = QRectF(opt.rect)
            full = QRectF(3, r.top() + 2, vp.width() - 6, r.height() - 4)
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setClipRect(opt.rect)
            p.setPen(Qt.PenStyle.NoPen)
            base = tint or ACC
            if sel or tint:
                g = QLinearGradient(full.left(), 0, full.right(), 0)
                g.setColorAt(0, mixc(PANEL, base, (.22 if sel else .17) if not LIGHT else .14))
                g.setColorAt(1, mixc(PANEL, base if tint else ("#ff5fa2" if PSYCHE else ACC2), .07 + (.04 if hov else 0)))
                p.setBrush(QBrush(g))
            else:
                p.setBrush(mixc(PANEL, TXT, .05))
            p.drawRoundedRect(full, 12, 12)
            if sel or tint:
                p.setBrush(QColor(ACC if sel else base))
                p.drawRoundedRect(QRectF(full.left() + 3, full.top() + 9, 3, full.height() - 18), 1.5, 1.5)
            p.restore()
        o = QStyleOptionViewItem(opt)
        o.state &= ~(QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus | QStyle.StateFlag.State_MouseOver)
        o.backgroundBrush = QBrush(Qt.BrushStyle.NoBrush)
        if self.check_col is not None and idx.column() == self.check_col:
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            c = QRectF(opt.rect).center()
            paint_check(p, c.x(), c.y(), sel if self.check_from_selection else bool(idx.data(CHECK_ROLE)), hov)
            p.restore()
            return
        super().paint(p, o, idx)


def style_table(view, check_col=None):
    if getattr(view, "_row_dlg", None) is None:
        view._row_dlg = RowDelegate(view, check_col)
        view.setItemDelegate(view._row_dlg)
    elif check_col is not None:
        view._row_dlg.check_col = check_col
    return view._row_dlg




# ------------------------------------------------------------------ utilitaires communs
# (définis ici pour être disponibles dans tous les modules de l'interface)

def new_painter(w):
    p = QPainter(w)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    return p


def _cl(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


class CheckLine(QAbstractButton):
    """Case à cocher sobre (même dessin que les listes)."""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFixedHeight(24)

    def sizeHint(self):
        return QSize(26 + self.fontMetrics().horizontalAdvance(self.text()), 24)

    def paintEvent(self, e):
        p = new_painter(self)
        paint_check(p, 9, 12, self.isChecked(), self.underMouse(), 16)
        p.setPen(QColor(TXT))
        p.drawText(QRectF(25, 0, self.width() - 25, 24), Qt.AlignmentFlag.AlignVCenter,
                   self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width() - 26))


def _msg(parent, kind, title, text):
    m = QMessageBox(parent)
    m.setWindowTitle(title)
    m.setText(text)
    m.setIcon({"info": QMessageBox.Icon.Information, "err": QMessageBox.Icon.Critical, "warn": QMessageBox.Icon.Warning}.get(kind, QMessageBox.Icon.Information))
    m.exec()


def info(parent, title, text):
    _msg(parent, "info", title, text)


def err(parent, title, text):
    _msg(parent, "err", title, text)


def yes(parent, title, text):
    m = QMessageBox(parent)
    m.setWindowTitle(title)
    m.setText(text)
    m.setIcon(QMessageBox.Icon.Question)
    m.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    m.button(QMessageBox.StandardButton.Yes).setText("Oui")
    m.button(QMessageBox.StandardButton.No).setText("Non")
    return m.exec() == QMessageBox.StandardButton.Yes


def ask_text(parent, title, label, init=""):
    t, ok = QInputDialog.getText(parent, title, label, text=init)
    return t if ok else None


def row(label, w, width=150):
    h = QHBoxLayout()
    l = lab(label, "mut")
    l.setFixedWidth(width)
    h.addWidget(l)
    if isinstance(w, QWidget):
        h.addWidget(w)
    else:
        h.addLayout(w)
    h.addStretch(1)
    return h


API_URL = "https://api.anthropic.com/v1/messages"


LLM_MODELS = (("claude-haiku-5-5", "Rapide (Claude Haiku)"), ("claude-sonnet-5-5", "Plus fin (Claude Sonnet)"))


PAGE_KEYS = ["diff", "son", "cart", "rec", "mon", "net", "sos", "set", "about"]


PAGE_TITLES = {"diff": "Diffusion", "son": "Processeur", "cart": "Cartoucheur", "rec": "Enregistrement", "mon": "Monitoring",
               "net": "Réseau", "sos": "SOS", "set": "Réglages", "about": "À propos"}


AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac")


JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")


class CLabel(QLabel):
    """Étiquette dont la couleur change souvent (état d'antenne, signal…) : la couleur est appliquée au dessin, sans
    feuille de style (changer une feuille de style recalcule le style et la mise en page du widget à chaque fois)."""

    def __init__(self, text="", name="", wrap=False, color=None):
        super().__init__(text)
        if name:
            self.setObjectName(name)
        self.setWordWrap(wrap)
        self._col = color

    def set_color(self, c):
        if c != self._col:
            self._col = c
            self.update()

    def paintEvent(self, e):
        if self._col is None:
            return super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self.font())
        p.setPen(QColor(self._col))
        fl = int(self.alignment().value if hasattr(self.alignment(), "value") else self.alignment())
        txt = self.text()
        if self.wordWrap():
            fl |= int(Qt.TextFlag.TextWordWrap.value if hasattr(Qt.TextFlag.TextWordWrap, "value") else Qt.TextFlag.TextWordWrap)
        elif getattr(self, "elide", False):           # une seule ligne : « … » si la place manque (texte complet en infobulle)
            el = self.fontMetrics().elidedText(txt, Qt.TextElideMode.ElideRight, self.contentsRect().width())
            if el != txt:
                txt = el
            tip = self.text() if el != self.text() else ""
            if self.toolTip() != tip:
                self.setToolTip(tip)
        p.drawText(self.contentsRect(), fl, txt)


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
