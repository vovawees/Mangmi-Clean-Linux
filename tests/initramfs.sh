#!/bin/bash
# The initramfs /init finds a disk image written into a partition (OpenABL
# internal install into Android's userdata) and the root partition inside it -
# also when the kernel gets someone else's root= (then by the system's own
# UUIDs from /etc/mangmi-root, or as a last resort by its label).
# Needs root and loop devices (skipped otherwise). Runs the script with busybox
# ash when BUSYBOX points to one (an aarch64 busybox works through qemu-user).
#
# The test images carry MBR partition entries next to their GPT, so that the
# test also works on kernels without GPT support: the partitions are then
# found by their MBR PARTUUIDs (<disk signature>-<number>).
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
init=$here/system/tools/usr/lib/mangmi/initramfs/init
if [[ $EUID -ne 0 || ! -e /dev/loop-control ]]; then
  echo "initramfs: skipped (needs root and loop devices)"; exit 0
fi
sh=(sh)
[[ -n ${BUSYBOX:-} ]] && sh=("$BUSYBOX" sh)
t=$(mktemp -d)
cleanup() {
  umount "$t/mnt" 2>/dev/null || :
  umount "$t/newroot" 2>/dev/null || :
  losetup -j "$t/emmc.img" -O NAME -n 2>/dev/null | xargs -r -n1 losetup -d 2>/dev/null || :
  for l in $(losetup -l -n -O NAME,BACK-FILE | awk '$2 ~ /^\/dev\/loop/ {print $1}'); do
    [[ -e /sys/class/block/${l#/dev/} ]] && losetup -d "$l" 2>/dev/null || :
  done
  rm -rf "$t"
}
trap cleanup EXIT

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

# a small Mangmi image: GPT + MBR, ESP + root (ext4 with /sbin/init)
mkdir -p "$t/root/sbin" "$t/mnt" "$t/newroot"
printf '#!/bin/sh\n' >"$t/root/sbin/init"; chmod 755 "$t/root/sbin/init"
truncate -s 64M "$t/mangmi.img"
sfdisk -q "$t/mangmi.img" <<SF
label: gpt
start=2048, size=16384, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="MANGMI_BOOT"
start=18432, size=110592, type=B921B045-1DF0-41C3-AF44-4C6F280D3FAE, name="MANGMI_ROOT"
SF
mbr "$t/mangmi.img" 6d616e67 "2048 16384 0xef" "18432 110592 0x83"
mkfs.ext4 -q -F -L MANGMI_ROOT -d "$t/root" -E offset=$((18432 * 512)) "$t/mangmi.img" 54M
root_uuid=6d616e67-02

# an "eMMC" with Android-like partitions; the image goes into the big one
truncate -s 1300M "$t/emmc.img"
mbr "$t/emmc.img" 454d4d43 "2048 8192 0x83" "10240 2650000 0x83"
dd if="$t/mangmi.img" of="$t/emmc.img" bs=1M seek=5 conv=notrunc,sparse status=none
emmc=$(losetup --find --show --partscan "$t/emmc.img")
[[ -e /sys/class/block/${emmc#/dev/}p2 ]] || { echo "initramfs: skipped (no partition scan)"; exit 0; }

fail() { echo "initramfs: $*" >&2; exit 1; }
echo "PARTUUID=${root_uuid}" >"$t/ids"
cmdline="root=PARTUUID=${root_uuid^^} rw rootfstype=ext4 quiet"
foreign="root=PARTUUID=d52a7c80-ee5d-4311-cd97-9bce4913f1f3 loglevel=6"
run() { # shell snippet after sourcing /init in test mode
  MANGMI_INIT_TEST=1 LOSETUP=$(command -v losetup) NEW_ROOT=$t/newroot \
    ROOT_IDS=${ids-$t/ids} MANGMI_CMDLINE=$cmdline "${sh[@]}" -c ". '$init'; $1"
}
[[ $(run 'echo "$root $mode $rootfstype"') == "PARTUUID=${root_uuid^^} rw ext4" ]]
run 'find_root' && fail "root visible before mapping"
dev=$(run 'attach_images && echo "$dev"')
[[ $dev == /dev/loop*p2 ]] || fail "unexpected root device '$dev'"
[[ $(run 'find_root && echo "$dev"') == "$dev" ]]
[[ $(losetup -n -O BACK-FILE "${dev%p2}") == "${emmc}p2" ]]
# the mapped root mounts and holds an init
[[ $(run "dev=$dev; use_root && echo \"\$init\"; umount \"\$NEW_ROOT\"") == /sbin/init ]] || fail "use_root failed on $dev"
# a partition without a file system is skipped, not booted
[[ $(run "dev=${emmc}p1 spec=PARTUUID=x; use_root && echo booted") == *"cannot mount"*skipped ]] || fail "booted ${emmc}p1"
losetup -d "${dev%p2}"

# someone else's root=: at first only root= is looked for (it may still be
# probing), after a second also this system's own PARTUUID (/etc/mangmi-root)
cmdline=$foreign
run 'attach_images' && fail "foreign root= found"
got=$(run 't=10; attach_images >/dev/null && echo "$dev $spec"')
[[ $got == "/dev/loop"*"p2 PARTUUID=${root_uuid}" ]] || fail "own root not found: '$got'"
losetup -d "${got%%p2 *}"
[[ $(run 't=10; candidates | tr "\n" " "') == *"PARTUUID=${root_uuid}"* ]]
# no own UUIDs either: the MANGMI_ROOT label, from 5 s on only
ids=$t/none
run 't=10; attach_images' && fail "label used before 5 s"
got=$(run 't=50; attach_images >/dev/null && echo "$dev $spec"')
[[ $got == "/dev/loop"*"p2 LABEL=MANGMI_ROOT" ]] || fail "label fallback failed: '$got'"
msg=$(run "dev=${got%% *} spec=LABEL=MANGMI_ROOT; use_root; umount \"\$NEW_ROOT\"")
[[ $msg == *"not found, using this system's root file system LABEL=MANGMI_ROOT"* ]] || fail "no notice: '$msg'"
losetup -d "${got%%p2 *}"
unset ids
cmdline="root=PARTUUID=${root_uuid^^} rw rootfstype=ext4 quiet"
dev=$(run 'attach_images && echo "$dev"')
# polling again in the same shell does not map the same partition twice
maps() { losetup -n -l -O BACK-FILE | grep -c "^${emmc}p2 *\$" || :; }
n=$(maps)
run 'attach_images; attach_images; :' >/dev/null
[[ $(maps) == $((n + 1)) ]] || { echo "partition mapped more than once" >&2; exit 1; }
mount -o ro "$dev" "$t/mnt"
[[ -x $t/mnt/sbin/init ]]
echo "initramfs: ok ($dev in ${emmc}p2, shell: ${sh[*]})"
