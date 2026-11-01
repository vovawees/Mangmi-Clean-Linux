# SPDX-License-Identifier: GPL-2.0-or-later
"""mangmi-store without the UI: catalogs, folder listings, downloads, Wi-Fi.

Sources
  * Homebrew Hub (https://hh3.gbdev.io): free homebrew for Game Boy, Game Boy
    Color and Game Boy Advance, published by their authors
  * a few freeware adventure games released for ScummVM by their rights holders
  * the user's own HTTP(S) folders (a NAS, a PC running
    "python -m http.server", ...) and direct links
Nothing that needs a licence the user may not have is preconfigured.
"""

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field

UA = "MangmiStore/1.0 (+https://github.com/vovawees/Mangmi-Clean-Linux)"
HH3 = os.environ.get("MANGMI_STORE_HH3", "https://hh3.gbdev.io").rstrip("/")
HH3_PLATFORMS = {"GB": "gb", "GBC": "gbc", "GBA": "gba"}
CATALOG_TTL = 24 * 3600


def home():
    return os.path.expanduser("~")


def roms_dir():
    return os.environ.get("MANGMI_ROMS") or os.path.join(home(), "ROMs")


def cache_dir(*sub):
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(home(), ".cache")
    return os.path.join(base, "mangmi", "store", *sub)


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home(), ".config")
    return os.path.join(base, "mangmi", "store.json")


# --------------------------------------------------------------------------
# systems

SYSTEM_NAMES = {
    "3do": "3DO", "amiga": "Amiga", "amstradcpc": "Amstrad CPC", "arcade": "Arcade",
    "atari2600": "Atari 2600", "atari5200": "Atari 5200", "atari7800": "Atari 7800",
    "atari800": "Atari 800", "atarijaguar": "Atari Jaguar", "atarilynx": "Atari Lynx",
    "c64": "Commodore 64", "colecovision": "ColecoVision", "dos": "DOS", "dreamcast": "Dreamcast",
    "fbneo": "FinalBurn Neo", "gamegear": "Game Gear", "gb": "Game Boy", "gba": "Game Boy Advance",
    "gbc": "Game Boy Color", "gc": "GameCube", "genesis": "Genesis", "intellivision": "Intellivision",
    "mame": "MAME", "mastersystem": "Master System", "megacd": "Mega-CD", "megadrive": "Mega Drive",
    "msx": "MSX", "msx2": "MSX2", "n64": "Nintendo 64", "naomi": "NAOMI", "nds": "Nintendo DS",
    "neogeo": "Neo Geo", "neogeocd": "Neo Geo CD", "nes": "NES / Famicom", "ngp": "Neo Geo Pocket",
    "ngpc": "Neo Geo Pocket Color", "odyssey2": "Odyssey 2", "pcengine": "PC Engine",
    "pcenginecd": "PC Engine CD", "pokemini": "Pokémon Mini", "ports": "Ports",
    "ps2": "PlayStation 2", "psp": "PSP", "psx": "PlayStation", "saturn": "Saturn",
    "scummvm": "ScummVM", "sega32x": "32X", "segacd": "Sega CD", "sg-1000": "SG-1000",
    "snes": "SNES / Super Famicom", "tic80": "TIC-80", "vectrex": "Vectrex",
    "virtualboy": "Virtual Boy", "wii": "Wii", "wonderswan": "WonderSwan",
    "wonderswancolor": "WonderSwan Color", "zxspectrum": "ZX Spectrum",
}

# extensions that name exactly one system
EXT_SYSTEM = {
    "gb": "gb", "dmg": "gb", "sgb": "gb", "gbc": "gbc", "cgb": "gbc", "gba": "gba", "agb": "gba",
    "nes": "nes", "fds": "nes", "unf": "nes", "unif": "nes",
    "sfc": "snes", "smc": "snes", "fig": "snes", "swc": "snes",
    "md": "megadrive", "gen": "megadrive", "smd": "megadrive", "32x": "sega32x",
    "sms": "mastersystem", "gg": "gamegear", "sg": "sg-1000",
    "pce": "pcengine", "n64": "n64", "z64": "n64", "v64": "n64", "nds": "nds",
    "a26": "atari2600", "a52": "atari5200", "a78": "atari7800", "lnx": "atarilynx",
    "j64": "atarijaguar", "jag": "atarijaguar", "ngp": "ngp", "ngc": "ngpc",
    "ws": "wonderswan", "wsc": "wonderswancolor", "vb": "virtualboy", "min": "pokemini",
    "col": "colecovision", "int": "intellivision", "vec": "vectrex", "tic": "tic80",
    "d64": "c64", "t64": "c64", "crt": "c64", "prg": "c64", "tzx": "zxspectrum",
    "z80": "zxspectrum", "sna": "zxspectrum", "adf": "amiga", "gdi": "dreamcast",
    "cdi": "dreamcast", "pbp": "psx", "cso": "psp", "rvz": "gc", "gcz": "gc", "wbfs": "wii",
    "scummvm": "scummvm",
}

# folder names that tell the system ("PlayStation", "GBA", "Sega Genesis", ...)
_ALIASES = {
    "psx": ["playstation", "playstation1", "ps1", "psone", "sonyplaystation"],
    "ps2": ["playstation2", "sonyplaystation2"],
    "psp": ["playstationportable", "sonypsp"],
    "gb": ["gameboy", "nintendogameboy"],
    "gbc": ["gameboycolor", "gameboycolour", "nintendogameboycolor"],
    "gba": ["gameboyadvance", "nintendogameboyadvance"],
    "nes": ["famicom", "nintendoentertainmentsystem", "nintendo", "fc"],
    "snes": ["supernintendo", "superfamicom", "sfc", "supernes"],
    "n64": ["nintendo64"],
    "nds": ["nintendods", "ds"],
    "megadrive": ["segamegadrive", "segagenesis", "md"],
    "genesis": [],
    "mastersystem": ["segamastersystem", "sms"],
    "gamegear": ["segagamegear", "gg"],
    "segacd": ["megacd", "segamegacd"],
    "saturn": ["segasaturn"],
    "dreamcast": ["segadreamcast", "dc"],
    "gc": ["gamecube", "nintendogamecube", "ngc"],
    "wii": ["nintendowii"],
    "pcengine": ["turbografx", "turbografx16", "tg16", "pce"],
    "pcenginecd": ["turbografxcd", "pcecd"],
    "neogeo": ["snk", "neogeoaes", "neogeomvs"],
    "atarilynx": ["lynx"],
    "c64": ["commodore64", "commodore"],
    "zxspectrum": ["spectrum", "zx", "zxspectrum48", "sinclair"],
    "amstradcpc": ["cpc", "amstrad"],
    "scummvm": [],
    "dos": ["msdos", "pc"],
}


def _norm(s):
    return re.sub(r"[^0-9a-zа-яё]", "", s.casefold())


ALIASES = {}
for _sys, _names in _ALIASES.items():
    for _n in _names:
        ALIASES[_n] = _sys
for _sys in SYSTEM_NAMES:
    ALIASES.setdefault(_norm(_sys), _sys)
    ALIASES.setdefault(_norm(SYSTEM_NAMES[_sys]), _sys)


def known_systems():
    """ES-DE system folders of this image (rom-systems.list), in list order"""
    out = []
    try:
        with open("/usr/share/mangmi/rom-systems.list", encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if line:
                    out.append(line)
    except OSError:
        pass
    return out or sorted(SYSTEM_NAMES)


def system_name(sys_id):
    return SYSTEM_NAMES.get(sys_id, sys_id)


def ext_of(name):
    base = name.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[-1].casefold() if "." in base else ""


def detect_system(path_parts, filename):
    """ES-DE system for a file, from its extension or the folders above it"""
    sys_id = EXT_SYSTEM.get(ext_of(filename))
    if sys_id:
        return sys_id
    for part in reversed([p for p in path_parts if p]):
        n = _norm(part)
        if n in ALIASES:
            return ALIASES[n]
        # "Sony - PlayStation (2000)" style names
        words = re.split(r"[\s_\-\(\)\[\]]+", part.casefold())
        for w in words:
            if w and _norm(w) in ALIASES and len(_norm(w)) > 2:
                return ALIASES[_norm(w)]
    return None


def safe_name(name, limit=120):
    """a file name ES-DE can show as the game title"""
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = name.replace("/", "-").replace("\\", "-").replace(":", " -").replace("|", "-")
    name = re.sub(r'[<>"?*]', "", name)  # also valid on exFAT / FAT32 cards
    name = re.sub(r"\s+", " ", name).strip().lstrip(".- ").rstrip(". ")
    if len(name) > limit:
        name = name[:limit].rstrip(". ")
    return name or "game"


# --------------------------------------------------------------------------
# items

@dataclass
class Item:
    title: str
    kind: str = "rom"            # rom | scummvm | dir | file
    system: str = ""             # ES-DE system ("" = ask)
    urls: list = field(default_factory=list)
    filename: str = ""           # name inside ~/ROMs/<system>/
    developer: str = ""
    description: str = ""
    shot: str = ""               # screenshot URL
    size: int = 0                # bytes, when known
    info: str = ""               # one extra line (licence, year, ...)
    game_id: str = ""            # ScummVM game id
    url: str = ""                # dir: listing URL

    def dest(self, system=None):
        sys_id = system or self.system
        if not sys_id or not self.filename:
            return ""
        return os.path.join(roms_dir(), sys_id, self.filename)

    def installed(self):
        d = self.dest()
        return bool(d) and os.path.exists(d)


def _plain(text):
    """description text without HTML tags and markdown links"""
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(\*\*|__|`)", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_ROM_EXT = {"gb", "gbc", "cgb", "dmg", "sgb", "gba", "agb"}
_RENAME_EXT = {"cgb": "gbc", "dmg": "gb", "agb": "gba"}


def _pick_file(files):
    roms = [f for f in files if isinstance(f, dict) and ext_of(f.get("filename", "")) in _ROM_EXT]
    for want in (lambda f: f.get("default"), lambda f: f.get("playable"), lambda f: True):
        for f in roms:
            if want(f):
                return f
    return None


def hh3_url(platform, page=1):
    return f"{HH3}/api/search?typetag=game&platform={platform}&results=1000&page={page}"


def parse_hh3(data, platform):
    """Homebrew Hub search result -> Items (games with a downloadable ROM)"""
    want = HH3_PLATFORMS[platform]
    items = []
    for e in data.get("entries") or []:
        if not isinstance(e, dict) or not e.get("slug"):
            continue
        f = _pick_file(e.get("files") or [])
        if not f:
            continue
        slug = e["slug"]
        base = f"{HH3}/static/{urllib.parse.quote(e.get('basepath') or 'database-gb')}/entries/{urllib.parse.quote(slug)}/"
        fname = f["filename"]
        ext = ext_of(fname)
        sys_id = want
        if (ext in ("gba", "agb")) != (want == "gba"):
            sys_id = EXT_SYSTEM[ext]
        devs = []
        dev = e.get("developer") or []
        for d in dev if isinstance(dev, list) else [dev]:
            name = d.get("name") if isinstance(d, dict) else d
            if isinstance(name, str) and name.strip() and name.strip() not in devs:
                devs.append(name.strip())
        shots = [s for s in e.get("screenshots") or [] if isinstance(s, str)]
        shot = ""
        for s in shots:
            if ext_of(s) in ("png", "jpg", "jpeg", "gif", "bmp", "webp"):
                shot = base + urllib.parse.quote(s)
                break
        info = []
        if e.get("date"):
            info.append(str(e["date"])[:4])
        lic = e.get("license") or e.get("gameLicense")
        if isinstance(lic, str) and lic:
            info.append(lic)
        title = re.sub(r"\s+", " ", str(e.get("title") or slug)).strip()
        items.append(Item(
            title=title, kind="rom", system=sys_id, urls=[base + urllib.parse.quote(fname)],
            filename=safe_name(title) + "." + _RENAME_EXT.get(ext, ext),
            developer=", ".join(devs[:3]), description=_plain(e.get("description", "")),
            shot=shot, info=" · ".join(info), game_id=slug))
    # two entries with the same title must not share one file (or one name in ES-DE)
    seen = {}
    for it in items:
        seen.setdefault((it.system, it.filename.rsplit(".", 1)[0].casefold()), []).append(it)
    for group in seen.values():
        if len(group) > 1:
            for it in group[1:]:
                stem, ext = it.filename.rsplit(".", 1)
                it.filename = f"{stem} ({it.game_id}).{ext}"
    items.sort(key=lambda it: it.title.casefold())
    return items


# Freeware games their rights holders released for ScummVM
# (https://www.scummvm.org/games/), English versions.
_SVM = "https://downloads.scummvm.org/frs/extras/"
SCUMMVM_GAMES = [
    dict(title="Beneath a Steel Sky", game_id="sky", year="1994", developer="Revolution Software",
         urls=[_SVM + "Beneath%20a%20Steel%20Sky/bass-cd-1.2.zip"], size=69,
         en="Cyberpunk adventure: Robert Foster is kidnapped to Union City, a grim city ruled by the computer LINC.",
         ru="Киберпанк-квест: Роберта Фостера похищают в Юнион-Сити, мрачный город под властью компьютера LINC."),
    dict(title="Flight of the Amazon Queen", game_id="queen", year="1995", developer="Interactive Binary Illusions",
         urls=[_SVM + "Flight%20of%20the%20Amazon%20Queen/FOTAQ_Talkie-1.1.zip"], size=34,
         en="Pilot Joe King crash-lands in the Amazon jungle and has to stop a mad scientist. Full speech.",
         ru="Пилот Джо Кинг терпит крушение в джунглях Амазонки и должен остановить безумного учёного. С озвучкой."),
    dict(title="Lure of the Temptress", game_id="lure", year="1992", developer="Revolution Software",
         urls=[_SVM + "Lure%20of%20the%20Temptress/lure-1.1.zip"], size=6,
         en="Revolution's first adventure: a peasant boy against the sorceress Selena and her Skorl.",
         ru="Первый квест Revolution: юноша-крестьянин против колдуньи Селины и её скорлов."),
    dict(title="Drascula: The Vampire Strikes Back", game_id="drascula", year="1996", developer="Alcachofa Soft",
         urls=[_SVM + "Drascula_%20The%20Vampire%20Strikes%20Back/drascula-1.0.zip",
               _SVM + "Drascula_%20The%20Vampire%20Strikes%20Back/drascula-audio-2.0.zip"], size=69,
         en="A comedy adventure from Spain: John Hacker has to save a girl from Count Drascula.",
         ru="Испанский комедийный квест: Джон Хакер спасает девушку от графа Драскулы."),
    dict(title="Dreamweb", game_id="dreamweb", year="1994", developer="Creative Reality",
         urls=[_SVM + "Dreamweb/dreamweb-cd-uk-1.1.zip"], size=226,
         en="A dark top-down cyberpunk adventure with full speech (CD version). Contains violence.",
         ru="Мрачный киберпанк-квест с видом сверху и озвучкой (CD-версия). Есть сцены насилия."),
    dict(title="Soltys", game_id="soltys", year="1995", developer="L.K. Avalon",
         urls=[_SVM + "Soltys/soltys-en-v1.0.zip"], size=4,
         en="A Polish fairy-tale comedy adventure, English translation.",
         ru="Польский сказочный комедийный квест (английская версия)."),
    dict(title="Sfinx", game_id="sfinx", year="1994", developer="L.K. Avalon",
         urls=[_SVM + "Sfinx/sfinx-en-v1.1.zip"], size=17,
         en="A humorous adventure in an ancient-Egypt flavoured fantasy world.",
         ru="Юмористический квест в сказочном мире в духе Древнего Египта."),
    dict(title="The Griffon Legend", game_id="griffon", year="2005", developer="Syn9",
         urls=[_SVM + "Griffon%20Legend/griffon-1.0.zip"], size=10,
         en="A small action RPG in the style of the 16-bit classics.",
         ru="Небольшая action-RPG в духе 16-битной классики."),
    dict(title="Nippon Safes Inc.", game_id="nippon", year="1992", developer="Dynabyte",
         urls=[_SVM + "Nippon%20Safes/nippon-1.0.zip"], size=2,
         en="A comedy adventure with three crooks in Tokyo (DOS version).",
         ru="Комедийный квест о трёх жуликах в Токио (DOS-версия)."),
]


def scummvm_items(russian=False):
    items = []
    for g in SCUMMVM_GAMES:
        items.append(Item(
            title=g["title"], kind="scummvm", system="scummvm", urls=list(g["urls"]),
            filename=safe_name(g["title"]) + ".scummvm", developer=g["developer"],
            description=g["ru" if russian else "en"], size=g["size"] * 1024 * 1024,
            info=g["year"], game_id=g["game_id"]))
    return items


# --------------------------------------------------------------------------
# the user's own folders

_SKIP_EXT = {"txt", "nfo", "html", "htm", "md", "jpg", "jpeg", "png", "gif", "sha1", "sha256",
             "md5", "sfv", "torrent", "xml", "dat", "json", "ini", "url", "db"}


def _human_size(s):
    m = re.match(r"^\s*([\d.,]+)\s*([KMGT]?)(?:i?B)?\s*$", s or "", re.I)
    if not m:
        return 0
    try:
        v = float(m.group(1).replace(",", "."))
    except ValueError:
        return 0
    unit = m.group(2).upper()
    return int(v * (1024 ** ("KMGT".index(unit) + 1) if unit else 1))


def parse_index(text, url, ctype="text/html"):
    """directory listing (Apache, nginx, lighttpd, Caddy, python http.server,
    nginx/Caddy JSON) -> Items for the direct children of url"""
    if not url.endswith("/"):
        url += "/"
    base = urllib.parse.urlsplit(url)
    entries = []  # (href, size)
    data = None
    if "json" in ctype or text.lstrip()[:1] in ("[", "{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
    if isinstance(data, dict):
        data = data.get("items") or data.get("files") or data.get("entries")
    if isinstance(data, list):
        for d in data:
            if not isinstance(d, dict) or not d.get("name"):
                continue
            name = str(d["name"])
            is_dir = d.get("type") == "directory" or d.get("is_dir") or name.endswith("/")
            href = d.get("url") or urllib.parse.quote(name.rstrip("/"))
            if is_dir and not href.endswith("/"):
                href += "/"
            size = d.get("size") if isinstance(d.get("size"), int) else 0
            entries.append((href, size))
    else:
        for m in re.finditer(r"<a\s[^>]*?href\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)[^>]*>(.*?)</a>(?=(.{0,160}))",
                             text, re.I | re.S):
            href = html.unescape(m.group(1).strip("\"'"))
            size = 0
            tail = re.sub(r"<[^>]+>", " ", m.group(3))
            sm = re.search(r"(?:\d{1,2}:\d{2}(?::\d{2})?|\d{4}-\d\d-\d\d)\s+([\d.,]+\s*[KMGT]?i?B?)(?:\s|$)", tail, re.I)
            if sm:
                size = _human_size(sm.group(1))
            entries.append((href, size))
    items, seen = [], set()
    for href, size in entries:
        if not href or href.startswith(("?", "#", "mailto:", "javascript:")):
            continue
        full = urllib.parse.urljoin(url, href)
        p = urllib.parse.urlsplit(full)
        if (p.scheme, p.netloc) != (base.scheme, base.netloc) or not p.path.startswith(base.path):
            continue
        rel = p.path[len(base.path):]
        is_dir = rel.endswith("/")
        rel = rel.strip("/")
        if not rel or "/" in rel:
            continue
        name = urllib.parse.unquote(rel)
        if name in (".", "..") or name.startswith(".") or (name, is_dir) in seen:
            continue
        seen.add((name, is_dir))
        full = urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))
        if is_dir:
            items.append(Item(title=name, kind="dir", url=full))
        elif ext_of(name) not in _SKIP_EXT:
            parts = [urllib.parse.unquote(x) for x in base.path.split("/")]
            items.append(Item(title=name, kind="file", urls=[full], filename=safe_name(name, 200),
                              system=detect_system(parts, name) or "", size=size))
    items.sort(key=lambda it: (it.kind != "dir", it.title.casefold()))
    return items


def link_item(url):
    """a direct download link -> Item"""
    p = urllib.parse.urlsplit(url)
    parts = [urllib.parse.unquote(x) for x in p.path.split("/")]
    name = parts[-1] if parts and parts[-1] else (p.netloc or "download")
    return Item(title=name, kind="file", urls=[url], filename=safe_name(name, 200),
                system=detect_system(parts[:-1], name) or "")


def normalize_url(text):
    text = text.strip()
    if not text:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
        text = "http://" + text
    p = urllib.parse.urlsplit(text)
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(urllib.parse.unquote(p.path), "/%:@!$&'()*+,;=~"),
                                    p.query, ""))


# --------------------------------------------------------------------------
# config

def load_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            cfg.setdefault("sources", [])
            return cfg
    except (OSError, ValueError):
        pass
    return {"sources": []}


def save_config(cfg):
    p = config_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def source_name(url):
    p = urllib.parse.urlsplit(url)
    tail = urllib.parse.unquote(p.path.rstrip("/").rsplit("/", 1)[-1])
    return f"{p.netloc} · {tail}" if tail else p.netloc


# --------------------------------------------------------------------------
# network

class NetError(Exception):
    pass


def _open(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise NetError(f"HTTP {e.code}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        reason = getattr(e, "reason", e)
        raise NetError(str(reason)) from e


def fetch(url, timeout=30, limit=32 << 20):
    """(body, content type)"""
    with _open(url, timeout) as r:
        try:
            body = r.read(limit)
        except OSError as e:
            raise NetError(str(e)) from e
        return body, r.headers.get("Content-Type", "")


def fetch_text(url, timeout=30):
    body, ctype = fetch(url, timeout)
    m = re.search(r"charset=([\w-]+)", ctype)
    try:
        text = body.decode(m.group(1) if m else "utf-8", errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    return text, ctype


def cached_json(url, name, ttl=CATALOG_TTL, refresh=False):
    """JSON from url, kept in the cache; a stale copy is used when offline"""
    path = cache_dir(name)
    fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl
    if fresh and not refresh:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    try:
        body, _ = fetch(url, timeout=40)
        data = json.loads(body)
    except (NetError, ValueError) as e:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        raise NetError(str(e)) from e
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "wb") as f:
        f.write(body)
    os.replace(path + ".tmp", path)
    return data


def load_hh3(platform, refresh=False):
    return parse_hh3(cached_json(hh3_url(platform), f"hh3-{platform}.json", refresh=refresh), platform)


def shot_path(url):
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    return cache_dir("shots", h + "." + (ext_of(url) or "img"))


def fetch_shot(url):
    path = shot_path(url)
    if not os.path.exists(path):
        body, _ = fetch(url, timeout=20, limit=4 << 20)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "wb") as f:
            f.write(body)
        os.replace(path + ".tmp", path)
    return path


def decode_image(path, maxw=640):
    """(w, h, RGBA bytes) via ffmpeg (PNG, JPEG, GIF, BMP, WebP); None if unavailable"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        out = subprocess.run(
            [ffmpeg, "-v", "error", "-nostdin", "-i", path, "-frames:v", "1",
             "-vf", f"scale='min({maxw},iw)':-1:flags=area", "-f", "image2pipe", "-c:v", "pam",
             "-pix_fmt", "rgba", "-"], capture_output=True, timeout=20, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    end = out.find(b"ENDHDR\n")
    if not out.startswith(b"P7") or end < 0:
        return None
    hdr = dict(line.split(b" ", 1) for line in out[3:end].split(b"\n") if b" " in line)
    try:
        w, h, depth = int(hdr[b"WIDTH"]), int(hdr[b"HEIGHT"]), int(hdr[b"DEPTH"])
    except (KeyError, ValueError):
        return None
    data = out[end + 7:end + 7 + w * h * 4]
    if depth != 4 or len(data) != w * h * 4:
        return None
    return w, h, data


# --------------------------------------------------------------------------
# downloads

class Cancelled(Exception):
    pass


def free_space(path):
    while path and not os.path.exists(path):
        path = os.path.dirname(path)
    try:
        return shutil.disk_usage(path or "/").free
    except OSError:
        return 1 << 62


def download(url, dest, progress=None, cancel=None, chunk=1 << 16):
    """url -> dest (through dest.part); progress(got, total)"""
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with _open(url, timeout=30) as r:
        total = int(r.headers.get("Content-Length") or 0)
        if total and free_space(dest) < total + (64 << 20):
            raise NetError("no space")
        got = 0
        try:
            with open(part, "wb") as f:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    try:
                        buf = r.read(chunk)
                    except OSError as e:
                        raise NetError(str(e)) from e
                    if not buf:
                        break
                    f.write(buf)
                    got += len(buf)
                    if progress:
                        progress(got, total)
            if total and got < total:
                raise NetError("connection closed")
            os.replace(part, dest)
        except BaseException:
            try:
                os.unlink(part)
            except OSError:
                pass
            raise
    return got


def extract_zip(path, dest):
    """unpack path into dest; a single top folder in the archive is dropped"""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n and not n.startswith("__MACOSX/")]
        tops = {n.split("/", 1)[0] for n in names}
        strip = ""
        if len(tops) == 1 and any("/" in n for n in names):
            strip = tops.pop() + "/"
        root = os.path.realpath(dest)
        for info in z.infolist():
            n = info.filename
            if n.startswith("__MACOSX/") or (strip and not n.startswith(strip)):
                continue
            rel = n[len(strip):]
            if not rel:
                continue
            target = os.path.realpath(os.path.join(root, rel))
            if target != root and not target.startswith(root + os.sep):
                continue  # unsafe path
            if n.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 16)


def install_item(item, system=None, progress=None, cancel=None):
    """download (and for ScummVM unpack) an item; returns the final path"""
    dest = item.dest(system)
    if not dest:
        raise ValueError("no destination")
    if item.kind != "scummvm":
        n = len(item.urls)
        for i, url in enumerate(item.urls):
            download(url, dest, (lambda g, t, i=i: progress(i, n, g, t)) if progress else None, cancel)
        return dest
    work = dest + ".part"
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    try:
        n = len(item.urls)
        for i, url in enumerate(item.urls):
            z = os.path.join(work, f".download-{i}.zip")
            download(url, z, (lambda g, t, i=i: progress(i, n, g, t)) if progress else None, cancel)
            try:
                extract_zip(z, work)
            except (zipfile.BadZipFile, OSError) as e:
                raise NetError(f"bad archive: {e}") from e
            os.unlink(z)
        # ES-DE shows the folder "<title>.scummvm" as one game and launches the
        # file of the same name inside; the ScummVM core reads the game id there
        with open(os.path.join(work, os.path.basename(dest)), "w", encoding="utf-8") as f:
            f.write(item.game_id + "\n")
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.replace(work, dest)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return dest


def remove_item(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.unlink(path)


class Job:
    def __init__(self, item, system):
        self.item, self.system = item, system
        self.state = "queued"  # queued | active | done | error | cancelled
        self.got = self.total = 0
        self.part = (0, 1)
        self.error = ""
        self.path = ""
        self.cancel = threading.Event()

    @property
    def fraction(self):
        i, n = self.part
        f = self.got / self.total if self.total else 0.0
        return min(1.0, (i + f) / max(1, n))


class Downloader:
    """one download at a time, in a background thread; notify() after changes"""

    def __init__(self, notify=lambda job: None):
        self.notify = notify
        self.jobs = []
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.done_count = 0
        self._last = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def add(self, item, system=None):
        with self.lock:
            for j in self.jobs:
                if j.item is item and j.state in ("queued", "active"):
                    return j
            j = Job(item, system or item.system)
            self.jobs.append(j)
            self.wake.notify()
        self.notify(j)
        return j

    def job_for(self, item):
        with self.lock:
            for j in reversed(self.jobs):
                if j.item is item:
                    return j
        return None

    def pending(self):
        with self.lock:
            return [j for j in self.jobs if j.state in ("queued", "active")]

    def cancel_all(self):
        with self.lock:
            for j in self.jobs:
                if j.state in ("queued", "active"):
                    j.cancel.set()
                    if j.state == "queued":
                        j.state = "cancelled"

    def _run(self):
        while True:
            with self.lock:
                job = next((j for j in self.jobs if j.state == "queued"), None)
                while job is None:
                    self.wake.wait()
                    job = next((j for j in self.jobs if j.state == "queued"), None)
                job.state = "active"
            self.notify(job)

            def progress(i, n, got, total, job=job):
                job.part, job.got, job.total = (i, n), got, total
                now = time.monotonic()
                if now - self._last > 0.1:
                    self._last = now
                    self.notify(job)

            try:
                job.path = install_item(job.item, job.system, progress, job.cancel)
                job.state = "done"
                self.done_count += 1
            except Cancelled:
                job.state = "cancelled"
            except (NetError, OSError, ValueError) as e:
                job.state, job.error = "error", str(e) or e.__class__.__name__
            self.notify(job)


# --------------------------------------------------------------------------
# Wi-Fi (NetworkManager)

def nm_split(line):
    """split one line of `nmcli -t` output (':' separated, '\\' escapes)"""
    out, cur, esc = [], [], False
    for ch in line:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def parse_wifi(text, saved=()):
    """`nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY dev wifi list` -> networks"""
    nets = {}
    for line in text.splitlines():
        f = nm_split(line)
        if len(f) < 4 or not f[1]:
            continue
        inuse, ssid, signal, sec = f[0], f[1], f[2], f[3]
        sig = int(signal) if signal.isdigit() else 0
        sec = "" if sec in ("", "--") else sec
        n = nets.get(ssid)
        active = inuse.strip() == "*"
        if n is None:
            nets[ssid] = n = {"ssid": ssid, "signal": sig, "security": sec, "active": active,
                              "saved": ssid in saved}
        else:
            n["signal"] = max(n["signal"], sig)
            n["active"] = n["active"] or active
    return sorted(nets.values(), key=lambda n: (not n["active"], not n["saved"], -n["signal"], n["ssid"].casefold()))


def parse_saved(text):
    """`nmcli -t -f NAME,TYPE connection show` -> names of Wi-Fi connections"""
    out = set()
    for line in text.splitlines():
        f = nm_split(line)
        if len(f) >= 2 and f[1] in ("802-11-wireless", "wifi"):
            out.add(f[0])
    return out


def nmcli(*args, timeout=40):
    """(ok, output)"""
    try:
        p = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "nmcli not found"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def wifi_scan(rescan=True):
    """(radio on, networks, error)"""
    ok, radio = nmcli("-t", "radio", "wifi", timeout=10)
    if not ok:
        return None, [], radio
    if radio.strip() != "enabled":
        return False, [], ""
    _, saved = nmcli("-t", "-f", "NAME,TYPE", "connection", "show", timeout=10)
    ok, out = nmcli("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list",
                    "--rescan", "yes" if rescan else "auto", timeout=30)
    if not ok:
        return True, [], out
    return True, parse_wifi(out, parse_saved(saved)), ""


def wifi_connect(ssid, password=None, saved=False):
    """(ok, message)"""
    if saved and password is None:
        ok, out = nmcli("--wait", "40", "connection", "up", "id", ssid, timeout=50)
        if ok:
            return ok, out
    args = ["--wait", "40", "device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    return nmcli(*args, timeout=50)


def wifi_status():
    """name of the active Wi-Fi connection or ''"""
    ok, out = nmcli("-t", "-f", "TYPE,STATE,CONNECTION", "device", timeout=10)
    if ok:
        for line in out.splitlines():
            f = nm_split(line)
            if len(f) >= 3 and f[0] == "wifi" and f[1] == "connected":
                return f[2]
    return ""


def online(timeout=5):
    ok, out = nmcli("-t", "networking", "connectivity", timeout=timeout)
    return (not ok) or out.strip() in ("full", "unknown")