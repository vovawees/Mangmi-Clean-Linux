# shellcheck shell=sh disable=SC2034
# Shared helpers for the OpenABL scripts (Android root shell, POSIX sh / mksh).
D=$(cd "$(dirname "$0")" && pwd)
ELF="$D/abl_signed-SM6115.elf"
BN=""
for p in /dev/block/by-name /dev/block/bootdevice/by-name; do
  [ -e "$p/abl_a" ] && [ -e "$p/abl_b" ] && { BN=$p; break; }
done
die() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "run as root: su -c sh $0"
[ -n "$BN" ] || die "abl_a/abl_b partitions not found"
platform=$(getprop ro.board.platform 2>/dev/null)
case "$platform" in
  bengal|sm6115|"") ;;
  *) [ "${FORCE:-0}" = 1 ] || die "this is not a Snapdragon 662 (ro.board.platform=$platform); FORCE=1 overrides" ;;
esac
# write_abl <image> : write to both slots and verify
write_abl() {
  size=$(stat -c %s "$1") || die "cannot read $1"
  want=$(sha256sum "$1" | cut -d' ' -f1)
  for s in a b; do
    dd if="$1" of="$BN/abl_$s" bs=1048576 2>/dev/null || die "writing abl_$s failed"
    sync
    got=$(dd if="$BN/abl_$s" bs="$size" count=1 2>/dev/null | sha256sum | cut -d' ' -f1)
    [ "$got" = "$want" ] || die "verification of abl_$s failed - do NOT reboot, run restore_abl.sh"
    echo "abl_$s: OK"
  done
}
