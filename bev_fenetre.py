# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - fenêtre principale : construction, en-tête, horloge, profils, fermeture.
Ses autres parties sont dans bev_diffusion, bev_antenne, bev_miseajour et bev_support (classes mixin), et dans les modules des pages."""
from bev_support import *  # noqa: F401,F403


class MainWindow(UndoMixin, CartMixin, PagesMixin1, PagesMixin2, PagesMixin3, PagesMixin4, DiffusionMixin,
                 AntenneMixin, MiseAJourMixin, SupportMixin, QMainWindow):
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
            QTimer.singleShot(2500, lambda: None if self.on_air else self.start(ask=False))
        if (UPDATE_REPO or S.get("update_repo")) and S.get("update_check", True):
            QTimer.singleShot(4000, lambda: self.update_start(False))
            self.upd_tm = QTimer(self)                        # puis toutes les 6 h (Bev reste souvent ouvert des jours entiers)
            self.upd_tm.timeout.connect(lambda: self.update_start(False))
            self.upd_tm.start(6 * 3600 * 1000)
        QTimer.singleShot(2600, self.after_update_greet)
        QTimer.singleShot(1200, self.warm_pages)          # pages cachées prêtes avant le premier clic sur un onglet
        QTimer.singleShot(6500, self.guide_start)         # premier lancement : Gaël guide jusqu'à la première antenne
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
        RZ[0] = time.time() + .3
        if hasattr(self, "l_beta"):
            self.compact_header()
        # Pendant qu'on tire le bord de la fenêtre, Windows envoie souvent plusieurs changements de taille entre deux images :
        # les ajustements (bandeau, bulle, pages compactes, colonne Diffusion) ne sont faits qu'une fois, pour la dernière
        # taille, au lieu d'une fois par changement.
        if not getattr(self, "_rz_pending", False):
            self._rz_pending = True
            QTimer.singleShot(0, self._after_resize)
        tm = getattr(self, "_warm_tm", None)
        if tm is None:
            tm = self._warm_tm = QTimer(self)
            tm.setSingleShot(True)
            tm.timeout.connect(self.warm_pages)
        tm.start(600)                                    # taille stabilisée : les autres onglets sont remis à la bonne taille

    def _after_resize(self):
        self._rz_pending = False
        self.fit_band()
        self.place_upd_bubble()
        self.apply_compact()
        self.diff_fit()

    def warm_pages(self):
        """Prépare les onglets cachés à la taille actuelle de la fenêtre (mise en page, styles, premier dessin), un par un
        et pendant les temps morts. Sans cela, le premier clic sur un onglet (au lancement, ou après avoir changé la taille
        de la fenêtre) faisait tout ce travail d'un coup : deux à cinq fois plus long qu'un changement d'onglet ordinaire."""
        st = getattr(self, "stack", None)
        if st is None or self._closing or not self.isVisible() or self.isMinimized():
            return
        if calm():                                       # on est encore en train de redimensionner : plus tard
            QTimer.singleShot(400, self.warm_pages)
            return
        size = st.size()
        for i in range(st.count()):
            pg = st.widget(i)
            if i != st.currentIndex() and pg.size() != size:
                try:
                    pg.setGeometry(st.rect())
                    pg.grab()                            # (rendu hors écran : mise en page + dessin, rien ne s'affiche)
                except RuntimeError:
                    return
                QTimer.singleShot(120, self.warm_pages)  # la page suivante au prochain temps mort
                return

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
