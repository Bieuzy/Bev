# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - flux de sortie, démarrage et arrêt de l'antenne, moteur audio, boucle d'affichage.
Méthodes de la fenêtre principale (MainWindow les reçoit par héritage)."""
from bev_diffusion import *  # noqa: F401,F403


class AntenneMixin:
    """Partie de MainWindow : flux de sortie, démarrage et arrêt de l'antenne, moteur audio, boucle d'affichage."""

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

    def start(self, ask=True):
        """Démarre l'antenne. ask=False : démarrage automatique (lancement, reprise après plantage), sans question."""
        prof = json.loads(json.dumps(self.collect_profile()))
        if not self.ready_check(ask):                   # « Prêt pour l'antenne ? » : tout ce qui manque, d'un coup
            return
        outs = [o for o in prof["outputs"] if o.get("enabled", True)]
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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
