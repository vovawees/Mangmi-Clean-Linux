#!/system/bin/sh
# Put the stock bootloader back (from backup_abl.sh).
#   su -c sh /sdcard/openabl/restore_abl.sh
. "$(dirname "$0")/common.sh"
for s in a b; do
  [ -f "$D/abl_$s-stock.img" ] || die "$D/abl_$s-stock.img not found"
done
want=$(stat -c %s "$D/abl_a-stock.img")
for s in a b; do
  dd if="$D/abl_$s-stock.img" of="$BN/abl_$s" bs=1048576 2>/dev/null || die "writing abl_$s failed"
done
sync
for s in a b; do
  [ "$(dd if="$BN/abl_$s" bs="$want" count=1 2>/dev/null | sha256sum | cut -d' ' -f1)" = \
    "$(sha256sum "$D/abl_$s-stock.img" | cut -d' ' -f1)" ] || die "verification of abl_$s failed"
done
echo "Stock ABL restored."
