# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - « Le saviez-vous ? », boîtes de dialogue, pages, réglages des flux et des jingles."""
from bev_secours import *  # noqa: F401,F403

# ------------------------------------------------------------------ « Le saviez-vous ? » : anecdotes de radio, de broadcast et de son
# (jour, mois, année, texte) ; jour / mois à None si seule l'année est sûre ; année à None pour un fait intemporel.
# Le texte daté est complété automatiquement par « il y a N ans » (ou « jour pour jour » le jour anniversaire).
FACTS = [
    (9, 4, 1860, "Édouard-Léon Scott de Martinville enregistrait « Au clair de la lune » sur son phonautographe : la plus ancienne voix humaine enregistrée qu'on sache réécouter."),
    (None, None, 1877, "Thomas Edison inventait le phonographe ; il y récita « Mary had a little lamb », premier enregistrement qu'il put lui-même réécouter."),
    (None, None, 1881, "Clément Ader présentait le théâtrophone à l'Exposition d'électricité de Paris : on écoutait l'Opéra au téléphone, avec deux écouteurs pour l'effet de relief."),
    (None, None, 1887, "Emile Berliner brevetait le gramophone et son disque plat, bien plus facile à reproduire que les cylindres d'Edison."),
    (None, None, 1890, "le Français Édouard Branly mettait au point le « radioconducteur » (cohéreur), premier vrai détecteur d'ondes radio."),
    (None, None, 1895, "le jeune Guglielmo Marconi réalisait ses premières transmissions sans fil dans la propriété familiale, près de Bologne."),
    (12, 12, 1901, "Marconi recevait à Terre-Neuve la lettre « S » en morse envoyée depuis les Cornouailles : la première liaison radio transatlantique."),
    (None, None, 1909, "Marconi et Ferdinand Braun recevaient ensemble le prix Nobel de physique pour la télégraphie sans fil."),
    (24, 12, 1906, "Reginald Fessenden aurait diffusé voix et violon depuis Brant Rock (États-Unis) : on la cite souvent comme la première émission de radio."),
    (2, 11, 1920, "KDKA, à Pittsburgh, annonçait en direct les résultats de l'élection présidentielle américaine : l'acte de naissance de la radio commerciale."),
    (18, 10, 1922, "naissait la British Broadcasting Company, qui deviendra la BBC."),
    (6, 11, 1922, "Radiola, première station privée française, commençait ses émissions régulières ; elle deviendra Radio-Paris."),
    (None, None, 1931, "l'ingénieur Alan Blumlein déposait un brevet sur le son stéréophonique : tout le principe de la stéréo y est déjà."),
    (12, 11, 1931, "ouvraient à Londres les studios EMI de la rue Abbey Road."),
    (26, 12, 1933, "Edwin Armstrong obtenait ses brevets sur la modulation de fréquence : l'invention de la FM, beaucoup moins sensible aux parasites que l'AM."),
    (None, None, 1935, "AEG présentait le Magnetophon au salon de la radio de Berlin, ancêtre de tous les magnétophones à bande."),
    (30, 10, 1938, "Orson Welles diffusait « La Guerre des mondes » sous forme de faux flash d'information : certains auditeurs crurent à une vraie invasion martienne."),
    (18, 6, 1940, "le général de Gaulle lançait son appel au micro de la BBC ; il n'en existe aucun enregistrement, mais le texte est resté célèbre."),
    (1, 6, 1944, "Radio Londres diffusait les premiers vers de Verlaine, « Les sanglots longs des violons de l'automne », pour annoncer à la Résistance l'imminence du Débarquement."),
    (None, None, 1948, "Columbia lançait le disque microsillon 33 tours : plus de 20 minutes par face au lieu de 4 pour un 78 tours."),
    (None, None, 1954, "sortait la Regency TR-1, premier poste de radio à transistors vendu au grand public : la radio devenait portable."),
    (4, 2, 1955, "Europe n°1 commençait à émettre, depuis un émetteur installé en Sarre, à l'époque sous influence française."),
    (None, None, 1963, "Philips présentait la cassette audio compacte au salon de la radio de Berlin."),
    (28, 3, 1964, "Radio Caroline émettait pour la première fois depuis un bateau ancré au large de l'Angleterre : la grande époque des radios pirates commençait."),
    (26, 9, 1969, "les Beatles sortaient Abbey Road, enregistré dans les studios qui portent aujourd'hui ce nom."),
    (None, None, 1977, "Radio Verte, l'une des premières radios libres françaises, émettait illégalement depuis Paris."),
    (1, 7, 1979, "Sony lançait le Walkman : la musique enregistrée devenait vraiment personnelle et nomade."),
    (9, 11, 1981, "la loi sur les radios locales privées mettait fin au monopole d'État en France : la naissance officielle des radios libres, dont beaucoup de radios associatives."),
    (1, 10, 1982, "les premiers CD audio étaient mis en vente au Japon, avec le lecteur Sony CDP-101."),
    (None, None, 1995, "la BBC et la radio norvégienne lançaient les premières émissions régulières en DAB, la radio numérique terrestre."),
    (14, 7, 1995, "l'institut Fraunhofer choisissait l'extension « .mp3 » pour son format de compression audio."),
    (None, None, 1998, "Nullsoft, les créateurs de Winamp, lançaient SHOUTcast, qui a permis à des milliers de webradios de naître."),
    (None, None, 2016, "France Inter cessait d'émettre en grandes ondes sur 162 kHz depuis l'émetteur d'Allouis, dans le Cher ; cette fréquence continue de servir à diffuser l'heure légale."),
    (None, None, None, "les ondes radio vont environ 900 000 fois plus vite que le son : en théorie, un auditeur à 1 000 km de l'émetteur entendrait la voix avant un spectateur assis à deux mètres du chanteur."),
    (None, None, None, "le RDS n'affiche que 8 caractères pour le nom de la station : c'est pour ça que certaines radios font défiler leur nom par morceaux."),
    (None, None, None, "en Europe, la bande FM s'étend de 87,5 à 108 MHz, avec des stations espacées de 100 kHz."),
    (None, None, None, "un CD échantillonne le son 44 100 fois par seconde : de quoi reproduire des fréquences jusqu'à 22 kHz, au-delà de ce que l'oreille humaine perçoit."),
    (None, None, None, "la recommandation EBU R128 vise une sonie moyenne de −23 LUFS : c'est elle qui a calmé la « guerre du volume » à la télévision européenne."),
    (None, None, None, "par défaut, un serveur Icecast écoute sur le port 8000 ; SHOUTcast utilise aussi le 8000 pour les auditeurs et le port suivant pour la source."),
    (None, None, None, "les ondes radio ont été mises en évidence par Heinrich Hertz à la fin des années 1880 : c'est pour ça que les fréquences se mesurent en hertz."),
    (None, None, None, "une radio qui coupe son émetteur une seconde, c'est un « blanc » d'antenne : les bénévoles des radios associatives le redoutent autant que les pros."),
    (None, None, 1969, "Neil Armstrong posait le pied sur la Lune : la retransmission en direct, à la radio comme à la télévision, fut suivie dans le monde entier."),
    (None, None, 1999, "naissait Icecast, serveur de streaming libre aujourd'hui maintenu par la fondation Xiph.Org."),
    (None, None, 2004, "le journaliste Ben Hammersley proposait le mot « podcasting » dans The Guardian, contraction d'iPod et de broadcasting."),
    (20, 6, 2014, "la radio numérique terrestre démarrait en France, avec des multiplex à Paris, Marseille et Nice."),
    (None, None, None, "le son parcourt environ 343 m par seconde dans l'air à 20 °C : le son d'une enceinte atteint donc un micro placé à trois mètres avec près de 9 ms de retard."),
    (None, None, None, "le décibel doit son nom à Alexander Graham Bell, l'inventeur du téléphone : le « bel » était à l'origine l'unité de mesure d'un rapport de puissances (le décibel en est le dixième)."),
    (None, None, None, "le DAB+ utilise le codec HE-AAC v2, le même genre de compression que beaucoup de flux Internet : à 64 kbit/s, il reste très correct pour de la voix."),
    (None, None, None, "dans le jargon radio anglophone, un silence à l'antenne s'appelle « dead air » : l'air mort, hantise de tous les animateurs."),
    (5, 11, 1898, "Eugène Ducretet réalisait une liaison par télégraphie sans fil entre la tour Eiffel et le Panthéon, à Paris."),
    (None, None, 1921, "la tour Eiffel diffusait ses premiers concerts radiophoniques pour le public : la radio française faisait ses débuts."),
    (26, 12, 1933, "l'Américain Edwin Armstrong obtenait ses brevets sur la modulation de fréquence : la FM était née."),
    (None, None, 1947, "John Bardeen, Walter Brattain et William Shockley inventaient le transistor aux laboratoires Bell : la fin des postes à lampes s'annonçait."),
    (None, None, 1954, "sortait la Regency TR-1, premier poste de radio à transistors vendu dans le commerce : la radio devenait vraiment portable."),
    (18, 6, 1940, "le général de Gaulle lançait son appel depuis les studios de la BBC, à Londres."),
    (30, 10, 1938, "Orson Welles adaptait « La Guerre des mondes » à la radio américaine ; la panique qu'elle aurait causée a depuis été largement exagérée par la presse."),
    (13, 2, 2012, "on célébrait la première Journée mondiale de la radio, proclamée par l'UNESCO."),
    (None, None, 1963, "Philips présentait la cassette audio compacte, qui allait accompagner des générations d'animateurs et de bricoleurs du son."),
    (None, None, None, "pour la FM, une antenne quart d'onde mesure environ 75 cm : la longueur d'onde vers 100 MHz est d'à peu près 3 mètres."),
    (None, None, None, "la stéréo FM tient grâce à une « fréquence pilote » à 19 kHz : le récepteur s'en sert pour retrouver la différence gauche-droite, cachée vers 38 kHz."),
    (None, None, None, "en Europe, la FM renforce les aigus à l'émission avec une préaccentuation de 50 µs (75 µs en Amérique du Nord) ; le récepteur les rabaisse d'autant, et le souffle avec."),
    (None, None, None, "les ondes courtes rebondissent sur l'ionosphère, ce qui permet d'entendre certaines radios à l'autre bout de la planète, surtout la nuit."),
    (None, None, None, "une minute de son en qualité CD non compressé (WAV) pèse environ 10 Mo ; en MP3 à 128 kbit/s, moins d'1 Mo."),
    (None, None, None, "dans un studio, le voyant rouge « ON AIR » s'allume dès qu'un micro est ouvert : à partir de là, on n'entre plus et on chuchote, au mieux."),
]
MOIS_LONG = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")


def fact_text(f, today=None):
    d, m, y, txt = f
    today = today or time.localtime()
    if y is None:
        return "Le saviez-vous ? " + txt[0].upper() + txt[1:]
    ago = today.tm_year - y - (1 if d and m and (today.tm_mon, today.tm_mday) < (m, d) else 0)
    if d and m:
        same = (today.tm_mon, today.tm_mday) == (m, d)
        when = (f"Il y a {ago} ans jour pour jour" if same else f"Le {d if d > 1 else '1er'} {MOIS_LONG[m - 1]} {y}, il y a {ago} ans")
    else:
        when = f"En {y}, il y a {today.tm_year - y} ans"
    return f"{when}, {txt}"


def fact_order(today=None):
    """Ordre de passage : d'abord les anniversaires du jour, puis ceux du mois, puis le reste mélangé."""
    today = today or time.localtime()
    idx = list(range(len(FACTS)))
    random.Random(today.tm_yday).shuffle(idx)
    day = [i for i in idx if FACTS[i][1] == today.tm_mon and FACTS[i][0] == today.tm_mday]
    month = [i for i in idx if FACTS[i][1] == today.tm_mon and i not in day]
    return day + month + [i for i in idx if i not in day and i not in month]


class FactCard(Card):
    """Carte « Le saviez-vous ? » : une anecdote d'une ou deux phrases, qui change toutes les 40 s (fondu doux)."""

    def __init__(self):
        super().__init__()
        self.lay.setContentsMargins(16, 10, 12, 10)
        h = QHBoxLayout()
        h.setSpacing(12)
        self.icon = QLabel()
        self.icon.setFixedSize(30, 30)
        pm = QPixmap(60, 60)
        pm.fill(Qt.GlobalColor.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.scale(2, 2)
        draw_logo(q, 15, 15, 15, None, 3, 0.0, sea=False)
        q.end()
        pm.setDevicePixelRatio(2)
        self.icon.setPixmap(pm)
        h.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        self.mini = False
        col = QVBoxLayout()
        col.setSpacing(2)
        t = self.title = lab("LE SAVIEZ-VOUS ?", "")
        t.setStyleSheet(f"color:{ACCT};font-size:10px;font-weight:800;letter-spacing:1px;")
        col.addWidget(t)
        self.txt = lab("", "", True)
        self.txt.setStyleSheet("font-size:12px;")
        col.addWidget(self.txt)
        h.addLayout(col, 1)
        nx = IconButton("refresh", "Une autre anecdote", 30)
        nx.clicked.connect(self.next)
        h.addWidget(nx, 0, Qt.AlignmentFlag.AlignTop)
        self.lay.addLayout(h)
        self.order, self.k = fact_order(), -1
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self.fx = QGraphicsOpacityEffect(self.txt)
        self.fx.setOpacity(1.0)
        self.txt.setGraphicsEffect(self.fx)
        self.fade = QVariantAnimation(self)
        self.fade.setDuration(260)
        self.fade.valueChanged.connect(lambda v: self.fx.setOpacity(float(v)))
        self.fade.finished.connect(self._faded)
        self.fx.setEnabled(False)            # l'effet de fondu ne coûte que pendant le fondu (sinon rendu hors écran à chaque repeint)
        self.tm = QTimer(self)
        self.tm.timeout.connect(self.next)
        self.tm.start(40000)
        self.next(instant=True)

    @staticmethod
    def wrap2(text, font, width, lines=3):
        """Coupe le texte en `lines` lignes au plus, aux espaces, avec « … » à la fin si besoin : jamais de texte rogné au milieu d'un mot."""
        fm = QFontMetrics(font)
        out, cur = [], ""
        words = text.split()
        for i, wd in enumerate(words):
            t = (cur + " " + wd).strip()
            if fm.horizontalAdvance(t) <= width:
                cur = t
                continue
            out.append(cur)
            cur = wd
            if len(out) == lines - 1:
                rest = " ".join(words[i:])
                out.append(fm.elidedText(rest, Qt.TextElideMode.ElideRight, int(width)))
                return "\n".join(out)
        out.append(cur)
        return "\n".join(out)

    def wfont(self):
        f = QFont(self.txt.font())
        f.setPixelSize(11 if self.mini else 12)
        return f

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.mini and getattr(self, "full", None):
            self.render_text()

    def render_text(self):
        if self.mini:
            self.txt.setText(self.wrap2(self.full, self.wfont(), max(120, self.txt.width() - 8)))
        else:
            self.txt.setText(self.full)

    def set_mini(self, on):
        """Fenêtre basse : plus d'icône, texte plus petit sur deux lignes au plus : l'anecdote reste visible."""
        if on != self.mini:
            self.mini = on
            self.icon.setVisible(not on)
            self.txt.setStyleSheet("font-size:11px;" if on else "font-size:12px;")
            self.txt.setWordWrap(not on)
            self.txt.setMaximumHeight(52 if on else 16777215)
            self.lay.setContentsMargins(14, 6, 10, 6) if on else self.lay.setContentsMargins(16, 10, 12, 10)
            if getattr(self, "full", None):
                self.render_text()

    def next(self, instant=False):
        self.k = (self.k + 1) % len(self.order)
        text = self.full = fact_text(FACTS[self.order[self.k]])
        self.txt.setToolTip(text)
        if self.mini:
            text = self.wrap2(text, self.wfont(), max(120, self.txt.width() - 8))
        cb = getattr(self, "on_text", None)
        if cb:
            cb()
        if instant or not ANIM or not self.isVisible():
            self.txt.setText(text)
            return
        self._next_text, self._phase = text, "out"
        self.fx.setEnabled(True)
        self.fade.stop()
        self.fade.setStartValue(1.0)
        self.fade.setEndValue(0.0)
        self.fade.start()

    def _faded(self):
        if getattr(self, "_phase", "") == "out":
            self._phase = "in"
            self.txt.setText(self._next_text)
            cb = getattr(self, "on_text", None)
            if cb:
                cb()
            self.fade.setStartValue(0.0)
            self.fade.setEndValue(1.0)
            self.fade.start()
        elif getattr(self, "_phase", "") == "in":
            self._phase = ""
            self.fx.setOpacity(1.0)
            self.fx.setEnabled(False)

# ------------------------------------------------------------------ boîtes de dialogue
OPTS = {"protocol": ["Icecast", "Shoutcast"], "format": ["MP3", "AAC", "OGG", "OPUS", "WAV", "FLAC"],
        "channels": ["1", "2"], "processing": ["Aucun", "Limiteur doux", "Radio (compresseur + limiteur)"],
        "bitrate": ["64", "96", "128", "192", "256", "320"]}
LABELS = {"name": "Nom", "protocol": "Protocole", "host": "Serveur", "port": "Port", "sc_port": "Port source (Shoutcast)",
          "mount": "Point de montage", "user": "Utilisateur", "password": "Mot de passe", "tls": "TLS", "format": "Format",
          "bitrate": "Débit (kbit/s)", "channels": "Canaux", "genre": "Genre", "desc": "Description", "enabled": "Actif",
          "reconnect": "Reconnexion auto", "processing": "Traitement", "device": "Carte son", "folder": "Dossier",
          "rotate": "Rotation (min)", "keep_days": "Garder (jours, 0 = tout)", "prefix": "Préfixe", "pige": "Pige (h)",
          "date": "Dossiers par date", "stamp": "Exemple d'horodatage", "rds": "RDS", "ps": "Nom RDS (PS)",
          "rds_mode": "Mode RDS", "rds_target": "Cible RDS", "rds_template": "Modèle RDS", "mode": "Mode", "odr_path": "Chemin odr-audioenc",
          "dest": "Destination", "profile": "Profil", "extra": "Options supplémentaires", "dls_file": "Fichier DLS",
          "net_url": "URL réseau", "net_format": "Format réseau"}


class FormDialog(QDialog):
    """Éditeur générique d'un dictionnaire de réglages (flux, tuiles…)."""

    def __init__(self, parent, title, data, skip=("id", "type"), labels=None, opts=None, files=()):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.data, self.w = data, {}
        labels, opts = labels or LABELS, opts or OPTS
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        body = QWidget()
        fl = QFormLayout(body)
        fl.setContentsMargins(0, 0, 8, 0)
        fl.setVerticalSpacing(10)
        for k, v in data.items():
            if k in skip or isinstance(v, (list, dict)):
                continue
            if isinstance(v, bool):
                w = QCheckBox()
                w.setChecked(v)
            elif k in opts:
                w = QComboBox()
                w.setEditable(True)
                w.addItems(opts[k])
                w.setCurrentText(str(v))
            elif k in files:
                w = QLineEdit(str(v))
            else:
                w = QLineEdit("" if v is None else str(v))
                if k == "password":
                    w.setEchoMode(QLineEdit.EchoMode.Password)
            self.w[k] = w
            row = w
            if k in files:
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(w, 1)
                h.addWidget(btn("…", "", lambda w=w: self._pick(w)))
            fl.addRow(labels.get(k, k.replace("_", " ").capitalize()), row)
        sa.setWidget(body)
        lay.addWidget(sa, 1)
        bb = QHBoxLayout()
        bb.addStretch(1)
        bb.addWidget(btn("Annuler", "", self.reject))
        bb.addWidget(btn("Enregistrer", "primary", self.accept))
        lay.addLayout(bb)
        self.resize(500, min(680, 140 + 46 * len(self.w)))

    def _pick(self, w):
        f, _ = QFileDialog.getOpenFileName(self, "Choisir un fichier", w.text())
        if f:
            w.setText(f)

    def values(self):
        out = dict(self.data)
        for k, w in self.w.items():
            if isinstance(w, QCheckBox):
                out[k] = w.isChecked()
            elif isinstance(w, QComboBox):
                out[k] = w.currentText()
            else:
                t = w.text()
                old = self.data.get(k)
                if isinstance(old, (int, float)) and not isinstance(old, bool):
                    try:
                        t = type(old)(float(t.replace(",", ".")))
                    except ValueError:
                        t = old
                out[k] = t
        return out


def qt_key_token(e):
    """Nom court de la touche (F5, q, 7, KP_1…) pour les raccourcis du cartoucheur ; '' si inutilisable."""
    m = e.modifiers()
    if m & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier):
        return ""
    k = e.key()
    if Qt.Key.Key_F1 <= k <= Qt.Key.Key_F12:
        return "F%d" % (k - Qt.Key.Key_F1 + 1)
    ch = e.text()
    if m & Qt.KeyboardModifier.KeypadModifier and len(ch) == 1 and ch.isalnum():
        return "KP_" + ch
    if len(ch) == 1 and ch.isprintable() and not ch.isspace():
        return ch.lower()
    return ""


class KeyEdit(QLineEdit):
    """Champ qui capte la touche pressée."""

    def __init__(self, tok=""):
        super().__init__()
        self.tok = tok
        self.setReadOnly(True)
        self.setPlaceholderText("clique ici puis appuie sur une touche")
        self.setText(key_label(tok))

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.tok = ""
        else:
            t = qt_key_token(e)
            if not t:
                return
            self.tok = t
        self.setText(key_label(self.tok))


class CartDialog(QDialog):
    """Réglages avancés d'une tuile. Ce qui se règle déjà dans le panneau de droite du cartoucheur (volume, fondus,
    boucle, couleur, entrée / sortie, notes) n'est volontairement pas répété ici."""

    def __init__(self, parent, title, cart):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.cart, self.result = dict(cart), None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(6)

        def section(t):
            l = lab(t.upper(), "mut")
            l.setStyleSheet(f"color:{MUT};font-size:10px;font-weight:800;letter-spacing:1px;margin-top:8px;")
            lay.addWidget(l)

        def hint(t):
            l = lab(t, "mut", True)
            l.setStyleSheet(f"color:{MUT};font-size:11px;")
            lay.addWidget(l)
        section("Son")
        self.name = QLineEdit(cart.get("name", ""))
        self.name.setPlaceholderText("Nom de la tuile")
        lay.addWidget(self.name)
        fr = QHBoxLayout()
        self.file = QLineEdit(cart.get("file", ""))
        fr.addWidget(self.file, 1)
        fr.addWidget(btn("Parcourir…", "", self.browse))
        lay.addLayout(fr)
        self.trim = CheckLine("Couper les silences au début et à la fin")
        self.trim.setChecked(bool(cart.get("trim")))
        self.maxi = CheckLine("Égaliser le volume (normaliser)")
        self.maxi.setChecked(bool(cart.get("maximize")))
        lay.addWidget(self.trim)
        lay.addWidget(self.maxi)
        section("À l'antenne")
        self.mode = QComboBox()
        for k, v in CART_MODES.items():
            self.mode.addItem(v, k)
        self.mode.setCurrentIndex(max(0, list(CART_MODES).index(cart.get("mode", "Par-dessus")) if cart.get("mode", "Par-dessus") in CART_MODES else 0))
        lay.addWidget(self.mode)
        hint("Ce que devient le direct pendant que la tuile joue.")
        gr = QHBoxLayout()
        gr.addWidget(lab("Groupe", ""))
        self.grp = QSpinBox()
        self.grp.setRange(0, 9)
        self.grp.setSpecialValueText("aucun")
        self.grp.setValue(int(cart.get("group", 0) or 0))
        self.grp.setFixedWidth(90)
        gr.addWidget(self.grp)
        gr.addSpacing(14)
        gr.addWidget(lab("Fondu à l'arrêt", ""))
        self.fc = QLineEdit("" if cart.get("fade_click") in (None, "") else str(cart.get("fade_click")))
        self.fc.setPlaceholderText("général")
        self.fc.setFixedWidth(80)
        gr.addWidget(self.fc)
        gr.addWidget(lab("s", "mut"))
        gr.addStretch(1)
        lay.addLayout(gr)
        hint("Groupe : lancer une tuile coupe les autres tuiles du même numéro. Fondu à l'arrêt : vide = réglage général.")
        section("Déclenchement")
        kr = QHBoxLayout()
        kr.addWidget(lab("Touche", ""))
        self.key = KeyEdit(cart.get("key", ""))
        kr.addWidget(self.key, 1)
        self.midi = cart.get("midi", "")
        self.midi_b = btn("Pad MIDI…", "", self.learn_midi)
        if self.midi:
            self.midi_b.setText("MIDI : " + midi_label(self.midi))
        kr.addWidget(self.midi_b)
        lay.addLayout(kr)
        lay.addSpacing(8)
        bb = QHBoxLayout()
        bb.addWidget(btn("Supprimer la tuile", "danger", self.delete))
        bb.addStretch(1)
        bb.addWidget(btn("Annuler", "", self.reject))
        bb.addWidget(btn("Enregistrer", "primary", self.ok))
        lay.addLayout(bb)

    def browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choisir un son", self.file.text(), "Audio (*.mp3 *.wav *.flac *.ogg *.opus *.m4a *.aac);;Tous (*)")
        if f:
            self.file.setText(f)
            if not self.name.text():
                self.name.setText(os.path.splitext(os.path.basename(f))[0])

    def ok(self):
        c = self.cart
        c.update(name=self.name.text().strip(), file=self.file.text().strip(), mode=self.mode.currentData(),
                 trim=self.trim.isChecked(), maximize=self.maxi.isChecked(), group=self.grp.value(),
                 fade_click=self.fc.text().strip() or None, key=self.key.tok, midi=self.midi)
        self.result = c
        self.accept()

    def learn_midi(self):
        app = self.parent()
        if not (have_module("mido") and have_module("rtmidi")):
            return info(self, "MIDI", "Le MIDI demande les modules « mido » et « python-rtmidi » (bouton d'installation dans Réglages).")
        app.midi_start()
        self.midi_b.setText("Appuie sur un pad…")
        app.midi_learn = self.got_midi

    def got_midi(self, tok):
        self.midi = tok
        self.midi_b.setText("MIDI : " + midi_label(tok))

    def done(self, r):
        app = self.parent()
        if getattr(app, "midi_learn", None) == self.got_midi:
            app.midi_learn = None
        super().done(r)

    def delete(self):
        self.result = "delete"
        self.accept()


# ------------------------------------------------------------------ pages
class FitScroll(QScrollArea):
    """La page prend exactement la hauteur visible (tout tient sur un écran) ; elle ne défile que si la fenêtre devient
    plus basse que le minimum de son contenu. Se réajuste quand le contenu change (ex. « Réglages avancés »)."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def setWidget(self, w):
        super().setWidget(w)
        w.installEventFilter(self)
        QTimer.singleShot(0, self.fit)

    def eventFilter(self, o, ev):
        if ev.type() == ev.Type.LayoutRequest and not getattr(self, "_fit_pending", False):
            self._fit_pending = True                     # plusieurs demandes d'affilée : un seul ajustement
            QTimer.singleShot(0, self.fit)
        return False

    def fit(self, vp=None):
        self._fit_pending = False
        w = self.widget()
        if w is None:
            return
        vp = vp or self.viewport().size()
        need = w.minimumSizeHint().height()
        lay = w.layout()
        if lay is not None and lay.hasHeightForWidth():      # textes qui passent à la ligne : leur vraie hauteur à cette largeur
            # hauteur MINIMALE à cette largeur (Qt 6.?+) ; totalHeightForWidth donne la hauteur PRÉFÉRÉE : la page défilait
            # dès que ses cartes auraient aimé être plus hautes, alors que leur minimum tenait (Diffusion, À propos)
            f = getattr(lay, "totalMinimumHeightForWidth", None)
            if f is not None:
                need = max(need, f(max(100, vp.width())))
            else:                                           # (préférée, mais sans dépasser l'écran : on ne défile que si
                need = max(need, min(lay.totalHeightForWidth(max(100, vp.width())), vp.height()))  # le minimum déborde)
        if 0 < need - vp.height() <= 6:                    # quelques pixels de trop : on serre plutôt que d'afficher
            need = vp.height()                               # une barre de défilement pour rien
        # Barre de défilement seulement si la page déborde vraiment. Laissée « au besoin » en permanence, elle apparaissait
        # puis disparaissait à chaque image d'un redimensionnement (le temps que la page prenne la nouvelle taille) : la
        # page entière était alors mise en page trois fois au lieu d'une.
        pol = Qt.ScrollBarPolicy.ScrollBarAsNeeded if need > vp.height() else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        if self.verticalScrollBarPolicy() != pol:
            self.setVerticalScrollBarPolicy(pol)
            if not getattr(self, "_fit_pending", False):    # la largeur utile change : on réajuste juste après
                self._fit_pending = True
                QTimer.singleShot(0, self.fit)
        sz = (max(100, vp.width()), max(vp.height(), need))
        if (w.width(), w.height()) != sz:
            w.resize(*sz)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fit()


def regrid(g, narrow, cols=1):
    """Fenêtre étroite (écran vertical) : les cartes d'une grille passent les unes sous les autres (sur `cols` colonnes),
    dans l'ordre de lecture ; fenêtre large : la disposition d'origine revient à l'identique."""
    if not hasattr(g, "_wide"):
        if not narrow:
            return
        items = []
        for i in range(g.count()):
            r, c, rs, cs = g.getItemPosition(i)
            it = g.itemAt(i)
            obj = it.widget() if it.widget() is not None else it.layout()
            if obj is not None:
                items.append((obj, r, c, rs, cs, it.alignment()))
        g._wide = items
        g._cs = [g.columnStretch(c) for c in range(g.columnCount())]
        g._rs = [g.rowStretch(r) for r in range(g.rowCount())]
    if getattr(g, "_is_narrow", False) == narrow:
        return
    g._is_narrow = narrow
    while g.count():
        g.takeAt(0)
    for c in range(g.columnCount()):
        g.setColumnStretch(c, 0)
    for r in range(g.rowCount()):
        g.setRowStretch(r, 0)

    def put(obj, r, c, rs, cs, al):
        if isinstance(obj, QWidget):
            g.addWidget(obj, r, c, rs, cs, al)
        else:
            g.addLayout(obj, r, c, rs, cs, al)
    if narrow:
        order = sorted(g._wide, key=lambda x: (x[1], x[2]))
        any_st = False
        for k, (obj, r, c, rs, cs, al) in enumerate(order):
            put(obj, k // cols, k % cols, 1, 1, al)
            if r < len(g._rs) and g._rs[r]:
                g.setRowStretch(k // cols, g._rs[r])
                any_st = True
        if not any_st and order:                    # rien d'extensible : le surplus va sous les cartes, pas dans l'une d'elles
            g.setRowStretch((len(order) - 1) // cols + 1, 1)
        for c in range(cols):
            g.setColumnStretch(c, 1)
    else:
        for obj, r, c, rs, cs, al in g._wide:
            put(obj, r, c, rs, cs, al)
        for c, v in enumerate(g._cs):
            g.setColumnStretch(c, v)
        for r, v in enumerate(g._rs):
            g.setRowStretch(r, v)
    g.invalidate()


class Page(FitScroll):
    """Page de cartes qui tient dans la fenêtre."""

    def __init__(self):
        super().__init__()
        self.body = QWidget()
        self.body.setObjectName("page")
        self.setWidget(self.body)
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(2, 2, 8, 4)
        self.grid.setSpacing(12)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

# ------------------------------------------------------------------ fenêtres de réglage des flux et des jingles
class OutputDialog(QDialog):
    """Fenêtre de réglage d'une sortie (Internet, FM, DAB+, enregistrement)."""

    def __init__(self, app, cfg):
        super().__init__(app)
        self.app, self.cfg, self.result = app, dict(cfg), None
        kind = cfg["type"]
        self.setWindowTitle(f"{KINDS[kind][0]} {KINDS[kind][1]} - réglages du flux")
        self.setMinimumWidth(620)
        self.w, self.dev_map = {}, {}
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        t = lab(f"{KINDS[kind][0]} {KINDS[kind][1]}".strip(), "")
        t.setStyleSheet("font-size:19px;font-weight:700;")
        v.addWidget(t)
        v.addWidget(lab(HINTS[kind], "mut", True))
        main, adv = QFormLayout(), QFormLayout()
        for f in (main, adv):
            f.setVerticalSpacing(8)
            f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        adv_keys = ADV.get(kind, ())
        for key, label, typ, opts in FIELDS[kind]:
            f = adv if key in adv_keys else main
            if typ == "check":
                w = Switch(label)
                w.setChecked(bool(cfg.get(key, key != "tls")))      # (TLS : désactivé tant qu'on ne l'a pas choisi)
                w.toggled.connect(self.update_state)
                f.addRow("", w)
            else:
                val = str(cfg.get(key, ""))
                if typ == "combo":
                    w = QComboBox()
                    w.setEditable(key == "bitrate")
                    w.addItems([str(o) for o in opts])
                    w.setCurrentText(val)
                    w.currentTextChanged.connect(self.update_state)
                elif typ == "devices":
                    w = QComboBox()
                    w.setEditable(True)
                    w.setCurrentText(val)
                elif typ in ("file", "folder"):
                    e = QLineEdit(val)
                    row = QWidget()
                    h = QHBoxLayout(row)
                    h.setContentsMargins(0, 0, 0, 0)
                    h.addWidget(e, 1)
                    h.addWidget(btn("…", "", lambda ee=e, tt=typ: self.browse(ee, tt)))
                    e.textChanged.connect(self.update_state)
                    self.w[key] = e
                    f.addRow(label, row)
                    continue
                else:
                    w = QLineEdit(val)
                    if typ == "password":
                        w.setEchoMode(QLineEdit.EchoMode.Password)
                    w.textChanged.connect(self.update_state)
            self.w[key] = w
            if typ == "devices":
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(w, 1)
                h.addWidget(btn("↻", "", self.refresh_devs))
                f.addRow(label, row)
            elif typ == "password":
                row = QWidget()
                h = QHBoxLayout(row)
                h.setContentsMargins(0, 0, 0, 0)
                h.addWidget(w, 1)
                sw = Switch("Afficher")
                sw.toggled.connect(lambda on, ww=w: ww.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
                h.addWidget(sw)
                f.addRow(label, row)
            elif typ != "check":
                f.addRow(label, w)
        v.addLayout(main)
        if kind == "internet":
            self.url = QLineEdit()
            self.url.setReadOnly(True)
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(self.url, 1)
            h.addWidget(btn("Copier", "", lambda: app.copy_text(self.url.text(), "Adresse")))
            fl = QFormLayout()
            fl.addRow("Adresse d'écoute", row)
            v.addLayout(fl)
        self.btn_adv = btn("Réglages avancés  ▾", "", self.toggle_adv)
        v.addWidget(self.btn_adv, 0, Qt.AlignmentFlag.AlignLeft)
        self.advw = QWidget()
        self.advw.setLayout(adv)
        self.advw.hide()
        v.addWidget(self.advw)
        self.testmsg = lab("", "", True)
        v.addWidget(self.testmsg)
        h = QHBoxLayout()
        h.addWidget(btn("Tester", "", self.test))
        h.addStretch(1)
        h.addWidget(btn("Annuler", "", self.reject))
        h.addWidget(btn("OK", "primary", self.ok))
        v.addLayout(h)
        if kind == "fm":
            self.refresh_devs()
        self.update_state()

    def toggle_adv(self):
        on = not self.advw.isVisible()
        self.advw.setVisible(on)
        self.btn_adv.setText("Réglages avancés  " + ("▴" if on else "▾"))
        self.adjustSize()

    def browse(self, e, typ):
        p = QFileDialog.getExistingDirectory(self, "Dossier") if typ == "folder" else QFileDialog.getOpenFileName(self, "Fichier")[0]
        if p:
            e.setText(p)

    def g(self, k):
        w = self.w[k]
        if isinstance(w, QComboBox):
            return w.currentText()
        if isinstance(w, QCheckBox):
            return w.isChecked()
        return w.text()

    def refresh_devs(self):
        w = self.w["device"]
        if not have_module("sounddevice"):
            self.testmsg.setText("Module sounddevice non installé (onglet SOS > Installer).")
            self.testmsg.setStyleSheet(f"color:{BADC};")
            return
        try:
            devs = list_output_devices()
            self.dev_map = dict(devs)
            cur = w.currentText()
            w.clear()
            w.addItems([d for d, _ in devs])
            w.setCurrentText(cur)
            self.testmsg.setText(f"{len(devs)} sortie(s) audio détectée(s).")
            self.testmsg.setStyleSheet(f"color:{OKC};")
        except Exception as e:
            self.testmsg.setText(f"Détection impossible : {e}")
            self.testmsg.setStyleSheet(f"color:{BADC};")

    def enable(self, key, on):
        w = self.w.get(key)
        if w is not None:
            w.setEnabled(bool(on))

    def show_row(self, key, on):
        """Affiche ou masque toute la ligne d'un réglage (libellé compris)."""
        w = self.w.get(key)
        if w is None:
            return
        for f in self.findChildren(QFormLayout):
            if f.indexOf(w) >= 0:
                try:
                    f.setRowVisible(w, bool(on))
                except AttributeError:                     # Qt < 6.4
                    w.setVisible(bool(on))
                    lb = f.labelForField(w)
                    if lb is not None:
                        lb.setVisible(bool(on))
                return

    def update_state(self, *_):
        if not hasattr(self, "testmsg"):
            return
        kind = self.cfg["type"]
        g = self.g
        if kind == "internet":
            try:
                self.url.setText(listen_url({k: g(k) for k in ("host", "port", "mount", "protocol")}))
            except (KeyError, AttributeError):
                pass
            shout = g("protocol") == "Shoutcast"
            for k in ("mount", "user"):
                self.enable(k, not shout)
            self.enable("sc_port", shout)
            fm = SHOUT_FORMATS if shout else list(FORMATS)
            w = self.w["format"]
            cur = w.currentText()
            if [w.itemText(i) for i in range(w.count())] != list(fm):
                w.blockSignals(True)
                w.clear()
                w.addItems(list(fm))
                w.setCurrentText(cur if cur in fm else "MP3")
                w.blockSignals(False)
            self.show_row("bitrate", not lossless(g("format")))     # sans perte : pas de débit à choisir
        elif kind == "fm":
            for k in ("ps", "rds_mode", "rds_target", "rds_template"):
                self.enable(k, bool(g("rds")))
        elif kind == "dab":
            odr = g("mode").startswith("ODR")
            for k in ("odr_path", "dest", "extra"):
                self.enable(k, odr)
            for k in ("net_url", "net_format"):
                self.enable(k, not odr)
        elif kind == "record":
            self.show_row("bitrate", not lossless(g("format")))

    def collect(self):
        out = dict(self.cfg)
        for k in self.w:
            val = self.g(k)
            out[k] = val if isinstance(val, bool) else val.strip()
        return out

    def ok(self):
        c = self.collect()
        kind = c["type"]
        try:
            if kind == "internet":
                if not c["host"]:
                    raise ValueError("Indique le serveur.")
                int(c["port"])
                if c["sc_port"]:
                    int(c["sc_port"])
            if kind == "dab" or (kind == "record" and not lossless(c.get("format"))):
                int(c["bitrate"] or 0)
            if kind == "record":
                if not c["folder"]:
                    raise ValueError("Choisis un dossier d'enregistrement.")
                float(c["rotate"] or 60)
                float(c["keep_days"] or 0)
        except ValueError as e:
            return info(self, "Réglages", str(e) if str(e) and "invalid" not in str(e) else "Une valeur numérique est incorrecte.")
        self.result = c
        self.accept()

    def test(self):
        c = self.collect()
        kind = c["type"]
        try:
            if kind == "internet":
                port = int(c["sc_port"] or int(c["port"]) + 1) if c["protocol"] == "Shoutcast" else int(c["port"])
                socket.create_connection((c["host"], port), timeout=3).close()
                msg = f"✔ Serveur joignable ({c['host']}:{port}). Le mot de passe sera vérifié au démarrage."
            elif kind == "fm":
                if not have_module("sounddevice"):
                    raise RuntimeError("sounddevice non installé")
                found = c["device"] in dict(list_output_devices())
                msg = "✔ Carte son trouvée." if found else "✖ Carte son introuvable : choisis-en une dans la liste."
                if c["rds"] and c["rds_mode"] == "TCP":
                    host, port = split_hostport(c["rds_target"])
                    socket.create_connection((host, port), timeout=3).close()
                    msg += " ✔ Encodeur RDS joignable."
            elif kind == "dab":
                if c["mode"].startswith("ODR"):
                    exe = c["odr_path"] or "odr-audioenc"
                    ok = shutil.which(exe) or os.path.isfile(exe)
                    msg = "✔ odr-audioenc trouvé." if ok else "✖ odr-audioenc introuvable : indique son chemin."
                else:
                    msg = "✔ Réglages enregistrés (la connexion réseau se vérifie au démarrage)."
            else:
                os.makedirs(c["folder"], exist_ok=True)
                free = shutil.disk_usage(c["folder"]).free / 1e9
                kbps = 1411 if c["format"] in ("WAV",) else (700 if c["format"] == "FLAC" else int(c["bitrate"] or 192))
                msg = f"✔ Dossier utilisable. Espace libre : {free:.1f} Go (~{free * 8e6 / kbps / 3600:.0f} h d'enregistrement)."
        except Exception as e:
            msg = f"✖ {e}"
        self.testmsg.setText(msg)
        self.testmsg.setStyleSheet(f"color:{'#1e8e3e' if msg.startswith('✔') else '#c0392b'};")


class JingleDialog(QDialog):
    """Liste des jingles du secours, avec le nombre de lectures de chacun."""

    def __init__(self, app, files):
        super().__init__(app)
        self.setWindowTitle("Jingles de la playlist de secours")
        self.app, self.files, self.result = app, list(files), None
        self.setMinimumSize(520, 380)
        v = QVBoxLayout(self)
        v.addWidget(lab("À chaque échéance, le jingle le moins lu passe entre deux morceaux (jamais en coupant la musique).", "mut", True))
        self.tb = QTableWidget(0, 2)
        self.tb.setHorizontalHeaderLabels(["JINGLE", "LECTURES"])
        self.tb.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tb.verticalHeader().hide()
        self.tb.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tb.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tb.setShowGrid(False)
        v.addWidget(self.tb, 1)
        h = QHBoxLayout()
        h.addWidget(btn("＋ Ajouter…", "", self.add))
        h.addWidget(btn("✕ Retirer", "", self.rem))
        h.addStretch(1)
        h.addWidget(btn("Annuler", "", self.reject))
        h.addWidget(btn("OK", "primary", self.ok))
        v.addLayout(h)
        self.fill()

    def fill(self):
        c = self.app.data.get("counts", {})
        self.tb.setRowCount(len(self.files))
        for i, f in enumerate(self.files):
            self.tb.setItem(i, 0, QTableWidgetItem(os.path.basename(f)))
            it = QTableWidgetItem(str(c.get(f, 0)))
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tb.setItem(i, 1, it)

    def add(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Jingles", "", "Audio (*.mp3 *.wav *.flac *.ogg *.opus *.m4a *.aac);;Tous (*)")
        self.files += [f for f in fs if f not in self.files]
        self.fill()

    def rem(self):
        for i in sorted({ix.row() for ix in self.tb.selectedIndexes()}, reverse=True):
            del self.files[i]
        self.fill()

    def ok(self):
        self.result = self.files
        self.accept()


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
