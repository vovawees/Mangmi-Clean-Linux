#!/system/bin/sh
# Save the stock bootloader (ABL, both slots) next to this script.
#   su -c sh /sdcard/openabl/backup_abl.sh
. "$(dirname "$0")/common.sh"
for s in a b; do
  dd if="$BN/abl_$s" of="$D/abl_$s-stock.img" bs=1048576 2>/dev/null || die "reading abl_$s failed"
done
sync
echo "Stock ABL saved: $D/abl_a-stock.img, $D/abl_b-stock.img"
echo "Copy them to your PC as well."
