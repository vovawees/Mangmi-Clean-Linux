#!/bin/bash
# Smoke test for mangmi-boot-update on a fake ESP.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
mkdir -p "$t/esp/dtbs/qcom" "$t/mod/7.2.15-mangmi" "$t/conf"
touch "$t/esp/Image-mangmi" "$t/esp/dtbs/qcom/sm6115-mangmi-air-x-mq66.dtb" "$t/esp/dtbs/qcom/sm6115-mangmi-air-x-mq66b.dtb"
echo linux-mangmi >"$t/mod/7.2.15-mangmi/pkgbase"
echo "root=PARTUUID=12345678-02 rw rootwait quiet" >"$t/cmdline"
export ESP=$t/esp MANGMI_CONF=$t/conf CMDLINE_FILE=$t/cmdline MODULES=$t/mod
# no initramfs builder: entries without initrd
INITRAMFS_CMD=no-such-command "$here/system/tools/usr/bin/mangmi-boot-update"
e=$t/esp/loader/entries/mangmi.conf
if grep -q "^initrd" "$e"; then exit 1; fi
# with the builder (stubbed: it only writes the file it is given)
printf '#!/bin/sh\necho stub >"$1"\n' >"$t/mkinitrd"; chmod +x "$t/mkinitrd"
export INITRAMFS_CMD=$t/mkinitrd
"$here/system/tools/usr/bin/mangmi-boot-update"
grep -qx "linux      /Image-mangmi" "$e"
grep -qx "initrd     /initramfs-mangmi.img" "$e"
grep -qx "initrd     /initramfs-mangmi.img" "$t/esp/loader/entries/mangmi-safe.conf"
[[ $(cat "$t/esp/initramfs-mangmi.img") == stub ]]
grep -qx "version    7.2.15-mangmi" "$e"
grep -qx "options    root=PARTUUID=12345678-02 rw rootwait quiet" "$e"
if grep -q devicetree "$e"; then exit 1; fi
grep -q "systemd.unit=multi-user.target" "$t/esp/loader/entries/mangmi-safe.conf"
grep -qx "default mangmi.conf" "$t/esp/loader/loader.conf"
"$here/system/tools/usr/bin/mangmi-boot-update" --model mq66
grep -qx "devicetree /dtbs/qcom/sm6115-mangmi-air-x-mq66.dtb" "$e"
grep -qx "devicetree /dtbs/qcom/sm6115-mangmi-air-x-mq66b.dtb" "$t/esp/loader/entries/mangmi-mq66b.conf"
grep -q "(MQ66B board)" "$t/esp/loader/entries/mangmi-mq66b.conf"
[[ ! -e $t/esp/loader/entries/mangmi-mq66.conf && ! -e $t/esp/loader/entries/mangmi-mq65.conf ]]
if "$here/system/tools/usr/bin/mangmi-boot-update" --model mq65 2>/dev/null; then
  echo "expected failure for a missing dtb" >&2; exit 1
fi
grep -qx mq66 "$t/conf/model"   # failed pin keeps the old one
"$here/system/tools/usr/bin/mangmi-boot-update" --model auto
if grep -q devicetree "$e"; then exit 1; fi
[[ ! -e $t/esp/loader/entries/mangmi-mq66b.conf ]]
for f in "$t"/esp/loader/entries/* "$t"/esp/loader/entries/.[!.]*; do
  [[ -e $f && $f != *.conf ]] && { echo "stray file $f" >&2; exit 1; }
done
echo "boot-update: ok"
