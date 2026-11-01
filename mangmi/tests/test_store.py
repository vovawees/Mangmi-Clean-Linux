# SPDX-License-Identifier: GPL-2.0-or-later
"""mangmi-store logic (no SDL needed) and, when SDL is available, a UI smoke test."""
import json
import os
import sys
import tempfile
import threading
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mangmi import storelib as L  # noqa: E402

HH3 = {
    "results": 4,
    "entries": [
        {"slug": "dorotea", "title": "Dorotea", "developer": "Pasqui Industry", "date": "2023-05-01",
         "license": "CC-BY-NC-ND-4.0", "basepath": "database-gb",
         "description": "A [puzzle](https://example.org) game.<br>Second line",
         "files": [{"default": False, "filename": "dorotea_it.gb", "playable": True},
                   {"default": True, "filename": "dorotea_en.gb", "playable": True}],
         "screenshots": ["shot 1.png"]},
        {"slug": "src-only", "title": "Source only", "basepath": "database-gb",
         "files": [{"filename": "source.zip", "default": True}], "screenshots": []},
        {"slug": "no-files", "title": "No files", "basepath": "database-gb", "files": []},
        {"slug": "dup", "title": "Dorotea", "developer": [{"name": "A"}, {"name": "B"}, "C"],
         "basepath": "database-gb", "files": [{"filename": "x.cgb", "playable": True}], "screenshots": []},
        {"slug": "advance", "title": "Advance thing", "basepath": "database-gba",
         "files": [{"filename": "a.gba"}], "screenshots": []},
    ],
}

APACHE_PRE = """<pre><img src="/icons/blank.gif"> <a href="?C=N;O=D">Name</a> <a href="?C=M;O=A">Last modified</a>
<hr><img src="/icons/back.gif"> <a href="/frs/extras/">Parent Directory</a>                    -
<img src="/icons/compressed.gif"> <a href="BASS-Floppy-1.3.zip">BASS-Floppy-1.3.zip</a>  2008-02-19 11:56  7.3M
<img src="/icons/unknown.gif"> <a href="BASS-Floppy-1.3.zip.sha256">BASS-Floppy-1.3.zip.sha256</a> 2018-11-19 12:58   64
<img src="/icons/folder.gif"> <a href="Sub%20Dir/">Sub Dir/</a>  2018-11-19 12:58    -
</pre>"""

NGINX = """<html><head><title>Index of /roms/PlayStation/</title></head><body><h1>Index of /roms/PlayStation/</h1>
<hr><pre><a href="../">../</a>
<a href="Game%20One%20(Europe).chd">Game One (Europe).chd</a>                    20-Oct-2026 17:05    524288000
<a href="Game%20Two.m3u">Game Two.m3u</a>                                      20-Oct-2026 17:05          64
<a href="covers/">covers/</a>                                                   20-Oct-2026 17:05       -
<a href="https://elsewhere.example/x.chd">x.chd</a>
<a href="/other/y.chd">y.chd</a>
</pre><hr></body></html>"""

PYTHON_SERVER = """<ul>
<li><a href="Super%20Game%20%28USA%29.sfc">Super Game (USA).sfc</a></li>
<li><a href="pack.zip">pack.zip</a></li>
<li><a href="notes.txt">notes.txt</a></li>
<li><a href=".hidden">.hidden</a></li>
</ul>"""


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = {k: os.environ.get(k) for k in ("HOME", "MANGMI_ROMS", "XDG_CACHE_HOME", "XDG_CONFIG_HOME")}
        os.environ["HOME"] = self.tmp.name
        os.environ["MANGMI_ROMS"] = os.path.join(self.tmp.name, "ROMs")
        os.environ.pop("XDG_CACHE_HOME", None)
        os.environ.pop("XDG_CONFIG_HOME", None)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()


class Catalogs(Env):
    def test_hh3(self):
        items = L.parse_hh3(HH3, "GB")
        self.assertEqual([it.title for it in items], ["Advance thing", "Dorotea", "Dorotea"])
        adv, first, dup = items
        self.assertEqual(adv.system, "gba")  # a GBA ROM listed under GB
        self.assertEqual(first.urls, [L.HH3 + "/static/database-gb/entries/dorotea/dorotea_en.gb"])
        self.assertEqual(first.shot, L.HH3 + "/static/database-gb/entries/dorotea/shot%201.png")
        self.assertEqual(first.filename, "Dorotea.gb")
        self.assertEqual(first.developer, "Pasqui Industry")
        self.assertEqual(first.info, "2023 · CC-BY-NC-ND-4.0")
        self.assertEqual(first.description, "A puzzle game.\nSecond line")
        self.assertEqual(dup.filename, "Dorotea (dup).gbc")  # .cgb saved as .gbc, name kept unique
        self.assertEqual(dup.system, "gb")
        self.assertEqual(dup.developer, "A, B, C")
        self.assertEqual(first.dest(), os.path.join(os.environ["MANGMI_ROMS"], "gb", "Dorotea.gb"))

    def test_scummvm(self):
        items = L.scummvm_items(russian=True)
        self.assertTrue(all(it.kind == "scummvm" and it.game_id and it.urls for it in items))
        self.assertTrue(all(u.startswith("https://downloads.scummvm.org/frs/extras/") for it in items for u in it.urls))
        self.assertTrue(all(it.filename.endswith(".scummvm") for it in items))
        self.assertIn("Драскул", next(it for it in items if it.game_id == "drascula").description)


class Listings(Env):
    def test_apache(self):
        url = "https://downloads.scummvm.org/frs/extras/Beneath%20a%20Steel%20Sky/"
        items = L.parse_index(APACHE_PRE, url)
        self.assertEqual([(it.kind, it.title) for it in items], [("dir", "Sub Dir"), ("file", "BASS-Floppy-1.3.zip")])
        self.assertEqual(items[0].url, url + "Sub%20Dir/")
        self.assertEqual(items[1].size, int(7.3 * 1024 * 1024))
        self.assertEqual(items[1].system, "")  # a zip: the system must be asked

    def test_nginx_folder_hint(self):
        items = L.parse_index(NGINX, "http://nas.local/roms/PlayStation/")
        files = [it for it in items if it.kind == "file"]
        self.assertEqual([it.title for it in files], ["Game One (Europe).chd", "Game Two.m3u"])
        self.assertTrue(all(it.system == "psx" for it in files))
        self.assertEqual(files[0].size, 524288000)
        self.assertEqual([it.title for it in items if it.kind == "dir"], ["covers"])

    def test_python_http_server(self):
        items = L.parse_index(PYTHON_SERVER, "http://192.168.1.10:8000/")
        self.assertEqual([(it.title, it.system) for it in items], [("pack.zip", ""), ("Super Game (USA).sfc", "snes")])
        self.assertEqual(items[1].urls, ["http://192.168.1.10:8000/Super%20Game%20%28USA%29.sfc"])

    def test_json(self):
        data = json.dumps([{"name": "a.gba", "type": "file", "size": 5}, {"name": "dir", "type": "directory"}])
        items = L.parse_index(data, "http://h/x/", "application/json")
        self.assertEqual([(it.kind, it.title, it.size) for it in items], [("dir", "dir", 0), ("file", "a.gba", 5)])
        caddy = json.dumps([{"name": "Mega Drive/", "is_dir": True, "url": "./Mega%20Drive/"}])
        self.assertEqual(L.parse_index(caddy, "http://h/", "application/json")[0].url, "http://h/Mega%20Drive/")

    def test_detect(self):
        self.assertEqual(L.detect_system([], "x.gba"), "gba")
        self.assertEqual(L.detect_system(["", "roms", "Sega Genesis"], "x.bin"), "megadrive")
        self.assertEqual(L.detect_system(["Sony - PlayStation 2"], "x.iso"), "ps2")
        self.assertEqual(L.detect_system(["Sony - PlayStation"], "x.cue"), "psx")
        self.assertEqual(L.detect_system(["games"], "x.iso"), None)
        self.assertEqual(L.detect_system(["SNES"], "x.zip"), "snes")

    def test_names_and_links(self):
        self.assertEqual(L.safe_name(" ../a/b: c?*<> "), "a-b - c")
        self.assertEqual(L.normalize_url("192.168.1.5:8000/roms dir/"), "http://192.168.1.5:8000/roms%20dir/")
        self.assertEqual(L.normalize_url("ftp://x/"), "")
        it = L.link_item("https://example.org/files/Game%20Boy/Cool%20Game.gb")
        self.assertEqual((it.title, it.system, it.filename), ("Cool Game.gb", "gb", "Cool Game.gb"))
        self.assertEqual(L.source_name("http://nas:8000/roms/GBA/"), "nas:8000 · GBA")

    def test_config(self):
        cfg = L.load_config()
        self.assertEqual(cfg, {"sources": []})
        cfg["sources"].append({"name": "n", "url": "http://x/"})
        L.save_config(cfg)
        self.assertEqual(L.load_config()["sources"][0]["url"], "http://x/")


class Downloads(Env):
    def _zip(self, name, files):
        path = os.path.join(self.tmp.name, name)
        with zipfile.ZipFile(path, "w") as z:
            for n, data in files.items():
                z.writestr(n, data)
        return "file://" + path

    def test_rom(self):
        src = os.path.join(self.tmp.name, "src.gb")
        with open(src, "wb") as f:
            f.write(b"\0" * 100000)
        it = L.Item(title="T", urls=["file://" + src], filename="T.gb", system="gb")
        seen = []
        path = L.install_item(it, progress=lambda i, n, g, t: seen.append((i, n, g, t)))
        self.assertEqual(os.path.getsize(path), 100000)
        self.assertTrue(it.installed())
        self.assertEqual(seen[-1], (0, 1, 100000, 100000))
        self.assertFalse(os.path.exists(path + ".part"))
        L.remove_item(path)
        self.assertFalse(it.installed())

    def test_cancel(self):
        src = os.path.join(self.tmp.name, "big.bin")
        with open(src, "wb") as f:
            f.write(b"\0" * 300000)
        ev = threading.Event()
        ev.set()
        it = L.Item(title="T", urls=["file://" + src], filename="T.nes", system="nes")
        with self.assertRaises(L.Cancelled):
            L.install_item(it, cancel=ev)
        self.assertEqual(os.listdir(os.path.join(os.environ["MANGMI_ROMS"], "nes")), [])

    def test_scummvm(self):
        a = self._zip("game.zip", {"game-1.0/": b"", "game-1.0/sky.dsk": b"d", "game-1.0/readme.txt": b"r"})
        b = self._zip("audio.zip", {"audio/track1.ogg": b"o", "readme.txt": b"r2", "../evil": b"x"})
        it = L.Item(title="Sky: Test", kind="scummvm", system="scummvm", urls=[a, b],
                    filename=L.safe_name("Sky: Test") + ".scummvm", game_id="sky")
        path = L.install_item(it)
        self.assertEqual(os.path.basename(path), "Sky - Test.scummvm")
        self.assertEqual(sorted(os.listdir(path)), ["Sky - Test.scummvm", "audio", "readme.txt", "sky.dsk"])
        with open(os.path.join(path, "Sky - Test.scummvm")) as f:
            self.assertEqual(f.read().strip(), "sky")
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(path), "evil")))
        self.assertTrue(it.installed())

    def test_downloader(self):
        src = os.path.join(self.tmp.name, "g.gba")
        with open(src, "wb") as f:
            f.write(b"x" * 1000)
        done = threading.Event()
        d = L.Downloader(lambda job: job.state in ("done", "error") and done.set())
        it = L.Item(title="G", urls=["file://" + src], filename="G.gba", system="gba")
        job = d.add(it)
        self.assertIs(d.add(it), job)  # no duplicates while queued
        self.assertTrue(done.wait(10))
        self.assertEqual(job.state, "done")
        self.assertEqual(d.done_count, 1)
        bad = L.Item(title="B", urls=["file:///nonexistent/b.gba"], filename="B.gba", system="gba")
        done.clear()
        job = d.add(bad)
        self.assertTrue(done.wait(10))
        self.assertEqual(job.state, "error")


class Wifi(unittest.TestCase):
    def test_split(self):
        self.assertEqual(L.nm_split(r"*:Cafe\: Free:45:"), ["*", "Cafe: Free", "45", ""])
        self.assertEqual(L.nm_split(r"a\\b:c"), ["a\\b", "c"])

    def test_parse(self):
        text = "\n".join([" :Weak:10:WPA2", "*:Home:82:WPA2", r" :Cafe\: Free:45:", " :Dup:30:WPA2",
                          " :Dup:60:WPA2", " ::50:WPA2"])
        nets = L.parse_wifi(text, saved={"Dup"})
        self.assertEqual([n["ssid"] for n in nets], ["Home", "Dup", "Cafe: Free", "Weak"])
        self.assertTrue(nets[0]["active"])
        self.assertEqual(nets[1]["signal"], 60)
        self.assertTrue(nets[1]["saved"])
        self.assertEqual(nets[2]["security"], "")
        self.assertEqual(L.parse_saved("Home:802-11-wireless\nWired:802-3-ethernet\n"), {"Home"})


def _sdl_available():
    try:
        from mangmi import sdlui
        sdlui.load()
        return True
    except Exception:  # noqa: BLE001 - any loader problem means "skip"
        return False


@unittest.skipUnless(os.environ.get("MANGMI_UI_TESTS") and _sdl_available(), "SDL UI test (MANGMI_UI_TESTS=1)")
class UiSmoke(Env):
    def test_screens(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")
        from mangmi import store
        app = store.App(windowed=True, software=True)
        try:
            app.step(1)
            app.action("down")
            app.keyboard("t", "", lambda t: setattr(self, "typed", t))
            for a in ("ok", "right", "ok", "start"):
                app.action(a)
            self.assertEqual(self.typed, "qw")
            app.push(store.Catalog(app, "S", lambda refresh: L.scummvm_items(), key="s"))
            for _ in range(50):
                app.step(20)
                if app.stack[-1].state == "ready":
                    break
            self.assertEqual(app.stack[-1].state, "ready")
            app.render()
            w, h, data = app.g.screenshot()
            self.assertEqual(len(data), w * h * 4)
        finally:
            app.g.close()


if __name__ == "__main__":
    unittest.main()
