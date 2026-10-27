# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - première prise en main (« Prêt pour l'antenne ? », guide de Gaël au premier lancement) et support
(rapport « Signaler un problème », erreurs internes et plantages). Méthodes de la fenêtre principale (SupportMixin)."""
from bev_miseajour import *  # noqa: F401,F403

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

SUPPORT_REPO = "Bieuzy/Bev"            # dépôt où arrivent les signalements (si UPDATE_REPO n'est pas renseigné)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<![\d.:])(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}(?!\d)")
_HOOK_RE = re.compile(r"https?://\S*(?:discord(?:app)?\.com/api/webhooks|hooks\.slack\.com|ntfy\.sh)/\S*", re.I)


def scrub(text):
    """Texte destiné au support : mots de passe, adresses mail, numéros de téléphone, liens d'alerte et nom du compte
    Windows (dans les chemins de fichiers) sont retirés."""
    t = redact(str(text))
    t = _HOOK_RE.sub("[lien d'alerte retiré]", t)
    t = _EMAIL_RE.sub("[adresse mail retirée]", t)
    t = _PHONE_RE.sub("[numéro retiré]", t)
    home = os.path.expanduser("~")
    if len(home) > 3:
        t = t.replace(home, "~").replace(home.replace("\\", "/"), "~")
    return t


def tail_file(path, n=200, maxc=60000):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read()[-maxc * 2:].splitlines()
        return "\n".join(lines[-n:])[-maxc:]
    except OSError:
        return ""


def settings_summary(data):
    """Réglages utiles au support, SANS rien de personnel : flux (type, serveur, format…), playlist de secours (nombre de
    titres), options générales. Ni mot de passe, ni clé, ni adresse mail, ni numéro, ni lien d'alerte."""
    out = []
    prof = (data.get("profiles") or {}).get(data.get("last")) or {}
    out.append(f"Profil : {data.get('last')} ({len(data.get('profiles') or {})} profil(s))")
    src = (prof.get("source") or {}).get("device") or "(aucune)"
    out.append(f"Entrée audio : {src}")
    for o in prof.get("outputs") or []:
        t = o.get("type")
        bits = [f"{t}", f"« {o.get('name')} »", "actif" if o.get("enabled", True) else "désactivé"]
        if t == "internet":
            bits += [o.get("protocol", ""), f"{o.get('host')}:{o.get('port')}{o.get('mount', '') if o.get('protocol') == 'Icecast' else ''}",
                     f"{o.get('format')} {o.get('bitrate')}k", "TLS" if o.get("tls") else "",
                     "mot de passe renseigné" if o.get("password") else "MOT DE PASSE VIDE"]
        elif t == "fm":
            bits += [f"carte : {o.get('device') or '?'}", "RDS" if o.get("rds") else ""]
        elif t == "dab":
            bits += [o.get("mode", ""), o.get("profile", ""), f"{o.get('bitrate')}k"]
        elif t == "record":
            bits += [o.get("format", ""), f"rotation {o.get('rotate')} min", f"garder {o.get('keep_days')} j"]
        bits.append(f"traitement : {o.get('processing', 'Aucun')}")
        out.append("Flux : " + " · ".join(b for b in bits if b))
    if not prof.get("outputs"):
        out.append("Flux : aucun")
    fb = prof.get("fallback") or {}
    pl = fb.get("playlist") or []
    out.append(f"Playlist de secours : {'activée' if fb.get('enabled') else 'désactivée'}, {len(pl)} titre(s), "
               f"seuil {fb.get('threshold')} dB, délai {fb.get('silence_s')} s")
    S = data.get("settings") or {}
    keep = ("mini", "perf", "theme", "mood", "nav", "look_v", "engine_proc", "resume_crash", "keep_awake", "topmost", "update_check",
            "daily_log", "gael_ai", "disk_warn", "panic_key", "mute_windows")
    opts = [f"{k}={S.get(k)}" for k in keep if k in S] + ([f"autostart={data.get('autostart')}"] if data.get("autostart") else [])
    out.append("Réglages : " + (", ".join(opts) if opts else "par défaut"))
    al = data.get("alerts") or {}
    ch = [n for n, on in (("mail", al.get("mail_on")), ("SMS", al.get("sms_on")), ("message", bool(al.get("url")))) if on]
    out.append("Alertes : " + (", ".join(ch) if ch else "aucune"))
    auto = data.get("automate") or {}
    out.append(f"Automate : {'relié' if auto.get('on') else 'non relié'}" + (" (réseau local)" if auto.get("lan") else ""))
    return "\n".join(scrub(x) for x in out)


class SupportMixin:
    """Partie de MainWindow : première prise en main et support."""

    # ------------------------------------------------------------ sons de Windows
    def set_mute_windows(self, on):
        self.set_val("mute_windows", bool(on))
        if on:
            ok = win_sounds_mute()
            self.log("Sons de Windows coupés (ils reviennent à la fermeture de Bev)." if ok else
                     "Impossible de couper les sons de Windows (voir le rapport de support).")
        elif win_sounds_restore():
            self.log("Sons de Windows rétablis.")

    def sounds_boot(self):
        """Au lancement : sons coupés si l'option est cochée ; sinon, s'ils étaient restés coupés (Bev fermé brutalement),
        ils sont rétablis."""
        if self.data.get("settings", {}).get("mute_windows"):
            if win_sounds_mute():
                self.log("Sons de Windows coupés pendant que Bev est ouvert.")
        elif win_sounds_restore():
            self.log("Sons de Windows rétablis (ils étaient restés coupés après une fermeture brutale).")

    # ------------------------------------------------------------ « Prêt pour l'antenne ? »
    def readiness(self, prof=None):
        """Ce qui manque pour partir à l'antenne. Liste de (niveau, clé, texte, bouton, action) ; niveau « bloque » (on ne
        peut pas démarrer) ou « conseil » (on peut démarrer quand même)."""
        prof = prof or self.collect_profile()
        R = []
        if not shutil.which("ffmpeg"):
            R.append(("bloque", "ffmpeg", "ffmpeg est introuvable : Bev ne peut rien encoder.", "Voir SOS", lambda: self.go_tab("sos")))
        dev = (prof["source"].get("device") or "").strip()
        if not dev:
            R.append(("bloque", "entree", "Aucune entrée audio choisie : rien ne serait diffusé.", "Choisir l'entrée", self.fix_input))
        else:
            known = set(getattr(self, "dev_map", {}).values())
            if known and dev not in known and not dev.startswith("lavfi:"):
                R.append(("conseil", "entree-absente", f"L'entrée « {dev_short_name(dev)} » n'existe pas sur cet ordinateur "
                          "(ou elle est débranchée) : les flux partiraient en silence.", "Choisir l'entrée", self.fix_input))
        outs = [o for o in prof["outputs"] if o.get("enabled", True)]
        if not outs:
            R.append(("bloque", "flux", "Aucun flux actif : il faut au moins une destination (serveur Internet, FM, DAB+ "
                      "ou enregistrement).", "Ajouter un flux Internet", lambda: self.fix_flux(None)))
        for o in outs:
            if o["type"] == "internet" and not o.get("password"):
                R.append(("bloque", "mdp", f"Le flux « {o['name']} » n'a pas de mot de passe source.", "Le renseigner",
                          lambda o=o: self.fix_flux(o["id"])))
        fb = prof["fallback"]
        titles = [f for f in fb["playlist"] if f not in set(fb.get("off") or [])]
        if fb["enabled"] and not titles:
            R.append(("bloque", "secours-vide", "La playlist de secours est activée mais vide : en cas de silence, rien ne "
                      "prendrait le relais.", "Ajouter des titres", self.fix_fallback))
        elif not fb["enabled"]:
            R.append(("conseil", "secours-off", "La playlist de secours est désactivée : si le son s'arrête, l'antenne reste "
                      "muette jusqu'à ce que quelqu'un s'en aperçoive.", "L'activer", self.fix_fallback))
        return R

    def fix_input(self):
        self.go_tab("diff")
        QTimer.singleShot(150, self.dev_pick.popup)

    def fix_flux(self, oid):
        self.go_tab("diff")
        if oid is None:
            QTimer.singleShot(100, lambda: self.add_output("internet"))
        else:
            self.select_output_id(oid)
            QTimer.singleShot(100, self.edit_output)

    def fix_fallback(self):
        self.go_tab("diff")
        if not self.sw_fb.isChecked():
            self.sw_fb.setChecked(True)
        if not [f for f in self.playlist if f not in self.pl_off]:
            QTimer.singleShot(100, self.pl_add)

    def ready_check(self, ask=True):
        """Avant « Démarrer » : True si on peut partir. Les points bloquants sont tous montrés ensemble (au lieu d'un
        message à la fois) avec de quoi les régler ; les conseils peuvent être ignorés, ou ne plus être montrés.
        ask=False (démarrage automatique, reprise après plantage) : seuls les points bloquants arrêtent, sans conseil."""
        R = self.readiness()
        S = self.data.setdefault("settings", {})
        muted = set(S.get("ready_muted") or [])
        block = [r for r in R if r[0] == "bloque"]
        advice = [r for r in R if r[0] == "conseil" and (r[1] not in muted or r[1] == "entree-absente")]
        if not ask:
            if block:
                self.log("Démarrage automatique impossible : " + " ; ".join(r[2] for r in block))
            return not block
        if not block and not advice:
            return True
        d = QDialog(self)
        d.setWindowTitle("Prêt pour l'antenne ?")
        v = QVBoxLayout(d)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(12)
        v.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)    # (textes sur plusieurs lignes : hauteur exacte)
        t = lab("Il manque quelque chose avant de démarrer" if block else "Avant de démarrer", "")
        t.setStyleSheet("font-size:18px;font-weight:700;")
        v.addWidget(t)
        res = {"go": False}
        for lvl, key, text, blabel, fn in block + advice:
            row = QHBoxLayout()
            row.setSpacing(10)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{BADC if lvl == 'bloque' else ACC2};font-size:14px;")
            dot.setAlignment(Qt.AlignmentFlag.AlignTop)
            dot.setFixedWidth(14)
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            tl = lab(text, "", True)
            tl.setFixedWidth(380)
            tl.setMinimumHeight(tl.heightForWidth(380))
            row.addWidget(tl, 0, Qt.AlignmentFlag.AlignTop)
            row.addStretch(1)
            row.addWidget(btn(blabel, "", lambda fn=fn: (d.reject(), QTimer.singleShot(0, fn))), 0, Qt.AlignmentFlag.AlignTop)
            v.addLayout(row)
        cb = None
        if advice and any(r[1] != "entree-absente" for r in advice):
            cb = QCheckBox("Ne plus me donner ces conseils")
            v.addWidget(cb)
        h = QHBoxLayout()
        h.addStretch(1)
        h.addWidget(btn("Annuler", "", d.reject))
        if not block:
            h.addWidget(btn("Démarrer quand même", "primary", lambda: (res.__setitem__("go", True), d.accept())))
        v.addLayout(h)
        d.exec()
        if cb is not None and cb.isChecked():
            S["ready_muted"] = sorted(muted | {r[1] for r in advice if r[1] != "entree-absente"})
            self.save_settings()
        return res["go"]

    # ------------------------------------------------------------ guide du premier lancement (bulle de Gaël)
    GUIDE = {"entree": ("Prochaine étape : l'entrée audio", "Choisis ce que Bev doit diffuser : la table de mixage, un micro, "
                        "ou le son de l'ordinateur."),
             "flux": ("Prochaine étape : un flux", "Ajoute la destination de l'antenne : le serveur Internet de la radio "
                      "(adresse, port, mot de passe source), l'émetteur FM, le DAB+ ou un enregistrement."),
             "mdp": ("Il manque un mot de passe", "Le flux Internet a besoin du mot de passe SOURCE du serveur."),
             "secours-vide": ("Prochaine étape : la playlist de secours", "Ajoute quelques titres : si le son s'arrête, "
                              "ils prennent le relais tout seuls."),
             "secours-off": ("Prochaine étape : la playlist de secours", "Active-la et ajoute quelques titres : si le son "
                             "s'arrête, ils prennent le relais tout seuls.")}

    def guide_start(self):
        """Premier lancement : Gaël indique l'étape suivante (entrée, flux, secours) jusqu'à ce que tout soit prêt. Rien si
        Bev est déjà configuré (radio existante, réglages importés) ou si on a choisi de ne plus le voir."""
        S = self.data.setdefault("settings", {})
        if S.get("guide_done") or self._closing:
            return
        if any(o for o in self.outputs_cfg) and self.playlist:          # déjà configuré : pas de guide
            S["guide_done"] = True
            self.save_settings()
            return
        self._guide_on = True
        self._guide_key = None
        self.guide_tick()
        tm = self._guide_tm = QTimer(self)
        tm.timeout.connect(self.guide_tick)
        tm.start(1500)

    def guide_stop(self, done=False):
        self._guide_on = False
        tm = getattr(self, "_guide_tm", None)
        if tm is not None:
            tm.stop()
        if getattr(self, "_upd_mode", "") == "guide":
            self.update_bubble_close()
        if done:
            self.data.setdefault("settings", {})["guide_done"] = True
            self.save_settings()

    def guide_tick(self):
        if not getattr(self, "_guide_on", False):
            return
        if self.on_air:                                   # l'antenne est partie : le guide a fini son travail
            return self.guide_stop(done=True)
        b = getattr(self, "upd_bubble", None)
        if b is not None and getattr(self, "_upd_mode", "") != "guide":
            return                                        # une autre bulle (mise à jour…) est affichée : on attend
        todo = [r for r in self.readiness() if r[1] in self.GUIDE]
        key = todo[0][1] if todo else "pret"
        if key == self._guide_key and b is not None:
            return
        self._guide_key = key
        later = ("Plus tard", "", lambda: self.guide_stop())
        never = ("Ne plus afficher", "", lambda: self.guide_stop(done=True))
        if key == "pret":
            self.gael_bubble("Tout est prêt !", "Clique sur « Démarrer » en haut à droite pour partir à l'antenne. "
                             "Bonne émission !", [("OK", "primary", lambda: self.guide_stop(done=True))], mode="guide")
            self._guide_on = False
            self._guide_tm.stop()
            self.data.setdefault("settings", {})["guide_done"] = True
            self.save_settings()
            return
        title, line = self.GUIDE[key]
        fix = todo[0]
        self.gael_bubble(title, line, [(fix[3], "primary", fix[4]), later, never], mode="guide")

    # ------------------------------------------------------------ « Signaler un problème »
    def support_report(self, desc=""):
        """Rapport texte pour le support : tout ce qu'il faut pour comprendre un problème, rien de personnel."""
        a = []
        add = a.append
        add(f"=== Rapport Bev · {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
        if desc.strip():
            add("\n--- Ce qui s'est passé (décrit par la radio)\n" + desc.strip())
        add("\n--- Système")
        for k, v in getattr(self, "about_info", []):
            if k != "Réglages":
                add(f"{k} : {v}")
        add(f"Mode : {'minimaliste' if MINI else 'normal'} · moteur séparé : "
            f"{'oui' if isinstance(self.engine, EngineProxy) else 'non'} · à l'antenne : {'oui' if self.on_air else 'non'}")
        code = os.environ.get("BEV_CODE")
        if code and code != "builtin":
            st = express_state()
            add(f"Mise à jour express : {st.get('version')} (installée : {st.get('from') or '?'})")
        add("\n--- Réglages (sans mot de passe ni coordonnées)")
        try:
            add(settings_summary(json.loads(json.dumps(self.data, default=str))))
        except Exception as ex:
            add(f"(résumé impossible : {ex})")
        add("\n--- Prêt pour l'antenne")
        try:
            R = self.readiness()
            add("\n".join(f"[{r[0]}] {r[2]}" for r in R) or "Rien ne manque.")
        except Exception as ex:
            add(f"(vérification impossible : {ex})")
        add("\n--- Diagnostic rapide")
        try:
            add(self.assistant.diagnose()[0])
        except Exception as ex:
            add(f"(diagnostic impossible : {ex})")
        if getattr(self, "diag_lines", None):
            add("\n--- Dernier diagnostic complet (SOS)\n" + "\n".join(self.diag_lines))
        add("\n--- Journal d'antenne (fin)\n" + "\n".join(self.log_lines[-300:]))
        for title, path, n in (("Journal technique (erreurs)", TRACE_FILE, 250),
                               ("Plantage de l'interface (précédent)", CRASH_FILE.replace(".log", "-precedent.log"), 80),
                               ("Plantage du moteur audio (précédent)", CRASH_FILE.replace(".log", "-moteur-precedent.log"), 80),
                               ("Mises à jour express", os.path.join(UPD_DIR, "journal.txt"), 40)):
            t = tail_file(path, n)
            if t.strip():
                add(f"\n--- {title} (fin)\n{t}")
        return scrub("\n".join(a)) + "\n"

    def support_dialog(self, desc=""):
        d = QDialog(self)
        d.setWindowTitle("Signaler un problème")
        d.setMinimumWidth(560)
        v = QVBoxLayout(d)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        t = lab("Signaler un problème", "")
        t.setStyleSheet("font-size:18px;font-weight:700;")
        v.addWidget(t)
        v.addWidget(lab("Bev prépare un rapport pour ceux qui le développent : version, système, réglages, diagnostic et fin "
                        "des journaux. Les mots de passe, clés, adresses mail, numéros de téléphone et liens d'alerte en sont "
                        "retirés.", "mut", True))
        ed = QPlainTextEdit()
        ed.setPlaceholderText("Que s'est-il passé ? Qu'étiez-vous en train de faire ? (facultatif, mais très utile)")
        ed.setPlainText(desc)
        ed.setMaximumHeight(110)
        v.addWidget(ed)
        st = lab("", "mut", True)
        v.addWidget(st)
        h = QHBoxLayout()
        h.setSpacing(8)

        def report():
            return self.support_report(ed.toPlainText())

        def save():
            base = next((p for p in (os.path.join(os.path.expanduser("~"), x) for x in ("Desktop", "Bureau", "Documents"))
                         if os.path.isdir(p)), os.path.expanduser("~"))
            dst, _ = QFileDialog.getSaveFileName(d, "Enregistrer le rapport", os.path.join(base, time.strftime("rapport-bev-%Y%m%d-%H%M.txt")),
                                                 "Texte (*.txt)")
            if dst:
                try:
                    with open(dst, "w", encoding="utf-8") as fh:
                        fh.write(report())
                    d._saved = dst
                    st.setText(f"Rapport enregistré : {dst}")
                    self.log("Rapport de support enregistré : " + scrub(dst))
                except OSError as ex:
                    st.setText(f"Enregistrement impossible : {ex}")

        def copy():
            QApplication.clipboard().setText(report())
            st.setText("Rapport copié : il suffit de le coller (Ctrl+V) dans un mail ou sur GitHub.")

        def github():
            if not getattr(d, "_saved", None):
                save()
            self.support_github(ed.toPlainText(), getattr(d, "_saved", None))
            st.setText("Page GitHub ouverte : décrivez le problème, puis glissez le fichier du rapport dans la zone de texte.")
        h.addWidget(btn("Enregistrer le rapport…", "", save))
        h.addWidget(btn("Copier", "", copy))
        h.addWidget(btn("Ouvrir GitHub", "primary", github))
        h.addStretch(1)
        h.addWidget(btn("Fermer", "", d.reject))
        v.addLayout(h)
        d.exec()

    def support_github(self, desc="", saved=None):
        """Fiche de bug GitHub pré-remplie (formulaire .github/ISSUE_TEMPLATE/bug.yml) : description et informations système.
        Le rapport complet est trop long pour une adresse web : on le joint en glissant le fichier."""
        from urllib.parse import urlencode
        repo = UPDATE_REPO or self.data.get("settings", {}).get("update_repo") or SUPPORT_REPO
        infos = "\n".join(f"{k} : {v}" for k, v in getattr(self, "about_info", []) if k != "Réglages")
        q = {"template": "bug.yml", "title": "[Bug] " + (desc.strip().splitlines()[0][:70] if desc.strip() else ""),
             "description": scrub(desc.strip())[:1500], "infos": scrub(infos)[:1500]}
        QDesktopServices.openUrl(QUrl(f"https://github.com/{repo}/issues/new?" + urlencode(q)))
        if saved:
            QTimer.singleShot(800, lambda: self.open_path(os.path.dirname(saved)))

    # ------------------------------------------------------------ erreurs internes et plantages
    def on_internal_error(self, summary):
        """Une erreur inattendue vient d'être notée (journal technique) : une ligne dans le journal d'antenne et, une fois par
        session, une petite bulle qui propose de la signaler. L'antenne n'est jamais touchée."""
        self.log(f"Erreur interne : {summary} (détails dans le rapport de support)")
        if getattr(self, "_err_told", False) or self._closing:
            return
        self._err_told = True
        QTimer.singleShot(400, lambda: self.gael_bubble(
            "Oups, un petit souci interne", "L'antenne continue normalement. Si quelque chose ne marche pas comme prévu, "
            "un rapport aidera à le corriger.", [("Signaler", "primary", lambda: (self.update_bubble_close(), self.support_dialog())),
                                                  ("Plus tard", "", self.update_bubble_close)], hide_after=20000, mode="err"))

    def crash_greet(self, report):
        """Lancement après un plantage brutal de Bev : proposition d'envoyer le rapport."""
        if not report.strip():
            return
        self.log("Bev s'est fermé brutalement lors de la dernière utilisation (détails dans le rapport de support).")
        self.gael_bubble("Bev s'est fermé brutalement la dernière fois", "Désolé ! Un rapport aiderait à trouver la cause.",
                         [("Signaler", "primary", lambda: (self.update_bubble_close(),
                                                           self.support_dialog("Bev s'est fermé brutalement pendant que… "))),
                          ("Non merci", "", self.update_bubble_close)], hide_after=30000, mode="err")


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
