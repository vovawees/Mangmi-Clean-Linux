#!/bin/bash
# mangmi-esp finds this system's boot partition next to the root file system,
# whatever /etc/fstab says, corrects /etc/fstab (no automount, the partitions
# that are really there) and mounts it on demand.
# Needs root and loop devices (skipped otherwise). Like tests/initramfs.sh the
# test image carries MBR partition entries next to its GPT, so that it also
# works on kernels without GPT support.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
esp_cmd=$here/system/tools/usr/bin/mangmi-esp
if [[ $EUID -ne 0 || ! -e /dev/loop-control ]]; then
  echo "esp: skipped (needs root and loop devices)"; exit 0
fi
for c in sfdisk mkfs.fat mkfs.ext4 blkid findfs; do
  command -v "$c" >/dev/null || { echo "esp: skipped (no $c)"; exit 0; }
done
t=$(mktemp -d)
loops=()
cleanup() {
  umount "$t/boot" 2>/dev/null || :
  for l in "${loops[@]}"; do losetup -d "$l" 2>/dev/null || :; done
  rm -rf "$t"
}
trap cleanup EXIT
fail() { echo "esp: $*" >&2; exit 1; }

# mbr IMAGE SIGNATURE "start size type" ... : MBR entries next to the GPT
mbr() {
  python3 - "$@" <<'PY'
import struct, sys
img, sig, parts = sys.argv[1], int(sys.argv[2], 16), sys.argv[3:]
with open(img, "r+b") as f:
    f.seek(440); f.write(struct.pack("<I", sig) + b"\0\0")
    for i, p in enumerate(parts):
        start, size, typ = (int(x, 0) for x in p.split())
        f.write(struct.pack("<B3sB3sII", 0, b"\xfe\xff\xff", typ, b"\xfe\xff\xff", start, size))
    f.write(b"\0" * 16 * (4 - len(parts)) + b"\x55\xaa")
PY
}

# image NAME SIGNATURE [esp]: a Mangmi-like disk, with or without boot
# partition, on a loop device -> $loop
image() {
  local img=$t/$1.img
  truncate -s 96M "$img"
  if [[ ${3:-} == esp ]]; then
    sfdisk -q "$img" <<SF
label: gpt
start=2048, size=65536, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="MANGMI_BOOT"
start=67584, size=126976, type=B921B045-1DF0-41C3-AF44-4C6F280D3FAE, name="MANGMI_ROOT"
SF
    mbr "$img" "$2" "2048 65536 0xef" "67584 126976 0x83"
  else
    sfdisk -q "$img" <<SF
label: gpt
start=67584, size=126976, type=B921B045-1DF0-41C3-AF44-4C6F280D3FAE, name="MANGMI_ROOT"
SF
    mbr "$img" "$2" "67584 126976 0x83"
  fi
  loop=$(losetup --find --show --partscan "$img")
  loops+=("$loop")
  partx -u "$loop" 2>/dev/null || :
  udevadm settle 2>/dev/null || :
}

image a 6d616e67 esp
a=$loop
[[ -b ${a}p2 ]] || { echo "esp: skipped (no partition scan)"; exit 0; }
mkfs.fat -n MANGMI_BOOT "${a}p1" >/dev/null 2>&1
mkfs.ext4 -q -F -L MANGMI_ROOT "${a}p2"
a_esp=$(blkid -p -s PART_ENTRY_UUID -o value "${a}p1")
a_root=$(blkid -p -s PART_ENTRY_UUID -o value "${a}p2")

mkdir -p "$t/boot" "$t/run"
# the fstab of the failing boot: an automount of a partition that is not there
cat >"$t/fstab" <<EOT
# <file system> <dir> <type> <options> <dump> <pass>
PARTUUID=d52a7c80-ee5d-4311-cd97-9bce4913f1f3  /      ext4   rw,noatime,commit=30  0  0
PARTUUID=8c6e3b22-a25d-481f-3f96-35b87930fda0  /boot  vfat   rw,noatime,fmask=0022,dmask=0022,utf8,errors=remount-ro,noauto,x-systemd.automount,x-systemd.idle-timeout=60  0  2
EOT
run() { MANGMI_ESP_ROOT=$root FSTAB=$t/fstab ESP_DIR=$t/boot MANGMI_ESP_RUN=$t/run "$esp_cmd" "$@"; }

root=${a}p2
[[ $(run find) == "${a}p1" ]] || fail "boot partition next to the root not found"
run fstab 2>/dev/null
grep -qx "PARTUUID=$a_root / ext4 rw,noatime,commit=30 0 0" "$t/fstab" || fail "/ not corrected: $(cat "$t/fstab")"
grep -qx "PARTUUID=$a_esp /boot vfat rw,noatime,fmask=0022,dmask=0022,utf8,errors=remount-ro,noauto,nofail,x-systemd.device-timeout=5s 0 2" \
  "$t/fstab" || fail "/boot not corrected: $(cat "$t/fstab")"
grep -q automount "$t/fstab" && fail "automount left in fstab"
grep -q 8c6e3b22 "$t/fstab.mangmi-old" || fail "no backup of the old fstab"
cp "$t/fstab" "$t/fstab.good"
run fstab 2>/dev/null
cmp -s "$t/fstab" "$t/fstab.good" || fail "a correct fstab was changed"

# a disk without a boot partition: the one named in fstab, if it is one
image b 62626262
b=$loop
mkfs.ext4 -q -F -L MANGMI_ROOT "${b}p1"
root=${b}p1
[[ $(run find) == "${a}p1" ]] || fail "boot partition from fstab not used"
sed -i "s/PARTUUID=$a_esp/PARTUUID=0badc0de-0000-4000-8000-000000000000/" "$t/fstab"
if run find 2>/dev/null; then fail "found a boot partition that is not there"; fi
# not found: mount fails, but fstab loses the automount anyway
cp "$t/fstab.mangmi-old" "$t/fstab"; rm -f "$t/fstab.mangmi-old"
if run mount 2>/dev/null; then fail "mount without a boot partition succeeded"; fi
grep -q automount "$t/fstab" && fail "automount left in fstab (no boot partition)"
grep -q "8c6e3b22-a25d-481f-3f96-35b87930fda0  /boot\|8c6e3b22-a25d-481f-3f96-35b87930fda0 /boot" "$t/fstab" || fail "unknown /boot partition was replaced"

# mount / umount; without FAT in this kernel a bind mount stands in for it
root=${a}p2
real=1
if ! grep -qw vfat /proc/filesystems && ! modprobe -q vfat 2>/dev/null; then
  real=""
  mkdir -p "$t/bin" "$t/fat"
  printf '#!/bin/sh\nfor d; do :; done\nexec %s --bind %s "$d"\n' "$(command -v mount)" "$t/fat" >"$t/bin/mount"
  chmod 755 "$t/bin/mount"
  export PATH=$t/bin:$PATH
fi
run mount
mountpoint -q "$t/boot" || fail "not mounted"
if [[ -n $real ]]; then
  [[ $(findmnt -nvo SOURCE "$t/boot") == "${a}p1" ]] || fail "wrong partition mounted"
fi
[[ $(cat "$t/run/esp-mounted") == "${a}p1" ]] || fail "mount not recorded"
run mount # already mounted: nothing to do
touch "$t/boot/x"
run umount
mountpoint -q "$t/boot" && fail "still mounted"
[[ ! -e $t/boot/x ]] || fail "file went to the directory"
[[ ! -e $t/run/esp-mounted ]] || fail "record left behind"
# mounted by someone else: left alone
mount --bind "$t/run" "$t/boot"
run umount
mountpoint -q "$t/boot" || fail "unmounted a mount it did not make"
umount "$t/boot"
echo "esp: ok"
