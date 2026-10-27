# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - page Diffusion de la fenêtre principale : entrée, playlist de secours, options du secours.
Méthodes de la fenêtre principale (MainWindow les reçoit par héritage)."""
from bev_bandeau import *  # noqa: F401,F403


class DiffusionMixin:
    """Partie de MainWindow : page Diffusion de la fenêtre principale : entrée, playlist de secours, options du secours."""

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
        """Fenêtre « Titre en cours depuis l'automate » : une explication simple, puis deux façons de faire (fichier ou
        réseau), l'adresse à recopier dans l'automate et un bouton pour tester. Les réglages techniques (port, réseau local,
        code secret) sont rangés dans « Réglages avancés »."""
        c = dict(self.automate_cfg())
        d = QDialog(self)
        d.setWindowTitle("Titre en cours depuis l'automate")
        v = QVBoxLayout(d)
        v.setContentsMargins(24, 20, 24, 18)
        v.setSpacing(10)
        v.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        W = 520

        def text(t, name="", style=""):
            l_ = lab(t, name, True)
            l_.setFixedWidth(W)
            if style:
                l_.setStyleSheet(style)
            return l_
        v.addWidget(text("Titre en cours depuis l'automate", "", "font-size:18px;font-weight:700;"))
        v.addWidget(text("Votre logiciel de diffusion automatique (RadioDJ, Radiologik, mAirList, Rivendell…) sait quel morceau "
                         "passe. Bev peut récupérer l'artiste, le titre et la pochette : il les affiche dans « 4 · À l'antenne » "
                         "et les envoie aux auditeurs (titre du flux Internet, RDS, DAB+).", "mut"))
        sw_on = Switch("Récupérer le titre depuis l'automate")
        sw_on.setChecked(bool(c["on"]))
        v.addWidget(sw_on)
        box = QWidget()
        bv = QVBoxLayout(box)
        bv.setContentsMargins(0, 4, 0, 0)
        bv.setSpacing(8)
        v.addWidget(box)
        head = QHBoxLayout()
        head.addWidget(lab("Comment l'automate transmet-il le titre ?", ""))
        head.addStretch(1)
        seg = Segmented(["Par le réseau", "Par un fichier"], 60, 28, fit=True)
        seg.setValue(0 if (c["net"] or not c["file"]) else 1)
        head.addWidget(seg)
        bv.addLayout(head)
        # --- par le réseau
        net = QWidget()
        nv = QVBoxLayout(net)
        nv.setContentsMargins(0, 0, 0, 0)
        nv.setSpacing(6)
        nv.addWidget(text("À chaque nouveau morceau, l'automate appelle une adresse de Bev. Recopiez cette adresse dans ses "
                          "réglages « Now Playing » (titre en cours) ou « envoi par adresse web » :", ""))
        url_row = QHBoxLayout()
        ed_url = QLineEdit()
        ed_url.setReadOnly(True)
        url_row.addWidget(ed_url, 1)
        url_row.addWidget(btn("Copier", "", lambda: self.copy_text(ed_url.text(), "Adresse de l'automate")))
        nv.addLayout(url_row)
        nv.addWidget(text("Remplacez ARTISTE, TITRE et POCHETTE par les balises (variables) correspondantes de l'automate. "
                          "Bev accepte aussi un envoi POST (JSON, formulaire, ou texte « Artiste - Titre »).", "mut"))
        bv.addWidget(net)
        # --- par un fichier
        fil = QWidget()
        fv = QVBoxLayout(fil)
        fv.setContentsMargins(0, 0, 0, 0)
        fv.setSpacing(6)
        fv.addWidget(text("L'automate écrit le morceau en cours dans un fichier (texte « Artiste - Titre », XML ou JSON). "
                          "Choisissez ce fichier : Bev le relit dès qu'il change.", ""))
        frow = QHBoxLayout()
        ed_f = QLineEdit(c["file"])
        ed_f.setPlaceholderText("Fichier écrit par l'automate")
        frow.addWidget(ed_f, 1)
        frow.addWidget(btn("Parcourir…", "", lambda: ed_f.setText(
            QFileDialog.getOpenFileName(d, "Fichier du titre en cours", ed_f.text())[0] or ed_f.text())))
        fv.addLayout(frow)
        bv.addWidget(fil)
        # --- réglages avancés (réseau)
        adv_b = btn("Réglages avancés ▾", "", None)
        adv = QWidget()
        av = QVBoxLayout(adv)
        av.setContentsMargins(0, 0, 0, 0)
        av.setSpacing(6)
        prow = QHBoxLayout()
        prow.addWidget(lab("Port", ""))
        ed_port = QLineEdit(str(int(c["port"] or AUTO_PORT)))
        from PySide6.QtGui import QIntValidator
        ed_port.setValidator(QIntValidator(1024, 65535, ed_port))
        ed_port.setFixedWidth(90)
        prow.addWidget(ed_port)
        prow.addWidget(lab("(8765 par défaut ; à changer seulement s'il est déjà utilisé)", "mut"))
        prow.addStretch(1)
        av.addLayout(prow)
        sw_lan = Switch("L'automate est sur un autre ordinateur du réseau local")
        sw_lan.setChecked(bool(c["lan"]))
        av.addWidget(sw_lan)
        sw_tok = Switch("Exiger le code secret (recommandé)")
        sw_tok.setChecked(bool(c.get("lan_token", True)))
        av.addWidget(sw_tok)
        av.addWidget(text("Le code secret, déjà inclus dans l'adresse ci-dessus, empêche un autre appareil du réseau de changer "
                          "le titre à l'antenne.", "mut"))
        adv.setVisible(False)
        adv_b.clicked.connect(lambda: (adv.setVisible(not adv.isVisible()),
                                       adv_b.setText("Réglages avancés ▴" if adv.isVisible() else "Réglages avancés ▾")))
        bv.addWidget(adv_b, 0, Qt.AlignmentFlag.AlignLeft)
        bv.addWidget(adv)
        # --- test
        trow = QHBoxLayout()
        b_test = btn("Tester la réception", "", None)
        trow.addWidget(b_test)
        st = lab("", "mut", True)
        trow.addWidget(st, 1)
        bv.addLayout(trow)

        def port():
            try:
                return max(1024, min(65535, int(ed_port.text())))
            except ValueError:
                return AUTO_PORT

        def refresh(*_):
            on = sw_on.isChecked()
            box.setEnabled(on)
            by_net = seg.val == 0
            net.setVisible(by_net)
            fil.setVisible(not by_net)
            adv_b.setVisible(by_net)
            adv.setVisible(adv.isVisible() and by_net)
            sw_tok.setEnabled(sw_lan.isChecked())
            host = "127.0.0.1"
            if sw_lan.isChecked():
                try:
                    host = default_route_ip() or host
                except Exception:
                    pass
            tk = f"token={c['token']}&" if (sw_lan.isChecked() and sw_tok.isChecked()) else ""
            ed_url.setText(f"http://{host}:{port()}/?{tk}artist=ARTISTE&title=TITRE&cover=POCHETTE")
            ed_url.setCursorPosition(0)
            b_test.setVisible(by_net)

        def save():
            cfg = self.automate_cfg()
            by_net = seg.val == 0
            cfg.update(on=sw_on.isChecked(), net=by_net, port=port(), lan=sw_lan.isChecked(), lan_token=sw_tok.isChecked())
            if not by_net:
                cfg["file"] = ed_f.text().strip()
            if not cfg["on"]:
                self.auto_info = None
            self.save_settings()
            self.automate_apply()

        def test():
            sw_on.setChecked(True)
            save()
            st.setText("Envoi d'un titre de test…")
            url = f"http://127.0.0.1:{port()}/?token={c['token']}&artist=Bev&title=Test%20de%20r%C3%A9ception"

            def work():
                time.sleep(.6)                                     # le temps que Bev ouvre l'adresse
                try:
                    with urllib.request.urlopen(url, timeout=4) as r:
                        ok = r.read().decode("utf-8", "replace").startswith("ok")
                    msg = "Ça marche : « Bev - Test de réception » est arrivé dans « 4 · À l'antenne »." if ok else "Réponse inattendue de Bev."
                except Exception as ex:
                    msg = f"Bev ne reçoit rien sur ce port ({str(ex)[:80]}). Essayez un autre port dans « Réglages avancés »."
                self.ui(st.setText, msg)
            threading.Thread(target=work, daemon=True).start()
        b_test.clicked.connect(test)
        for w_ in (sw_on, sw_lan, sw_tok):
            w_.toggled.connect(refresh)
        seg.changed.connect(refresh)
        ed_port.textChanged.connect(refresh)
        refresh()
        bb = QHBoxLayout()
        bb.addStretch(1)
        bb.addWidget(btn("Annuler", "", d.reject))
        bb.addWidget(btn("Enregistrer", "primary", d.accept))
        v.addLayout(bb)
        if d.exec():
            save()
            self.log("Automate : " + ("relié." if self.automate_cfg()["on"] else "désactivé."))

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


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
