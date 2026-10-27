# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - Gaël assistant : compréhension des demandes, conversation avancée (API Claude), ressources."""
from bev_monitoring import *  # noqa: F401,F403

# ------------------------------------------------------------------ Gaël : assistant qui comprend une demande et propose un réglage
# Tout est local (aucune connexion, aucune clé) : Gaël repère l'intention dans la phrase, extrait les valeurs utiles
# (serveur, port, mot de passe, débit…), demande ce qui manque, puis présente le réglage. Rien n'est modifié sans « Appliquer ».

HOST_RE = re.compile(r"(?:(?:https?|icecast|http)://)?((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}|localhost|\d{1,3}(?:\.\d{1,3}){3})(?::(\d{2,5}))?(/[\w./-]*)?", re.I)
MAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}")
URL_RE = re.compile(r"https?://\S+", re.I)
GAEL_FORMATS = {"mp3": "MP3", "aac": "AAC", "ogg": "OGG Vorbis", "vorbis": "OGG Vorbis", "opus": "Opus", "flac": "FLAC"}
YES = ("oui", "ok", "d'accord", "dac", "vas-y", "vas y", "go", "valide", "applique", "parfait", "yes", "c'est bon", "carrement", "bien sur")
NO = ("non", "annule", "laisse tomber", "stop", "pas maintenant", "plus tard", "abandonne")
SKIP = ("par defaut", "defaut", "passe", "peu importe", "je sais pas", "je ne sais pas", "standard", "normal")


# Compréhension souple : synonymes, mots familiers et fautes de frappe courantes ramenés au vocabulaire de Gaël
GAEL_SYN = (
    (r"\bstreams?\b|\bwebradios?\b|\bsortie internet\b", "flux"), (r"\bplaylists?\b|\bplayliste\b|\bplay list\b", "playlist"),
    (r"\bsecour\b|\bbackup\b|\bfallback\b|\brelai(s)?\b|\breleve\b", "secours"), (r"\bmicros?\b|\bmic\b|\bmicrophone\b", "micro"),
    (r"\bzik\b|\bmusic\b|\bmusiques?\b|\bsons? de la playlist\b", "musique"), (r"\bjingles?\b|\bvirgules?\b|\bcartouches?\b|\btuiles?\b", "cartouche"),
    (r"\bcasque\b|\becouteurs?\b|\bheadphones?\b", "casque"), (r"\bmuet\b|\bmute\b", "mute"),
    (r"\bon air\b|\ben direct\b|\ba l'antenne\b", "antenne"), (r"\bplus de son\b|\bpas de son\b|\baucun son\b", "pas de son"),
    (r"\bmaj\b|\bmise a jour\b|\bmises a jour\b|\bupdate\b|\bnouvelle version\b", "mise a jour"),
    (r"\btraitement\b|\bprocessing\b|\begaliseur\b|\beq\b|\bcompresseur\b", "traitement"),
    (r"\bstp\b|\bsvp\b|\bs'il te plait\b|\bs'il vous plait\b|\bplease\b", ""),
)
GAEL_VOCAB = ("flux", "playlist", "secours", "antenne", "diffusion", "cartouche", "cartoucheur", "micro", "entree", "casque", "ecouter",
              "musique", "traitement", "enregistrement", "monitoring", "reseau", "alerte", "demarre", "arrete", "active", "desactive",
              "lance", "coupe", "seuil", "delai", "debit", "gain", "volume", "auditeurs", "serveur", "icecast", "shoutcast", "jingle",
              "redemarre", "relance", "retour", "direct", "ordinateur", "table", "mixage", "tonalite", "playlist", "mise", "version")


class GaelBrain:
    pending = None

    @staticmethod
    def normalize(n):
        """Phrase déjà sans accents ni majuscules : synonymes ramenés à un mot connu, fautes de frappe corrigées
        (« secour », « plyalist », « antene »…), politesse retirée. Gaël comprend ainsi bien plus de façons de dire."""
        import difflib
        for pat, rep_ in GAEL_SYN:
            n = re.sub(pat, rep_, n)
        out = []
        for w in re.findall(r"[a-z0-9'@:/._+-]+|[^a-z0-9'@:/._+-]+", n):
            if re.fullmatch(r"[a-z]{5,}", w) and w not in GAEL_VOCAB:
                c = difflib.get_close_matches(w, GAEL_VOCAB, 1, 0.84)
                if c:
                    w = c[0]
            out.append(w)
        return re.sub(r"\s+", " ", "".join(out)).strip()

    # ---------------------------------------------------------- outils de lecture de phrase
    @staticmethod
    def has(n, *words):
        return any(w in n for w in words)

    @staticmethod
    def num(n, pat):
        m = re.search(pat, n)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except (ValueError, IndexError):
            return None

    def extract_stream(self, q, n, slots):
        """Remplit les champs d'un flux Internet à partir d'une phrase libre."""
        url = None
        for m in HOST_RE.finditer(q):
            h = m.group(1)
            if "@" in q[max(0, m.start() - 1):m.start()]:
                continue
            if h.lower() in ("mot.de", "e.g") or re.fullmatch(r"\d+(\.\d+)?", h):
                continue
            url = m
            break
        if url:
            slots["host"] = url.group(1)
            if url.group(2):
                slots["port"] = url.group(2)
            if url.group(3) and len(url.group(3)) > 1:
                slots["mount"] = url.group(3)
        m = re.search(r"\bport\s*:?\s*(\d{2,5})", n)
        if m:
            slots["port"] = m.group(1)
        m = re.search(r"(?:point de montage|montage|mountpoint|mount)\s*:?\s*(/?[\w.-]+)", q, re.I)
        if m:
            slots["mount"] = "/" + m.group(1).lstrip("/")
        m = re.search(r"(?:mot de passe|mdp|password|pass|passe)\s*(?:source)?\s*(?:est|:|=)?\s*[«\"']?([^\s«»\"']+)", q, re.I)
        if m and norm_txt(m.group(1)) not in ("est", "source", "de", "du"):
            slots["password"] = m.group(1)
        for k, v in GAEL_FORMATS.items():
            if re.search(r"\b" + k + r"\b", n):
                slots["format"] = v
        b = self.num(n, r"\b(\d{2,3})\s*(?:k\b|kb|kbps|kbit|kbits|kilo)")
        if b:
            slots["bitrate"] = str(int(b))
        if "shoutcast" in n:
            slots["protocol"] = "Shoutcast"
        elif "icecast" in n:
            slots["protocol"] = "Icecast"
        m = re.search(r"(?:nomm[ée]e?|appel[ée]e?|appelle|intitul[ée]e?|nom)\s*:?\s*[«\"']\s*([^»\"']+?)\s*[»\"']", q, re.I) or \
            re.search(r"(?:nomm[ée]e?|appel[ée]e?|intitul[ée]e?)\s+([\w' -]{2,30})$", q, re.I)
        if m:
            slots["name"] = m.group(1).strip()
        return slots

    # ---------------------------------------------------------- point d'entrée
    def answer(self, q):
        n = self.normalize(norm_txt(q).strip())
        if self.pending:
            r = self.continue_pending(q, n)
            if r is not None:
                return r
        r = self.intent(q, n)
        if r is not None:
            return r
        r = self.chat_reply(q, n)
        if r is not None:
            return r
        r = AssistantKB.answer(self, q)
        text, acts = r if isinstance(r, tuple) else (r, None)
        if text.startswith("Je n'ai pas trouvé") or text.startswith("Je ne suis pas sûr"):
            tip = "" if self.llm_on() or getattr(self, "_tip_ai", False) else \
                "\n\nAstuce : avec la conversation avancée (Réglages > Gaël, le radio-bot), je comprends les phrases libres bien mieux."
            self._tip_ai = True
            text = random.choice(("Hmm, je ne suis pas sûr de te suivre.", "Pas sûr d'avoir compris, désolé.",
                                  "Je sèche un peu là-dessus.")) + " Tu peux me le dire autrement ? Sinon, voici des sujets proches :" + tip
        return (text, acts)

    # ---------------------------------------------------------- petite conversation (hors technique)
    def chat_reply(self, q, n):
        words = re.findall(r"[a-z0-9']+", n)
        if len(words) > 9:
            return None
        H = self.has
        pick = random.choice
        a = self.app
        h = time.localtime().tm_hour
        if re.match(r"^(bonjour|salut|coucou|hello|hey|yo|demat|bonsoir|bjr|slt|hi)\b", n) and len(words) <= 4:
            hi = pick(("Demat !", "Salut !", "Bonjour !")) if h < 18 else pick(("Bonsoir !", "Noz vat !" if h >= 21 else "Bonsoir !"))
            st = ("L'antenne tourne bien" if a.on_air else "On est hors antenne pour l'instant")
            return f"{hi} {st}. Qu'est-ce que je peux faire pour toi ?"
        if H(n, "ca va", "comment vas", "comment tu vas", "la forme", "tu vas bien", "quoi de neuf"):
            if a.on_air and a.engine:
                bad = [o.cfg["name"] for o in a.engine.outputs if o.cfg.get("enabled", True) and o.state == "error"]
                if bad:
                    return (f"Moi ça va, mais « {bad[0]} » fait des siennes. Tu veux que je regarde ?", [("Oui, regarde", lambda: self.ask("Flux en erreur"), "primary")])
                return pick(("Ça roule ! L'antenne est stable et le son passe.", "Au top, l'antenne ronronne. Et toi ?", "Tranquille : tout est au vert de mon côté."))
            return pick(("Très bien, merci ! Je surveille, prêt pour la prochaine émission.", "Ça va bien ! Hors antenne, je profite du calme. Et toi ?"))
        if H(n, "merci", "trugarez", "thanks", "cool merci", "top merci", "c'est gentil"):
            return pick(("Avec plaisir !", "Trugarez à toi !", "De rien, c'est pour ça que je suis là.", "Pas de quoi, bonne émission !"))
        if H(n, "qui es-tu", "qui es tu", "t'es qui", "tu es qui", "ton nom", "tu t'appelles", "c'est qui gael", "qui est gael", "presente-toi"):
            return ("Je suis Gaël, le radio-bot : un petit robot marin : marinière, béret à pompon et antenne qui capte. "
                    "Je veille sur l'antenne, j'explique les pannes et je prépare les réglages pour toi.")
        if H(n, "que sais-tu", "tu sais faire quoi", "tu fais quoi", "a quoi tu sers", "tu peux faire quoi", "aide-moi", "aide moi") and len(words) <= 6:
            return ("Je peux te dire comment va l'antenne, expliquer une erreur de flux, dépanner un souci de son ou de réseau, lancer un diagnostic, "
                    "et préparer des réglages : créer un flux, activer le secours, régler le gain, prévenir quelqu'un en cas de panne…",
                    [("Comment va l'antenne ?", lambda: self.ask("État"), "primary"), ("Créer un flux", lambda: self.ask("Crée un flux Internet"))])
        if H(n, "blague", "raconte", "fais-moi rire", "drole"):
            return pick(("Pourquoi les radios associatives n'ont jamais froid ? Parce qu'elles ont plein de bénévoles… et des tonnes de câbles pour se couvrir.",
                         "Un auditeur appelle : « Vous émettez sur quelle fréquence ? » « Sur la bonne, j'espère ! »",
                         "Mon rêve ? Une émission entière sans larsen. On peut toujours rêver, hein."))
        if H(n, "au revoir", "kenavo", "a plus", "a+", "bonne nuit", "bye", "ciao", "a demain", "bonne soiree"):
            return pick(("Kenavo ! Je garde un œil sur l'antenne.", "À plus ! Je reste de veille.", "Bonne soirée, et bonne émission !"))
        if H(n, "bravo", "genial", "super", "parfait", "excellent", "trop bien", "nickel", "top") and len(words) <= 4:
            return pick(("Merci ! On fait une bonne équipe.", "Ravi que ça marche !", "Nickel. Autre chose ?"))
        if n in ("ok", "d'accord", "dac", "oui", "ouais", "non", "bon", "ah", "ah ok", "ok merci", "compris"):
            return pick(("Très bien. Autre chose ?", "Ça marche. Je reste là si besoin.", "Entendu."))
        if H(n, "t'es nul", "tu sers a rien", "idiot", "debile", "nul"):
            return "Aïe, désolé de ne pas avoir aidé. Dis-moi ce qui coince avec d'autres mots, je vais faire mieux."
        if H(n, "quelle heure", "on est quel jour", "quel jour"):
            t = time.localtime()
            return f"Il est {t.tm_hour} h {t.tm_min:02d}, on est {JOURS[t.tm_wday]} {t.tm_mday} {MOIS[t.tm_mon - 1]}."
        return None

    # ---------------------------------------------------------- intentions reconnues
    def direct(self, q, n):
        """Commandes directes de la régie : entrée, écoute, playlist, cartouches, mute, traitement, auditeurs, mise à jour…"""
        a = self.app
        H = self.has
        e = a.engine
        # --- écoute de contrôle au casque
        if H(n, "casque", "ecouter l'antenne", "ecoute l'antenne", "entendre l'antenne", "ecouter ce qui part", "entendre la playlist", "ecouter la playlist") \
                and not H(n, "cartouche", "pre-ecoute", "preecoute"):
            on = not H(n, "arrete", "coupe", "stop", "enleve")
            if bool(e and e.listen) == on:
                return "C'est déjà " + ("en cours : l'antenne part dans le casque." if on else "arrêté.")
            return ("Je " + ("mets l'antenne dans le casque (carte son du cartoucheur)." if on else "coupe l'écoute au casque."),
                    [("Écouter l'antenne" if on else "Arrêter l'écoute", a.toggle_listen, "primary")])
        # --- contrôle d'entrée / changement d'entrée
        if H(n, "teste le micro", "tester le micro", "teste l'entree", "tester l'entree", "voir l'entree", "verifie l'entree", "controle d'entree", "niveau du micro"):
            if a.on_air:
                return "Pendant l'antenne, le niveau d'entrée s'affiche déjà en permanence (vumètre ENTRÉE)."
            return ("J'ouvre l'entrée pour voir son niveau, sans rien diffuser.", [("Voir l'entrée", lambda: (a.go_tab("diff"), a.toggle_preview() if not a.preview else None), "primary")])
        if H(n, "entree", "source", "micro", "table de mixage", "mixage", "interface", "carte son", "son de l'ordinateur", "line in") and \
                H(n, "change", "utilise", "prends", "passe sur", "bascule sur", "mets", "choisis", "selectionne", "branche"):
            words = [w for w in re.findall(r"[a-z0-9]{3,}", n) if w not in ("change", "utilise", "prends", "passe", "bascule", "entree", "source", "mets", "choisis",
                                                                           "selectionne", "sur", "les", "des", "une", "son", "pour", "avec", "table",
                                                                           "mixage", "comme", "branche", "carte")]
            if H(n, "table de mixage", "mixage", "interface"):
                words += ["line", "usb", "mix", "interface", "behringer", "focusrite", "yamaha", "mackie", "umc"]
            if H(n, "ordinateur", "pc", "loopback", "spotify", "navigateur"):
                words += ["ordinateur"]
            best, score = None, 0
            for lbl, val in a.dev_map.items():
                t = norm_txt(lbl)
                sc = sum(1 for w in words if w in t)
                if sc > score:
                    best, score = (lbl, val), sc
            if best:
                lbl, val = best
                return self.propose("Entrée audio", [("Nouvelle entrée", lbl), ("Pendant l'antenne", "changement immédiat")],
                                    lambda: (a.dev_pick.set_current(lbl), a.on_dev_select(lbl), a.log(f"Gaël : entrée changée pour « {lbl} ».")))
            return ("Laquelle ? Voici les entrées détectées :", [(l[:32], (lambda l=l: (a.dev_pick.set_current(l), a.on_dev_select(l)))) for l in list(a.dev_map)[:6]])
        # --- playlist de secours : lancer / revenir au direct / jouer un titre
        if H(n, "revien au direct", "reviens au direct", "retour au direct", "repasse au direct", "remets le direct", "arrete la playlist", "coupe la playlist"):
            if not (e and a.on_air and e.manual):
                return "Le direct est déjà à l'antenne." if a.on_air else "Rien n'est à l'antenne pour l'instant."
            return ("Je repasse au direct ?", [("Revenir au direct", a.toggle_manual, "primary")])
        if H(n, "lance la playlist", "lancer la playlist", "passe la playlist", "mets la playlist", "envoie la playlist", "lance la musique", "mets de la musique", "passe de la musique"):
            if not a.on_air:
                return "Démarre d'abord la diffusion : la playlist part à l'antenne."
            if not a.playlist:
                return ("La playlist de secours est vide.", [("Ajouter des morceaux…", a.pl_add, "primary")])
            return ("Je lance la playlist de secours à l'antenne (tu reviens au direct quand tu veux) ?", [("Lancer la playlist", a.toggle_manual, "primary")])
        m = re.match(r"^(?:joue|jouer|passe|lance|envoie|mets)\s+(?:le titre |la chanson |le morceau |l'emission )?(.{3,})$", n)
        if m and not H(n, "playlist", "diffusion", "antenne", "flux", "cartouche"):
            want = m.group(1).strip()
            best, sc0 = None, 0.0
            import difflib
            for i, f in enumerate(a.playlist):
                inf = a.pl_info.get(f) or {}
                t = norm_txt((inf.get("title") or os.path.splitext(os.path.basename(f))[0]) + " " + (inf.get("artist") or ""))
                sc = difflib.SequenceMatcher(None, want, t).ratio() + (0.5 if want in t else 0)
                if sc > sc0:
                    best, sc0 = i, sc
            for si, pg in enumerate(a.carts()):
                for ci, d in enumerate(pg):
                    t = norm_txt(d.get("name") or os.path.basename(d.get("file", "")))
                    sc = difflib.SequenceMatcher(None, want, t).ratio() + (0.5 if want in t else 0)
                    if sc > sc0:
                        best, sc0 = ("cart", si, ci, d), sc
            if best is not None and sc0 >= .55:
                if isinstance(best, tuple):
                    _, si, ci, d = best
                    return (f"Je joue la cartouche « {d.get('name') or os.path.basename(d['file'])} »" + ("" if a.on_air else " (au casque, hors antenne)") + " ?",
                            [("Jouer", lambda: a.trigger(d, si * CID + ci, True), "primary")])
                f = a.playlist[best]
                nm = (a.pl_info.get(f) or {}).get("title") or os.path.basename(f)
                if a.on_air:
                    return (f"Je passe « {nm} » à l'antenne maintenant ?", [("Jouer à l'antenne", lambda: a.pl_play(best), "primary"),
                                                                          ("Pré-écouter au casque", lambda: a.pl_prelisten(best))])
                return (f"Hors antenne, je peux te faire pré-écouter « {nm} » au casque.", [("Pré-écouter", lambda: a.pl_prelisten(best), "primary")])
        # --- cartouches
        if H(n, "cartouche") and H(n, "arrete", "stop", "coupe", "silence", "tais"):
            return ("J'arrête toutes les cartouches (fondu) ?", [("Tout arrêter", a.stop_all_btn, "primary")])
        # --- mute / tonalité
        if H(n, "mute", "coupe le son de l'antenne", "coupe l'antenne", "rends l'antenne muette") and not H(n, "flux"):
            if not a.on_air:
                return "Rien n'est à l'antenne pour l'instant."
            on = not (e and e.mute)
            return ("Antenne " + ("coupée (mute)" if on else "rétablie") + " ?", [("Couper l'antenne" if on else "Rétablir le son", a.sos_mute, "danger" if on else "primary")])
        if H(n, "tonalite", "bip de test", "1 khz", "1khz", "son de test"):
            return ("Tonalité de test 1 kHz à l'antenne ?", [("Lancer / arrêter la tonalité", a.sos_tone, "primary")])
        # --- traitement du son (processeur d'antenne)
        if H(n, "traitement", "processeur", "processing") and H(n, "bypass", "desactive", "coupe le traitement", "son brut"):
            return ("Je passe le processeur en bypass (son brut à l'antenne, en fondu) ?", [("Bypass", a.proc_toggle_bypass, "primary")]) \
                if not a.proc.get("bypass") else ("Je remets le processeur à l'antenne ?", [("Réactiver", a.proc_toggle_bypass, "primary")])
        if H(n, "traitement", "processeur", "processing", "preset", "prereglage") and H(
                n, "voix", "talk", "parole", "info", "news", "journal", "classique", "jazz", "acoustique", "pop", "hits", "rock",
                "urbain", "rap", "hip hop", "loud", "fort", "generaliste", "variete", "protection", "neutre"):
            name = ("Talk-show" if H(n, "voix", "talk", "parole") else "Info (news)" if H(n, "info", "news", "journal")
                    else "Classique" if H(n, "classique") else "Jazz & acoustique" if H(n, "jazz", "acoustique")
                    else "Pop / Hits" if H(n, "pop", "hits") else "Rock" if H(n, "rock") else "Urbain" if H(n, "urbain", "rap", "hip hop")
                    else "Loud" if H(n, "loud", "fort") else "Protection seule" if H(n, "protection", "neutre") else "Généraliste")
            return self.propose("Processeur d'antenne", [("Préréglage", name), ("Appliqué", "en direct, sans coupure")],
                                lambda: a.proc_preset(name))
        # --- redémarrer les flux, auditeurs, mise à jour
        if H(n, "redemarre les flux", "relance les flux", "reconnecte", "redemarre le flux", "relance le flux"):
            return ("Je relance tous les flux ?", [("Redémarrer les flux", a.sos_restart, "primary")])
        if H(n, "auditeurs", "combien de personnes", "combien d'auditeurs", "qui ecoute", "nombre d'auditeurs"):
            L = [f"{s_['name']} : {st[2]} auditeur(s)" for s_ in a.mon_streams for st in [a.mon_state.get(s_["url"])] if st and st[2] is not None]
            return ("\n".join(L) if L else "Je n'ai pas de compte d'auditeurs : ajoute ton flux dans l'onglet Monitoring (Icecast les donne).",
                    [("Ouvrir Monitoring", lambda: a.go_tab("mon"))])
        if H(n, "mise a jour"):
            return ("Je regarde s'il existe une nouvelle version de Bev.", [("Vérifier maintenant", lambda: a.update_start(True), "primary")])
        if H(n, "depuis combien", "depuis quand") and H(n, "antenne", "direct", "diffusion"):
            return self.state().splitlines()[0] if a.on_air else "On est hors antenne."
        return None

    def intent(self, q, n):
        r = self.direct(q, n)
        if r is not None:
            return r
        a = self.app
        H = self.has
        make = H(n, "cree", "creer", "ajoute", "ajouter", "nouveau", "nouvelle", "configure", "configurer", "monte", "monter", "mets en place",
                 "installe", "prepare", "fais", "faire", "ajout", "je veux", "j'aimerais", "voudrais", "besoin d'un", "besoin d'une", "parametr")
        # --- un nouveau flux
        if (make or H(n, "enregistre")) and H(n, "enregistr", "pige", "archive") and not H(n, "internet", "icecast"):
            QTimer.singleShot(400, lambda: a.go_tab("rec"))
            return ("L'enregistrement de l'antenne se règle dans son onglet dédié : dossier, format, découpage et pige ARCOM. Je te l'ouvre.",
                    [("Ouvrir Enregistrement", lambda: a.go_tab("rec"), "primary")])
        if make and H(n, "flux", "stream", "sortie", "diffusion vers", "diffuser sur", "diffuser vers", "webradio", "icecast", "shoutcast", "emetteur"):
            kind = "internet"
            if H(n, " fm", "fm ", "emetteur", "rds") or n.endswith("fm"):
                kind = "fm"
            elif H(n, "dab"):
                kind = "dab"
            elif False:
                kind = "record"
            return self.start_stream(kind, q, n)
        if make and H(n, "plateau", "direct exterieur", "duplex"):
            return ("Un plateau extérieur reprend le serveur de ton flux Internet avec une nouvelle adresse d'écoute.",
                    [("Créer un plateau", a.new_plateau, "primary")])
        # --- secours
        if H(n, "secours", "bascule auto", "playlist de secours") and H(n, "activ", "allume", "mets", "met ", "branche", "lance la bascule", "active", "desactiv", "coupe", "eteins", "enleve", "seuil", "delai", "apres"):
            return self.p_fallback(q, n)
        # --- gain d'entrée
        if "gain" in n or (H(n, "monte", "baisse", "augmente", "diminue") and H(n, "entree", "micro", "niveau d'entree")):
            return self.p_gain(n)
        # --- retard de sécurité
        if H(n, "retard de securite", "delai de securite", "retard securite") or (H(n, "retard") and self.num(n, r"(\d+)\s*s")):
            v = self.num(n, r"(\d+)")
            if v is not None:
                v = int(_cl(v, 0, 40))
                return self.propose("Retard de sécurité", [("Retard avant l'antenne", f"{v} s")],
                                    lambda: (a.sp_delay.setValue(v), a.log(f"Gaël : retard de sécurité réglé à {v} s.")))
        # --- alertes
        if H(n, "previen", "prevenir", "alerte", "avertis", "avertir", "notifi", "sms", "texto", "mail", "courriel", "discord", "ntfy", "slack") and \
                not H(n, "ne part pas", "marche pas", "fonctionne pas", "recois pas", "erreur"):
            r = self.p_alerts(q, n)
            if r is not None:
                return r
        # --- monitoring
        if H(n, "surveill", "monitor") and URL_RE.search(q):
            u = URL_RE.search(q).group(0).rstrip(".,;)")
            return self.propose("Surveiller un flux", [("Adresse", u)], lambda: (a.mon_add(None, u), a.go_tab("mon")), "Ajouter au monitoring")
        # --- débit des flux Internet
        if H(n, "debit", "bitrate", "qualite") and self.num(n, r"(\d{2,3})"):
            return self.p_bitrate(n)
        # --- activer / désactiver un flux précis
        m = re.search(r"\b(active|reactive|allume|desactive|coupe|eteins|arrete|suspend)s?\b.*\bflux\b\s*(.*)$", n)
        if m and a.outputs_cfg:
            on = m.group(1) in ("active", "reactive", "allume")
            c = self.find_output(m.group(2))
            if c:
                return self.toggle_proposal(c, on)
            verb = "activer" if on else "désactiver"
            return (f"Quel flux veux-tu {verb} ?", [(c["name"][:30], (lambda c=c: self.say_reply(self.toggle_proposal(c, on))))
                                                     for c in self.app.outputs_cfg[:6]])
        # --- antenne
        if H(n, "demarre", "lance", "commence", "on air", "prends l'antenne", "allume l'antenne") and H(n, "diffusion", "antenne", "emission", "on air", "direct") \
                and not H(n, "secours"):
            if a.on_air:
                return "L'antenne tourne déjà. " + self.state().splitlines()[0]
            return ("Je lance la diffusion avec les flux actifs ?", [("Démarrer la diffusion", a.start, "primary"), ("Pas maintenant", lambda: None)])
        if H(n, "arrete", "coupe", "stoppe", "termine", "fin de") and H(n, "diffusion", "antenne", "emission") and not H(n, "secours", "flux "):
            if not a.on_air:
                return "Rien n'est à l'antenne pour l'instant."
            return ("Tu veux vraiment arrêter la diffusion ?", [("Arrêter la diffusion", a.stop, "danger"), ("Non, on continue", lambda: None)])
        # --- apparence
        if H(n, "mode clair", "theme clair", "en clair", "fond blanc"):
            return self.propose("Apparence", [("Mode", "clair"), ("Prise en compte", "au redémarrage")], lambda: self.set_setting("theme", "light"))
        if H(n, "mode sombre", "theme sombre", "en sombre", "mode nuit", "fond noir"):
            return self.propose("Apparence", [("Mode", "sombre"), ("Prise en compte", "au redémarrage")], lambda: self.set_setting("theme", "dark"))
        if H(n, "reduis les animations", "reduire les animations", "moins d'animation", "sans animation", "arrete les animations", "coupe les animations"):
            return self.propose("Animations", [("Réduire les animations", "oui"), ("Prise en compte", "au redémarrage")], lambda: self.set_setting("perf", True))
        # --- navigation
        m = re.search(r"\b(?:ouvre|va|aller|affiche|montre|emmene)\b.*\b(diffusion|traitement|cartoucheur|cartouches|enregistrement|monitoring|reseau|reglages|a propos)\b", n)
        if m:
            k = {"diffusion": "diff", "traitement": "son", "cartoucheur": "cart", "cartouches": "cart", "enregistrement": "rec", "monitoring": "mon",
                 "reseau": "net", "reglages": "set", "a propos": "about"}[m.group(1)]
            QTimer.singleShot(400, lambda: a.go_tab(k))
            return f"J'ouvre l'onglet {PAGE_TITLES[k]}."
        # --- pour le plaisir
        for words, anim, txt in ((("danse", "gavotte", "fest-noz", "fest noz", "an dro"), "gavotte", "Hop ! Une gavotte, comme au fest-noz. Regarde à gauche, sous le menu."),
                                 (("crepe", "galette", "bilig", "faim"), "crepes", "Une crêpe au beurre salé, ça arrive ! Regarde sous le menu."),
                                 (("café", "cafe", "pause"), "cafe", "Une petite pause café, regarde sous le menu."),
                                 (("pluie", "crachin", "meteo", "il pleut"), "crachin", "Le crachin, c'est que de l'eau ! Je sors le parapluie, regarde sous le menu."),
                                 (("goeland", "mouette", "oiseau"), "goeland", "Oh non, pas un goéland… pas sur le béret ! Regarde sous le menu."),
                                 (("bagad", "bombarde", "biniou", "defile"), "bagad", "En avant le bagad ! Regarde sous le menu."),
                                 (("mixage", "table de mixage", "console", "dj"), "mixage", "Je prends la console ! Regarde sous le menu."),
                                 (("fierte", "pride", "lgbt", "queer", "arc-en-ciel", "arc en ciel"), "fierte",
                                  "Bev est ouvert à toutes et à tous ! Regarde sous le menu."),
                                 (("pylone", "emetteur", "grimpe", "escalade", "antenne fm"), "antenne", "Je grimpe au pylône FM ! Regarde sous le menu.")):
            if H(n, *words) and len(n) < 60 and not H(n, "flux", "secours", "erreur"):
                if hasattr(a.rail, "gael"):
                    a.rail.gael.play(anim)
                return txt
        return None

    # ---------------------------------------------------------- proposition de réglage (carte avec Appliquer)
    def propose(self, title, rows, fn, ok="Appliquer", extra=None):
        self.pending = None
        lines = "\n".join(f"  {k} : {v}" for k, v in rows)
        acts = [(ok, fn, "primary")] + list(extra or []) + [("Annuler", lambda: None)]
        return (f"Réglage proposé · {title}\n{lines}", acts)

    def set_setting(self, key, val):
        a = self.app
        a.data.setdefault("settings", {})[key] = val
        a.save_settings()
        a.log(f"Gaël : réglage « {key} » enregistré (actif au prochain démarrage).")
        if hasattr(a, "l_restart"):
            a.l_restart.setText("Redémarrage nécessaire")
        QTimer.singleShot(300, lambda: self.say("C'est noté. Le changement sera visible au prochain démarrage de l'application.", "bot",
                                                [("Redémarrer maintenant", a.restart_app)]))

    def find_output(self, words):
        w = norm_txt(words or "").strip(" .!?")
        outs = self.app.outputs_cfg
        if not w:
            return outs[0] if len(outs) == 1 else None
        for c in outs:
            if norm_txt(c["name"]) in w or w in norm_txt(c["name"]):
                return c
        for c in outs:
            if norm_txt(KINDS[c["type"]][1]) in w:
                return c
        toks = {t for t in re.findall(r"[a-z0-9]+", w) if len(t) >= 3}
        best, score = None, 0
        for c in outs:
            ct = set(re.findall(r"[a-z0-9]+", norm_txt(c["name"] + " " + c.get("host", ""))))
            sc = len(toks & ct)
            if sc > score:
                best, score = c, sc
        return best

    def toggle_proposal(self, c, on):
        return self.propose(("Activer" if on else "Désactiver") + " un flux", [("Flux", c["name"]), ("Actif", "oui" if on else "non")],
                            lambda: self.set_enabled(c, on))

    def say_reply(self, r):
        text, acts = r if isinstance(r, tuple) else (r, None)
        self.say(text, "bot", acts)

    def set_enabled(self, c, on):
        c["enabled"] = on
        self.app.refresh_outputs()
        self.app.log(f"Gaël : flux « {c['name']} » {'activé' if on else 'désactivé'}.")

    # ---------------------------------------------------------- création de flux (avec questions)
    STREAM_ASK = {"host": "Quelle est l'adresse du serveur ? (par exemple radio.mon-asso.bzh:8000, ou l'adresse complète fournie par ton hébergeur)",
                  "password": "Quel est le mot de passe SOURCE du serveur ? (celui de la source, pas celui de l'administrateur)"}

    def start_stream(self, kind, q, n):
        slots = {}
        if kind == "internet":
            self.extract_stream(q, n, slots)
            if "radio king" in n or "radioking" in n:
                slots.setdefault("port", "80")
        self.pending = {"kind": kind, "slots": slots, "ask": None}
        if kind == "fm":
            try:
                outs = [l for l, _ in list_output_devices()]
            except Exception:
                outs = []
            if outs:
                self.pending["ask"] = "device"
                acts = [(o[:34], (lambda o=o: self.pick_slot("device", o))) for o in outs[:6]]
                return ("Flux FM : quelle carte son alimente ton émetteur ?", acts + [("Je choisirai plus tard", lambda: self.pick_slot("device", ""))])
        return self.next_question()

    def pick_slot(self, key, val):
        if not self.pending:
            return
        self.pending["slots"][key] = val
        self.say(val or "(plus tard)", "me")
        r = self.next_question()
        text, acts = r if isinstance(r, tuple) else (r, None)
        QTimer.singleShot(350, lambda: self.say(text, "bot", acts))

    def next_question(self):
        P = self.pending
        k, s = P["kind"], P["slots"]
        if k == "internet":
            for need in ("host", "password"):
                if not s.get(need):
                    P["ask"] = need
                    pre = "D'accord, je prépare un flux Internet. " if not P.get("asked") else ""
                    P["asked"] = True
                    return (pre + self.STREAM_ASK[need], [("Annuler", self.cancel_pending)])
        return self.stream_proposal()

    def continue_pending(self, q, n):
        P = self.pending
        if n in NO or any(n.startswith(w) for w in NO):
            self.pending = None
            return "Pas de souci, j'annule. Rien n'a été modifié."
        ask = P.get("ask")
        if not ask:
            return None
        s = P["slots"]
        if P["kind"] == "internet":
            before = dict(s)
            self.extract_stream(q, n, s)
            if ask == "password" and not s.get("password"):
                tok = q.strip().strip("«»\"'")
                if tok and " " not in tok:
                    s["password"] = tok
            if ask == "host" and not s.get("host") and n in SKIP:
                s["host"] = "localhost"
            if s == before and ask not in s:
                # la réponse ne ressemble pas à ce qui était demandé : on laisse la base de connaissances répondre
                if len(n.split()) > 4:
                    self.pending = None
                    return None
                return ("Je n'ai pas reconnu " + ("d'adresse de serveur" if ask == "host" else "de mot de passe") + ". " + self.STREAM_ASK[ask],
                        [("Annuler", self.cancel_pending)])
            return self.next_question()
        return None

    def cancel_pending(self):
        self.pending = None
        self.say("C'est annulé, rien n'a été modifié.", "bot")

    def stream_proposal(self):
        P = self.pending
        k, s = P["kind"], P["slots"]
        c = new_output(k)
        for key in ("protocol", "host", "port", "mount", "password", "format", "bitrate", "name", "device"):
            if s.get(key) is not None and key in c or key == "name" and s.get("name"):
                c[key] = s[key]
        if k == "internet" and c["protocol"] == "Shoutcast":
            c["mount"] = c.get("mount") or "/"
        if k == "internet" and not s.get("name"):
            h = c["host"]
            short = c["protocol"] if re.fullmatch(r"[\d.]+", h) else (h.rsplit(".", 1)[0] if "." in h else h)
            c["name"] = "Internet · " + short[:22]
        if k == "internet" and c["format"] == "FLAC":
            c["bitrate"] = c.get("bitrate") or "0"
            fq = fmt_quality(c.get("format", ""), c["bitrate"])
        rows = {"internet": lambda: [("Serveur", f"{c['protocol']} {c['host']}:{c['port']}" + (c["mount"] if c["protocol"] == "Icecast" else "")),
                                     ("Mot de passe", "•" * min(10, len(c["password"]))), ("Format", fq),
                                     ("Nom", c["name"])],
                "fm": lambda: [("Carte son", c.get("device") or "à choisir"), ("Traitement", c["processing"])],
                "dab": lambda: [("Mode", c["mode"]), ("Destination", c["dest"]), ("Débit", c["bitrate"] + " kbit/s")],
                "record": lambda: [("Dossier", c["folder"]), ("Format", fq), ("Découpage", c["rotate"] + " min")]}[k]()
        a = self.app

        def apply():
            a.outputs_cfg.append(c)
            a.refresh_outputs()
            a.select_output_id(c["id"])
            a.note_restart()
            a.save_all()
            a.log(f"Gaël : flux « {c['name']} » créé.")
            follow = [("Voir dans Diffusion", lambda: a.go_tab("diff"))]
            if k == "internet":
                follow.insert(0, ("Tester le serveur", lambda: self.test_server(c), "primary"))
            QTimer.singleShot(300, lambda: self.say(f"C'est fait : « {c['name']} » est ajouté et actif. Il partira au prochain démarrage de la diffusion.", "bot", follow))

        def adjust():
            d = OutputDialog(a, c)
            if d.exec() and d.result:
                a.outputs_cfg.append(d.result)
                a.refresh_outputs()
                a.select_output_id(d.result["id"])
                a.note_restart()
                a.log(f"Gaël : flux « {d.result['name']} » créé.")
                self.say(f"C'est fait : « {d.result['name']} » est ajouté.", "bot")
        return self.propose("Nouveau flux " + KINDS[k][1], rows, apply, "Créer le flux", [("Ajuster avant…", adjust)])

    def test_server(self, c):
        self.say(f"Je teste {c['host']}:{c['port']}…", "bot")

        def work():
            t0 = time.time()
            try:
                socket.create_connection((c["host"], int(c["port"])), timeout=4).close()
                msg = f"Le serveur {c['host']}:{c['port']} répond ({(time.time() - t0) * 1000:.0f} ms). Le mot de passe sera vérifié au démarrage du flux."
            except Exception as e:
                msg = f"Le serveur ne répond pas : {e}.\nVérifie l'adresse, le port et ta connexion Internet."
            self.app.bridge.call.emit(lambda: self.say(msg, "bot"))
        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------- secours, gain, débit, alertes
    def p_fallback(self, q, n):
        a = self.app
        off = self.has(n, "desactiv", "coupe", "eteins", "enleve", "arrete la bascule", "pas de secours")
        thr = self.num(n, r"seuil[^\d-]*(-?\d+)")
        dly = self.num(n, r"(?:apres|delai|au bout de)[^\d]*(\d+)\s*(?:s|sec)")
        rows, ops = [], []
        if not off:
            rows.append(("Lancer la playlist de secours si le signal disparaît", "oui"))
            ops.append(lambda: a.sw_fb.setChecked(True))
        else:
            rows.append(("Lancer la playlist de secours si le signal disparaît", "non"))
            ops.append(lambda: a.sw_fb.setChecked(False))
        if thr is not None:
            thr = -abs(thr)
            rows.append(("Seuil de silence", f"{thr:.0f} dB"))
            ops.append(lambda: a.fb_ed["threshold"].setText(f"{thr:.0f}"))
        if dly is not None:
            rows.append(("Délai avant bascule", f"{dly:.0f} s"))
            ops.append(lambda: a.fb_ed["silence_s"].setText(f"{dly:.0f}"))
        extra = []
        if not off and not a.playlist:
            rows.append(("Attention", "la playlist de secours est vide"))
            extra.append(("Ajouter des morceaux…", a.pl_add))
        return self.propose("Playlist de secours", rows, lambda: ([f() for f in ops], a.live_fb(), a.log("Gaël : réglages du secours appliqués.")), extra=extra)

    def p_gain(self, n):
        a = self.app
        cur = a.sl_gain.value()
        v = self.num(n, r"([+-]?\d+)\s*(?:db|decibel)?")
        if self.has(n, "a zero", "a 0", "remet", "reinitialis"):
            new = 0
        elif v is not None and self.has(n, "monte", "augmente", "plus fort", "hausse"):
            new = cur + abs(v)
        elif v is not None and self.has(n, "baisse", "diminue", "moins fort"):
            new = cur - abs(v)
        elif v is not None:
            new = v
        elif self.has(n, "monte", "augmente", "plus fort"):
            new = cur + 3
        elif self.has(n, "baisse", "diminue", "moins fort"):
            new = cur - 3
        else:
            return (f"Le gain d'entrée est à {cur:+d} dB. Dis-moi par exemple « monte le gain de 3 dB » ou « gain à -2 ».", None)
        new = int(_cl(new, -12, 12))
        return self.propose("Gain d'entrée", [("Actuel", f"{cur:+d} dB"), ("Nouveau", f"{new:+d} dB")],
                            lambda: (a.sl_gain.setValue(new), a.log(f"Gaël : gain d'entrée réglé à {new:+d} dB.")))

    def p_bitrate(self, n):
        a = self.app
        v = int(self.num(n, r"(\d{2,3})"))
        outs = [c for c in a.outputs_cfg if c["type"] in ("internet", "record", "dab")]
        if not outs:
            return ("Il n'y a pas encore de flux dont on peut régler le débit. Tu veux que je crée un flux Internet ?",
                    [("Créer un flux Internet", lambda: self.ask("Créer un flux Internet"), "primary")])
        named = self.find_output(n.split("flux", 1)[1] if "flux" in n else "") if "flux" in n else None
        tgt = [named] if named else [c for c in outs if c["type"] == "internet"] or outs
        return self.propose("Débit", [("Flux", ", ".join(c["name"] for c in tgt)), ("Nouveau débit", f"{v} kbit/s")],
                            lambda: ([c.__setitem__("bitrate", str(v)) for c in tgt], a.refresh_outputs(), a.note_restart(),
                                     a.log(f"Gaël : débit réglé à {v} kbit/s.")))

    def p_alerts(self, q, n):
        a = self.app
        c = a.data["alerts"]
        mail = MAIL_RE.search(q)
        phone = PHONE_RE.search(q)
        url = URL_RE.search(q)
        rows, ops = [], []
        if mail:
            rows.append(("Mail vers", mail.group(0)))
            ops.append(lambda: c.update(mail_to=mail.group(0), mail_on=True))
            if not c.get("mail_host"):
                dom = mail.group(0).split("@")[1].lower()
                host = {"gmail.com": "smtp.gmail.com", "outlook.fr": "smtp-mail.outlook.com", "outlook.com": "smtp-mail.outlook.com",
                        "hotmail.fr": "smtp-mail.outlook.com", "hotmail.com": "smtp-mail.outlook.com", "orange.fr": "smtp.orange.fr",
                        "free.fr": "smtp.free.fr", "laposte.net": "smtp.laposte.net", "yahoo.fr": "smtp.mail.yahoo.com"}.get(dom)
                if host:
                    rows.append(("Serveur d'envoi suggéré", f"{host} : 587"))
                    ops.append(lambda: c.update(mail_host=host, mail_port=587, mail_tls=True, mail_from=c.get("mail_from") or mail.group(0),
                                                mail_user=c.get("mail_user") or mail.group(0)))
        if phone:
            num = re.sub(r"[\s.-]", "", phone.group(0))
            rows.append(("SMS vers", num))
            ops.append(lambda: c.update(sms_to=num, sms_on=True))
        if url and ("discord" in url.group(0) or "ntfy" in url.group(0) or "slack" in url.group(0)):
            u = url.group(0).rstrip(".,;)")
            kind = "Discord" if "discord" in u else ("ntfy" if "ntfy" in u else "Slack")
            rows.append(("Message", f"{kind} · {u[:48]}…" if len(u) > 48 else f"{kind} · {u}"))
            ops.append(lambda: c.update(kind=kind, url=u))
        if not rows:
            if self.has(n, "sms", "texto"):
                return ("Pour les SMS, le plus simple est Free Mobile (gratuit pour les abonnés) : active « Notifications par SMS » dans ton espace abonné, "
                        "puis donne-moi ton numéro, ou ouvre la fenêtre des alertes.",
                        [("Configurer les alertes", a.alert_dialog, "primary")])
            if self.has(n, "mail", "courriel"):
                return ("Donne-moi l'adresse à prévenir (par exemple « préviens benevole@radio.bzh ») et je prépare le réglage.",
                        [("Configurer les alertes", a.alert_dialog, "primary")])
            return None
        need = []
        if mail and not (c.get("mail_pw") and c.get("mail_host")):
            need.append("le mot de passe d'application du compte d'envoi")
        if phone and not c.get("sms_key"):
            need.append("l'identifiant et la clé SMS")

        def apply():
            for f in ops:
                f()
            a.save_all()
            a.alert_summary()
            a.log("Gaël : destinataires des alertes enregistrés.")
            if need:
                QTimer.singleShot(300, lambda: self.say("C'est noté. Il reste " + " et ".join(need) + " : je t'ouvre la fenêtre pour finir ?", "bot",
                                                        [("Terminer la configuration", a.alert_dialog, "primary")]))
            else:
                QTimer.singleShot(300, lambda: self.say("C'est prêt. Envoie un test pour vérifier.", "bot", [("Envoyer un test", a.alert_test, "primary")]))
        return self.propose("Prévenir en cas de panne", rows, apply)


# ------------------------------------------------------------------ téléphone animé (module « Prévenir en cas de panne »)
class PhoneAnim(QWidget):
    """Smartphone qui vibre et reçoit une notification ; muet avec pastille rouge tant que personne n'est prévenu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(130, 164)
        self.ok, self.channels = False, []
        self.clock = QElapsedTimer()
        self.clock.start()
        Ticker.add(self, lambda t, dt: self.tick(), 60, always=True)

    def set_small(self, on):
        if on != getattr(self, "_small", False):
            self._small = on
            self.setFixedSize(*((104, 132) if on else (130, 164)))
            self.update()

    def set_state(self, ok, channels):
        if (ok, channels) != (self.ok, channels):
            self.ok, self.channels = ok, list(channels)
            self.clock.restart()
            self.update()

    def tick(self):
        """Ne repeint que quand quelque chose bouge : la vibration (60 i/s), la notification qui glisse et la pastille qui
        pulse (30 i/s). Le reste du cycle de 4,2 s, le téléphone est immobile : une seule image (et une par minute pour l'heure)."""
        if not self.isVisible() or calm() or (self.window() and self.window().isMinimized()):
            return
        mn = time.strftime("%H:%M")
        if not ANIM:
            if mn != getattr(self, "_mn", None):
                self._mn = mn
                self.update()
            return
        t = self.clock.elapsed() / 1000.0
        cyc = t % 4.2
        vib = .38 < cyc < 1.62
        slide = .53 < cyc < .97 or 3.58 < cyc < 4.02 or not self.ok
        self._n = getattr(self, "_n", 0) + 1
        if vib or (slide and self._n % 2 == 0):
            self._was = True
            self.update()
        elif (not vib and not slide and getattr(self, "_was", True)) or mn != getattr(self, "_mn", None):
            self._was = False
            self._mn = mn
            self.update()

    def paintEvent(self, e):
        p = new_painter(self)
        W, H = self.width(), self.height()
        t = self.clock.elapsed() / 1000.0 if ANIM else 1.2
        cyc = t % 4.2
        ring = 0.0 if not ANIM else (1.0 if .4 < cyc < 1.6 else 0.0)
        env = win(cyc, .4, .55) * (1 - win(cyc, 1.45, 1.6))
        wob = math.sin(t * 52) * 3.2 * env
        notif = win(cyc, .55, .95) * (1 - win(cyc, 3.6, 4.0))
        if getattr(self, "_small", False):          # version réduite : même dessin, à l'échelle 0,8
            p.scale(.8, .8)
            W, H = 130, 164
        cx, cy = W / 2, H / 2 + 4
        col = QColor(OKC if self.ok else BADC)
        # ondes de vibration
        if env > 0:
            for side in (-1, 1):
                for k in range(2):
                    c = QColor(col)
                    c.setAlphaF(.55 * env * (1 - k * .45))
                    p.setPen(QPen(c, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    r = 46 + k * 9 + math.sin(t * 20) * 1.5
                    a0 = 150 if side < 0 else -30
                    p.drawArc(QRectF(cx - r, cy - r - 6, 2 * r, 2 * r), int((a0) * 16), int(60 * 16))
        p.save()
        p.translate(cx, cy)
        p.rotate(wob)
        pw, ph = 82, 132
        body = QRectF(-pw / 2, -ph / 2, pw, ph)
        scr = body.adjusted(4, 4, -4, -4)
        if wob == 0.0:                               # téléphone immobile : corps recopié depuis une image pré-rendue
            dpr = p.device().devicePixelRatioF() * (.8 if getattr(self, "_small", False) else 1.0)
            key = (self.ok, time.strftime("%H:%M"), round(dpr, 3))
            if getattr(self, "_bk", None) != key:
                pm = QPixmap(int(math.ceil(100 * dpr)), int(math.ceil(150 * dpr)))
                pm.setDevicePixelRatio(dpr)
                pm.fill(Qt.GlobalColor.transparent)
                q = new_painter(pm)
                q.translate(50, 70)
                self._body(q, body)
                q.end()
                self._bpm, self._bk = pm, key
            p.drawPixmap(QPointF(-50, -70), self._bpm)
        else:
            self._body(p, body)
        # notification qui glisse
        if notif > 0:
            nr = QRectF(scr.left() + 4, scr.top() + 44 - (1 - notif) * 14, scr.width() - 8, 38)
            p.setOpacity(notif)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(nr, 9, 9)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(nr.left() + 5, nr.top() + 6, 12, 12), 4, 4)
            f2 = QFont(self.font())
            f2.setPointSizeF(6.6)
            f2.setBold(True)
            p.setFont(f2)
            p.setPen(QColor("#10131b"))
            p.drawText(QRectF(nr.left() + 21, nr.top() + 5, nr.width() - 23, 14), Qt.AlignmentFlag.AlignVCenter, "Studio" if self.ok else "Alertes")
            f2.setBold(False)
            p.setFont(f2)
            p.setPen(QColor("#4a5266"))
            txt = ("Je veille" if self.ok else "désactivées")
            p.drawText(QRectF(nr.left() + 6, nr.top() + 20, nr.width() - 10, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)
            p.setOpacity(1)
        p.restore()
        # pastille d'état
        bc = QPointF(cx + 34, cy - 58)
        pulse = (math.sin(t * 4) + 1) / 2 if (ANIM and not self.ok) else 0
        if pulse:
            c = QColor(col)
            c.setAlphaF(.35 * (1 - pulse))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(bc, 10 + 5 * pulse, 10 + 5 * pulse)
        p.setPen(QPen(QColor(PANEL), 2.5))
        p.setBrush(col)
        p.drawEllipse(bc, 10, 10)
        p.setPen(ppen("#ffffff", 2.2))
        if self.ok:
            p.drawPolyline([QPointF(bc.x() - 4, bc.y()), QPointF(bc.x() - 1, bc.y() + 3), QPointF(bc.x() + 4.5, bc.y() - 3.5)])
        else:
            p.drawLine(QPointF(bc.x(), bc.y() - 5), QPointF(bc.x(), bc.y() + 1))
            p.drawPoint(QPointF(bc.x(), bc.y() + 4.5))

    def _body(self, p, body):
        """Corps du téléphone (ombre, écran, heure, cloche), dans le repère centré du téléphone."""
        # ombre douce
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(4):
            p.setBrush(QColor(0, 0, 0, 16))
            p.drawRoundedRect(body.adjusted(-i, 2 + i, i, 3 + i), 16, 16)
        g = QLinearGradient(body.topLeft(), body.bottomRight())
        g.setColorAt(0, QColor("#3a4152"))
        g.setColorAt(1, QColor("#1d2230"))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(body, 16, 16)
        scr = body.adjusted(4, 4, -4, -4)
        sg = QLinearGradient(scr.topLeft(), scr.bottomRight())
        if self.ok:
            sg.setColorAt(0, mixc("#0b1020", ACC, .35))
            sg.setColorAt(1, mixc("#0b1020", "#a76bff" if PSYCHE else ACC2, .30))
        else:
            sg.setColorAt(0, QColor("#141824"))
            sg.setColorAt(1, QColor("#0d1018"))
        p.setBrush(QBrush(sg))
        p.drawRoundedRect(scr, 13, 13)
        p.setBrush(QColor("#0b0e15"))
        p.drawRoundedRect(QRectF(-11, scr.top() + 4, 22, 6), 3, 3)
        # heure
        f = QFont(self.font())
        f.setPointSizeF(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(QRectF(scr.left(), scr.top() + 14, scr.width(), 22), Qt.AlignmentFlag.AlignCenter, time.strftime("%H:%M"))
        # cloche (barrée si personne n'est prévenu)
        bx, by = 0, scr.bottom() - 22
        p.setPen(ppen(QColor(255, 255, 255, 150), 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        bell = QPainterPath(QPointF(bx - 7, by + 4))
        bell.cubicTo(QPointF(bx - 6, by - 8), QPointF(bx + 6, by - 8), QPointF(bx + 7, by + 4))
        bell.closeSubpath()
        p.drawPath(bell)
        p.drawLine(QPointF(bx - 2, by + 7), QPointF(bx + 2, by + 7))
        if not self.ok:
            p.setPen(ppen(BADC, 2))
            p.drawLine(QPointF(bx - 9, by - 8), QPointF(bx + 9, by + 8))


class HeroCard(Card):
    """Carte mise en avant : halo coloré selon l'état (vert = protégé, rouge = personne n'est prévenu)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.col = BADC

    def set_color(self, c):
        if c != self.col:
            self.col = c
            self.update()

    def paintEvent(self, e):
        # fond dégradé mis en cache à la taille de la carte : le téléphone animé posé dessus ne fait plus retracer la carte
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr, self.col)
        if getattr(self, "_bgk", None) != key:
            pm = QPixmap(max(1, int(math.ceil(self.width() * dpr))), max(1, int(math.ceil(self.height() * dpr))))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            r = QRectF(self.rect()).adjusted(1, 1, -1, -2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc("#000000", 18 if not LIGHT else 10))
            p.drawRoundedRect(r.translated(0, 2), 18, 18)
            g = QLinearGradient(r.topLeft(), r.topRight())
            g.setColorAt(0, mixc(PANEL, self.col, .13) if not MINI else QColor(PANEL))
            g.setColorAt(.55, QColor(PANEL))
            g.setColorAt(1, mixc(PANEL, ACC, .05) if not MINI else QColor(PANEL))
            p.setBrush(QBrush(g))
            p.setPen(QPen(mixc(LINE, self.col, .55) if not MINI else QColor(LINE), 1.2))
            p.drawRoundedRect(r, 18, 18)
            p.end()
            self._bgpm, self._bgk = pm, key
        er = e.rect()
        p = QPainter(self)
        p.drawPixmap(QRectF(er), self._bgpm, QRectF(er.x() * dpr, er.y() * dpr, er.width() * dpr, er.height() * dpr))

# ------------------------------------------------------------------ Gaël : conversation avancée (optionnelle) via l'API Claude
# Activée seulement si une clé API est saisie dans Réglages. Gaël parle alors librement, en français, et peut utiliser
# des « outils » : lire l'état de l'antenne, lancer un diagnostic, et PROPOSER des réglages (toujours validés par un clic).
# Aucun mot de passe ni clé n'est envoyé : l'état transmis est nettoyé. Sans clé ou sans Internet, Gaël répond en local.

GAEL_SYSTEM = """Tu es Gaël, le radio-bot de l'application de diffusion radio « {app} », portée par des radios associatives de Bretagne.
Tu as l'apparence d'un petit robot breton en marinière, avec un béret à pompon rouge et une antenne qui capte les ondes.
Tu parles en français, tu tutoies, chaleureux et direct, avec à l'occasion un mot de breton (demat, trugarez, kenavo) sans en abuser.
Tu réponds comme dans une vraie conversation : phrases courtes, pas de listes à rallonge, pas de titres markdown, pas de gras.
Les utilisateurs sont souvent bénévoles et pas techniciens : explique simplement, sans jargon inutile.
Tu peux aider sur tout ce qui touche la radio, le streaming (Icecast, Shoutcast), la FM, le DAB+, le son, l'enregistrement, le réseau,
et bavarder un peu ; si on te demande autre chose, réponds brièvement puis reviens gentiment à l'antenne.
Pour modifier un réglage, utilise toujours l'outil adapté : il affiche une carte « Réglage proposé » avec un bouton que l'utilisateur
doit cliquer ; ne prétends jamais avoir modifié quelque chose toi-même. S'il manque une information indispensable
(adresse du serveur, mot de passe source…), demande-la d'abord. Ne demande jamais de mot de passe d'administration.
Quand tu as besoin de connaître la situation, appelle get_state ; pour un problème, run_diagnostic.
Onglets de l'application : Diffusion (source audio, flux, secours, à l'antenne), Processeur d'antenne (bêta, temps réel : 4 banques A-D, une banque par flux, préréglages radio, réglage à zéro, bypass, densité, égalisation, multibande simplifié, stéréo), Cartoucheur, Enregistrement (dont la pige ARCOM),
Monitoring (surveillance de flux), Réseau (liens Internet et bascule), SOS (toi, alertes de panne, journal), Réglages, À propos.
État actuel au moment du message :
{state}"""


def _tool(name, desc, props=None, req=()):
    return {"name": name, "description": desc,
            "input_schema": {"type": "object", "properties": props or {}, "required": list(req)}}


GAEL_TOOLS = [
    _tool("get_state", "État détaillé de l'antenne : diffusion, flux et leur état, secours, entrée audio, réseau, alertes, monitoring."),
    _tool("run_diagnostic", "Lance le diagnostic complet (ffmpeg, encodeurs, entrées audio, serveurs des flux, disques) ; le rapport s'affiche dans la discussion."),
    _tool("read_journal", "Dernières lignes du journal d'antenne (erreurs comprises).", {"n": {"type": "integer", "description": "nombre de lignes (max 80)"}}),
    _tool("propose_internet_stream", "Propose de créer un flux Internet (Icecast ou Shoutcast). Demande d'abord le serveur et le mot de passe source s'ils manquent.",
          {"host": {"type": "string"}, "port": {"type": "string"}, "mount": {"type": "string", "description": "point de montage Icecast, ex. /live"},
           "password": {"type": "string", "description": "mot de passe SOURCE"}, "protocol": {"type": "string", "enum": ["Icecast", "Shoutcast"]},
           "format": {"type": "string", "enum": ["MP3", "AAC", "OGG Vorbis", "Opus", "FLAC"]}, "bitrate": {"type": "string"}, "name": {"type": "string"}},
          ("host", "password")),
    _tool("propose_fm_or_dab_stream", "Propose de créer une sortie FM (carte son vers l'émetteur) ou DAB+.", {"kind": {"type": "string", "enum": ["fm", "dab"]}}, ("kind",)),
    _tool("propose_fallback", "Propose d'activer ou désactiver le secours automatique, avec seuil de silence (dB, négatif) et délai (s).",
          {"enabled": {"type": "boolean"}, "threshold_db": {"type": "number"}, "delay_s": {"type": "number"}}, ("enabled",)),
    _tool("propose_gain", "Propose un nouveau gain d'entrée en dB (-12 à +12).", {"db": {"type": "number"}}, ("db",)),
    _tool("propose_delay", "Propose le retard de sécurité avant l'antenne, en secondes (0 à 40).", {"seconds": {"type": "number"}}, ("seconds",)),
    _tool("propose_bitrate", "Propose un débit (kbit/s) pour les flux Internet, ou pour un flux précis.", {"kbps": {"type": "integer"}, "stream": {"type": "string"}}, ("kbps",)),
    _tool("propose_toggle_stream", "Propose d'activer ou désactiver un flux existant.", {"stream": {"type": "string"}, "enabled": {"type": "boolean"}}, ("stream", "enabled")),
    _tool("propose_alerts", "Propose de prévenir quelqu'un en cas de panne (mail, numéro de mobile pour SMS, lien Discord / ntfy / Slack).",
          {"email": {"type": "string"}, "phone": {"type": "string"}, "webhook": {"type": "string"}}),
    _tool("propose_monitor", "Propose d'ajouter une adresse de flux au monitoring.", {"url": {"type": "string"}}, ("url",)),
    _tool("propose_broadcast", "Propose de démarrer ou d'arrêter la diffusion.", {"action": {"type": "string", "enum": ["start", "stop"]}}, ("action",)),
    _tool("open_tab", "Ouvre un onglet de l'application.", {"tab": {"type": "string", "enum": ["diff", "son", "cart", "rec", "mon", "net", "sos", "set", "about"]}}, ("tab",)),
    _tool("play_animation", "Gaël fait une petite animation sous le menu (pour le plaisir).", {"name": {"type": "string", "enum": ["gavotte", "crepes", "crachin", "goeland", "cafe", "etire", "hoquet", "bagad", "mixage", "fierte", "antenne"]}}, ("name",)),
]


class GaelLLM:
    history = None

    def llm_cfg(self):
        S = self.app.data.get("settings", {})
        return (S.get("gael_key") or "").strip(), S.get("gael_model") or LLM_MODELS[0][0], bool(S.get("gael_ai", True))

    def llm_on(self):
        key, _, on = self.llm_cfg()
        return bool(key) and on

    # --- état transmis (sans aucun secret)
    def llm_state(self):
        a, e = self.app, self.app.engine
        L = []
        L.append("Diffusion : " + (self.state().replace("\n", " ") if a.on_air else ("contrôle d'entrée / cartoucheur seul" if a.preview else "arrêtée")))
        L.append(f"Entrée audio : {a.cur_device or 'aucune'} ; gain {a.sl_gain.value():+d} dB")
        for c in a.outputs_cfg:
            o = e.output(c["id"]) if (e and not a.preview) else None
            d = a.describe(c)
            L.append(f"Flux « {c['name']} » ({KINDS[c['type']][1]}, {d}, {'actif' if c.get('enabled', True) else 'désactivé'}"
                     + (f", {fmt_quality(c.get('format', ''), c.get('bitrate', ''))}" if c["type"] == "internet" else "")
                     + (f", état : {o.status_text()}" if o else "") + ")")
        if not a.outputs_cfg:
            L.append("Aucun flux configuré.")
        L.append(f"Secours : {'activé' if a.sw_fb.isChecked() else 'désactivé'}, seuil {a.fb_ed['threshold'].text()} dB, délai {a.fb_ed['silence_s'].text()} s, "
                 f"{len(a.playlist)} titres dans la playlist")
        L.append(f"Retard de sécurité : {a.sp_delay.value()} s")
        ch = a.alerts.channels()
        L.append("Alertes de panne : " + (", ".join(ch) if ch else "personne n'est prévenu"))
        act = getattr(a, "net_active", None)
        if act:
            st = a.net_stats.get(act) or {}
            L.append(f"Internet : {a.net_label(act)} ({a.net_kind(act)})" + (f", {st.get('lat', 0):.0f} ms" if st.get("lat") is not None else ""))
        if a.mon_streams:
            L.append("Monitoring : " + ", ".join(f"{s['name']} ({(a.mon_state.get(s['url']) or ('?', 'pas encore vérifié'))[1]})" for s in a.mon_streams[:6]))
        t = time.localtime()
        L.append(f"Date et heure : {JOURS[t.tm_wday]} {t.tm_mday} {MOIS[t.tm_mon - 1]} {t.tm_year}, {t.tm_hour} h {t.tm_min:02d}")
        return "\n".join(L)

    # --- exécution des outils (dans le fil de l'interface)
    def llm_tool(self, name, inp):
        a = self.app
        show = lambda r: (self.say_reply(r), "Carte « Réglage proposé » affichée : l'utilisateur doit cliquer pour appliquer.")[1]
        if name == "get_state":
            return self.llm_state()
        if name == "run_diagnostic":
            a.run_diag()
            return "Diagnostic lancé : son rapport va s'afficher dans la discussion d'ici quelques secondes."
        if name == "read_journal":
            n = max(5, min(80, int(inp.get("n") or 30)))
            return "\n".join(a.log_lines[-n:]) or "(journal vide)"
        if name == "propose_internet_stream":
            self.pending = {"kind": "internet", "slots": {k: str(v) for k, v in inp.items() if v not in (None, "")}, "ask": None}
            return show(self.stream_proposal())
        if name == "propose_fm_or_dab_stream":
            self.pending = {"kind": inp.get("kind", "fm"), "slots": {}, "ask": None}
            return show(self.stream_proposal())
        if name == "propose_fallback":
            txt = ("active" if inp.get("enabled", True) else "desactive") + " le secours"
            if inp.get("threshold_db") is not None:
                txt += f" seuil {abs(float(inp['threshold_db'])):.0f}"
            if inp.get("delay_s") is not None:
                txt += f" apres {float(inp['delay_s']):.0f} s"
            return show(self.p_fallback(txt, txt))
        if name == "propose_gain":
            return show(self.p_gain(f"gain a {int(round(float(inp.get('db', 0))))}"))
        if name == "propose_delay":
            v = int(_cl(float(inp.get("seconds", 0)), 0, 40))
            return show(self.propose("Retard de sécurité", [("Retard avant l'antenne", f"{v} s")],
                                     lambda: (a.sp_delay.setValue(v), a.log(f"Gaël : retard de sécurité réglé à {v} s."))))
        if name == "propose_bitrate":
            return show(self.p_bitrate(f"debit {int(inp.get('kbps', 128))} " + (f"flux {inp['stream']}" if inp.get("stream") else "")))
        if name == "propose_toggle_stream":
            c = self.find_output(norm_txt(inp.get("stream", "")))
            if not c:
                return "Aucun flux ne correspond à ce nom. Flux existants : " + ", ".join(x["name"] for x in a.outputs_cfg)
            return show(self.toggle_proposal(c, bool(inp.get("enabled"))))
        if name == "propose_alerts":
            q = " ".join(str(inp.get(k) or "") for k in ("email", "phone", "webhook"))
            r = self.p_alerts(q, norm_txt(q))
            return show(r) if r else "Il me faut une adresse mail, un numéro de mobile ou un lien de webhook."
        if name == "propose_monitor":
            u = inp.get("url", "")
            return show(self.propose("Surveiller un flux", [("Adresse", u)], lambda: (a.mon_add(None, u), a.go_tab("mon")), "Ajouter au monitoring"))
        if name == "propose_broadcast":
            if inp.get("action") == "stop":
                if not a.on_air:
                    return "Rien n'est à l'antenne."
                self.say("Tu confirmes l'arrêt de la diffusion ?", "bot", [("Arrêter la diffusion", a.stop, "danger"), ("Non, on continue", lambda: None)])
            else:
                if a.on_air:
                    return "La diffusion tourne déjà."
                self.say("On lance la diffusion avec les flux actifs ?", "bot", [("Démarrer la diffusion", a.start, "primary"), ("Pas maintenant", lambda: None)])
            return "Bouton de confirmation affiché."
        if name == "open_tab":
            k = inp.get("tab", "diff")
            QTimer.singleShot(300, lambda: a.go_tab(k))
            return f"Onglet {PAGE_TITLES.get(k, k)} ouvert."
        if name == "play_animation":
            if hasattr(a.rail, "gael"):
                a.rail.gael.play(inp.get("name", "gavotte"))
            return "Animation lancée sous le menu."
        return "Outil inconnu."

    def on_ui(self, fn):
        """Exécute fn dans le fil de l'interface et attend son résultat (appelé depuis le fil réseau)."""
        box, ev = {}, threading.Event()

        def run():
            try:
                box["r"] = fn()
            except Exception as ex:
                box["r"] = f"Erreur : {ex}"
            ev.set()
        self.app.bridge.call.emit(run)
        ev.wait(20)
        return box.get("r", "Pas de réponse de l'interface.")

    # --- conversation
    def llm_ask(self, q):
        key, model, _ = self.llm_cfg()
        if self.history is None:
            self.history = []
        self.history = self.history[-23:]
        # l'historique doit commencer par une vraie question : un message « résultats d'outils » en tête (son appel d'outil
        # ayant été coupé par la limite) fait refuser toutes les demandes suivantes par l'API (erreur 400)
        while self.history and not (self.history[0]["role"] == "user" and isinstance(self.history[0]["content"], str)):
            self.history.pop(0)
        mark = len(self.history)
        self.history.append({"role": "user", "content": q})
        state = self.llm_state()
        sysmsg = GAEL_SYSTEM.format(app=APP, state=state)
        box = {"b": self.stream_bubble()}

        def work():
            try:
                for _ in range(4):
                    content, stop = self.llm_call(key, model, sysmsg, box["b"])
                    self.history.append({"role": "assistant", "content": content})
                    if stop != "tool_use":
                        break
                    results = []
                    for b in content:
                        if b.get("type") == "tool_use":
                            r = self.on_ui(lambda b=b: self.llm_tool(b["name"], b.get("input") or {}))
                            results.append({"type": "tool_result", "tool_use_id": b["id"], "content": str(r)[:6000]})
                    self.history.append({"role": "user", "content": results})
                    box["b"] = self.on_ui(self.stream_bubble)
                self.app.bridge.call.emit(lambda: self.llm_done(box["b"]))
            except Exception as ex:
                msg = str(ex)
                # échec en plein échange (appel d'outil sans son résultat…) : on revient à l'historique d'avant la question,
                # sinon chaque question suivante était refusée par l'API et Gaël restait en « IA indisponible »
                del self.history[mark:]
                self.app.bridge.call.emit(lambda: self.llm_fail(q, msg, box["b"]))
        threading.Thread(target=work, daemon=True).start()

    def llm_call(self, key, model, sysmsg, bubble):
        import urllib.request
        body = json.dumps({"model": model, "max_tokens": 900, "system": sysmsg, "tools": GAEL_TOOLS,
                           "messages": self.history, "stream": True}).encode("utf-8")
        req = urllib.request.Request(API_URL, data=body, method="POST", headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        blocks, cur, stop, text_acc, last = [], None, None, "", 0.0
        try:
            resp = urllib.request.urlopen(req, timeout=45)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise RuntimeError({401: "clé API refusée", 403: "accès refusé", 429: "trop de demandes, réessaie dans un instant",
                                529: "service surchargé"}.get(e.code, f"erreur {e.code}") + (f" ({detail})" if e.code not in (401, 429) else ""))
        with resp:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                try:
                    ev = json.loads(line[5:].strip())
                except ValueError:
                    continue
                t = ev.get("type")
                if t == "content_block_start":
                    cb = dict(ev["content_block"])
                    if cb.get("type") == "tool_use":
                        cb["_json"] = ""
                    blocks.append(cb)
                    cur = cb
                elif t == "content_block_delta" and cur is not None:
                    d = ev["delta"]
                    if d.get("type") == "text_delta":
                        cur["text"] = cur.get("text", "") + d["text"]
                        text_acc += d["text"]
                        if bubble is not None and time.time() - last > .04:
                            last = time.time()
                            txt = text_acc
                            self.app.bridge.call.emit(lambda txt=txt: self.stream_update(bubble, txt))
                    elif d.get("type") == "input_json_delta":
                        cur["_json"] += d.get("partial_json", "")
                elif t == "content_block_stop" and cur is not None:
                    if cur.get("type") == "tool_use":
                        try:
                            cur["input"] = json.loads(cur.pop("_json") or "{}")
                        except ValueError:
                            cur["input"] = {}
                    cur = None
                elif t == "message_delta":
                    stop = ev.get("delta", {}).get("stop_reason", stop)
                elif t == "error":
                    raise RuntimeError(ev.get("error", {}).get("message", "erreur du service"))
        if bubble is not None:
            self.app.bridge.call.emit(lambda: self.stream_update(bubble, text_acc, final=True))
        content = [{k: v for k, v in b.items() if not k.startswith("_")} for b in blocks]
        content = [b for b in content if not (b.get("type") == "text" and not b.get("text"))]
        return content or [{"type": "text", "text": "…"}], stop

    def llm_done(self, bubble):
        self.bot.think = False
        self.set_status()
        if bubble is not None and not bubble.property("txt"):
            bubble.parentWidget().hide()

    def llm_fail(self, q, msg, bubble):
        self.bot.think = False
        if bubble is not None and not bubble.property("txt"):
            bubble.parentWidget().hide()
        self.l_st.setText("en local (IA indisponible)")
        r = self.answer(q)
        text, acts = r if isinstance(r, tuple) else (r, None)
        self.say(text + f"\n\n(Conversation avancée indisponible : {msg}. J'ai répondu en local.)", "bot", acts)

# ------------------------------------------------------------------ SOS : ressources consommées et performances
class ResourceStrip(QWidget):
    """Bande de six indicateurs (processeur, mémoire, moteur audio, fluidité, réseau, disque) avec courbe des 60 dernières
    secondes. Mesures une fois par seconde ; dessin entièrement à la main, un seul widget : coût négligeable."""
    N = 60

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.TH, self.rows = 74, 1
        self.setFixedHeight(74)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.keys = ("cpu", "ram", "audio", "ui", "net", "disk")
        self.title = {"cpu": "PROCESSEUR", "ram": "MÉMOIRE", "audio": "MOTEUR AUDIO", "ui": "FLUIDITÉ", "net": "RÉSEAU", "disk": "DISQUE"}
        self.hist = {k: [] for k in self.keys}
        self.val = {k: "—" for k in self.keys}
        self.sub = {k: "" for k in self.keys}
        self.state = {k: "ok" for k in self.keys}
        self.ps, self.proc = None, None
        try:
            import psutil
            self.ps = psutil
            self.proc = psutil.Process()
            self.proc.cpu_percent(None)
            psutil.cpu_percent(None)
        except Exception:
            pass
        self.t_cpu, self.t_wall = time.process_time(), time.time()
        self.frames, self.t_fr = 0, time.time()
        self.tm = QTimer(self)
        self.tm.timeout.connect(self.measure)
        self.tm.start(1000)
        self.setToolTip("Mesuré chaque seconde. Courbes : les 60 dernières secondes.")

    def frame(self):
        """Appelé par la boucle d'affichage (30 i/s visés) pour mesurer la fluidité réelle de l'interface."""
        self.frames += 1

    def push(self, k, v, val, sub="", state="ok"):
        h = self.hist[k]
        h.append(v)
        del h[:-self.N]
        self.val[k], self.sub[k], self.state[k] = val, sub, state

    def measure(self):
        a, e, now = self.app, self.app.engine, time.time()
        ncpu = os.cpu_count() or 1
        # processeur
        if self.proc is not None:
            try:
                me = self.proc.cpu_percent(None) / ncpu
                kids = self.proc.children(recursive=True)
                for c in kids:
                    try:
                        me += c.cpu_percent(None) / ncpu
                    except Exception:
                        pass
                sysc = self.ps.cpu_percent(None)
                self.push("cpu", me, f"{me:.0f} %", f"ordinateur {sysc:.0f} %", "bad" if sysc > 90 else ("warn" if sysc > 70 else "ok"))
            except Exception:
                pass
        else:
            pt = time.process_time()
            me = 100 * (pt - self.t_cpu) / max(.001, now - self.t_wall) / ncpu
            self.t_cpu, self.t_wall = pt, now
            self.push("cpu", me, f"{me:.0f} %", "application", "warn" if me > 60 else "ok")
        # mémoire
        mb = None
        try:
            if self.proc is not None:
                mb = self.proc.memory_info().rss / 1e6
                wp = a.worker_pids() if hasattr(a, "worker_pids") else set()
                n = 0
                for c in self.proc.children(recursive=True):
                    if c.pid in wp:
                        try:
                            mb += c.memory_info().rss / 1e6
                        except Exception:
                            pass
                    else:
                        n += 1
                sub = f"{n} processus ffmpeg" if n else "sans encodeur actif"
            else:
                import resource
                mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1e3 if SYS != "Darwin" else 1e6)
                sub = "application"
        except Exception:
            sub = "installe psutil pour le détail"
        if mb is not None:
            self.push("ram", mb, f"{mb:.0f} Mo", sub, "warn" if mb > 1500 else "ok")
        # moteur audio
        if e:
            load = 100 * e.proc_ms / 20.0
            late = e.late
            self.push("audio", load, f"{e.proc_ms:.1f} ms", f"{load:.0f} % du temps · {late} retard{'s' if late > 1 else ''}",
                      "bad" if load > 80 or e.slow_now() else ("warn" if load > 50 else "ok"))
        else:
            self.push("audio", 0, "arrêté", "démarre la diffusion", "idle")
        # fluidité de l'interface
        dt = max(.001, now - self.t_fr)
        fps = self.frames / dt
        self.frames, self.t_fr = 0, now
        self.push("ui", fps, f"{fps:.0f} i/s", "objectif 30 images/s", "ok" if fps >= 27 else ("warn" if fps >= 20 else "bad"))
        # réseau (lien actif)
        act = getattr(a, "net_active", None)
        rt = a.net_rate.get(act) if act else None
        if rt:
            self.push("net", rt[1], f"↑ {rt[1]:.0f} ko/s", f"↓ {rt[0]:.0f} ko/s · {a.net_label(act)}", "ok")
        else:
            self.push("net", 0, "—", "lien non mesuré", "idle")
        # disque des enregistrements
        try:
            d = a.rec_dir() or os.path.expanduser("~")
            free = shutil.disk_usage(d if os.path.isdir(d) else os.path.expanduser("~")).free / 1e9
            self.push("disk", free, f"{free:.0f} Go", "libres (enregistrements)", "bad" if free < 2 else ("warn" if free < 10 else "ok"))
        except OSError:
            pass
        if self.isVisible():
            self.update()

    def paintEvent(self, ev):
        p = new_painter(self)
        W, H = self.width(), self.height()
        n = len(self.keys)
        gap = 10
        rows = self.rows
        per = -(-n // rows)
        tw = (W - gap * (per - 1)) / per
        TH = self.TH
        cols = {"ok": OKC, "warn": "#ffb347", "bad": BADC, "idle": MUT}
        f1 = QFont(self.font())
        f1.setPointSizeF(7)
        f1.setBold(True)
        f1.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        f2 = QFont(self.font())
        f2.setPixelSize(17)
        f2.setBold(True)
        try:
            f2.setFeature(QFont.Tag("tnum"), 1)
        except Exception:
            pass
        f3 = QFont(self.font())
        f3.setPointSizeF(8)
        for i, k in enumerate(self.keys):
            p.save()
            p.translate((i % per) * (tw + gap), (i // per) * (TH + gap))
            r = QRectF(0, 0, tw, TH)
            col = QColor(cols.get(self.state[k], MUT))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(mixc(PANEL, TXT, .035))
            p.drawRoundedRect(r, 12, 12)
            # courbe
            h = self.hist[k]
            if len(h) >= 2:
                top = max(max(h) * 1.15, {"cpu": 25, "audio": 50, "ui": 70}.get(k, 1e-9))
                lo = min(h) * .9 if k in ("disk", "ram") else 0
                span = max(1e-9, top - lo)
                path = QPainterPath()
                for j, v in enumerate(h):
                    px = r.left() + 8 + (r.width() - 16) * (j + self.N - len(h)) / (self.N - 1)
                    py = r.bottom() - 6 - (r.height() * .42) * _cl((v - lo) / span)
                    path.moveTo(px, py) if j == 0 else path.lineTo(px, py)
                area = QPainterPath(path)
                area.lineTo(path.currentPosition().x(), r.bottom() - 4)
                area.lineTo(r.left() + 8 + (r.width() - 16) * (self.N - len(h)) / (self.N - 1), r.bottom() - 4)
                area.closeSubpath()
                g = QLinearGradient(0, r.center().y(), 0, r.bottom())
                g.setColorAt(0, qc(col.name(), 60))
                g.setColorAt(1, qc(col.name(), 0))
                p.setBrush(QBrush(g))
                p.drawPath(area)
                p.setPen(QPen(qc(col.name(), 200), 1.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
                p.setPen(Qt.PenStyle.NoPen)
            p.setFont(f1)
            p.setPen(QColor(MUT))
            p.drawText(QRectF(r.left() + 12, 6, tw - 30, 14), Qt.AlignmentFlag.AlignVCenter, self.title[k])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(r.right() - 12, 13), 3.2, 3.2)
            p.setFont(f2)
            p.setPen(QColor(TXT))
            p.drawText(QRectF(r.left() + 12, 19, tw - 18, 22), Qt.AlignmentFlag.AlignVCenter, self.val[k])
            p.setFont(f3)
            p.setPen(QColor(MUT))
            p.drawText(QRectF(r.left() + 12, 40, tw - 18, 14), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(f3).elidedText(self.sub[k], Qt.TextElideMode.ElideRight, int(tw - 20)))
            p.restore()

    def resizeEvent(self, e):
        """Fenêtre étroite (écran vertical) : deux rangées de trois indicateurs plutôt que six tuiles illisibles."""
        rows = 2 if (self.width() - 50) / 6 < 128 else 1
        if rows != self.rows:
            self.rows = rows
            self.setFixedHeight(self.TH * rows + 10 * (rows - 1))
        super().resizeEvent(e)


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
