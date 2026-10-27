# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - page Monitoring."""
from bev_pages import *  # noqa: F401,F403

# ------------------------------------------------------------------ Monitoring
class FluxLamp(QWidget):
    """Voyant d'état d'un flux (pulse doucement quand tout va bien)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(22, 22)
        self.col, self.t = MUT, 0.0

    def set_color(self, c):
        self.col = c
        self.update()

    def tick(self):
        self.t += .12
        self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        c = QColor(self.col)
        k = (math.sin(self.t) + 1) / 2 if ANIM else .5
        halo = QColor(c)
        halo.setAlphaF(.10 + .22 * k)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QPointF(11, 11), 6 + 4 * k, 6 + 4 * k)
        p.setBrush(c)
        p.drawEllipse(QPointF(11, 11), 5.5, 5.5)


def log_html(ts, msg):
    cls = log_class(msg)
    col = {"ok": OKC, "bad": BADC, "warn": ACC2, "info": TXT}[cls]
    esc = lambda x: str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<span style='color:{col}'>●</span> <span style='color:{MUT}'>{esc(ts)}</span>&nbsp; <span style='color:{col}'>{esc(msg)}</span>"


class StreamWatch:
    """Veille CONTINUE d'un flux (onglet Monitoring) : un petit décodage ffmpeg permanent (mono 8 kHz, très léger) écoute le
    flux en direct. Une coupure est vue en ~5 s (plus aucune donnée), un silence au-delà du délai choisi ; reconnexion
    automatique toutes les 5 s. Avant, une vérification de 5 s toutes les 30 s pouvait laisser passer plus d'une minute."""
    CHUNK = 1600                                   # 0,1 s de son (8 kHz, mono, 16 bits)

    def __init__(self, url, params):
        self.url, self.params = url, params        # params() -> (seuil dB, silence toléré s, coupure s)
        self.state, self.detail, self.level = "wait", "Connexion au flux…", -90.0
        self.t_state = time.time()
        self.last_data = self.last_sound = 0.0
        self.stop_ev, self.kick_ev = threading.Event(), threading.Event()
        self.proc = None
        threading.Thread(target=self.run, daemon=True).start()

    def set(self, state, detail):
        if state != self.state:
            self.t_state = time.time()
        self.state, self.detail = state, detail

    def stop(self):
        self.stop_ev.set()
        self.kick_ev.set()
        self._kill()

    def kick(self):
        """« Vérifier maintenant » : reconnexion immédiate."""
        self.kick_ev.set()
        self._kill()

    def _kill(self):
        p = self.proc
        if p is not None and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def run(self):
        while not self.stop_ev.is_set():
            self.kick_ev.clear()
            err = deque(maxlen=6)
            t0 = time.time()
            connected = False
            try:
                p = self.proc = popen(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-rw_timeout", "8000000",
                                       "-i", self.url, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
                threading.Thread(target=Engine.drain, args=(p, err), daemon=True).start()
                threading.Thread(target=self.watchdog, args=(p, t0), daemon=True).start()
                while not self.stop_ev.is_set() and not self.kick_ev.is_set():
                    b = p.stdout.read(self.CHUNK)
                    if not b:
                        break
                    now = time.time()
                    if not connected:
                        connected = True
                        self.last_sound = now
                    self.last_data = now
                    lv = pcm_level_mono(b)
                    self.level = lv
                    thr, sil, _ = self.params()
                    if lv > thr:
                        self.last_sound = now
                        self.set("ok", f"Audio présent (crête {lv:.0f} dB)")
                    elif now - self.last_sound >= sil:
                        self.set("silence", f"Connecté mais pas d'audio (silence depuis {now - self.last_sound:.0f} s)")
                    elif self.state != "ok":
                        self.set("ok", "Audio présent")
            except Exception as ex:
                err.append(str(ex))
            self._kill()
            self.proc = None
            self.level = -90.0
            if self.stop_ev.is_set():
                break
            if not self.kick_ev.is_set():
                why = next((re.sub(r"^(\[[^\]]*\]\s*)+", "", l) for l in reversed(list(err)) if l), "")
                if getattr(self, "_cut", False):
                    why, self._cut = "plus aucune donnée reçue", False
                self.set("down", "Flux inactif : " + friendly_net_error(why, connected))
                self.kick_ev.wait(5)

    def watchdog(self, p, t0):
        while p.poll() is None and not self.stop_ev.is_set():
            time.sleep(0.5)
            _, _, cut = self.params()
            now = time.time()
            if self.last_data >= t0 and now - self.last_data > cut:
                self._cut = True                       # plus de données : coupure
                self._kill()
            elif self.last_data < t0 and now - t0 > 12:
                self._kill()                           # ne répond pas du tout


def friendly_net_error(why, connected=False):
    """Erreur ffmpeg -> phrase claire pour l'onglet Monitoring."""
    w = (why or "").lower()
    for pat, txt in (("404", "aucune source sur cette adresse (le serveur répond 404)"), ("401", "accès refusé (401)"),
                     ("403", "accès interdit (403)"), ("refused", "serveur injoignable (connexion refusée)"),
                     ("timed out", "pas de réponse du serveur"), ("timeout", "pas de réponse du serveur"),
                     ("name or service", "adresse du serveur introuvable"), ("getaddrinfo", "adresse du serveur introuvable"),
                     ("no route", "réseau injoignable"), ("network is unreachable", "pas d'accès Internet"),
                     ("plus aucune donnée", "le flux s'est coupé (plus aucune donnée reçue)"),
                     ("input/output error", "le flux s'est coupé"), ("end of file", "le flux s'est arrêté"),
                     ("invalid data", "ce n'est pas un flux audio lisible")):
        if pat in w:
            return txt
    return (why or "")[:90] or ("le flux s'est arrêté" if connected else "aucune réponse")


def pcm_level_mono(b):
    n = len(b) // 2 * 2
    if not n:
        return -90.0
    if np is not None:
        v = int(np.abs(np.frombuffer(b[:n], dtype="<i2").astype(np.int32)).max())
    else:
        a = array("h")
        a.frombytes(b[:n])
        v = max(map(abs, a)) if a else 0
    return 20 * math.log10(v / 32768) if v else -90.0


class PagesMixin3:
    def _page_mon(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(10)
        m = self.data["monitor"]
        m.setdefault("streams", [])
        m.setdefault("interval", 30)
        m.setdefault("threshold", -50)
        m.setdefault("silence_s", 15)
        m.setdefault("cut_s", 4)
        self.mon_streams = m["streams"]
        self.mon_iv, self.mon_thr = m["interval"], m["threshold"]
        self.mon_sil, self.mon_cut = m["silence_s"], m["cut_s"]
        self.mon_watch = {}
        add = Card("Surveiller un flux", "Écoute continue : alerte en quelques secondes en cas de coupure ou de silence")
        h = QHBoxLayout()
        self.ed_mon_url = QLineEdit()
        self.ed_mon_url.setPlaceholderText("Adresse du flux (http://…)")
        self.ed_mon_url.returnPressed.connect(lambda: self.mon_add())
        h.addWidget(self.ed_mon_url, 1)
        h.addWidget(btn("Ajouter", "primary", lambda: self.mon_add()))
        add.lay.addLayout(h)
        h = QHBoxLayout()
        h.addWidget(lab("Écouter sur", "mut"))
        self.cb_listen = QComboBox()
        self.cb_listen.addItem(NODEV)
        self.cb_listen.hide()                   # liste réelle ; on affiche le même sélecteur que la source audio de Diffusion
        self.listen_pick = DevicePicker(mode="out", height=40, role="Écoute du flux", none_label="Sortie par défaut de l'ordinateur")
        self.listen_pick.setMinimumWidth(240)
        self.listen_pick.picked.connect(lambda l: (self.cb_listen.setCurrentText(l or NODEV), self.listen_pick_sync()))
        self.listen_pick.refresh.connect(self.listen_devices)
        h.addWidget(self.listen_pick, 1)
        self.l_listen = lab("Clique « Écouter » sur un flux.", "mut")
        h.addWidget(self.l_listen, 1)
        self.btn_lstop = btn("Arrêter", "", self.mon_listen_stop)
        h.addWidget(self.btn_lstop)
        add.lay.addLayout(h)
        v.addWidget(add)
        self.listen_proc, self.listen_url, self.listen_mon, self.mon_listen_btns = None, None, None, {}
        sf = Card("Flux surveillés", "État en temps réel · vert : audio présent")
        sf.hl.addWidget(btn("Vérifier maintenant", "", self.mon_check_all, "Reconnecte tout de suite la veille de chaque flux."))
        more = btn("Plus")
        mm = QMenu(more)
        for txt, cmd in (("Ajouter mes flux Internet", self.mon_add_mine),
                         ("Copier la liste des flux", self.mon_copy_list), ("Exporter la liste (page web, texte, CSV)…", self.mon_export),
                         ("Réglages de la surveillance…", self.mon_settings)):
            mm.addAction(txt, cmd)
        more.setMenu(mm)
        sf.hl.addWidget(more)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        self.mon_body = QWidget()
        self.mon_body.setObjectName("page")
        self.mon_grid = QGridLayout(self.mon_body)
        self.mon_grid.setColumnStretch(2, 1)
        self.mon_grid.setVerticalSpacing(6)
        sa.setWidget(self.mon_body)
        sf.lay.addWidget(sa, 1)
        v.addWidget(sf, 1)
        inc = Card("Journal des incidents")
        self.mon_log = QTextEdit()
        self.mon_log.setReadOnly(True)
        self.mon_log.setMinimumHeight(48)
        self.mon_log.setMaximumHeight(84)
        inc.lay.addWidget(self.mon_log)
        v.addWidget(inc)
        self.mon_widgets = {}
        self.rebuild_mon()
        QTimer.singleShot(1500, self.listen_devices)
        self.mon_timer = QTimer(self)
        self.mon_timer.timeout.connect(self.mon_tick)
        self.mon_timer.start(1000)
        self.mon_anim_t = QTimer(self)
        self.mon_anim_t.timeout.connect(self.mon_anim)
        self.mon_anim_t.start(250 if SET.get("perf") else 90)
        return w

    def mon_settings(self):
        d = QDialog(self)
        d.setWindowTitle("Réglages de la surveillance")
        f = QFormLayout(d)
        f.setContentsMargins(20, 16, 20, 16)
        ex = lab("Chaque flux est écouté en continu (cela consomme son débit, par exemple 128 kbit/s par flux).", "mut", True)
        ex.setMaximumWidth(380)
        f.addRow(ex)
        b = QLineEdit(str(self.mon_thr))
        c = QLineEdit(str(self.mon_sil))
        k = QLineEdit(str(self.mon_cut))
        for x in (b, c, k):
            x.setMaximumWidth(80)
        f.addRow("Silence sous (dB)", b)
        f.addRow("Alerte silence après (s)", c)
        f.addRow("Alerte coupure après (s)", k)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(d.accept)
        f.addRow(bb)
        d.exec()
        num = lambda t, dft, lo, hi: max(lo, min(hi, float(t.text().replace(",", ".")))) if t.text().strip() else dft
        for attr, w_, dft, lo, hi in (("mon_thr", b, -50.0, -90.0, -1.0), ("mon_sil", c, 15.0, 2.0, 600.0), ("mon_cut", k, 4.0, 2.0, 60.0)):
            try:
                setattr(self, attr, num(w_, dft, lo, hi))
            except ValueError:
                setattr(self, attr, dft)
        self.sync_alerts()

    def mon_params(self):
        return self.mon_iv, self.mon_thr

    def mon_watch_params(self):
        return float(self.mon_thr), float(self.mon_sil), float(self.mon_cut)

    def sync_alerts(self):
        self.data["monitor"].update(interval=self.mon_iv, threshold=self.mon_thr, silence_s=self.mon_sil, cut_s=self.mon_cut)

    def mon_rows(self):
        out = []
        for s in self.mon_streams:
            st, sx = self.mon_state.get(s["url"]), self.mon_stats.get(s["url"])
            out.append((s["name"], s["url"], (st[1] if st else "pas encore vérifié"), (str(st[2]) if st and st[2] is not None else ""),
                        (f"{100 * sx['ok'] // max(1, sx['n'])} %" if sx else "")))
        return out

    def mon_copy_list(self):
        rows = self.mon_rows()
        if not rows:
            return info(self, "Monitoring", "Aucun flux dans la liste.")
        self.copy_text("\n".join(f"{n} : {u}" for n, u, *_ in rows), f"Liste de {len(rows)} flux")

    def mon_export(self):
        rows = self.mon_rows()
        if not rows:
            return info(self, "Monitoring", "Aucun flux dans la liste.")
        dst, _ = QFileDialog.getSaveFileName(self, "Exporter la liste des flux", time.strftime("flux_%Y-%m-%d.html"),
                                             "Page web (à partager) (*.html);;Texte (*.txt);;CSV (Excel) (*.csv)")
        if not dst:
            return
        low, now = dst.lower(), time.strftime("%d/%m/%Y à %H:%M")
        station = (self.data.get("settings", {}).get("station") or "Ma radio")
        if low.endswith(".csv"):
            body = "Nom;Adresse;État;Auditeurs;Disponibilité\n" + "\n".join(";".join('"%s"' % c.replace('"', "'") for c in r) for r in rows)
            enc = "utf-8-sig"
        elif low.endswith(".txt"):
            body = f"{station} : flux surveillés ({now})\n\n" + "\n".join(f"{n}\n  {u}\n  {s}" for n, u, s, *_ in rows)
            enc = "utf-8"
        else:
            esc = lambda x: str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            tr = "".join(f"<tr><td><b>{esc(n)}</b></td><td><a href='{esc(u)}'>{esc(u)}</a></td><td>{esc(s)}</td><td>{esc(a)}</td><td>{esc(d)}</td></tr>"
                         for n, u, s, a, d in rows)
            body = ("<!doctype html><html lang='fr'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                    f"<title>{esc(station)} · flux</title><style>body{{font:16px system-ui,sans-serif;background:#12151c;color:#eef1f6;margin:0;padding:24px}}"
                    "h1{margin:0 0 4px}small{color:#8a93a6}table{border-collapse:collapse;width:100%;margin-top:18px}"
                    "td,th{padding:10px 12px;border-bottom:1px solid #262c3a;text-align:left}th{color:#8a93a6;font-weight:600}"
                    f"a{{color:#ffb347}}</style><h1>{esc(station)}</h1><small>Flux surveillés · {now}</small>"
                    f"<table><tr><th>Flux</th><th>Adresse</th><th>État</th><th>Auditeurs</th><th>Dispo</th></tr>{tr}</table></html>")
            enc = "utf-8"
        with open(dst, "w", encoding=enc, newline="") as fh:
            fh.write(body)
        self.log(f"Liste de {len(rows)} flux exportée : {dst}")

    def mon_rename(self, url):
        s = next((x for x in self.mon_streams if x["url"] == url), None)
        if s:
            n = ask_text(self, "Renommer", "Nom du flux :", s["name"])
            if n and n.strip():
                s["name"] = n.strip()
                self.rebuild_mon()

    def mon_add(self, name=None, url=None):
        url = (url or self.ed_mon_url.text()).strip()
        if not url:
            return
        if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
            url = "http://" + url
        if any(s["url"] == url for s in self.mon_streams):
            return
        name = (name or "").strip() or url.split("://", 1)[-1]
        self.mon_streams.append({"name": name, "url": url})
        self.ed_mon_url.clear()
        self.rebuild_mon()
        self.mon_check(url)

    def mon_add_mine(self):
        n = 0
        for c in self.outputs_cfg:
            if c["type"] == "internet":
                base = f"http://{c['host']}:{c['port']}"
                self.mon_add(c["name"], base + ("/" + c["mount"].lstrip("/") if c["protocol"] == "Icecast" else "/;"))
                n += 1
        if not n:
            info(self, "Monitoring", "Aucun flux Internet à ajouter.")

    def mon_remove(self, url):
        self.mon_streams[:] = [s for s in self.mon_streams if s["url"] != url]
        self.mon_state.pop(url, None)
        w = self.mon_watch.pop(url, None)
        if w:
            w.stop()
        self.rebuild_mon()

    def rebuild_mon(self):
        g = self.mon_grid
        while g.count():
            it = g.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        self.mon_widgets, self.mon_listen_btns = {}, {}
        if not self.mon_streams:
            g.addWidget(lab("Aucun flux surveillé : saisis une adresse ci-dessus, ou « Plus » > « Ajouter mes flux Internet ».", "mut", True), 0, 0, 1, 5)
        for r, s in enumerate(self.mon_streams):
            dot = GaelHead(40)
            g.addWidget(dot, r, 0)
            nm = QWidget()
            nv = QVBoxLayout(nm)
            nv.setContentsMargins(0, 2, 10, 2)
            nv.setSpacing(0)
            nv.addWidget(lab(s["name"], "")).__class__
            nm.findChildren(QLabel)[0].setStyleSheet("font-weight:700;")
            ul = lab(s["url"] if len(s["url"]) < 44 else s["url"][:41] + "…", "mut")
            ul.setStyleSheet("font-size:11px;")
            ul.setCursor(Qt.CursorShape.PointingHandCursor)
            ul.mouseReleaseEvent = lambda _e, u=s["url"]: self.copy_text(u)
            nv.addWidget(ul)
            g.addWidget(nm, r, 1)
            st = QWidget()
            sv = QVBoxLayout(st)
            sv.setContentsMargins(0, 2, 0, 2)
            sv.setSpacing(0)
            lb = lab("En attente de vérification…", "")
            dis = lab("", "mut")
            dis.setStyleSheet("font-size:11px;")
            sv.addWidget(lb)
            sv.addWidget(dis)
            wv = Wave(26, accent=OKC)
            wv.setVisible(self.listen_url == s["url"])
            sv.addWidget(wv)
            if self.listen_url == s["url"]:
                self.listen_wave = wv
            g.addWidget(st, r, 2)
            b = btn("Stop" if self.listen_url == s["url"] else "Écouter", "", lambda u=s["url"]: self.mon_listen(u))
            g.addWidget(b, r, 3)
            self.mon_listen_btns[s["url"]] = b
            mb = btn("Plus")
            mn = QMenu(mb)
            mn.addAction("Copier l'adresse", lambda u=s["url"]: self.copy_text(u))
            mn.addAction("Renommer…", lambda u=s["url"]: self.mon_rename(u))
            mn.addAction("Retirer de la surveillance", lambda u=s["url"]: self.mon_remove(u))
            mb.setMenu(mn)
            g.addWidget(mb, r, 4)
            self.mon_widgets[s["url"]] = (dot, lb, wv, dis)
            if s["url"] in self.mon_state:
                self.update_mon_row(s["url"])
        g.setRowStretch(len(self.mon_streams) + 1, 1)

    def listen_devices(self):
        try:
            devs = [d for d, _ in list_output_devices()]
        except Exception:
            devs = []
        vals = [NODEV] + devs
        cur = self.cb_listen.currentText()
        self.cb_listen.clear()
        self.cb_listen.addItems(vals)
        if cur in vals:
            self.cb_listen.setCurrentText(cur)
        else:
            cart = self.cb_cdev.currentText() if hasattr(self, "cb_cdev") else NODEV
            self.cb_listen.setCurrentText(cart if cart in vals else NODEV)
        self.listen_pick_sync()

    def listen_pick_sync(self):
        p = getattr(self, "listen_pick", None)
        if p is not None:
            p.set_devices([self.cb_listen.itemText(i) for i in range(1, self.cb_listen.count())])
            t = self.cb_listen.currentText()
            p.set_current("" if t == NODEV else t)

    def mon_listen(self, url):
        if self.listen_url == url:
            return self.mon_listen_stop()
        self.mon_listen_stop()
        dev = self.cb_listen.currentText()
        name = next((s["name"] for s in self.mon_streams if s["url"] == url), url)
        use_sd = dev != NODEV and have_module("sounddevice")
        if not use_sd and not shutil.which("ffplay"):
            return info(self, "Écouter", "Choisis une sortie audio dans la liste (module sounddevice requis), ou installe ffmpeg complet (ffplay).")
        self.listen_url = url
        flags = 0x08000000 if SYS == "Windows" else 0
        if use_sd:
            self.listen_mon = CartMonitor(lambda m: self.log(m.replace("Cartoucheur : carte son", "Écoute : carte son")))
            self.listen_mon.set_device(dev)
            cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re", "-i", url, "-vn", "-ac", "2", "-ar", str(SR), "-f", "s16le", "pipe:1"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=flags)
            mon = self.listen_mon

            def pump():
                while proc.poll() is None:
                    b = proc.stdout.read(CH)
                    if not b:
                        break
                    mon.push(b)
                    self.listen_level = pcm_peak_db(b)
                self.bridge.call.emit(lambda: self.mon_listen_ended(proc))
            threading.Thread(target=pump, daemon=True).start()
        else:
            proc = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", url], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            # niveau pour la forme d'onde : petit décodage à part, en mono 8 kHz (très léger)
            lv = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-re", "-i", url, "-vn", "-ac", "1", "-ar", "8000",
                                   "-f", "s16le", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=flags)
            self.listen_lv = lv

            def lvl():
                while lv.poll() is None:
                    b = lv.stdout.read(800)
                    if not b:
                        break
                    self.listen_level = pcm_peak_db(b)
            threading.Thread(target=lvl, daemon=True).start()
        self.listen_proc = proc
        self.listen_level = -90.0
        self.listen_wave = self.mon_widgets.get(url, (None, None, None, None))[2]
        for u, w in self.mon_widgets.items():
            if w[2] is not None:
                w[2].setVisible(u == url)
                w[2].reset()
        if not hasattr(self, "listen_tm"):
            self.listen_tm = QTimer(self)
            self.listen_tm.timeout.connect(self.listen_feed)
        self.listen_tm.start(50)
        self.l_listen.setText(f"● Écoute de « {name} »" + ("" if use_sd else "  (sortie par défaut de l'ordinateur)"))
        self.l_listen.setStyleSheet(f"color:{OKC};")
        self.refresh_listen_btns()

    def mon_listen_ended(self, proc):
        if proc is self.listen_proc:
            self.l_listen.setText("Le flux s'est arrêté ou ne répond pas.")
            self.l_listen.setStyleSheet(f"color:{BADC};")
            self.mon_listen_stop(keep_msg=True)

    def listen_feed(self):
        w = getattr(self, "listen_wave", None)
        if w is not None and self.listen_proc is not None:
            try:
                w.push(getattr(self, "listen_level", -90.0))
            except RuntimeError:
                pass

    def mon_listen_stop(self, keep_msg=False):
        p, self.listen_proc, self.listen_url = self.listen_proc, None, None
        lv, self.listen_lv = getattr(self, "listen_lv", None), None
        if lv and lv.poll() is None:
            try:
                lv.terminate()
            except OSError:
                pass
        if hasattr(self, "listen_tm"):
            self.listen_tm.stop()
        for w in self.mon_widgets.values():
            if w[2] is not None:
                try:
                    w[2].hide()
                except RuntimeError:
                    pass
        if p and p.poll() is None:
            try:
                p.terminate()
            except OSError:
                pass
        if self.listen_mon:
            self.listen_mon.close()
            self.listen_mon = None
        if not keep_msg:
            self.l_listen.setText("Clique « Écouter » sur un flux ci-dessous.")
            self.l_listen.setStyleSheet(f"color:{MUT};")
        self.refresh_listen_btns()

    def refresh_listen_btns(self):
        for u, b in list(self.mon_listen_btns.items()):
            try:
                b.setText("Stop" if u == self.listen_url else "Écouter")
            except RuntimeError:
                pass

    def mon_anim(self):
        if ANIM and self.page_key == "mon" and not calm():
            for w in self.mon_widgets.values():
                try:
                    w[0].tick()
                except RuntimeError:
                    pass

    def mon_check(self, url):
        """Lance (ou relance tout de suite) la veille continue d'un flux."""
        w = self.mon_watch.get(url)
        if w is None:
            self.mon_watch[url] = StreamWatch(url, self.mon_watch_params)
        else:
            w.kick()
        self.mon_started[url] = time.time()

    def mon_check_all(self):
        for s in self.mon_streams:
            self.mon_check(s["url"])
            self.mon_lis_t = {}
        self.log("Monitoring : vérification immédiate de tous les flux.")

    def mon_stop_all(self):
        for w in list(getattr(self, "mon_watch", {}).values()):
            w.stop()
        self.mon_watch = {}

    def mon_result(self, url, status, detail, lis):
        """Changement d'état d'un flux surveillé : journal des incidents + alerte (bip seulement quand il tombe)."""
        name = next((s["name"] for s in self.mon_streams if s["url"] == url), None)
        if name is None:
            return
        before = self.mon_state.get(url)
        stats = self.mon_stats.setdefault(url, {"n": 0, "ok": 0, "since": time.time()})
        if before and before[0] != status:
            stats["since"] = time.time()
            txt = f"« {name} » : " + ("audio rétabli" if status == "ok" else "INACTIF") + f" ({detail})"
            self.mon_incident(txt)
            self.alerts.send("Flux " + txt, "mon-" + url + status, sound=(status != "ok"))
        elif before is None and status != "ok":
            self.mon_incident(f"« {name} » : INACTIF ({detail})")
        self.mon_state[url] = (status, detail, lis)
        self.update_mon_row(url)

    def mon_incident(self, txt):
        self.mon_log.append(log_html(time.strftime("%d/%m %H:%M:%S"), txt))
        self.log("Monitoring : " + txt)

    def update_mon_row(self, url):
        w = self.mon_widgets.get(url)
        st = self.mon_state.get(url)
        if not (w and st):
            return
        dot, lb, _, dis = w
        dot.set_mood("ok" if st[0] == "ok" else ("warn" if "silence" in (st[1] or "") else "bad"))
        wa = self.mon_watch.get(url)
        dot.set_level(wa.level if (wa and st[0] == "ok") else None)
        set_ss(lb, f"color:{OKC if st[0] == 'ok' else BADC};font-weight:600;")
        since = time.strftime('%H:%M:%S', time.localtime(wa.t_state)) if wa else time.strftime('%H:%M:%S')
        txt = f"{st[1]}  [depuis {since}]"
        if lb.text() != txt:
            lb.setText(txt)
        s = self.mon_stats.get(url)
        parts = ([f"{st[2]} auditeurs"] if st[2] is not None else []) + (
            [f"dispo {100 * s['ok'] // max(1, s['n'])} % depuis {time.strftime('%H:%M', time.localtime(s['since0']))}"] if s and s.get("since0") else [])
        t = " · ".join(parts)
        if dis.text() != t:
            dis.setText(t)

    def mon_tick(self):
        """Une fois par seconde : état de chaque veille (affichage, incidents), disponibilité, nombre d'auditeurs (toutes les 30 s)."""
        now = time.time()
        lis_t = self.__dict__.setdefault("mon_lis_t", {})
        for s in self.mon_streams:
            u = s["url"]
            w = self.mon_watch.get(u)
            if w is None:
                self.mon_check(u)
                continue
            if w.state == "wait":
                continue
            status = "ok" if w.state == "ok" else "down"
            st = self.mon_stats.setdefault(u, {"n": 0, "ok": 0, "since": now})
            st.setdefault("since0", now)
            st["n"] += 1
            st["ok"] += status == "ok"
            lis = (self.mon_state.get(u) or (None, None, None))[2]
            if status == "ok" and now - lis_t.get(u, 0) > 30:
                lis_t[u] = now

                def fetch(u=u):
                    n = fetch_listeners(u)
                    self.bridge.call.emit(lambda: self.mon_lis(u, n))
                threading.Thread(target=fetch, daemon=True).start()
            cur = self.mon_state.get(u)
            if cur is None or cur[0] != status or cur[1] != w.detail:
                self.mon_result(u, status, w.detail, lis)
            elif self.page_key == "mon":
                self.update_mon_row(u)

    def mon_lis(self, u, n):
        cur = self.mon_state.get(u)
        if cur is not None:
            self.mon_state[u] = (cur[0], cur[1], n)
            self.update_mon_row(u)


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
