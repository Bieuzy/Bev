# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - Gaël : connaissances de l'assistant, dessin de la mascotte, animations, écran de démarrage."""
from bev_maj import *  # noqa: F401,F403

class AssistantKB:
    # --- connaissances
    def state(self):
        a = self.app
        e = a.engine
        if not a.on_air:
            if a.preview:
                return "Tu es hors antenne (contrôle de l'entrée ou cartoucheur seul). Clique sur Démarrer pour émettre."
            return "Tu es hors antenne. Choisis l'entrée, ajoute au moins un flux, puis clique sur Démarrer."
        if e.mute:
            mode = "l'antenne est COUPÉE (mute)"
        elif e.tone:
            mode = "la tonalité 1 kHz est à l'antenne"
        elif e.backup:
            mode = "la playlist de secours passe" + (f" ({e.track})" if e.track else "")
        elif e.silent_ms >= 1000:
            mode = f"aucun signal d'entrée depuis {e.silent_ms // 1000} s et rien pour le remplacer"
        else:
            mode = "le direct passe normalement"
        outs = [f"{o.cfg['name']} : {o.status_text()}" for o in e.outputs if o.cfg.get("enabled", True)]
        return f"En antenne depuis {fmt_dur(time.time() - e.started)} ; {mode}.\nFlux :\n • " + "\n • ".join(outs or ["aucune"])

    def internet(self):
        a = self.app
        act = getattr(a, "net_active", None)
        if not act:
            return "Je ne sais pas encore quel lien Internet est utilisé (détection en cours, ou module psutil absent)."
        st = a.net_stats.get(act) or {}
        q = quality(st)[0] if st else "inconnue"
        return f"Internet passe par « {a.net_label(act)} » ({a.net_kind(act)}), qualité {q.lower()}."

    def alerts(self):
        ch = self.app.alerts.channels()
        base = "Une panne de plus d'1 minute (flux en erreur, plus de signal sans secours) déclenche un message."
        return base + ("\nActuellement actif : " + ", ".join(ch) + "." if ch else "\nRien n'est configuré pour l'instant.")

    def diagnose(self):
        a, e = self.app, self.app.engine
        L = []
        L.append(("OK" if shutil.which("ffmpeg") else "Problème") + " : ffmpeg " + ("trouvé" if shutil.which("ffmpeg") else "introuvable"))
        L.append("OK : entrée audio « %s »" % (a.device_name() or "?") if a.device_name() else "Problème : aucune entrée choisie")
        if e and getattr(e, "cap_state", "") == "error":
            L.append("Problème : entrée audio indisponible (" + (getattr(e, "cap_err", "") or "?") + ")")
        if e and a.on_air:
            bad = [o for o in e.outputs if o.cfg.get("enabled", True) and o.state == "error"]
            L.append(("Problème : %d flux en erreur (%s)" % (len(bad), ", ".join(o.cfg["name"] for o in bad))) if bad
                     else "OK : flux actifs sans erreur")
            L.append(("Problème : " if e.silent_ms >= 3000 else "OK : ") + ("pas de signal depuis %d s" % (e.silent_ms // 1000) if e.silent_ms >= 3000 else "signal d'entrée présent"))
            L.append(("Problème : %d blocs en retard" % e.late) if e.late > 20 else "OK : calcul audio fluide")
        else:
            L.append("Info : hors antenne, flux non testés")
        act = getattr(a, "net_active", None)
        L.append(("OK : Internet via " + a.net_label(act)) if act else "Info : lien Internet non détecté")
        L.append("OK : alertes " + ", ".join(a.alerts.channels()) if a.alerts.channels() else "Info : aucune alerte mail / SMS configurée")
        acts = [("Diagnostic complet", a.run_diag)]
        if e and any(o.state == "error" for o in e.outputs):
            acts.insert(0, ("Redémarrer les flux", a.sos_restart))
        return "\n".join(L), acts

    def journal(self):
        a = self.app
        text = "\n".join(a.log_lines[-400:])
        found = [adv for pat, adv in ADVICE if re.search(pat, text)]
        if not found:
            return "Rien d'anormal dans le journal récent."
        return "Voici ce que je vois dans le journal :\n • " + "\n • ".join(found)

    # --- base de connaissances (dépannage)
    @staticmethod
    def explain_error(detail):
        d = (detail or "").lower()
        for pat, adv in (("401", "mot de passe source refusé : vérifie le mot de passe du flux (celui de la SOURCE, pas de l'admin)"),
                         ("403", "le serveur refuse : mountpoint déjà utilisé par une autre source, ou limite de sources atteinte"),
                         ("404", "adresse introuvable : un Icecast répond 404 tant que rien n'est envoyé vers cette adresse. Vérifie que l'antenne tourne, que le flux est démarré (« Marche / arrêt ») et que le nom de l'adresse est le bon"),
                         ("refused", "connexion refusée : le serveur ne tourne pas, ou le port est faux"),
                         ("timed out", "délai dépassé : pare-feu, mauvais port ou serveur surchargé"),
                         ("timeout", "délai dépassé : pare-feu, mauvais port ou serveur surchargé"),
                         ("getaddrinfo", "nom d'hôte introuvable : vérifie l'adresse du serveur et ta connexion Internet"),
                         ("name or service", "nom d'hôte introuvable : vérifie l'adresse du serveur et ta connexion Internet"),
                         ("ssl", "problème de certificat / chiffrement : essaie le port sans SSL ou vérifie l'option SSL"),
                         ("broken pipe", "le serveur a coupé la connexion : il va se reconnecter seul"),
                         ("no such file", "fichier ou programme introuvable : vérifie le chemin indiqué")):
            if pat in d:
                return adv
        return ""

    def output_help(self):
        e, a = self.app.engine, self.app
        if not e:
            return ("Erreurs de flux les plus fréquentes :\n • 401 : mauvais mot de passe SOURCE\n • 403 : mountpoint déjà pris ou trop de sources\n"
                    " • 404 : adresse sans flux (flux arrêté, ou nom différent côté serveur)\n • connexion refusée : serveur éteint ou mauvais port\n • délai dépassé : pare-feu ou serveur injoignable\n"
                    " • hôte introuvable : adresse fausse ou pas d'Internet\nDémarre la diffusion et je te dirai laquelle s'applique.")
        L = []
        for o in e.outputs:
            if o.cfg.get("enabled", True) and o.state == "error":
                adv = self.explain_error(getattr(o, "detail", ""))
                L.append(f"• {o.cfg['name']} : {o.status_text()}" + (f"\n   → {adv}" if adv else ""))
        if not L:
            return "Tous les flux actifs sont en ligne ou en cours de connexion."
        return "Flux en erreur :\n" + "\n".join(L) + "\nUne fois corrigé, redémarre les flux."

    def kb(self):
        a = self.app
        e = lambda: a.engine
        go = lambda k, lab: [(lab, lambda: a.go_tab(k))]
        rs = [("Redémarrer les flux", a.sos_restart)]
        T = []

        def add(title, keys, fn):
            T.append((title, keys, fn))
        add("État de l'antenne", ["etat", "statut", "situation", "ca va", "tout va", "en ce moment", "antenne"],
            lambda: (self.state(), rs if (e() and any(o.state == "error" for o in e().outputs)) else None))
        add("Diagnostic", ["diagnostic", "verifie", "teste tout", "controle", "bilan", "check"], self.diagnose)
        add("Analyse du journal", ["journal", "historique des erreurs", "analyse", "logs"], lambda: (self.journal(), None))
        add("Signaler un problème", ["bug", "signaler", "rapport", "support", "plante", "plantage", "beug", "remonter", "developpeur"],
            lambda: ("Pour signaler un problème, je prépare un rapport (version, réglages, diagnostic, journaux) sans aucun mot de passe "
                     "ni coordonnée. Tu pourras l'enregistrer, le copier ou ouvrir directement la page GitHub de Bev.",
                     [("Signaler un problème", lambda: a.support_dialog())]))
        add("Flux en erreur", ["flux en erreur", "sortie en erreur", "flux", "erreur", "ne se connecte pas", "deconnecte", "serveur", "icecast", "shoutcast", "mot de passe", "401", "403", "refuse", "mountpoint", "connexion refusee", "timeout"],
            lambda: (self.output_help(), rs))
        add("Pas de son", ["pas de son", "silence", "plus de son", "rien ne sort", "muet", "inaudible", "ne s'entend pas", "on n'entend rien"],
            lambda: ("Pas de son ? Je vérifie dans l'ordre :\n 1. Entrée : le vumètre « L / R » de la source bouge-t-il ? Sinon, change d'entrée.\n"
                     " 2. Windows : Paramètres > Confidentialité > Microphone, autoriser les applications.\n 3. Le gain d'entrée n'est pas à -12 dB.\n"
                     " 4. L'antenne n'est pas en mute (SOS).\n 5. Le seuil de silence du secours n'est pas trop haut.\n"
                     + ("\nLà, tout de suite : " + self.state().splitlines()[0] if a.on_air else ""),
                     [("Voir l'entrée", lambda: (a.go_tab("diff"), a.toggle_preview() if not (a.on_air or a.preview) else None)),
                      ("Rétablir le son", a.sos_mute) if (e() and e().mute) else ("Aller à Diffusion", lambda: a.go_tab("diff"))]))
        add("Aucune entrée détectée", ["aucune entree", "entree introuvable", "micro introuvable", "carte son introuvable", "peripherique", "detecte", "liste des entrees", "microphone"],
            lambda: ("Aucune entrée détectée : branche le micro/la table de mixage puis clique sur ↻ à côté de la liste. Sous Windows, vérifie que l'appareil est "
                     "activé (Son > Enregistrement) et autorisé. Tu peux aussi taper le nom exact de l'appareil dans la liste.", go("diff", "Aller à Diffusion")))
        add("Son de l'ordinateur", ["son de l'ordinateur", "loopback", "capturer le son", "stereo mix", "mixage stereo", "audio systeme", "spotify", "navigateur"],
            lambda: "Pour diffuser le son de l'ordinateur sous Windows, installe PyAudioWPatch (bouton « Activer la capture du son de l'ordinateur » dans Diffusion), "
                    "puis choisis « Son de l'ordinateur » dans la liste des entrées.")
        add("Son saturé", ["sature", "clip", "distorsion", "trop fort", "grésille", "gresille", "craque", "ecrete", "rouge"],
            lambda: "Son saturé (CLIP) : baisse le gain d'entrée de quelques dB et vérifie que la table de mixage ne sature pas déjà. Vise des crêtes autour de -6 dB. "
                    "Le processeur d'antenne (onglet « Processeur d'antenne ») tient le niveau et garantit le plafond : vérifie qu'il n'est pas en bypass.")
        add("Son trop faible", ["trop faible", "trop bas", "volume bas", "pas assez fort", "niveau bas", "gain"],
            lambda: "Son trop faible : monte le gain d'entrée (+6 dB max), ou choisis un préréglage plus dense dans « Processeur d'antenne » (son AGC ramène les sources faibles au bon niveau).")
        add("Écho / larsen", ["echo", "larsen", "retour", "eco", "double son", "on s'entend"],
            lambda: "Écho ou larsen : coupe le haut-parleur d'écoute pendant les prises de parole, ou écoute au casque. Si l'écho vient des auditeurs, ils entendent leur radio avec le retard "
                    "du flux (10 à 30 s) : demande-leur de couper leur poste.")
        add("Saccades", ["saccade", "coupure", "hache", "lag", "bug audio", "fluide", "ralenti", "lent", "freeze", "blocs en retard"],
            lambda: ("Ça saccade : ferme les programmes lourds, installe numpy (calcul bien plus rapide), baisse le débit des flux Internet, vérifie la connexion."
                     + (f"\nMesure actuelle : {e().proc_ms:.1f} ms de calcul par bloc de 20 ms, {e().late} blocs en retard." if e() else ""), go("net", "Ouvrir Réseau")))
        add("Retard / latence", ["retard", "latence", "decalage", "delai", "delay", "dump", "en differe"],
            lambda: "Les auditeurs entendent le son avec 5 à 30 s de décalage : c'est normal pour le streaming. Le « Retard de sécurité » (SOS) garde quelques secondes avant "
                    "l'antenne ; « Supprimer l'audio retenu » efface ce tampon en cas de propos à ne pas diffuser.")
        add("Internet", ["internet", "reseau", "wifi", "4g", "5g", "rj45", "ethernet", "bascule", "connexion", "lien", "debit", "ping"],
            lambda: (self.internet(), go("net", "Ouvrir Réseau")))
        add("Bascule réseau", ["bascule impossible", "administrateur", "droits", "changer de connexion", "basculer"],
            lambda: ("La bascule automatique de connexion demande de lancer l'application en administrateur (Windows/Linux). Sans cela, elle te prévient et propose le lien à utiliser. "
                     "Active-la dans Réseau avec « Bascule automatique ».", go("net", "Ouvrir Réseau")))
        add("Titre affiché", ["titre affiche", "metadonnee", "metadata", "now playing", "titre en cours", "auditeurs voient", "nom du morceau", "pochette", "image"],
            lambda: "Le titre affiché est envoyé aux flux Internet. Tape-le dans « Titre affiché » puis Envoyer, ou active « En secours, afficher le titre de la piste jouée ». "
                    "L'image est envoyée par Image… (selon le serveur).")
        add("FM / RDS", ["fm", "emetteur", "rds", "pifm", "carte son fm", "ps rt"],
            lambda: "FM : dans le flux FM, choisis la carte son qui alimente l'émetteur. Le RDS (nom de station PS et texte RT) suit le titre en cours. "
                    "Si la liste des cartes est vide, installe sounddevice (SOS > Plus).")
        add("DAB+", ["dab", "mux", "odr", "multiplex", "audioenc", "padenc", "dls"],
            lambda: "DAB+ : le flux envoie l'audio vers ODR-AudioEnc ou ton multiplexeur (TCP ou pipe). Vérifie le chemin d'odr-audioenc et l'adresse (ex. tcp://127.0.0.1:9000) dans Modifier.")
        add("Le secours ne démarre pas", ["secours ne demarre", "secours ne se lance", "pas de secours", "secours ne marche", "playlist ne demarre", "bascule secours", "seuil"],
            lambda: ("Le secours ne démarre pas : l'option « Passer en secours si le signal disparaît » doit être active, la liste non vide, et le silence doit durer plus que le délai "
                     "(Options). Le seuil se règle sous le niveau normal de ton direct (ex. -50 dB).", go("diff", "Aller à Diffusion")))
        add("Le secours ne s'arrête pas", ["secours ne s'arrete", "revenir au direct", "retour direct", "secours reste", "forcer"],
            lambda: ("Retour au direct : le signal doit revenir au-dessus du seuil pendant le délai « Retour ». Si tu as lancé le secours à la main, clique « Revenir au direct ».",
                     [("Revenir au direct", a.toggle_manual)]))
        add("Secours : musique", ["secours", "playlist", "musique", "titre", "compteur", "moins lu", "jingle", "ajouter des morceaux"],
            lambda: ("Secours : les titres et jingles les moins lus passent en premier (compteur « lectures »). Ajoute des fichiers avec ＋ Ajouter ou en les glissant sur la liste ; "
                     "clic sur la pastille verte pour exclure un titre.", [("Lancer le secours", a.toggle_manual)]))
        add("Fichiers illisibles", ["illisible", "format", "mp3 ne joue", "fichier ne joue", "codec", "m4a", "wma"],
            lambda: "Fichier illisible : ffmpeg doit être installé et reconnaître le format. Essaie de convertir le fichier en MP3 ou WAV. Vérifie qu'il n'est pas déplacé ou protégé (DRM).")
        add("Cartoucheur", ["cartouche", "cartoucheur", "touche", "pad", "sound board", "jingle", "pub", "f1"],
            lambda: ("Cartoucheur : clic = jouer ou arrêter, clic droit = régler la touche (nom, couleur, volume, fondu). F1 à F12 au clavier, Échap = tout arrêter. "
                     "Glisse des sons sur une touche pour les affecter.", go("cart", "Ouvrir le cartoucheur")))
        add("Sortie audio du cartoucheur", ["sortie audio", "pre-ecoute", "preecoute", "casque", "ecouter avant", "sortie casque", "maj clic"],
            lambda: ("Sortie audio : choisis-la dans le cartoucheur, puis Maj + clic sur une touche (ou joue hors antenne). Il faut le module sounddevice.", go("cart", "Ouvrir le cartoucheur")))
        add("Glisser-déposer", ["glisser", "deposer", "drag", "drop"],
            lambda: ("Glisser-déposer : fonctionne directement. Dépose des sons sur une touche ou des fichiers sur la liste de secours.", go("cart", "Ouvrir le cartoucheur")))
        add("Enregistrement", ["enregistr", "record", "archive", "fichier de l'emission", "reecouter", "disque plein", "espace disque"],
            lambda: ("Enregistrement : onglet Enregistrement. L'antenne est enregistrée en fichiers découpés (par défaut toutes les 60 min) dans le dossier choisi. "
                     "Tu peux y écouter, renommer, supprimer, et régler le format et la durée de conservation.", go("rec", "Ouvrir Enregistrement")))
        add("Alertes mail / SMS", ["alerte", "mail", "sms", "panne", "notification", "prevenir", "prevenu", "email", "webhook", "discord", "slack", "ntfy"],
            lambda: (self.alerts(), [("Configurer les alertes", lambda: a.alert_dialog())]))
        add("Mail : configuration", ["gmail", "smtp", "mot de passe d'application", "mail ne part pas", "587", "465", "authentification"],
            lambda: ("Mail : pour Gmail, active la validation en 2 étapes puis crée un « mot de passe d'application » (pas ton mot de passe habituel). Serveur smtp.gmail.com, port 587 (STARTTLS) "
                     "ou 465 (SSL). Teste avec le bouton Tester de la fenêtre d'alertes.", [("Configurer les alertes", lambda: a.alert_dialog())]))
        add("SMS : configuration", ["free mobile", "twilio", "sms ne part pas", "sms free"],
            lambda: ("SMS Free Mobile : active l'option « Notifications par SMS » dans ton espace abonné, puis copie l'identifiant et la clé dans la fenêtre d'alertes. "
                     "Twilio : SID, jeton, numéro d'envoi et destinataire.", [("Configurer les alertes", lambda: a.alert_dialog())]))
        add("ffmpeg", ["ffmpeg", "introuvable", "pas installe", "winget", "ffprobe"],
            lambda: "ffmpeg est indispensable. Windows : winget install Gyan.FFmpeg puis rouvre l'application. Mac : brew install ffmpeg. Linux : sudo apt install ffmpeg.")
        add("Performances", ["cpu", "processeur", "lourd", "numpy", "performance", "ventilateur", "chauffe", "memoire", "ram"],
            lambda: ("Performances : installe numpy (calcul audio ~30× plus rapide), active « Réduire les animations » dans Réglages et ferme les autres logiciels lourds."
                     + (f"\nMesure : {e().proc_ms:.1f} ms par bloc de 20 ms." if e() else ""), go("set", "Ouvrir Réglages")))
        add("Veille de l'ordinateur", ["veille", "mise en veille", "ecran s'eteint", "se coupe la nuit", "nuit", "windows update"],
            lambda: ("Pour une antenne de nuit : active « Empêcher la mise en veille » dans Réglages, branche l'ordinateur sur secteur et mets les mises à jour automatiques en dehors des heures d'antenne.", go("set", "Ouvrir Réglages")))
        add("Apparence", ["theme", "mode clair", "mode sombre", "couleur", "accent", "apparence", "plein ecran", "f11", "taille"],
            lambda: ("Apparence : Réglages > Apparence pour le mode clair / sombre et la couleur d'accent (redémarrage nécessaire). Plein écran : touche F11.", go("set", "Ouvrir Réglages")))
        add("Démarrage automatique", ["auto-demarrage", "demarrage auto", "demarrer tout seul", "au lancement", "reboot", "redemarrage de l'ordinateur"],
            lambda: "Auto-démarrage : coche « Auto-démarrage » en haut ; l'antenne se lance 2 s après l'ouverture. Place un raccourci de l'application dans le dossier Démarrage de Windows pour qu'elle s'ouvre avec l'ordinateur.")
        add("Profils / réglages", ["profil", "reglage", "sauvegarde", "config", "perdu mes reglages", "reinitialiser", "reset", "exporter"],
            lambda: "Les réglages vivent dans le profil choisi en haut ; Enregistrer les sauvegarde. Le dossier des réglages s'ouvre depuis SOS > Plus. Réinitialiser garde une copie « .sauvegarde ».")
        add("Premiers pas", ["commencer", "debuter", "premiere fois", "premiere emission", "lancer ma premiere", "comment ca marche", "comment faire", "par ou", "tutoriel", "mode d'emploi", "demarrer une emission", "installer", "installation"],
            lambda: "Premiers pas : 1) choisis l'entrée (Source audio) ; 2) ajoute au moins un flux (Internet, FM, DAB+ ou enregistrement) ; 3) ajoute quelques morceaux au Secours ; "
                    "4) clique Démarrer. Le cartoucheur et le monitoring se règlent ensuite.")
        add("Monitoring", ["monitoring", "surveiller", "flux inactif", "ecouter le flux", "audience", "auditeurs", "verifier mon flux"],
            lambda: ("Monitoring : colle l'adresse d'un flux (bouton Coller) ; l'application vérifie régulièrement qu'il répond et qu'il y a de l'audio, et t'alerte en cas de panne.", go("mon", "Ouvrir le monitoring")))
        add("Pige ARCOM", ["pige", "arcom", "csa", "un fichier par heure", "conserver l'antenne", "obligation", "nom du fichier", "nom de fichier", "prefixe"],
            lambda: ("Pige ARCOM : dans l'onglet Enregistrement, active « Pige ARCOM » : l'antenne est enregistrée en continu, un fichier par heure pile "
                     "(par exemple Pige_2026-10-23_16h.mp3). Règle aussi le nom du fichier, le format de la date et la durée de conservation "
                     "(0 = toujours). Vérifie l'espace disque restant affiché à côté.", go("rec", "Ouvrir Enregistrement")))
        add("Dossiers de la playlist", ["dossier", "ranger", "classer", "trier la playlist", "categorie", "plusieurs playlists", "chercher un titre", "recherche", "pochette titre"],
            lambda: ("Dossiers : dans le Secours, « + Dossier » crée un dossier ; clic droit sur un titre > Ranger dans… ; clic droit sur un dossier pour le renommer, "
                     "le supprimer ou l'exclure de la rotation. Glisser un dossier du disque sur la liste le crée tout seul. La recherche filtre les titres ; "
                     "flèches, Entrée, Espace et Suppr fonctionnent au clavier.", go("diff", "Aller à Diffusion")))
        add("Tête de lecture", ["tete de lecture", "se balader", "point de depart", "demarrer au milieu", "debut du son", "forme d'onde", "onde", "ecouter un passage"],
            lambda: ("Tête de lecture : clic droit sur une touche du cartoucheur, puis fais glisser la tête sur l'onde. « Écouter ici » lit depuis ce point, "
                     "« Démarrer ici » en fait le départ de la touche.", go("cart", "Ouvrir le cartoucheur")))
        add("À propos / horloge", ["propos", "version", "heure", "horloge", "bretagne", "projet", "credit", "qui a fait", "createur", "auteur", "logiciel", "licence", "qui a cree"],
            lambda: "L'horloge avec secondes est en haut à droite. Projet porté par des radios associatives de Bretagne : voir l'onglet À propos.")
        add("Qui es-tu ?", ["gael", "bonjour", "salut", "coucou", "hello", "demat", "qui es", "tu es", "aide", "que sais-tu", "que peux-tu"],
            lambda: ("Demat ! Je suis Gaël. Je sais lire l'état de l'antenne, expliquer une erreur de flux, dépanner le son, le réseau, le secours, le cartoucheur, "
                     "les alertes ou l'enregistrement, faire un diagnostic, et régler pour toi : créer un flux, activer le secours, configurer les alertes, ajuster le gain…", [("Diagnostic", lambda: self.ask("Diagnostic")), ("État", lambda: self.ask("État"))]))
        add("Merci", ["merci", "super", "bravo", "genial", "parfait"], lambda: "Avec plaisir. Bonne émission !")
        return T

    STOP = set("le la les un une des de du d l a au aux et ou en que qui quoi quel quelle quels ce cet cette ces mon ma mes ton ta tes son sa ses "
               "je tu il on nous vous ils elles me te se y ne pas plus pour par sur sous dans avec sans est es suis sont fait faire peut peux veux "
               "veut dois comment pourquoi quand combien ca cela ceci moi toi lui leur tres bien aussi alors donc mais si c j n m s t qu quelque "
               "chose truc souci probleme aide besoin voudrais voudrait savoir svp stp radio".split())
    SYN = {"plant": "erreur", "bug": "erreur", "marche pas": "erreur", "fonctionne pas": "erreur", "ne repond": "erreur", "bloqu": "freeze saccade",
           "saute": "saccade", "hache": "saccade", "coupe": "coupure", "coupent": "coupure", "souffle": "sature", "bruit": "sature", "parasite": "sature",
           "entend pas": "pas de son", "entend rien": "pas de son", "ecoute pas": "pas de son", "plus rien": "pas de son", "sans son": "pas de son",
           "lance pas": "ne demarre pas", "demarre pas": "ne demarre pas", "part pas": "erreur", "fonctionne plus": "erreur",
           "wifi": "internet reseau", "box": "internet", "freebox": "internet", "orange": "internet", "4g": "internet", "connexion": "internet",
           "pige": "pige enregistrement", "arcom": "pige enregistrement", "csa": "pige enregistrement", "archiv": "enregistrement",
           "dossier": "dossier playlist", "ranger": "dossier playlist", "pochette": "pochette titre affiche", "tete de lecture": "forme d onde",
           "balader": "tete de lecture point de depart", "aller dans le son": "tete de lecture", "point de depart": "tete lecture cartouche", "horloge": "heure", "heure": "heure",
           "bretagne": "propos", "a propos": "propos", "version": "propos", "mot de passe": "mot de passe erreur", "crash": "erreur", "freeze": "saccade",
           "trop de bruit": "sature", "voix": "niveau son", "volume": "niveau son", "niveau": "niveau son", "micro": "microphone entree"}

    def answer(self, q):
        import difflib
        n = norm_txt(q)
        m = re.match(r"^(?:cherche|trouve|recherche|grep)\s+(.+)$", n)
        if m or n.startswith("journal "):
            term = (m.group(1) if m else n[8:]).strip()
            hits = [l for l in self.app.log_lines[-600:] if term in norm_txt(l)]
            if hits:
                return "Dans le journal, « %s » apparaît ici :\n%s" % (term, "\n".join(hits[-6:]))
            return f"Je ne trouve pas « {term} » dans le journal récent."
        kb = self.kb()
        n2 = n
        extra = []
        for k, v in self.SYN.items():
            if k in n:
                extra.append(v)
        if extra:
            n2 = n + " " + " ".join(extra)
        toks = re.findall(r"[a-z0-9']+", n2)
        padded = " " + n2 + " "
        # suites de conversation : « et alors ? », « comment ? », « explique »
        if self.last and len(toks) <= 3 and re.match(r"^(et |alors|ok|oui|plus|detail|explique|comment|pourquoi|et ca|d'accord|encore|continue)", n):
            tt, fn = self.last
            r = fn()
            r = r if isinstance(r, tuple) else (r, None)
            return ("À propos de « %s » : \n" % tt + r[0], r[1])
        stem = lambda t: t[:5] if len(t) > 5 else t
        qs = {stem(t) for t in re.findall(r"[a-z0-9]+", n2) if len(t) >= 3 and t not in self.STOP}
        if not hasattr(self, "_tstems"):
            self._tstems = [{stem(t) for t in re.findall(r"[a-z0-9]+", norm_txt(ti + " " + " ".join(ks))) if len(t) >= 3 and t not in self.STOP}
                            for ti, ks, _ in kb]
            df = {}
            for st in self._tstems:
                for t in st:
                    df[t] = df.get(t, 0) + 1
            self._idf = {t: math.log(1 + len(kb) / c) for t, c in df.items()}
        scored = []
        for (title, keys, fn), tst in zip(kb, self._tstems):
            s = 0.0
            for k in list(keys) + [title]:
                k = norm_txt(k)
                if " " in k or len(k) <= 3:
                    if (" " + k + " ") in padded or (" " in k and k in n2):
                        s += len(k) * 1.3
                elif k in n2:
                    s += len(k)
                else:
                    c = [t for t in difflib.get_close_matches(k, toks, n=3, cutoff=0.86) if t[0] == k[0] and len(k) >= 6]
                    if c:
                        s += len(k) * .7
            hit = qs & tst
            if hit:
                s += 2.4 * sum(self._idf.get(t, 1) for t in hit) * (0.6 + 0.4 * len(hit) / max(1, len(qs)))
            if s:
                scored.append((s, title, fn))
        scored.sort(key=lambda x: -x[0])
        if scored and scored[0][0] >= 4.5:
            best = scored[0]
            self.last = (best[1], best[2])
            r = best[2]()
            text, acts = r if isinstance(r, tuple) else (r, None)
            alts = [x for x in scored[1:3] if x[0] >= max(4.5, best[0] * .6)]
            if alts:
                acts = list(acts or []) + [("Plutôt : " + t, (lambda tt=t: self.ask(tt))) for _, t, _ in alts]
            return (text, acts)
        if scored:
            sugg = [(t, (lambda tt=t: self.ask(tt))) for _, t, _ in scored[:3]]
            return ("Je ne suis pas sûr d'avoir compris. Tu parlais de l'un de ces sujets ?", sugg)
        tops = [("État de l'antenne", None), ("Pas de son", None), ("Flux en erreur", None), ("Internet", None), ("Premiers pas", None)]
        return ("Je n'ai pas trouvé de réponse. Essaie avec d'autres mots (par exemple « pas de son », « le flux coupe », « mail ne part pas »), "
                "demande un diagnostic, ou choisis un sujet :", [(t, (lambda tt=t: self.ask(tt))) for t, _ in tops])

# ------------------------------------------------------------------ Gaël : la mascotte articulée et ses animations
# Gaël est dessiné en vectoriel à chaque image (aucune image chargée). Les animations sont pilotées par le temps réel
# (QElapsedTimer) : elles restent fluides même si une image saute. Le minuteur s'arrête dès que Gaël n'est pas visible.
from PySide6.QtCore import QThread
from PySide6.QtGui import QTransform

# Gaël « le Marin » : marinière, béret à pompon, antenne qui capte. Quatre couleurs : marine, blanc, rouge, ambre.
G_NAVY, G_WHITE, G_RED, G_AMBER = "#12294a", "#ffffff", "#d9263d", "#f2a33a"
G_OUT = "#12294a" if LIGHT else "#0a1830"      # contour (sur fond sombre, un marine plus profond reste lisible)
G_COIF, G_LACE, G_VELVET = G_NAVY, G_NAVY, G_NAVY  # (anciens noms : béret)
G_HEAD, G_SCREEN = "#eef2f7", G_NAVY
G_BODY_D, G_BODY_L, G_GRILLE = G_NAVY, G_WHITE, G_NAVY
G_LIMB = G_NAVY if LIGHT else "#1d3a63"
G_HAND, G_HAND_LINE = G_WHITE, G_NAVY
G_SHOE = G_NAVY if LIGHT else "#1d3a63"
G_BLUSH = "#8a2b48"
G_EDGE = "#b9c6da"                              # liseré des bras et jambes sur fond sombre
ARM_A, ARM_B = 19.0, 18.0          # bras, avant-bras
LEG_A, LEG_B = 9.5, 9.0            # cuisse, tibia
HIP_Y = -24.0                      # hanches (le sol est en y = 0)
SHOULDER = (28.0, -33.0)           # épaule droite, repère du corps (origine aux hanches)




def ss(x):
    """Lissage doux (smoothstep)."""
    x = _cl(x)
    return x * x * (3 - 2 * x)


def win(t, a, b):
    """Avancement 0 → 1 de t entre a et b, lissé."""
    return ss((t - a) / (b - a)) if b > a else float(t >= b)


def back_out(x):
    x = _cl(x)
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


POSE0 = dict(x=0.0, y=0.0, rot=0.0, sq=0.0, flip=1.0, head=0.0, coif=0.0,
             la1=10.0, la2=8.0, ra1=10.0, ra2=8.0, ll1=4.0, ll2=0.0, rl1=4.0, rl2=0.0,
             look=0.0, lookv=0.0, eye=0.0, mouth=0.0, blink=0.0, eyec=None)
DISCRETE = ("eye", "mouth", "eyec")


def blend(a, b, t):
    out = {}
    for k, v in a.items():
        w = b.get(k, v)
        out[k] = (w if t >= .5 else v) if k in DISCRETE else v + (w - v) * t
    return out


def dir_r(a):
    r = math.radians(a)
    return math.sin(r), math.cos(r)


def ik(side, tx, ty):
    """Bras à deux segments : angles (épaule, coude) pour amener la main en (tx, ty) dans le repère du corps."""
    sx = SHOULDER[0] * side
    sy = SHOULDER[1]
    dx, dy = (tx - sx) * side, ty - sy
    d = max(abs(ARM_A - ARM_B) + .5, min(ARM_A + ARM_B - .3, math.hypot(dx, dy)))
    th = math.degrees(math.atan2(dx, dy))
    al = math.degrees(math.acos(_cl((ARM_A ** 2 + d * d - ARM_B ** 2) / (2 * ARM_A * d), -1, 1)))
    best = None
    for a1 in (th + al, th - al):
        ex, ey = dir_r(a1)
        ex, ey = ex * ARM_A, ey * ARM_A
        fa = math.degrees(math.atan2(dx - ex, dy - ey))
        score = ey + abs(ex) * .35
        if best is None or score > best[0]:
            best = (score, a1, fa - a1)
    return best[1], best[2]


class GaelPainter:
    """Dessine Gaël dans une pose donnée. Les rappels hand_r / hand_l dessinent un objet tenu en main.
    Les parties fixes (corps, tête, coiffe) sont pré-rendues en images à la bonne résolution et seulement recopiées."""

    def __init__(self):
        self.hands = {}
        self.cache = {}

    def cached(self, p, key, rect, fn):
        """Dessine `fn` via une image mise en cache à l'échelle réelle de l'écran (nette, et ~5× plus rapide)."""
        tr = p.worldTransform()
        sc = max(abs(tr.m11()) + abs(tr.m21()), abs(tr.m22()) + abs(tr.m12())) * p.device().devicePixelRatioF()
        sc = max(.5, round(sc * 4) / 4)
        k = (key, sc)
        pm = self.cache.get(k)
        if pm is None:
            if len(self.cache) > 24:
                self.cache.clear()
            pm = QPixmap(max(1, int(rect.width() * sc + 2)), max(1, int(rect.height() * sc + 2)))
            pm.fill(Qt.GlobalColor.transparent)
            q = QPainter(pm)
            q.setRenderHints(QPainter.RenderHint.Antialiasing)
            q.scale(sc, sc)
            q.translate(-rect.left() + 1 / sc, -rect.top() + 1 / sc)
            q.setPen(Qt.PenStyle.NoPen)
            fn(q)
            q.end()
            self.cache[k] = pm
        p.drawPixmap(QRectF(rect.left() - 1 / sc, rect.top() - 1 / sc, pm.width() / sc, pm.height() / sc), pm, QRectF(pm.rect()))

    def body_transform(self, P):
        T = QTransform()
        T.translate(P["x"], P["y"])
        sq = P["sq"]
        T.scale((1 - sq * .6) * P["flip"], 1 + sq)
        T.translate(0, HIP_Y)
        T.rotate(P["rot"])
        return T

    def hand_pos(self, P, side):
        """Position de la main (repère racine) pour poser des objets."""
        a1, a2 = (P["ra1"], P["ra2"]) if side > 0 else (P["la1"], P["la2"])
        ex, ey = dir_r(a1)
        fx, fy = dir_r(a1 + a2)
        x = SHOULDER[0] * side + side * (ex * ARM_A + fx * ARM_B)
        y = SHOULDER[1] + ey * ARM_A + fy * ARM_B
        return self.body_transform(P).map(QPointF(x, y))

    def draw(self, p, P, talk=0.0, on_air=False, t=0.0, hand_r=None, hand_l=None, dial=0.0):
        self.on_air = on_air
        p.save()
        sq = P["sq"]
        # ombre au sol (rétrécit pendant les sauts)
        h = _cl(-P["y"] / 30.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(70 * (1 - .6 * h))))
        p.drawEllipse(QPointF(P["x"], 1.5), 30 * (1 - .35 * h), 4.2 * (1 - .35 * h))
        p.translate(P["x"], P["y"])
        p.scale((1 - sq * .6) * P["flip"], 1 + sq)
        # jambes (depuis les hanches, dans le repère racine pour garder les pieds au sol)
        for side, a1, a2 in ((-1, P["ll1"], P["ll2"]), (1, P["rl1"], P["rl2"])):
            hx, hy = 12 * side, HIP_Y + 2
            kx, ky = dir_r(a1)
            kx, ky = hx + side * kx * LEG_A, hy + ky * LEG_A
            fx, fy = dir_r(a1 - a2)
            fx, fy = kx + side * fx * LEG_B, ky + fy * LEG_B
            leg = [QPointF(hx, hy), QPointF(kx, ky), QPointF(fx, fy)]
            if not LIGHT:                       # liseré clair : le marine reste visible sur le fond sombre
                p.setPen(ppen(G_EDGE, 9.5))
                p.drawPolyline(leg)
            p.setPen(ppen(G_LIMB, 7))
            p.drawPolyline(leg)
            p.setPen(QPen(QColor(G_EDGE), 1.4) if not LIGHT else Qt.PenStyle.NoPen)
            p.setBrush(QColor(G_SHOE))
            p.drawEllipse(QRectF(fx - 9 + side * 3, fy - 3, 18, 7.5))
            p.setPen(Qt.PenStyle.NoPen)
        p.translate(0, HIP_Y)
        p.rotate(P["rot"])
        self._torso(p, on_air, dial)
        # tête + coiffe
        p.save()
        p.translate(0, -40)
        p.rotate(P["head"])
        self._head(p, P, talk, t)
        p.restore()
        # bras par-dessus le corps
        for side, a1, a2, cb in ((-1, P["la1"], P["la2"], hand_l), (1, P["ra1"], P["ra2"], hand_r)):
            sx, sy = SHOULDER[0] * side, SHOULDER[1]
            ex, ey = dir_r(a1)
            ex, ey = sx + side * ex * ARM_A, sy + ey * ARM_A
            hx, hy = dir_r(a1 + a2)
            hx, hy = ex + side * hx * ARM_B, ey + hy * ARM_B
            arm = [QPointF(sx, sy), QPointF(ex, ey), QPointF(hx, hy)]
            p.setBrush(Qt.BrushStyle.NoBrush)
            if not LIGHT:
                p.setPen(ppen(G_EDGE, 8))
                p.drawPolyline(arm)
            p.setPen(ppen(G_LIMB, 5.4))
            p.drawPolyline(arm)
            if cb:
                p.save()
                p.translate(hx, hy)
                ang = a1 + a2
                cb(p, -ang if side > 0 else ang)
                p.restore()
            p.setPen(QPen(QColor(G_HAND_LINE), 2.2))
            p.setBrush(QColor(G_HAND))
            p.drawEllipse(QPointF(hx, hy), 4.8, 4.8)
        p.restore()

    @staticmethod
    def _rr(p, x0, y0, x1, y1, r, fill):
        p.setBrush(QColor(fill) if not isinstance(fill, QBrush) else fill)
        p.drawRoundedRect(QRectF(x0, y0, x1 - x0, y1 - y0), r, r)

    def _torso_static(self, p):
        """Marinière : corps arrondi rayé marine et blanc, contour franc, petit foulard rouge au col."""
        r = QRectF(-27, -42, 54, 42)
        path = QPainterPath()
        path.addRoundedRect(r, 13, 13)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(G_WHITE))
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        p.setBrush(QColor(G_NAVY))
        for k in range(4):
            p.drawRect(QRectF(-30, -31 + k * 8.4, 60, 4.4))
        p.restore()
        p.setPen(QPen(QColor(G_OUT), 2.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(QPen(QColor(G_OUT), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor(G_RED))
        p.drawPolygon(QPolygonF([QPointF(-10, -42.5), QPointF(10, -42.5), QPointF(0, -34)]))
        p.setPen(Qt.PenStyle.NoPen)

    def _torso(self, p, on_air, dial):
        """Corps (origine = hanches, haut du corps en y = -42)."""
        p.setPen(Qt.PenStyle.NoPen)
        self.cached(p, "torso", QRectF(-30, -46, 60, 49), self._torso_static)

    def _head(self, p, P, talk, t):
        """Tête (origine = base du cou) : visage-écran marine, oreillettes, béret à pompon (qui suit les mouvements
        avec un léger retard) et antenne qui capte (ondes ambre quand on est à l'antenne)."""
        rr = self._rr
        p.setPen(Qt.PenStyle.NoPen)
        mini = P.get("mini")
        if not mini:                            # antenne, derrière la tête
            p.save()
            p.translate(13, -44)
            p.rotate(P["coif"] * .8)
            p.setPen(ppen(G_NAVY if LIGHT else "#c9d3e3", 2.2))
            p.drawLine(QPointF(0, 0), QPointF(13, -24))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(G_AMBER))
            p.drawEllipse(QPointF(13, -25), 3.4, 3.4)
            air = getattr(self, "on_air", False)
            for k in range(2):
                if air and ANIM:
                    u = (t * .9 + k * .5) % 1.0
                    c = qc(G_AMBER, int(255 * (1 - u)))
                    rad = 6 + u * 9
                else:
                    c, rad = QColor(G_AMBER), 6.5 + k * 5
                p.setPen(ppen(c, 1.8))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(QRectF(13 - rad, -25 - rad, 2 * rad, 2 * rad), -55 * 16, 110 * 16)
            p.restore()
        self.cached(p, "head", QRectF(-30, -47, 60, 47), self._head_static)
        # béret à pompon (par-dessus la tête ; il bascule un peu avec la tête)
        p.save()
        p.translate(0, -43)
        p.rotate(P["coif"] * (.35 if not mini else 0))
        self.cached(p, "beret", QRectF(-31, -20, 63, 24), self._coif_static)
        p.restore()
        # yeux
        lx, ly = P["look"] * 2.6, P["lookv"] * 2.2
        e, bl = int(P["eye"]), P["blink"]
        col = QColor(P.get("eyec") or ("#ffd38a" if talk else G_AMBER))
        p.setBrush(QColor(G_BLUSH))                    # joues
        p.drawEllipse(QPointF(-14.5, -17), 2.4, 2.4)
        p.drawEllipse(QPointF(14.5, -17), 2.4, 2.4)
        for xx in (-9, 9):
            cx, cy = xx + lx, -26 + ly
            if e == 1:                          # heureux : ^ ^
                p.setPen(ppen(col, 2.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPolyline([QPointF(cx - 4, cy + 1.5), QPointF(cx, cy - 2.5), QPointF(cx + 4, cy + 1.5)])
                p.setPen(Qt.PenStyle.NoPen)
                continue
            if e == 5:                          # fâché : yeux plissés + sourcils froncés
                p.setBrush(col)
                p.drawRoundedRect(QRectF(cx - 4, cy - 1.5, 8, 4.5), 2, 2)
                p.setPen(ppen(col, 2.2))
                s_ = 1 if xx < 0 else -1
                p.drawLine(QPointF(cx - 5 * s_, cy - 8), QPointF(cx + 4 * s_, cy - 4.5))
                p.setPen(Qt.PenStyle.NoPen)
                continue
            if e == 2:                          # paupières mi-closes (bof)
                p.setBrush(col)
                p.drawRoundedRect(QRectF(cx - 4, cy - .5, 8, 3), 1.5, 1.5)
                continue
            hgt = 4.2 if e != 3 else 5.6
            if e == 4:
                hgt = 2.6
            hgt = max(.8, hgt * (1 - bl))
            wd = 4.2 if e != 3 else 5.0
            p.setBrush(col)
            p.drawEllipse(QRectF(cx - wd, cy - hgt, wd * 2, hgt * 2))
            if e == 3 and bl < .5:
                p.setBrush(QColor(G_SCREEN))
                p.drawEllipse(QPointF(cx + .8, cy - 1.2), 1.4, 1.4)
        # bouche
        m = int(P["mouth"])
        if talk:
            for i in range(5):
                hh = 2 + abs(math.sin(t * 13 + i * 1.3)) * 4.2 * min(1.0, talk)
                rr(p, -13 + i * 6, -14 - hh / 2, -10 + i * 6, -14 + hh / 2, 1, G_AMBER)
        elif m == 1:
            p.setBrush(QColor(G_AMBER))
            p.drawEllipse(QPointF(0, -14), 3.2, 3.6)
        elif m == 2:
            path = QPainterPath(QPointF(-8, -17))
            path.cubicTo(QPointF(-6, -8), QPointF(6, -8), QPointF(8, -17))
            path.closeSubpath()
            p.setBrush(QColor(G_AMBER))
            p.drawPath(path)
        elif m == 4:                            # grimace (pas content)
            p.setPen(ppen(P.get("eyec") or G_AMBER, 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(QPointF(-8, -12))
            for k in range(1, 5):
                path.lineTo(QPointF(-8 + k * 4, -12 - (3 if k % 2 else 0)))
            p.drawPath(path)
            p.setPen(Qt.PenStyle.NoPen)
        elif m == 3:                            # moue
            p.setPen(ppen(G_AMBER, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(-6, -15, 12, 8), 20 * 16, 140 * 16)
            p.setPen(Qt.PenStyle.NoPen)
        else:
            p.setPen(ppen(G_AMBER, 2.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(-8, -20, 16, 10), -160 * 16, 140 * 16)
            p.setPen(Qt.PenStyle.NoPen)

    def _coif_static(self, p):
        """Béret marine à pompon rouge (origine = haut de la tête)."""
        path = QPainterPath(QPointF(-28, 1.5))
        path.cubicTo(QPointF(-25, -9), QPointF(-9, -13), QPointF(2, -13))
        path.cubicTo(QPointF(15, -13), QPointF(28, -7), QPointF(30, 1.5))
        path.cubicTo(QPointF(16, -1), QPointF(-14, -1), QPointF(-28, 1.5))
        p.setPen(QPen(QColor(G_OUT if LIGHT else G_EDGE), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor(G_NAVY))
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(G_RED))
        p.drawEllipse(QPointF(1, -14.5), 4.6, 4.6)
        p.setBrush(qc("#ffffff", 70))
        p.drawEllipse(QPointF(-.4, -16), 1.4, 1.4)

    def _head_static(self, p):
        rr = self._rr
        p.setPen(QPen(QColor(G_OUT if LIGHT else G_EDGE), 1.4))
        rr(p, -28, -32, -21, -16, 3.5, G_NAVY)       # oreillettes
        rr(p, 21, -32, 28, -16, 3.5, G_NAVY)
        p.setPen(QPen(QColor(G_OUT), 2.6))
        rr(p, -23, -45, 23, -2, 15, G_HEAD)
        p.setPen(Qt.PenStyle.NoPen)
        rr(p, -18, -38, 18, -8, 9, G_SCREEN)
        p.setPen(Qt.PenStyle.NoPen)


# ------------------------------------------------------------------ petits dessins (accessoires)
def draw_note(p, x, y, col, s=1.0, double=False):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.save()
    p.translate(x, y)
    p.rotate(-18)
    p.drawEllipse(QPointF(0, 0), 3.4 * s, 2.5 * s)
    p.restore()
    p.setPen(QPen(col, 1.4 * s))
    p.drawLine(QPointF(x + 3 * s, y - .5 * s), QPointF(x + 3 * s, y - 12 * s))
    if double:
        p.drawLine(QPointF(x + 3 * s, y - 12 * s), QPointF(x + 11 * s, y - 14 * s))
        p.drawLine(QPointF(x + 11 * s, y - 14 * s), QPointF(x + 11 * s, y - 3 * s))
        p.setPen(Qt.PenStyle.NoPen)
        p.save()
        p.translate(x + 8 * s, y - 2.5 * s)
        p.rotate(-18)
        p.drawEllipse(QPointF(0, 0), 3.4 * s, 2.5 * s)
        p.restore()
    else:
        path = QPainterPath(QPointF(x + 3 * s, y - 12 * s))
        path.cubicTo(QPointF(x + 8 * s, y - 10 * s), QPointF(x + 9 * s, y - 7 * s), QPointF(x + 7 * s, y - 4 * s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


def draw_sparkle(p, x, y, r, col):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    path = QPainterPath(QPointF(x, y - r))
    for a, b in ((x + r * .22, y - r * .22), (x + r, y), (x + r * .22, y + r * .22), (x, y + r), (x - r * .22, y + r * .22),
                 (x - r, y), (x - r * .22, y - r * .22)):
        path.lineTo(a, b)
    path.closeSubpath()
    p.drawPath(path)


def draw_heart(p, x, y, s, col):
    path = QPainterPath(QPointF(x, y + 4 * s))
    path.cubicTo(QPointF(x - 7 * s, y - 1 * s), QPointF(x - 4 * s, y - 7 * s), QPointF(x, y - 3 * s))
    path.cubicTo(QPointF(x + 4 * s, y - 7 * s), QPointF(x + 7 * s, y - 1 * s), QPointF(x, y + 4 * s))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawPath(path)


def draw_gull(p, x, y, flap, s=1.0, facing=-1, perched=False):
    """Goéland : corps blanc, ailes grises à bout noir, bec jaune à tache rouge."""
    p.save()
    p.translate(x, y)
    p.scale(s * facing, s)
    p.setPen(Qt.PenStyle.NoPen)
    wing = QColor("#b9c3d1")
    if perched:
        p.setPen(ppen("#f0a030", 1.6))
        p.drawLine(QPointF(-2, 5), QPointF(-3, 10))
        p.drawLine(QPointF(3, 5), QPointF(4, 10))
        p.setPen(Qt.PenStyle.NoPen)
    # aile arrière
    a = math.radians(flap)
    for k, (sh, col) in enumerate(((-1.5, mixc(wing, "#000000", .15)), (0, wing))):
        p.save()
        p.translate(1 + sh, -2)
        p.rotate(-math.degrees(a) * (1 if k else .7))
        path = QPainterPath(QPointF(0, 0))
        path.cubicTo(QPointF(4, -6), QPointF(12, -7), QPointF(19, -5))
        path.lineTo(QPointF(14, -1.5))
        path.cubicTo(QPointF(9, 0), QPointF(4, 1), QPointF(0, 1.5))
        p.setBrush(col)
        p.drawPath(path)
        p.setBrush(QColor("#1d2230"))
        tip = QPainterPath(QPointF(15, -5.6))
        tip.lineTo(QPointF(19, -5))
        tip.lineTo(QPointF(15.5, -2.2))
        tip.closeSubpath()
        p.drawPath(tip)
        p.restore()
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QPointF(0, 1), 9, 4.6)
    tail = QPainterPath(QPointF(7, 0))
    tail.lineTo(QPointF(13, -1.5))
    tail.lineTo(QPointF(12, 3))
    tail.closeSubpath()
    p.setBrush(QColor("#e7ebf2"))
    p.drawPath(tail)
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QPointF(-8, -2.5), 4, 3.8)
    p.setBrush(QColor("#f6c443"))
    beak = QPainterPath(QPointF(-11.5, -3))
    beak.lineTo(QPointF(-17, -1.6))
    beak.lineTo(QPointF(-11.5, -.8))
    beak.closeSubpath()
    p.drawPath(beak)
    p.setBrush(QColor("#e0393e"))
    p.drawEllipse(QPointF(-14.6, -1.3), .8, .8)
    p.setBrush(QColor("#10131b"))
    p.drawEllipse(QPointF(-9, -3.4), 1, 1)
    p.restore()


# ------------------------------------------------------------------ les animations
class GAnim:
    """Une animation = une durée, une pose en fonction du temps, des accessoires dessinés derrière / devant."""
    name, label, dur = "", "", 6.0

    def __init__(self):
        rnd = random.Random(hash(self.name) & 0xffff)
        self.rnd = [rnd.random() for _ in range(64)]

    def pose(self, t, P):
        return P

    def back(self, p, t, gp, P):
        pass

    def front(self, p, t, gp, P):
        pass

    def hand_r(self, t):
        return None

    def hand_l(self, t):
        return None


class AGavotte(GAnim):
    name, label, dur = "gavotte", "La gavotte", 8.4
    BEAT = .42

    def pose(self, t, P):
        b = t / self.BEAT
        ph = b % 1.0
        hop = abs(math.sin(math.pi * b))
        even = int(b) % 2 == 0
        lift = math.sin(math.pi * ph)
        P.update(y=-hop * 6.5, sq=-.05 * math.cos(2 * math.pi * b) * .8, x=11 * math.sin(2 * math.pi * t / (self.BEAT * 8)),
                 rot=(4.5 if even else -4.5) * lift, head=(-3 if even else 3) * lift, eye=1, mouth=2,
                 la1=44 + 18 * math.sin(math.pi * b), la2=100 + 16 * math.sin(math.pi * b + .6),
                 ra1=44 + 18 * math.sin(math.pi * b), ra2=100 + 16 * math.sin(math.pi * b + .6))
        if even:
            P.update(ll1=4 + 26 * lift, ll2=48 * lift, rl1=4, rl2=0)
        else:
            P.update(rl1=4 + 26 * lift, rl2=48 * lift, ll1=4, ll2=0)
        sp = win(t, self.dur - 1.7, self.dur - .5)       # pirouette finale
        if 0 < sp < 1:
            c = math.cos(sp * 2 * math.pi)
            P["flip"] = math.copysign(max(.2, abs(c)), c)
            P["y"] -= math.sin(sp * math.pi) * 9
        return P

    def back(self, p, t, gp, P):
        for k in range(int(t / (self.BEAT * 2)) + 1):
            t0 = k * self.BEAT * 2
            u = (t - t0) / 1.9
            if not 0 <= u <= 1 or t0 > self.dur - 1.2:
                continue
            side = -1 if k % 2 else 1
            x = side * (36 + 10 * u) + math.sin(u * 7 + k) * 5
            y = -110 - u * 70
            c = QColor(grad((k * .23) % 1))
            c.setAlphaF(_cl(min(u * 5, (1 - u) * 2.2)))
            draw_note(p, x, y, c, 1.15, double=k % 3 == 1)


class ACrepes(GAnim):
    name, label, dur = "crepes", "Les crêpes", 9.0
    BX, BY = 47.0, -38.0     # centre du bilig (repère racine)
    RX = 25.0

    def stage(self, t):
        return back_out((t - .1) / .55) * (1 - win(t, self.dur - .7, self.dur - .15))

    def pose(self, t, P):
        P.update(x=-9.0, look=1, eye=4, mouth=0)
        hx, hy = self.BX - 9 + 0, self.BY + HIP_Y * -1 - 18   # repère corps
        # étaler la pâte
        if 1.0 <= t < 3.4:
            u = (t - 1.0) / 2.4
            a = u * 4.6 * math.pi
            r = 2 + 8 * u
            tx, ty = 38 + math.cos(a) * r, -21 + math.sin(a) * r * .32
            P["ra1"], P["ra2"] = ik(1, tx, ty)
            P["rot"], P["head"] = 4, 5
        elif t < 1.0:
            k = win(t, .3, 1.0)
            a1, a2 = ik(1, 30, -22)
            P["ra1"], P["ra2"] = lerp(P["ra1"], a1, k), lerp(P["ra2"], a2, k)
        elif t < 4.2:                       # cuisson : il surveille, main sur la hanche
            P.update(ra1=38, ra2=-70, eye=4, rot=3, head=6)
        elif t < 6.2:                       # le saut de la crêpe
            u = win(t, 4.2, 4.55)
            v = win(t, 4.55, 4.75)
            a1, a2 = ik(1, 34, -16)
            b1, b2 = ik(1, 24, -40)
            P["ra1"], P["ra2"] = lerp(lerp(38, a1, u), b1, v), lerp(lerp(-70, a2, u), b2, v)
            P["sq"] = .06 * u * (1 - v) - .05 * v * (1 - win(t, 4.8, 5.2))
            f = self.flight(t)
            if f is not None:
                P.update(eye=3, mouth=1, lookv=-1 + f[2], look=.6, head=-6)
            if t > 5.35:
                P.update(eye=1, mouth=2, lookv=0)
        else:                               # pliage et dégustation
            P.update(eye=1, mouth=2, ra1=30, ra2=60, la1=30, la2=60, head=-4 * math.sin((t - 6.2) * 5))
        return P

    def flight(self, t):
        if 4.6 <= t <= 5.35:
            u = (t - 4.6) / .75
            return (self.BX + 2 * math.sin(u * math.pi), self.BY - 2 - 66 * math.sin(u * math.pi), u)
        return None

    def crepe_color(self, t):
        k = win(t, 3.2, 4.2)
        return mixc("#f6e7bd", "#e2a14c", k)

    def back(self, p, t, gp, P):
        s = self.stage(t)
        if s <= 0.01:
            return
        p.save()
        p.translate(self.BX, 0)
        p.scale(s, s)
        # pied et bilig (galettière en fonte)
        p.setPen(ppen("#6b7488", 2.4))
        p.drawLine(QPointF(-14, 0), QPointF(-8, self.BY + 6))
        p.drawLine(QPointF(14, 0), QPointF(8, self.BY + 6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2a2f3c"))
        p.drawEllipse(QPointF(0, self.BY + 2.5), self.RX + 1, 8)
        p.setBrush(QColor("#3c4252"))
        p.drawEllipse(QPointF(0, self.BY), self.RX, 7)
        p.setBrush(QColor("#ff8a3d"))
        p.drawEllipse(QPointF(0, self.BY + 5), 2.2, 1.2)
        p.restore()
        x0 = self.BX
        # pâte étalée
        if 1.0 <= t < 4.6 or t >= 5.35:
            if t < 3.4:
                u = (t - 1.0) / 2.4
                r = 3 + (self.RX - 5) * ss(u)
            else:
                r = self.RX - 2
            c = self.crepe_color(t)
            if t >= 5.35:
                c = mixc("#e2a14c", "#c98436", .4)
            fold = win(t, 6.3, 6.9) * .5 + win(t, 7.0, 7.5) * .25
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            rect = QRectF(x0 - r * s, self.BY - r * .28 * s, 2 * r * s, 2 * r * .28 * s)
            if t >= 6.3:
                p.drawPie(rect, int(90 * 16), int(360 * (1 - fold) * 16))
            else:
                p.drawEllipse(rect)
            if 3.0 < t < 4.6:
                p.setBrush(qc("#8a5220", int(160 * win(t, 3.4, 4.2))))
                for i in range(7):
                    a = self.rnd[i] * 6.28
                    rr = self.rnd[i + 8] * (r - 4)
                    p.drawEllipse(QPointF(x0 + math.cos(a) * rr, self.BY + math.sin(a) * rr * .28), 1.3, .55)
            if t >= 6.9:                     # noisette de beurre salé
                k = win(t, 6.9, 7.2) * (1 - win(t, 7.8, 8.4) * .5)
                p.setBrush(QColor("#ffe58a"))
                p.drawRoundedRect(QRectF(x0 + 3, self.BY - 5 * k, 6 * k, 3.6 * k), 1, 1)
        # vapeur
        if 2.8 < t < 4.6:
            for i in range(3):
                u = ((t * .9 + i / 3) % 1.0)
                c = QColor(TXT)
                c.setAlphaF(.22 * math.sin(u * math.pi) * win(t, 2.8, 3.3))
                path = QPainterPath(QPointF(x0 - 10 + i * 10, self.BY - 6))
                for k in range(1, 7):
                    path.lineTo(x0 - 10 + i * 10 + math.sin(k * 1.4 + t * 4 + i) * 3, self.BY - 6 - k * 4 - u * 12)
                p.setPen(QPen(c, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)

    def front(self, p, t, gp, P):
        f = self.flight(t)
        if f is not None:
            x, y, u = f
            phi = .284 + u * 2 * math.pi
            ry = abs(math.sin(phi)) * (self.RX - 2)
            c = self.crepe_color(t) if math.cos(phi) > 0 else mixc("#e2a14c", "#b8732c", .35)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), self.RX - 2, max(1.2, ry))
        if t >= 7.3:
            k = (t - 7.3) / 1.4
            if k <= 1:
                c = QColor("#ff6b8a")
                c.setAlphaF(_cl(min(k * 4, (1 - k) * 2)))
                draw_heart(p, self.BX - 20 + math.sin(k * 6) * 3, -100 - k * 34, 1.3, c)
        if 7.2 < t < 8.4:
            k = win(t, 7.2, 7.6) * (1 - win(t, 8.0, 8.4))
            for i, (dx, dy) in enumerate(((-12, -48), (14, -52), (2, -60))):
                draw_sparkle(p, self.BX + dx, dy, (2.4 + 1.4 * math.sin(t * 9 + i)) * k, qc("#ffe58a", 230))

    def hand_r(self, t):
        if .6 < t < 3.6:                    # le rozell (râteau en bois)
            u = _cl((t - 1.0) / 2.4)

            def f(p, ang):
                p.rotate(-12 + 10 * math.sin(t * 9))
                p.setPen(ppen("#c08a4e", 2.2))
                p.drawLine(QPointF(0, 0), QPointF(0, 13))
                p.setPen(ppen("#d9a56a", 3.2))
                p.drawLine(QPointF(-7, 13), QPointF(7, 13))
            return f
        if 4.15 < t < 4.9:                  # la spatule
            def g(p, ang):
                p.rotate(-30)
                p.setPen(ppen("#c08a4e", 2))
                p.drawLine(QPointF(0, 0), QPointF(0, 12))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#d9a56a"))
                p.drawRoundedRect(QRectF(-2.5, 11, 5, 14), 2, 2)
            return g
        return None


class ACrachin(GAnim):
    name, label, dur = "crachin", "Le crachin breton", 8.6
    CY = -176.0

    def cloud_x(self, t):
        return lerp(-120, -6, back_out(_cl(t / 1.3) * .999) if t < 1.3 else 1) + 150 * ss((t - 5.0) / 1.2)

    def umb(self, t):
        return win(t, 2.1, 2.7) * (1 - win(t, 5.9, 6.5))

    def pose(self, t, P):
        if t < 2.1:
            P.update(lookv=-1 * win(t, .6, 1.2), look=-.3, eye=2 if t > 1.5 else 0, mouth=3 if t > 1.5 else 0)
            if t > 1.6:
                P["head"] = math.sin(t * 14) * 3 * (1 - win(t, 1.9, 2.1))
        u = self.umb(t)
        if 2.0 <= t < 6.6:
            P.update(ra1=lerp(10, 158, win(t, 2.0, 2.5)), ra2=lerp(8, 4, win(t, 2.0, 2.5)), eye=0, mouth=0, lookv=-.4)
        if 5.2 <= t < 6.6:
            P.update(eye=3, mouth=1, lookv=-1, look=-.8)
        if 6.6 <= t:
            k = win(t, 6.6, 7.0) * (1 - win(t, self.dur - .5, self.dur))
            P.update(ra1=lerp(10, 60, k), ra2=lerp(8, 40 + math.sin(t * 30) * 25 * k, k), eye=1, mouth=2, sq=.03 * math.sin(t * 30) * k)
        return P

    def back(self, p, t, gp, P):
        sun = win(t, 5.3, 6.0) * (1 - win(t, self.dur - .7, self.dur))
        if sun > 0:
            c = QColor("#ffcf4a")
            c.setAlphaF(sun)
            rb = ("#ff5f6d", "#ffb347", "#ffe066", "#5fd38d", "#4cc9f0", "#a76bff")
            for i, col in enumerate(rb):
                cc = QColor(col)
                cc.setAlphaF(.55 * sun)
                p.setPen(QPen(cc, 2.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                r = 74 - i * 3
                p.drawArc(QRectF(-r + 6, -120 - r, 2 * r, 2 * r), 20 * 16, 140 * 16)
            p.save()
            p.translate(-46, -168)
            p.rotate(t * 40)
            p.setPen(QPen(c, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for i in range(8):
                p.rotate(45)
                p.drawLine(QPointF(0, 11 * sun), QPointF(0, 16 * sun))
            p.restore()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPointF(-46, -168), 8 * sun, 8 * sun)

    def front(self, p, t, gp, P):
        cx = self.cloud_x(t)
        u = self.umb(t)
        R = gp.hand_pos(P, 1)
        top = R.y() - 58
        # parapluie (ciré jaune)
        if u > 0.01:
            shx = R.x() + 0
            p.setPen(ppen("#3a4152" if not LIGHT else "#5d6678", 1.8))
            p.drawLine(R, QPointF(shx, top))
            w = 44 * u
            path = QPainterPath(QPointF(shx - w, top + 2))
            path.cubicTo(QPointF(shx - w * .9, top - 22 * u), QPointF(shx + w * .9, top - 22 * u), QPointF(shx + w, top + 2))
            seg = 2 * w / 4
            for k in range(4):
                x1 = shx + w - (k + 1) * seg
                path.quadTo(QPointF(x1 + seg / 2, top - 3 * u), QPointF(x1, top + 2))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#ffc93c"))
            p.drawPath(path)
            p.setPen(QPen(QColor("#e0a81e"), 1))
            for k in (-1, 0, 1):
                p.drawLine(QPointF(shx, top - 20 * u), QPointF(shx + k * w * .5, top + 1))
            p.setBrush(QColor("#e0a81e"))
            p.drawEllipse(QPointF(shx, top - 20 * u), 1.6, 1.6)
        # pluie
        rain = win(t, 1.2, 1.7) * (1 - win(t, 4.8, 5.4))
        if rain > 0:
            c = QColor("#86b8ff")
            c.setAlphaF(.75 * rain)
            p.setPen(QPen(c, 1.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for i in range(18):
                x = cx - 26 + self.rnd[i] * 52
                y = self.CY + 10 + ((t * 150 + self.rnd[i + 20] * 200) % 190)
                stop = 0.0
                if u > .5 and abs(x - R.x()) < 44 * u:
                    stop = top - 18 * u * (1 - ((x - R.x()) / (44 * u)) ** 2)
                    if y > stop:
                        continue
                if y > -1:
                    continue
                p.drawLine(QPointF(x, y), QPointF(x - 1.2, y + 6))
            # éclaboussures sur la toile
            if u > .5:
                for i in range(3):
                    k = ((t * 3 + i * .33) % 1.0)
                    xx = R.x() + (self.rnd[i + 40] - .5) * 60
                    yy = top - 14
                    c2 = QColor("#86b8ff")
                    c2.setAlphaF((1 - k) * rain)
                    p.setPen(QPen(c2, 1))
                    p.drawArc(QRectF(xx - 4 * k - 2, yy - 2 * k, 8 * k + 4, 4 * k + 2), 0, 180 * 16)
        # gouttes en secouant le parapluie
        if t > 6.6:
            for i in range(6):
                k = ((t - 6.6) * 1.6 + i * .17) % 1.0
                c = QColor("#86b8ff")
                c.setAlphaF((1 - k) * (1 - win(t, self.dur - .6, self.dur)))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawEllipse(QPointF(R.x() + (self.rnd[i] - .5) * 40 * k, R.y() - 4 + k * 30), 1.4, 2)
        # nuage
        a = win(t, 0, .6) * (1 - win(t, 5.4, 6.3))
        if a > 0:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc("#8b95a8" if not LIGHT else "#aab3c4", int(255 * a)))
            for dx, dy, r in ((-16, 4, 11), (0, -2, 15), (16, 3, 12), (-4, 8, 12), (8, 8, 11)):
                p.drawEllipse(QPointF(cx + dx, self.CY + dy), r, r * .82)
            p.setBrush(qc("#a4adbf" if not LIGHT else "#c7cedb", int(255 * a)))
            p.drawEllipse(QPointF(cx - 2, self.CY - 5), 9, 6)


class AGoeland(GAnim):
    name, label, dur = "goeland", "Le goéland chapardeur", 8.6
    LAND = 1.9
    LEAVE = 5.2

    def gull(self, t):
        """(x, y, battement, posé ?) ; la coiffe culmine vers y = -150."""
        if t < self.LAND:
            u = ss(t / self.LAND)
            x = lerp(118, 2, u)
            y = lerp(-212, -152, u) - math.sin(u * math.pi) * 14
            flap = 38 * math.sin(t * 17) if u < .82 else lerp(20, -50, (u - .82) / .18)
            return x, y, flap, False
        if t < self.LEAVE:
            return 2, -152, -55, True
        u = (t - self.LEAVE) / 1.6
        x = lerp(2, -128, ss(u))
        y = -152 - u * 70 - math.sin(u * 3) * 6
        return x, y, 38 * math.sin(t * 18), False

    def pose(self, t, P):
        if t < self.LAND:
            P.update(lookv=-win(t, .6, 1.4), look=lerp(1, 0, win(t, .4, 1.6)), eye=0)
        elif t < self.LEAVE:
            v = t - self.LAND
            bump = math.exp(-v * 5) * math.sin(v * 22)
            P.update(sq=-.05 * bump, coif=-9 * bump, lookv=-1, eye=3 if v < 1.6 else 4, mouth=1 if v < 1.6 else 3)
            if 1.8 < v < 3.2:               # il chasse l'oiseau d'un revers de main
                k = win(v, 1.8, 2.1) * (1 - win(v, 2.9, 3.2))
                P.update(ra1=lerp(10, 165, k), ra2=lerp(8, 30 + math.sin(v * 26) * 26, k), head=4 * math.sin(v * 13) * k)
        else:
            v = t - self.LEAVE
            k = win(v, .3, .7) * (1 - win(t, self.dur - .6, self.dur))
            P.update(la1=lerp(10, 58, k), la2=lerp(8, 82, k), ra1=lerp(10, 58, k), ra2=lerp(8, 82, k), eye=2 if v < 1.6 else 1,
                     mouth=0 if v < 1.6 else 2, lookv=-.5 * (1 - win(v, 1, 2)), look=-.6 * (1 - win(v, 1, 2)), y=-2 * math.sin(k * math.pi))
        return P

    def front(self, p, t, gp, P):
        x, y, flap, perched = self.gull(t)
        if perched:
            v = t - self.LAND
            peck = max(0.0, math.sin(v * 9)) * 3 if 0.5 < v < 1.6 else 0
            y = -152 + P["y"] + peck * .4
            x = 2 + math.sin(v * 2) * 2
            if 2.1 < v < 3.0:
                y -= 6 * math.sin((v - 2.1) / .9 * math.pi)
                flap = 30 * math.sin(v * 20)
            draw_gull(p, x, y, flap, 1.25, -1 if v < 2.5 else 1, perched=True)
        else:
            draw_gull(p, x, y, flap, 1.25, -1 if t < self.LAND else 1)
        if self.LEAVE <= t < self.LEAVE + 1.1:     # « Kiaaa ! »
            k = (t - self.LEAVE) / 1.1
            c = QColor(TXT)
            c.setAlphaF(_cl(min(k * 5, (1 - k) * 2)))
            f = QFont()
            f.setPointSizeF(8.5)
            f.setBold(True)
            p.setFont(f)
            p.setPen(c)
            p.drawText(QPointF(x - 20, y - 12), "Kiaaa !")
        if t >= self.LEAVE:                  # plume qui tombe en zigzag
            u = (t - self.LEAVE) / 3.0
            if u <= 1:
                fx = 4 + math.sin(u * 9) * 14
                fy = lerp(-150, -6, u)
                c = QColor("#ffffff")
                c.setAlphaF(_cl((1 - u) * 3))
                p.save()
                p.translate(fx, fy)
                p.rotate(math.sin(u * 9) * 40)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawEllipse(QPointF(0, 0), 2.2, 6)
                p.setPen(QPen(qc("#b9c3d1", c.alpha()), .8))
                p.drawLine(QPointF(0, -6), QPointF(0, 8))
                p.restore()


class ACafe(GAnim):
    name, label, dur = "cafe", "La pause café", 4.6

    def pose(self, t, P):
        up = win(t, .3, 1.0) * (1 - win(t, 3.6, 4.3))
        sip = win(t, 1.4, 1.9) * (1 - win(t, 2.6, 3.0))
        h = ik(1, lerp(26, 12, up), lerp(-14, -62, up))
        P.update(ra1=h[0], ra2=h[1], eye=1 if sip > .3 else 0, mouth=0, head=-5 * sip, look=.4)
        return P

    def front(self, p, t, gp, P):
        R = gp.hand_pos(P, 1)
        p.save()
        p.translate(R)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f4efe6"))
        p.drawRoundedRect(QRectF(-6, -12, 12, 12), 2.5, 2.5)
        p.setBrush(QColor("#5a3a24"))
        p.drawRect(QRectF(-5, -11, 10, 2.4))
        p.setPen(QPen(QColor("#f4efe6"), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(3, -10, 7, 7), -90 * 16, 180 * 16)
        for i in range(3):
            u = ((t * .9) + i / 3) % 1.0
            c = QColor(MUT)
            c.setAlphaF((1 - u) * .7)
            p.setPen(QPen(c, 1.3))
            p.drawLine(QPointF(-3 + i * 3 + math.sin(u * 6 + i) * 1.5, -14 - u * 12),
                       QPointF(-3 + i * 3 + math.sin(u * 6 + i + 1) * 1.5, -17 - u * 12))
        p.restore()


class ACasque(GAnim):
    name, label, dur = "casque", "Le morceau préféré", 5.0

    def pose(self, t, P):
        k = win(t, .3, .8) * (1 - win(t, 4.4, 4.9))
        b = t * 2 * math.pi / .55
        P.update(head=lerp(0, 7 * math.sin(b), k), y=-1.6 * k * abs(math.sin(b / 2)), eye=1 if k > .3 else 0, mouth=2 if k > .5 else 0,
                 la1=lerp(10, 70, k), la2=lerp(8, 90, k))
        return P

    def front(self, p, t, gp, P):
        k = win(t, .3, .8) * (1 - win(t, 4.4, 4.9))
        if k <= .01:
            return
        for i in range(3):
            u = ((t * .7) + i / 3) % 1.0
            col = QColor(ACC)
            col.setAlphaF(_cl(min(u * 5, (1 - u) * 1.6)) * k)
            draw_note(p, 30 + math.sin(u * 5 + i) * 8, -110 - u * 55, col, .8, i == 1)


class AEtire(GAnim):
    name, label, dur = "etire", "L'étirement du matin", 4.4

    def pose(self, t, P):
        up = win(t, .4, 1.3) * (1 - win(t, 3.0, 3.8))
        yawn = win(t, 1.2, 1.7) * (1 - win(t, 2.7, 3.1))
        r = ik(1, 18, -120)
        l = ik(-1, -18, -120)
        P.update(ra1=lerp(10, r[0], up), ra2=lerp(8, r[1], up), la1=lerp(10, l[0], up), la2=lerp(8, l[1], up),
                 y=-3 * up, sq=-.05 * up + .015 * math.sin(t * 9) * yawn, head=-6 * yawn,
                 eye=1 if yawn > .2 else 0, mouth=1 if yawn > .3 else 0)
        return P


class AHoquet(GAnim):
    name, label, dur = "hoquet", "Le hoquet", 4.4
    HIC = (.8, 1.9, 2.7, 3.3)

    def pose(self, t, P):
        k = 0.0
        for h in self.HIC:
            d = t - h
            if 0 <= d < .35:
                k = max(k, math.sin(d / .35 * math.pi))
        P.update(y=-9 * k, sq=.07 * k, head=3 * k, eye=3 if k > .35 else 0, mouth=1 if k > .35 else 0,
                 ra1=lerp(10, 34, k), ra2=lerp(8, 60, k))
        return P

    def front(self, p, t, gp, P):
        f = QFont()
        f.setPointSizeF(9)
        f.setBold(True)
        p.setFont(f)
        for h in self.HIC:
            d = t - h
            if 0 <= d < .9:
                c = QColor(ACC)
                c.setAlphaF(_cl(1 - d / .9))
                p.setPen(c)
                p.drawText(QPointF(26, -140 - d * 22), "hic !")


class AHello(GAnim):
    """Petit coucou (au survol)."""
    name, label, dur = "hello", "Coucou", 1.8

    def pose(self, t, P):
        k = win(t, 0, .25) * (1 - win(t, self.dur - .3, self.dur))
        P.update(ra1=lerp(P["ra1"], 150, k), ra2=lerp(P["ra2"], 18 + math.sin(t * 13) * 26 * k, k), eye=1, mouth=2, head=-4 * k)
        return P


class AMaj(GAnim):
    """Mise à jour : la nouvelle version tombe du ciel en petits colis que Gaël réceptionne dans un carton posé à ses pieds
    (le carton se remplit au rythme du téléchargement). Une fois tout reçu, le carton se ferme d'un ruban et Gaël saute de
    joie au milieu des étincelles ; en cas d'échec, il se gratte la tête. Elle dure tant que la mise à jour n'est pas finie."""
    name, label, dur = "maj", "La mise à jour", 3600.0
    BX, BW, BH = 50.0, 34.0, 26.0

    def __init__(self):
        super().__init__()
        self.k, self.state, self.t_state = 0.0, "dl", time.monotonic()

    def set(self, state=None, k=None):
        if state is not None and state != self.state:
            self.state, self.t_state = state, time.monotonic()
        if k is not None:
            self.k = max(0.0, min(1.0, float(k)))

    def since(self):
        return time.monotonic() - self.t_state

    def pose(self, t, P):
        st, d = self.state, self.since()
        if st == "dl":                               # regarde les colis tomber, la main tendue vers le carton
            h = ik(1, 36, -4 + 3 * math.sin(t * 3))
            nod = math.sin(t * 2 * math.pi / .9)
            P.update(ra1=h[0], ra2=h[1], look=.9, lookv=-.4 + .3 * math.sin(t * 1.4), head=2.5 * nod, eye=0, mouth=0,
                     y=-1.2 * abs(nod))
        elif st == "done":                           # saut de joie, les deux bras en l'air, puis pouce levé
            j = max(0.0, 1 - d / 1.6)
            hop = abs(math.sin(d * 7.5)) * j
            arms = 1.0 if d < 1.6 else max(0.0, 1 - (d - 1.6) / .5)
            P.update(y=-9 * hop, la1=lerp(P["la1"], 150, arms), la2=lerp(P["la2"], 20, arms), ra1=lerp(P["ra1"], 150, arms),
                     ra2=lerp(P["ra2"], 20 + 18 * math.sin(d * 10) * arms, arms), eye=1, mouth=2, head=-4 * math.sin(d * 7.5) * j)
        elif st == "restart":                        # au revoir : petit signe de la main
            P.update(ra1=150, ra2=18 + math.sin(t * 13) * 26, eye=1, mouth=2, head=-4)
        else:                                        # échec : il se gratte la tête, perplexe
            h = ik(1, 14, -78)
            P.update(ra1=h[0], ra2=h[1] + 6 * math.sin(t * 9), eye=4, mouth=0, head=-6, look=-.5)
        return P

    def front(self, p, t, gp, P):
        st, d = self.state, self.since()
        bx, bw, bh = self.BX, self.BW, self.BH
        x0, y0 = bx - bw / 2, -bh
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        if st == "dl":                               # colis qui tombent dans le carton
            per = .62
            for i in range(4):
                u = ((t + i * per) % (per * 4)) / (per * 4)
                y = lerp(-212, y0 - 4, u * u)
                a = _cl(min(u * 6, (1 - u) * 9))
                x = bx + math.sin(u * 5 + i * 1.7) * 6 * (1 - u)
                c = QColor("#e9dfc8")
                c.setAlphaF(a)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x - 5, y - 5, 10, 10), 2, 2)
                ac = QColor(ACC)
                ac.setAlphaF(a)
                p.setPen(QPen(ac, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(x, y - 3), QPointF(x, y + 2.5))
                p.drawLine(QPointF(x - 2.6, y), QPointF(x, y + 2.8))
                p.drawLine(QPointF(x + 2.6, y), QPointF(x, y + 2.8))
                p.setPen(Qt.PenStyle.NoPen)
        # carton (de face) : le contenu monte avec le téléchargement
        p.setBrush(qc("#000000", 64))
        p.drawEllipse(QPointF(bx, 1), bw * .62, 3)
        p.setBrush(QColor("#c9965a"))
        p.drawRoundedRect(QRectF(x0, y0, bw, bh), 2.5, 2.5)
        k = 1.0 if st in ("done", "restart") else self.k
        if k > 0:
            fill = QLinearGradient(0, y0, 0, 0)
            fill.setColorAt(0, QColor(ACC2))
            fill.setColorAt(1, QColor(ACC))
            p.setBrush(QBrush(fill))
            fh = (bh - 7) * k
            p.drawRoundedRect(QRectF(x0 + 4, -3.5 - fh, bw - 8, fh), 1.5, 1.5)
        p.setBrush(QColor("#a87a43"))
        p.drawRect(QRectF(x0, y0, bw, 3))
        if st in ("done", "restart"):                # rabats fermés + ruban
            c = min(1.0, d / .35)
            p.setBrush(QColor("#b9864d"))
            p.drawRect(QRectF(x0 - 1, y0 - 3 * c, bw + 2, 4))
            p.setBrush(QColor(ONAIR_RED))
            p.drawRect(QRectF(bx - 2.5, y0 - 3 * c, 5, bh + 3 * c))
            for sd in (-1, 1):                       # nœud
                bow = QPainterPath(QPointF(bx, y0 - 3 * c))
                bow.cubicTo(QPointF(bx + sd * 10, y0 - 13 * c), QPointF(bx + sd * 12, y0 - 2 * c), QPointF(bx, y0 - 3 * c))
                p.drawPath(bow)
            for i in range(6):                       # étincelles
                u = ((d * .8) + i / 6) % 1.0
                ang = i * 1.05 + d * .4
                sc = QColor(SECOURS_Y if i % 2 else ACC2)
                sc.setAlphaF(_cl(min(u * 4, (1 - u) * 2.5)))
                draw_sparkle(p, bx + math.cos(ang) * (16 + 22 * u), y0 - 10 + math.sin(ang) * (12 + 16 * u) - 18 * u,
                             2.2 + 2.4 * (1 - u), sc)
        else:                                        # rabats ouverts
            p.setBrush(QColor("#b9864d"))
            for sd in (-1, 1):
                fl = QPainterPath(QPointF(bx + sd * bw / 2, y0))
                fl.lineTo(QPointF(bx + sd * (bw / 2 + 7), y0 - 8))
                fl.lineTo(QPointF(bx + sd * (bw / 2 - 9), y0 - 8))
                fl.lineTo(QPointF(bx + sd * (bw / 2 - 11), y0))
                fl.closeSubpath()
                p.drawPath(fl)
            if st == "err":                          # point d'interrogation au-dessus du carton
                p.setPen(QColor(ACC2))
                f = QFont()
                f.setPixelSize(16)
                f.setBold(True)
                p.setFont(f)
                p.drawText(QRectF(bx - 10, y0 - 34 + 2 * math.sin(t * 3), 20, 20), Qt.AlignmentFlag.AlignCenter, "?")
        p.restore()


G_ANIMS = [AGavotte(), ACrepes(), ACrachin(), AGoeland(), ACafe(), ACasque(), AEtire(), AHoquet()]
G_HELLO = AHello()
G_MAJ = AMaj()


class GaelView(QWidget):
    """Gaël animé. mode « rail » : sous le menu, joue ses animations ; mode « chat » : parle et réfléchit (onglet SOS)."""
    clicked = Signal()
    BOX = {"rail": QRectF(-64, -222, 150, 240), "chat": QRectF(-48, -160, 96, 170), "head": QRectF(-34, -158, 68, 104)}

    def __init__(self, mode="rail", parent=None, app=None):
        super().__init__(parent)
        self.mode, self.app = mode, app
        self.gp = GaelPainter()
        self.clock = QElapsedTimer()
        self.clock.start()
        self.t_last = 0.0
        self.anim, self.a_t0 = None, 0.0
        self.queue = list(range(len(G_ANIMS)))
        random.shuffle(self.queue)
        self.next_at = 7.0
        self.talk, self.think, self.on_air = 0.0, False, False
        self.blink_at, self.look_at, self.look_to, self.look_cur = 2.5, 4.0, 0.0, 0.0
        self.coif, self.coif_v, self.prev = 0.0, 0.0, None
        self.hover = False
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._drawn = 0.0
        self._pm, self._pm_sig, self._fresh = None, None, True     # dernière image de Gaël (voir paintEvent)
        Ticker.add(self, self._tick, 60, always=True)
        if mode == "rail":
            self.setToolTip("Gaël, ton assistant d'antenne · clic : une animation · clic droit : menu")

    def head_point(self):
        """Point juste à droite de la tête de Gaël (coordonnées du widget) : la bulle de BD y pointe."""
        W, H = self.width(), self.height()
        box = self.BOX[self.mode]
        name_h = 18 if self.mode == "rail" else 0
        s = min(W / box.width(), (H - name_h) / box.height())
        ox, oy = W / 2 - box.center().x() * s, (H - name_h) - box.bottom() * s
        return QPointF(ox + 40 * s, oy - 112 * s)

    # --- cadence : 60 i/s pendant une animation, 30 i/s au repos, arrêt complet si invisible
    def now(self):
        return self.clock.elapsed() / 1000.0

    def play(self, a):
        if isinstance(a, str):
            a = next((x for x in G_ANIMS if x.name == a), None)
        if a is None:
            return
        self.anim, self.a_t0 = a, self.now()
        self._fresh = True
        self.update()

    def play_next(self):
        if not self.queue:
            self.queue = list(range(len(G_ANIMS)))
            random.shuffle(self.queue)
        self.play(G_ANIMS[self.queue.pop(0)])

    def say(self, n):
        self.talk = max(self.talk, n)

    def enterEvent(self, e):
        self.hover = True
        if self.mode == "rail" and self.anim is None:
            self.play(G_HELLO)

    def leaveEvent(self, e):
        self.hover = False

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.mode == "rail":
                if self.anim is None or self.anim is G_HELLO:
                    self.play_next()
            self.clicked.emit()

    def contextMenuEvent(self, e):
        if self.mode != "rail":
            return
        m = QMenu(self)
        if self.app is not None:
            m.addAction("Parler à Gaël (SOS)", lambda: self.app.go_tab("sos"))
            m.addSeparator()
        for a in G_ANIMS:
            m.addAction(a.label, lambda a=a: self.play(a))
        m.exec(e.globalPos())

    def _tick(self, tt, dt):
        """Horloge commune : 60 i/s pendant une animation (ou s'il parle), 30 i/s au repos, rien s'il est caché."""
        t = self.now()
        if self.anim is None and self.mode == "rail" and ANIM and t > self.next_at:
            self.play_next()
        if self.anim is not None and t - self.a_t0 > self.anim.dur:
            self.anim = None
            self.next_at = t + random.uniform(26, 48)
        busy = self.anim is not None or self.talk > 0 or self.hover or abs(self.coif_v) > .5
        # au repos, seuls la respiration et le léger balancement de la tête bougent, très lentement : 15 images/s
        # suffisent (deux fois moins de dessin) ; un clignement ou un regard qui se déplace repassent à 30 images/s
        lively = t >= self.blink_at - .02 or abs(self.look_to - self.look_cur) > .03
        if not busy and (not ANIM or t - self._drawn < (.030 if lively else .064)):
            return False
        self._drawn = t
        self._fresh = True
        return True

    # --- pose courante
    def current_pose(self, t, dt=.016):
        P = dict(POSE0)
        br = math.sin(t * 2.1)
        P.update(sq=br * .012, la1=10 + br * 2.5, ra1=10 + br * 2.5, head=math.sin(t * .7) * 1.6)
        if t > self.look_at:
            self.look_to = random.choice((-1, -.5, 0, 0, .5, 1))
            self.look_at = t + random.uniform(2.5, 6)
        self.look_cur += (self.look_to - self.look_cur) * min(1.0, dt * 7)
        P["look"] = self.look_cur
        if t > self.blink_at:
            d = t - self.blink_at
            P["blink"] = math.sin(min(1, d / .16) * math.pi)
            if d > .16:
                self.blink_at = t + random.uniform(2.2, 5.5)
        if self.think:
            a1, a2 = ik(1, 8, -40)
            P.update(ra1=a1, ra2=a2, look=-.8, lookv=-1, eye=4, head=-5)
        if self.anim is not None:
            at = t - self.a_t0
            AP = self.anim.pose(at, dict(P))
            w = min(win(at, 0, .35), 1 - win(at, self.anim.dur - .35, self.anim.dur))
            blink = P["blink"]
            P = blend(P, AP, w)
            P["blink"] = blink if AP.get("eye", 0) in (0, 3, 4) else 0
        return P

    def spring(self, t, P, dt):
        """La coiffe suit les mouvements avec un léger retard (ressort amorti)."""
        hx = P["x"]
        ha = P["rot"] + P["head"]
        if self.prev is None:
            self.prev = (hx, ha, 0.0)
        px, pa, pvx = self.prev
        vx = (hx - px) / dt if dt > 0 else 0.0
        ax = (vx - pvx) / dt if dt > 0 else 0.0
        da = (ha - pa) / dt if dt > 0 else 0.0
        acc = -90.0 * self.coif - 9.0 * self.coif_v - _cl(ax, -900, 900) * .02 - _cl(da, -400, 400) * .05
        self.coif_v += acc * dt
        self.coif += self.coif_v * dt
        self.coif = _cl(self.coif, -16, 16)
        self.prev = (hx, ha, vx)

    def paintEvent(self, e):
        # Gaël est souvent repeint sans avoir bougé : la fenêtre change de taille, on change d'onglet, le menu se met à jour…
        # On recopie alors simplement sa dernière image (quelques microsecondes au lieu de près d'une milliseconde). Une
        # nouvelle image n'est dessinée que si son horloge l'a demandé (_fresh) ou si son état visible a changé.
        dpr = self.devicePixelRatioF()
        sig = (self.width(), self.height(), dpr, self.on_air, self.think, self.talk > 0, self.hover, id(self.anim))
        if self._pm is not None and not self._fresh and sig == self._pm_sig:
            q = QPainter(self)
            q.drawPixmap(0, 0, self._pm)
            self._paint_name(q)
            return
        if self._pm is not None and calm() and sig[2:] == self._pm_sig[2:]:
            # fenêtre en cours de redimensionnement : Gaël change seulement d'échelle ; on agrandit ou réduit sa dernière
            # image le temps du geste (il est redessiné net dès que la taille ne bouge plus)
            q = QPainter(self)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            o0, s0 = self._origin(*self._pm_sig[:2])
            o1, s1 = self._origin(self.width(), self.height())
            q.translate(o1)
            q.scale(s1 / s0, s1 / s0)
            q.translate(-o0)
            q.drawPixmap(0, 0, self._pm)
            q.resetTransform()
            self._paint_name(q)
            if not getattr(self, "_sharp_pending", False):   # image nette une fois la taille stabilisée
                self._sharp_pending = True
                QTimer.singleShot(400, self._sharpen)
            return
        self._fresh = False
        pm = QPixmap(max(1, int(round(self.width() * dpr))), max(1, int(round(self.height() * dpr))))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = new_painter(pm)
        self._paint_frame(p)
        p.end()
        self._pm, self._pm_sig = pm, sig
        q = QPainter(self)
        q.drawPixmap(0, 0, pm)
        self._paint_name(q)

    def _sharpen(self):
        self._sharp_pending = False
        if calm():
            self._sharp_pending = True
            QTimer.singleShot(250, self._sharpen)
            return
        self._fresh = True
        self.update()

    def _origin(self, W, H):
        """Point d'ancrage (bas de Gaël) et échelle de son dessin pour un widget de W × H."""
        box = self.BOX[self.mode]
        name_h = 18 if self.mode == "rail" else 0
        s = min(W / box.width(), (H - name_h) / box.height())
        return QPointF(W / 2 - box.center().x() * s, (H - name_h) - box.bottom() * s), s

    def _paint_frame(self, p):
        t = self.now()
        dt = _cl(t - self.t_last, 0.0, .05)
        self.t_last = t
        if self.talk > 0:
            self.talk = max(0.0, self.talk - dt)
        P = self.current_pose(t, dt)
        self.spring(t, P, dt)
        P["coif"] += self.coif
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        W, H = self.width(), self.height()
        box = self.BOX[self.mode]
        name_h = 18 if self.mode == "rail" else 0
        s = min(W / box.width(), (H - name_h) / box.height())
        p.translate(W / 2 - (box.center().x()) * s, (H - name_h) - box.bottom() * s)
        p.scale(s, s)
        a = self.anim
        at = t - self.a_t0 if a else 0
        if a:
            a.back(p, at, self.gp, P)
        self.gp.draw(p, P, talk=min(1.0, self.talk * 2), on_air=self.on_air, t=t,
                     hand_r=a.hand_r(at) if a else None, hand_l=a.hand_l(at) if a else None, dial=t * (1.6 if self.on_air else .5))
        if a:
            a.front(p, at, self.gp, P)
        if self.think:
            for i in range(3):
                c = QColor(MUT)
                c.setAlphaF(.35 + .65 * max(0.0, math.sin(t * 6 - i * .9)))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawEllipse(QPointF(24 + i * 7, -150), 2.2, 2.2)

    def _paint_name(self, p):
        """Nom sous Gaël (menu) : dessiné directement sur l'écran, pour un texte aussi net que le reste."""
        if self.mode == "rail":
            W, H = self.width(), self.height()
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
            f = QFont(self.font())
            f.setPointSizeF(9.5)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor(TXT))
            fm = QFontMetrics(f)
            name = "Gaël, le radio-bot"
            tw = fm.horizontalAdvance(name)
            x0 = (W - tw - 12) / 2
            p.drawText(QPointF(x0 + 12, H - 4), name)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(OKC if self.on_air else MUT))
            p.drawEllipse(QPointF(x0 + 3, H - 8), 3, 3)


class GaelHead(QWidget):
    """Petite tête de Gaël pour les voyants d'état : contente (ok), inquiète (silence, attente) ou fâchée (panne).
    Dessinée seulement quand l'état change (et une petite secousse en cas de panne) : coût quasi nul."""
    MOODS = {"ok": dict(eye=1, mouth=2, eyec=None), "wait": dict(eye=0, mouth=0, eyec="#8a93a8"),
             "warn": dict(eye=2, mouth=3, eyec="#ffb347"), "bad": dict(eye=5, mouth=4, eyec="#ff5d6c")}
    _gp = None

    def __init__(self, size=34, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.mood, self.t, self.level, self.tt = "wait", 0, .7, 0.0
        if GaelHead._gp is None:
            GaelHead._gp = GaelPainter()
        Ticker.add(self, self._step, 30)

    def _step(self, t, dt):
        self.tt = t
        return self.mood in ("ok", "bad")

    def set_level(self, db):
        """Crête mesurée (dB) : la forme d'onde est plus ou moins haute selon le niveau réel du flux."""
        self.level = _cl((db + 50) / 44, .25, 1.0) if db is not None else .7

    def set_mood(self, m):
        if m != self.mood:
            self.mood = m
            self.setToolTip({"ok": "Gaël : tout va bien, le son passe", "wait": "Gaël : vérification en attente",
                             "warn": "Gaël : silence sur ce flux", "bad": "Gaël : ce flux ne répond pas !"}.get(m, ""))
            self.update()

    def set_color(self, c):                    # compatibilité avec l'ancien voyant
        self.set_mood("ok" if c in ("#2ecc71", OKC) else ("bad" if c in ("#e74c3c", BADC) else "wait"))

    def tick(self):
        pass

    def paintEvent(self, e):
        p = new_painter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        W, H = self.width(), self.height()
        s = W / 64.0
        P = dict(POSE0)
        P.update(self.MOODS.get(self.mood, {}))
        P["mini"] = True
        if self.mood == "ok":                   # tout va bien : petite forme d'onde vivante à la place de la tête
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(OKC, 34))
            p.drawRoundedRect(QRectF(0, 0, W, H), 10, 10)
            n, t = 7, self.tt
            bw = W / (n * 1.7)
            rects = []
            for i in range(n):
                v = .35 + .65 * abs(math.sin(t * (2.3 + i * .37) + i * 1.3) * math.sin(t * 1.1 + i * .8))
                hh = max(2.5, v * self.level * (H - 10))
                x = (W - (n - 1) * bw * 1.7 - bw) / 2 + i * bw * 1.7
                rects.append(QRectF(x, H / 2 - hh / 2, bw, hh))
            p.setBrush(QColor(OKC))
            for r in rects:
                p.drawRoundedRect(r, bw / 2, bw / 2)
            return
        if MINI:                                # minimaliste : un simple voyant, pas de robot
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor({"bad": BADC, "warn": "#ffb347"}.get(self.mood, MUT)))
            p.drawEllipse(QPointF(W / 2, H / 2), W * .16, W * .16)
            return
        if self.mood == "bad":
            P["head"] = math.sin(self.tt * 4.2) * 2.4
        if self.mood == "bad":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(BADC, 50))
            p.drawEllipse(QPointF(W / 2, H / 2 + 2 * s), W / 2, W / 2.2)
        p.translate(W / 2, H - .5)
        p.scale(s, s)
        p.rotate(P["head"])
        GaelHead._gp._head(p, P, 0, 0.0)


class Splash(QWidget):
    """Écran de démarrage : le phare de Bev émet ses ondes. Une seule animation, du double-clic à l'ouverture : l'image
    affichée par l'exécutable avant même que Python démarre (build/splash.png) est la toute première image de cette
    animation (même taille, même place, même dessin), qui prend le relais sans saut."""
    current = None           # l'écran de démarrage affiché en ce moment (fermé par la fenêtre principale)
    W, H = 460, 270

    def __init__(self, t0=None):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(self.W, self.H)
        self.clock = QElapsedTimer()
        self.clock.start()
        self.t_fixed = t0
        try:
            g = QApplication.primaryScreen().availableGeometry()
            self.move(g.center() - self.rect().center())
        except Exception:
            pass

    def spin(self, ms):
        """Anime pendant `ms` millisecondes (la boucle d'événements reste vivante)."""
        end = self.clock.elapsed() + ms
        while self.clock.elapsed() < end:
            self.update()
            QApplication.processEvents()
            QThread.msleep(10)

    def tick(self):
        """Une image de plus pendant la construction de la fenêtre (dessin immédiat, sans traiter d'autres événements)."""
        try:
            self.repaint()
        except Exception:
            pass

    def paintEvent(self, e):
        t = self.t_fixed if self.t_fixed is not None else self.clock.elapsed() / 1000.0
        p = new_painter(self)
        W, H = self.width(), self.height()
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, QColor(11, 31, 58))
        g.setColorAt(1, QColor(17, 45, 80))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(0, 0, W, H))
        p.setPen(QPen(QColor(40, 66, 104), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(1, 1, W - 2, H - 2))
        cx, cy, r = 102.0, 124.0, 66.0
        lx, ly = cx, cy - r + 129 * 2 * r / 560          # lanterne du phare
        # ondes émises : elles partent de la lanterne et s'éloignent en s'effaçant (à t = 0 : rien encore)
        for k in range(3):
            u = (t * .7 - k / 3.0)
            if u < 0:
                continue
            u %= 1.0
            rr = 40 + u * 52
            c = QColor(255, 176, 59)
            c.setAlphaF(_cl((1 - u) * .7 * min(1.0, t * 2)))
            p.setPen(QPen(c, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for a0 in (-38, 142):
                p.drawArc(QRectF(lx - rr, ly - rr, 2 * rr, 2 * rr), int(a0 * 16), int(76 * 16))
        pulse = 1.0 if t <= 0 else .6 + .4 * (math.cos(t * 4.4) + 1) / 2
        draw_logo(p, cx, cy, r, None, 3, 0.0, False, True, pulse=pulse)   # sans tuile : les ondes partent bien du phare
        f = QFont(self.font())
        f.setPixelSize(64)
        f.setWeight(QFont.Weight.ExtraBold)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(196, 52, 250, 80), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, APP)
        f2 = QFont(self.font())
        f2.setPixelSize(14)
        f2.setWeight(QFont.Weight.DemiBold)
        f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        p.setFont(f2)
        p.setPen(QColor(255, 210, 122))
        p.drawText(QRectF(200, 134, 250, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "BROADCAST TOOL")
        f3 = QFont(self.font())
        f3.setPixelSize(14)
        p.setFont(f3)
        p.setPen(QColor(170, 186, 210))
        p.drawText(QRectF(200, 166, 250, 22), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "Démarrage…")
        bw, x0, y0 = 150.0, 200.0, 200.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(40, 66, 104))
        p.drawRoundedRect(QRectF(x0, y0, bw, 4), 2, 2)
        if t > 0:
            p.setBrush(QColor(255, 176, 59))
            u = (t * .9) % 1.0
            a, bb = max(0, u * 1.5 - .5), min(1, u * 1.5)
            p.drawRoundedRect(QRectF(x0 + a * bw, y0, (bb - a) * bw, 4), 2, 2)
        p.end()


def render_splash(path):
    """Première image de l'écran de démarrage, enregistrée pour l'exécutable (construction GitHub : tools/prepare.py)."""
    sp = Splash(t0=0.0)
    sp.grab().save(path)


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
