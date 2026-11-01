# SPDX-License-Identifier: GPL-2.0-or-later
"""mangmi-store - get games with one button, made for the gamepad.

  mangmi-store             the store (free homebrew, ScummVM freeware,
                           your own HTTP folders and links)
  mangmi-store --wifi      only the Wi-Fi screen
  mangmi-store --windowed  in a window (testing)

A = choose / download, B = back, Y = search, X = delete, L1/R1 = page.
Keyboard, mouse and touch work too. Games are saved to ~/ROMs/<system>/;
ES-DE is restarted on exit (console mode) so it lists them right away.
"""

import argparse
import math
import os
import queue
import signal
import subprocess
import sys
import threading
import time

from . import sdlui as S
from . import storelib as L

RU = False


def tr(en, ru):
    return ru if RU else en


def _detect_russian():
    lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    if not lang:
        try:
            with open("/etc/locale.conf", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("LANG="):
                        lang = line[5:].strip().strip('"')
        except OSError:
            pass
    return lang[:2] in ("ru", "uk", "be", "kk")


# Nord palette, like the RetroArch menu
BG = (36, 41, 51)
HEAD = (46, 52, 64)
PANEL = (59, 66, 82)
PANEL2 = (67, 76, 94)
SEL = (136, 192, 208)
SEL_TEXT = (36, 41, 51)
TEXT = (236, 239, 244)
DIM = (216, 222, 233, 150)
FAINT = (216, 222, 233, 90)
ACCENT = (129, 161, 193)
GREEN = (163, 190, 140)
RED = (191, 97, 106)
YELLOW = (235, 203, 139)
ORANGE = (208, 135, 112)
PURPLE = (180, 142, 173)

REPEAT_FIRST, REPEAT_NEXT = 0.38, 0.07


def font_file(bold):
    for p in (("/usr/share/fonts/noto/NotoSans-Bold.ttf",) if bold else ()) + (
            "/usr/share/fonts/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf"):
        if os.path.exists(p) and (bold or "Bold" not in p):
            return p, False
    try:
        p = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans:bold" if bold else "Noto Sans"],
                           capture_output=True, text=True, timeout=5).stdout.strip()
        if p and os.path.exists(p):
            return p, bold and "Bold" not in p
    except (OSError, subprocess.SubprocessError):
        pass
    raise S.SDLError("no font found (noto-fonts)")


def human(n):
    """1536 -> '1.5 KB' ('1,5 КБ')"""
    if not n:
        return ""
    units = (tr("B", "Б"), tr("KB", "КБ"), tr("MB", "МБ"), tr("GB", "ГБ"))
    v, i = float(n), 0
    while v >= 1024 and i < 3:
        v /= 1024
        i += 1
    if i == 0:
        return f"{int(v)} {units[0]}"
    txt = f"{v:.1f}".rstrip("0").rstrip(".") if v < 10 else f"{v:.0f}"
    return (txt.replace(".", ",") if RU else txt) + " " + units[i]


def plural(n, one, few, many):
    if not RU:
        return one if n == 1 else many
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def games(n):
    return f"{n} " + plural(n, tr("game", "игра"), tr("games", "игры"), tr("games", "игр"))


# ==========================================================================
# screens

class Screen:
    modal = False

    def __init__(self, app):
        self.app = app

    def title(self):
        return ""

    def hints(self):
        return []

    def on(self, action):
        return False

    def draw(self, x, y, w, h):
        pass

    def tap(self, x, y):
        pass

    def drag(self, dy):
        pass

    def scroll(self, rows):
        pass

    def text_input(self, s):
        pass

    def busy(self):
        return False

    def tick(self):
        pass

    def enter(self):
        pass


class ListScreen(Screen):
    row_units = 62

    def __init__(self, app):
        super().__init__(app)
        self.rows = []
        self.sel = 0
        self.top = 0
        self.vis = 8
        self.area = (0, 0, 0, 0, 1)
        self._drag = 0.0

    @property
    def current(self):
        return self.rows[self.sel] if 0 <= self.sel < len(self.rows) else None

    def select(self, i):
        if not self.rows:
            return
        i = max(0, min(len(self.rows) - 1, i))
        if i != self.sel:
            self.sel = i
            self.on_select()
        self.app.dirty = True

    def on_select(self):
        pass

    def move(self, d):
        if not self.rows:
            return
        n = len(self.rows)
        if abs(d) == 1:
            self.select((self.sel + d) % n)
        else:
            self.select(self.sel + d)

    def activate(self, row):
        pass

    def on(self, a):
        if a == "up":
            self.move(-1)
        elif a == "down":
            self.move(1)
        elif a in ("l1", "pgup"):
            self.move(-max(1, self.vis - 1))
        elif a in ("r1", "pgdn"):
            self.move(max(1, self.vis - 1))
        elif a == "home":
            self.select(0)
        elif a == "end":
            self.select(len(self.rows) - 1)
        elif a == "ok" and self.current is not None:
            self.activate(self.current)
        elif a == "back":
            self.app.pop()
        else:
            return False
        return True

    def draw_rows(self, x, y, w, h, paint):
        s = self.app.s
        x, y, w, h = int(x), int(y), int(w), int(h)
        rh = max(1, int(self.row_units * s))
        self.vis = vis = max(1, h // rh)
        n = len(self.rows)
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + vis:
            self.top = self.sel - vis + 1
        self.top = max(0, min(self.top, max(0, n - vis)))
        self.area = (x, y, w, h, rh)
        g = self.app.g
        bar = int(6 * s) if n > vis else 0
        for i in range(self.top, min(n, self.top + vis)):
            ry = y + (i - self.top) * rh
            sel = i == self.sel
            if sel:
                g.rrect(x, ry + 2 * s, w - bar - 6 * s * bool(bar), rh - 4 * s, 10 * s, SEL)
            paint(self.rows[i], sel, x, ry, w - bar - 6 * s * bool(bar), rh)
        if bar:
            g.rrect(x + w - bar, y, bar, vis * rh, bar / 2, PANEL)
            th = max(int(30 * s), int(vis * rh * vis / n))
            ty = y + int((vis * rh - th) * self.top / max(1, n - vis))
            g.rrect(x + w - bar, ty, bar, th, bar / 2, ACCENT)

    def row_at(self, px, py):
        x, y, w, h, rh = self.area
        if x <= px < x + w and y <= py < y + min(h, self.vis * rh):
            i = self.top + int((py - y) // rh)
            if i < len(self.rows):
                return i
        return None

    def tap(self, px, py):
        i = self.row_at(px, py)
        if i is None:
            return
        if i == self.sel:
            self.activate(self.rows[i])
        else:
            self.select(i)

    def drag(self, dy):
        rh = self.area[4]
        self._drag += dy
        steps = int(self._drag / rh)
        if steps:
            self._drag -= steps * rh
            self.scroll(-steps)

    def scroll(self, rows):
        n = len(self.rows)
        if not n:
            return
        self.top = max(0, min(max(0, n - self.vis), self.top + rows))
        if self.sel < self.top:
            self.select(self.top)
        elif self.sel >= self.top + self.vis:
            self.select(self.top + self.vis - 1)
        self.app.dirty = True


# --------------------------------------------------------------------------

class Home(ListScreen):
    row_units = 78

    def __init__(self, app):
        super().__init__(app)
        self.counts = {}
        self.build()

    def title(self):
        return tr("Game Store", "Магазин игр")

    def build(self):
        a = self.app
        rows = []
        for plat, color in (("GB", GREEN), ("GBC", YELLOW), ("GBA", PURPLE)):
            sys_id = L.HH3_PLATFORMS[plat]
            rows.append(dict(
                badge=plat, color=color,
                title=tr(f"{L.system_name(sys_id)}: free homebrew", f"{L.system_name(sys_id)}: бесплатные игры"),
                sub=tr("Homebrew Hub, new games by independent authors",
                       "Homebrew Hub — новые игры от независимых авторов"),
                open=lambda p=plat, n=L.system_name(sys_id): a.push(Catalog(
                    a, n, lambda refresh, p=p: L.load_hh3(p, refresh), key="hh3-" + p))))
        rows.append(dict(
            badge="SVM", color=ORANGE, title=tr("ScummVM: classic adventures", "ScummVM: классические квесты"),
            sub=tr("Freeware releases by the original developers", "Бесплатно от самих авторов игр"),
            open=lambda: a.push(Catalog(a, "ScummVM", lambda refresh: L.scummvm_items(RU), key="scummvm"))))
        for src in a.cfg.get("sources", []):
            rows.append(dict(
                badge="HTTP", color=ACCENT, title=src.get("name") or src["url"], sub=src["url"], source=src,
                open=lambda src=src: a.push(Folder(a, src["url"], src.get("name") or src["url"]))))
        rows.append(dict(badge="+", color=PANEL2, title=tr("Add your folder…", "Добавить свою папку…"),
                         sub=tr("A link to a folder on your PC or NAS (HTTP)",
                                "Ссылка на папку на ПК или NAS (HTTP)"),
                         open=self.add_source))
        rows.append(dict(badge="URL", color=PANEL2, title=tr("Download by link…", "Скачать по ссылке…"),
                         sub=tr("One file from the internet or your network",
                                "Один файл из интернета или домашней сети"),
                         open=self.add_link))
        rows.append(dict(badge="Wi-Fi", color=PANEL2, title="Wi-Fi",
                         sub=lambda: a.net or tr("Not connected", "Нет подключения"),
                         open=lambda: a.push(Wifi(a))))
        self.rows = rows
        self.sel = min(self.sel, len(rows) - 1)

    def hints(self):
        h = [("A", tr("Open", "Открыть"), "ok")]
        if self.current and self.current.get("source"):
            h.append(("X", tr("Remove", "Убрать"), "x"))
        h.append(("B", tr("Exit", "Выход"), "back"))
        return h

    def activate(self, row):
        row["open"]()

    def on(self, a):
        if a == "x" and self.current and self.current.get("source"):
            src = self.current["source"]

            def remove():
                self.app.cfg["sources"] = [s for s in self.app.cfg["sources"] if s is not src]
                self.app.save_cfg()
                self.build()
            self.app.ask(tr(f"Remove “{src.get('name')}” from the list? Downloaded games stay.",
                            f"Убрать «{src.get('name')}» из списка? Скачанные игры останутся."),
                         [(tr("Remove", "Убрать"), remove), (tr("Cancel", "Отмена"), None)])
            return True
        if a == "back":
            self.app.quit()
            return True
        return super().on(a)

    def add_source(self):
        a = self.app

        def done(text):
            url = L.normalize_url(text)
            if not url:
                a.toast(tr("That is not an http:// link", "Это не ссылка http://"))
                return
            if not url.endswith("/"):
                url += "/"
            a.cfg["last_url"] = url
            src = {"name": L.source_name(url), "url": url}
            if not any(s["url"] == url for s in a.cfg["sources"]):
                a.cfg["sources"].append(src)
                a.save_cfg()
            self.build()
            a.push(Folder(a, url, src["name"]))
        a.keyboard(tr("Folder link, e.g. 192.168.1.10:8000/roms/", "Ссылка на папку, например 192.168.1.10:8000/roms/"),
                   a.cfg.get("last_url", "http://"), done, url=True)

    def add_link(self):
        a = self.app

        def done(text):
            url = L.normalize_url(text)
            if not url:
                a.toast(tr("That is not an http:// link", "Это не ссылка http://"))
                return
            a.download(L.link_item(url))
        a.keyboard(tr("Link to the file", "Ссылка на файл"), "https://", done, url=True)

    def paint(self, row, sel, x, y, w, h):
        a, g, s = self.app, self.app.g, self.app.s
        fg = SEL_TEXT if sel else TEXT
        bw = int(h - 22 * s)
        bx, by = x + 14 * s, y + 11 * s
        g.rrect(bx, by, bw, bw, 12 * s, row["color"] if not sel else HEAD)
        f = a.font("small_b") if len(row["badge"]) <= 3 else a.font("tiny_b")
        g.text(f, row["badge"], bx + bw / 2, by + bw / 2, TEXT if row["color"] == PANEL2 or sel else HEAD,
               align="center", valign="middle")
        tx = bx + bw + 20 * s
        sub = row["sub"]() if callable(row["sub"]) else row["sub"]
        tw = w - (tx - x) - 20 * s
        if sub:
            g.text(a.font("big"), row["title"], tx, y + h * 0.30, fg, maxw=tw, valign="middle")
            g.text(a.font("small"), sub, tx, y + h * 0.68, (fg[0], fg[1], fg[2], 170), maxw=tw, valign="middle")
        else:
            g.text(a.font("big"), row["title"], tx, y + h / 2, fg, maxw=tw, valign="middle")

    def draw(self, x, y, w, h):
        s = self.app.s
        m = int(min(w * 0.14, 140 * s))
        self.draw_rows(x + m, y + 14 * s, w - 2 * m, h - 14 * s, self.paint)


# --------------------------------------------------------------------------

class Spinner:
    @staticmethod
    def draw(app, cx, cy, r):
        t = time.monotonic()
        for i in range(8):
            ang = i / 8 * 6.2832
            a = int(60 + 195 * (((t * 1.4 - i / 8) % 1.0)))
            app.g.disc(cx + r * math.cos(ang), cy + r * math.sin(ang), max(2, r * 0.18), (*TEXT, a))


class ItemList(ListScreen):
    """games / files with a status column and a details panel"""

    def __init__(self, app, name):
        super().__init__(app)
        self.name = name
        self.state = "loading"
        self.error = ""
        self.all = []
        self.query = ""

    def title(self):
        t = self.name
        if self.query:
            t += " · " + tr("search", "поиск") + f": {self.query}"
        return t

    def busy(self):
        return self.state == "loading"

    def set_items(self, items):
        cur = self.current
        self.all = items
        self.filter()
        if cur in self.rows:
            self.sel = self.rows.index(cur)
        self.state = "ready"
        self.on_select()
        self.app.dirty = True

    def failed(self, err):
        self.state, self.error = "error", err
        self.app.dirty = True

    def filter(self):
        q = self.query.casefold()
        self.rows = [it for it in self.all if not q or q in it.title.casefold() or q in it.developer.casefold()]
        self.sel = min(self.sel, max(0, len(self.rows) - 1))

    def on_select(self):
        it = self.current
        if it is not None and it.shot:
            self.app.shots.want(it.shot)

    def status(self, it):
        """(text, color, fraction or None)"""
        job = self.app.dl.job_for(it)
        if job and job.state == "active":
            return f"{int(job.fraction * 100)}%", YELLOW, job.fraction
        if job and job.state == "queued":
            return tr("queued", "в очереди"), DIM, None
        if it.kind != "dir" and it.installed():
            return "✓", GREEN, None
        if job and job.state == "error":
            return "!", RED, None
        return "", TEXT, None

    def activate(self, it):
        a = self.app
        job = a.dl.job_for(it)
        if job and job.state in ("queued", "active"):
            a.toast(tr("Already downloading — X cancels", "Уже скачивается — X отменит"))
        elif it.installed():
            a.toast(tr("Already downloaded. Find it in ES-DE: ", "Уже скачано. Ищите в ES-DE: ") +
                    L.system_name(it.system))
        else:
            a.download(it)

    def on(self, a):
        app = self.app
        it = self.current
        if self.state == "error" and a == "ok":
            self.reload()
            return True
        if a == "y" and self.state == "ready":
            def done(text):
                self.query = text.strip()
                self.filter()
                self.sel = 0
                self.top = 0
                self.on_select()
            app.keyboard(tr("Search", "Поиск"), self.query, done)
            return True
        if a == "x" and it is not None:
            job = app.dl.job_for(it)
            if job and job.state in ("queued", "active"):
                job.cancel.set()
                if job.state == "queued":
                    job.state = "cancelled"
                app.toast(tr("Download cancelled", "Загрузка отменена"))
            elif it.kind != "dir" and it.installed():
                path = it.dest()
                app.ask(tr(f"Delete “{it.title}” from the console?", f"Удалить «{it.title}» с консоли?"),
                        [(tr("Delete", "Удалить"), lambda: (L.remove_item(path), app.toast(tr("Deleted", "Удалено")))),
                         (tr("Cancel", "Отмена"), None)])
            return True
        if a == "back" and self.query:
            self.query = ""
            self.filter()
            self.on_select()
            app.dirty = True
            return True
        if a == "start":
            self.reload(refresh=True)
            return True
        return super().on(a)

    def hints(self):
        it = self.current
        h = []
        if self.state == "error":
            return [("A", tr("Retry", "Повторить"), "ok"), ("B", tr("Back", "Назад"), "back")]
        if it is not None:
            job = self.app.dl.job_for(it)
            if it.kind == "dir":
                h.append(("A", tr("Open", "Открыть"), "ok"))
            elif job and job.state in ("queued", "active"):
                h.append(("X", tr("Cancel", "Отменить"), "x"))
            elif it.installed():
                h.append(("X", tr("Delete", "Удалить"), "x"))
            else:
                h.append(("A", tr("Download", "Скачать"), "ok"))
        if self.state == "ready":
            h.append(("Y", tr("Search", "Поиск"), "y"))
        h.append(("B", tr("Back", "Назад"), "back"))
        return h

    def reload(self, refresh=False):
        pass

    def paint(self, it, sel, x, y, w, h):
        a, g, s = self.app, self.app.g, self.app.s
        fg = SEL_TEXT if sel else TEXT
        txt, col, frac = self.status(it)
        sw = int(96 * s)
        tx = x + 18 * s
        tw = w - sw - 30 * s
        if it.kind == "dir":
            g.rrect(tx, y + h * 0.28, 26 * s, h * 0.44, 5 * s, YELLOW if not sel else HEAD)
            tx += 38 * s
            tw -= 38 * s
        sub = it.developer or (L.system_name(it.system) if it.system else "")
        if it.kind == "dir":
            sub = tr("folder", "папка")
        elif it.kind == "file":
            sub = (L.system_name(it.system) if it.system else tr("system: ask", "система: спросить"))
            if it.size:
                sub += " · " + human(it.size)
        if sub:
            g.text(a.font("row"), it.title, tx, y + h * 0.33, fg, maxw=tw, valign="middle")
            g.text(a.font("tiny"), sub, tx, y + h * 0.72, (fg[0], fg[1], fg[2], 160), maxw=tw, valign="middle")
        else:
            g.text(a.font("row"), it.title, tx, y + h / 2, fg, maxw=tw, valign="middle")
        if frac is not None:
            bx, bw2 = x + w - sw - 8 * s, sw - 4 * s
            g.rrect(bx, y + h * 0.62, bw2, 8 * s, 4 * s, HEAD if sel else PANEL2)
            g.rrect(bx, y + h * 0.62, max(8 * s, bw2 * frac), 8 * s, 4 * s, YELLOW if not sel else HEAD)
            g.text(a.font("tiny_b"), txt, x + w - 12 * s, y + h * 0.36, fg, align="right", valign="middle")
        elif txt:
            c = fg if sel else col
            if txt == "✓":
                f, txt = a.icon_font("big", "✓")
            else:
                f = a.font("big_b") if txt == "!" else a.font("tiny")
            g.text(f, txt, x + w - 22 * s, y + h / 2, c, align="right", valign="middle")

    def draw_details(self, it, x, y, w, h):
        a, g, s = self.app, self.app.g, self.app.s
        g.rrect(x, y, w, h, 16 * s, PANEL)
        pad = 22 * s
        x, y, w, h = x + pad, y + pad, w - 2 * pad, h - 2 * pad
        bottom = y + h
        if it.kind == "rom" or it.shot:
            ih = int(h * 0.42)
            tex = a.shots.get(it.shot) if it.shot else None
            if tex:
                k = min(w / tex.w, ih / tex.h)
                sharp = k >= 2
                if sharp:
                    k = int(k)  # whole pixels for pixel art
                S.F.SDL_SetTextureScaleMode(tex.ptr, S.SCALEMODE_NEAREST if sharp else S.SCALEMODE_LINEAR)
                dw, dh = int(tex.w * k), int(tex.h * k)
                g.rrect(x, y, w, ih, 10 * s, BG)
                g.blit(tex, x + (w - dw) / 2, y + (ih - dh) / 2, size=(dw, dh))
            else:
                g.rrect(x, y, w, ih, 10 * s, BG)
                label = L.system_name(it.system)
                if it.shot and a.shots.loading(it.shot):
                    Spinner.draw(a, x + w / 2, y + ih / 2, 16 * s)
                else:
                    g.text(a.font("big_b"), label, x + w / 2, y + ih / 2, FAINT, align="center", valign="middle")
            y += ih + 16 * s
        g.text(a.font("title"), it.title, x, y, TEXT, maxw=w)
        y += a.font("title").height + 2 * s
        meta = []
        if it.developer:
            meta.append(it.developer)
        if it.info:
            meta.append(it.info)
        if it.kind == "dir":
            meta.append(tr("folder", "папка"))
        elif it.kind == "file":
            meta.append(L.system_name(it.system) if it.system else tr("system will be asked", "система — спросим"))
        if it.size:
            meta.append(human(it.size))
        if meta:
            g.text(a.font("small"), " · ".join(meta), x, y, DIM, maxw=w)
            y += a.font("small").height + 10 * s
        # status / action line at the bottom
        job = a.dl.job_for(it)
        bh = int(50 * s)
        by = bottom - bh
        if job and job.state == "active":
            g.rrect(x, by, w, bh, 12 * s, BG)
            g.rrect(x, by, max(24 * s, w * job.fraction), bh, 12 * s, (*YELLOW, 200))
            label = tr("Downloading", "Скачивание") + f" {int(job.fraction * 100)}%"
            if job.total:
                label += f" · {human(job.got)} / {human(job.total)}"
            g.text(a.font("small_b"), label, x + w / 2, by + bh / 2, TEXT, align="center", valign="middle")
        elif it.kind != "dir" and it.installed():
            f, mark = a.icon_font("big", "✓")
            mw = g.text(f, mark, x, by + bh / 2, GREEN, valign="middle")
            g.text(a.font("small_b"), tr("Downloaded: ", "Скачано: ") + L.system_name(it.system),
                   x + mw + 10 * s, by + bh / 2, GREEN, maxw=w - mw - 10 * s, valign="middle")
        elif job and job.state == "error":
            g.text(a.font("small_b"), tr("Error: ", "Ошибка: ") + job.error, x, by + bh / 2, RED, maxw=w, valign="middle")
        elif job and job.state == "queued":
            g.text(a.font("small_b"), tr("Waiting in the queue…", "Ждёт в очереди…"), x, by + bh / 2, DIM, valign="middle")
        elif it.kind != "dir":
            a.button_hint(x, by + bh / 2, "A", tr("Download", "Скачать"), big=True)
        if it.description and by - y > 30 * s:
            g.wrapped(a.font("small"), it.description, x, y, w, by - y - 12 * s, (*TEXT, 220))

    def draw(self, x, y, w, h):
        a, g, s = self.app, self.app.g, self.app.s
        m = int(24 * s)
        x, y, w, h = x + m, y + 12 * s, w - 2 * m, h - 24 * s
        if self.state == "loading" and not self.rows:
            Spinner.draw(a, x + w / 2, y + h / 2 - 20 * s, 26 * s)
            g.text(a.font("row"), tr("Loading…", "Загрузка…"), x + w / 2, y + h / 2 + 40 * s, DIM, align="center")
            return
        if self.state == "error":
            g.text(a.font("big_b"), tr("Could not load the list", "Не удалось загрузить список"),
                   x + w / 2, y + h * 0.36, TEXT, align="center")
            g.text(a.font("small"), self.error, x + w / 2, y + h * 0.36 + 50 * s, DIM, align="center", maxw=w)
            if not a.net:
                g.text(a.font("small"), tr("No network: connect in Wi-Fi (main screen)",
                                           "Нет сети: подключитесь в разделе Wi-Fi на главном экране"),
                       x + w / 2, y + h * 0.36 + 90 * s, YELLOW, align="center", maxw=w)
            return
        if not self.rows:
            g.text(a.font("row"), tr("Nothing here", "Здесь пусто") if not self.query else
                   tr("Nothing found", "Ничего не найдено"), x + w / 2, y + h * 0.4, DIM, align="center")
            return
        lw = int(w * 0.52)
        self.draw_rows(x, y, lw, h, self.paint)
        if self.current is not None:
            self.draw_details(self.current, x + lw + 20 * s, y, w - lw - 20 * s, h)


class Catalog(ItemList):
    def __init__(self, app, name, loader, key):
        super().__init__(app, name)
        self.loader = loader
        self.key = key
        self.reload()

    def reload(self, refresh=False):
        self.state = "loading"
        self.app.dirty = True

        def work():
            try:
                items = self.loader(refresh)
                self.app.post(lambda: self.set_items(items))
            except (L.NetError, OSError, ValueError) as e:
                err = str(e)
                self.app.post(lambda: self.failed(err))
        threading.Thread(target=work, daemon=True).start()

    def title(self):
        t = super().title()
        if self.state == "ready" and not self.query:
            t += " · " + games(len(self.all))
        return t


class Folder(ItemList):
    def __init__(self, app, url, name):
        super().__init__(app, name)
        self.url = url
        self.reload()

    def reload(self, refresh=False):
        self.state = "loading"
        self.app.dirty = True
        url = self.url

        def work():
            try:
                text, ctype = L.fetch_text(url)
                items = L.parse_index(text, url, ctype)
                self.app.post(lambda: self.set_items(items))
            except (L.NetError, OSError, ValueError) as e:
                err = str(e)
                self.app.post(lambda: self.failed(err))
        threading.Thread(target=work, daemon=True).start()

    def activate(self, it):
        if it.kind == "dir":
            self.app.push(Folder(self.app, it.url, it.title))
        else:
            super().activate(it)

    def on(self, a):
        if a == "y" and self.state == "ready":
            files = [it for it in self.rows if it.kind == "file" and not it.installed()]
            if not files:
                self.app.toast(tr("No new files in this folder", "В этой папке нет новых файлов"))
                return True
            size = sum(it.size for it in files)
            msg = tr(f"Download all {len(files)} files", f"Скачать все файлы: {len(files)}")
            if size:
                msg += f" ({human(size)})"
            self.app.ask(msg + "?", [(tr("Download", "Скачать"), lambda: self.app.download_many(files)),
                                     (tr("Cancel", "Отмена"), None)])
            return True
        return super().on(a)

    def hints(self):
        h = super().hints()
        for i, (b, label, act) in enumerate(h):
            if b == "Y":
                h[i] = ("Y", tr("Download all", "Скачать всё"), "y")
        return h


class SystemPicker(ListScreen):
    row_units = 56

    def __init__(self, app, what, done):
        super().__init__(app)
        self.what = what
        self.done = done
        self.rows = L.known_systems()

    def title(self):
        return tr(f"Which system is “{self.what}” for?", f"Для какой системы «{self.what}»?")

    def hints(self):
        return [("A", tr("Choose", "Выбрать"), "ok"), ("B", tr("Cancel", "Отмена"), "back")]

    def activate(self, sys_id):
        self.app.pop()
        self.done(sys_id)

    def paint(self, sys_id, sel, x, y, w, h):
        a, g, s = self.app, self.app.g, self.app.s
        fg = SEL_TEXT if sel else TEXT
        g.text(a.font("row"), L.system_name(sys_id), x + 20 * s, y + h / 2, fg, valign="middle", maxw=w * 0.6)
        g.text(a.font("small"), f"~/ROMs/{sys_id}", x + w - 20 * s, y + h / 2, (fg[0], fg[1], fg[2], 150),
               align="right", valign="middle")

    def draw(self, x, y, w, h):
        s = self.app.s
        m = int(min(w * 0.2, 220 * s))
        self.draw_rows(x + m, y + 12 * s, w - 2 * m, h - 24 * s, self.paint)


# --------------------------------------------------------------------------

class Wifi(ListScreen):
    row_units = 68

    def __init__(self, app):
        super().__init__(app)
        self.state = "scanning"
        self.radio = True
        self.error = ""
        self.connecting = ""
        self.scan(rescan=False)

    def title(self):
        return "Wi-Fi"

    def busy(self):
        return self.state == "scanning" or bool(self.connecting)

    def scan(self, rescan=True):
        self.state = "scanning"
        self.app.dirty = True

        def work():
            radio, nets, err = L.wifi_scan(rescan)
            self.app.post(lambda: self.scanned(radio, nets, err))
        threading.Thread(target=work, daemon=True).start()

    def scanned(self, radio, nets, err):
        cur = self.current["ssid"] if self.current else None
        self.radio = radio is not False
        self.error = err if radio is None or (not nets and err) else ""
        self.rows = nets
        self.sel = next((i for i, n in enumerate(nets) if n["ssid"] == cur), 0)
        self.state = "ready"
        self.app.refresh_net()
        self.app.dirty = True

    def hints(self):
        if not self.radio:
            return [("A", tr("Turn Wi-Fi on", "Включить Wi-Fi"), "ok"), ("B", tr("Back", "Назад"), "back")]
        h = []
        n = self.current
        if n and not n["active"]:
            h.append(("A", tr("Connect", "Подключить"), "ok"))
        h.append(("Y", tr("Refresh", "Обновить"), "y"))
        if n and n["saved"]:
            h.append(("X", tr("Forget", "Забыть"), "x"))
        h.append(("B", tr("Back", "Назад"), "back"))
        return h

    def on(self, a):
        if self.connecting:
            return a != "back" or super().on(a)
        if not self.radio and a == "ok":
            threading.Thread(target=lambda: (L.nmcli("radio", "wifi", "on"), time.sleep(3),
                                             self.app.post(lambda: self.scan())), daemon=True).start()
            self.state = "scanning"
            return True
        if a == "y":
            self.scan()
            return True
        if a == "x" and self.current and self.current["saved"]:
            ssid = self.current["ssid"]
            self.app.ask(tr(f"Forget the network “{ssid}”?", f"Забыть сеть «{ssid}»?"),
                         [(tr("Forget", "Забыть"), lambda: threading.Thread(
                             target=lambda: (L.nmcli("connection", "delete", "id", ssid),
                                             self.app.post(lambda: self.scan(False))), daemon=True).start()),
                          (tr("Cancel", "Отмена"), None)])
            return True
        return super().on(a)

    def activate(self, n):
        if n["active"]:
            self.app.toast(tr("Already connected", "Уже подключено"))
        elif n["security"] and not n["saved"]:
            self.ask_password(n)
        else:
            self.connect(n, None)

    def ask_password(self, n):
        self.app.keyboard(tr(f"Password for “{n['ssid']}”", f"Пароль сети «{n['ssid']}»"), "",
                          lambda pw: self.connect(n, pw), secret=True)

    def connect(self, n, password):
        self.connecting = n["ssid"]
        self.app.dirty = True

        def work():
            ok, msg = L.wifi_connect(n["ssid"], password, saved=n["saved"] and password is None)
            self.app.post(lambda: self.connected(n, password, ok, msg))
        threading.Thread(target=work, daemon=True).start()

    def connected(self, n, password, ok, msg):
        self.connecting = ""
        if ok:
            self.app.toast(tr(f"Connected to “{n['ssid']}”", f"Подключено к «{n['ssid']}»"))
            self.scan(False)
            return
        low = msg.lower()
        if n["security"] and ("secret" in low or "password" in low or "802-1x" in low or "psk" in low):
            self.app.toast(tr("Wrong password?", "Неверный пароль?"))
            self.ask_password(n)
        else:
            self.app.toast(tr("Could not connect: ", "Не удалось подключиться: ") + msg.splitlines()[-1][:120]
                           if msg else tr("Could not connect", "Не удалось подключиться"))
        self.app.dirty = True

    def paint(self, n, sel, x, y, w, h):
        a, g, s = self.app, self.app.g, self.app.s
        fg = SEL_TEXT if sel else TEXT
        # signal bars
        bx = x + 20 * s
        for i in range(4):
            bh = (8 + 7 * i) * s
            on = n["signal"] >= 15 + i * 22
            c = fg if on else (fg[0], fg[1], fg[2], 70)
            g.rrect(bx + i * 10 * s, y + h / 2 + 14 * s - bh, 7 * s, bh, 2 * s, c)
        tx = bx + 56 * s
        g.text(a.font("row"), n["ssid"], tx, y + h * 0.36, fg, maxw=w * 0.55, valign="middle")
        sub = []
        if n["active"]:
            sub.append(tr("connected", "подключено"))
        elif self.connecting == n["ssid"]:
            sub.append(tr("connecting…", "подключение…"))
        elif n["saved"]:
            sub.append(tr("saved", "сохранена"))
        sub.append(n["security"] or tr("open", "открытая"))
        col = GREEN if n["active"] and not sel else (fg[0], fg[1], fg[2], 160)
        g.text(a.font("tiny"), " · ".join(sub), tx, y + h * 0.72, col, maxw=w * 0.6, valign="middle")
        g.text(a.font("small"), f"{n['signal']}%", x + w - 20 * s, y + h / 2, (fg[0], fg[1], fg[2], 170),
               align="right", valign="middle")

    def draw(self, x, y, w, h):
        a, g, s = self.app, self.app.g, self.app.s
        m = int(min(w * 0.16, 180 * s))
        x, w = x + m, w - 2 * m
        if not self.radio:
            g.text(a.font("big_b"), tr("Wi-Fi is off", "Wi-Fi выключен"), x + w / 2, y + h * 0.4, TEXT, align="center")
            return
        if self.error and not self.rows:
            g.text(a.font("row"), self.error, x + w / 2, y + h * 0.4, DIM, align="center", maxw=w)
        if self.state == "scanning":
            Spinner.draw(a, x + w - 30 * s, y + 30 * s, 14 * s)
            if not self.rows:
                g.text(a.font("row"), tr("Looking for networks…", "Поиск сетей…"), x + w / 2, y + h * 0.4, DIM,
                       align="center")
        if self.connecting:
            Spinner.draw(a, x + w - 30 * s, y + 30 * s, 14 * s)
        self.draw_rows(x, y + 12 * s, w, h - 24 * s, self.paint)


# ==========================================================================
# modal: dialog and on-screen keyboard

class Dialog(Screen):
    modal = True

    def __init__(self, app, text, buttons):
        super().__init__(app)
        self.text = text
        self.buttons = buttons
        self.sel = 0
        self.hits = []

    def hints(self):
        return [("A", tr("Choose", "Выбрать"), "ok"), ("B", tr("Cancel", "Отмена"), "back")]

    def press(self, i):
        self.app.close_modal(self)
        cb = self.buttons[i][1]
        if cb:
            cb()

    def on(self, a):
        if a in ("left", "up"):
            self.sel = (self.sel - 1) % len(self.buttons)
        elif a in ("right", "down"):
            self.sel = (self.sel + 1) % len(self.buttons)
        elif a in ("ok", "start"):
            self.press(self.sel)
        elif a in ("back", "select"):
            self.app.close_modal(self)
            last = self.buttons[-1][1]
            if last and len(self.buttons) == 1:
                last()
        self.app.dirty = True
        return True

    def tap(self, px, py):
        for i, (x, y, w, h) in enumerate(self.hits):
            if x <= px < x + w and y <= py < y + h:
                self.press(i)
                return

    def draw(self, X, Y, W, H):
        a, g, s = self.app, self.app.g, self.app.s
        g.fill(0, 0, g.w, g.h, (0, 0, 0, 150))
        w = int(min(W * 0.8, 760 * s))
        f = a.font("row")
        t = g._text_tex(f, self.text, wrap=int(w - 60 * s))
        th = min(t.h if t else f.height, f.height * 6)
        h = int(th + 150 * s)
        x, y = (g.w - w) // 2, (g.h - h) // 2
        g.rrect(x, y, w, h, 18 * s, PANEL)
        g.wrapped(f, self.text, x + 30 * s, y + 28 * s, w - 60 * s, th, TEXT)
        bw = int((w - 60 * s - 20 * s * (len(self.buttons) - 1)) / len(self.buttons))
        bh = int(56 * s)
        by = y + h - bh - 24 * s
        self.hits = []
        for i, (label, _) in enumerate(self.buttons):
            bx = x + 30 * s + i * (bw + 20 * s)
            sel = i == self.sel
            g.rrect(bx, by, bw, bh, 12 * s, SEL if sel else PANEL2)
            g.text(a.font("row_b"), label, bx + bw / 2, by + bh / 2, SEL_TEXT if sel else TEXT,
                   align="center", valign="middle", maxw=bw - 10 * s)
            self.hits.append((bx, by, bw, bh))


_LAYOUTS = {
    "en": ["1234567890", "qwertyuiop", "asdfghjkl'", "zxcvbnm-_@"],
    "ru": ["1234567890", "йцукенгшщзхъ", "фывапролджэё", "ячсмитьбю-_"],
    "sym": ["1234567890", "!@#$%^&*()", "-_=+[]{};:", "'\",.<>/?\\|~`"],
}


class Keyboard(Screen):
    modal = True

    def __init__(self, app, prompt, text, done, secret=False, url=False):
        super().__init__(app)
        self.prompt = prompt
        self.text = text
        self.done = done
        self.secret = secret
        self.show = not secret
        self.letters = "ru" if RU and not url and not secret else "en"
        self.layout = self.letters
        self.shift = False
        self.url = url
        self.r, self.c = 1, 0
        self.keys = []  # rows of (label, value, units)
        self.hits = []
        self.blink = 0
        self.build()
        S.F.SDL_StartTextInput()

    def build(self):
        rows = []
        for line in _LAYOUTS[self.layout]:
            rows.append([(ch.upper() if self.shift else ch, ch.upper() if self.shift else ch, 1) for ch in line])
        special = [("⇧", "shift", 1.5)]
        if self.layout == "sym":
            special.append(("АБВ" if self.letters == "ru" else "ABC", "sym", 1.4))
        else:
            special.append(("#+=", "sym", 1.4))
            if RU:
                other = "en" if self.layout == "ru" else "ru"
                special.append((other.upper(), "lang:" + other, 1.2))
        if self.url:
            special += [(".", ".", 1), ("/", "/", 1), (":", ":", 1)]
        special += [(tr("Space", "Пробел"), " ", 2.6), ("⌫", "bksp", 1.4)]
        if self.secret:
            special.append((tr("Show", "Показать") if not self.show else tr("Hide", "Скрыть"), "show", 1.8))
        special.append((tr("Done", "Готово"), "done", 2))
        rows.append(special)
        self.keys = rows
        self.r = min(self.r, len(rows) - 1)
        self.c = min(self.c, len(rows[self.r]) - 1)

    def hints(self):
        return [("A", tr("Type", "Ввод"), "ok"), ("B", tr("Erase", "Стереть"), "back"),
                ("Y", tr("Space", "Пробел"), "y"), ("L1", tr("Layout", "Язык"), "l1"),
                ("R1", "Shift", "r1"), ("Start", tr("Done", "Готово"), "start"),
                ("Select", tr("Cancel", "Отмена"), "select")]

    def finish(self, ok):
        S.F.SDL_StopTextInput()
        self.app.close_modal(self)
        if ok:
            self.done(self.text)

    def press(self, value):
        if value == "shift":
            self.shift = not self.shift
        elif value == "sym":
            self.layout = "sym" if self.layout != "sym" else self.letters
        elif value.startswith("lang:"):
            self.layout = self.letters = value[5:]
        elif value == "bksp":
            self.text = self.text[:-1]
        elif value == "show":
            self.show = not self.show
        elif value == "done":
            self.finish(True)
            return
        else:
            self.text += value
            if not self.shift:
                return self._dirty()
            self.shift = False
        self.build()
        self._dirty()

    def _dirty(self):
        self.app.dirty = True

    def _centers(self, r):
        row = self.keys[r]
        tot = sum(u for _, _, u in row)
        out, acc = [], 0.0
        for _, _, u in row:
            out.append((acc + u / 2) / tot)
            acc += u
        return out

    def on(self, a):
        if a in ("left", "right"):
            n = len(self.keys[self.r])
            self.c = (self.c + (1 if a == "right" else -1)) % n
        elif a in ("up", "down"):
            cx = self._centers(self.r)[self.c]
            self.r = (self.r + (1 if a == "down" else -1)) % len(self.keys)
            cs = self._centers(self.r)
            self.c = min(range(len(cs)), key=lambda i: abs(cs[i] - cx))
        elif a == "ok":
            self.press(self.keys[self.r][self.c][1])
        elif a in ("back", "x", "bksp"):
            if a == "back" and not self.text:
                self.finish(False)
            self.text = self.text[:-1]
        elif a == "y":
            self.text += " "
        elif a == "l1":
            order = ["ru", "en", "sym"] if RU else ["en", "sym"]
            self.layout = order[(order.index(self.layout) + 1) % len(order)]
            if self.layout != "sym":
                self.letters = self.layout
            self.build()
        elif a == "r1":
            self.press("shift")
        elif a in ("start", "enter"):
            self.finish(True)
        elif a in ("select", "escape"):
            self.finish(False)
        self.app.dirty = True
        return True

    def text_input(self, s):
        self.text += s
        self.app.dirty = True

    def tap(self, px, py):
        for (x, y, w, h), r, c in self.hits:
            if x <= px < x + w and y <= py < y + h:
                self.r, self.c = r, c
                self.press(self.keys[r][c][1])
                return

    def draw(self, X, Y, W, H):
        a, g, s = self.app, self.app.g, self.app.s
        g.fill(0, 0, g.w, g.h, (0, 0, 0, 170))
        kh = int(min(64 * s, (g.h - a.foot_h) * 0.11))
        gap = int(8 * s)
        rows = len(self.keys)
        kw_total = int(min(g.w - 40 * s, 1100 * s))
        top_h = int(150 * s)
        h = top_h + rows * (kh + gap) + 20 * s
        x = (g.w - kw_total) // 2
        y = g.h - a.foot_h - h - 10 * s
        g.rrect(x - 20 * s, y, kw_total + 40 * s, h, 20 * s, PANEL)
        g.text(a.font("small"), self.prompt, x, y + 18 * s, DIM, maxw=kw_total)
        fy = y + 58 * s
        g.rrect(x, fy, kw_total, 62 * s, 12 * s, BG)
        shown = self.text if self.show else "•" * len(self.text)
        f = a.font("big")
        tw = f.width(shown)
        avail = kw_total - 40 * s
        if tw > avail:  # keep the end (the cursor) visible
            while shown and f.width("…" + shown) > avail:
                shown = shown[1:]
            shown = "…" + shown
        w = g.text(f, shown, x + 20 * s, fy + 31 * s, TEXT, valign="middle")
        if self.blink == 0:
            g.fill(x + 22 * s + w, fy + 14 * s, 3 * s, 34 * s, SEL)
        self.hits = []
        ky = y + top_h
        for r, row in enumerate(self.keys):
            tot = sum(u for _, _, u in row)
            unit = (kw_total - gap * (len(row) - 1)) / tot
            kx = x
            for c, (label, value, u) in enumerate(row):
                kw = unit * u
                sel = (r, c) == (self.r, self.c)
                special = len(value) > 1
                col = SEL if sel else (PANEL2 if not special else HEAD)
                if value == "done" and not sel:
                    col = (94, 129, 172)
                if value == "shift" and self.shift and not sel:
                    col = ACCENT
                g.rrect(kx, ky, kw, kh, 10 * s, col)
                fnt = a.font("row") if not special else a.font("small_b")
                if label in ("⇧", "⌫"):
                    fnt, label = a.icon_font("big", label)
                g.text(fnt, label, kx + kw / 2, ky + kh / 2, SEL_TEXT if sel else TEXT,
                       align="center", valign="middle", maxw=kw - 6 * s)
                self.hits.append(((kx, ky, kw, kh), r, c))
                kx += kw + gap
            ky += kh + gap

    def tick(self):
        b = int(time.monotonic() * 2) % 2
        if b != self.blink:
            self.blink = b
            self.app.dirty = True


# ==========================================================================
# screenshots

class Shots:
    """screenshots fetched and decoded in the background, latest request first"""

    def __init__(self, app):
        self.app = app
        self.tex = {}
        self.order = []
        self.failed = set()
        self.wanted = None
        self.busy_url = None
        self.cv = threading.Condition()
        threading.Thread(target=self._run, daemon=True).start()

    def want(self, url):
        if url in self.tex or url in self.failed:
            return
        with self.cv:
            self.wanted = url
            self.cv.notify()

    def get(self, url):
        return self.tex.get(url)

    def loading(self, url):
        return url not in self.tex and url not in self.failed

    def _run(self):
        while True:
            with self.cv:
                while self.wanted is None:
                    self.cv.wait()
                url, self.wanted = self.wanted, None
            img = None
            try:
                img = L.decode_image(L.fetch_shot(url))
            except (L.NetError, OSError):
                img = None
            self.app.post(lambda url=url, img=img: self._ready(url, img))

    def _ready(self, url, img):
        if img is None:
            self.failed.add(url)
        else:
            w, h, data = img
            try:
                self.tex[url] = self.app.g.texture_rgba(data, w, h)
                self.order.append(url)
            except S.SDLError:
                self.failed.add(url)
            while len(self.order) > 48:
                self.tex.pop(self.order.pop(0)).destroy()
        self.app.dirty = True


# ==========================================================================

class App:
    def __init__(self, windowed=False, software=False, wifi_only=False):
        self.g = S.Gfx("Mangmi Store", fullscreen=not windowed, software=software)
        self.fonts = {}
        self.s = 1.0
        self.head_h = self.foot_h = 0
        self.layout()
        self.wake_type = S.F.SDL_RegisterEvents(1)
        self.posted = queue.Queue()
        self.cfg = L.load_config()
        self.net = ""
        self.dirty = True
        self.running = True
        self.stack = []
        self.modals = []
        self.toast_text, self.toast_until = "", 0.0
        self.held = {}
        self.axes = {}
        self.pointer = None
        self.hint_hits = []
        self.controllers = []
        self.shots = Shots(self)
        self.dl = L.Downloader(lambda job: self.post(lambda: None))
        self.wifi_only = wifi_only
        self.stack.append(Wifi(self) if wifi_only else Home(self))
        self.refresh_net()
        S.F.SDL_StopTextInput()  # only while the on-screen keyboard is open

    # ---- plumbing -------------------------------------------------------
    def post(self, fn):
        """run fn on the UI thread (thread safe)"""
        self.posted.put(fn)
        ev = S.new_event_buffer()
        ev[0:4] = (self.wake_type & 0xFFFFFFFF).to_bytes(4, "little")
        S.F.SDL_PushEvent(ev)

    def layout(self):
        g = self.g
        s = max(0.5, min(g.w / 1280, g.h / 720))
        if abs(s - self.s) > 0.01 or not self.fonts:
            self.s = s
            for f in self.fonts.values():
                f.close()
            g.flush_text()
            reg, _ = font_file(False)
            bold, fake = font_file(True)
            sizes = dict(title=32, big=27, row=24, small=19, tiny=16)
            self.fonts = {}
            sym = next((p for p in ("/usr/share/fonts/noto/NotoSansSymbols2-Regular.ttf",
                                    "/usr/share/fonts/TTF/DejaVuSans.ttf") if os.path.exists(p)), None)
            for k, v in sizes.items():
                self.fonts[k] = S.Font(reg, v * s)
                self.fonts[k + "_b"] = S.Font(bold, v * s, bold=fake)
                if sym:
                    self.fonts[k + "_sym"] = S.Font(sym, v * s)
        self.head_h = int(72 * self.s)
        self.foot_h = int(60 * self.s)

    def font(self, name):
        return self.fonts[name]

    _ICON_TEXT = {"✓": "OK", "⌫": "Del", "⇧": "Shift", "✕": "x"}

    def icon_font(self, size, icon):
        """(font, text) for a symbol, with a plain-text fallback"""
        f = self.fonts.get(size + "_sym")
        return (f, icon) if f else (self.fonts[size + "_b"], self._ICON_TEXT.get(icon, icon))

    def refresh_net(self):
        def work():
            st = L.wifi_status()
            if not st:
                ok, out = L.nmcli("-t", "-f", "TYPE,STATE,CONNECTION", "device", timeout=10)
                for line in out.splitlines() if ok else ():
                    f = L.nm_split(line)
                    if len(f) >= 3 and f[0] == "ethernet" and f[1] == "connected":
                        st = f[2]
            self.post(lambda: self._net(st))
        threading.Thread(target=work, daemon=True).start()

    def _net(self, st):
        if st != self.net:
            self.net = st
            self.dirty = True

    def save_cfg(self):
        try:
            L.save_config(self.cfg)
        except OSError as e:
            self.toast(str(e))

    # ---- navigation -----------------------------------------------------
    @property
    def top(self):
        return self.modals[-1] if self.modals else self.stack[-1]

    def push(self, screen):
        self.stack.append(screen)
        screen.enter()
        self.dirty = True

    def pop(self):
        if len(self.stack) > 1:
            self.stack.pop()
            self.stack[-1].enter()
            if isinstance(self.stack[-1], Home):
                self.stack[-1].build()
        else:
            self.quit()
        self.dirty = True

    def close_modal(self, m):
        if m in self.modals:
            self.modals.remove(m)
        self.dirty = True

    def ask(self, text, buttons):
        self.modals.append(Dialog(self, text, buttons))
        self.dirty = True

    def keyboard(self, prompt, text, done, secret=False, url=False):
        self.modals.append(Keyboard(self, prompt, text, done, secret=secret, url=url))
        self.dirty = True

    def toast(self, text, secs=3.0):
        self.toast_text, self.toast_until = text, time.monotonic() + secs
        self.dirty = True

    def quit(self):
        if self.dl.pending():
            def stop():
                self.dl.cancel_all()
                self.running = False
            self.ask(tr("Downloads are not finished. Stop them and exit?",
                        "Загрузки ещё не закончены. Прервать и выйти?"),
                     [(tr("Exit", "Выйти"), stop), (tr("Stay", "Остаться"), None)])
        else:
            self.running = False

    def download(self, item, system=None):
        sys_id = system or item.system
        if not sys_id:
            def chosen(s):
                item.system = s
                self.download(item, s)
            self.push(SystemPicker(self, item.title, chosen))
            return
        item.system = sys_id
        if item.installed():
            self.toast(tr("Already downloaded", "Уже скачано"))
            return
        self.dl.add(item, sys_id)
        self.toast(tr(f"Downloading “{item.title}”", f"Скачиваю «{item.title}»"))

    def download_many(self, items):
        ask = [it for it in items if not it.system]

        def go(sys_id=None):
            for it in items:
                if not it.system and sys_id:
                    it.system = sys_id
                if it.system and not it.installed():
                    self.dl.add(it, it.system)
            self.toast(tr(f"Added to downloads: {len(items)}", f"Добавлено в загрузки: {len(items)}"))
        if ask:
            self.push(SystemPicker(self, tr(f"{len(ask)} files", f"файлов: {len(ask)}"), go))
        else:
            go()

    # ---- input ----------------------------------------------------------
    def action(self, a):
        self.top.on(a)
        self.dirty = True

    def press(self, a, repeat=True):
        self.action(a)
        if repeat and a in ("up", "down", "left", "right", "l1", "r1"):
            self.held[a] = time.monotonic() + REPEAT_FIRST

    def release(self, a):
        self.held.pop(a, None)

    _BUTTONS = {S.CB_A: "ok", S.CB_B: "back", S.CB_X: "x", S.CB_Y: "y", S.CB_START: "start",
                S.CB_BACK: "select", S.CB_LEFTSHOULDER: "l1", S.CB_RIGHTSHOULDER: "r1",
                S.CB_DPAD_UP: "up", S.CB_DPAD_DOWN: "down", S.CB_DPAD_LEFT: "left", S.CB_DPAD_RIGHT: "right"}
    _KEYS = {S.K_UP: "up", S.K_DOWN: "down", S.K_LEFT: "left", S.K_RIGHT: "right", S.K_RETURN: "ok",
             S.K_KP_ENTER: "ok", S.K_ESCAPE: "back", S.K_AC_BACK: "back", S.K_PAGEUP: "l1",
             S.K_PAGEDOWN: "r1", S.K_HOME: "home", S.K_END: "end", S.K_DELETE: "x", S.K_F5: "start",
             S.K_TAB: "y"}

    def handle(self, e):
        t = e.type
        if t == S.QUIT:
            self.dl.cancel_all()
            self.running = False
        elif t == self.wake_type:
            pass
        elif t == S.WINDOWEVENT:
            if self.g.update_size():
                self.layout()
            self.dirty = True
        elif t == S.CONTROLLERDEVICEADDED:
            c = S.F.SDL_GameControllerOpen(e.which)
            if c:
                self.controllers.append(c)
        elif t == S.CONTROLLERBUTTONDOWN:
            a = self._BUTTONS.get(e.button)
            if a:
                self.press(a)
        elif t == S.CONTROLLERBUTTONUP:
            a = self._BUTTONS.get(e.button)
            if a:
                self.release(a)
        elif t == S.CONTROLLERAXISMOTION and e.axis in (S.AXIS_LEFTX, S.AXIS_LEFTY):
            neg, pos = ("left", "right") if e.axis == S.AXIS_LEFTX else ("up", "down")
            want = neg if e.value < -20000 else pos if e.value > 20000 else None
            prev = self.axes.get(e.axis)
            if want != prev and (want or abs(e.value) < 12000):
                if prev:
                    self.release(prev)
                self.axes[e.axis] = want
                if want:
                    self.press(want)
        elif t == S.KEYDOWN:
            kb = isinstance(self.top, Keyboard)
            if kb and e.key == S.K_BACKSPACE:
                self.action("bksp")
            elif kb and e.key in (S.K_RETURN, S.K_KP_ENTER):
                self.action("enter")
            elif kb and e.key == S.K_ESCAPE:
                self.action("escape")
            elif kb and e.key in (S.K_SPACE, S.K_TAB, S.K_DELETE):
                pass  # typed text arrives as TEXTINPUT
            elif e.key == S.K_BACKSPACE:
                self.action("back")
            elif e.key in self._KEYS:
                a = self._KEYS[e.key]
                if e.repeat and a not in ("up", "down", "left", "right", "l1", "r1"):
                    return
                self.action(a)
            elif not kb and (e.key == ord("/") or (e.key == ord("f") and e.mod & S.KMOD_CTRL)):
                self.action("y")
        elif t == S.TEXTINPUT:
            if isinstance(self.top, Keyboard):
                self.top.text_input(e.text)
        elif t in (S.MOUSEBUTTONDOWN, S.FINGERDOWN):
            if t == S.MOUSEBUTTONDOWN and e.which == 0xFFFFFFFF:
                return  # touch, handled as finger
            if t == S.MOUSEBUTTONDOWN and e.button == 3:
                self.action("back")
                return
            x, y = self._pos(e)
            self.pointer = [x, y, y, False]
        elif t in (S.MOUSEMOTION, S.FINGERMOTION) and self.pointer:
            if t == S.MOUSEMOTION and (e.which == 0xFFFFFFFF or not e.button & 1):
                return
            x, y = self._pos(e)
            p = self.pointer
            if not p[3] and abs(y - p[1]) > 14 * self.s:
                p[3] = True
            if p[3]:
                self.top.drag(y - p[2])
                p[2] = y
                self.dirty = True
        elif t in (S.MOUSEBUTTONUP, S.FINGERUP):
            if t == S.MOUSEBUTTONUP and (e.which == 0xFFFFFFFF or e.button != 1):
                return
            p, self.pointer = self.pointer, None
            if p and not p[3]:
                self.click(*self._pos(e))
        elif t == S.MOUSEWHEEL and e.y:
            self.top.scroll(-e.y * 3)

    def _pos(self, e):
        if e.type in (S.FINGERDOWN, S.FINGERUP, S.FINGERMOTION):
            return e.x * self.g.w, e.y * self.g.h
        # mouse coordinates are in window points; the renderer may be in pixels
        g = self.g
        return e.x * g.w / max(1, g.win_w or g.w), e.y * g.h / max(1, g.win_h or g.h)

    def click(self, x, y):
        for (hx, hy, hw, hh), a in self.hint_hits:
            if hx <= x < hx + hw and hy <= y < hy + hh:
                self.action(a)
                return
        if not self.modals and y < self.head_h and x < self.head_h * 1.4 and len(self.stack) > 1:
            self.pop()  # the back arrow
            return
        self.top.tap(x, y)
        self.dirty = True

    def repeat_tick(self):
        now = time.monotonic()
        for a, t in list(self.held.items()):
            if now >= t:
                self.action(a)
                self.held[a] = now + REPEAT_NEXT

    # ---- drawing --------------------------------------------------------
    def button_hint(self, x, y, button, label, big=False):
        """draw a gamepad button + label at (x, middle y); returns its width"""
        g, s = self.g, self.s
        f = self.font("small_b" if big else "tiny_b")
        d = int((40 if big else 32) * s)
        if len(button) == 1:
            g.disc(x + d / 2, y, d / 2, TEXT)
            g.text(f, button, x + d / 2, y, HEAD, align="center", valign="middle")
            bw = d
        else:
            bw = int(f.width(button) + 18 * s)
            g.rrect(x, y - d / 2, bw, d, d / 2, TEXT)
            g.text(f, button, x + bw / 2, y, HEAD, align="center", valign="middle")
        lw = g.text(self.font("small" if big else "tiny"), label, x + bw + 9 * s, y, TEXT, valign="middle")
        return bw + 9 * s + lw

    def render(self):
        g, s = self.g, self.s
        g.clear(BG)
        base = self.stack[-1]
        # header
        g.fill(0, 0, g.w, self.head_h, HEAD)
        x = 28 * s
        if len(self.stack) > 1:
            g.text(self.font("title_b"), "‹", x, self.head_h / 2, DIM, valign="middle")
            x += 34 * s
        right = g.w - 28 * s
        pend = self.dl.pending()
        if pend:
            active = next((j for j in pend if j.state == "active"), None)
            pct = f" {int(active.fraction * 100)}%" if active else ""
            label = tr("Downloads", "Загрузки") + f": {len(pend)}{pct}"
            w = self.font("small_b").width(label)
            g.rrect(right - w - 24 * s, self.head_h / 2 - 18 * s, w + 24 * s, 36 * s, 18 * s, YELLOW)
            g.text(self.font("small_b"), label, right - 12 * s, self.head_h / 2, HEAD, align="right", valign="middle")
            right -= w + 40 * s
        net = self.net or tr("offline", "нет сети")
        nw = g.text(self.font("small"), net, right, self.head_h / 2, GREEN if self.net else RED,
                    align="right", valign="middle", maxw=g.w * 0.25)
        right -= nw + 24 * s
        g.text(self.font("title_b"), base.title(), x, self.head_h / 2, TEXT, valign="middle", maxw=right - x)
        # body
        body_y = self.head_h
        body_h = g.h - self.head_h - self.foot_h
        base.draw(0, body_y, g.w, body_h)
        for m in self.modals:
            m.draw(0, body_y, g.w, body_h)
        # footer
        fy = g.h - self.foot_h
        g.fill(0, fy, g.w, self.foot_h, HEAD)
        self.hint_hits = []
        x = 28 * s
        for b, label, act in self.top.hints():
            w = self.button_hint(x, fy + self.foot_h / 2, b, label)
            self.hint_hits.append(((x - 6 * s, fy, w + 12 * s, self.foot_h), act))
            x += w + 30 * s
        # toast
        if self.toast_text and time.monotonic() < self.toast_until:
            f = self.font("row")
            tw = min(f.width(self.toast_text), g.w * 0.8)
            th = f.height + 24 * s
            tx, ty = (g.w - tw) / 2 - 24 * s, fy - th - 20 * s
            if isinstance(self.top, Keyboard):
                ty = self.head_h + 16 * s  # above the on-screen keyboard
            g.rrect(tx, ty, tw + 48 * s, th, th / 2, (20, 24, 30, 235))
            g.text(f, self.toast_text, g.w / 2, ty + th / 2, TEXT, align="center", valign="middle", maxw=g.w * 0.8)
        g.present()

    def busy(self):
        """something on screen is animated"""
        return any(sc.busy() for sc in [self.stack[-1], *self.modals]) or (
            isinstance(self.stack[-1], ItemList) and self.stack[-1].current is not None
            and self.stack[-1].current.shot and self.shots.loading(self.stack[-1].current.shot))

    def step(self, timeout_ms):
        ev = S.new_event_buffer()
        if S.F.SDL_WaitEventTimeout(ev, timeout_ms):
            self.handle(S.Event(ev))
            while S.F.SDL_PollEvent(ev):
                self.handle(S.Event(ev))
        while True:
            try:
                fn = self.posted.get_nowait()
            except queue.Empty:
                break
            fn()
            self.dirty = True
        self.repeat_tick()
        self.top.tick()
        if self.toast_text and time.monotonic() >= self.toast_until:
            self.toast_text = ""
            self.dirty = True
        if self.dirty or self.busy():
            self.dirty = False
            self.render()

    def run(self):
        last_net = time.monotonic()
        while self.running:
            self.step(16 if self.held else (33 if self.busy() else 250))
            if time.monotonic() - last_net > 15:
                last_net = time.monotonic()
                self.refresh_net()
        self.dl.cancel_all()
        self.g.close()
        return self.dl.done_count


def _frontend_pid():
    """pid of the ES-DE that started us (console mode), or None"""
    pid = os.getppid()
    for _ in range(8):
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8", errors="replace") as f:
                stat = f.read()
        except OSError:
            return None
        comm = stat[stat.index("(") + 1:stat.rindex(")")]
        if comm in ("es-de", "AppRun"):
            return pid
        pid = int(stat[stat.rindex(")") + 2:].split()[1])
        if pid <= 1:
            return None
    return None


def main(argv=None):
    global RU
    p = argparse.ArgumentParser(prog="mangmi-store", description="Download games for Mangmi Clean Linux")
    p.add_argument("--wifi", action="store_true", help="show only the Wi-Fi screen")
    p.add_argument("--windowed", action="store_true", help="run in a window")
    p.add_argument("--software", action="store_true", help="software rendering")
    args = p.parse_args(argv)
    RU = _detect_russian()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    try:
        app = App(windowed=args.windowed, software=args.software, wifi_only=args.wifi)
    except S.SDLError as e:
        print(f"mangmi-store: {e}", file=sys.stderr)
        return 1
    frontend = _frontend_pid()
    done = app.run()
    if done and frontend:
        # ES-DE only scans the ROM folders at start: let console-frontend restart it
        try:
            os.kill(frontend, signal.SIGTERM)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())