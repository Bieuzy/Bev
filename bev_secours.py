# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - playlist de secours : bibliothèque, dossiers, liste des titres, fiche d'un titre."""
from bev_gael import *  # noqa: F401,F403

# ------------------------------------------------------------------ pochette par défaut
def default_cover_pm(size=96):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(mixc(PANEL, ACC, .25)))
    g.setColorAt(1, QColor(mixc(PANEL, "#a76bff" if PSYCHE else ACC2, .25)))
    p.setBrush(QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * .16, size * .16)
    draw_logo(p, size / 2, size / 2, size * .36, None, 3, 0.0, tile=False, sea=False)
    p.end()
    return pm


# ------------------------------------------------------------------ bibliothèque du secours (façon Apple Musique)
# Lecture des étiquettes et pochettes directement dans les fichiers (ID3, FLAC, MP4/M4A) : pas besoin de ffmpeg,
# donc fiable sous Windows. ffmpeg / ffprobe ne servent plus que de secours (OGG, formats exotiques, durée).
import struct as _st


def _syncsafe(b):
    return (b[0] & 0x7f) << 21 | (b[1] & 0x7f) << 14 | (b[2] & 0x7f) << 7 | (b[3] & 0x7f)


def _id3_text(data):
    if not data:
        return ""
    enc, raw = data[0], data[1:]
    try:
        if enc == 0:
            t = raw.decode("latin-1")
        elif enc == 1:
            t = raw.decode("utf-16")
        elif enc == 2:
            t = raw.decode("utf-16-be")
        else:
            t = raw.decode("utf-8")
    except Exception:
        t = raw.decode("latin-1", "replace")
    return t.replace("\x00", " / ").strip(" /")


def _id3(fh):
    h = fh.read(10)
    if len(h) < 10 or h[:3] != b"ID3":
        return {}
    ver, flags, size = h[3], h[5], _syncsafe(h[6:10])
    data = fh.read(size)
    if flags & 0x80:                                 # désynchronisation globale
        data = data.replace(b"\xff\x00", b"\xff")
    pos, out = 0, {}
    if flags & 0x40 and ver >= 3 and len(data) > 4:  # en-tête étendu
        ext = _syncsafe(data[:4]) if ver == 4 else _st.unpack(">I", data[:4])[0] + 4
        pos = ext
    names = {"TIT2": "title", "TPE1": "artist", "TALB": "album", "TPE2": "albumartist", "TCON": "genre", "TYER": "year", "TDRC": "year",
             "TT2": "title", "TP1": "artist", "TAL": "album", "TCO": "genre", "TYE": "year"}
    while pos < len(data) - 10:
        if ver == 2:
            fid, fsz, hl = data[pos:pos + 3].decode("latin-1", "replace"), int.from_bytes(data[pos + 3:pos + 6], "big"), 6
        else:
            fid = data[pos:pos + 4].decode("latin-1", "replace")
            fsz = _syncsafe(data[pos + 4:pos + 8]) if ver == 4 else _st.unpack(">I", data[pos + 4:pos + 8])[0]
            hl = 10
        if not fid.strip("\x00") or fsz <= 0:
            break
        body = data[pos + hl:pos + hl + fsz]
        pos += hl + fsz
        if fid in names and names[fid] not in out:
            out[names[fid]] = _id3_text(body)
        elif fid in ("APIC", "PIC") and "art" not in out and body:
            enc = body[0]
            if fid == "APIC":
                e = body.index(b"\x00", 1)
                ptype, i = body[e + 1], e + 2
            else:
                ptype, i = body[4], 5
            if enc in (1, 2):
                while i + 1 < len(body) and body[i:i + 2] != b"\x00\x00":
                    i += 2
                i += 2
            else:
                i = body.index(b"\x00", i) + 1
            img = body[i:]
            if img:
                out.setdefault("_arts", []).append((ptype, img))
    arts = out.pop("_arts", [])
    if arts:
        out["art"] = next((a for t, a in arts if t == 3), arts[0][1])   # 3 = recto de la pochette
    if out.get("genre", "").startswith("(") and ")" in out.get("genre", ""):
        out["genre"] = out["genre"].split(")", 1)[1] or out["genre"]
    return out


def _flac(fh):
    if fh.read(4) != b"fLaC":
        return {}
    out = {}
    while True:
        h = fh.read(4)
        if len(h) < 4:
            break
        last, typ, ln = h[0] & 0x80, h[0] & 0x7f, int.from_bytes(h[1:4], "big")
        b = fh.read(ln)
        if typ == 4:                                 # VORBIS_COMMENT
            try:
                vl = _st.unpack("<I", b[:4])[0]
                o = 4 + vl
                n = _st.unpack("<I", b[o:o + 4])[0]
                o += 4
                for _ in range(n):
                    cl = _st.unpack("<I", b[o:o + 4])[0]
                    k, _, v = b[o + 4:o + 4 + cl].decode("utf-8", "replace").partition("=")
                    o += 4 + cl
                    key = {"title": "title", "artist": "artist", "album": "album", "genre": "genre", "date": "year"}.get(k.lower())
                    if key and key not in out:
                        out[key] = v
            except Exception as _ex:
                trace("_flac", _ex)
        elif typ == 6 and "art" not in out:           # PICTURE
            try:
                o = 4
                ml = _st.unpack(">I", b[o:o + 4])[0]
                o += 4 + ml
                dl = _st.unpack(">I", b[o:o + 4])[0]
                o += 4 + dl + 16
                il = _st.unpack(">I", b[o:o + 4])[0]
                out["art"] = b[o + 4:o + 4 + il]
            except Exception:
                pass
        if last:
            break
    return out


def _mp4(fh):
    out = {}
    fh.seek(0, 2)
    end = fh.tell()

    def atoms(start, stop):
        pos = start
        while pos + 8 <= stop:
            fh.seek(pos)
            h = fh.read(8)
            if len(h) < 8:
                return
            size, name = _st.unpack(">I", h[:4])[0], h[4:8]
            hl = 8
            if size == 1:
                size, hl = _st.unpack(">Q", fh.read(8))[0], 16
            elif size == 0:
                size = stop - pos
            if size < hl:
                return
            yield name, pos + hl, pos + size
            pos += size
    keys = {b"\xa9nam": "title", b"\xa9ART": "artist", b"\xa9alb": "album", b"\xa9gen": "genre", b"\xa9day": "year", b"covr": "art"}

    def walk(start, stop, depth=0):
        for name, a, b in atoms(start, stop):
            if name in (b"moov", b"udta", b"ilst"):
                walk(a, b, depth + 1)
            elif name == b"meta":
                walk(a + 4, b, depth + 1)
            elif name in keys and keys[name] not in out:
                for n2, a2, b2 in atoms(a, b):
                    if n2 == b"data":
                        fh.seek(a2 + 8)
                        raw = fh.read(b2 - a2 - 8)
                        out[keys[name]] = raw if name == b"covr" else raw.decode("utf-8", "replace")
                        break
    fh.seek(4)
    if fh.read(4) != b"ftyp":
        return {}
    walk(0, end)
    return out


def read_tags(path):
    """{title, artist, album, genre, year, art (octets de l'image)} lus dans le fichier ; {} si rien."""
    try:
        with open(path, "rb") as fh:
            low = path.lower()
            if low.endswith(".flac"):
                return _flac(fh)
            if low.endswith((".m4a", ".mp4", ".aac", ".alac", ".m4b")):
                r = _mp4(fh)
                if r or not low.endswith(".aac"):
                    return r
                fh.seek(0)
            return _id3(fh)
    except Exception:
        return {}


def folder_art(path):
    try:
        d = os.path.dirname(path)
        imgs = [f for f in os.listdir(d) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp"))]
        low = {f.lower(): f for f in imgs}
        for stem in ("cover", "folder", "front", "album", "albumart", "artwork", "pochette"):
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                if stem + ext in low:
                    return os.path.join(d, low[stem + ext])
        pick = next((f for f in imgs if any(k in f.lower() for k in ("cover", "front", "folder", "album", "pochette"))), None)
        if pick or len(imgs) == 1:
            return os.path.join(d, pick or imgs[0])
    except OSError:
        pass
    return None


def square_image(img, size):
    """Image recadrée au carré et réduite (QImage : utilisable hors du fil de l'interface)."""
    if img is None or img.isNull():
        return None
    s = min(img.width(), img.height())
    img = img.copy((img.width() - s) // 2, (img.height() - s) // 2, s, s)
    return img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def track_meta(path, size=96):
    """(infos, pochette QImage ou None) : étiquettes, puis image du dossier, puis ffmpeg en dernier recours."""
    tags = read_tags(path)
    img = None
    art = tags.pop("art", None)
    if art:
        q = QImage()
        if q.loadFromData(art):
            img = square_image(q, size)
    if img is None:
        fa = folder_art(path)
        if fa:
            img = square_image(QImage(fa), size)
    if img is None and shutil.which("ffmpeg"):
        png = cover_png(path, size)
        if png:
            q = QImage()
            if q.loadFromData(png):
                img = square_image(q, size)
    return tags, img


# ------------------------------------------------------------------ colonne des dossiers
TRACK_MIME = "application/x-studio-tracks"


class FolderBar(QWidget):
    """Barre latérale des dossiers : clic = filtrer, glisser des titres dessus = les ranger, glisser des fichiers = les ajouter."""
    RH = 32

    def __init__(self, app):
        super().__init__()
        self.app, self.items, self.hov, self.drop = app, [], None, None
        self.setFixedWidth(120)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_items(self, items, cur):
        """items : [(libellé, clé, nombre)] ; clé None = tous, "" = sans dossier."""
        self.items, self.cur = items, cur
        self.setMinimumHeight(min(96, 30 + (len(items) + 1) * self.RH))
        self.update()

    def row_at(self, y):
        k = int((y - 26) // self.RH)
        return k if 0 <= k <= len(self.items) else None

    def mouseMoveEvent(self, e):
        k = self.row_at(e.position().y())
        if k != self.hov:
            self.hov = k
            self.update()

    def leaveEvent(self, e):
        self.hov = None
        self.update()

    def mouseReleaseEvent(self, e):
        k = self.row_at(e.position().y())
        if k is None:
            return
        if k == len(self.items):
            return self.app.pl_new_folder()
        key = self.items[k][1]
        if e.button() == Qt.MouseButton.RightButton and key:
            return self.app.pl_folder_menu(key, e.globalPosition().toPoint())
        self.app.pl_set_view(key)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(TRACK_MIME) or e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        k = self.row_at(e.position().y())
        ok = k is not None and k < len(self.items) and (self.items[k][1] is not None or e.mimeData().hasUrls())
        if k != self.drop:
            self.drop = k if ok else None
            self.update()
        e.acceptProposedAction() if ok else e.ignore()

    def dragLeaveEvent(self, e):
        self.drop = None
        self.update()

    def dropEvent(self, e):
        k, self.drop = self.row_at(e.position().y()), None
        self.update()
        if k is None or k >= len(self.items):
            return
        key = self.items[k][1]
        md = e.mimeData()
        if md.hasFormat(TRACK_MIME):
            idx = [int(x) for x in bytes(md.data(TRACK_MIME)).decode().split(",") if x.isdigit()]
            if key is not None:
                self.app.pl_move(idx, key)
                self.app.log(f"{len(idx)} titre(s) rangé(s) dans « {key or 'Sans dossier'} ».")
        elif md.hasUrls():
            prev = self.app.pl_view
            self.app.pl_view = key or None
            self.app.pl_drop([u.toLocalFile() for u in md.urls() if u.isLocalFile()])
            if prev != self.app.pl_view:
                self.app.pl_refresh()
        e.acceptProposedAction()

    def paintEvent(self, e):
        p = new_painter(self)
        W = self.width()
        f = QFont(self.font())
        f.setPointSizeF(7.6)
        f.setBold(True)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        p.setFont(f)
        p.setPen(QColor(MUT))
        p.drawText(QRectF(10, 4, W, 18), Qt.AlignmentFlag.AlignVCenter, "BIBLIOTHÈQUE")
        fn = QFont(self.font())
        fn.setPointSizeF(9.6)
        for k, (lb, key, n) in enumerate(self.items + [("Nouveau", "+", 0)]):
            y = 26 + k * self.RH
            r = QRectF(2, y + 2, W - 6, self.RH - 4)
            on = key == self.cur and key != "+"
            p.setPen(Qt.PenStyle.NoPen)
            if self.drop == k:
                p.setBrush(qc(ACC, 70))
                p.drawRoundedRect(r, 10, 10)
                p.setPen(QPen(QColor(ACC), 1.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, 10, 10)
            elif on:
                p.setBrush(mixc(PANEL, TXT, .07))
                p.drawRoundedRect(r, 10, 10)
            elif k == self.hov:
                p.setBrush(mixc(PANEL, TXT, .05))
                p.drawRoundedRect(r, 10, 10)
            col = QColor(ACCT if on else (MUT if key == "+" else TXT))
            ic = r.left() + 14
            cy = r.center().y()
            p.setPen(ppen(ACCT if on else MUT, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            if key is None:                          # note de musique
                p.drawEllipse(QPointF(ic - 2, cy + 3), 2.6, 2.2)
                p.drawLine(QPointF(ic + .6, cy + 3), QPointF(ic + .6, cy - 5))
                p.drawLine(QPointF(ic + .6, cy - 5), QPointF(ic + 5, cy - 3))
            elif key == "+":
                p.drawLine(QPointF(ic - 4, cy), QPointF(ic + 4, cy))
                p.drawLine(QPointF(ic, cy - 4), QPointF(ic, cy + 4))
            else:                                    # dossier
                path = QPainterPath(QPointF(ic - 6, cy + 5))
                path.lineTo(ic - 6, cy - 4)
                path.lineTo(ic - 2, cy - 4)
                path.lineTo(ic, cy - 2)
                path.lineTo(ic + 6, cy - 2)
                path.lineTo(ic + 6, cy + 5)
                path.closeSubpath()
                p.drawPath(path)
            fb = QFont(fn)
            fb.setBold(on)
            p.setFont(fb)
            p.setPen(col)
            fm = QFontMetrics(fb)
            p.drawText(QRectF(ic + 12, y, W - ic - 44, self.RH), Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(lb, Qt.TextElideMode.ElideRight, int(W - ic - 46)))
            if key != "+":
                p.setFont(fn)
                p.setPen(QColor(ACCT if on else MUT))
                p.drawText(QRectF(W - 40, y, 32, self.RH), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, str(n))


# ------------------------------------------------------------------ liste des titres
class TrackList(QWidget):
    """Liste façon Apple Musique : case de sélection (tout sélectionner dans l'en-tête), pochette, titre / artiste · album,
    rotation, lectures, durée. Glisser des titres vers un dossier pour les ranger ; déposer des fichiers pour les ajouter."""
    RH, HEAD = 46, 26          # hauteur de ligne visée ; la vraie (self.rh) s'ajuste pour que seules des lignes entières s'affichent

    def __init__(self, on_toggle, on_play, on_menu=None, on_delete=None):
        super().__init__()
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.rows, self.now, self.prog, self.off = [], -1, 0.0, 0.0
        self.rh = float(self.RH)
        self.sel, self.hov, self.anchor = set(), None, None
        self.cb_t, self.cb_p, self.cb_m, self.cb_d, self.cb_s, self.cb_drop = on_toggle, on_play, on_menu, on_delete, None, None
        self.drag, self.press, self.dropping = None, None, False
        self.clock = QElapsedTimer()
        self.clock.start()
        Ticker.add(self, lambda t, dt: self.tick(), 30)   # petite animation du titre en cours : 30 i/s suffisent

    # --- état
    def tick(self):
        if self.now >= 0 and ANIM:
            k = next((i for i, r in enumerate(self.rows) if r["i"] == self.now), -1)
            if k >= 0:
                y = self.HEAD + k * self.rh - self.off
                self.update(QRect(0, int(y), self.width(), self.rh))

    def body_h(self):
        return self.height() - self.HEAD

    def nvis(self):
        return max(1, round(self.body_h() / self.RH))

    def resizeEvent(self, e):
        top = int(round(self.off / self.rh)) if self.rh else 0
        self.rh = max(30.0, self.body_h() / self.nvis())
        self.off = top * self.rh
        self.clamp()
        super().resizeEvent(e)

    def maxoff(self):
        return max(0, len(self.rows) - self.nvis()) * self.rh

    def clamp(self):
        """Toujours aligné sur une ligne entière : jamais de pochette coupée en haut ou en bas."""
        self.off = max(0.0, min(self.maxoff(), round(self.off / self.rh) * self.rh))

    def set(self, rows, now=-1):
        self.rows = [r for r in rows if r["i"] == now] + [r for r in rows if r["i"] != now]
        self.now = now
        self.sel &= {r["i"] for r in rows}
        self._sc()
        self.clamp()
        self.update()

    def set_prog(self, p):
        if abs(p - self.prog) > .003:
            self.prog = p

    def selection(self):
        return sorted(self.sel)

    def _sc(self):
        if self.cb_s:
            self.cb_s(len(self.sel))

    def select_all(self, on=True):
        self.sel = {r["i"] for r in self.rows} if on else set()
        self.anchor = None
        self._sc()
        self.update()

    def all_selected(self):
        return bool(self.rows) and len(self.sel) >= len(self.rows)

    def cur_k(self):
        ks = [k for k, r in enumerate(self.rows) if r["i"] in self.sel]
        return ks[-1] if ks else -1

    def show_k(self, k):
        top = int(round(self.off / self.rh))
        if k < top:
            top = k
        elif k >= top + self.nvis():
            top = k - self.nvis() + 1
        self.off = top * self.rh
        self.clamp()

    def step(self, d, extend=False):
        if not self.rows:
            return
        k = self.cur_k()
        k = 0 if k < 0 else max(0, min(len(self.rows) - 1, k + d))
        i = self.rows[k]["i"]
        if extend and self.anchor is not None:
            a = next((q for q, r in enumerate(self.rows) if r["i"] == self.anchor), k)
            self.sel = {r["i"] for r in self.rows[min(a, k):max(a, k) + 1]}
        else:
            self.sel, self.anchor = {i}, i
        self.show_k(k)
        self._sc()
        self.update()

    def keyPressEvent(self, e):
        k, sh = e.key(), bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        K = Qt.Key
        if k == K.Key_Up:
            self.step(-1, sh)
        elif k == K.Key_Down:
            self.step(1, sh)
        elif k == K.Key_PageUp:
            self.step(-6)
        elif k == K.Key_PageDown:
            self.step(6)
        elif k == K.Key_Home:
            self.step(-9999)
        elif k == K.Key_End:
            self.step(9999)
        elif k in (K.Key_Return, K.Key_Enter):
            kk = self.cur_k()
            if kk >= 0:
                self.cb_p(self.rows[kk]["i"])
        elif k == K.Key_Space:
            if self.sel:
                self.cb_t(min(self.sel))
        elif k in (K.Key_Delete, K.Key_Backspace):
            if self.cb_d and self.sel:
                self.cb_d()
        elif k == K.Key_A and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.select_all(not self.all_selected())
        else:
            return super().keyPressEvent(e)

    # --- souris
    def wheelEvent(self, e):
        self._wacc = getattr(self, "_wacc", 0) + e.angleDelta().y()
        n = int(self._wacc / 120)                    # une ligne entière par cran de molette
        if n:
            self._wacc -= n * 120
            self.off -= n * self.rh
            self.clamp()
            self.update()

    def row_at(self, y):
        if y < self.HEAD:
            return None
        k = int((y - self.HEAD + self.off) // self.rh)
        return k if 0 <= k < len(self.rows) else None

    def cols(self):
        W = self.width() - (12 if len(self.rows) > self.nvis() else 0)
        plays = any(r.get("n") for r in self.rows)    # colonne « Lectures » seulement si quelque chose a été joué
        return {"chk": 24, "art": 6, "txt": 50, "dur": W - 8, "plays": W - 58 if plays else W - 8, "show_plays": plays, "rot": -999, "W": W}

    def mouseMoveEvent(self, e):
        y = e.position().y()
        if self.drag is not None:
            H, tot = self.body_h(), len(self.rows) * self.rh
            th = max(24, H * H / max(tot, 1))
            self.off = max(0, min(self.maxoff(), self.drag[1] + (y - self.drag[0]) * (tot - H) / max(1, H - th)))
            self.clamp()
            return self.update()
        if self.press and e.buttons() & Qt.MouseButton.LeftButton and (e.position() - self.press).manhattanLength() > 8 and self.sel:
            self.press = None
            from PySide6.QtCore import QMimeData
            from PySide6.QtGui import QDrag
            md = QMimeData()
            md.setData(TRACK_MIME, ",".join(str(i) for i in sorted(self.sel)).encode())
            dr = QDrag(self)
            dr.setMimeData(md)
            pm = QPixmap(150, 30)
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            q.setBrush(QColor(ACC))
            q.setPen(Qt.PenStyle.NoPen)
            q.drawRoundedRect(QRectF(0, 0, 150, 30), 15, 15)
            q.setPen(QColor(ONACC))
            n = len(self.sel)
            q.drawText(QRectF(0, 0, 150, 30), Qt.AlignmentFlag.AlignCenter, f"{n} titre{'s' if n > 1 else ''}")
            q.end()
            dr.setPixmap(pm)
            dr.setHotSpot(QPoint(20, 15))
            dr.exec(Qt.DropAction.MoveAction)
            return
        k = self.row_at(y)
        if k != self.hov:
            self.hov = k
            self.update()

    def leaveEvent(self, e):
        if self.hov is not None:
            self.hov = None
            self.update()

    def mouseReleaseEvent(self, e):
        self.drag = None
        self.press = None

    def mousePressEvent(self, e):
        self.setFocus()
        x, y = e.position().x(), e.position().y()
        C = self.cols()
        if y < self.HEAD:                            # en-tête : case « tout sélectionner »
            if x < 44:
                self.select_all(not self.all_selected())
            return
        if e.button() == Qt.MouseButton.RightButton:
            k = self.row_at(y)
            if k is not None and self.cb_m:
                if self.rows[k]["i"] not in self.sel:
                    self.sel = {self.rows[k]["i"]}
                    self._sc()
                    self.update()
                self.cb_m(self.rows[k]["i"], e.globalPosition().toPoint())
            return
        H, tot = self.body_h(), len(self.rows) * self.rh
        if x > self.width() - 14 and tot > H:
            th = max(24, H * H / tot)
            ty = self.HEAD + self.off / (tot - H) * (H - th)
            if not (ty <= y <= ty + th):
                self.off = max(0, min(self.maxoff(), (y - self.HEAD - th / 2) / max(1, H - th) * (tot - H)))
                self.clamp()
                self.update()
            self.drag = (y, self.off)
            return
        k = self.row_at(y)
        if k is None:
            self.sel.clear()
            self._sc()
            return self.update()
        r = self.rows[k]
        if x < 44 and (r["i"] in self.sel or k == self.hov) and self.sel:   # case sur la pochette : ajoute / retire sans toucher au reste
            self.sel ^= {r["i"]}
            self.anchor = r["i"]
            self._sc()
            return self.update()
        mods = e.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.sel ^= {r["i"]}
            self.anchor = r["i"]
        elif mods & Qt.KeyboardModifier.ShiftModifier and self.anchor is not None:
            a = next((q for q, xx in enumerate(self.rows) if xx["i"] == self.anchor), k)
            self.sel = {xx["i"] for xx in self.rows[min(a, k):max(a, k) + 1]}
        elif r["i"] not in self.sel or len(self.sel) <= 1:
            self.sel, self.anchor = {r["i"]}, r["i"]
        self.press = e.position()
        self._sc()
        self.update()

    def mouseDoubleClickEvent(self, e):
        k = self.row_at(e.position().y())
        if k is not None:
            self.cb_p(self.rows[k]["i"])

    # --- fichiers déposés
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self.dropping = True
            self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.dropping = False
        self.update()

    def dropEvent(self, e):
        self.dropping = False
        self.update()
        if self.cb_drop and e.mimeData().hasUrls():
            self.cb_drop([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
            e.acceptProposedAction()

    # --- dessin
    @staticmethod
    def fit(text, font, maxw):
        return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, int(max(10, maxw)))

    def paintEvent(self, e):
        p = new_painter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        W0, H = self.width(), self.height()
        if W0 < 160:
            return
        C = self.cols()
        W = C["W"]
        fh = QFont(self.font())
        fh.setPointSizeF(7.4)
        fh.setBold(True)
        fh.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        # en-tête
        p.setFont(fh)
        allsel = self.all_selected()
        paint_check(p, C["chk"], self.HEAD / 2, allsel, False, 16)   # au-dessus des pochettes
        if self.sel and not allsel:                  # sélection partielle : tiret
            p.setPen(ppen(MUT, 2))
            p.drawLine(QPointF(C["chk"] - 3.5, self.HEAD / 2), QPointF(C["chk"] + 3.5, self.HEAD / 2))
        p.setPen(QColor(MUT))
        p.drawText(QRectF(C["txt"] - 6, 0, 200, self.HEAD), Qt.AlignmentFlag.AlignVCenter, "TITRE")
        if C["show_plays"]:
            p.drawText(QRectF(C["plays"] - 60, 0, 66, self.HEAD), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "LECTURES")
        p.drawText(QRectF(C["dur"] - 44, 0, 44, self.HEAD), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "DURÉE")
        p.setPen(QPen(mixc(LINE, PANEL, .4), 1))
        p.drawLine(QPointF(4, self.HEAD - .5), QPointF(W0 - 4, self.HEAD - .5))
        if not self.rows:
            if not MINI:                         # minimaliste : juste la consigne, sans décor
                for dx, dy in ((-22, -6), (22, 2)):
                    draw_ermine(p, W0 / 2 + dx, (H + self.HEAD) / 2 + dy, mixc(PANEL, TXT, .22), 1.6)
            p.setPen(QColor(MUT))
            p.drawText(QRectF(0, (H + self.HEAD) / 2 + 26, W0, 24), Qt.AlignmentFlag.AlignCenter,
                       "Glisse des morceaux ici ou clique « ＋ Ajouter »" + ("" if MINI else "  ·  Sonerezh !"))
            if self.dropping:
                p.setPen(QPen(QColor(ACC), 1.6, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(QRectF(4, self.HEAD + 4, W0 - 8, H - self.HEAD - 8), 14, 14)
            return
        p.setClipRect(QRectF(0, self.HEAD, W0, H - self.HEAD))
        first = int(round(self.off / self.rh))
        last = min(len(self.rows), first + self.nvis())
        fb, fn = QFont(self.font()), QFont(self.font())
        fb.setPointSizeF(10.2)
        fb.setWeight(QFont.Weight.DemiBold)
        fn.setPointSizeF(8.8)
        t = self.clock.elapsed() / 1000.0
        cols = list(CART_COLORS.values())
        for k in range(first, last):
            r = self.rows[k]
            y = self.HEAD + k * self.rh - self.off
            now, off, sel = r["i"] == self.now, r["off"], r["i"] in self.sel
            rr = QRectF(2, y + 2, W - 4, self.rh - 4)
            p.setPen(Qt.PenStyle.NoPen)
            if now or sel:
                g = QLinearGradient(rr.left(), 0, rr.right(), 0)
                g.setColorAt(0, mixc(PANEL, ACC, (.22 if now else .13) if not LIGHT else (.15 if now else .09)))
                g.setColorAt(1, mixc(PANEL, "#ff5fa2" if PSYCHE else ACC2, .06 if now else .03))
                p.setBrush(QBrush(g))
                p.drawRoundedRect(rr, 12, 12)
            elif k == self.hov:
                p.setBrush(mixc(PANEL, TXT, .05))
                p.drawRoundedRect(rr, 12, 12)
            cy = y + self.rh / 2
            # pochette
            x0, y0 = C["art"], y + 6
            img = r.get("img")
            ar = QRectF(x0, cy - 18, 36, 36)
            p.save()
            if off:
                p.setOpacity(.38)
            if img is not None and not img.isNull():
                path = QPainterPath()
                path.addRoundedRect(ar, 7, 7)
                p.setClipPath(path, Qt.ClipOperation.IntersectClip)
                p.drawPixmap(ar, img, QRectF(img.rect()))
            else:
                col = QColor(cols[abs(hash(r["artist"] + r["title"])) % len(cols)])
                g = QLinearGradient(ar.topLeft(), ar.bottomRight())
                g.setColorAt(0, col.lighter(118))
                g.setColorAt(1, col.darker(118))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(g))
                p.drawRoundedRect(ar, 7, 7)
                p.setPen(ppen(qc("#ffffff", 200), 1.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                cx_, cy_ = ar.center().x(), ar.center().y()
                p.drawEllipse(QPointF(cx_ - 3, cy_ + 5), 3.4, 2.8)
                p.drawLine(QPointF(cx_ + .4, cy_ + 5), QPointF(cx_ + .4, cy_ - 7))
                p.drawLine(QPointF(cx_ + .4, cy_ - 7), QPointF(cx_ + 7, cy_ - 4))
            p.restore()
            if now:                                  # égaliseur animé sur la pochette
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 120))
                p.drawRoundedRect(ar, 7, 7)
                p.setBrush(QColor("#ffffff"))
                for b in range(4):
                    hh = 4 + (abs(math.sin(t * (5.3 + b * 1.7) + b)) * 12 if ANIM else 8)
                    p.drawRoundedRect(QRectF(ar.left() + 9 + b * 5.5, ar.bottom() - 9 - hh, 3.2, hh), 1.4, 1.4)
            if sel or (k == self.hov and self.sel):   # case cochée posée sur la pochette
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 110))
                p.drawRoundedRect(ar, 7, 7)
                paint_check(p, ar.center().x(), cy, sel, not sel, 16)
            # texte
            tx = C["txt"] - 6
            tmax = C["plays"] - 54 - tx
            sub = r["artist"] or "Artiste inconnu"
            if r.get("album"):
                sub += "  ·  " + r["album"]
            if r.get("folder"):
                sub += "  ·  " + r["folder"]
            p.setFont(fb)
            p.setPen(QColor(ACCT if now else (MUT if off else TXT)))
            p.drawText(QPointF(tx, cy - 2), self.fit(r["title"], fb, tmax))
            p.setFont(fn)
            p.setPen(QColor(mixc(MUT, PANEL, .3) if off else MUT))
            p.drawText(QPointF(tx, cy + 13), self.fit(sub, fn, tmax))
            if now and self.prog:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(LINE))
                p.drawRoundedRect(QRectF(tx, y + self.rh - 7, tmax, 2.4), 1.2, 1.2)
                p.setBrush(QColor(ACC))
                p.drawRoundedRect(QRectF(tx, y + self.rh - 7, tmax * min(1, self.prog), 2.4), 1.2, 1.2)
            if off:                                  # hors rotation : petite étiquette discrète
                ft = QFont(fn)
                ft.setPointSizeF(7.4)
                p.setFont(ft)
                tw_ = QFontMetrics(ft).horizontalAdvance("hors rotation") + 12
                tr_ = QRectF(C["plays"] - 54 - tw_, cy - 8, tw_, 16)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(mixc(PANEL, TXT, .07))
                p.drawRoundedRect(tr_, 8, 8)
                p.setPen(QColor(MUT))
                p.drawText(tr_, Qt.AlignmentFlag.AlignCenter, "hors rotation")
            if False:
                rx = C["rot"]
                c = QColor(OKC if not off else MUT)
                if k == self.hov:
                    c = c.lighter(115)
                p.setPen(ppen(c, 1.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(QRectF(rx - 6, cy - 6, 12, 12), 40 * 16, 280 * 16)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                tri = QPainterPath(QPointF(rx + 5.5, cy - 7.5))
                tri.lineTo(QPointF(rx + 7.5, cy - 2))
                tri.lineTo(QPointF(rx + 2, cy - 3))
                tri.closeSubpath()
                p.drawPath(tri)
                if off:
                    p.setPen(ppen(BADC, 1.6))
                    p.drawLine(QPointF(rx - 7, cy + 7), QPointF(rx + 7, cy - 7))
            p.setFont(fn)
            n = r["n"]
            p.setPen(QColor(mixc(MUT, PANEL, .25)))
            if C["show_plays"]:
                p.drawText(QRectF(C["plays"] - 46, y, 46, self.rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(n) if n else "–")
            if r["dur"]:
                p.setPen(QColor(MUT))
                p.drawText(QRectF(C["dur"] - 64, y, 64, self.rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt_ms(r["dur"]))
        p.setClipping(False)
        tot = len(self.rows) * self.rh
        Hb = self.body_h()
        if len(self.rows) > self.nvis():
            th = max(24, Hb * Hb / tot)
            ty = self.HEAD + self.off / (tot - Hb) * (Hb - th)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(TXT, 50 if self.drag else 30))
            p.drawRoundedRect(QRectF(W0 - 7, ty + 2, 4, th - 4), 2, 2)
        if self.dropping:
            p.setPen(QPen(QColor(ACC), 1.6, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(3, self.HEAD + 3, W0 - 6, H - self.HEAD - 6), 14, 14)


# ------------------------------------------------------------------ fiche « Infos » d'un titre
class TrackInfoDialog(QDialog):
    def __init__(self, app, path, info, img, n):
        super().__init__(app)
        self.setWindowTitle("Infos")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(14)
        h = QHBoxLayout()
        h.setSpacing(18)
        art = QLabel()
        art.setFixedSize(150, 150)
        if img is not None and not img.isNull():
            pm = QPixmap.fromImage(img).scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            r = QPixmap(150, 150)
            r.fill(Qt.GlobalColor.transparent)
            q = QPainter(r)
            q.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, 150, 150), 14, 14)
            q.setClipPath(path)
            q.drawPixmap(0, 0, pm)
            q.end()
            art.setPixmap(r)
        else:
            art.setPixmap(default_cover_pm(150))
        h.addWidget(art)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = lab(info.get("title") or os.path.splitext(os.path.basename(path))[0], "", True)
        t.setStyleSheet("font-size:19px;font-weight:800;")
        col.addWidget(t)
        a = lab(info.get("artist") or "Artiste inconnu", "", True)
        a.setStyleSheet(f"font-size:14px;color:{ACCT};font-weight:600;")
        col.addWidget(a)
        if info.get("album"):
            al = lab(info["album"], "mut", True)
            col.addWidget(al)
        col.addStretch(1)
        h.addLayout(col, 1)
        v.addLayout(h)
        f = QFormLayout()
        f.setHorizontalSpacing(18)
        for k, lbl in (("genre", "Genre"), ("year", "Année"), ("dur", "Durée"), ("n", "Lectures"), ("folder", "Dossier")):
            val = {"dur": fmt_ms(info.get("dur", 0)) if info.get("dur") else "", "n": str(n)}.get(k, info.get(k, ""))
            if val:
                f.addRow(lab(lbl, "mut"), lab(str(val), ""))
        pl = lab(path, "mut", True)
        pl.setStyleSheet(f"color:{MUT};font-size:11px;")
        pl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addRow(lab("Fichier", "mut"), pl)
        v.addLayout(f)
        bb = QHBoxLayout()
        bb.addStretch(1)
        bb.addWidget(btn("OK", "primary", self.accept))
        v.addLayout(bb)


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
