# shellcheck shell=bash disable=SC2154
# SPDX-License-Identifier: GPL-2.0-or-later
# Shared by the *-bin packages: unpack an upstream AppImage into /opt so it
# starts without FUSE and without decompressing on every launch.

# _appimage_extract FILE DEST
_appimage_extract() {
  local f=$1 dest=$2 off
  chmod +x "$f"
  rm -rf squashfs-root
  if ! { "./$f" --appimage-extract >/dev/null 2>&1 && [[ -d squashfs-root ]]; }; then
    # foreign architecture: the payload starts right after the ELF runtime
    off=$(python3 - "$f" <<'PY'
import struct, sys
with open(sys.argv[1], "rb") as fh:
    h = fh.read(64)
assert h[:4] == b"\x7fELF" and h[4] == 2, "not an ELF64 AppImage"
shoff = struct.unpack_from("<Q", h, 0x28)[0]
shentsize, shnum = struct.unpack_from("<HH", h, 0x3A)
print(shoff + shentsize * shnum)
PY
)
    rm -rf squashfs-root
    unsquashfs -q -n -o "$off" -d squashfs-root "$f"
  fi
  chmod -R u+rwX,go+rX,go-w squashfs-root
  install -dm755 "$(dirname "$dest")"
  mv squashfs-root "$dest"
}

# _appimage_launcher NAME TARGET  -> /usr/bin/NAME
_appimage_launcher() {
  install -Dm755 /dev/stdin "$pkgdir/usr/bin/$1" <<SH
#!/bin/sh
exec $2 "\$@"
SH
}

# _appimage_desktop SRC-DIR EXEC ICON-NAME: install the bundled .desktop + icon
# (AppDir entries are often symlinks, some of them dangling: use the first
# candidate that resolves to a real file)
_appimage_desktop() {
  local c d="" icon="" ext=""
  for c in "$1"/*.desktop; do [[ -f $c ]] && { d=$c; break; }; done
  if [[ -n $d ]]; then
    sed -E "s|^Exec=[^ ]*|Exec=$2|; s|^TryExec=.*||; s|^Icon=.*|Icon=$3|" "$d" \
      | install -Dm644 /dev/stdin "$pkgdir/usr/share/applications/$3.desktop"
  fi
  for c in "$1"/*.svg "$1"/*.png "$1"/.DirIcon; do [[ -f $c ]] && { icon=$c; break; }; done
  if [[ -n $icon ]]; then
    case $icon in *.svg) ext=svg ;; *.png) ext=png ;; *) ext=$(file -b --extension "$icon" | cut -d/ -f1) ;; esac
    install -Dm644 "$icon" "$pkgdir/usr/share/pixmaps/$3.${ext:-png}"
  fi
  return 0
}

# _appimage_dedupe APPDIR LIBDIR SONAME...: delete the bundled copies of
# libraries the system provides with the same SONAME (list them, and depend on
# their packages), then every bundled library no ELF executable of the AppDir
# needs any more. The bundled libraries find the system ones through the
# normal search path once their own copy is gone.
_appimage_dedupe() {
  local appdir=$1 libdir=$2 s
  shift 2
  for s in "$@"; do rm -f "$libdir/$s"; done
  python3 - "$appdir" "$libdir" <<'PY'
import os, re, subprocess, sys
appdir, libdir = sys.argv[1], os.path.realpath(sys.argv[2])
def is_elf(p):
    try:
        with open(p, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False
def needed(p):
    out = subprocess.run(["readelf", "-d", p], capture_output=True, text=True).stdout
    return re.findall(r"\(NEEDED\)\s+Shared library: \[(.+?)\]", out)
bundled = {f for f in os.listdir(libdir) if ".so" in f}
roots = []
for d, _, files in os.walk(appdir):
    if os.path.realpath(d) == libdir:
        continue
    roots += [os.path.join(d, f) for f in files if not os.path.islink(os.path.join(d, f)) and is_elf(os.path.join(d, f))]
seen, todo = set(), [n for r in roots for n in needed(r)]
while todo:
    n = todo.pop()
    if n in bundled and n not in seen:
        seen.add(n)
        todo += needed(os.path.join(libdir, n))
gone = sorted(bundled - seen)
for n in gone:
    os.remove(os.path.join(libdir, n))
print(f"appimage: {len(gone)} unused bundled libraries removed", file=sys.stderr)
PY
}
