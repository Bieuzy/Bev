# SPDX-License-Identifier: GPL-3.0-or-later — Bev, copyright (C) 2026 les auteurs de Bev. Voir LICENSE.
"""Bev (interface) - notes de version et mises à jour (vérification GitHub, mise à jour express, installateur)."""
from bev_alertes import *  # noqa: F401,F403

# ------------------------------------------------------------ mise à jour + mini Radiobot
NEWS = {
    "1.4.0": """## Première prise en main

- « Prêt pour l'antenne ? » : au moment de démarrer, tout ce qui manque est montré d'un coup (entrée audio, flux, mot de passe, playlist de secours), avec un bouton pour régler chaque point.
- Au premier lancement, Gaël indique l'étape suivante jusqu'à la première antenne (« Plus tard » ou « Ne plus afficher »).
- Démarrage automatique et reprise après plantage : plus aucune fenêtre ne bloque un démarrage sans personne devant l'écran.

## Support

- « Signaler un problème » (SOS et À propos) : un rapport prêt à envoyer (version, réglages, diagnostic, journaux), sans mot de passe, clé, adresse mail, numéro ni lien d'alerte. Enregistrer, copier, ou ouvrir directement la fiche de bug GitHub.
- Les erreurs internes sont notées avec tous leurs détails ; Gaël propose de les signaler, l'antenne n'est jamais touchée.
- Si Bev se ferme brutalement, il le dit au lancement suivant et propose d'envoyer le rapport.
- Demander « signaler un bug » à Gaël ouvre aussi le rapport.

## Alertes et sons

- « Prévenir en cas de panne » : le voyant vert ne s'allume que si l'envoi a vraiment réussi (test ou alerte). Configuré mais pas testé : orange ; test raté : rouge, avec le canal en cause.
- Plus aucun bip dans Bev (l'option « Bip répété » est retirée) : les pannes se voient à l'écran et partent par message, mail ou SMS.
- Nouveau réglage : couper les sons de Windows pendant que Bev est ouvert (ils reviennent à la fermeture).
- Alertes sur la qualité d'Internet allégées : un message seulement si le problème dure 5 minutes, au plus une fois par heure.

## Interface

- Les bulles de Gaël restent dans sa colonne, au-dessus de lui : la page n'est plus cachée.
- À propos : le phare de Bev, une présentation plus claire.
- Automate de diffusion : fenêtre refaite, avec une explication simple, l'adresse à recopier et un bouton « Tester la réception ».
- Journal : le filtre « Playlist de secours » montre les silences et les relèves.
- Gaël : le goéland est devenu farceur (gare au béret !), et quatre nouvelles animations : le bagad, la table de mixage, la marche des fiertés et l'escalade du pylône FM.""",
    "1.3.0": """## Plus fluide

- Changement d'onglet jusqu'à trois fois plus rapide, y compris le premier clic et juste après avoir changé la taille de la fenêtre : les onglets cachés sont préparés pendant les temps morts.
- Redimensionnement plus léger : chaque page n'est plus mise en page qu'une fois par image (au lieu de trois), et Gaël n'est plus redessiné entièrement pendant le geste.
- Plus de barre de défilement inutile qui apparaissait un instant sur les pages qui tiennent à l'écran.
- Gaël consomme deux fois moins au repos.

## Coulisses

- Le code de Bev est découpé en modules (un par grande partie de l'application) : plus simple et plus sûr à faire évoluer.
- Outil de mesure de la fluidité (tools/perf.py).""",
    "1.2.1": """## Sécurité et solidité

- Préparation des mises à jour signées par l'auteur de Bev (activées dans une prochaine version).
- Mots de passe des serveurs, du mail, des SMS et clé de Gaël chiffrés dans le fichier de réglages (Windows).
- Automate de diffusion : code secret pour les autres postes du réseau, et aucune page web ne peut changer le titre à l'antenne.
- Option de connexion chiffrée (TLS) pour les serveurs Icecast qui l'acceptent.
- FFmpeg fixé sur une version stable (9.0.2), vérifiée à chaque construction.
- Les erreurs discrètes sont notées dans Bev_journaux/bev-erreurs.log pour retrouver les bugs plus vite.
- SMS Free Mobile : l'adresse personnalisée fonctionne.
- Bev est un logiciel libre sous licence GNU GPL v3 ; les licences des composants sont livrées avec l'application.""",
    "1.2.0": """## Processeur d'antenne (bêta)

- **Quatre banques A, B, C, D** de réglages, et **un traitement par flux** : par exemple Internet sur A, FM sur B (filtre 15 kHz), enregistrement en son brut. Tous tournent en même temps.
- **À zéro** (réglage neutre) et **Réinitialiser** (retour au préréglage de la banque).
- **Page repensée, sur un seul écran** : en haut la banque, le préréglage et le bypass ; au milieu ce que fait le processeur (une ligne par étape, dans l'ordre où passe le son) et la banque de chaque flux ; en bas les réglages fins, rangés en 4 onglets (Niveau, Couleur, Compression, Stéréo et sortie).

## Antenne

- Le voyant d'antenne change de couleur : rouge, tout passe ; orange, un flux est HS ; jaune, la playlist de secours est à l'antenne. Il ne déborde plus.
- La **sonie de sortie** (LUFS) est visible sur tous les onglets, dans le bandeau.
- **Automate de diffusion** (Radiologik, RadioDJ…) : titre, artiste et pochette récupérés par fichier ou par le réseau, affichés dans « À l'antenne » et envoyés aux flux.

## Alertes

- Un message quand il n'y a plus de son en entrée, au même délai que la playlist de secours, et une alerte si la playlist de secours est muette.
- Chaque panne est signalée, début et fin, même quand plusieurs se suivent dans la même session ; un envoi raté (Internet coupé) est retenté pendant 30 minutes.

## Divers

- Pas de réglage de débit pour FLAC et WAV (qualité maximale d'office).
- Nouvelle présentation dans « À propos ».
- Affichage : plus aucun chevauchement sur les écrans de portable (1920 × 1080 à 125 %) : l'anecdote « Le saviez-vous ? » ne passe plus sur « À l'antenne », la cartouche en cours ne passe plus sur la sonie dans le bandeau.""",
    "1.1.1": """## Des mises à jour qui passent toutes seules

- **Mise à jour express** : la plupart des versions ne pèsent plus que ~1 Mo. Bev récupère son nouveau code, vérifie son empreinte, et redémarre en quelques secondes. Pas d'installateur à lancer, pas de droits administrateur : Smart App Control, SmartScreen, l'antivirus et le pare-feu n'ont plus rien à bloquer.
- Si une version a besoin de l'installateur complet (nouvelles bibliothèques), Bev le dit clairement, affiche la progression (taille, débit, temps restant), puis ouvre **l'installateur normal**, comme un double-clic : on voit ce qui se passe et Windows peut poser ses questions. Bev ne se ferme que si l'installateur a vraiment démarré ; si Windows le bloque, Bev reste ouvert et montre le fichier pour le lancer à la main.
- Garde-fou : si une nouvelle version ne démarre pas, Bev revient tout seul à la précédente.
- À l'antenne, rien ne coupe le direct : la mise à jour s'applique au prochain démarrage.

## Gaël et ses bulles

- Gaël a une **animation de mise à jour** : il réceptionne les colis de la nouvelle version dans un carton qui se remplit, le ferme d'un ruban et saute de joie quand tout est prêt.
- Les bulles changent en douceur au fil de l'opération (téléchargement, vérification, prêt, redémarrage) au lieu de s'empiler.
- Les bulles ont une largeur bornée et restent dans la fenêtre : elles ne débordent plus sur l'application.
- Après une mise à jour, Gaël l'annonce, avec un lien vers les nouveautés.

## À propos

- Nouvelle case **Nouveautés de la version**, et accès aux notes de toutes les versions.""",
    "1.1.0": """## Un vrai processeur d'antenne

- Traitement temps réel de tout ce qui part à l'antenne : AGC, compresseur-limiteur 5 bandes à phase linéaire, élargisseur stéréo, écrêteur suréchantillonné, limiteur sur les crêtes vraies.
- 10 préréglages radio, réglage MOINS ↔ PLUS, vumètres et sonie LUFS, bypass sans coupure.

## Diffusion

- Les noms des flux défilent dans la pastille EN ANTENNE.
- Playlist de secours : bandeau et cadre jaunes ; le phare change d'animation selon l'état de l'antenne.""",
}


def parse_ver(s):
    """'v1.2.3-beta' -> (1, 2, 3) ; comparaison de versions."""
    nums = re.findall(r"\d+", str(s).split("-")[0])[:4]
    return tuple(int(n) for n in nums) or (0,)


def installed_copy():
    """Bev installé par l'installateur Windows (désinstalleur présent à côté de l'exécutable) : mise à jour automatique possible."""
    return bool(getattr(sys, "frozen", False)) and os.path.isfile(os.path.join(os.path.dirname(sys.executable), "unins000.exe"))


def fmt_size(n):
    n = float(n or 0)
    if n >= 1e6:
        return ("%.1f Mo" % (n / 1e6)).replace(".", ",")
    return "%d Ko" % max(0, round(n / 1e3))


def download(url, dst, prog=None, size=0, timeout=30):
    """Téléchargement HTTPS en flux (progression, reprise sur coupure brève, empreinte SHA-256 calculée en route).
    Renvoie (octets reçus, empreinte)."""
    h = hashlib.sha256()
    got, last_t = 0, 0.0
    for attempt in range(3):
        try:
            hdr = {"User-Agent": "Bev-update"}
            if got:
                hdr["Range"] = f"bytes={got}-"
            rq = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(rq, timeout=timeout) as resp, open(dst, "ab" if got else "wb") as fh:
                if got and resp.status != 206:              # le serveur ne reprend pas : on recommence au début
                    fh.seek(0)
                    fh.truncate()
                    got, h = 0, hashlib.sha256()
                total = int(resp.headers.get("Content-Length") or 0) + got or int(size or 0)
                while True:
                    blk = resp.read(256 * 1024)
                    if not blk:
                        break
                    fh.write(blk)
                    h.update(blk)
                    got += len(blk)
                    now = time.time()
                    if prog and now - last_t > .08:
                        last_t = now
                        prog(got, total)
            if size and got != size:
                raise RuntimeError(f"fichier incomplet ({fmt_size(got)} sur {fmt_size(size)})")
            if prog:
                prog(got, total or got)
            return got, h.hexdigest()
        except (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout) as ex:
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    return got, h.hexdigest()


AV_GONE = "Windows Defender (ou l'antivirus) a supprimé l'installateur en le prenant à tort pour un virus"


def lossless(fmt):
    """FLAC (sans perte) et WAV (non compressé) : qualité maximale d'office, aucun débit à choisir."""
    return str(fmt or "").upper() in ("FLAC", "WAV")


def fmt_quality(fmt, bitrate):
    """« MP3 128 kbit/s », ou « FLAC · sans perte » : jamais de débit affiché pour un format qui n'en a pas."""
    f = str(fmt or "")
    if f.upper() == "FLAC":
        return "FLAC · sans perte"
    if f.upper() == "WAV":
        return "WAV · non compressé"
    return f"{f} {bitrate} kbit/s".strip()


def friendly_dl_error(ex):
    t = str(ex)
    if getattr(ex, "winerror", None) in (225, 226) or "virus" in t.lower():
        return AV_GONE                                     # ERROR_VIRUS_INFECTED / ERROR_VIRUS_DELETED
    if isinstance(ex, urllib.error.HTTPError):
        return f"GitHub a répondu avec l'erreur {ex.code}"
    if isinstance(ex, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)):
        return "la connexion à Internet a été interrompue (ou un pare-feu bloque github.com)"
    if isinstance(ex, PermissionError) or "Permission" in t or "denied" in t.lower():
        return "l'antivirus ou Windows a empêché d'enregistrer le fichier"
    if isinstance(ex, OSError) and getattr(ex, "errno", None) == 28:
        return "le disque est plein"
    return t[:160] or type(ex).__name__


def md_html(md):
    """Notes de version (Markdown simple de GitHub : titres, listes, gras, liens) -> HTML pour l'affichage."""
    import html as _h
    out, in_ul = [], False
    for raw in (md or "").replace("\r", "").split("\n"):
        line = raw.rstrip()
        m = re.match(r"^\s*[-*•]\s+(.*)", line)
        if not m and in_ul:
            out.append("</ul>")
            in_ul = False
        txt = _h.escape(m.group(1) if m else line.lstrip("# ").strip())
        txt = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)
        txt = re.sub(r"(?<![*\w])\*(?!\s)(.+?)\*(?!\w)", r"<i>\1</i>", txt)
        txt = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', txt)
        if m:
            if not in_ul:
                out.append("<ul style='margin-top:2px;margin-bottom:6px'>")
                in_ul = True
            out.append(f"<li style='margin-bottom:3px'>{txt}</li>")
        elif line.startswith("#"):
            out.append(f"<h3 style='margin-top:12px;margin-bottom:4px'>{txt}</h3>")
        elif re.fullmatch(r"-{3,}", line.strip()):
            out.append("<hr>")
        elif txt:
            out.append(f"<p style='margin-top:2px;margin-bottom:6px'>{txt}</p>")
    if in_ul:
        out.append("</ul>")
    return "".join(out)


def signed_manifest(assets, get_raw, pubkey=None):
    """Manifeste (bev-maj.json) de la Release et sa signature. -> (manifeste ou None, None) ou (None, raison du refus).
    Sans clé publique dans Bev : manifeste lu sans contrôle d'auteur (comportement d'avant). Avec la clé : la signature
    (bev-maj.json.sig) est OBLIGATOIRE et doit être valide, sinon la version n'est pas proposée du tout."""
    pubkey = UPDATE_PUBKEY if pubkey is None else pubkey
    by = {str(a.get("name", "")): a for a in assets}
    m = by.get("bev-maj.json")
    if not m:
        return (None, "version non signée (manifeste absent)") if pubkey else (None, None)
    try:
        raw = get_raw(m["browser_download_url"])
    except Exception as ex:
        return (None, f"manifeste illisible ({ex})") if pubkey else (None, None)
    if pubkey:
        sg = by.get("bev-maj.json.sig")
        if not sg:
            return None, "version pas encore signée par l'auteur"
        try:
            sig = bytes.fromhex(get_raw(sg["browser_download_url"]).decode("ascii", "replace").strip())
            ok = ed25519_verify(bytes.fromhex(pubkey), raw, sig)
        except Exception:
            ok = False
        if not ok:
            return None, "signature invalide : cette version ne vient peut-être pas de l'auteur de Bev"
    try:
        man = json.loads(raw.decode("utf-8"))
    except ValueError:
        return (None, "manifeste illisible") if pubkey else (None, None)
    return (man if isinstance(man, dict) else None), None


def express_plan(assets, tag, man):
    """La nouvelle version peut-elle s'installer en express (code seul) ? -> (infos, None) ou (None, raison).
    man : le manifeste déjà lu (et vérifié, si les mises à jour sont signées) par signed_manifest."""
    if not getattr(sys, "frozen", False):
        return None, "lancé depuis le code source"
    by = {str(a.get("name", "")): a for a in assets}
    if not man:
        return None, "pas de mise à jour express pour cette version"
    if not isinstance(man, dict) or _ver_tuple(man.get("version")) != _ver_tuple(tag):
        return None, "manifeste d'une autre version"
    if man.get("runtime") != RUNTIME:
        return None, "cette version change le socle de Bev (bibliothèques)"
    f = by.get(str(man.get("file", "")))
    if not f or not re.fullmatch(r"[0-9a-f]{64}", str(man.get("sha256", ""))):
        return None, "fichier de mise à jour absent"
    need = list(man.get("modules") or []) + (list(man.get("windows_modules") or []) if SYS == "Windows" else [])
    missing = []
    for mod in need:
        try:
            if importlib.util.find_spec(mod) is None:
                missing.append(mod)
        except Exception:
            missing.append(mod)
    if missing:
        return None, "modules absents du socle : " + ", ".join(missing[:4])
    dg = str(f.get("digest") or "")
    if dg.startswith("sha256:") and dg[7:].lower() != man["sha256"]:
        return None, "empreintes différentes entre GitHub et le manifeste"
    return {"url": f["browser_download_url"], "file": os.path.basename(str(man["file"])), "sha256": man["sha256"],
            "size": int(man.get("size") or f.get("size") or 0), "version": str(man["version"])}, None


def check_update(repo, timeout=10):
    """Dernière Release GitHub : {'tag','url','notes','asset'} ; en cas d'échec {'error': message clair}."""
    import urllib.request
    import urllib.error

    def get_raw(url):
        rq = urllib.request.Request(url, headers={"User-Agent": "Bev-update-check", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return r.read(4_000_000)

    def get(url):
        return json.loads(get_raw(url).decode("utf-8", "replace"))
    repo = str(repo).strip().replace("https://github.com/", "").strip("/")
    if repo.count("/") != 1:
        return {"error": "Le dépôt doit s'écrire « compte/depot » (par exemple monpseudo/bev)."}
    try:
        try:
            js = get(f"https://api.github.com/repos/{repo}/releases/latest")
        except urllib.error.HTTPError as ex:
            if ex.code != 404:
                raise
            lst = [x for x in get(f"https://api.github.com/repos/{repo}/releases?per_page=10") if not x.get("draft")]
            if not lst:
                return {"error": "Aucune version n'est publiée sur ce dépôt (ou le dépôt est privé : il doit être public). Crée une Release GitHub pour que les mises à jour soient détectées."}
            js = lst[0]
        exts = (".exe",) if SYS == "Windows" else ((".dmg", ".zip") if SYS == "Darwin" else ())
        assets = [a for a in js.get("assets", []) if exts and str(a.get("name", "")).lower().endswith(exts)]
        assets.sort(key=lambda a: "setup" not in str(a.get("name", "")).lower())     # l'installateur d'abord
        a = assets[0] if assets else {}
        res = {"tag": str(js.get("tag_name", "")), "url": js.get("html_url", ""), "notes": (js.get("body") or "").strip(),
               "title": str(js.get("name") or "").strip(),
               "asset": a.get("browser_download_url", ""), "asset_name": a.get("name", ""), "size": int(a.get("size") or 0),
               "digest": str(a.get("digest") or "")}
        if parse_ver(res["tag"]) <= parse_ver(VERSION):    # rien de plus récent : pas besoin du manifeste
            res["express"], res["express_why"] = None, "déjà à jour"
            return res
        man, why = signed_manifest(js.get("assets", []), get_raw)
        if why:                                    # mises à jour signées : version refusée en bloc (ni express ni installateur)
            return {"error": f"Bev {res['tag'].lstrip('vV')} n'est pas proposée : {why}.", "unsigned": True}
        inst = (man or {}).get("installers") or {}
        if UPDATE_PUBKEY and res["asset_name"]:
            if not re.fullmatch(r"[0-9a-f]{64}", str(inst.get(res["asset_name"], ""))):
                return {"error": f"Bev {res['tag'].lstrip('vV')} n'est pas proposée : installateur absent du manifeste signé.",
                        "unsigned": True}
        res["installer_sha256"] = str(inst.get(res["asset_name"], "")) if UPDATE_PUBKEY else ""
        res["express"], res["express_why"] = express_plan(js.get("assets", []), res["tag"], man)
        return res
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            return {"error": f"Dépôt « {repo} » introuvable. Vérifie son nom, et qu'il est public."}
        if ex.code in (403, 429):
            return {"error": "GitHub limite temporairement les demandes (trop d'essais). Réessaie dans quelques minutes."}
        return {"error": f"GitHub a répondu avec l'erreur {ex.code}."}
    except Exception as ex:
        return {"error": "Impossible de joindre GitHub (pas d'accès à Internet, pare-feu ?). Détail : " + str(ex)[:120]}


__all__ = [_n for _n in list(globals()) if not _n.startswith("__")]   # tout est transmis au module suivant (noms en _ compris)
