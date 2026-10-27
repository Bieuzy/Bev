# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - pages Réglages, Enregistrement, À propos et Processeur (traitement du son)."""
from bev_cartoucheur import *  # noqa: F401,F403

# ------------------------------------------------------------------ utilitaires de dialogue + pages Réglages / Enregistrement / À propos










class Swatches(QWidget):
    """Pastilles de couleur d'accent."""
    picked = Signal(str)

    def __init__(self, cur):
        super().__init__()
        self.cur = cur
        self.setFixedSize(len(ACCENTS) * 42, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, e):
        k = int(e.position().x() // 42)
        names = list(ACCENTS)
        if 0 <= k < len(names):
            self.cur = names[k]
            self.update()
            self.picked.emit(names[k])

    def paintEvent(self, e):
        p = new_painter(self)
        for k, (name, (col, _)) in enumerate(ACCENTS.items()):
            x = 20 + k * 42
            if name == self.cur:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(col), 2))
                p.drawEllipse(QPointF(x, 16), 15, 15)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(col))
            p.drawEllipse(QPointF(x, 16), 10, 10)


class Hero(QWidget):
    """Triskell + hermines (ambiances sobre / psyché)."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(320, 84)

    def paintEvent(self, e):
        p = new_painter(self)
        draw_logo(p, 42, 42, 38, None, 4, 0.0)
        f = QFont(self.font())
        f.setPointSizeF(24)
        f.setWeight(QFont.Weight.ExtraBold)
        p.setFont(f)
        p.setPen(QColor(TXT))
        p.drawText(QRectF(94, 10, 220, 40), Qt.AlignmentFlag.AlignVCenter, APP)
        f.setPointSizeF(8)
        f.setWeight(QFont.Weight.Normal)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        p.setFont(f)
        p.setPen(QColor(MUT))
        p.drawText(QRectF(95, 50, 220, 20), Qt.AlignmentFlag.AlignVCenter, "BROADCAST TOOL")




class PagesMixin1:
    TABNAMES = {"Diffusion": "diff", "Processeur d'antenne": "son", "Cartoucheur": "cart", "Enregistrement": "rec", "Monitoring": "mon", "SOS": "sos"}

    @property
    def outputs_cfg(self):
        return self.prof["outputs"]

    def ui(self, fn):
        QTimer.singleShot(0, fn)

    def bell(self):
        QApplication.beep()

    def copy_text(self, txt, what="Adresse"):
        QApplication.clipboard().setText(txt)
        self.log(f"{what} copiée : {txt}")

    def note_restart(self):
        if self.on_air:
            self.log("Modification enregistrée : elle sera prise en compte au prochain démarrage.")

    def open_path(self, p):
        try:
            if SYS == "Windows":
                os.startfile(p)
            else:
                subprocess.Popen(["open" if SYS == "Darwin" else "xdg-open", p])
        except Exception as e:
            self.log(f"Impossible d'ouvrir : {e}")

    # ------------------------------------------------------------ réglages généraux
    def save_settings(self):
        try:
            save_data(self.data)
        except OSError as e:
            self.log(f"Enregistrement des réglages impossible : {e}")

    def keep_awake(self, on):
        try:
            if SYS == "Windows":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 | 0x00000002 if on else 0))
                return
            p = getattr(self, "_awake", None)
            if p and p.poll() is None:
                p.terminate()
            self._awake = None
            if on:
                cmd = ["caffeinate", "-di"] if SYS == "Darwin" else ["systemd-inhibit", "--what=idle:sleep", "--why=Antenne", "sleep", "infinity"]
                if shutil.which(cmd[0]):
                    self._awake = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def apply_settings(self, first=False):
        S = self.data.setdefault("settings", {})
        fl = self.windowFlags()
        top = bool(S.get("topmost"))
        if top != bool(fl & Qt.WindowType.WindowStaysOnTopHint):
            vis = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, top)
            if vis:
                self.show()
        self.keep_awake(bool(S.get("keep_awake")))
        if first and S.get("start_tab", "diff") != "diff":
            QTimer.singleShot(200, lambda: self.go_tab(S["start_tab"]))
        if first and S.get("fullscreen_start"):
            QTimer.singleShot(400, self.toggle_fullscreen)

    # ---- propositions des Réglages
    MARK = os.path.expanduser("~/.bev_onair")

    def props_init(self):
        from PySide6.QtGui import QShortcut
        S = self.data.setdefault("settings", {})
        self._crashed = os.path.exists(self.MARK)
        try:
            os.remove(self.MARK)
        except OSError:
            pass
        if self._crashed and S.get("resume_crash") and not self.data.get("autostart"):
            self.log("Fermeture brutale détectée : reprise de l'antenne.")
            QTimer.singleShot(3000, lambda: None if self.on_air else self.start())
        self.prop_n, self._disk_t = 0, 0.0
        self.prop_tm = QTimer(self)
        self.prop_tm.timeout.connect(self.props_tick)
        self.prop_tm.start(5000)
        sc = QShortcut(QKeySequence("Ctrl+Shift+S"), self)
        sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc.activated.connect(self.panic)

    def panic(self):
        if not self.data.get("settings", {}).get("panic_key"):
            return
        e = self.engine
        if not (e and self.on_air and self.playlist):
            return self.toast("Raccourci d'urgence : démarre la diffusion avec une playlist de secours pour l'utiliser")
        self.toggle_manual()
        self.toast("Playlist de secours lancée" if e.manual else "Retour au direct")

    def props_tick(self):
        S = self.data.get("settings", {})
        self.prop_n += 1
        try:                                                    # marqueur « antenne en cours » pour détecter une fermeture brutale
            if self.on_air:
                if not os.path.exists(self.MARK):
                    open(self.MARK, "w").close()
            elif os.path.exists(self.MARK):
                os.remove(self.MARK)
        except OSError:
            pass
        if S.get("siren") and getattr(self, "alert_kind", None) in ("flux", "son") and self.prop_n % 2 == 0:
            QApplication.beep()
        if S.get("disk_warn") and time.time() - self._disk_t > 1800:
            try:
                d = self.rec_dir() or ""
                if d and os.path.isdir(d) and shutil.disk_usage(d).free < 2e9:
                    self._disk_t = time.time()
                    QApplication.beep()
                    self.log(f"⚠ Disque presque plein : moins de 2 Go libres pour les enregistrements ({d}).")
                    self.toast("Disque presque plein : moins de 2 Go libres", 6000)
            except OSError:
                pass

    def daily_log(self, line):
        try:
            d = os.path.expanduser("~/Bev_journaux")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, time.strftime("%Y-%m-%d") + ".log"), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def set_val(self, key, val):
        self.data.setdefault("settings", {})[key] = val
        self.save_settings()

    def set_flag(self, key, val, restart=False):
        self.data.setdefault("settings", {})[key] = bool(val)
        self.save_settings()
        if restart:
            self.l_restart.setText("Redémarrage nécessaire")
        else:
            self.apply_settings()

    def need_restart(self, key, val):
        S = self.data.setdefault("settings", {})
        if S.get("look_v") != 2:                      # premier choix : on fige l'apparence actuelle (Phare) avant de changer un seul réglage
            S["mood"], S["accent"], S["look_v"] = "phare", "Phare", 2
        self.set_val(key, val)
        self.l_restart.setText("Redémarrage nécessaire")

    def _page_settings(self):
        pg = Page()
        g = pg.grid
        S = self.data.setdefault("settings", {})
        # apparence
        c = Card("Apparence", "Thème, ambiance et couleur d'accent")
        wm = Switch("Mode minimaliste : sobre, sans animation, centré sur la diffusion")
        wm.setChecked(bool(S.get("mini")))
        wm.setToolTip("Palette grise, aucune animation, menu réduit à Diffusion, Cartoucheur, Enregistrement, Monitoring, SOS et Réglages. "
                      "Le plus léger pour l'ordinateur ; à choisir pour les vieilles machines ou les émissions où l'on ne veut rien d'autre sous les yeux.")
        wm.toggled.connect(lambda on: self.set_flag("mini", on, restart=True))
        c.lay.addWidget(wm)
        s1 = Segmented(["Sombre", "Clair", "Auto"], 84)
        s1.setValue({"dark": 0, "light": 1, "auto": 2}.get(S.get("theme", "dark"), 0))
        s1.changed.connect(lambda k: self.need_restart("theme", ("dark", "light", "auto")[k]))
        c.lay.addLayout(row("Mode", s1))
        s2 = Segmented(["Phare Ouest", "Sobre", "Psyché"], 100)
        s2.setValue({"sobre": 1, "psyche": 2}.get(S.get("mood", "phare") if S.get("look_v") == 2 else "phare", 0))
        s2.changed.connect(lambda k: self.need_restart("mood", ("phare", "sobre", "psyche")[k]))
        c.lay.addLayout(row("Ambiance", s2))
        s3 = Segmented(["Menu latéral", "Barre du haut"], 120)
        s3.setValue(1 if S.get("nav") == "top" else 0)
        s3.changed.connect(lambda k: self.need_restart("nav", "top" if k else "side"))
        c.lay.addLayout(row("Navigation", s3))
        sw = Swatches(S.get("accent", "Phare") if S.get("look_v") == 2 else "Phare")
        sw.picked.connect(lambda n: self.need_restart("accent", n))
        c.lay.addLayout(row("Accent", sw))
        w = Switch("Mode performance (ordinateur lent : coupe les effets)")
        w.setChecked(bool(S.get("perf")))
        w.toggled.connect(lambda on: self.set_flag("perf", on, restart=True))
        c.lay.addWidget(w)
        h = QHBoxLayout()
        self.l_restart = lab("", "")
        self.l_restart.setStyleSheet(f"color:{ACCT};")
        h.addWidget(self.l_restart)
        h.addStretch(1)
        h.addWidget(btn("Appliquer et redémarrer", "primary", self.restart_app))
        c.lay.addLayout(h)
        c.lay.addStretch(1)
        g.addWidget(c, 0, 0)
        # fonctionnement
        c = Card("Fonctionnement", "Comportement en exploitation")
        self.sw_auto = Switch("Démarrer l'antenne au lancement (auto-démarrage)")
        self.sw_auto.setChecked(bool(self.prof.get("autostart")))
        self.sw_auto.toggled.connect(lambda on: self.prof.__setitem__("autostart", on))
        c.lay.addWidget(self.sw_auto)
        for key, label in (("topmost", "Toujours au premier plan"), ("keep_awake", "Empêcher la mise en veille de l'ordinateur"),
                           ("confirm_stop", "Demander confirmation avant d'arrêter l'antenne"), ("fullscreen_start", "Démarrer en plein écran")):
            w = Switch(label)
            w.setChecked(bool(S.get(key)))
            w.toggled.connect(lambda on, k=key: self.set_flag(k, on))
            c.lay.addWidget(w)
        w = Switch("Moteur audio séparé (recommandé : l'interface ne peut plus faire décrocher l'antenne)")
        w.setChecked(bool(S.get("engine_proc", True)))
        w.setToolTip("Le son est traité dans un processus à part, sur son propre cœur de processeur.\n"
                     "Pris en compte au prochain démarrage de l'antenne.")
        w.toggled.connect(lambda on: (self.set_flag("engine_proc", on), self.prewarm() if on else None))
        c.lay.addWidget(w)
        h = QHBoxLayout()
        h.addWidget(lab("Baisse du direct sous une cartouche", ""))
        h.addStretch(1)
        self.l_duck = lab("", "mut")
        h.addWidget(self.l_duck)
        c.lay.addLayout(h)
        self.sl_duck = Slider(Qt.Orientation.Horizontal)
        self.sl_duck.setRange(0, 100)
        self.sl_duck.setValue(int(self.prof["carts"].get("duck", 40)))
        self.l_duck.setText(f"{self.sl_duck.value()} %")
        self.sl_duck.valueChanged.connect(self.duck_changed)
        c.lay.addWidget(self.sl_duck)
        sec = lab("SÉCURITÉ DE L'ANTENNE", "mut")
        sec.setStyleSheet(f"color:{MUT};font-size:10px;font-weight:800;letter-spacing:1px;margin-top:6px;")
        c.lay.addWidget(sec)
        for key, label, tip in (            # (anciennes « Propositions » : rangées ici, explication au survol)
                ("siren", "Bip répété tant qu'une panne dure", "Un bip toutes les 10 s sur cet ordinateur, jusqu'au retour de l'antenne (au lieu d'un seul)."),
                ("resume_crash", "Reprendre l'antenne après une fermeture brutale", "Si Bev ou l'ordinateur a planté en pleine émission, la diffusion repart toute seule au prochain lancement."),
                ("daily_log", "Garder un journal par jour dans un fichier", "Un fichier texte par jour dans le dossier « Bev_journaux » de votre dossier personnel."),
                ("disk_warn", "Prévenir quand le disque des enregistrements se remplit", "Alerte (bip + journal) sous 2 Go libres, rappelée toutes les 30 minutes."),
                ("panic_key", "Raccourci d'urgence Ctrl + Maj + S", "Bascule tout de suite sur la playlist de secours, et revient au direct en réappuyant.")):
            w = Switch(label)
            w.setToolTip(tip)
            w.setChecked(bool(S.get(key, False)))
            w.toggled.connect(lambda on, k=key: self.set_val(k, bool(on)))
            c.lay.addWidget(w)
        c.lay.addStretch(1)
        g.addWidget(c, 0, 1, 2, 1)
        # ma radio
        c = Card("Ma radio", "Identité de la station et démarrage")
        self.ed_station = QLineEdit(S.get("station", ""))
        self.ed_station.setMaximumWidth(260)
        self.ed_station.textChanged.connect(self.set_station)
        c.lay.addLayout(row("Nom de la radio", self.ed_station, 130))
        self.cb_start = QComboBox()
        self.cb_start.addItems(list(self.TABNAMES))
        self.cb_start.setCurrentText(next((n for n, k in self.TABNAMES.items() if k == S.get("start_tab", "diff")), "Diffusion"))
        self.cb_start.activated.connect(lambda *_: self.set_val("start_tab", self.TABNAMES.get(self.cb_start.currentText(), "diff")))
        c.lay.addLayout(row("Page au démarrage", self.cb_start, 130))
        for key, label, d in (("fkeys", "Touches F1 à F12 pour jouer les cartouches", True), ("update_check", "Vérifier les mises à jour au lancement", True)):
            w = Switch(label)
            w.setChecked(bool(S.get(key, d)))
            w.toggled.connect(lambda on, k=key: self.set_flag(k, on))
            c.lay.addWidget(w)
        c.lay.addStretch(1)
        g.addWidget(c, 1, 0)
        # sauvegarde
        c = Card()
        c.lay.setContentsMargins(18, 10, 18, 10)
        h = QHBoxLayout()
        tl = QVBoxLayout()
        tl.setSpacing(0)
        t = lab("Sauvegarde", "")
        t.setStyleSheet("font-size:15px;font-weight:700;")
        tl.addWidget(t)
        tl.addWidget(lab("Profils, touches, flux et alertes : une copie, ou les installer sur un autre ordinateur", "mut"))
        h.addLayout(tl, 1)
        h.addWidget(btn("Exporter…", "", self.export_conf))
        h.addWidget(btn("Importer…", "", self.import_conf))
        h.addWidget(btn("Ouvrir le dossier", "", lambda: self.open_path(os.path.dirname(CONF))))
        c.lay.addLayout(h)
        g.addWidget(c, 2, 0, 1, 2)
        g.setRowStretch(3, 1)
        return pg

    def gael_settings(self):
        """Petite fenêtre « Gaël · conversation avancée », ouverte depuis l'assistant (onglet SOS)."""
        S = self.data.setdefault("settings", {})
        if getattr(self, "gael_dlg", None) is None:
            d = self.gael_dlg = QDialog(self)
            d.setWindowTitle("Gaël · conversation avancée")
            d.setMinimumWidth(460)
            c = QVBoxLayout(d)
            c.setContentsMargins(20, 16, 20, 16)
            c.setSpacing(10)
            c.addWidget(lab("Sans clé, Gaël répond en local. Avec une clé API Anthropic, tu lui parles librement ; "
                            "il prépare les réglages, tu valides toujours d'un clic.", "mut", True))
            self.sw_gai = Switch("Activer la conversation avancée")
            self.sw_gai.setChecked(bool(S.get("gael_ai", True)) and bool(S.get("gael_key")))
            self.sw_gai.toggled.connect(lambda on: (self.set_val("gael_ai", bool(on)), self.assistant.set_status()))
            c.addWidget(self.sw_gai)
            kr = QHBoxLayout()
            self.ed_gkey = QLineEdit(S.get("gael_key", ""))
            self.ed_gkey.setEchoMode(QLineEdit.EchoMode.Password)
            self.ed_gkey.setPlaceholderText("sk-ant-…  (console.anthropic.com > API Keys)")
            self.ed_gkey.editingFinished.connect(self.gael_key_saved)
            kr.addWidget(self.ed_gkey, 1)
            kr.addWidget(btn("Afficher", "", lambda: self.ed_gkey.setEchoMode(
                QLineEdit.EchoMode.Normal if self.ed_gkey.echoMode() == QLineEdit.EchoMode.Password else QLineEdit.EchoMode.Password)))
            c.addLayout(kr)
            kr = QHBoxLayout()
            self.cb_gmodel = QComboBox()
            for mid, ml in LLM_MODELS:
                self.cb_gmodel.addItem(ml, mid)
            cur = S.get("gael_model") or LLM_MODELS[0][0]
            if self.cb_gmodel.findData(cur) < 0:
                self.cb_gmodel.addItem(cur, cur)
            self.cb_gmodel.setCurrentIndex(max(0, self.cb_gmodel.findData(cur)))
            self.cb_gmodel.activated.connect(lambda *_: self.set_val("gael_model", self.cb_gmodel.currentData()))
            kr.addWidget(self.cb_gmodel, 1)
            kr.addWidget(btn("Tester", "", self.gael_test))
            c.addLayout(kr)
            self.l_gtest = lab("Clé gardée sur cet ordinateur. Les questions et un résumé de l'antenne (sans mot de passe) sont envoyés à Anthropic ; "
                               "usage facturé sur ton compte.", "mut", True)
            self.l_gtest.setStyleSheet(f"color:{MUT};font-size:11px;")
            c.addWidget(self.l_gtest)
        self.gael_dlg.show()
        self.gael_dlg.raise_()

    def gael_key_saved(self):
        k = self.ed_gkey.text().strip()
        if k != self.data.get("settings", {}).get("gael_key", ""):
            self.set_val("gael_key", k)
            if k and hasattr(self, "sw_gai") and not self.sw_gai.isChecked():
                self.sw_gai.setChecked(True)
            self.assistant.set_status()

    def gael_test(self):
        self.gael_key_saved()
        key = self.ed_gkey.text().strip()
        if not key:
            return self.l_gtest.setText("Saisis d'abord une clé API.")
        self.l_gtest.setText("Test en cours…")
        model = self.cb_gmodel.currentData()

        def work():
            import urllib.request
            try:
                body = json.dumps({"model": model, "max_tokens": 30, "messages": [{"role": "user", "content": "Dis bonjour en cinq mots."}]}).encode()
                req = urllib.request.Request(API_URL, data=body, method="POST", headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                                                                          "content-type": "application/json"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    js = json.loads(r.read().decode("utf-8"))
                txt = "".join(b.get("text", "") for b in js.get("content", []))
                msg, col = f"Ça marche ! Gaël répond : « {txt.strip()[:80]} »", OKC
            except urllib.error.HTTPError as e:
                msg, col = {401: "Clé refusée : vérifie-la sur console.anthropic.com.", 404: "Modèle introuvable : choisis l'autre modèle."}.get(
                    e.code, f"Erreur {e.code} : " + e.read().decode("utf-8", "replace")[:160]), BADC
            except Exception as e:
                msg, col = f"Impossible de joindre le service : {e}", BADC
            self.ui(lambda: (self.l_gtest.setText(msg), self.l_gtest.setStyleSheet(f"color:{col};font-size:11px;")))
        threading.Thread(target=work, daemon=True).start()

    def duck_changed(self, v):
        self.prof["carts"]["duck"] = int(v)
        self.l_duck.setText(f"{int(v)} %")
        if self.engine:
            try:
                self.engine.prof_update("carts", duck=int(v))
            except Exception as _ex:
                trace("duck_changed", _ex)

    def set_station(self, *_):
        name = self.ed_station.text().strip()
        self.set_val("station", name)
        self.nav_w.set_title(name)
        self.setWindowTitle((name + " · " if name else "") + APP)

    def export_conf(self):
        self.save_all()
        dst, _ = QFileDialog.getSaveFileName(self, "Exporter les réglages", "reglages_radio.json", "Réglages (*.json)")
        if dst:
            # export lisible sur un autre ordinateur : mots de passe en clair (ceux du fichier de réglages sont chiffrés
            # pour CE compte Windows seulement)
            try:
                with open(dst, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2, ensure_ascii=False)
            except OSError as e:
                return err(self, "Exporter", f"Export impossible : {e}")
            self.log("Réglages exportés : " + dst + " · attention, ce fichier contient les mots de passe en clair : "
                     "ne le partage pas tel quel.")

    def import_conf(self):
        src, _ = QFileDialog.getOpenFileName(self, "Importer des réglages", "", "Réglages (*.json);;Tous (*)")
        if not src:
            return
        try:
            with open(src, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict) or "profiles" not in d:
                raise ValueError("ce fichier n'est pas un export de réglages")
        except Exception as e:
            return err(self, "Importer", f"Fichier refusé : {e}")
        if not yes(self, "Importer", "Remplacer tes réglages actuels par ceux de ce fichier ? (une copie .avant-import est gardée)"):
            return
        try:
            shutil.copyfile(CONF, CONF + ".avant-import")
        except OSError:
            pass
        try:
            reveal_secrets(d)                     # (export d'avant la 1.2.1 : en clair ; sinon déchiffrés si possible)
            save_data(d)                          # (et rechiffrés pour ce compte Windows)
        except OSError:
            shutil.copyfile(src, CONF)
        self.log("Réglages importés. Redémarrage…")
        self.restart_app()

    def restart_app(self):
        if self.on_air:
            return info(self, "Redémarrer", "Arrête d'abord la diffusion : l'application doit se relancer.")
        try:
            self.save_all()
        except Exception as _ex:
            trace("restart_app", _ex)
        try:
            relaunch_self()
        except Exception as e:
            return err(self, "Redémarrer", f"Impossible de relancer : {e}")
        self._closing = True
        self.close()

    # ------------------------------------------------------------ Enregistrement
    def rec_cfg(self):
        return next((c for c in self.outputs_cfg if c["type"] == "record"), None)

    def _page_record(self):
        pg = Page()
        g = pg.grid
        st = Card("En cours", "Captation synchronisée avec l'antenne")
        self.rec_state = lab("", "")
        self.rec_state.setStyleSheet("font-size:19px;font-weight:700;")
        self.rec_file = lab("", "")
        self.rec_file.setStyleSheet(f"color:{ACCT};")
        self.rec_disk = lab("", "mut")
        st.lay.addWidget(self.rec_state)
        st.lay.addWidget(self.rec_file)
        st.lay.addWidget(self.rec_disk)
        self.btn_rec = btn("", "primary", self.rec_toggle)
        self.btn_rec.setMinimumHeight(40)
        st.lay.addWidget(self.btn_rec, 0, Qt.AlignmentFlag.AlignLeft)
        st.lay.addStretch(1)
        g.addWidget(st, 0, 0)
        cf = Card("Réglages", "Format, découpage et conservation")
        self.rv = {k: "" for k in ("folder", "format", "bitrate", "rotate", "keep_days", "prefix", "stamp")}
        self.rw = {}
        self.rw["folder"] = QLineEdit()             # valeur (cachée) ; l'affichage est la carte dossier ci-dessous
        self.rw["folder"].hide()
        h = QHBoxLayout()
        self.rec_chip = FolderChip()
        self.rec_chip.clicked.connect(self.rec_pick)
        h.addWidget(self.rec_chip, 1)
        h.addWidget(btn("Ouvrir", "", self.rec_open_dir))
        cf.lay.addLayout(h)
        self.rw["folder"].textChanged.connect(lambda t: self.rec_chip.set_path(t))
        self.rw["prefix"] = QLineEdit()
        self.rw["prefix"].setMaximumWidth(260)
        cf.lay.addLayout(row("Nom du fichier", self.rw["prefix"], 110))
        self.rec_ex = lab("", "")
        self.rec_ex.setStyleSheet(f"color:{ACCT};")
        self.rec_ex.setWordWrap(True)
        cf.lay.addWidget(self.rec_ex)
        self.sw_rdate = Switch("Ajouter la date et l'heure au nom du fichier")
        self.sw_rdate.setChecked(True)
        cf.lay.addWidget(self.sw_rdate)
        self.sw_rpige = Switch("Pige ARCOM : découper l'enregistrement en fichiers réguliers")
        cf.lay.addWidget(self.sw_rpige)
        self.rec_pige = QWidget()
        pv = QVBoxLayout(self.rec_pige)
        pv.setContentsMargins(0, 0, 0, 0)
        self.rw["rotate"] = QComboBox()
        self.rw["rotate"].setEditable(True)
        self.rw["rotate"].addItems(["15", "30", "60", "120", "180"])
        self.rw["rotate"].setMaximumWidth(90)
        h = QHBoxLayout()
        h.addWidget(self.rw["rotate"])
        h.addWidget(lab("min  (60 = à l'heure pile)", "mut"))
        pv.addLayout(row("Un fichier toutes les", h, 150))
        self.rw["keep_days"] = QLineEdit()
        self.rw["keep_days"].setMaximumWidth(60)
        h = QHBoxLayout()
        h.addWidget(self.rw["keep_days"])
        h.addWidget(lab("jours  (0 = toujours · vérifiez la durée exigée pour votre radio)", "mut"))
        pv.addLayout(row("Garder pendant", h, 150))
        cf.lay.addWidget(self.rec_pige)
        self.btn_radv = btn("Réglages avancés  ▾", "", self.rec_toggle_adv)
        cf.lay.addWidget(self.btn_radv, 0, Qt.AlignmentFlag.AlignLeft)
        self.rec_adv = QWidget()
        av = QVBoxLayout(self.rec_adv)
        av.setContentsMargins(0, 0, 0, 0)
        self.rw["stamp"] = QComboBox()
        self.rw["stamp"].addItems(list(REC_STAMPS))
        self.rw["format"] = QComboBox()
        self.rw["format"].addItems(REC_FORMATS)
        self.rw["bitrate"] = QComboBox()
        self.rw["bitrate"].setEditable(True)
        self.rw["bitrate"].addItems([str(b) for b in BITRATES])
        for t, k in (("Présentation de la date", "stamp"), ("Format", "format"), ("Débit (kb/s)", "bitrate")):
            self.rw[k].setMaximumWidth(260)
            rw_ = QWidget()                                # (une ligne = un widget : on peut la masquer d'un coup)
            hl = row(t, self.rw[k], 150)
            hl.setContentsMargins(0, 0, 0, 0)
            rw_.setLayout(hl)
            av.addWidget(rw_)
            if k == "bitrate":
                self.rec_br_row = rw_
        self.rec_adv.hide()
        cf.lay.addWidget(self.rec_adv)
        self.rec_saved = lab("", "mut")
        self.rec_saved.setAlignment(Qt.AlignmentFlag.AlignRight)
        cf.lay.addWidget(self.rec_saved)
        g.addWidget(cf, 0, 1)
        fl = Card("Enregistrements", "Archives disponibles dans le dossier")
        self.tb_rec = QTableWidget(0, 4)
        self.tb_rec.setHorizontalHeaderLabels(["", "FICHIER", "DATE", "TAILLE"])
        dl = style_table(self.tb_rec, check_col=0)
        dl.check_from_selection = True               # la case reflète la sélection (Ctrl / Maj + clic, Ctrl+A)
        hh = self.tb_rec.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.tb_rec.setColumnWidth(0, 44)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tb_rec.setColumnWidth(2, 150)
        self.tb_rec.setColumnWidth(3, 90)
        hh.sectionClicked.connect(lambda c: self.rec_select_all() if c == 0 else None)
        self.tb_rec.verticalHeader().hide()
        self.tb_rec.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tb_rec.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tb_rec.cellClicked.connect(self.rec_cell_click)
        self.tb_rec.itemSelectionChanged.connect(self.rec_sel_changed)
        self.tb_rec.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tb_rec.setShowGrid(False)
        self.tb_rec.setMinimumHeight(90)
        self.tb_rec.doubleClicked.connect(lambda *_: self.rec_play())
        fl.lay.addWidget(self.tb_rec)
        h = WrapRow()
        self.b_recall = btn("Tout sélectionner", "", self.rec_select_all)
        h.addWidget(self.b_recall)
        self.l_recsel = lab("", "")
        self.l_recsel.setStyleSheet(f"color:{ACCT};font-weight:700;")
        h.addWidget(self.l_recsel)
        h.addStretch(1)
        self.rec_btns = {}
        for t, fn in (("Écouter", self.rec_play), ("Renommer…", self.rec_rename), ("Déplacer…", self.rec_move),
                      ("Copier le chemin", self.rec_copy), ("Supprimer", self.rec_delete)):
            b = btn(t, "danger" if t == "Supprimer" else "", fn)
            self.rec_btns[t] = b
            h.addWidget(b)
        mb = btn("Plus")
        mm = QMenu(mb)
        mm.addAction("Actualiser la liste", self.rec_files)
        mm.addAction("Ouvrir le dossier", self.rec_open_dir)
        mm.addAction("Ouvrir la corbeille", lambda: self.open_path(self.rec_trash()))
        mm.addAction("Vider la corbeille…", self.rec_empty_trash)
        mb.setMenu(mm)
        h.addWidget(mb)
        fl.lay.addLayout(h)
        g.addWidget(fl, 1, 0, 1, 2)
        g.setRowStretch(2, 1)
        self._rec_job = QTimer(self)
        self._rec_job.setSingleShot(True)
        self._rec_job.timeout.connect(self.rec_autosave)
        self._rec_ready = False
        self.rec_sig, self.rec_newest, self.rec_visit = None, None, 0
        self.rec_load()
        for k, w in self.rw.items():
            if isinstance(w, QComboBox):
                w.currentTextChanged.connect(self.rec_dirty)
            else:
                w.textChanged.connect(self.rec_dirty)
        self.sw_rdate.toggled.connect(self.rec_dirty)
        self.sw_rpige.toggled.connect(self.rec_pige_toggle)
        self.rec_sel_changed()
        return pg

    def rv_get(self, k):
        w = self.rw[k]
        return (w.currentText() if isinstance(w, QComboBox) else w.text()).strip()

    def rv_set(self, k, v):
        w = self.rw[k]
        if isinstance(w, QComboBox):
            w.setCurrentText(str(v))
        else:
            w.setText(str(v))

    def rec_load(self):
        c = self.rec_cfg() or new_output("record")
        self._rec_ready = False
        for k in self.rw:
            self.rv_set(k, str(c.get(k, "")) or ("2026-10-23_16h30" if k == "stamp" else ""))
        self.sw_rpige.setChecked(c.get("pige") == "1")
        self.sw_rdate.setChecked(c.get("date", "1") != "0")
        self.rec_pige.setVisible(self.sw_rpige.isChecked())
        self.rec_example()
        QTimer.singleShot(300, lambda: setattr(self, "_rec_ready", True))

    def rec_pick(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier des enregistrements", self.rv_get("folder") or "")
        if d:
            self.rv_set("folder", d)

    def rec_pige_toggle(self, on):
        if on:
            if self.rv_get("rotate") in ("", "0"):
                self.rv_set("rotate", "60")
            if self.rv_get("keep_days") in ("", "0"):
                self.rv_set("keep_days", "30")
        self.rec_pige.setVisible(on)
        self.rec_dirty()

    def rec_toggle_adv(self):
        on = not self.rec_adv.isVisible()
        self.rec_adv.setVisible(on)
        self.btn_radv.setText("Réglages avancés  " + ("▴" if on else "▾"))

    def rec_dirty(self, *_):
        self.rec_example()
        if not self._rec_ready:
            return
        self.rec_saved.setText("…")
        self._rec_job.start(900)

    def rec_autosave(self):
        self.rec_apply()
        self.rec_saved.setText("✓ Enregistré")

    def rec_example(self):
        if hasattr(self, "rec_br_row"):                    # FLAC / WAV : qualité maximale, pas de débit à choisir
            self.rec_br_row.setVisible(not lossless(self.rv_get("format")))
        try:
            ext = RecordOutput.CODECS.get(self.rv_get("format") or "MP3", RecordOutput.CODECS["MP3"])[1]
            pre = re.sub(r'[\\/:*?"<>|]', "_", self.rv_get("prefix"))
            if self.sw_rpige.isChecked():
                try:
                    mn = int(float(self.rv_get("rotate") or 60))
                except ValueError:
                    mn = 60
                st = "%Y-%m-%d_%Hh" if mn == 60 else "%Y-%m-%d_%Hh%M"
                if pre and pre[-1] not in "_- ":
                    pre += "_"
                txt = "Exemple : " + pre + time.strftime(st) + ext + "  (puis un nouveau fichier toutes les %d min)" % mn
            else:
                name = pre
                if self.sw_rdate.isChecked():
                    if name and name[-1] not in "_- ":
                        name += "_"
                    name += time.strftime(REC_STAMPS.get(self.rv_get("stamp"), "%Y-%m-%d_%Hh%M"))
                txt = "Exemple : " + (name.strip("_- ") or "Enregistrement") + ext + "  (un seul fichier par émission)"
            self.rec_ex.setText(txt)
        except Exception:
            pass

    def rec_apply(self):
        c = self.rec_cfg()
        if not c:
            c = new_output("record")
            self.outputs_cfg.append(c)
        for k in self.rw:
            c[k] = self.rv_get(k)
        c["pige"] = "1" if self.sw_rpige.isChecked() else "0"
        c["date"] = "1" if self.sw_rdate.isChecked() else "0"
        if c["pige"] == "1" and not c.get("prefix"):
            c["prefix"] = "Pige_"
        for k, d in (("rotate", "60"), ("keep_days", "0"), ("bitrate", "192")):
            if k == "rotate" and c["pige"] != "1":
                continue
            try:
                c[k] = str(max(0, int(float(c.get(k) or d))))
            except ValueError:
                c[k] = d
        self.refresh_outputs()
        self.note_restart()
        self.save_all()
        self.rec_files()
        self.log("Réglages d'enregistrement enregistrés.")

    def rec_toggle(self):
        c = self.rec_cfg()
        if not c:
            c = new_output("record")
            self.outputs_cfg.append(c)
        else:
            c["enabled"] = not c.get("enabled", True)
        self.refresh_outputs()
        self.note_restart()
        self.save_all()
        self.rec_tick()

    def rec_dir(self):
        return self.rv_get("folder") or (self.rec_cfg() or {}).get("folder", "")

    def rec_files(self):
        d = self.rec_dir()
        exts = (".mp3", ".wav", ".flac", ".ogg", ".opus")
        rows = []
        try:
            for n in os.listdir(d):
                if n.lower().endswith(exts):
                    p = os.path.join(d, n)
                    rows.append((os.path.getmtime(p), n, p, os.path.getsize(p)))
        except OSError:
            pass
        rows.sort(reverse=True)
        keep = set(self.rec_paths()) if hasattr(self, "rec_btns") else set()
        self.tb_rec.setRowCount(0)
        for mt, n, p, sz in rows[:400]:
            r = self.tb_rec.rowCount()
            self.tb_rec.insertRow(r)
            for k, t in enumerate(("", n, time.strftime("%d/%m/%Y  %H:%M", time.localtime(mt)),
                                   f"{sz / 1e6:.1f} Mo" if sz >= 1e6 else f"{sz / 1e3:.0f} Ko")):
                it = QTableWidgetItem(t)
                it.setData(Qt.ItemDataRole.UserRole, p)
                self.tb_rec.setItem(r, k, it)
        self.rec_newest = rows[0] if rows else None
        if keep:
            from PySide6.QtCore import QItemSelectionModel
            for r in range(self.tb_rec.rowCount()):
                if self.tb_rec.item(r, 1).data(Qt.ItemDataRole.UserRole) in keep:
                    self.tb_rec.selectionModel().select(self.tb_rec.model().index(r, 0),
                                                        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        if hasattr(self, "rec_btns"):
            self.rec_sel_changed()

    def rec_paths(self):
        rows = sorted({i.row() for i in self.tb_rec.selectedIndexes()})
        out = []
        for r in rows:
            it = self.tb_rec.item(r, 1)
            if it:
                out.append(it.data(Qt.ItemDataRole.UserRole))
        return out

    def rec_sel(self):
        p = self.rec_paths()
        return p[0] if p else None

    def rec_cell_click(self, r, c):
        if c == 0:                                    # clic sur la case : ajoute / retire la ligne sans toucher au reste
            sm = self.tb_rec.selectionModel()
            from PySide6.QtCore import QItemSelectionModel
            sm.select(self.tb_rec.model().index(r, 0), QItemSelectionModel.SelectionFlag.Toggle | QItemSelectionModel.SelectionFlag.Rows)

    def rec_select_all(self):
        n = self.tb_rec.rowCount()
        if n and len(self.rec_paths()) >= n:
            self.tb_rec.clearSelection()
        else:
            self.tb_rec.selectAll()

    def rec_sel_changed(self):
        ps = self.rec_paths()
        n, tot = len(ps), self.tb_rec.rowCount()
        size = 0
        for p in ps:
            try:
                size += os.path.getsize(p)
            except OSError:
                pass
        self.l_recsel.setText(f"{n} sélectionné{'s' if n > 1 else ''}  ·  {size / 1e6:.0f} Mo" if n else "")
        self.b_recall.setText("Tout désélectionner" if tot and n >= tot else "Tout sélectionner")
        for t, b in self.rec_btns.items():
            b.setEnabled(n == 1 if t in ("Écouter", "Copier le chemin") else n > 0)

    def rec_trash(self):
        d = os.path.join(self.rec_dir() or os.path.expanduser("~"), ".corbeille")
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def free_name(d, name):
        base, ext = os.path.splitext(name)
        p, k = os.path.join(d, name), 2
        while os.path.exists(p):
            p, k = os.path.join(d, f"{base} ({k}){ext}"), k + 1
        return p

    def rec_play(self):
        p = self.rec_sel()
        if p:
            self.open_path(p)

    def rec_open_dir(self):
        d = self.rec_dir()
        if d:
            os.makedirs(d, exist_ok=True)
            self.open_path(d)

    def rec_copy(self):
        p = self.rec_sel()
        if p:
            self.copy_text(p, "Chemin")

    def rec_rename(self):
        ps = self.rec_paths()
        if not ps:
            return
        moves = []
        if len(ps) == 1:
            p = ps[0]
            base, ext = os.path.splitext(os.path.basename(p))
            n = ask_text(self, "Renommer", "Nouveau nom :", base)
            if not (n and n.strip()):
                return
            dst = self.free_name(os.path.dirname(p), re.sub(r'[\\/:*?"<>|]', "_", n.strip()) + ext)
            try:
                os.rename(p, dst)
                moves.append((dst, p))
            except OSError as e:
                err(self, "Renommer", str(e))
        else:
            n = ask_text(self, "Renommer", f"Nom commun pour les {len(ps)} fichiers (ils seront numérotés 01, 02…) :", "Emission")
            if not (n and n.strip()):
                return
            n = re.sub(r'[\\/:*?"<>|]', "_", n.strip())
            for k, p in enumerate(sorted(ps, key=os.path.getmtime), 1):
                ext = os.path.splitext(p)[1]
                dst = self.free_name(os.path.dirname(p), f"{n}_{k:02d}{ext}")
                try:
                    os.rename(p, dst)
                    moves.append((dst, p))
                except OSError:
                    pass
        self.undo_push_files(moves, f"renommage de {len(moves)} enregistrement(s)")
        self.rec_files()
        if moves:
            self.toast(f"{len(moves)} enregistrement(s) renommé(s)   ·   Ctrl+Z pour annuler")

    def rec_move(self):
        ps = self.rec_paths()
        if not ps:
            return
        d = QFileDialog.getExistingDirectory(self, f"Déplacer {len(ps)} enregistrement(s) vers…", self.rec_dir() or "")
        if not d or os.path.abspath(d) == os.path.abspath(self.rec_dir() or ""):
            return
        moves = []
        for p in ps:
            dst = self.free_name(d, os.path.basename(p))
            try:
                shutil.move(p, dst)
                moves.append((dst, p))
            except OSError as e:
                self.log(f"Déplacement impossible : {e}")
        self.undo_push_files(moves, f"déplacement de {len(moves)} enregistrement(s)")
        self.rec_files()
        if moves:
            self.toast(f"{len(moves)} enregistrement(s) déplacé(s) vers « {os.path.basename(d)} »   ·   Ctrl+Z pour annuler")

    def rec_delete(self):
        ps = self.rec_paths()
        if not ps:
            return
        if not yes(self, "Supprimer", f"Mettre {len(ps)} enregistrement(s) à la corbeille ?\n(Ctrl+Z pour annuler ; la corbeille se vide depuis « Plus ».)"):
            return
        tr = self.rec_trash()
        moves = []
        for p in ps:
            dst = self.free_name(tr, os.path.basename(p))
            try:
                shutil.move(p, dst)
                moves.append((dst, p))
            except OSError as e:
                self.log(f"Suppression impossible : {e}")
        self.undo_push_files(moves, f"suppression de {len(moves)} enregistrement(s)")
        self.rec_files()
        if moves:
            self.toast(f"{len(moves)} enregistrement(s) mis à la corbeille   ·   Ctrl+Z pour annuler")

    def rec_empty_trash(self):
        tr = self.rec_trash()
        files = [os.path.join(tr, f) for f in os.listdir(tr)]
        if not files:
            return info(self, "Corbeille", "La corbeille est vide.")
        size = sum(os.path.getsize(f) for f in files if os.path.isfile(f)) / 1e6
        if yes(self, "Vider la corbeille", f"Supprimer définitivement {len(files)} fichier(s) ({size:.0f} Mo) ? Cette action ne peut pas être annulée."):
            for f in files:
                try:
                    os.remove(f)
                except OSError:
                    pass
            self.undo_stack[:] = [x for x in self.undo_stack if not (x[0] == "files" and any(c.startswith(tr) for c, _ in x[1]))]
            self.log(f"Corbeille vidée ({len(files)} fichier(s)).")

    def rec_tick(self):
        try:
            c = self.rec_cfg()
            live = self.engine.output(c["id"]) if (c and self.on_air and self.engine) else None
            if not c:
                st, col, bt = "Aucun enregistrement", MUT, "Créer l'enregistrement"
            elif not c.get("enabled", True):
                st, col, bt = "Enregistrement désactivé", MUT, "Activer l'enregistrement"
            elif live and live.state == "live":
                st, col, bt = "Enregistrement en cours", BADC, "Désactiver l'enregistrement"
            elif live:
                st, col, bt = live.status_text(), ACC2, "Désactiver l'enregistrement"
            else:
                st, col, bt = "Prêt : démarre avec l'antenne", OKC, "Désactiver l'enregistrement"
            self.rec_state.setText(("●  " if live and live.state == "live" else "") + st)
            set_ss(self.rec_state, f"font-size:19px;font-weight:700;color:{col};")
            self.btn_rec.setText(bt)
            d = self.rec_dir()
            self.rec_file.setText("")
            if live and live.state == "live" and self.rec_newest:
                self.rec_file.setText(f"{self.rec_newest[1]}  ·  {self.rec_newest[3] / 1e6:.1f} Mo")
            try:
                root = d
                while root and not os.path.isdir(root):
                    root = os.path.dirname(root)
                free = shutil.disk_usage(root or ".").free / 1e9
                fmt = (c or {}).get("format", "MP3")
                kbps = 1411 if fmt == "WAV" else (700 if fmt == "FLAC" else int(float((c or {}).get("bitrate") or 192)))
                self.rec_disk.setText(f"Espace libre : {free:.1f} Go  ·  environ {free * 8e6 / kbps / 3600:.0f} h d'enregistrement")
            except (OSError, ValueError):
                self.rec_disk.setText("")
            if self.on_air or self.page_key == "rec":
                sig = (d, int(time.time() // 5) if self.on_air else self.rec_visit)
                if sig != self.rec_sig:
                    self.rec_sig = sig
                    self.rec_files()
        except Exception as _ex:
            trace("rec_tick", _ex)

    # ------------------------------------------------------------ À propos
    def _page_about(self):
        pg = Page()
        g = pg.grid
        hero = Card("Bev", "« Bev » signifie « direct » en breton.")
        hero.lay.setSpacing(6)
        hero.lay.addWidget(lab("Bev est un logiciel de diffusion radiophonique destiné aux radios associatives : diffusion vers Internet, "
                               "la FM et le DAB+, enregistrement de l'antenne, playlist de secours, cartoucheur, processeur d'antenne "
                               "et surveillance des flux, avec alerte en cas de panne.", "", True))
        orig = lab("", "", True)
        orig.setTextFormat(Qt.TextFormat.RichText)
        orig.setOpenExternalLinks(True)
        orig.setText(f"Sa création initiale a été réalisée en 2026 pour <a href='https://rbg.bzh' style='color:{ACCT}'>Radio Bro Gwened</a>"
                     " (rbg.bzh), radio associative du pays vannetais.")
        hero.lay.addWidget(orig)
        hero.lay.addWidget(lab("Bev est un logiciel libre (licence GNU GPL v3), utilisable gratuitement. Ses auteurs invitent chaque utilisatrice et chaque "
                               "utilisateur à soutenir une radio associative de son choix : par un don, une adhésion ou du bénévolat.", "", True))
        hero.lay.addWidget(lab("Les radios associatives défendent des valeurs essentielles : une presse libre et indépendante, sans "
                               "financeur privé ; le travail d'enquête et d'information de proximité ; un rôle d'acteur culturel local, "
                               "ouvert aux langues et aux expressions du territoire ; et une place de premier lieu d'éducation aux médias, "
                               "où chacun peut apprendre à faire de la radio.", "mut", True))
        k = lab("Trugarez ! Merci, et bonne antenne.", "")
        k.setStyleSheet(f"color:{ACCT};font-weight:700;font-size:14px;")
        hero.lay.addWidget(k)
        hero.lay.addStretch(1)
        g.addWidget(hero, 0, 0)
        sy = Card("Système", "Version et composants installés")
        ff = ""
        if shutil.which("ffmpeg"):
            ff = (run(["ffmpeg", "-version"]).strip().splitlines() or [""])[0].replace("ffmpeg version ", "")[:48]
        try:
            import PySide6
            qv = PySide6.__version__
        except Exception:
            qv = "?"
        code = os.environ.get("BEV_CODE")
        vtxt = VERSION + (f"  (mise à jour express, installée : {express_state().get('from') or '?'})" if code and code != "builtin" else "")
        self.about_info = [("Version de l'application", vtxt), ("Python", platform.python_version()), ("Qt (PySide6)", qv),
                           ("Système", platform.platform()[:52]), ("ffmpeg", ff or "introuvable"),
                           ("numpy (calcul rapide)", "oui" if np is not None else "non"),
                           ("sounddevice (cartes son)", "oui" if have_module("sounddevice") else "non"),
                           ("Réglages", CONF)]
        sg = QGridLayout()
        sg.setVerticalSpacing(3)
        sg.setHorizontalSpacing(12)
        for i, (a, b) in enumerate(self.about_info):
            l = lab(a, "mut")
            v = lab(b, "", True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            sg.addWidget(l, i, 0)
            sg.addWidget(v, i, 1)
        sg.setColumnStretch(1, 1)
        sy.lay.addLayout(sg)
        h = QHBoxLayout()
        h.addWidget(btn("Copier les infos", "", lambda: self.copy_text("\n".join(f"{a} : {b}" for a, b in self.about_info), "Infos")))
        h.addWidget(btn("Vérifier les mises à jour", "", lambda: self.update_start(True)))
        h.addStretch(1)
        sy.lay.addLayout(h)
        g.addWidget(sy, 0, 1)
        nw = Card(f"Nouveautés de la version {VERSION}", "Ce qui a changé avec la dernière mise à jour")
        notes = NEWS.get(VERSION) or express_state().get("notes") or ""
        tx = QLabel(md_html(notes) or "Pas de notes pour cette version.")
        tx.setWordWrap(True)
        tx.setTextFormat(Qt.TextFormat.RichText)
        tx.setOpenExternalLinks(True)
        tx.setStyleSheet("font-size:13px;")
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setWidget(tx)
        sc.setMinimumHeight(80)
        sc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)   # défile en interne, n'agrandit pas la page
        sc.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        nw.lay.addWidget(sc, 1)
        h = QHBoxLayout()
        h.addWidget(btn("Tout lire", "", lambda: self.news_dialog(None)))
        h.addWidget(btn("Toutes les versions", "", lambda: webbrowser.open(
            f"https://github.com/{UPDATE_REPO or self.data.get('settings', {}).get('update_repo') or 'Bieuzy/Bev'}/releases")))
        h.addStretch(1)
        nw.lay.addLayout(h)
        g.addWidget(nw, 1, 0)
        sk = Card("Raccourcis", "Commandes clavier et souris")
        grid = QGridLayout()
        for i, (k, v) in enumerate((("F1 à F12", "jouer la touche du cartoucheur"), ("Maj + clic sur une touche", "jouer sur la sortie audio seule (sans antenne)"),
                                    ("Clic droit sur une touche", "régler la touche (nom, couleur, volume…)"), ("Échap", "arrêter toutes les cartouches"),
                                    ("F11", "plein écran"), ("Glisser un son sur une touche", "l'affecter à la touche"),
                                    ("Glisser des fichiers sur la liste", "les ajouter à la playlist de secours"), ("Ctrl + Z  /  Ctrl + Y", "annuler / rétablir la dernière modification"))):
            l = QLabel(f"<b style='color:{ACCT}'>{k}</b>  {v}")
            l.setWordWrap(True)
            grid.addWidget(l, i, 0)
        grid.setVerticalSpacing(4)
        self._sk = (grid, [grid.itemAt(i).widget() for i in range(grid.count())])
        sk.lay.addLayout(grid)
        sk.lay.addStretch(1)
        g.addWidget(sk, 1, 1)
        g.setRowStretch(1, 1)
        return pg

# ------------------------------------------------------------------ Traitement du son
PROC_INFO = {
    "Généraliste": "Variété, programmation mixte : dense mais naturel, voix et musique au même niveau.",
    "Talk-show": "Émissions parlées, plateaux, interviews : voix présentes et régulières, souffle et graves tenus.",
    "Info (news)": "Journaux, flashs, chroniques : intelligibilité maximale, niveau parfaitement constant.",
    "Classique": "Musique classique : dynamique respectée, AGC très lente, aucun écrêtage.",
    "Jazz & acoustique": "Jazz, folk, musique trad' : traitement léger, timbres et respiration préservés.",
    "Pop / Hits": "Hits, pop, électro : brillant, punchy, volume perçu élevé.",
    "Rock": "Rock, guitares : médiums denses, attaque des batteries conservée.",
    "Urbain": "Rap, R'n'B, afro : graves profonds et tenus, voix devant.",
    "Loud": "Volume perçu maximal (style FM commerciale) : très dense, écrêtage poussé.",
    "Protection seule": "Aucune couleur : juste le limiteur final qui garantit le plafond.",
}
PROC_OLD = {"Voix parlée": "Talk-show", "Musique": "Généraliste", "Radio punchy": "Pop / Hits", "Doux (nuit)": "Classique",
            "Neutre": "Protection seule"}
PROC_SHORT = ("Graves", "Bas-méd.", "Médium", "Présence", "Aigus")


class EQCurve(QWidget):
    """Courbe de l'égalisation du processeur (coupe-bas, graves, présence, air, filtre FM) et repères des 5 bandes."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(110)
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.vals = {}

    @staticmethod
    def db_at(f, v):
        num = lambda k: float(v.get(k, 0) or 0)
        r = 0.0
        if num("hpf") > 0:
            r -= 10 * math.log10(1 + (num("hpf") / f) ** 8)
        b = num("bass")
        if abs(b) > .05:
            x = (90.0 / f) ** 2
            r += 10 * math.log10((1 + 10 ** (b / 10) * x) / (1 + x))
        r += num("presence") * math.exp(-(math.log2(f / 3200.0) / 0.8) ** 2)
        a = num("air")
        if abs(a) > .05:
            x = (f / 11000.0) ** 2
            r += 10 * math.log10((1 + 10 ** (a / 10) * x) / (1 + x))
        if v.get("fm15") and f > 14700:
            u = min(1.0, (f - 14700.0) / 1000.0)
            r += 20 * math.log10(max(1e-3, math.cos(u * math.pi / 2) ** 2))
        return r

    def set(self, vals):
        self.vals = dict(vals)
        self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        W, H = self.width(), self.height()
        x0, x1, y0, y1 = 34, W - 12, 8, H - 22
        grid = QColor("#d5d9e3" if LIGHT else "#2b3242")
        txt = QColor("#8a93a8" if LIGHT else "#6c7589")
        fx = lambda f: x0 + (math.log10(f) - math.log10(20)) / (math.log10(20000) - math.log10(20)) * (x1 - x0)
        dy = lambda d: (y0 + y1) / 2 - d / 12.0 * (y1 - y0) / 2
        f8 = QFont(self.font())
        f8.setPointSizeF(7.5)
        p.setFont(f8)
        for d in ((-12, -6, 0, 6, 12) if y1 - y0 >= 90 else (-12, 0, 12)):     # petite hauteur : 3 repères lisibles
            p.setPen(QPen(grid, 1, Qt.PenStyle.DashLine if d else Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(x0, dy(d)), QPointF(x1, dy(d)))
            p.setPen(txt)
            p.drawText(QRectF(0, dy(d) - 8, x0 - 6, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "%+d" % d if d else "0")
        for f, l in ((50, "50"), (100, "100"), (500, "500"), (1000, "1 k"), (5000, "5 k"), (10000, "10 k")):
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(fx(f), y0), QPointF(fx(f), y1))
            p.setPen(txt)
            p.drawText(QRectF(fx(f) - 20, y1 + 3, 40, 14), Qt.AlignmentFlag.AlignCenter, l)
        p.setPen(QPen(qc(ACC, 90), 1, Qt.PenStyle.DotLine))       # frontières des 5 bandes du multibande
        for fc in P_XO:
            p.drawLine(QPointF(fx(fc), y0), QPointF(fx(fc), y1))
        pts = []
        for i in range(161):
            f = 20 * 1000 ** (i / 160.0)
            pts.append(QPointF(fx(f), dy(max(-12, min(12, self.db_at(f, self.vals))))))
        mid = dy(0)
        fill = QPainterPath()
        fill.moveTo(pts[0].x(), mid)
        for q in pts:
            fill.lineTo(q)
        fill.lineTo(pts[-1].x(), mid)
        fill.closeSubpath()
        g = QLinearGradient(x0, 0, x1, 0)
        stops = ("#4cc9f0", "#a76bff", "#ff5fa2") if PSYCHE else (ACC, ACC2, ACC)
        for i, c in enumerate(stops):
            g.setColorAt(i / 2, QColor(c))
        fc_ = QBrush(g)
        p.setPen(Qt.PenStyle.NoPen)
        p.setOpacity(.18)
        p.setBrush(fc_)
        p.drawPath(fill)
        p.setOpacity(1)
        line = QPainterPath()
        line.moveTo(pts[0])
        for q in pts[1:]:
            line.lineTo(q)
        p.setPen(QPen(fc_, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)


class ProcMeters(QWidget):
    """Ce que fait le processeur, en lignes horizontales lisibles (une par étape, dans l'ordre où passe le son) :
    volume automatique (± dB), compression de chacune des 5 bandes, limiteur final et écrêteur, puis la sonie de sortie.
    Mis à jour 30 fois par seconde. Rien ne se chevauche : chaque ligne a son nom à gauche et sa valeur à droite."""
    ROWS = (("agc", "Volume auto"),) + tuple((i, n) for i, n in enumerate(BAND_NAMES)) + (("lim", "Limiteur"), ("clip", "Écrêteur"))

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(150)
        self.setMinimumWidth(420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.m, self.state = {}, "idle"
        self.disp = {"agc": 0.0, "bagc": 0.0, "gr": [0.0] * 5, "lim": 0.0, "clip": 0.0}
        self.hold = [0.0] * 7

    def set(self, m, state):
        self.state = state
        if m:
            self.m = m
            d = self.disp
            k = .45
            d["agc"] += (m.get("agc", 0.0) - d["agc"]) * k
            d["bagc"] += (m.get("bagc", 0.0) - d["bagc"]) * k
            for i, v in enumerate(m.get("gr", [0.0] * 5)[:5]):
                d["gr"][i] = v if v > d["gr"][i] else d["gr"][i] + (v - d["gr"][i]) * .25
            for key in ("lim", "clip"):
                v = m.get(key, 0.0)
                d[key] = v if v > d[key] else d[key] + (v - d[key]) * .2
            vals = d["gr"] + [d["lim"], d["clip"]]
            self.hold = [max(v, h - .15) for v, h in zip(vals, self.hold)]
        self.update()

    def status(self):
        live = self.state in ("air", "input")
        if self.state == "off":
            return "Processeur indisponible (numpy absent) : le son part sans traitement", BADC
        if self.state == "idle":
            return "En attente du son : lance l'antenne ou « Voir l'entrée » (Diffusion)", MUT
        if live and self.m.get("bypass"):
            return "BYPASS : le son brut part à l'antenne", "#ffb020"
        if self.state == "input":
            return "Hors antenne : mesures sur l'entrée, rien n'est diffusé", MUT
        return "À l'antenne : mesures en direct", OKC

    def paintEvent(self, e):
        p = new_painter(self)
        W, H = self.width(), self.height()
        txt, mut = QColor(TXT), QColor(MUT)
        live = self.state in ("air", "input")
        bypass = bool(self.m.get("bypass")) and live
        d = self.disp
        f = QFont(self.font())
        f.setPixelSize(11)
        fb = QFont(f)
        fb.setBold(True)
        try:
            fb.setFeature(QFont.Tag("tnum"), 1)
        except Exception:
            pass
        # --- état, en haut (jamais par-dessus les mesures)
        msg, col = self.status()
        p.setFont(fb)
        p.setPen(QColor(col))
        p.drawText(QRectF(0, 0, W - 170, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(fb).elidedText(msg, Qt.TextElideMode.ElideRight, W - 176))
        # --- lignes : nom | barre | valeur
        top = 24
        n = len(self.ROWS)
        rh = max(12.0, min(30.0, (H - top) / n))
        lw, vw = 92, 58
        x0, x1 = lw, W - 160 - vw
        p.setFont(f)
        for k, (key, name) in enumerate(self.ROWS):
            y = top + k * rh
            cy = y + rh / 2
            if key == 0 or key == "lim":                   # séparateurs : volume | compression | protection
                p.setPen(QPen(QColor("#d5d9e3" if LIGHT else "#2b3242"), 1))
                p.drawLine(QPointF(0, y - 1), QPointF(x1 + vw, y - 1))
            p.setFont(f)
            p.setPen(mut)
            p.drawText(QRectF(0, y, lw - 8, rh), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            bh = max(5.0, min(10.0, rh - 10))
            tr = QRectF(x0, cy - bh / 2, x1 - x0, bh)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(TRACK))
            p.drawRoundedRect(tr, bh / 2, bh / 2)
            if key == "agc":                               # ± 15 dB autour du centre
                v, rng, unit = d["agc"], 15.0, "%+.1f dB"
                mid = tr.center().x()
                if live:
                    c = QColor("#4cc9f0")
                    if bypass:
                        c.setAlphaF(.35)
                    p.setBrush(c)
                    wv = max(-1.0, min(1.0, v / rng)) * tr.width() / 2
                    p.drawRoundedRect(QRectF(min(mid, mid + wv), tr.top(), abs(wv) + 2, bh), bh / 2, bh / 2)
                p.setPen(QPen(txt, 1))
                p.drawLine(QPointF(mid, tr.top() - 2), QPointF(mid, tr.bottom() + 2))
                hold = None
            else:                                          # réduction de gain, de gauche à droite
                if key == "lim":
                    v, rng, c, hold = d["lim"], 6.0, QColor(ONAIR_RED), self.hold[5]
                elif key == "clip":
                    v, rng, c, hold = d["clip"], 8.0, QColor("#ffb020"), self.hold[6]
                else:
                    v, rng, hold = d["gr"][key], 18.0, self.hold[key]
                    c = QColor(grad(.15 + key * .17)) if not callable(SEGCOL) else QColor(SEGCOL(min(1.0, v / 18)))
                unit = "%.1f dB"
                if live:
                    if bypass:
                        c.setAlphaF(.35)
                    p.setBrush(c)
                    p.drawRoundedRect(QRectF(tr.left(), tr.top(), max(bh, tr.width() * min(1.0, v / rng)), bh), bh / 2, bh / 2)
                    if hold is not None and hold > .05:
                        hx = tr.left() + tr.width() * min(1.0, hold / rng)
                        p.setPen(QPen(txt, 1.6))
                        p.drawLine(QPointF(hx, tr.top() - 1), QPointF(hx, tr.bottom() + 1))
            p.setFont(fb)
            p.setPen(txt if live and abs(v) > .3 else mut)
            p.drawText(QRectF(x1 + 6, y, vw - 6, rh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       ((unit % v).replace(".", ",").replace("-", "−")) if live else "–")
        # --- sonie de sortie, à droite
        rx = W - 148
        r = QRectF(rx, 0, 148, H)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(FIELD))
        p.drawRoundedRect(r, 12, 12)
        lu, lm = self.m.get("lufs", -70.0), self.m.get("lufs_m", -70.0)
        on = live and lu > -60
        big = QFont(self.font())
        big.setPixelSize(30 if H >= 150 else 24)
        big.setBold(True)
        cy = H / 2
        p.setFont(f)
        p.setPen(mut)
        p.drawText(QRectF(rx, cy - 54, 148, 16), Qt.AlignmentFlag.AlignHCenter, "SONIE DE SORTIE")
        p.setFont(big)
        p.setPen(QColor(ACCT) if on else mut)
        p.drawText(QRectF(rx, cy - 38, 148, 40), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   ("%.1f" % lu).replace(".", ",").replace("-", "−") if on else "––")
        p.setFont(f)
        p.drawText(QRectF(rx, cy + 2, 148, 16), Qt.AlignmentFlag.AlignHCenter, "LUFS · sur 3 s")
        p.setPen(txt if on and lm > -60 else mut)
        p.drawText(QRectF(rx, cy + 22, 148, 16), Qt.AlignmentFlag.AlignHCenter,
                   ("instantanée %.1f" % lm).replace(".", ",").replace("-", "−") if on and lm > -60 else "instantanée ––")
        out = self.m.get("out", -90.0)
        if on and out > -80:
            p.setPen(mut)
            p.drawText(QRectF(rx, cy + 40, 148, 16), Qt.AlignmentFlag.AlignHCenter,
                       ("crête %.1f dBFS" % out).replace(".", ",").replace("-", "−"))


class PagesMixin2:
    """Page « Processeur d'antenne » (bêta) : quatre banques de réglages, un traitement par flux, réglé en temps réel."""

    # --- réglages enregistrés : self.data["proc"] = {"banks": {A, B, C, D}, "edit": banque affichée, "bypass": bool}
    @staticmethod
    def proc_norm(params):
        p = proc_params((params or {}).get("preset", PROC_DEFAULT))
        p.update({k: v for k, v in (params or {}).items() if k in PROC_BASE})
        p["preset"] = (params or {}).get("preset", PROC_DEFAULT) if (params or {}).get("preset") in PROC_PRESETS else (
            "zero" if (params or {}).get("preset") == "zero" else PROC_DEFAULT)
        p["custom"] = bool((params or {}).get("custom"))
        return p

    def proc_load(self):
        d = self.data.get("proc")
        if not isinstance(d, dict) or not isinstance(d.get("banks"), dict):
            base = None
            if isinstance(d, dict) and isinstance(d.get("params"), dict):       # 1.1 : un seul réglage -> les 4 banques
                base, byp = d["params"], bool(d.get("bypass"))
            else:                                                               # plus ancien : pages A-D de traitement
                pages = self.data.get("fx_pages") or {}
                old = pages.get(self.data.get("fx_page", "A")) or self.data.get("fx") or {}
                base = proc_params(PROC_OLD.get(old.get("preset"), PROC_DEFAULT))
                if old.get("mono"):
                    base["mono"] = True
                byp = bool(old) and not old.get("on", True)
            d = {"banks": {b: json.loads(json.dumps(base)) for b in BANKS}, "edit": "A", "bypass": byp}
            self.data["proc"] = d
        d["banks"] = {b: self.proc_norm(d["banks"].get(b)) for b in BANKS}
        d["edit"] = d.get("edit") if d.get("edit") in BANKS else "A"
        d["bypass"] = bool(d.get("bypass"))
        self.proc_fx(d)
        return d

    @staticmethod
    def proc_fx(d):
        FX["banks"] = json.loads(json.dumps(d["banks"]))
        FX["bypass"] = bool(d.get("bypass"))
        FX["edit"] = d.get("edit", "A")

    def pp(self):
        """Réglages de la banque affichée."""
        return self.proc["banks"][self.proc["edit"]]

    def proc_send(self):
        """Envoi au moteur (au plus 25 fois par seconde pendant qu'on bouge un curseur) : appliqué au bloc audio suivant."""
        self.proc_fx(self.proc)
        e = self.engine
        if e is not None and getattr(e, "running", False):
            try:
                e.apply_fx()
            except Exception as _ex:
                trace("proc_send", _ex)

    def proc_changed(self, refresh=True):
        if not hasattr(self, "_proc_tm"):
            self._proc_tm = QTimer(self)
            self._proc_tm.setSingleShot(True)
            self._proc_tm.timeout.connect(self.proc_send)
            self._proc_save_tm = QTimer(self)
            self._proc_save_tm.setSingleShot(True)
            self._proc_save_tm.timeout.connect(self.save_settings)
        if not self._proc_tm.isActive():
            self._proc_tm.start(40)
        self._proc_save_tm.start(700)
        if refresh:
            self.proc_refresh()

    def proc_slider(self, card, label, key, lo, hi, fmt, idx=None, scale=10, tip="", get=None, put=None, lay=None):
        """Curseur d'un réglage. get / put : conversion pour les réglages simplifiés (ex. « Médiums » = bandes 2 et 3)."""
        h = QHBoxLayout()
        h.setSpacing(8)
        l = lab(label, "")
        l.setFixedWidth(118)
        if tip:
            l.setToolTip(tip)
        h.addWidget(l)
        sl = Slider(Qt.Orientation.Horizontal)
        sl.setRange(int(lo * scale), int(hi * scale))
        if tip:
            sl.setToolTip(tip)
        val = lab("", "")
        val.setFixedWidth(86)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val.setStyleSheet(f"color:{ACCT};font-weight:700;")

        def _get():
            if get is not None:
                return float(get(self.pp()))
            v = self.pp()[key]
            return float(v[idx] if idx is not None else v)

        def moved(v):
            x = v / scale
            val.setText(fmt(x) if callable(fmt) else fmt % x)
            if self._proc_loading:
                return
            pp = self.pp()
            if put is not None:
                put(pp, x)
            elif idx is not None:
                t = list(pp[key])
                t[idx] = x
                pp[key] = t
            else:
                pp[key] = x
            pp["custom"] = True
            self.proc_changed()
        sl.valueChanged.connect(moved)
        h.addWidget(sl, 1)
        h.addWidget(val)
        (lay or card.lay).addLayout(h)
        self.procw.append((sl, val, fmt, _get, scale))
        sl.setValue(int(round(_get() * scale)))
        val.setText(fmt(_get()) if callable(fmt) else fmt % _get())
        return sl

    def proc_switch(self, card, text, key, tip="", lay=None):
        w = Switch(text)
        if tip:
            w.setToolTip(tip)
        w.setChecked(bool(self.pp().get(key)))

        def tg(on):
            if not self._proc_loading:
                self.pp()[key] = bool(on)
                self.pp()["custom"] = True
                self.proc_changed()
        w.toggled.connect(tg)
        (lay or card.lay).addWidget(w)
        self.procs.append((w, key))
        return w

    # équilibre tonal simplifié : 3 curseurs pour les 5 bandes du multibande
    TONE = (("Graves", (0,)), ("Médiums", (1, 2)), ("Aigus", (3, 4)))

    @staticmethod
    def _rel_get(pp):                    # vitesse 1 (lent, 1,2 s) … 10 (rapide, 60 ms) <-> retour du multibande
        r = max(60.0, min(1200.0, float(pp.get("mb_release", 250.0))))
        return 1 + 9 * math.log(1200.0 / r) / math.log(20.0)

    @staticmethod
    def _rel_put(pp, v):
        pp["mb_release"] = round(1200.0 / 20.0 ** ((v - 1) / 9), 0)

    PROC_TABS = (
        ("Niveau", "Rend le volume régulier : l'AGC remonte doucement les passages faibles, la densité règle le volume perçu."),
        ("Couleur", "L'égalisation : la couleur du son (graves, voix, brillance) et le filtrage des fréquences inutiles."),
        ("Compression", "Le « son » de l'antenne : le compresseur 5 bandes rend le son plus dense, plus égal et plus fort."),
        ("Stéréo et sortie", "Largeur stéréo, puis protection finale : rien ne dépasse le plafond, même entre les échantillons."),
    )

    def _page_son(self):
        """Processeur d'antenne, repensé pour être lisible d'un coup d'œil :
        1. en haut, ce qu'on choisit le plus souvent : la banque, le préréglage, le bypass ;
        2. au milieu, ce que fait le processeur (une ligne par étape, dans l'ordre où passe le son) et le réglage de chaque flux ;
        3. en bas, les réglages fins, rangés en 4 onglets (Niveau, Couleur, Compression, Stéréo et sortie)."""
        pg = Page()
        g = pg.grid
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(2, 1)
        self.proc = self.proc_load()
        self.procw, self.procs, self._proc_loading = [], [], True          # (construction : rien n'est envoyé)
        # --- 1. en-tête : banque, préréglage, réinitialiser, à zéro, bypass
        top = Card()
        top.lay.setSpacing(6)
        top.lay.setContentsMargins(18, 12, 18, 12)
        h = QHBoxLayout()
        h.setSpacing(10)
        # (le titre « Processeur » est déjà en haut de la fenêtre : la carte commence directement par la banque)
        beta = lab("BÊTA", "")
        beta.setStyleSheet(f"background:{ACC};color:{ONACC};font-size:10px;font-weight:800;border-radius:8px;padding:2px 8px;")
        beta.setToolTip("Fonction en cours de mise au point : écoutez le résultat avant de l'utiliser à l'antenne.")
        h.addWidget(beta, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addSpacing(8)
        h.addWidget(lab("Banque", "mut"))
        self.seg_bank = Segmented(list(BANKS), w=40, h=28)
        self.seg_bank.setValue(BANKS.index(self.proc["edit"]))
        self.seg_bank.changed.connect(lambda k: self.proc_bank(BANKS[k]))
        self.seg_bank.setToolTip("Quatre banques de réglages. Chaque flux choisit la sienne (carte « Chaque flux ») : "
                                 "plusieurs traitements peuvent tourner en même temps.")
        h.addWidget(self.seg_bank)
        h.addSpacing(6)
        self.btn_preset = btn("Préréglage", "", None, "Charger un préréglage radio dans la banque affichée")
        menu = QMenu(self.btn_preset)
        for name in PROC_ORDER:
            a_ = menu.addAction(name.replace("&", "&&"))
            a_.setToolTip(PROC_INFO.get(name, ""))
            a_.triggered.connect(lambda _c=False, n=name: self.proc_preset(n))
        menu.setToolTipsVisible(True)
        self.btn_preset.setMenu(menu)
        h.addWidget(self.btn_preset)
        self.l_preset = self.btn_preset                     # (ancien nom : le préréglage s'affiche sur le bouton)
        self.btn_preset_reset = btn("Réinitialiser", "", self.proc_reset, "Annule les réglages fins : la banque revient à son préréglage")
        h.addWidget(self.btn_preset_reset)
        h.addWidget(btn("À zéro", "", self.proc_zero, "Réglage neutre : aucune couleur ni compression, seul le limiteur "
                                                       "final garantit le plafond. Point de départ pour construire son son."))
        h.addStretch(1)
        self.btn_bypass = btn("", "primary", self.proc_toggle_bypass,
                              "Bypass : le son brut part à l'antenne sur tous les flux (bascule en fondu, sans coupure)")
        self.btn_bypass.setMinimumHeight(36)
        h.addWidget(self.btn_bypass)
        top.lay.addLayout(h)
        self.l_preset_info = CLabel("", "mut", False, MUT)
        self.l_preset_info.elide = True
        self.l_preset_info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.l_preset_info.setMinimumWidth(40)
        top.lay.addWidget(self.l_preset_info)
        g.addWidget(top, 0, 0, 1, 3)
        # --- 2a. ce que fait le processeur
        nv = Card("Ce que fait le processeur", "Une ligne par étape, dans l'ordre où passe le son")
        self.proc_meters = ProcMeters()
        nv.lay.addWidget(self.proc_meters, 1)
        g.addWidget(nv, 1, 0, 1, 2)
        # --- 2b. réglage envoyé à chaque flux
        pf = Card("Chaque flux", "La banque qui part sur chaque flux")
        self.fx_rows = QVBoxLayout()
        self.fx_rows.setSpacing(4)
        pf.lay.addLayout(self.fx_rows)
        pf.lay.addStretch(1)
        n_ = lab("Chaque banque utilisée ajoute un peu de calcul.", "mut", True)
        n_.setStyleSheet(f"color:{MUT};font-size:11px;")
        n_.setToolTip("Environ 2 ms de calcul par bloc audio de 20 ms et par banque utilisée.")
        pf.lay.addWidget(n_)
        g.addWidget(pf, 1, 2)
        # --- 3. réglages fins, en onglets
        st = Card("Réglages", "")
        self.l_proc_set = st.head
        self.seg_proc = Segmented([n for n, _ in self.PROC_TABS], w=128, h=28)
        st.hl.addWidget(self.seg_proc)
        self.l_proc_tab = lab("", "mut")
        self.l_proc_tab.setStyleSheet(f"color:{MUT};font-size:12px;")
        st.lay.addWidget(self.l_proc_tab)
        self.proc_stack = QStackedWidget()
        st.lay.addWidget(self.proc_stack, 1)

        def tab():
            w_ = QWidget()
            hh = QHBoxLayout(w_)
            hh.setContentsMargins(0, 0, 0, 0)
            hh.setSpacing(28)
            c1, c2 = QVBoxLayout(), QVBoxLayout()
            for c in (c1, c2):
                c.setSpacing(4)
                c.setContentsMargins(0, 0, 0, 0)
            hh.addLayout(c1, 1)
            hh.addLayout(c2, 1)
            self.proc_stack.addWidget(w_)
            return c1, c2
        # Niveau
        c1, c2 = tab()
        self.proc_switch(st, "Volume automatique (AGC)", "agc",
                         "Ramène doucement toutes les sources au même niveau ; se fige dans les silences", lay=c1)
        self.proc_slider(st, "Vitesse de l'AGC", "agc_speed", .3, 6, "%.1f dB/s", tip="Vitesse de remontée du niveau", lay=c1)
        self.proc_slider(st, "Densité", "lm", 1, 10, lambda v: ("naturel" if v < 3.5 else "dense" if v > 7 else "moyen") + f"  {v:.1f}",
                         tip="MOINS ↔ PLUS : plus dense = plus fort et plus régulier, moins dense = plus naturel", lay=c2)
        for c in (c1, c2):
            c.addStretch(1)
        # Couleur (égalisation) : la courbe à gauche, les curseurs à droite
        c1, c2 = tab()
        self.eqc = EQCurve()
        self.eqc.setMinimumHeight(110)
        c1.addWidget(self.eqc, 1)
        self.proc_slider(st, "Coupe-bas", "hpf", 0, 120, lambda v: "aucun" if v < 1 else "%.0f Hz" % v, scale=1,
                         tip="Supprime les très basses fréquences (vent, chocs, ronflements)", lay=c2)
        self.proc_slider(st, "Graves", "bass", -6, 6, "%+.1f dB", tip="Plateau à 90 Hz", lay=c2)
        self.proc_slider(st, "Voix (présence)", "presence", -6, 6, "%+.1f dB", tip="Autour de 3 kHz : voix plus devant", lay=c2)
        self.proc_slider(st, "Brillance (air)", "air", -6, 6, "%+.1f dB", tip="Plateau à 11 kHz", lay=c2)
        self.proc_switch(st, "Émetteur FM : rien au-dessus de 15 kHz", "fm15",
                         "Indispensable pour un émetteur FM (protège le pilote stéréo à 19 kHz)", lay=c2)
        c2.addStretch(1)
        # Compression
        c1, c2 = tab()
        self.proc_switch(st, "Compresseur multibande", "mb_on", lay=c1)
        self.proc_slider(st, "Force", "mb_drive", 0, 15, lambda v: ("légère" if v < 4 else "forte" if v > 9 else "moyenne") + f"  {v:.0f}",
                         tip="Quantité de compression : plus fort = son plus dense et plus égal", lay=c1)
        self.proc_slider(st, "Vitesse", "mb_release", 1, 10, lambda v: ("lente" if v < 4 else "rapide" if v > 7 else "normale"),
                         get=self._rel_get, put=self._rel_put, tip="Vitesse de retour : lente = naturel, rapide = punchy", lay=c1)
        for nm, bands in self.TONE:
            self.proc_slider(st, nm, "mix", -6, 6, "%+.1f dB",
                             get=lambda pp, b=bands: sum(pp["mix"][i] for i in b) / len(b),
                             put=lambda pp, x, b=bands: pp.__setitem__("mix", [x if i in b else v for i, v in enumerate(pp["mix"])]),
                             tip=f"Niveau des {nm.lower()} après compression", lay=c2)
        for c in (c1, c2):
            c.addStretch(1)
        # Stéréo et sortie
        c1, c2 = tab()
        self.proc_slider(st, "Élargisseur", "width", 0, 100, "%.0f %%", scale=1,
                         tip="Élargit l'image stéréo ; le mono reste intact", lay=c1)
        self.proc_switch(st, "Graves en mono (sous 120 Hz)", "bass_mono", "Graves plus fermes, compatibles FM et enceintes mono", lay=c1)
        self.proc_switch(st, "Sortie mono", "mono", lay=c1)
        self.proc_slider(st, "Écrêteur", "clip", 0, 100, "%.0f %%", scale=1,
                         tip="Plus de volume perçu ; 0 pour la musique classique", lay=c2)
        self.proc_slider(st, "Plafond", "ceiling", -3, -0.1, "%.1f dBTP",
                         tip="Aucun échantillon ne dépasse ce niveau, même entre les échantillons (-1 dBTP pour les flux)", lay=c2)
        for c in (c1, c2):
            c.addStretch(1)
        self.seg_proc.changed.connect(self.proc_tab)
        self.proc_tab(int(self.data.get("settings", {}).get("proc_tab", 0) or 0) % len(self.PROC_TABS))
        g.addWidget(st, 2, 0, 1, 3)
        g.setRowStretch(1, 1)
        self.fx_flux_rows()
        self._proc_loading = False
        self.proc_refresh()
        return pg

    def proc_tab(self, k):
        """Onglet de réglages affiché (retenu d'une ouverture à l'autre)."""
        self.proc_stack.setCurrentIndex(k)
        if self.seg_proc.val != k:
            self.seg_proc.setValue(k)
        self.l_proc_tab.setText(self.PROC_TABS[k][1])
        self.data.setdefault("settings", {})["proc_tab"] = k

    def proc_bank(self, b):
        """Affiche (et règle) une autre banque ; ses mesures s'affichent."""
        if b not in BANKS:
            return
        self.proc["edit"] = b
        self.proc_load_widgets()
        self.proc_changed()

    def proc_set_bank(self, params, what):
        self.proc["banks"][self.proc["edit"]] = params
        self.proc_load_widgets()
        self.proc_changed()
        self.log(f"Processeur d'antenne, banque {self.proc['edit']} : {what}" + (" (en direct)." if self.on_air else "."))

    def proc_preset(self, name):
        if name not in PROC_PRESETS:
            return
        p = proc_params(name)
        p["custom"] = False
        self.proc_set_bank(p, f"préréglage « {name} »")

    def proc_zero(self):
        """Réglage à zéro : rien ne colore ni ne compresse, seul le limiteur final (plafond) reste actif."""
        p = proc_params("Protection seule", bass=0.0, presence=0.0, air=0.0, hpf=0, width=0, clip=0, lm=5.0,
                        mix=(0.0, 0.0, 0.0, 0.0, 0.0), makeup=0.0, mono=False, fm15=self.pp().get("fm15", False))
        p["preset"], p["custom"] = "zero", False
        self.proc_set_bank(p, "réglage à zéro")

    def proc_reset(self):
        """Annule les réglages fins : la banque revient à son préréglage (ou au réglage à zéro)."""
        cur = self.pp().get("preset", PROC_DEFAULT)
        if cur == "zero":
            return self.proc_zero()
        self.proc_preset(cur if cur in PROC_PRESETS else PROC_DEFAULT)

    def proc_load_widgets(self):
        self._proc_loading = True
        try:
            for sl, val, fmt, get, scale in self.procw:
                sl.setValue(int(round(get() * scale)))
                val.setText(fmt(get()) if callable(fmt) else fmt % get())
            for w, key in self.procs:
                w.setChecked(bool(self.pp().get(key)))
        finally:
            self._proc_loading = False

    def proc_toggle_bypass(self):
        self.proc["bypass"] = not self.proc.get("bypass")
        self.proc_send()
        self.save_settings()
        self.proc_refresh()
        self.log("Processeur d'antenne : " + ("BYPASS, le son brut part à l'antenne." if self.proc["bypass"] else "remis à l'antenne."))

    def proc_refresh(self):
        pp = self.pp()
        name = pp.get("preset", PROC_DEFAULT)
        custom = bool(pp.get("custom"))
        byp = bool(self.proc.get("bypass"))
        self.set_kind(self.btn_bypass, "○  BYPASS · son brut  (réactiver)" if byp else "●  PROCESSEUR À L'ANTENNE", "stop" if byp else "primary")
        self.btn_bypass.setMinimumWidth(self.btn_bypass.fontMetrics().horizontalAdvance(self.btn_bypass.text()) + 44)
        shown = "Réglage à zéro" if name == "zero" else name
        txt = shown + ("  · modifié" if custom else "")
        self.btn_preset.setText(txt)
        self.btn_preset.setMinimumWidth(self.btn_preset.fontMetrics().horizontalAdvance(txt) + 60)   # (+ flèche du menu)
        self.btn_preset_reset.setEnabled(custom)
        b = self.proc["edit"]
        used = [c.get("name") or "flux" for c in getattr(self, "outputs_cfg", []) if out_bank(c) == b]
        info = ("Aucun réglage, seul le limiteur final." if name == "zero" else PROC_INFO.get(name, ""))
        self.l_preset_info.setText(info + (f"   ·   Banque {b} sur : " + ", ".join(used) if used else f"   ·   Banque {b} : sur aucun flux"))
        self.l_preset_info.set_color(MUT)
        if hasattr(self, "l_proc_set"):
            self.l_proc_set.setText(f"Réglages fins · banque {b}")
        if self.seg_bank.val != BANKS.index(self.proc["edit"]):
            self.seg_bank.setValue(BANKS.index(self.proc["edit"]))
        self.eqc.set(pp)

    def son_tick(self, e):
        """30 fois par seconde, page affichée : vumètres de la banque affichée."""
        if np is None:
            self.proc_meters.set({}, "off")
            return
        pm = getattr(e, "pm", None) if e is not None else None
        st = "idle"
        if pm:
            st = "air" if (self.on_air and e.air) else "input"
        self.proc_meters.set(pm or {}, st)

    FX_LABELS = {**{b: f"Banque {b}" for b in BANKS}, RAW: "Son brut"}

    def fx_flux_rows(self):
        while self.fx_rows.count():
            it = self.fx_rows.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        for c in self.outputs_cfg:
            h = QHBoxLayout()
            w = QWidget()
            w.setLayout(h)
            h.setContentsMargins(0, 0, 0, 0)
            l = CLabel(c["name"], "", False, TXT)
            l.elide = True
            l.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            l.setMinimumWidth(60)
            h.addWidget(l, 1)
            cb = QComboBox()
            cb.addItems(list(self.FX_LABELS.values()))
            cb.setCurrentText(self.FX_LABELS[out_bank(c)])
            cb.activated.connect(lambda _i, cc=c, b=cb: self.fx_flux_set(cc, next(k for k, v in self.FX_LABELS.items() if v == b.currentText())))
            cb.setMinimumWidth(cb.fontMetrics().horizontalAdvance(self.FX_LABELS[RAW]) + 48)
            cb.setToolTip("Banque du processeur pour ce flux, ou son brut (sans traitement)")
            h.addWidget(cb)
            self.fx_rows.addWidget(w)
        if not self.outputs_cfg:
            self.fx_rows.addWidget(lab("Aucun flux pour l'instant : ajoutez-en un dans Diffusion.", "mut", True))
        if hasattr(self, "l_preset_info"):
            self.proc_refresh()

    def fx_flux_set(self, cfg, bank):
        cfg["fx"] = bank
        cfg.pop("fxmode", None)
        self.save_all()
        if self.on_air and self.engine:
            self.engine.set_out_fx({cfg["id"]: bank})
        self.log(f"[{cfg.get('name')}] " + (f"banque {bank} du processeur d'antenne." if bank != RAW else "son brut, sans traitement."))
        self.proc_refresh()


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
