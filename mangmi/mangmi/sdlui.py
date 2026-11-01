# SPDX-License-Identifier: GPL-2.0-or-later
"""A small ctypes binding for SDL2 + SDL2_ttf and a few drawing helpers.

Only what the full-screen tools (mangmi-store) need: one window with an
accelerated renderer, text, rounded boxes, RGBA images, keyboard / mouse /
touch / game controller events. Uses the system libSDL2 (sdl2-compat) and
libSDL2_ttf, so no extra Python packages are needed on the device.
"""

import collections
import ctypes as C
import os
import struct

INIT_VIDEO = 0x20
INIT_JOYSTICK = 0x200
INIT_GAMECONTROLLER = 0x2000
INIT_EVENTS = 0x4000

WINDOW_FULLSCREEN_DESKTOP = 0x1001
WINDOW_RESIZABLE = 0x20
WINDOW_ALLOW_HIGHDPI = 0x2000
WINDOWPOS_CENTERED = 0x2FFF0000
RENDERER_SOFTWARE = 1
RENDERER_ACCELERATED = 2
RENDERER_PRESENTVSYNC = 4
BLENDMODE_BLEND = 1
PIXELFORMAT_RGBA32 = 0x16762004  # ABGR8888 = bytes R,G,B,A on little endian
SCALEMODE_NEAREST = 0
SCALEMODE_LINEAR = 1

# event types
QUIT = 0x100
WINDOWEVENT = 0x200
KEYDOWN = 0x300
KEYUP = 0x301
TEXTINPUT = 0x303
MOUSEMOTION = 0x400
MOUSEBUTTONDOWN = 0x401
MOUSEBUTTONUP = 0x402
MOUSEWHEEL = 0x403
CONTROLLERAXISMOTION = 0x650
CONTROLLERBUTTONDOWN = 0x651
CONTROLLERBUTTONUP = 0x652
CONTROLLERDEVICEADDED = 0x653
CONTROLLERDEVICEREMOVED = 0x654
FINGERDOWN = 0x700
FINGERUP = 0x701
FINGERMOTION = 0x702

# SDL_GameControllerButton (positional, Xbox naming: A = south, B = east)
CB_A, CB_B, CB_X, CB_Y, CB_BACK, CB_GUIDE, CB_START = 0, 1, 2, 3, 4, 5, 6
CB_LEFTSTICK, CB_RIGHTSTICK, CB_LEFTSHOULDER, CB_RIGHTSHOULDER = 7, 8, 9, 10
CB_DPAD_UP, CB_DPAD_DOWN, CB_DPAD_LEFT, CB_DPAD_RIGHT = 11, 12, 13, 14
AXIS_LEFTX, AXIS_LEFTY, AXIS_TRIGGERLEFT, AXIS_TRIGGERRIGHT = 0, 1, 4, 5

# keycodes
K_BACKSPACE, K_TAB, K_RETURN, K_ESCAPE, K_SPACE, K_DELETE = 8, 9, 13, 27, 32, 127
K_F5 = 0x4000003E
K_HOME, K_PAGEUP, K_END, K_PAGEDOWN = 0x4000004A, 0x4000004B, 0x4000004D, 0x4000004E
K_RIGHT, K_LEFT, K_DOWN, K_UP = 0x4000004F, 0x40000050, 0x40000051, 0x40000052
K_KP_ENTER = 0x40000058
K_AC_BACK = 0x4000010E
KMOD_CTRL = 0x00C0


class Rect(C.Structure):
    _fields_ = [("x", C.c_int), ("y", C.c_int), ("w", C.c_int), ("h", C.c_int)]


class Color(C.Structure):
    _fields_ = [("r", C.c_uint8), ("g", C.c_uint8), ("b", C.c_uint8), ("a", C.c_uint8)]


class SDLError(RuntimeError):
    pass


def _load(names, mode=C.DEFAULT_MODE):
    where = os.environ.get("MANGMI_SDL_DIR")
    err = None
    for n in names:
        try:
            return C.CDLL(os.path.join(where, n) if where else n, mode=mode)
        except OSError as e:
            err = e
    raise SDLError(f"cannot load {names[0]}: {err}")


_sdl = _ttf = None


class _Functions:
    """the bound C functions, filled by load()"""


F = _Functions()


def _bind(lib, name, res, *args):
    fn = getattr(lib, name)
    fn.restype = res
    fn.argtypes = list(args)
    setattr(F, name, fn)


def load():
    """Load the libraries and declare the functions (idempotent)."""
    global _sdl, _ttf
    if _sdl:
        return
    _sdl = _load(["libSDL2-2.0.so.0", "libSDL2-2.0.so", "libSDL2.so"], C.RTLD_GLOBAL)
    _ttf = _load(["libSDL2_ttf-2.0.so.0", "libSDL2_ttf-2.0.so", "libSDL2_ttf.so"])
    vp, i, u32, cp = C.c_void_p, C.c_int, C.c_uint32, C.c_char_p
    pi = C.POINTER(C.c_int)
    pr = C.POINTER(Rect)
    s = _sdl
    _bind(s, "SDL_SetHint", C.c_int, cp, cp)
    _bind(s, "SDL_Init", i, u32)
    _bind(s, "SDL_Quit", None)
    _bind(s, "SDL_GetError", cp)
    _bind(s, "SDL_CreateWindow", vp, cp, i, i, i, i, u32)
    _bind(s, "SDL_DestroyWindow", None, vp)
    _bind(s, "SDL_GetWindowSize", None, vp, pi, pi)
    _bind(s, "SDL_CreateRenderer", vp, vp, i, u32)
    _bind(s, "SDL_DestroyRenderer", None, vp)
    _bind(s, "SDL_GetRendererOutputSize", i, vp, pi, pi)
    _bind(s, "SDL_SetRenderDrawColor", i, vp, C.c_uint8, C.c_uint8, C.c_uint8, C.c_uint8)
    _bind(s, "SDL_SetRenderDrawBlendMode", i, vp, i)
    _bind(s, "SDL_RenderClear", i, vp)
    _bind(s, "SDL_RenderFillRect", i, vp, pr)
    _bind(s, "SDL_RenderCopy", i, vp, vp, pr, pr)
    _bind(s, "SDL_RenderPresent", None, vp)
    _bind(s, "SDL_RenderSetClipRect", i, vp, pr)
    _bind(s, "SDL_RenderReadPixels", i, vp, pr, u32, vp, i)
    _bind(s, "SDL_CreateTextureFromSurface", vp, vp, vp)
    _bind(s, "SDL_CreateRGBSurfaceWithFormatFrom", vp, vp, i, i, i, i, u32)
    _bind(s, "SDL_FreeSurface", None, vp)
    _bind(s, "SDL_DestroyTexture", None, vp)
    _bind(s, "SDL_QueryTexture", i, vp, C.POINTER(u32), pi, pi, pi)
    _bind(s, "SDL_SetTextureColorMod", i, vp, C.c_uint8, C.c_uint8, C.c_uint8)
    _bind(s, "SDL_SetTextureAlphaMod", i, vp, C.c_uint8)
    _bind(s, "SDL_SetTextureBlendMode", i, vp, i)
    _bind(s, "SDL_SetTextureScaleMode", i, vp, i)
    _bind(s, "SDL_PollEvent", i, vp)
    _bind(s, "SDL_WaitEventTimeout", i, vp, i)
    _bind(s, "SDL_PushEvent", i, vp)
    _bind(s, "SDL_RegisterEvents", u32, i)
    _bind(s, "SDL_NumJoysticks", i)
    _bind(s, "SDL_IsGameController", C.c_int, i)
    _bind(s, "SDL_GameControllerOpen", vp, i)
    _bind(s, "SDL_StartTextInput", None)
    _bind(s, "SDL_StopTextInput", None)
    _bind(s, "SDL_ShowCursor", i, i)
    _bind(s, "SDL_GetTicks", u32)
    t = _ttf
    _bind(t, "TTF_Init", i)
    _bind(t, "TTF_Quit", None)
    _bind(t, "TTF_OpenFont", vp, cp, i)
    _bind(t, "TTF_CloseFont", None, vp)
    _bind(t, "TTF_FontHeight", i, vp)
    _bind(t, "TTF_SetFontStyle", None, vp, i)
    _bind(t, "TTF_SizeUTF8", i, vp, cp, pi, pi)
    _bind(t, "TTF_RenderUTF8_Blended", vp, vp, cp, Color)
    _bind(t, "TTF_RenderUTF8_Blended_Wrapped", vp, vp, cp, Color, u32)


def error():
    return F.SDL_GetError().decode(errors="replace")


class Event:
    """A decoded SDL_Event (only the fields the store uses)."""

    __slots__ = ("type", "key", "mod", "repeat", "text", "button", "x", "y", "value", "which", "axis")

    def __init__(self, buf):
        raw = bytes(buf)
        self.type = struct.unpack_from("<I", raw, 0)[0]
        self.key = self.mod = self.repeat = self.button = self.value = self.which = self.axis = 0
        self.x = self.y = 0
        self.text = ""
        t = self.type
        if t in (KEYDOWN, KEYUP):
            self.repeat = raw[13]
            self.key, self.mod = struct.unpack_from("<iH", raw, 20)
        elif t == TEXTINPUT:
            self.text = raw[12:44].split(b"\0", 1)[0].decode(errors="ignore")
        elif t in (MOUSEBUTTONDOWN, MOUSEBUTTONUP):
            self.which = struct.unpack_from("<I", raw, 12)[0]
            self.button = raw[16]
            self.x, self.y = struct.unpack_from("<ii", raw, 20)
        elif t == MOUSEMOTION:
            self.which, self.button = struct.unpack_from("<II", raw, 12)
            self.x, self.y = struct.unpack_from("<ii", raw, 20)
        elif t == MOUSEWHEEL:
            self.which, self.x, self.y = struct.unpack_from("<Iii", raw, 12)
        elif t in (CONTROLLERBUTTONDOWN, CONTROLLERBUTTONUP):
            self.which = struct.unpack_from("<i", raw, 8)[0]
            self.button = raw[12]
        elif t == CONTROLLERAXISMOTION:
            self.which = struct.unpack_from("<i", raw, 8)[0]
            self.axis = raw[12]
            self.value = struct.unpack_from("<h", raw, 16)[0]
        elif t in (CONTROLLERDEVICEADDED, CONTROLLERDEVICEREMOVED):
            self.which = struct.unpack_from("<i", raw, 8)[0]
        elif t in (FINGERDOWN, FINGERUP, FINGERMOTION):
            # normalized 0..1 coordinates
            self.x, self.y = struct.unpack_from("<ff", raw, 24)


class Font:
    def __init__(self, path, size, bold=False):
        self.ptr = F.TTF_OpenFont(path.encode(), int(size))
        if not self.ptr:
            raise SDLError(f"font {path}: {error()}")
        if bold:
            F.TTF_SetFontStyle(self.ptr, 1)  # synthetic bold (no bold font file)
        self.size = int(size)
        self.height = F.TTF_FontHeight(self.ptr)
        self._w = {}

    def width(self, text):
        w = self._w.get(text)
        if w is None:
            a, b = C.c_int(), C.c_int()
            F.TTF_SizeUTF8(self.ptr, text.encode(), C.byref(a), C.byref(b))
            w = a.value
            if len(self._w) > 4000:
                self._w.clear()
            self._w[text] = w
        return w

    def fit(self, text, maxw):
        """text, shortened with an ellipsis to fit maxw pixels"""
        if self.width(text) <= maxw:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.width(text[:mid].rstrip() + "…") <= maxw:
                lo = mid
            else:
                hi = mid - 1
        return text[:lo].rstrip() + "…"

    def close(self):
        if self.ptr:
            F.TTF_CloseFont(self.ptr)
            self.ptr = None


class Texture:
    __slots__ = ("ptr", "w", "h")

    def __init__(self, ptr, w, h):
        self.ptr, self.w, self.h = ptr, w, h

    def destroy(self):
        if self.ptr:
            F.SDL_DestroyTexture(self.ptr)
            self.ptr = None


class Gfx:
    """Window + renderer + cached white text textures, tinted when drawn."""

    def __init__(self, title, fullscreen=True, size=(1280, 720), software=False):
        load()
        F.SDL_SetHint(b"SDL_JOYSTICK_HIDAPI", os.environ.get("SDL_JOYSTICK_HIDAPI", "0").encode())
        F.SDL_SetHint(b"SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", b"0")
        F.SDL_SetHint(b"SDL_VIDEO_WAYLAND_WMCLASS", b"mangmi-store")
        F.SDL_SetHint(b"SDL_APP_ID", b"mangmi-store")
        if F.SDL_Init(INIT_VIDEO | INIT_GAMECONTROLLER | INIT_EVENTS) != 0:
            # no controller support is not fatal
            if F.SDL_Init(INIT_VIDEO | INIT_EVENTS) != 0:
                raise SDLError(f"SDL_Init: {error()}")
        if F.TTF_Init() != 0:
            raise SDLError(f"TTF_Init: {error()}")
        flags = WINDOW_ALLOW_HIGHDPI | (WINDOW_FULLSCREEN_DESKTOP if fullscreen else WINDOW_RESIZABLE)
        self.win = F.SDL_CreateWindow(title.encode(), WINDOWPOS_CENTERED, WINDOWPOS_CENTERED,
                                    size[0], size[1], flags)
        if not self.win:
            raise SDLError(f"SDL_CreateWindow: {error()}")
        self.ren = None
        if not software:
            self.ren = F.SDL_CreateRenderer(self.win, -1, RENDERER_ACCELERATED | RENDERER_PRESENTVSYNC)
        if not self.ren:
            self.ren = F.SDL_CreateRenderer(self.win, -1, RENDERER_SOFTWARE)
        if not self.ren:
            raise SDLError(f"SDL_CreateRenderer: {error()}")
        F.SDL_SetRenderDrawBlendMode(self.ren, BLENDMODE_BLEND)
        self._text = collections.OrderedDict()
        self._disc = {}
        self.w = self.h = self.win_w = self.win_h = 0
        self.update_size()

    def flush_text(self):
        """forget cached text (fonts were replaced)"""
        for t in self._text.values():
            t.destroy()
        self._text.clear()

    def update_size(self):
        a, b = C.c_int(), C.c_int()
        F.SDL_GetWindowSize(self.win, C.byref(a), C.byref(b))
        self.win_w, self.win_h = a.value, b.value
        F.SDL_GetRendererOutputSize(self.ren, C.byref(a), C.byref(b))
        changed = (a.value, b.value) != (self.w, self.h)
        self.w, self.h = a.value, b.value
        return changed

    # primitives ---------------------------------------------------------
    def clear(self, rgb):
        F.SDL_SetRenderDrawColor(self.ren, rgb[0], rgb[1], rgb[2], 255)
        F.SDL_RenderClear(self.ren)

    def fill(self, x, y, w, h, rgba):
        if w <= 0 or h <= 0:
            return
        F.SDL_SetRenderDrawColor(self.ren, rgba[0], rgba[1], rgba[2], rgba[3] if len(rgba) > 3 else 255)
        F.SDL_RenderFillRect(self.ren, C.byref(Rect(int(x), int(y), int(w), int(h))))

    def _disc_tex(self, r):
        """white anti-aliased disc of radius r (cached)"""
        t = self._disc.get(r)
        if t:
            return t
        d = 2 * r
        buf = bytearray(d * d * 4)
        for yy in range(d):
            dy = yy + 0.5 - r
            for xx in range(d):
                dx = xx + 0.5 - r
                a = r - (dx * dx + dy * dy) ** 0.5 + 0.5
                a = 0 if a <= 0 else (255 if a >= 1 else int(a * 255))
                o = (yy * d + xx) * 4
                buf[o:o + 4] = bytes((255, 255, 255, a))
        t = self.texture_rgba(bytes(buf), d, d, smooth=True)
        self._disc[r] = t
        return t

    def rrect(self, x, y, w, h, r, rgba):
        """filled rounded rectangle"""
        x, y, w, h = int(x), int(y), int(w), int(h)
        r = int(max(0, min(r, w // 2, h // 2)))
        if r < 2:
            return self.fill(x, y, w, h, rgba)
        a = rgba[3] if len(rgba) > 3 else 255
        if a == 255:
            self.fill(x + r, y, w - 2 * r, h, rgba)
            self.fill(x, y + r, r, h - 2 * r, rgba)
            self.fill(x + w - r, y + r, r, h - 2 * r, rgba)
        else:  # no overlaps: alpha must not stack
            self.fill(x + r, y, w - 2 * r, r, rgba)
            self.fill(x, y + r, w, h - 2 * r, rgba)
            self.fill(x + r, y + h - r, w - 2 * r, r, rgba)
        t = self._disc_tex(r)
        F.SDL_SetTextureColorMod(t.ptr, rgba[0], rgba[1], rgba[2])
        F.SDL_SetTextureAlphaMod(t.ptr, a)
        for sx, sy, dx, dy in ((0, 0, x, y), (r, 0, x + w - r, y), (0, r, x, y + h - r), (r, r, x + w - r, y + h - r)):
            F.SDL_RenderCopy(self.ren, t.ptr, C.byref(Rect(sx, sy, r, r)), C.byref(Rect(dx, dy, r, r)))

    def disc(self, cx, cy, r, rgba):
        r = max(1, int(r))
        t = self._disc_tex(r)
        F.SDL_SetTextureColorMod(t.ptr, rgba[0], rgba[1], rgba[2])
        F.SDL_SetTextureAlphaMod(t.ptr, rgba[3] if len(rgba) > 3 else 255)
        F.SDL_RenderCopy(self.ren, t.ptr, None, C.byref(Rect(int(cx) - r, int(cy) - r, 2 * r, 2 * r)))

    def clip(self, rect=None):
        F.SDL_RenderSetClipRect(self.ren, C.byref(Rect(*map(int, rect))) if rect else None)

    # text ---------------------------------------------------------------
    def _text_tex(self, font, text, wrap=0):
        key = (id(font), font.size, text, wrap)
        t = self._text.get(key)
        if t:
            self._text.move_to_end(key)
            return t
        white = Color(255, 255, 255, 255)
        if wrap:
            surf = F.TTF_RenderUTF8_Blended_Wrapped(font.ptr, text.encode(), white, int(wrap))
        else:
            surf = F.TTF_RenderUTF8_Blended(font.ptr, text.encode(), white)
        if not surf:
            return None
        ptr = F.SDL_CreateTextureFromSurface(self.ren, surf)
        F.SDL_FreeSurface(surf)
        if not ptr:
            return None
        w, h = C.c_int(), C.c_int()
        F.SDL_QueryTexture(ptr, None, None, C.byref(w), C.byref(h))
        t = Texture(ptr, w.value, h.value)
        self._text[key] = t
        while len(self._text) > 600:
            self._text.popitem(last=False)[1].destroy()
        return t

    def text(self, font, text, x, y, rgba, maxw=None, align="left", valign="top"):
        """draw one line; returns its width"""
        if not text:
            return 0
        if maxw is not None:
            text = font.fit(text, maxw)
        t = self._text_tex(font, text)
        if not t:
            return 0
        if align == "center":
            x -= t.w / 2
        elif align == "right":
            x -= t.w
        if valign == "middle":
            y -= t.h / 2
        self.blit(t, x, y, tint=rgba)
        return t.w

    def wrapped(self, font, text, x, y, w, maxh, rgba):
        """draw wrapped text, cut at maxh; returns the height used"""
        if not text or w <= 0:
            return 0
        t = self._text_tex(font, text, wrap=int(w))
        if not t:
            return 0
        h = min(t.h, int(maxh))
        if h <= 0:
            return 0
        self.blit(t, x, y, src=(0, 0, t.w, h), size=(t.w, h), tint=rgba)
        return h

    # images -------------------------------------------------------------
    def texture_rgba(self, data, w, h, smooth=False):
        buf = C.create_string_buffer(data, len(data))
        surf = F.SDL_CreateRGBSurfaceWithFormatFrom(buf, w, h, 32, w * 4, PIXELFORMAT_RGBA32)
        if not surf:
            raise SDLError(f"surface: {error()}")
        ptr = F.SDL_CreateTextureFromSurface(self.ren, surf)
        F.SDL_FreeSurface(surf)
        if not ptr:
            raise SDLError(f"texture: {error()}")
        F.SDL_SetTextureBlendMode(ptr, BLENDMODE_BLEND)
        F.SDL_SetTextureScaleMode(ptr, SCALEMODE_LINEAR if smooth else SCALEMODE_NEAREST)
        return Texture(ptr, w, h)

    def blit(self, t, x, y, size=None, src=None, tint=None):
        if tint is not None:
            F.SDL_SetTextureColorMod(t.ptr, tint[0], tint[1], tint[2])
            F.SDL_SetTextureAlphaMod(t.ptr, tint[3] if len(tint) > 3 else 255)
        w, h = size or (t.w, t.h)
        s = C.byref(Rect(*map(int, src))) if src else None
        F.SDL_RenderCopy(self.ren, t.ptr, s, C.byref(Rect(int(x), int(y), int(w), int(h))))

    def present(self):
        F.SDL_RenderPresent(self.ren)

    def screenshot(self):
        """(w, h, RGBA bytes) of the current frame (tests)"""
        buf = C.create_string_buffer(self.w * self.h * 4)
        F.SDL_RenderReadPixels(self.ren, None, PIXELFORMAT_RGBA32, buf, self.w * 4)
        return self.w, self.h, buf.raw

    def close(self):
        for t in self._text.values():
            t.destroy()
        for t in self._disc.values():
            t.destroy()
        self._text.clear()
        self._disc.clear()
        if self.ren:
            F.SDL_DestroyRenderer(self.ren)
        if self.win:
            F.SDL_DestroyWindow(self.win)
        self.ren = self.win = None
        F.TTF_Quit()
        F.SDL_Quit()


def new_event_buffer():
    return (C.c_uint8 * 64)()


def write_png(path, w, h, rgba):
    """minimal PNG writer (tests / screenshots)"""
    import zlib

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))