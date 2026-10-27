# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - pages Réseau et SOS, fenêtre des alertes, panneau de Gaël."""
from bev_assistant import *  # noqa: F401,F403

# ------------------------------------------------------------------ Réseau + SOS + Radiobot
class Radar(QWidget):
    """Qualité du lien (onglet Réseau) : anneau de score, latence en grand, courbe des dernières mesures.
    Aucune animation permanente : un fondu de 400 ms quand une mesure arrive, un fin arc qui tourne seulement pendant un test."""

    def __init__(self, size=112):
        super().__init__()
        self.setFixedSize(300, 112)
        self.score, self.shown, self.lat, self.jit, self.loss = None, 0.0, None, None, None
        self.label, self.col, self.hist, self.scan, self.txt, self.name = "—", MUT, [], False, "", ""
        self.an = QVariantAnimation(self)
        self.an.setDuration(420)
        self.an.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.an.valueChanged.connect(lambda v: (setattr(self, "shown", float(v)), self.update()))
        self.clock = QElapsedTimer()
        self.clock.start()
        self.tm = QTimer(self)
        self.tm.timeout.connect(lambda: self.update() if self.isVisible() and not calm() else None)

    def set_scan(self, on, txt=""):
        on = bool(on)
        if on != self.scan:
            self.scan, self.txt = on, txt
            if on and ANIM:
                self.tm.start(Gov.ivl(16))
                Gov.reg(self.tm, 16)
            else:
                self.tm.stop()
            self.update()

    @staticmethod
    def score_of(st):
        if not st or st.get("lat") is None:
            return 0.0
        return _cl(100 - max(0, st["lat"] - 20) / 4.0 - st.get("jit", 0) * .6 - st.get("loss", 0) * 2.5, 0, 100)

    def set_link(self, name, st, hist):
        q, col, _ = quality(st) if st else ("—", MUT, False)
        sc = self.score_of(st) if st else None
        self.name, self.label, self.col = name or "", q, QUAL_COL.get(q, col)
        self.lat = st.get("lat") if st else None
        self.jit = st.get("jit") if st else None
        self.loss = st.get("loss") if st else None
        self.hist = list(hist or [])[-40:]
        if sc != self.score:
            self.score = sc
            self.an.stop()
            self.an.setStartValue(self.shown)
            self.an.setEndValue(float(sc or 0))
            self.an.start() if ANIM else setattr(self, "shown", float(sc or 0))
        self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        R = QRectF(8, 8, 96, 96)
        col = QColor(self.col)
        p.setPen(QPen(mixc(PANEL, TXT, .08), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(R, 225 * 16, -270 * 16)
        if self.shown > .5:
            g = QLinearGradient(R.bottomLeft(), R.topRight())
            g.setColorAt(0, mixc(col, PANEL, .35))
            g.setColorAt(1, col)
            p.setPen(QPen(QBrush(g), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(R, 225 * 16, int(-270 * 16 * self.shown / 100))
        if self.scan:
            a = (self.clock.elapsed() / 1000.0 * 300) % 360
            c = QColor(ACC2)
            c.setAlphaF(.8)
            p.setPen(QPen(c, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(R.adjusted(-6, -6, 6, 6), int(-a * 16), 50 * 16)
        f = QFont(self.font())
        f.setPixelSize(22)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(TXT))
        p.drawText(QRectF(R.left(), R.top() + 26, R.width(), 30), Qt.AlignmentFlag.AlignCenter, f"{self.lat:.0f}" if self.lat is not None else "—")
        f2 = QFont(self.font())
        f2.setPixelSize(10)
        p.setFont(f2)
        p.setPen(QColor(MUT))
        p.drawText(QRectF(R.left(), R.top() + 54, R.width(), 14), Qt.AlignmentFlag.AlignCenter, "ms")
        # colonne de droite
        x0 = 122
        f3 = QFont(self.font())
        f3.setPixelSize(15)
        f3.setBold(True)
        p.setFont(f3)
        p.setPen(col)
        p.drawText(QRectF(x0, 8, 180, 20), Qt.AlignmentFlag.AlignVCenter, self.label if not self.scan else "Mesure en cours…")
        p.setFont(f2)
        p.setPen(QColor(MUT))
        det = []
        if self.jit is not None:
            det.append(f"gigue {self.jit:.0f} ms")
        if self.loss is not None:
            det.append(f"perte {self.loss:.0f} %")
        p.drawText(QRectF(x0, 28, 180, 14), Qt.AlignmentFlag.AlignVCenter, (self.name + "  ·  " if self.name else "") + " · ".join(det))
        # courbe de latence (40 dernières mesures)
        G = QRectF(x0, 50, 170, 50)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mixc(PANEL, TXT, .035))
        p.drawRoundedRect(G, 10, 10)
        vals = [v for v in self.hist if v is not None]
        if len(vals) >= 2:
            top = max(60.0, max(vals) * 1.15)
            n = len(self.hist)
            path, area = QPainterPath(), QPainterPath()
            first = True
            for k, v in enumerate(self.hist):
                if v is None:
                    continue
                x = G.left() + 8 + (G.width() - 16) * (k / max(1, n - 1))
                y = G.bottom() - 6 - (G.height() - 12) * min(1.0, v / top)
                if first:
                    path.moveTo(x, y)
                    area.moveTo(x, G.bottom() - 4)
                    area.lineTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)
                    area.lineTo(x, y)
            area.lineTo(path.currentPosition().x(), G.bottom() - 4)
            area.closeSubpath()
            ag = QLinearGradient(0, G.top(), 0, G.bottom())
            ag.setColorAt(0, qc(col.name(), 70))
            ag.setColorAt(1, qc(col.name(), 0))
            p.setBrush(QBrush(ag))
            p.drawPath(area)
            p.setPen(QPen(col, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            lp = path.currentPosition()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawEllipse(lp, 3, 3)
        else:
            p.setPen(QColor(MUT))
            p.drawText(G, Qt.AlignmentFlag.AlignCenter, "historique de latence")


QUAL_COL = {"Excellente": OKC, "Bonne": "#27ae60", "Moyenne": "#f26a35", "Mauvaise": "#e5485a", "Coupée": "#e5485a"}


class PagesMixin4:
    # ------------------------------------------------------------ Réseau
    def _page_net(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(10)
        n = self.data.setdefault("net", {})
        n.setdefault("links", [])
        n.setdefault("auto", False)
        n.setdefault("interval", 10)
        n.setdefault("back_s", 90)
        n.setdefault("targets", "1.1.1.1:443, 8.8.8.8:443")
        self.net_links, self.net_stats, self.net_speed, self.net_rate, self.net_io = [], {}, {}, {}, {}
        self.net_busy, self.net_last, self.net_active, self.net_last_switch = False, 0.0, None, 0.0
        self.net_bad, self.net_good_since, self.net_info, self.net_scan_until, self.net_scan_who = {}, {}, {}, 0.0, ""
        bar = WrapRow()
        for txt, cmd in (("↻ Détecter", self.net_refresh), ("Tester le débit", self.net_speedtest), ("Monter", lambda: self.net_move(-1)),
                         ("Descendre", lambda: self.net_move(1)), ("Nommer", self.net_rename), ("↪ Utiliser celle-ci maintenant", self.net_use_now)):
            b = btn(txt, "", cmd)
            if txt in ("Monter", "Descendre", "Nommer", "↪ Utiliser celle-ci maintenant", "Tester le débit"):
                self.gray_net = getattr(self, "gray_net", []) + [b]
            bar.addWidget(b)
        bar.addStretch(1)
        self.sw_net_auto = Switch("Bascule automatique")
        self.sw_net_auto.setChecked(bool(n["auto"]))
        bar.addWidget(self.sw_net_auto)
        v.addLayout(bar)
        self.l_netact = lab("", "")
        self.l_netact.setMinimumHeight(40)
        v.addWidget(self.l_netact)
        c = Card()
        cols = ("#", "SUIVI", "CONNEXION", "TYPE", "ADRESSE", "ÉTAT", "LATENCE", "GIGUE", "PERTE", "DÉBIT MESURÉ", "TRAFIC", "QUALITÉ")
        self.tb_net = QTableWidget(0, len(cols))
        self.tb_net.setHorizontalHeaderLabels(cols)
        style_table(self.tb_net, check_col=1)
        hh = self.tb_net.horizontalHeader()
        # largeurs fixes : les chiffres qui changent (latence, débit, trafic) ne font plus bouger les colonnes
        for col, wd in enumerate((36, 58, 0, 74, 124, 96, 74, 66, 60, 150, 146, 96)):
            if wd:
                hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                self.tb_net.setColumnWidth(col, wd)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tb_net.verticalHeader().hide()
        self.tb_net.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tb_net.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tb_net.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tb_net.setShowGrid(False)
        self.tb_net.setMinimumHeight(84)
        self.tb_net.verticalHeader().setDefaultSectionSize(46)
        self.tb_net.cellClicked.connect(self.net_click)
        self.tb_net.itemSelectionChanged.connect(lambda: self.net_details())
        c.lay.addWidget(self.tb_net)
        v.addWidget(c)
        h = QHBoxLayout()
        h.addWidget(lab("Mesure toutes les", "mut"))
        self.ed_net_iv = QLineEdit(str(n["interval"]))
        self.ed_net_iv.setFixedWidth(60)
        h.addWidget(self.ed_net_iv)
        h.addWidget(lab("s     Retour au lien principal après", "mut"))
        self.ed_net_back = QLineEdit(str(n["back_s"]))
        self.ed_net_back.setFixedWidth(60)
        h.addWidget(self.ed_net_back)
        h.addWidget(lab("s de stabilité", "mut"))
        h.addStretch(1)
        v.addLayout(h)
        self.l_netinfo = lab("Détection des connexions...", "mut")
        v.addWidget(self.l_netinfo)
        dc = Card("Détails de la connexion", "Sélectionner un lien pour l'afficher")
        hh2 = QHBoxLayout()
        gd = QGridLayout()
        self.net_det = {}
        fields = (("name", "Nom"), ("kind", "Type"), ("ip", "Adresse IP"), ("mask", "Masque"), ("mac", "Adresse MAC"), ("speed", "Débit du lien"),
                  ("ssid", "Réseau Wi-Fi"), ("signal", "Signal"), ("pub", "IP publique"), ("org", "Opérateur"), ("place", "Lieu"), ("mtu", "MTU · IPv6"))
        for i, (k, l) in enumerate(fields):
            r, cc = i // 4, i % 4
            cell = QHBoxLayout()
            lb = lab(l, "mut")
            lb.setFixedWidth(88)
            cell.addWidget(lb)
            self.net_det[k] = lab("-", "")
            cell.addWidget(self.net_det[k], 1)
            gd.addLayout(cell, r, cc)
            gd.setColumnStretch(cc, 1)
        self.net_gd = gd
        left = QVBoxLayout()
        left.addLayout(gd)
        left.addWidget(btn("Actualiser les détails", "", lambda: self.net_details(True)), 0, Qt.AlignmentFlag.AlignLeft)
        hh2.addLayout(left, 1)
        self.radar = Radar()
        hh2.addWidget(self.radar)
        dc.lay.addLayout(hh2)
        v.addWidget(dc)
        lf = Card("Incidents réseau")
        self.net_logbox = QPlainTextEdit()
        self.net_logbox.setReadOnly(True)
        self.net_logbox.setMinimumHeight(44)        # la zone de texte occupe toute la carte (plus de titre flottant au milieu)
        lf.lay.addWidget(self.net_logbox)
        v.addWidget(lf, 1)
        QTimer.singleShot(800, self.net_refresh)
        self.net_timer = QTimer(self)
        self.net_timer.timeout.connect(self.net_tick)
        self.net_timer.start(1000)
        return w

    def net_cfg(self, name):
        for c in self.data["net"]["links"]:
            if c["name"] == name:
                return c
        c = {"name": name, "label": "", "enabled": True}
        self.data["net"]["links"].append(c)
        return c

    def net_kind(self, name):
        l = next((x for x in self.net_links if x["name"] == name), None)
        return KIND_TXT[l["kind"]] if l else "?"

    def net_label(self, name):
        return self.net_cfg(name).get("label") or name

    def sync_net(self):
        n = self.data.get("net")
        if n is None or not hasattr(self, "sw_net_auto"):
            return
        n["auto"] = self.sw_net_auto.isChecked()
        try:
            n["interval"] = max(5, int(float(self.ed_net_iv.text())))
        except ValueError:
            n["interval"] = 10
        try:
            n["back_s"] = max(10, int(float(self.ed_net_back.text())))
        except ValueError:
            n["back_s"] = 90

    def net_log(self, msg):
        now = time.time()
        seen = getattr(self, "_net_seen", {})
        self._net_seen = seen
        if now - seen.get(msg, 0) < 300:          # même constat répété à chaque mesure : noté une fois toutes les 5 min
            return
        seen[msg] = now
        self.net_logbox.appendPlainText(f"{time.strftime('%d/%m %H:%M:%S')}  {msg}")
        self.log("Réseau : " + msg)

    def net_refresh(self):
        def work():
            if not have_module("psutil"):
                return self.bridge.call.emit(self.net_nopsutil)
            try:
                links = list_links()
                self.bridge.call.emit(lambda: self.net_apply_links(links))
            except Exception as e:
                msg = str(e)
                self.bridge.call.emit(lambda: self.l_netinfo.setText(f"Détection impossible : {msg}"))
        threading.Thread(target=work, daemon=True).start()

    def net_nopsutil(self):
        self.l_netinfo.setText("Le module « psutil » est nécessaire pour détecter les connexions : clique ici pour l'installer (puis relance l'appli).")
        set_ss(self.l_netinfo, "color:#e5485a;")
        self.l_netinfo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.l_netinfo.mouseReleaseEvent = lambda _e: self.install("psutil")

    def net_apply_links(self, links):
        by = {l["name"]: l for l in links}
        order = [c["name"] for c in self.data["net"]["links"] if c["name"] in by]
        order += [l["name"] for l in links if l["name"] not in order]
        for nm in order:
            self.net_cfg(nm)
        self.net_links = [by[nm] for nm in order]
        self.data["net"]["links"].sort(key=lambda c: order.index(c["name"]) if c["name"] in order else 999)
        self.l_netinfo.setText(f"{len(links)} connexion(s) détectée(s)")
        set_ss(self.l_netinfo, f"color:{MUT};")
        self.net_render(rebuild=True)
        self.net_last = 0.0
        if self.net_links and not self.net_sel():
            first = next((i for i, l in enumerate(self.net_links) if l["name"] == self.net_active), 0)
            self.tb_net.selectRow(first)

    def install(self, pkg, done=None):
        if getattr(sys, "frozen", False):
            return self.log(f"{pkg} : module non disponible dans cette version de l'application.")
        self.log(f"Installation de {pkg}...")

        def work():
            for extra in ([], ["--break-system-packages"]):
                r = subprocess.run([sys.executable, "-m", "pip", "install", pkg] + extra, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   creationflags=0x08000000 if SYS == "Windows" else 0)
                if r.returncode == 0:
                    importlib.invalidate_caches()
                    if done:
                        self.log(f"{pkg} installé et activé.")
                        return self.bridge.call.emit(done)
                    return self.log(f"{pkg} installé. Relance l'application pour l'activer.")
            self.log(f"Échec de l'installation de {pkg} : " + (r.stdout + r.stderr)[-400:])
        threading.Thread(target=work, daemon=True).start()

    def net_render(self, rebuild=False):
        tb = self.tb_net
        sel = self.net_sel()
        if tb.rowCount() != len(self.net_links):
            tb.setRowCount(len(self.net_links))
        for i, l in enumerate(self.net_links):
            nm, st = l["name"], self.net_stats.get(l["name"])
            c = self.net_cfg(nm)
            q = quality(st)[0] if (st and c["enabled"] and l["up"]) else ""
            if not l["up"]:
                q = "Coupée"
            sp, rt = self.net_speed.get(nm), self.net_rate.get(nm)
            vals = (i + 1, "", self.net_label(nm), KIND_TXT[l["kind"]], l["ip"],
                    "● ACTIF" if nm == self.net_active else ("en veille" if l["up"] else "○ coupée"),
                    f"{st['lat']:.0f} ms" if st and st.get("lat") is not None else ("-" if not st else "×"),
                    f"{st['jit']:.0f} ms" if st and st.get("lat") is not None else "-", f"{st['loss']:.0f} %" if st else "-",
                    (f"↓ {sp[0]:.0f} / ↑ {sp[1]:.0f} Mb/s" if sp and sp != "..." and sp[0] is not None and sp[1] is not None
                     else ("test..." if sp == "..." else "-")),
                    f"↓ {rt[0]:.0f} / ↑ {rt[1]:.0f} ko/s" if rt else "-", q or "-")
            for k, t in enumerate(vals):
                it = tb.item(i, k)
                if it is None:
                    it = QTableWidgetItem()
                    tb.setItem(i, k, it)
                    if k in (0, 1, 6, 7, 8, 11):
                        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if it.text() != str(t):
                    it.setText(str(t))
                it.setData(Qt.ItemDataRole.UserRole, nm)
                if k == 1:
                    it.setData(CHECK_ROLE, bool(c["enabled"]))
                act = nm == self.net_active
                it.setData(TINT_ROLE, OKC if act else None)
                if act:
                    it.setForeground(QColor(OKC) if k in (2, 5) else QColor(TXT))
                    f = it.font()
                    f.setBold(k in (2, 5))
                    it.setFont(f)
                else:
                    it.setForeground(QColor(MUT if not l["up"] else TXT))
                    f = it.font()
                    f.setBold(False)
                    it.setFont(f)
                if k == 11 and q:
                    it.setForeground(QColor(QUAL_COL.get(q, TXT)))
        a = next((l for l in self.net_links if l["name"] == self.net_active), None)
        if a:
            st = self.net_stats.get(a["name"]) or {}
            qq = quality(st)[0] if st else ""
            lat = f" · {st['lat']:.0f} ms" if st.get("lat") is not None else ""
            self.l_netact.setText(f"●  Internet passe par  {self.net_label(a['name'])}  ({KIND_TXT[a['kind']]}){lat}" + (f" · {qq}" if qq else ""))
            set_ss(self.l_netact, f"background:{mixc(PANEL, OKC, .18).name()};color:{OKC};font-weight:800;font-size:15px;border-radius:12px;padding:6px 16px;border-left:5px solid {OKC};")
        else:
            self.l_netact.setText("Aucune connexion active détectée")
            set_ss(self.l_netact, f"background:{FIELD};color:{MUT};font-weight:700;border-radius:12px;padding:6px 16px;")

    def net_sel(self):
        r = self.tb_net.currentRow() if hasattr(self, "tb_net") else -1
        if 0 <= r < len(self.net_links):
            return self.net_links[r]["name"]
        return None

    def net_click(self, r, col):
        if col == 1 and 0 <= r < len(self.net_links):
            c = self.net_cfg(self.net_links[r]["name"])
            c["enabled"] = not c["enabled"]
            self.net_render()

    def net_details(self, fetch=False):
        nm = self.net_sel()
        l = next((x for x in self.net_links if x["name"] == nm), None)
        if not l:
            return
        inf = self.net_info.setdefault(nm, {})
        if fetch or "pub" not in inf:
            inf.setdefault("pub", "…")
            self.net_scan(4, l["ip"])

            def work():
                d = {}
                if l["up"]:
                    d.update(public_info(l["ip"]))
                    if l["kind"] == "wifi":
                        d.update(wifi_info(nm))
                d.setdefault("pub", "indisponible")

                def done():
                    self.net_info.setdefault(nm, {}).update(d)
                    self.net_details_show(nm)
                self.bridge.call.emit(done)
            threading.Thread(target=work, daemon=True).start()
        self.net_details_show(nm)

    def net_details_show(self, nm):
        self.net_gauge()
        l = next((x for x in self.net_links if x["name"] == nm), None)
        if not l or nm != self.net_sel():
            return
        i = self.net_info.get(nm, {})
        place = ", ".join(x for x in (i.get("city", ""), i.get("country", "")) if x)
        vals = {"name": self.net_label(nm), "kind": KIND_TXT[l["kind"]] + (" · actif" if nm == self.net_active else ""),
                "ip": l["ip"], "mask": l.get("mask") or "-", "mac": l.get("mac") or "-", "speed": f"{l['speed']} Mb/s" if l.get("speed") else "-",
                "ssid": i.get("ssid") or ("-" if l["kind"] != "wifi" else "…"), "signal": i.get("signal") or "-", "pub": i.get("pub", "-"),
                "org": i.get("org") or "-", "place": place or "-", "mtu": f"{l.get('mtu', 0) or '-'} · {l.get('v6', 0)} adresse(s)"}
        for k, v in vals.items():
            self.net_det[k].setText(str(v))

    def net_move(self, d):
        nm = self.net_sel()
        names = [l["name"] for l in self.net_links]
        if not nm or nm not in names:
            return
        i, j = names.index(nm), names.index(nm) + d
        if 0 <= j < len(names):
            self.net_links[i], self.net_links[j] = self.net_links[j], self.net_links[i]
            order = [l["name"] for l in self.net_links]
            self.data["net"]["links"].sort(key=lambda c: order.index(c["name"]) if c["name"] in order else 999)
            self.net_render(rebuild=True)
            self.tb_net.selectRow(j)

    def net_rename(self):
        nm = self.net_sel()
        if nm:
            v = ask_text(self, "Nom de la connexion", f"Nom affiché pour « {nm} » (ex. Fibre RJ45, Clé 4G) :", self.net_cfg(nm).get("label", ""))
            if v is not None:
                self.net_cfg(nm)["label"] = v.strip()
                self.net_render()

    def net_use_now(self):
        nm = self.net_sel()
        if nm:
            self.net_switch(nm, "choix manuel")

    def net_speedtest(self):
        self.net_scan(6, "speed.cloudflare.com")
        for l in self.net_links:
            if l["up"] and self.net_cfg(l["name"])["enabled"]:
                self.net_speed[l["name"]] = "..."

                def work(l=l):
                    d, u = speed_test(l["ip"])
                    self.bridge.call.emit(lambda: self.net_speed_done(l["name"], (d, u)))
                threading.Thread(target=work, daemon=True).start()
        self.net_render()

    def net_speed_done(self, name, res):
        self.net_speed[name] = res if res[0] is not None or res[1] is not None else None
        if res[0] is None and res[1] is None:
            self.net_log(f"Test de débit impossible sur « {self.net_label(name)} » (pas d'accès à speed.cloudflare.com depuis ce lien).")
        self.net_render()

    def net_tick(self):
        try:
            now = time.time()
            if have_module("psutil") and self.net_links:
                import psutil
                io = psutil.net_io_counters(pernic=True)
                for l in self.net_links:
                    c = io.get(l["name"])
                    if c:
                        old = self.net_io.get(l["name"])
                        if old and now > old[2]:
                            dt = now - old[2]
                            self.net_rate[l["name"]] = ((c.bytes_recv - old[0]) / 1000 / dt, (c.bytes_sent - old[1]) / 1000 / dt)
                        self.net_io[l["name"]] = (c.bytes_recv, c.bytes_sent, now)
            self.sync_net()
            self.net_radar_update()
            if self.net_links and not self.net_busy and now - self.net_last >= self.data["net"]["interval"]:
                self.net_cycle()
            if self.net_links and self.page_key == "net":
                self.net_render()
        except Exception as e:
            self.log(f"(erreur réseau : {e})")

    def net_scan(self, secs, who=""):
        self.net_scan_until = max(self.net_scan_until, time.time() + secs)
        if who:
            self.net_scan_who = who
        self.net_radar_update()

    def net_radar_update(self):
        on = time.time() < self.net_scan_until or any(v == "..." for v in self.net_speed.values())
        self.radar.set_scan(on, "SCAN " + self.net_scan_who)

    def net_cycle(self):
        self.net_busy, self.net_last = True, time.time()
        targets = parse_targets(self.data["net"]["targets"])
        self.net_scan(2.5, f"{targets[0][0]}")
        todo = [l for l in self.net_links if l["up"] and self.net_cfg(l["name"])["enabled"]]
        res = {}

        def one(l):
            res[l["name"]] = probe_link(l["name"], l["ip"], targets)

        def work():
            ths = [threading.Thread(target=one, args=(l,), daemon=True) for l in todo]
            for th in ths:
                th.start()
            for th in ths:
                th.join(20)
            self.bridge.call.emit(lambda: self.net_after_cycle(res))
        threading.Thread(target=work, daemon=True).start()

    def set_net_label(self, text, color):
        changed = text != self.l_net.text()
        self.l_net.setText(text)
        set_ss(self.l_net, f"background:{FIELD};color:{color};font-weight:700;border-radius:12px;padding:4px 14px;")
        if changed:
            QTimer.singleShot(0, self.fit_band)

    def net_after_cycle(self, res):
        self.net_busy = False
        now = time.time()
        self.net_stats.update(res)
        self.net_hist = getattr(self, "net_hist", {})
        for nm, st in res.items():
            h = self.net_hist.setdefault(nm, [])
            h.append(st.get("lat") if st else None)
            del h[:-40]
        ip = default_route_ip()
        self.net_active = next((l["name"] for l in self.net_links if l["ip"] == ip), None)
        order = [l["name"] for l in self.net_links if l["up"] and self.net_cfg(l["name"])["enabled"]]
        usable = {nm: quality(self.net_stats.get(nm))[2] for nm in order}
        for nm in order:
            if usable[nm]:
                self.net_good_since.setdefault(nm, now)
                self.net_bad[nm] = 0
            else:
                self.net_good_since.pop(nm, None)
                self.net_bad[nm] = self.net_bad.get(nm, 0) + 1
        act = self.net_active
        if act and self.net_stats.get(act):
            q, col, _ = quality(self.net_stats[act])
            lat = self.net_stats[act].get("lat")
            kd, lb = self.net_kind(act), self.net_label(act)
            who = kd if (lb == kd or lb.lower() == act.lower() and kd.lower() in lb.lower()) else f"{kd} · {lb}"
            self.set_net_label(f"{who} · " + (f"{lat:.0f} ms · {q}" if lat is not None else q), col)
        else:
            self.set_net_label("Internet : lien actif inconnu", MUT)
        main = order[0] if order else None
        target, reason = None, ""
        n = self.data["net"]
        if not (act in order and self.net_bad.get(act, 0) >= 2):
            self._net_bad_since = None                    # qualité redevenue correcte : le compteur repart de zéro
        if act in order and self.net_bad.get(act, 0) >= 2:
            alt = next((x for x in order if x != act and usable[x]), None)
            qa = quality(self.net_stats.get(act))[0]
            if alt:
                target, reason = alt, f"« {self.net_label(act)} » {qa.lower()}"
            else:
                self.net_log(f"« {self.net_label(act)} » {qa.lower()} et aucune connexion de secours disponible.")
                self.net_alert(f"Internet : « {self.net_label(act)} » {qa.lower()}, pas de lien de secours.", "out-net-down")
        elif main and act and act != main and usable.get(main) and now - self.net_good_since.get(main, now) >= n["back_s"]:
            target, reason = main, "retour au lien principal (stable)"
        if target and now - self.net_last_switch > 60:
            if self.sw_net_auto.isChecked():
                self.net_switch(target, reason)
            else:
                self.net_log(f"Conseil : {reason} → utiliser « {self.net_label(target)} » (sélectionne-la puis « Utiliser celle-ci maintenant »).")
                self.net_alert(f"Internet : {reason}. Lien conseillé : {self.net_label(target)}.", "out-net-advice")
        self.net_render()
        self.net_gauge()

    NET_ALERT_AFTER = 300       # mauvaise qualité : message seulement si elle dure 5 min…
    NET_ALERT_EVERY = 3600      # … et au plus une fois par heure (pour chaque type de message)

    def net_alert(self, text, key, sustained=True):
        """Alertes sur la qualité d'Internet, allégées : le Wi-Fi qui faiblit quelques instants n'envoie plus rien (c'est noté
        dans le journal du réseau). Un message ne part que si la mauvaise qualité dure 5 minutes, et au plus une fois par
        heure ; une bascule de lien est signalée au plus une fois par heure."""
        now = time.time()
        if sustained:
            if getattr(self, "_net_bad_since", None) is None:
                self._net_bad_since = now
            if now - self._net_bad_since < self.NET_ALERT_AFTER:
                return
        last = getattr(self, "_net_alert_t", {})
        self._net_alert_t = last
        if key in last and now - last[key] < self.NET_ALERT_EVERY:
            return
        last[key] = now
        self.alerts.send(text + (" (depuis plus de 5 min)" if sustained else ""), key)

    def net_gauge(self):
        nm = None
        try:
            sel = self.net_sel()
            nm = sel["name"] if isinstance(sel, dict) else sel
        except Exception:
            nm = None
        nm = nm or self.net_active
        if nm:
            self.radar.set_link(self.net_label(nm), self.net_stats.get(nm), getattr(self, "net_hist", {}).get(nm))

    def net_switch(self, name, reason):
        self.net_last_switch = time.time()
        self.net_log(f"Bascule vers « {self.net_label(name)} » ({reason})...")

        def work():
            ok, msg = prefer_link(name)
            self.bridge.call.emit(lambda: self.net_switched(name, ok, msg, reason))
        threading.Thread(target=work, daemon=True).start()

    def net_switched(self, name, ok, msg, reason):
        if not ok:
            self.net_log(f"Bascule impossible : {msg}")
            self.net_alert(f"Internet : bascule vers {self.net_label(name)} impossible ({msg}).", "out-net-fail", sustained=False)
            return
        self.net_log(f"Internet passe par « {self.net_label(name)} ».")
        self.net_alert(f"Internet : bascule sur {self.net_label(name)} ({reason}).", "out-net-switch", sustained=False)
        self.net_last = 0.0
        if self.on_air:
            outs = [o for o in self.engine.outputs if o.cfg["type"] == "internet"]
            for o in outs:
                o.stop()
            QTimer.singleShot(2500, lambda: [o.start() for o in outs if self.on_air and o.cfg.get("enabled", True)])

    # ------------------------------------------------------------ SOS
    def _page_sos(self):
        pg = Page()
        g = pg.grid
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        # --- module mis en avant : prévenir en cas de panne
        al = self.al_card = HeroCard()
        al.lay.setContentsMargins(18, 10, 20, 10)
        h = QHBoxLayout()
        h.setSpacing(22)
        self.al_phone = PhoneAnim()
        if MINI:                                          # minimaliste : pas de téléphone animé
            self.al_phone.hide()
        h.addWidget(self.al_phone, 0, Qt.AlignmentFlag.AlignVCenter)
        left = QVBoxLayout()
        left.setSpacing(8)
        tt = lab("Prévenir en cas de panne", "")
        tt.setStyleSheet("font-size:19px;font-weight:800;")
        left.addWidget(tt)
        st = self.al_sub = lab(f"Notification par SMS, mail ou messagerie dès qu'une panne dure plus de {Alerts.OUTAGE_S} s.", "")
        st.setStyleSheet(f"color:{MUT};font-size:12px;")
        left.addWidget(st)
        left.addSpacing(4)
        self.al_head = lab("", "")
        self.al_head.setStyleSheet(f"font-size:16px;font-weight:700;color:{OKC};")
        left.addWidget(self.al_head)
        ch = QHBoxLayout()
        ch.setSpacing(8)
        self.al_chan = {}
        for key in ("mail", "sms", "msg"):
            l = lab("", "")
            l.setCursor(Qt.CursorShape.PointingHandCursor)
            l.mouseReleaseEvent = lambda _e: self.alert_dialog()
            self.al_chan[key] = l
            ch.addWidget(l)
        ch.addStretch(1)
        left.addLayout(ch)
        self.l_alert = lab("", "mut")
        self.l_alert.hide()
        left.addSpacing(2)
        k0 = lab("ME PRÉVENIR QUAND", "")
        k0.setStyleSheet(f"color:{MUT};font-size:10px;font-weight:700;letter-spacing:1px;")
        left.addWidget(k0)
        trg = QHBoxLayout()
        trg.setSpacing(16)
        self.al_sw = {}
        for key, l in (("on_output", "un flux tombe"), ("on_fallback", "plus de son en entrée ou secours muet"), ("on_monitor", "un flux surveillé est inactif")):
            sw = Switch(l)
            sw.setChecked(bool(self.data["alerts"].get(key, True)))
            sw.toggled.connect(lambda on, k=key: self.data["alerts"].__setitem__(k, bool(on)))
            self.al_sw[key] = sw
            trg.addWidget(sw)
        trg.addStretch(1)
        left.addLayout(trg)
        left.addStretch(1)
        h.addLayout(left, 1)
        bt = QVBoxLayout()
        bt.setSpacing(8)
        bt.addStretch(1)
        self.al_cfg = btn("Configurer SMS / mail…", "primary", self.alert_dialog)
        self.al_cfg.setMinimumSize(196, 44)
        self.al_cfg.setStyleSheet("font-size:14px;")
        bt.addWidget(self.al_cfg)
        self.al_testb = btn("Envoyer un test", "", self.alert_test)
        bt.addWidget(self.al_testb)
        if not MINI:                                      # minimaliste : pas de Gaël
            bt.addWidget(btn("Demander à Gaël", "", lambda: (self.assistant.ed.setFocus(), self.assistant.ask("Préviens-moi en cas de panne"))))
        bt.addStretch(1)
        h.addLayout(bt)
        al.lay.addLayout(h)
        g.addWidget(al, 0, 0, 1, 2)
        self.al_head.setWordWrap(True)
        self._sos_lay = (h, bt, trg)
        # --- ressources et performances (+ retard de sécurité)
        rc = Card()
        rc.lay.setContentsMargins(14, 10, 14, 10)
        top = QHBoxLayout()
        top.setSpacing(14)
        self.res = ResourceStrip(self)
        top.addWidget(self.res, 1)
        dv = QVBoxLayout()
        dv.setSpacing(4)
        k0 = lab("RETARD DE SÉCURITÉ", "")
        k0.setStyleSheet(f"color:{MUT};font-size:9px;font-weight:700;letter-spacing:1px;")
        dv.addWidget(k0)
        dr = QHBoxLayout()
        self.sp_delay = Stepper(0, 40, " s")
        self.sp_delay.setToolTip("Retard de sécurité : secondes retenues avant l'antenne (0 = direct)")
        self.sp_delay.valueChanged.connect(self.sos_delay_changed)
        dr.addWidget(self.sp_delay)
        dv.addLayout(dr)
        dv.addStretch(1)
        top.addLayout(dv)
        rc.lay.addLayout(top)
        self.l_health = lab("", "mut")
        self.l_health.hide()
        g.addWidget(rc, 1, 0, 1, 2)
        faq = Card()
        self.assistant = Assistant(self)
        faq.lay.addWidget(self.assistant, 1)
        g.addWidget(faq, 2, 0)
        if MINI:                                          # minimaliste : pas de Gaël, le journal prend toute la largeur
            faq.hide()
        jl = Card("Journal", "Historique des événements d'antenne")
        tb = QHBoxLayout()
        self.seg_jf = Segmented(["Tout", "Problèmes", "Playlist de secours"], 50, 26, fit=True)
        self.seg_jf.setToolTip("Playlist de secours : les silences à l'antenne et les moments où la playlist a pris le relais")
        self.seg_jf.changed.connect(lambda *_: self.journal_render())
        tb.addWidget(self.seg_jf)
        self.ed_jq = QLineEdit()
        self.ed_jq.setPlaceholderText("Chercher…")
        self.ed_jq.setMaximumWidth(140)
        self.ed_jq.setMinimumWidth(110)
        self.ed_jq.textChanged.connect(lambda *_: self.journal_render())
        tb.addWidget(self.ed_jq)
        tb.addStretch(1)
        self.l_jcount = lab("", "")
        self.l_jcount.setStyleSheet(f"color:{BADC};")
        tb.addWidget(self.l_jcount)
        tb.addWidget(btn("Effacer", "", self.journal_clear))
        tb.addWidget(btn("Exporter", "", self.journal_export))
        tb.addWidget(btn("Signaler", "", lambda: self.support_dialog(), "Signaler un problème : rapport prêt à envoyer (sans mot de passe ni coordonnées)"))
        jl.lay.addLayout(tb)
        self.logbox2 = QTextEdit()
        self.logbox2.setReadOnly(True)
        self.logbox2.setMinimumHeight(100)
        jl.lay.addWidget(self.logbox2, 1)
        g.addWidget(jl, 2, 0 if MINI else 1, 1, 2 if MINI else 1)
        g.setRowStretch(2, 1)
        self.alert_summary()
        return pg

    def sos_delay_changed(self, v):
        if self.engine:
            try:
                self.engine.set_delay(float(v))
            except ValueError:
                pass
        self.prof["delay"] = str(v)
        if hasattr(self, "ed_delay") and self.ed_delay.text() != str(v):
            self.ed_delay.setText(str(v))

    def journal_pass(self, ts, msg, cls):
        f = self.seg_jf.val
        if f == 1 and cls != "bad":
            return False
        if f == 2 and not re.search(r"playlist de secours|prend le relais|retour au direct|aucun signal|silence", norm_txt(msg)):
            return False
        q = norm_txt(self.ed_jq.text().strip())
        return not q or q in norm_txt(msg) or q in ts

    def journal_render(self, *_):
        self.logbox2.clear()
        html = []
        for ts, msg, cls in self.log_rec[-600:]:
            if self.journal_pass(ts, msg, cls):
                html.append(log_html(ts, msg))
        self.logbox2.setHtml("<br>".join(html))
        self.logbox2.verticalScrollBar().setValue(self.logbox2.verticalScrollBar().maximum())
        bad = sum(1 for r in self.log_rec if r[2] == "bad")
        self.l_jcount.setText(f"{bad} ⚠" if bad else "")

    def journal_clear(self):
        self.log_rec.clear()
        self.log_lines.clear()
        self.journal_render()

    def journal_export(self):
        dst, _ = QFileDialog.getSaveFileName(self, "Exporter le journal", time.strftime("journal_%Y-%m-%d.txt"), "Texte (*.txt);;CSV (Excel) (*.csv)")
        if not dst:
            return
        csvm = dst.lower().endswith(".csv")
        with open(dst, "w", encoding="utf-8-sig" if csvm else "utf-8", newline="") as fh:
            for ts, msg, cls in self.log_rec:
                fh.write((f'"{ts}";"{cls}";"{msg}"' if csvm else f"{ts}  {msg}") + "\n")
        self.log("Journal exporté : " + dst)

    def export_history(self):
        p = hist_path()
        if not os.path.exists(p):
            return info(self, "Historique", "Rien n'a encore été diffusé : l'historique se remplit pendant l'antenne (cartouches, jingles et titres du secours).")
        dst, _ = QFileDialog.getSaveFileName(self, "Enregistrer l'historique", "historique_diffusions.csv", "CSV (Excel) (*.csv)")
        if dst:
            shutil.copyfile(p, dst)
            self.log("Historique enregistré : " + dst)

    def need_engine(self):
        if self.on_air:
            return True
        info(self, "SOS", "Cette commande agit pendant la diffusion.")
        return False

    def sos_mute(self):
        if self.need_engine():
            self.engine.mute = not self.engine.mute
            self.log("ANTENNE COUPÉE (mute)." if self.engine.mute else "Son rétabli.")

    def sos_tone(self):
        if self.need_engine():
            self.engine.tone = not self.engine.tone
            self.log("Tonalité de test à l'antenne." if self.engine.tone else "Tonalité arrêtée.")

    def sos_restart(self):
        if self.need_engine():
            outs = list(self.engine.outputs)
            for o in outs:
                o.stop()
            self.log("Redémarrage des flux...")
            QTimer.singleShot(2000, lambda: [o.start() for o in outs if self.on_air and o.cfg.get("enabled", True)])

    def dump(self):
        if self.engine:
            self.engine.dump_delay()
        else:
            info(self, "Retard", "Le DUMP n'agit que pendant la diffusion.")

    def run_diag(self):
        self.diag_lines = []
        outs = json.loads(json.dumps(self.outputs_cfg))

        def work():
            lines = []
            L = lines.append
            L(f"{APP} v2 · Python {platform.python_version()} · {platform.platform()}")
            if shutil.which("ffmpeg"):
                L("OK · " + run(["ffmpeg", "-version"]).strip().splitlines()[0][:90])
                enc = run(["ffmpeg", "-hide_banner", "-encoders"])
                for n in ("libmp3lame", "libopus", "libvorbis", "flac", "aac"):
                    L(("OK" if n in enc else "Manque") + f" encodeur {n}")
                L(("OK" if "libfdk_aac" in enc else "Info") + " libfdk_aac (HE-AAC pour DAB+ via ffmpeg)" + ("" if "libfdk_aac" in enc else " : absent, utilise ODR-AudioEnc"))
            else:
                L("Manque · ffmpeg introuvable : installe-le (winget install Gyan.FFmpeg) puis rouvre le terminal.")
            L(("OK" if shutil.which("ffprobe") else "Info") + " ffprobe (titres des pistes)")
            L(("OK" if have_module("sounddevice") else "Info") + " module sounddevice (sortie FM sur carte son)")
            if SYS == "Windows":
                L(("OK" if have_loopback() else "Info") + " module PyAudioWPatch (son de l'ordinateur)")
            try:
                devs, _ = list_devices()
                L(f"OK · {len(devs)} entrée(s) audio détectée(s)" if devs else "Manque · Aucune entrée audio détectée (autorisations micro ?)")
            except Exception as e:
                L(f"Manque · Détection des entrées impossible : {e}")
            for c in outs:
                tag = f"[{c['name']}]"
                try:
                    if c["type"] == "internet":
                        port = int(c["sc_port"] or int(c["port"]) + 1) if c["protocol"] == "Shoutcast" else int(c["port"])
                        socket.create_connection((c["host"], port), timeout=3).close()
                        L(f"OK · {tag} serveur {c['host']}:{port} joignable")
                    elif c["type"] == "dab" and c.get("mode", "").startswith("ODR"):
                        exe = c.get("odr_path") or "odr-audioenc"
                        L(("OK" if (shutil.which(exe) or os.path.isfile(exe)) else "Manque") + f" {tag} odr-audioenc")
                    elif c["type"] == "record":
                        os.makedirs(c["folder"], exist_ok=True)
                        L(f"OK · {tag} dossier OK, {shutil.disk_usage(c['folder']).free / 1e9:.1f} Go libres")
                    elif c["type"] == "fm":
                        L(("OK" if c.get("device") else "Manque") + f" {tag} carte son " + ("choisie" if c.get("device") else "non choisie"))
                except Exception as e:
                    L(f"Manque · {tag} {e}")
            L(f"Info · Réglages : {CONF}")
            L("Diagnostic terminé.")
            self.bridge.call.emit(lambda: self.assistant.say("\n".join(lines), "bot", [("Copier le rapport", self.copy_report)]))
        threading.Thread(target=work, daemon=True).start()

    def copy_report(self):
        lines = [f"{APP} v2 · Python {platform.python_version()} · {platform.platform()}", f"ffmpeg : {shutil.which('ffmpeg') or 'introuvable'}", "Flux :"]
        for c in self.outputs_cfg:
            lines.append(f"  - {c['type']} « {c['name']} » {self.describe(c)} actif={c.get('enabled', True)}")
        lines += ["", "Journal :"] + self.log_lines[-100:]
        QApplication.clipboard().setText("\n".join(lines))
        self.log("Rapport copié dans le presse-papiers (sans mots de passe).")

    def reset_settings(self):
        if self.on_air:
            return info(self, "Réinitialiser", "Arrête d'abord la diffusion.")
        if not yes(self, "Réinitialiser", "Remettre le profil actuel à zéro ? (une copie est gardée)"):
            return
        try:
            shutil.copy(CONF, CONF + ".sauvegarde")
        except OSError:
            pass
        self.data["profiles"][self.data["last"]] = default_profile()
        self.save_all_raw()
        self.log("Profil réinitialisé (copie : .sauvegarde). Redémarrage…")
        self.restart_app()

    @staticmethod
    def describe(c):
        k = c["type"]
        if k == "internet":
            d = f"{c['protocol']} {c['host']}:{c['port']}"
            return d + c["mount"] if c["protocol"] == "Icecast" else d
        if k == "fm":
            return c.get("device") or "(carte son à choisir)"
        if k == "dab":
            return c["dest"] if c.get("mode", "").startswith("ODR") else c.get("net_url", "")
        return c.get("folder", "")

    # --- alertes
    def alert_dialog(self):
        AlertDialog(self).exec()
        self.alert_summary()

    def alert_test(self):
        if not self.alerts.channels():
            return self.alert_dialog()
        for k in self.alerts.configured():
            self.alerts.set_status(k, "attente")
        self.alert_summary()
        self.alerts.send("Test d'alerte : si tu reçois ce message, les alertes fonctionnent.", force=True, urgent=True, test=True)
        self.log("Alerte de test envoyée : le voyant passe au vert seulement si l'envoi réussit.")

    def alert_result(self, kind, ok, test):
        """Résultat d'un envoi (fil des alertes) : le voyant du canal suit ce qui s'est VRAIMENT passé."""
        if kind not in self.alerts.CHAN_FIELDS:
            return
        if ok:
            self.alerts.set_status(kind, "ok")
        elif test:
            self.alerts.set_status(kind, "echec")
            self.log(f"⚠ Test d'alerte en échec ({ {'mail': 'mail', 'sms': 'SMS', 'msg': 'message'}[kind] }) : vérifie ses réglages.")
        self.save_settings()
        self.alert_summary()

    def alert_card_update(self):
        """Le vert ne s'affiche que si chaque canal configuré a VRAIMENT réussi un envoi (test ou alerte), avec ses réglages
        actuels. Configuré mais pas encore testé : orange ; test raté : rouge."""
        c = self.data["alerts"]
        ch = self.alerts.channels()
        conf = self.alerts.configured()
        st = {k: self.alerts.chan_status(k) for k in conf}
        bad = [k for k in conf if st[k] == "echec"]
        wait = [k for k in conf if st[k] == "attente"]
        untested = [k for k in conf if st[k] == "a_tester"]
        names = {"mail": "mail", "sms": "SMS", "msg": c.get("kind", "message")}
        if not conf:
            head, col = "Personne ne sera prévenu en cas de panne !", BADC
        elif bad:
            head, col = "Le test a échoué (" + ", ".join(names[k] for k in bad) + ") : vérifie les réglages", BADC
        elif wait:
            head, col = "Test en cours…", ACC2
        elif untested:
            head, col = "Alertes configurées : envoie un test pour vérifier", ACC2
        else:
            head, col = "Tu seras prévenu en cas de panne", OKC
        self.al_head.setText(head)
        set_ss(self.al_head, f"font-size:16px;font-weight:700;color:{col};")
        self.al_card.set_color(col)
        verified = bool(conf) and all(st[k] == "ok" for k in conf)
        self.al_phone.set_state(verified, ch if verified else [])
        self.al_cfg.setText("Modifier les alertes…" if ch else "Configurer SMS / mail…")
        if hasattr(self.rail, "set_badge"):
            self.rail.set_badge("sos", None if verified else (BADC if (not conf or bad) else ACC2))
        for key, l, det in (("mail", "Mail", c.get("mail_to", "")), ("sms", "SMS", c.get("sms_to", "")),
                            ("msg", c.get("kind", "Message"), "")):
            w = self.al_chan[key]
            if key not in conf:
                txt, fg, bg = f"○  {l}  ·  non configuré", MUT, FIELD
            else:
                s_ = st[key]
                txt = {"ok": f"●  {l}" + (f"  ·  {det}" if det else "") + "  ·  testé",
                       "echec": f"✕  {l}  ·  échec du test", "attente": f"◌  {l}  ·  test en cours…",
                       "a_tester": f"◐  {l}" + (f"  ·  {det}" if det else "") + "  ·  à tester"}[s_]
                fg = {"ok": OKC, "echec": BADC, "attente": ACC2, "a_tester": ACC2}[s_]
                bg = mixc(PANEL, fg, .16).name()
            w.setText(txt)
            set_ss(w, f"background:{bg};color:{fg};font-weight:700;border-radius:13px;padding:6px 13px;")

    def alert_summary(self):
        self.alert_card_update()
        ch = self.alerts.channels()
        self.l_alert.setText(("Alertes de panne vers : " + ", ".join(ch)) if ch else "Aucune alerte de panne configurée.")
        set_ss(self.l_alert, f"color:{OKC if ch else MUT};")

    def update_health(self, e):
        if not e:
            self.l_health.setText("Moteur audio : arrêté")
            set_ss(self.l_health, f"color:{MUT};")
            return
        slow = e.slow_now()
        self.l_health.setText(f"Moteur audio : {e.proc_ms:.1f} ms de calcul par bloc de 20 ms · blocs en retard : {e.late} · "
                              + ("calcul rapide (numpy)" if np is not None else "calcul standard (installe numpy pour plus de fluidité)"))
        set_ss(self.l_health, f"color:{'#b0391f' if slow else MUT};")

    OUT_CLEAR_S = 20.0    # un flux n'est « rétabli » qu'après 20 s sans problème

    def check_outages(self, e):
        """Flux hors service depuis plus d'une minute : alerte mail / SMS / message (une au début, une à la fin de chaque
        panne). Un flux qui se reconnecte par intermittence (quelques secondes en ligne, puis de nouveau en panne) reste
        UNE panne : avant, chaque reconnexion remettait le compteur à zéro et l'alerte ne partait jamais.
        (Le silence en entrée et la playlist de secours muette sont signalés par le moteur, au délai du secours.)"""
        now = time.time()
        probs = {}
        if self.on_air and not self.preview:
            for o in e.outputs:
                if o.cfg.get("enabled", True) and o.state in ("error", "connecting"):
                    probs["out-" + o.cfg["id"]] = f"flux « {o.cfg['name']} » hors service"
        self.prob_since = getattr(self, "prob_since", {})
        self.prob_sent = getattr(self, "prob_sent", {})
        self.prob_ok = getattr(self, "prob_ok", {})
        due = []
        for k, txt in probs.items():
            self.prob_ok.pop(k, None)
            t0 = self.prob_since.setdefault(k, now)
            if now - t0 >= Alerts.OUTAGE_S and k not in self.prob_sent:
                self.prob_sent[k] = txt
                due.append(txt)
        if due:
            self.alerts.send(f"PANNE depuis {Alerts.OUTAGE_S} s : " + " ; ".join(due) + ".", force=True, urgent=True, sound=True)
        for k in list(self.prob_since):
            if k in probs:
                continue
            if self.on_air and now - self.prob_ok.setdefault(k, now) < self.OUT_CLEAR_S:
                continue                                   # pas encore stable : la panne continue
            self.prob_since.pop(k)
            self.prob_ok.pop(k, None)
            txt = self.prob_sent.pop(k, None)
            if txt and self.on_air:
                self.alerts.send(f"Rétabli : {txt}.", force=True, urgent=True)


class AlertDialog(QDialog):
    """Où envoyer les alertes de panne : un onglet par moyen (mail, SMS, message), fenêtre de taille raisonnable."""

    def __init__(self, app):
        super().__init__(app)
        self.setWindowTitle("Alertes de panne")
        self.app = app
        c = app.data["alerts"]
        self.w = {}
        self.setMinimumWidth(540)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(12)
        t = lab("Prévenir en cas de panne", "")
        t.setStyleSheet("font-size:18px;font-weight:800;")
        v.addWidget(t)
        v.addWidget(lab("Mail et SMS : plus de son en entrée (au délai de la playlist de secours), playlist de secours muette, ou flux en "
                        f"panne depuis plus de {Alerts.OUTAGE_S} s. Un message aussi quand tout revient. Un envoi raté est retenté pendant 30 min.", "mut", True))
        mail_on = bool(c.get("mail_on") and c.get("mail_to"))
        sms_on = bool(c.get("sms_on") and c.get("sms_to"))
        msg_on = bool((c.get("url") or "").strip())
        tabs = ["Mail" + (" ●" if mail_on else ""), "SMS" + (" ●" if sms_on else ""), "Message" + (" ●" if msg_on else ""), "Options"]
        self.seg = Segmented(tabs, 112, 30)
        v.addWidget(self.seg, 0, Qt.AlignmentFlag.AlignLeft)
        self.stack = QStackedWidget()
        v.addWidget(self.stack, 1)

        def page(onkey, rows, note=""):
            pg = QWidget()
            pv = QVBoxLayout(pg)
            pv.setContentsMargins(2, 6, 2, 2)
            pv.setSpacing(8)
            if onkey:
                self.sw(onkey, "Activer", c.get(onkey, False), pv)
            f = QFormLayout()
            f.setHorizontalSpacing(14)
            f.setVerticalSpacing(8)
            for key, label, kw in rows:
                if kw.get("values"):
                    w = QComboBox()
                    w.addItems(kw["values"])
                    w.setCurrentText(str(c.get(key, kw["values"][0])))
                else:
                    w = QLineEdit(str(c.get(key, kw.get("default", ""))))
                    if kw.get("pw"):
                        w.setEchoMode(QLineEdit.EchoMode.Password)
                    if kw.get("narrow"):
                        w.setMaximumWidth(90)
                    if kw.get("ph"):
                        w.setPlaceholderText(kw["ph"])
                self.w[key] = w
                f.addRow(label, w)
            pv.addLayout(f)
            if note:
                pv.addWidget(lab(note, "mut", True))
            pv.addStretch(1)
            self.stack.addWidget(pg)
            return pv
        mv = page("mail_on", [("mail_to", "Destinataire(s)", {"ph": "benevole@radio.bzh, autre@…"}), ("mail_host", "Serveur SMTP", {"ph": "smtp.gmail.com"}),
                              ("mail_port", "Port", {"default": 587, "narrow": 1}), ("mail_user", "Identifiant", {}),
                              ("mail_pw", "Mot de passe", {"pw": 1}), ("mail_from", "Expéditeur", {})],
                  "Gmail : active la validation en 2 étapes et crée un « mot de passe d'application ».")
        self.sw("mail_tls", "Connexion sécurisée (STARTTLS)", c.get("mail_tls", True), mv)
        page("sms_on", [("sms_to", "Numéro destinataire", {"ph": "06…"}), ("sms_provider", "Service", {"values": Alerts.SMS}),
                        ("sms_user", "Identifiant / SID", {}), ("sms_key", "Clé / jeton", {"pw": 1}), ("sms_from", "Numéro expéditeur (Twilio)", {})],
             "Free Mobile : active « Notifications par SMS » dans ton espace abonné, puis copie l'identifiant et la clé.")
        self.w["kind"] = QComboBox()
        self.w["kind"].addItems(Alerts.KINDS)
        self.w["kind"].setCurrentText(c.get("kind", "Discord"))
        self.w["url"] = QLineEdit(c.get("url", ""))
        self.w["url"].setPlaceholderText("https://discord.com/api/webhooks/…  ou  https://ntfy.sh/ma-radio")
        pgm = QWidget()
        pm = QVBoxLayout(pgm)
        pm.setContentsMargins(2, 6, 2, 2)
        fm = QFormLayout()
        fm.setHorizontalSpacing(14)
        fm.addRow("Service", self.w["kind"])
        fm.addRow("Adresse (webhook / ntfy)", self.w["url"])
        pm.addLayout(fm)
        pm.addWidget(lab("Le message part dès que l'adresse est remplie.", "mut", True))
        pm.addStretch(1)
        self.stack.addWidget(pgm)
        po = QWidget()
        pov = QVBoxLayout(po)
        pov.setContentsMargins(2, 6, 2, 2)
        pov.setSpacing(8)
        for k, l in (("on_output", "Prévenir quand un flux tombe"), ("on_fallback", "Prévenir quand il n'y a plus de son en entrée (au délai du secours) ou que la playlist de secours est muette"),
                     ("on_monitor", "Prévenir quand un flux surveillé est inactif")):
            self.sw(k, l, c.get(k, True), pov)
        pov.addWidget(lab("Les identifiants sont enregistrés dans le fichier de réglages de cet ordinateur (chiffrés pour ce compte "
                          "sous Windows). Ils n'apparaissent jamais dans les journaux ni dans les rapports.", "mut", True))
        pov.addStretch(1)
        self.stack.addWidget(po)
        self.seg.changed.connect(self.stack.setCurrentIndex)
        first = 0 if mail_on or not (sms_on or msg_on) else (1 if sms_on else 2)
        self.seg.setValue(first)
        self.stack.setCurrentIndex(first)
        h = QHBoxLayout()
        h.addWidget(btn("Envoyer un test", "", self.test))
        h.addStretch(1)
        h.addWidget(btn("Annuler", "", self.reject))
        h.addWidget(btn("Enregistrer", "primary", self.ok))
        v.addLayout(h)
        scr = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        self.resize(580, min(470, (scr.height() - 80) if scr else 470))

    def sw(self, key, text, val, lay):
        s = Switch(text)
        s.setChecked(bool(val))
        self.w[key] = s
        lay.addWidget(s)

    def store(self):
        c = self.app.data["alerts"]
        for k, w in self.w.items():
            if isinstance(w, Switch):
                c[k] = w.isChecked()
            elif isinstance(w, QComboBox):
                c[k] = w.currentText()
            else:
                c[k] = w.text().strip()
        try:
            c["mail_port"] = int(c["mail_port"])
        except (ValueError, TypeError):
            c["mail_port"] = 587

    def test(self):
        self.store()
        self.app.alerts.send("Test d'alerte : tout fonctionne.", force=True, urgent=True)

    def ok(self):
        self.store()
        self.app.save_all()
        self.accept()


class Assistant(GaelLLM, GaelBrain, AssistantKB, QWidget):
    """Gaël, le radio-bot : discussion épurée façon Messages. Répond en local, ou en conversation avancée (IA) si une clé est réglée."""
    CHIPS = (("État de l'antenne", "Comment va l'antenne ?"), ("Plus de son", "Je n'ai plus de son"), ("Flux Internet", "Crée un flux Internet"),
             ("Playlist de secours", "Active la playlist de secours"), ("Alerte SMS", "Préviens-moi par SMS"), ("Diagnostic", "Lance un diagnostic"))

    def __init__(self, app):
        super().__init__()
        self.app, self.t, self.talk, self.blink, self.typing = app, 0, 0, 0, False
        self.last = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        # en-tête compact : petite tête de Gaël, nom + état sur une ligne, deux petits boutons
        hd = QHBoxLayout()
        hd.setSpacing(8)
        self.bot = GaelView("head", app=app)
        self.bot.setFixedSize(30, 40)
        hd.addWidget(self.bot)
        n = lab("Gaël", "")
        n.setStyleSheet("font-weight:800;font-size:14px;")
        hd.addWidget(n)
        self.l_st = lab("", "")
        hd.addWidget(self.l_st, 1)
        self.b_set = QPushButton("⚙")
        self.b_clear = QPushButton("↺")
        for b_, tip, fn in ((self.b_set, "Conversation avancée (clé API, modèle)", lambda: self.app.gael_settings()),
                            (self.b_clear, "Effacer la conversation", self.clear)):
            b_.setFixedSize(28, 28)
            b_.setCursor(Qt.CursorShape.PointingHandCursor)
            b_.setToolTip(tip)
            b_.setStyleSheet(f"QPushButton{{border-radius:14px;padding:0;font-size:14px;background:{FIELD};color:{MUT};}}"
                             f"QPushButton:hover{{color:{TXT};}}")
            b_.clicked.connect(lambda _=False, f=fn: f())
            hd.addWidget(b_)
        v.addLayout(hd)
        # fil de discussion
        self.sa = QScrollArea()
        self.sa.setWidgetResizable(True)
        self.sa.setFrameShape(QFrame.Shape.NoFrame)
        self.sa.setMinimumHeight(100)
        self.sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("page")
        self.body.setStyleSheet(f"#page{{background:{PANEL};}}")
        self.bl = QVBoxLayout(self.body)
        self.bl.setContentsMargins(2, 6, 6, 6)
        self.bl.setSpacing(6)
        self.bl.addStretch(1)                      # les messages se posent en bas, près de la saisie (comme Messages)
        self.sa.setWidget(self.body)
        v.addWidget(self.sa, 1)
        # accueil (conversation vide) : Gaël en grand, une phrase, et rien d'autre : pas de grand vide
        self.welcome = QWidget()
        wv = QVBoxLayout(self.welcome)
        wv.setContentsMargins(0, 0, 0, 0)
        wv.setSpacing(4)
        wv.addStretch(1)
        self.big = GaelView("chat", app=app)
        self.big.setFixedSize(92, 150)
        wv.addWidget(self.big, 0, Qt.AlignmentFlag.AlignHCenter)
        self.l_hi = lab("", "")
        self.l_hi.setStyleSheet("font-size:17px;font-weight:800;")
        self.l_hi.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        wv.addWidget(self.l_hi)
        l2 = lab("Dis-moi ce qui se passe ou ce que tu veux faire : je propose, tu valides d'un clic.", "mut", True)
        l2.setStyleSheet(f"color:{MUT};font-size:12px;")
        l2.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        wv.addWidget(l2)
        wv.addStretch(1)
        v.addWidget(self.welcome, 1)
        # suggestions : pastilles teintées, faciles à viser
        cs = QWidget()
        cl = WrapRow(cs, 6)
        cl.vsp = 6
        for i, (c, qq) in enumerate(self.CHIPS):
            b = QPushButton(c)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(qq)
            b.setMinimumWidth(0)
            ac = QColor(ACC)
            rg = f"{ac.red()},{ac.green()},{ac.blue()}"
            b.setStyleSheet(f"QPushButton{{background:rgba({rg},22);border:1px solid rgba({rg},80);border-radius:12px;padding:3px 11px;"
                            f"min-height:18px;font-size:12px;font-weight:600;color:{ACCT};}}"
                            f"QPushButton:hover{{background:rgba({rg},50);color:{TXT};}}")
            b.clicked.connect(lambda _=False, x=qq: self.ask(x))
            cl.addWidget(b)
        self.chips_sa = cs
        v.addWidget(cs)
        # saisie : champ arrondi + bouton envoyer
        box = QFrame()
        box.setObjectName("inbox")
        box.setStyleSheet(f"#inbox{{background:{FIELD};border:1px solid {LINE};border-radius:20px;}}")
        r = QHBoxLayout(box)
        r.setContentsMargins(12, 2, 3, 2)
        self.ed = QLineEdit()
        self.ed.setPlaceholderText("Écris à Gaël comme à un collègue…")
        self.ed.setStyleSheet("background:transparent;border:none;padding:4px 0;font-size:13px;")
        self.ed.returnPressed.connect(self.ask)
        r.addWidget(self.ed, 1)
        sb = QPushButton("↑")
        sb.setProperty("kind", "primary")
        sb.setFixedSize(28, 28)
        sb.setCursor(Qt.CursorShape.PointingHandCursor)
        sb.setStyleSheet("border-radius:14px;font-size:15px;font-weight:800;padding:0;")
        sb.clicked.connect(lambda: self.ask())
        r.addWidget(sb)
        v.addWidget(box)
        self.set_status()
        self.greet()

    def chips_compact(self, on):
        self._chips_hidden = on
        if on:
            self.chips_sa.hide()

    def greet(self):
        h = time.localtime().tm_hour
        hi = "Noz vat" if h >= 21 or h < 5 else ("Demat" if h < 18 else "Bonsoir")
        self.l_hi.setText(f"{hi} ! Moi c'est Gaël.")
        self.set_welcome(True)

    def set_welcome(self, on):
        """Conversation vide : accueil (Gaël en grand) à la place du fil de discussion."""
        self.welcome.setVisible(on)
        self.sa.setVisible(not on)

    def set_status(self):
        on = self.llm_on()
        self.l_st.setText(("● conversation avancée" if on else "● en ligne"))
        self.l_st.setStyleSheet(f"color:{OKC};font-size:11px;")
        self.l_st.setToolTip("Conversation avancée : réglable avec le bouton « Réglages » ci-contre.")

    def clear(self):
        while self.bl.count() > 1:
            it = self.bl.takeAt(1)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        self.history, self.pending, self.last = [], None, None
        self.chips_sa.show()
        self.greet()

    # --- bulles
    def bubble(self, text, me, acts):
        w = QWidget()
        h = QVBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        prop = (not me) and text.startswith("Réglage proposé")
        if prop:
            head, _, rest = text.partition("\n")
            card = QFrame()
            card.setObjectName("prop")
            card.setStyleSheet(f"#prop{{background:{mixc(PANEL, ACC, .08).name()};border:1px solid {mixc(LINE, ACC, .45).name()};border-radius:16px;}}")
            card.setMaximumWidth(460)
            card.setMinimumWidth(min(340, max(220, self.sa.viewport().width() - 40)))
            cv = QVBoxLayout(card)
            cv.setContentsMargins(14, 10, 14, 12)
            cv.setSpacing(4)
            k0 = lab("RÉGLAGE PROPOSÉ", "")
            k0.setStyleSheet(f"color:{MUT};font-size:10px;font-weight:700;letter-spacing:1px;")
            cv.addWidget(k0)
            t = lab(head.replace("Réglage proposé · ", ""), "")
            t.setStyleSheet(f"font-weight:800;color:{ACCT};font-size:13px;")
            cv.addWidget(t)
            for line in rest.splitlines():
                k, _, v_ = line.strip().partition(" : ")
                rr = QHBoxLayout()
                a1 = lab(k, "", True)
                a1.setStyleSheet(f"color:{MUT};")
                a2 = lab(v_, "", True)
                a2.setStyleSheet("font-weight:600;")
                a2.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                rr.addWidget(a1, 1)
                rr.addWidget(a2, 1)
                cv.addLayout(rr)
            row = QHBoxLayout()
            row.addWidget(card)
            row.addStretch(1)
            h.addLayout(row)
        else:
            l = QLabel(text.strip())
            l.setWordWrap(True)
            l.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            l.setMaximumWidth(470)
            f_ = QFont(l.font())
            f_.setPixelSize(13)
            tw = max(QFontMetrics(f_).horizontalAdvance(x) for x in (text.strip() or " ").splitlines()) + 32
            l.setMinimumWidth(int(min(tw, 470, max(160, self.sa.viewport().width() - 70))))   # bulle à la largeur du texte
            if me:
                l.setStyleSheet(f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {ACC},stop:1 {'#ff5fa2' if PSYCHE else ACC2});"
                                f"color:{ONACC};border-radius:18px;border-bottom-right-radius:6px;padding:8px 14px;font-size:13px;")
            else:
                l.setStyleSheet(f"background:{mixc(PANEL, TXT, .07).name()};color:{TXT};border-radius:18px;border-bottom-left-radius:6px;"
                                "padding:8px 14px;font-size:13px;")
            row = QHBoxLayout()
            if me:
                row.addStretch(1)
            row.addWidget(l)
            if not me:
                row.addStretch(1)
            h.addLayout(row)
            w.lbl = l
        if acts:
            ar = QHBoxLayout()
            ar.setSpacing(6)
            bts = []

            def run(fn, b):
                for x in bts:
                    x.setEnabled(False)
                if b.property("kind") in ("primary", "danger"):
                    b.setText("✓ " + b.text())
                try:
                    fn()
                except Exception as ex:
                    self.say(f"Oups, ça n'a pas marché ({ex}).", "bot")
            for act in acts:
                lb, fn = act[0], act[1]
                kind = act[2] if len(act) > 2 else ""
                b = btn(lb, kind)
                b.clicked.connect(lambda _=False, f=fn, bb=b: run(f, bb))
                b.setStyleSheet("padding:5px 12px;font-size:12px;border-radius:11px;" + ("" if kind else f"color:{ACCT};"))
                b.setMinimumWidth(0)
                bts.append(b)
                ar.addWidget(b)
            ar.addStretch(1)
            h.addLayout(ar)
        return w

    def scroll_end(self):
        for ms in (20, 120):
            QTimer.singleShot(ms, lambda: self.sa.verticalScrollBar().setValue(self.sa.verticalScrollBar().maximum()))

    def say(self, text, who="bot", actions=None):
        if self._typing_w is not None:
            self._typing_w.deleteLater()
            self._typing_w = None
        self.set_welcome(False)
        self.bl.addWidget(self.bubble(text, who == "me", actions))
        while self.bl.count() > 61:
            it = self.bl.takeAt(1)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        if who == "bot":
            self.bot.say(min(4.0, .5 + len(text) / 70.0))
        self.scroll_end()

    def stream_bubble(self):
        """Bulle vide que la réponse remplit au fil de l'eau (conversation avancée)."""
        if self._typing_w is not None:
            self._typing_w.deleteLater()
            self._typing_w = None
        w = self.bubble("· · ·", False, None)
        self.set_welcome(False)
        self.bl.addWidget(w)
        self.scroll_end()
        w.lbl.setProperty("txt", "")
        return w.lbl

    def stream_update(self, lbl, txt, final=False):
        try:
            if txt:
                lbl.setText(txt.strip())
                lbl.setProperty("txt", txt)
                self.bot.say(.6)
            self.scroll_end()
        except RuntimeError:
            pass

    _typing_w = None

    def ask(self, q=None):
        q = (q if isinstance(q, str) else self.ed.text()).strip()
        if not q:
            return
        self.ed.clear()
        self.say(q, "me")
        self.chips_sa.setVisible(self.bl.count() < 8 and not getattr(self, "_chips_hidden", False))
        self.bot.think = True
        if self.llm_on() and not (self.pending and self.pending.get("ask")):
            return self.llm_ask(q)
        self._typing_w = self.bubble("· · ·", False, None)
        self.bl.addWidget(self._typing_w)

        def reply():
            try:
                a = self.answer(q)
                text, acts = a if isinstance(a, tuple) else (a, None)
            except Exception as ex:
                text, acts = f"Oups, je n'ai pas pu répondre ({ex}).", None
            self.bot.think = False
            self.say(text, "bot", acts)
        QTimer.singleShot(220, reply)


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
