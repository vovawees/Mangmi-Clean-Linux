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
