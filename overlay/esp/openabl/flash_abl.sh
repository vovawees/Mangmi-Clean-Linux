#!/system/bin/sh
# Install OpenABL (both slots). Android keeps working.
#   su -c sh /sdcard/openabl/flash_abl.sh
. "$(dirname "$0")/common.sh"
[ -f "$ELF" ] || die "$ELF not found"
[ -f "$D/abl_a-stock.img" ] || die "run backup_abl.sh first"
if [ -f "$ELF.sha256" ]; then
  [ "$(cut -d' ' -f1 "$ELF.sha256")" = "$(sha256sum "$ELF" | cut -d' ' -f1)" ] || die "$ELF is corrupted"
fi
write_abl "$ELF"
echo "OpenABL installed. Power off, insert the Mangmi Clean Linux card and"
echo "power on holding Volume Down: Boot mode -> Linux, then Start."
