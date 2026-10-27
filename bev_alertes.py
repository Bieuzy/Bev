# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - écoute des flux surveillés, alertes de panne (mail, SMS, Discord, ntfy, Slack), MIDI, aide."""
from bev_widgets import *  # noqa: F401,F403

# ------------------------------------------------- monitoring, alertes, dialogues
def probe_stream(url, thr=-50.0, secs=5):
    """Écoute `secs` secondes d'un flux. Retourne (statut, détail) :
    statut = "ok" (audio présent) ou "down" (inactif ou silence)."""
    if not shutil.which("ffmpeg"):
        return "down", "ffmpeg introuvable"
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-rw_timeout", "10000000",
           "-t", str(secs), "-i", url, "-vn", "-af", "volumedetect", "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=secs + 30, stdin=subprocess.DEVNULL,
                           creationflags=0x08000000 if SYS == "Windows" else 0)
    except subprocess.TimeoutExpired:
        return "down", "Flux inactif : délai dépassé"
    except Exception as e:
        return "down", f"Erreur : {e}"
    m = re.search(r"max_volume:\s*(-inf|-?[\d.]+)\s*dB", r.stderr)
    if not m:
        lines = [ln.strip() for ln in r.stderr.splitlines() if ln.strip()]
        why = redact(lines[-1])[:90] if lines else "aucune réponse"
        return "down", f"Flux inactif : {why}"
    level = -99.0 if m.group(1) == "-inf" else float(m.group(1))
    if level > thr:
        return "ok", f"Audio présent (crête {level:.0f} dB)"
    return "down", "Connecté mais pas d'audio (silence)"


def fetch_listeners(url):
    """Icecast : nombre d'auditeurs d'un flux via status-json.xsl (None si inconnu)."""
    m = re.match(r"^(https?://[^/]+)(/[^?#]*)?", url)
    if not m or not m.group(2):
        return None
    base, mount = m.group(1), m.group(2)
    try:
        req = urllib.request.Request(base + "/status-json.xsl",
                                     headers={"User-Agent": "Bev/2.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        src = data["icestats"].get("source") or []
        for s in [src] if isinstance(src, dict) else src:
            if s.get("listenurl", "").endswith(mount):
                return int(s.get("listeners", 0))
    except Exception as _ex:
        trace("fetch_listeners", _ex)
    return None


import smtplib
from email.message import EmailMessage


def norm_txt(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def log_class(msg):
    m = norm_txt(msg)
    if any(k in m for k in ("erreur", "impossible", "inactif", "aucun signal", "panne", "echec", "non envoye",
                            "refus", "perdu", "coupee")):
        return "bad"
    if any(k in m for k in ("retabli", "retrouve", "installe", "en direct", "passe par", "reussi", "ok")):
        return "ok"
    if any(k in m for k in ("bascule", "secours", "conseil", "retard", "dump", "alerte", "mute")):
        return "warn"
    return "info"


class Alerts:
    """Alertes : bip + message (Discord / Slack / ntfy / URL), mail et SMS pour les pannes."""
    KINDS = ["Discord", "Slack", "ntfy", "Générique (JSON)"]
    SMS = ["Free Mobile", "Twilio"]
    OUTAGE_S = 60

    # Pannes suivies par le moteur (une alerte au début, une à la fin de CHAQUE panne) : jamais filtrées par le délai
    # anti-répétition, et envoyées aussi par mail / SMS. Les autres alertes gardent ce délai (reconnexions répétées…).
    INCIDENT_RE = re.compile(r"^(silence|fallback-silent|out-[0-9a-f]{8})(-ok)?$")
    URGENT_RE = re.compile(r"^(silence|fallback-silent)(-ok)?$|^engine-crash$")
    RETRY_S, RETRY_FOR_S = 30, 1800       # un envoi raté est retenté toutes les 30 s pendant 30 min

    def __init__(self, app):
        self.app = app
        self.last = {}
        self.q = queue.Queue()
        self.sent = []                     # (heure, canal, texte, ok) : historique des envois, pour les tests et le journal
        threading.Thread(target=self._sender, daemon=True).start()

    def cfg(self):
        return self.app.data["alerts"]

    def wanted(self, key, c):
        return not ((key.startswith("out-") and not c.get("on_output", True)) or
                    (key.startswith(("fallback", "silence")) and not c.get("on_fallback", True)) or
                    (key.startswith("mon-") and not c.get("on_monitor", True)))

    def send(self, text, key=None, force=False, urgent=False, sound=False):
        """Alerte : journal + message / mail / SMS selon les réglages. Le bip est réservé aux vraies pannes (sound=True) :
        une reconnexion, une bascule automatique sur le secours ou un retour à la normale ne bipent pas."""
        c = self.cfg()
        text = redact(text)
        incident = bool(key and self.INCIDENT_RE.match(key))
        if key and not force:
            if not incident and time.time() - self.last.get(key, 0) < 120:
                return
            if not self.wanted(key, c):
                return
        if key:
            self.last[key] = time.time()
            if self.URGENT_RE.match(key):
                urgent = True
                sound = sound or not key.endswith("-ok")
        self.app.log("" + text)
        if sound and c.get("sound", True):
            self.app.ui(self.beep)
        if (c.get("url") or "").strip():
            self.q.put(("msg", text, time.time()))
        if urgent:
            if c.get("mail_on"):
                self.q.put(("mail", text, time.time()))
            if c.get("sms_on"):
                self.q.put(("sms", text, time.time()))

    def _sender(self):
        """Envois dans l'ordre, un par un. Un envoi raté (souvent : la panne, c'est justement Internet) est gardé et retenté
        toutes les 30 s pendant 30 min, au lieu d'être perdu. Les SMS sont espacés (Free Mobile refuse les rafales)."""
        waiting, last_sms = [], 0.0
        while True:
            try:
                item = self.q.get(timeout=1.0)
                waiting.append([item[0], item[1], item[2], 0.0])
            except queue.Empty:
                pass
            now = time.time()
            for it in list(waiting):
                kind, text, t0, nxt = it
                if now < nxt:
                    continue
                if kind == "sms" and now - last_sms < 3.0:
                    continue
                stamp = time.strftime("%H:%M", time.localtime(t0))
                body = text if now - t0 < 90 else f"[{stamp}] {text}"       # message retardé : l'heure de la panne
                try:
                    ok = {"msg": lambda: self.post(self.cfg().get("kind", "Discord"), (self.cfg().get("url") or "").strip(), body),
                          "mail": lambda: self.mail(body), "sms": lambda: self.sms(body)}[kind]()
                except Exception:
                    ok = False
                if kind == "sms":
                    last_sms = time.time()
                self.sent.append((time.time(), kind, body, bool(ok)))
                del self.sent[:-200]
                if ok or now - t0 > self.RETRY_FOR_S:
                    waiting.remove(it)
                    if not ok:
                        self.app.log(f"Alerte abandonnée après 30 min d'essais ({kind}) : {text[:80]}")
                else:
                    it[3] = now + self.RETRY_S

    def channels(self):
        c = self.cfg()
        out = []
        if (c.get("url") or "").strip():
            out.append(c.get("kind", "Discord"))
        if c.get("mail_on") and c.get("mail_to"):
            out.append("mail")
        if c.get("sms_on") and c.get("sms_to"):
            out.append("SMS")
        return out

    def beep(self):
        """Bip d'alerte joué en arrière-plan (winsound.Beep bloquait l'interface 0,3 s à chaque alerte).
        Jamais plus d'un bip toutes les 20 s, même si plusieurs pannes arrivent en même temps."""
        now = time.time()
        if now - getattr(self, "_last_beep", 0.0) < 20:
            return
        self._last_beep = now
        if SYS == "Windows":
            def b():
                try:
                    import winsound
                    winsound.Beep(880, 300)
                except Exception:
                    pass
            threading.Thread(target=b, daemon=True).start()
        else:
            QApplication.beep()

    def post(self, kind, url, text):
        try:
            hdr = {"User-Agent": "Bev/2.0", "Content-Type": "application/json"}
            if kind == "Discord":
                body = json.dumps({"content": "" + text}).encode()
            elif kind == "Slack":
                body = json.dumps({"text": "" + text}).encode()
            elif kind == "ntfy":
                body, hdr["Content-Type"] = text.encode("utf-8"), "text/plain; charset=utf-8"
                hdr["Title"] = APP
            else:
                body = json.dumps({"message": text, "source": APP}).encode()
            urllib.request.urlopen(urllib.request.Request(url, body, hdr), timeout=8).read()
            return True
        except Exception as e:
            self.app.log(f"Alerte non envoyée ({kind}) : {e} · nouvel essai dans 30 s")
            return False

    def mail(self, text):
        c = self.cfg()
        try:
            msg = EmailMessage()
            msg["Subject"] = "" + APP + " : " + text[:70]
            msg["From"] = c.get("mail_from") or c.get("mail_user") or "radio@localhost"
            msg["To"] = c["mail_to"]
            msg.set_content(text + "\n\n" + time.strftime("%d/%m/%Y %H:%M:%S"))
            port = int(c.get("mail_port") or 587)
            if port == 465:
                s = smtplib.SMTP_SSL(c["mail_host"], port, timeout=15)
            else:
                s = smtplib.SMTP(c["mail_host"], port, timeout=15)
                if c.get("mail_tls", True):
                    s.starttls()
            if c.get("mail_user"):
                s.login(c["mail_user"], c.get("mail_pw", ""))
            s.send_message(msg)
            s.quit()
            self.app.log("Mail d'alerte envoyé à " + c["mail_to"])
            return True
        except Exception as e:
            self.app.log(f"Mail non envoyé : {e} · nouvel essai dans 30 s")
            return False

    def sms(self, text):
        c = self.cfg()
        try:
            if c.get("sms_provider") == "Twilio":
                data = urllib.parse.urlencode({"From": c.get("sms_from", ""), "To": c["sms_to"],
                                               "Body": text[:300]}).encode()
                req = urllib.request.Request(
                    f"https://api.twilio.com/2010-04-01/Accounts/{c['sms_user']}/Messages.json", data)
                tok = base64.b64encode(f"{c['sms_user']}:{c.get('sms_key', '')}".encode()).decode()
                req.add_header("Authorization", "Basic " + tok)
            else:  # Free Mobile : le numéro est celui du compte, « sms_to » sert de mémo
                q = urllib.parse.urlencode({"user": c["sms_user"], "pass": c.get("sms_key", ""), "msg": text[:300]})
                base = (c.get("sms_url") or "").strip() or "https://smsapi.free-mobile.fr/sendmsg"
                # (adresse personnalisée : l'identifiant, la clé et le message y sont ajoutés, comme pour l'adresse
                # par défaut ; avant, ils étaient oubliés et le SMS échouait à chaque fois)
                if "user=" in base:               # adresse complète déjà munie de l'identifiant : seul le message s'ajoute
                    q = urllib.parse.urlencode({"msg": text[:300]})
                req = urllib.request.Request(base + ("&" if "?" in base else "?") + q)
            urllib.request.urlopen(req, timeout=15).read()
            self.app.log("SMS d'alerte envoyé à " + c["sms_to"])
            return True
        except Exception as e:
            self.app.log(f"SMS non envoyé : {e} · nouvel essai dans 30 s")
            return False

DAB_BITRATES = ["32", "48", "64", "72", "80", "88", "96", "104", "112", "120", "128", "160", "192"]
REC_FORMATS = list(RecordOutput.CODECS)

# (clé, libellé, type, options)
FIELDS = {
    "internet": [
        ("name", "Nom du flux", "entry", None),
        ("protocol", "Protocole", "combo", ["Icecast", "Shoutcast"]),
        ("host", "Serveur", "entry", None),
        ("port", "Port", "entry", None),
        ("sc_port", "Port source Shoutcast (vide = port + 1)", "entry", None),
        ("mount", "Mountpoint (Icecast)", "entry", None),
        ("user", "Utilisateur (Icecast)", "entry", None),
        ("password", "Mot de passe source", "password", None),
        ("tls", "Connexion chiffrée TLS (Icecast, si le serveur l'accepte)", "check", None),
        ("genre", "Genre", "entry", None),
        ("desc", "Description", "entry", None),
        ("format", "Format", "combo", list(FORMATS)),
        ("bitrate", "Débit (kbps)", "combo", BITRATES),
        ("channels", "Canaux", "combo", ["2", "1"]),
        ("processing", "Traitement audio", "combo", list(PROCESSING)),
        ("reconnect", "Reconnexion automatique", "check", None),
    ],
    "fm": [
        ("name", "Nom du flux", "entry", None),
        ("device", "Carte son de sortie (vers l'émetteur)", "devices", None),
        ("processing", "Traitement audio", "combo", list(PROCESSING)),
        ("rds", "Envoyer le texte RDS", "check", None),
        ("ps", "PS - nom de station (8 caractères max)", "entry", None),
        ("rds_mode", "Transport RDS", "combo", ["Fichier / pipe", "UDP", "TCP"]),
        ("rds_target", "Cible RDS (fichier, ou hôte:port)", "file", None),
        ("rds_template", "Modèle du message ({PS} {RT}, \\n = ligne)", "entry", None),
        ("reconnect", "Reconnexion automatique", "check", None),
    ],
    "dab": [
        ("name", "Nom du flux", "entry", None),
        ("mode", "Mode", "combo", ["ODR-AudioEnc", "AAC réseau (UDP/RTP/TCP)"]),
        ("profile", "Codec DAB+", "combo", ["HE-AAC (SBR)", "HE-AAC v2 (SBR+PS)", "AAC-LC"]),
        ("bitrate", "Débit (kbps)", "combo", DAB_BITRATES),
        ("processing", "Traitement audio", "combo", list(PROCESSING)),
        ("odr_path", "Programme odr-audioenc", "file", None),
        ("dest", "Destination ODR (ex. tcp://127.0.0.1:9000)", "entry", None),
        ("extra", "Options ODR supplémentaires", "entry", None),
        ("net_url", "URL réseau (ex. udp://192.168.1.20:5004)", "entry", None),
        ("net_format", "Conteneur réseau", "combo", ["mpegts", "adts", "rtp"]),
        ("dls_file", "Fichier texte DLS (pour odr-padenc -t)", "file", None),
        ("reconnect", "Reconnexion automatique", "check", None),
    ],
    "record": [
        ("name", "Nom du flux", "entry", None),
        ("folder", "Dossier d'enregistrement", "folder", None),
        ("format", "Format", "combo", REC_FORMATS),
        ("bitrate", "Débit (kbps)", "combo", BITRATES),
        ("rotate", "Nouveau fichier toutes les (minutes)", "entry", None),
        ("keep_days", "Conserver (jours, 0 = illimité)", "entry", None),
        ("processing", "Traitement audio", "combo", list(PROCESSING)),
        ("reconnect", "Relancer automatiquement", "check", None),
    ],
}
ADV = {"internet": ("sc_port", "user", "tls", "genre", "desc", "channels", "processing", "reconnect"),
       "fm": ("processing", "rds", "ps", "rds_mode", "rds_target", "rds_template", "reconnect"),
       "dab": ("profile", "processing", "odr_path", "extra", "net_format", "dls_file", "reconnect"),
       "record": ("bitrate", "keep_days", "processing", "reconnect")}
HINTS = {
    "internet": "Les infos du serveur de streaming : adresse, port, point de montage et mot de passe source.",
    "fm": "Choisis la carte son reliée à l'entrée de ton émetteur ou processeur FM. Le RDS se règle dans les réglages avancés.",
    "dab": "Envoie l'audio à ton multiplex DAB+ (ODR-AudioEnc) ou en AAC sur le réseau. Les autres options sont dans les réglages avancés.",
    "record": "Garde une trace de tout ce qui part à l'antenne, découpée en fichiers. Pour la pige ARCOM, utilise l'onglet Enregistrement.",
}

def key_token(e):
    """Nom court de la touche pressée (F5, q, 7, KP_1…) pour les raccourcis du cartoucheur ; '' si inutilisable."""
    if e.state & 0x4 or e.state & (0x20000 if SYS == "Windows" else 0x8):  # Ctrl ou Alt : réservé aux raccourcis du système
        return ""
    ks = e.keysym
    if re.fullmatch(r"F\d{1,2}", ks):
        return ks
    if ks.startswith("KP_") and len(ks) > 3 and ks[3:].isalnum():
        return ks
    ch = e.char
    if len(ch) == 1 and ch.isprintable() and not ch.isspace():
        return ch.lower()
    return ""


def key_label(t):
    return {"": "", "KP_Add": "Pavé +"}.get(t, t.upper() if len(t) == 1 else t.replace("KP_", "Pavé "))


def midi_token(msg):
    t = getattr(msg, "type", "")
    if t == "note_on" and msg.velocity > 0:
        return f"n{msg.note}"
    if t == "control_change" and msg.value >= 64:
        return f"c{msg.control}"
    if t == "program_change":
        return f"p{msg.program}"
    return ""


def midi_label(t):
    return "" if not t else {"n": "note ", "c": "contrôleur ", "p": "programme "}.get(t[0], "") + t[1:]


class MidiListener:
    """Écoute toutes les entrées MIDI (pads, consoles) si le module « mido » est présent."""

    def __init__(self, cb):
        self.cb, self.ports, self.err = cb, [], ""

    def start(self):
        self.stop()
        self.err = ""
        try:
            import mido
            for name in mido.get_input_names():
                try:
                    self.ports.append(mido.open_input(name, callback=self._msg))
                except Exception as ex:
                    self.err = str(ex)[:100]
        except Exception as ex:
            self.err = str(ex)[:100] or "module absent"
        return len(self.ports)

    def _msg(self, msg):
        t = midi_token(msg)
        if t:
            self.cb(t)

    def stop(self):
        for p in self.ports:
            try:
                p.close()
            except Exception:
                pass
        self.ports = []

# ---------------------------------------------------------------- application
ADVICE = [
    (r"401|Unauthorized|Mot de passe refusé", "Mot de passe, utilisateur ou mountpoint refusé par le serveur : vérifie-les dans le flux."),
    (r"Connection refused|refusée", "Serveur injoignable : vérifie l'adresse, le port et le pare-feu du serveur."),
    (r"timed out|Délai|délai", "Pas de réponse à temps : serveur éteint, mauvais port ou connexion réseau coupée."),
    (r"404|Not Found", "Adresse ou mountpoint inexistant sur le serveur."),
    (r"Permission denied|Access is denied|Accès", "Accès refusé : autorise le micro pour les applications de bureau (Windows > Confidentialité) ou les droits du dossier."),
    (r"Unknown encoder|Encoder .* not found", "Ton ffmpeg n'a pas cet encodeur : installe une version « full » (gyan.dev)."),
    (r"sounddevice manquant", "Installe le module de sortie son depuis l'onglet SOS (bouton « Installer sounddevice »)."),
    (r"odr-audioenc introuvable", "Indique le chemin complet de odr-audioenc dans le flux DAB+."),
    (r"Could not find|introuvable|No such file|Lecture impossible", "Fichier ou périphérique introuvable : revérifie le nom ou le chemin."),
    (r"Address already in use|already in use", "Ce port ou cette adresse est déjà utilisé par un autre programme."),
    (r"Entrée audio indisponible|Capture impossible", "L'entrée audio ne répond pas : rebranche-la ou choisis-en une autre dans la liste."),
    (r"Aucun signal", "Pas de signal en entrée : vérifie le niveau, le câble, ou le seuil de silence."),
]
FAQ = """Démarrage rapide
 1. Onglet Diffusion : choisis ton entrée audio, ajoute une ou plusieurs sorties (Internet, FM, DAB+, Enregistrement), puis ▶ DÉMARRER.
 2. Playlist de secours : coche l'option et ajoute des fichiers ; l'app bascule seule si le signal disparaît, avec un fondu enchaîné.
 3. Monitoring : ajoute des adresses de flux ; rond vert = audio présent, rond rouge = inactif ou silence.

Problèmes fréquents
 • Liste d'entrées vide : ffmpeg est absent ou ne voit pas le micro (autorisations Windows, bouton ↻).
 • 401 / mot de passe refusé : vérifie le mot de passe source et le mountpoint.
 • Rien en entrée sous Windows : choisis « Son de l'ordinateur » (bouton d'activation sous la liste).
 • Ça saccade : baisse le débit, ferme les programmes lourds, vérifie la sortie en erreur dans la liste.
"""


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
