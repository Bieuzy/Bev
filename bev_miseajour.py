# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - mises à jour vues de la fenêtre principale : bulle de Gaël, annonce, mise à jour express, installateur.
Méthodes de la fenêtre principale (MainWindow les reçoit par héritage)."""
from bev_antenne import *  # noqa: F401,F403


class MiseAJourMixin:
    """Partie de MainWindow : mises à jour vues de la fenêtre principale : bulle de Gaël, annonce, mise à jour express, installateur."""

    # ------------------------------------------------------------ mises à jour + bulle de Radiobot
    def update_start(self, manual=False):
        st = self.data.setdefault("settings", {})
        repo = UPDATE_REPO or st.get("update_repo")      # (version empaquetée : toujours le dépôt officiel)
        if not repo:
            if not manual:
                return
            txt, ok = QInputDialog.getText(self, "Mise à jour", "Dépôt GitHub où sont publiées les versions (compte/depot) :\n"
                                           "(rempli automatiquement dans la version téléchargée depuis GitHub)")
            if not ok or not txt.strip():
                return
            repo = txt.strip()
            st["update_repo"] = repo
            self.save_settings()

        def work():
            r = check_update(repo)
            self.ui(self.update_result, r, manual)
        if manual:
            self.log("Recherche de mises à jour…")
        threading.Thread(target=work, daemon=True).start()

    def update_result(self, r, manual):
        first = not getattr(self, "_upd_greeted", False)
        self._upd_greeted = True
        if not r or r.get("error"):
            if manual:
                self.gael_bubble("Je n'ai pas pu vérifier les mises à jour.", (r or {}).get("error") or "Recherche impossible.", hide_after=9000)
            return
        newer = parse_ver(r["tag"]) > parse_ver(VERSION)
        st = express_state()
        if r.get("express") and _ver_tuple(st.get("version")) == _ver_tuple(r["tag"]):
            if int(st.get("fails", 0)) >= 2:          # ce code express n'a pas démarré ici : installateur complet
                r["express"], r["express_why"] = None, "la mise à jour express n'a pas démarré sur cet ordinateur"
            elif os.environ.get("BEV_CODE") not in (None, "", "builtin"):
                newer = False                          # (déjà sur cette version)
            else:
                self._upd_express_ready = r["tag"]     # déjà téléchargée : il ne reste qu'à redémarrer
        if newer:
            if manual or self.upd_bubble is None or getattr(self, "_upd_mode", "") in ("info", "guide"):
                if getattr(self, "upd_pending", None) and getattr(self, "_upd_pending_tag", "") == r["tag"]:
                    return self.update_ready_bubble(r)
                self.update_bubble(r)
        elif (manual or first) and not getattr(self, "_just_updated", False):   # au lancement : Gaël dit bonjour, tout est à jour
            self.gael_bubble("Demat ! Bev est à jour." if not manual else "Bev est à jour.", f"Version {VERSION}", hide_after=6000)

    def gael_bubble(self, title, line="", buttons=(), hide_after=0, mode="info", one_line=False, progress=None):
        """Bulle de BD qui sort de Gaël. buttons : [(texte, type, fonction)]. hide_after : disparaît seule (ms).
        progress : None (pas de barre) ou 0-1 (barre de progression ; -1 = en cours, durée inconnue).
        La bulle a une largeur bornée (le texte passe à la ligne) et reste toujours dans la fenêtre."""
        self.update_bubble_close()
        self._upd_mode = mode
        self.bot_talk = 40
        # menu latéral : la bulle reste dans la colonne de Gaël, au-dessus de lui (la page n'est jamais cachée)
        b = SpeechBubble(self.centralWidget(), tail="top" if NAVTOP else ("bottom" if self.bubble_in_rail() else "left"))
        b.t = lab("", "", True)
        b.t.setStyleSheet("font-weight:800;font-size:13px;")
        b.lay.addWidget(b.t)
        b.l_line = lab("", "mut", True)
        b.l_line.setStyleSheet(f"color:{MUT};font-size:12px;")
        b.lay.addWidget(b.l_line)
        b.bar = UpdBar()
        b.lay.addWidget(b.bar)
        b.btns = QWidget()
        b.btn_l = QVBoxLayout(b.btns) if b.tail == "bottom" else QHBoxLayout(b.btns)     # colonne étroite : boutons empilés
        b.btn_l.setContentsMargins(0, 2, 0, 0)
        b.btn_l.setSpacing(6)
        b.lay.addWidget(b.btns)
        self.upd_bubble = b
        b.bar._off = b.btns._off = True
        self.bubble_set(title, line, buttons or [], progress)
        b.pop()
        if hide_after:
            b.hide_t.timeout.connect(lambda b=b: self.update_bubble_close() if self.upd_bubble is b else None)
            b.hide_t.start(hide_after)
        g = getattr(self.rail, "gael", None)
        if g is not None and g.isVisible():
            try:
                if g.anim is not G_MAJ:
                    g.play(G_HELLO)
                g.say(min(3.0, .9 + len(title) / 30))
            except Exception:
                pass
        return b

    BUBBLE_W = 330

    def bubble_in_rail(self):
        """La bulle peut-elle tenir dans la colonne de Gaël ? (menu latéral déplié, Gaël visible)"""
        g = getattr(self.rail, "gael", None)
        return not NAVTOP and not getattr(self.rail, "compact", False) and g is not None and g.isVisible()

    def bubble_set(self, title=None, line=None, buttons=None, progress="keep"):
        """Fait évoluer la bulle en place (titre, texte, barre, boutons) : pas de clignotement, pas de nouvelle bulle."""
        b = self.upd_bubble
        if b is None:
            return
        cw = self.centralWidget()
        if b.tail == "bottom":
            wmax = self.rail.width() - 12 - 28                    # largeur de la colonne moins les marges de la bulle
            for l in (b.t, b.l_line):
                l.setFixedWidth(wmax)
        else:
            wmax = max(220, min(self.BUBBLE_W, cw.width() - (self.rail.width() if not NAVTOP else 0) - 40))
            for l in (b.t, b.l_line):
                l.setMaximumWidth(wmax)
                l.setMinimumWidth(min(wmax, 230))
        if title is not None:
            b.t.setText(title)
        anim = b.anim.state() == QVariantAnimation.State.Running

        def vis(w, on):
            w._off = not on
            if not anim:
                w.setVisible(on)
        if line is not None:
            b.l_line.setText(line)
            vis(b.l_line, bool(line))
        if progress != "keep":
            vis(b.bar, progress is not None)
            if progress is not None:
                b.bar.set(progress)
        if buttons is not None:
            while b.btn_l.count():
                it = b.btn_l.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            for txt, kind, fn in buttons:
                bt = btn(txt, kind, fn)
                bt.setMinimumHeight(30)
                if b.tail == "bottom":
                    bt.setMinimumWidth(0)
                    bt.setStyleSheet("font-size:12px;padding:4px 8px;")
                b.btn_l.addWidget(bt)
            if b.tail != "bottom":
                b.btn_l.addStretch(1)
            vis(b.btns, bool(buttons))
        b.lay.activate()
        b.adjustSize()
        self.place_upd_bubble()

    def place_upd_bubble(self):
        b = getattr(self, "upd_bubble", None)
        if b is None:
            return
        b.adjustSize()
        cw = self.centralWidget()
        W, H = cw.width(), cw.height()
        if b.tail == "bottom":                                   # dans la colonne de Gaël, juste au-dessus de sa tête
            g = getattr(self.rail, "gael", None)
            bw = self.rail.width() - 12
            b.setFixedWidth(bw)
            b.adjustSize()
            if g is not None and g.isVisible():
                hp = g.mapTo(cw, g.head_point())
                hp = QPointF(min(max(hp.x() - 22, 30), bw - 24), hp.y() - 40)
            else:
                hp = QPointF(bw / 2, H - 8)
            x = 6
            y = int(max(8, hp.y() - b.height()))
            b.move(x, y)
            b.tip = QPointF(hp.x() - x, min(hp.y() - y, b.height() - 1))
            b.raise_()
            b.update()
            return
        if NAVTOP:
            bb = self.bot_btn
            if bb is not None and bb.isVisible():
                c = bb.mapTo(cw, QPointF(bb.width() / 2, bb.height() - 4))
            else:
                c = QPointF(W - 40, TopNav.H - 4)
            x = int(max(8, min(c.x() - b.width() + 46, W - b.width() - 8)))
            y = int(min(c.y() + 6, H - b.height() - 8))
            b.move(x, y)
            b.tip = QPointF(c.x() - x, 0)
        else:
            g = getattr(self.rail, "gael", None)
            if g is not None and g.isVisible():                  # la pointe touche la tête de Gaël
                hp = g.mapTo(cw, g.head_point())
            else:                                                # Gaël caché (fenêtre basse) : la bulle part du bas du menu
                hp = QPointF(self.rail.width() - 8, H - 60)
            x = int(min(hp.x() + 4, W - b.width() - 8))
            y = int(max(8, min(hp.y() - b.height() * .55, H - b.height() - 8)))
            b.move(x, y)
            b.tip = QPointF(hp.x() - x, hp.y() - y)
        b.raise_()
        b.update()

    def gael_maj(self, state=None, k=None):
        """Animation de mise à jour de Gaël (colis, carton, saut de joie) ; state=None : arrêt."""
        g = getattr(self.rail, "gael", None)
        if g is None:
            return
        if state is None:
            if g.anim is G_MAJ:
                g.anim = None
                g.update()
            return
        G_MAJ.set(state, k)
        if g.anim is not G_MAJ:
            G_MAJ.k = 0.0 if k is None else G_MAJ.k
            g.play(G_MAJ)

    # ------------------------------------------------------------ mise à jour : annonce
    def upd_title(self, r):
        """« 1.1.0 → 1.1.1 » suivi du titre de la version s'il apporte quelque chose (« Processeur d'antenne »)."""
        new = r.get("tag", "").lstrip("vV")
        t = re.sub(r"(?i)^\s*bev\s*", "", r.get("title", "")).strip()
        t = re.sub(r"(?i)^v?\d+(\.\d+)*\s*", "", t).strip(" ·:-–")
        t = re.sub(r"(?i)\b(available|disponible)\b", "", t).strip(" ·:-–")
        return f"{VERSION}  →  {new}" + (f"  ·  {t}" if t else "")

    def express_settle(self):
        """Bev tourne depuis 20 s sur le code express : il a bien démarré (le compteur de démarrages ratés repart à zéro)."""
        code = os.environ.get("BEV_CODE")
        if code and code != "builtin":
            st = express_state()
            if st.get("fails"):
                express_state({"fails": 0})

    def after_update_greet(self):
        """Premier lancement après une mise à jour : Gaël l'annonce, avec un accès direct aux nouveautés."""
        if SECRETS_LOST:
            self.log("Mots de passe illisibles (réglages venus d'un autre ordinateur ou compte Windows) : à ressaisir pour "
                     + ", ".join(SECRETS_LOST[:6]))
        S = self.data.setdefault("settings", {})
        seen = S.get("seen_version")
        S["seen_version"] = VERSION
        self.save_settings()
        if not seen or parse_ver(seen) >= parse_ver(VERSION):
            return
        self._just_updated = True
        self.log(f"Bev est passé de la version {seen} à la version {VERSION}.")
        self.gael_maj("done")
        self.gael_bubble(f"Bev est passé en {VERSION} !", f"Mise à jour réussie (tu avais la {seen}). Tes réglages sont tous là.",
                         [("Voir les nouveautés", "primary", lambda: (self.close_maj(), self.go_tab("about"))), ("OK", "", self.close_maj)],
                         hide_after=20000, mode="info")
        QTimer.singleShot(3500, lambda: self.gael_maj(None) if self._upd_mode != "dl" else None)

    def update_bubble(self, r):
        """Nouvelle version : ce qu'elle apporte (titre), comment elle s'installe (express ou complète), et 3 boutons."""
        self.upd_info = r
        new = r.get("tag", "").lstrip("vV")
        ex = r.get("express")
        news = ("Nouveautés", "", lambda: self.news_dialog(r))
        later = ("Plus tard", "", self.update_bubble_close)
        if ex:
            line = (f"{self.upd_title(r)}\nMise à jour express : {fmt_size(ex['size'])}, sans installateur ni droits "
                    "administrateur. Tes réglages, playlists et cartouches restent en place.")
            btns = [("Mettre à jour", "primary", lambda: self.express_install(r)), news, later]
        elif SYS == "Windows" and "setup" in str(r.get("asset_name", "")).lower() and installed_copy():
            line = (f"{self.upd_title(r)}\nCette version renouvelle les bibliothèques de Bev : elle passe par "
                    f"l'installateur complet ({fmt_size(r.get('size', 0))}).")
            btns = [("Télécharger et installer", "primary", lambda: self.full_install(r)), news, later]
        else:
            line = f"{self.upd_title(r)}\nTélécharge la nouvelle version depuis la page des versions."
            btns = [("Télécharger", "primary", lambda: (self.update_bubble_close(), webbrowser.open(r.get("asset") or r["url"]))),
                    news, later]
        self.gael_bubble(f"Bev {new} est disponible !", line, btns, mode="new")

    def update_ready_bubble(self, r):
        """Mise à jour déjà téléchargée (express ou installateur) : on rappelle simplement comment l'appliquer."""
        if getattr(self, "_upd_express_ready", "") == r.get("tag"):
            return self.express_ready(r)
        self.gael_maj("done")
        self.gael_bubble("Mise à jour prête ✓", "Elle s'installera quand tu fermeras Bev : le direct n'est pas coupé.",
                         [("OK", "", self.update_bubble_close)], hide_after=12000, mode="ready")

    def news_dialog(self, r=None):
        """Nouveautés d'une version (notes de la Release GitHub), dans une fenêtre lisible."""
        notes = (r or {}).get("notes") or NEWS.get(VERSION, "")
        ver = ((r or {}).get("tag") or VERSION).lstrip("vV")
        d = QDialog(self)
        d.setWindowTitle(f"Nouveautés de Bev {ver}")
        d.resize(620, 560)
        v = QVBoxLayout(d)
        tx = QTextEdit()
        tx.setReadOnly(True)
        tx.setHtml(md_html(notes) or "<p>Pas de notes pour cette version.</p>")
        v.addWidget(tx, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        d.exec()

    # ------------------------------------------------------------ mise à jour express (code seul, ~1 Mo)
    def express_install(self, r):
        ex = r.get("express") or {}
        new = r.get("tag", "").lstrip("vV")
        self.gael_maj("dl", 0.0)
        self.gael_bubble(f"Je récupère Bev {new}…", f"0 Ko sur {fmt_size(ex.get('size', 0))}", progress=0.0, mode="dl")
        dst = os.path.join(UPD_DIR, ex["file"])

        def prog(got, total):
            if self._upd_mode != "dl" or self.upd_bubble is None:
                return
            k = got / total if total else -1
            self.gael_maj("dl", max(0.0, k))
            self.bubble_set(line=f"{fmt_size(got)} sur {fmt_size(total)}" if total else fmt_size(got), progress=k)

        def work():
            res = {}
            try:
                os.makedirs(UPD_DIR, exist_ok=True)
                data, sha = download(ex["url"], dst + ".part", lambda g, t: self.ui(prog, g, t), size=ex.get("size", 0))
                if sha != ex["sha256"]:
                    raise RuntimeError("le fichier reçu est abîmé (empreinte différente) : rien n'a été changé")
                with open(dst + ".part", "rb") as fh:
                    compile(fh.read(), dst, "exec")         # code lisible par ce Bev (sinon : on ne l'active pas)
                os.replace(dst + ".part", dst)
                express_state({"version": ex["version"], "runtime": RUNTIME, "file": ex["file"], "sha256": ex["sha256"],
                               "fails": 0, "from": VERSION, "notes": (r.get("notes") or "")[:20000]})
                # anciens codes express : supprimés, SAUF celui qui tourne en ce moment. Le moteur audio est relancé avec ce
                # même fichier (BEV_CODE) s'il redémarre avant Bev : effacé, il repartait sur la version installée, plus
                # ancienne, différente de l'interface (antenne en panne jusqu'au redémarrage de Bev).
                busy = os.path.basename(os.environ.get("BEV_CODE") or "")
                for f in os.listdir(UPD_DIR):
                    if f.startswith("bev-") and f.endswith(".py") and f not in (ex["file"], busy):
                        try:
                            os.remove(os.path.join(UPD_DIR, f))
                        except OSError:
                            pass
                res["ok"] = True
            except Exception as e:
                res["err"] = friendly_dl_error(e)
                try:
                    os.remove(dst + ".part")
                except OSError:
                    pass
            self.ui(self.express_done, r, res)
        threading.Thread(target=work, daemon=True).start()

    def express_done(self, r, res):
        new = r.get("tag", "").lstrip("vV")
        if not res.get("ok"):
            self.gael_maj("err")
            self.log(f"Mise à jour express {new} impossible : {res.get('err')}")
            btns = [("Réessayer", "primary", lambda: self.express_install(r))]
            if SYS == "Windows" and "setup" in str(r.get("asset_name", "")).lower() and installed_copy():
                btns.append(("Installateur complet", "", lambda: self.full_install(r)))
            self.gael_bubble("Le téléchargement n'a pas abouti.", f"{res.get('err')}\nRien n'a changé : Bev continue normalement.",
                             btns + [("Fermer", "", self.close_maj)], mode="err")
            return
        self._upd_express_ready = r.get("tag")
        self.log(f"Mise à jour express {new} téléchargée et vérifiée.")
        self.express_ready(r)

    def express_ready(self, r):
        new = r.get("tag", "").lstrip("vV")
        self.gael_maj("done")
        if self.on_air:
            self.gael_bubble(f"Bev {new} est prêt ✓", "Il s'appliquera au prochain démarrage de Bev : le direct n'est pas touché.",
                             [("Parfait", "primary", self.close_maj)], mode="ready")
        else:
            self.gael_bubble(f"Bev {new} est prêt ✓", "Il ne reste qu'à redémarrer Bev : quelques secondes, et tout est "
                             "conservé (réglages, playlists, cartouches).",
                             [("Redémarrer maintenant", "primary", self.express_restart), ("Au prochain lancement", "", self.close_maj)],
                             mode="ready")

    def express_restart(self):
        if self.on_air:
            return self.express_ready(self.upd_info or {})
        self.gael_maj("restart")
        self.bubble_set(title="À tout de suite !", line="Bev redémarre dans sa nouvelle version…", buttons=[], progress=-1)
        self.log("Redémarrage sur la nouvelle version (mise à jour express).")

        def go():
            try:
                self.save_all()
            except Exception as _ex:
                trace("go", _ex)
            relaunch_self(fresh=True)
            self._closing = True
            self.close()
        QTimer.singleShot(900, go)

    def close_maj(self):
        self.gael_maj(None)
        self.update_bubble_close()

    # ------------------------------------------------------------ installateur complet (quand le socle change)
    def full_install(self, r):
        url = r.get("asset") or ""
        if not url:
            return webbrowser.open(r.get("url") or "")
        new = r.get("tag", "").lstrip("vV")
        # dans le dossier de Bev (et non le dossier temporaire de Windows) : un programme qui dépose un .exe dans %TEMP% puis
        # le lance, c'est exactement ce que guettent Defender et les antivirus, d'où des suppressions « pour virus »
        dst = os.path.join(UPD_DIR, os.path.basename(r.get("asset_name") or "Bev-Setup.exe"))
        self.gael_maj("dl", 0.0)
        self.gael_bubble(f"Je télécharge l'installateur de Bev {new}…", "Préparation…", progress=0.0, mode="dl")
        t0 = time.time()

        def prog(got, total):
            if self._upd_mode != "dl" or self.upd_bubble is None:
                return
            k = got / total if total else -1
            el = max(.5, time.time() - t0)
            sp = got / el
            rest = (total - got) / sp if (total and sp > 0) else 0
            eta = f"  ·  encore {int(rest // 60)} min {int(rest % 60):02d} s" if rest >= 60 else (f"  ·  encore {int(rest)} s" if rest >= 2 else "")
            self.gael_maj("dl", max(0.0, k))
            self.bubble_set(line=f"{fmt_size(got)} sur {fmt_size(total)}  ·  {fmt_size(sp)}/s{eta}" if total else fmt_size(got),
                            progress=k)

        def work():
            res = {}
            try:
                os.makedirs(UPD_DIR, exist_ok=True)
                _, sha = download(url, dst + ".part", lambda g, t: self.ui(prog, g, t), size=r.get("size", 0))
                dg = r.get("digest", "")
                if dg.startswith("sha256:") and dg[7:].lower() != sha:
                    raise RuntimeError("le fichier reçu est abîmé (empreinte différente)")
                want = r.get("installer_sha256", "")
                if UPDATE_PUBKEY and want != sha:
                    raise RuntimeError("l'installateur reçu ne correspond pas à la version signée par l'auteur : rien n'a été lancé")
                if os.path.exists(dst):
                    os.remove(dst)
                os.replace(dst + ".part", dst)
                if UPDATE_PUBKEY:                         # installateur vérifié par signature : la marque « téléchargé
                    try:                                  # d'Internet » est retirée ; sinon Windows garde son contrôle
                        os.remove(dst + ":Zone.Identifier")
                    except OSError:
                        pass
                # Defender analyse le fichier juste après son enregistrement et peut le supprimer quelques secondes plus
                # tard : on vérifie qu'il est toujours là (et lisible) avant d'annoncer « Installateur prêt »
                time.sleep(2.0)
                with open(dst, "rb") as fh:
                    fh.read(4096)
                res["ok"] = True
            except FileNotFoundError:
                res["err"], res["av"] = AV_GONE, True
            except Exception as e:
                res["err"] = friendly_dl_error(e)
                res["av"] = res["err"] == AV_GONE
            if not res.get("ok"):
                try:
                    os.remove(dst + ".part")
                except OSError:
                    pass
            self.ui(self.full_downloaded, r, dst, res)
        threading.Thread(target=work, daemon=True).start()

    def full_downloaded(self, r, dst, res):
        new = r.get("tag", "").lstrip("vV")
        if not res.get("ok"):
            self.gael_maj("err")
            self.log(f"Installateur de Bev {new} : {res.get('err')}")
            if res.get("av"):                     # réessayer ne servirait à rien : Defender le supprimerait encore
                return self.full_blocked(res["err"], "av")
            self.gael_bubble("Le téléchargement n'a pas abouti.", f"{res.get('err')}\nRien n'a changé : Bev continue normalement.",
                             [("Réessayer", "primary", lambda: self.full_install(r)),
                              ("Page des versions", "", lambda: (self.close_maj(), webbrowser.open(r.get("url") or "")))], mode="err")
            return
        self.upd_pending, self._upd_pending_tag = dst, r.get("tag", "")
        self.gael_maj("done")
        if self.on_air:
            self.log(f"Installateur de Bev {new} prêt : il s'installera à la fermeture de Bev.")
            self.gael_bubble("Installateur prêt ✓", "Il s'installera quand tu fermeras Bev : le direct n'est pas coupé.",
                             [("Parfait", "primary", self.close_maj)], mode="ready")
            return
        self.gael_bubble("Installateur prêt ✓", f"L'installateur de Bev {new} va s'ouvrir et Bev se fermera : suis ses "
                         "étapes (Suivant, Installer). Tes réglages sont conservés.",
                         [("Installer maintenant", "primary", self.full_launch_now), ("À la fermeture de Bev", "", self.close_maj)],
                         mode="ready")

    def full_launch_now(self):
        """Lance l'installateur, et ne ferme Bev que lorsqu'il a vraiment démarré : si Windows (Smart App Control,
        SmartScreen) ou un antivirus le bloque, Bev reste ouvert et explique quoi faire, au lieu de disparaître."""
        self.bubble_set(title="Ouverture de l'installateur…", line="Si Windows demande une confirmation, accepte-la.", buttons=[], progress=-1)
        p, why = self.update_launch(relaunch=True)
        if p is None:
            return self.full_blocked(why, getattr(self, "_upd_block", ""))

        def check(n=0):
            rc = p.poll()
            if rc is None and n < 6:
                return QTimer.singleShot(400, lambda: check(n + 1))
            if rc not in (None, 0):
                return self.full_blocked(f"l'installateur s'est arrêté tout de suite (code {rc})")
            self.log("Installateur de la mise à jour ouvert : Bev se ferme pour le laisser faire.")
            self._closing = True
            self.close()
        QTimer.singleShot(400, check)

    def full_blocked(self, why, kind=""):
        """L'installateur n'a pas pu s'ouvrir. kind : "sac" (Smart App Control), "av" (Defender / antivirus), "policy"
        (stratégie de l'ordinateur) ou "" (autre). Dans les trois premiers cas, Windows refusera de nouveau : on ne
        réessaie PAS à la fermeture de Bev (avant, chaque fermeture redéclenchait le blocage) et on explique quoi faire."""
        self.gael_maj("err")
        self.upd_pending = None if kind in ("sac", "av", "policy") else getattr(self, "_upd_last_dst", None)
        self.log(f"Mise à jour bloquée : {why}")
        r = self.upd_info or {}
        page = ("Page des versions", "", lambda: (self.close_maj(), webbrowser.open(r.get("url") or "")))
        fermer = ("Fermer", "", self.close_maj)
        if kind == "sac":
            line = ("Smart App Control n'accepte que les programmes signés, et l'installateur de Bev ne l'est pas encore. "
                    "Bev continue normalement dans sa version actuelle ; les prochaines mises à jour passeront en express, "
                    "sans installateur. Le mieux est d'attendre une version signée plutôt que de désactiver Smart App Control (avant "
                    "Windows 11 25H2, il ne peut plus être réactivé ensuite).")
            btns = [page, fermer]
        elif kind == "av":
            line = ("C'est une fausse alerte, fréquente pour les logiciels libres non signés. Bev continue normalement. "
                    "Pour installer quand même : Sécurité Windows > Protection contre les virus et menaces > Historique de "
                    "protection > Autoriser, puis télécharge l'installateur depuis la page des versions.")
            btns = [page, fermer]
        elif kind == "policy":
            line = ("Une règle de cet ordinateur (gérée par l'informatique de la structure) interdit les programmes non "
                    "signés. Bev continue normalement ; demande à la personne qui gère l'ordinateur d'installer la mise à jour.")
            btns = [page, fermer]
        else:
            line = ("Rien n'a changé : Bev continue normalement. Ouvre le dossier et double-clique sur l'installateur "
                    "(Windows peut proposer « Exécuter quand même »), ou installe depuis la page des versions.")
            btns = [("Ouvrir le dossier", "primary", self.open_installer_folder), page, fermer]
        self.gael_bubble(why[:1].upper() + why[1:] + ".", line, btns, mode="err")

    def open_installer_folder(self):
        """Montre l'installateur téléchargé dans l'Explorateur : un double-clic le lance (Windows peut alors proposer
        « Exécuter quand même »)."""
        dst = getattr(self, "_upd_last_dst", None)
        self.close_maj()
        try:
            if dst and os.path.isfile(dst) and SYS == "Windows":
                subprocess.Popen(["explorer", "/select,", os.path.normpath(dst)])
            elif dst:
                webbrowser.open("file://" + os.path.dirname(dst))
        except Exception as ex:
            self.log(f"Ouverture du dossier impossible : {ex}")

    def update_launch(self, relaunch):
        """Lance l'installateur téléchargé NORMALEMENT (assistant d'installation visible, comme un double-clic) : c'est le
        plus sûr, Windows peut poser ses questions et l'on voit ce qui se passe. Bev se rouvre via la case « Lancer Bev »
        de fin d'installation. Renvoie (processus, None) ou (None, raison)."""
        dst = getattr(self, "upd_pending", None)
        self._upd_block = ""
        if not dst or not os.path.isfile(dst):
            self.upd_pending = None
            if dst:                                   # téléchargé, puis disparu : Defender l'a mis en quarantaine
                self._upd_block = "av"
                return None, AV_GONE
            return None, "installateur introuvable"
        self._upd_last_dst = dst
        try:
            kw = {"creationflags": 0x00000008 | 0x00000200} if SYS == "Windows" else {}
            args = [dst, "/LOG=" + os.path.join(os.path.dirname(dst), "Bev-mise-a-jour.log")]
            env = clean_env(True)
            env.pop("BEV_CODE", None)
            p = subprocess.Popen(args, env=env, close_fds=True, **kw)
            self.upd_pending = None
            return p, None
        except OSError as ex:
            w = getattr(ex, "winerror", None)
            why = {4551: "Smart App Control (Windows) a bloqué l'installateur", 1260: "une stratégie de Windows bloque l'installateur",
                   225: AV_GONE, 226: AV_GONE, 5: "Windows a refusé l'accès à l'installateur"}.get(w, f"lancement impossible ({ex})")
            self._upd_block = {4551: "sac", 1260: "policy", 225: "av", 226: "av"}.get(w, "")
            self.log(f"Impossible de lancer la mise à jour : {ex}")
            return None, why
        except Exception as ex:
            self.log(f"Impossible de lancer la mise à jour : {ex}")
            return None, f"lancement impossible ({ex})"

    def update_bubble_close(self):
        if self.upd_bubble is not None:
            self.upd_bubble.hide()
            self.upd_bubble.deleteLater()
            self.upd_bubble = None
        self._upd_mode = ""


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
