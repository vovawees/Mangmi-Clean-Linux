#!/bin/bash
# Smoke test for mangmi-boot-update on a fake ESP.
set -euo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
mkdir -p "$t/esp/dtbs/qcom" "$t/mod/7.2.15-mangmi" "$t/conf"
touch "$t/esp/Image-mangmi" "$t/esp/dtbs/qcom/sm6115-mangmi-air-x-mq66.dtb"
echo linux-mangmi >"$t/mod/7.2.15-mangmi/pkgbase"
echo "root=PARTUUID=12345678-02 rw rootwait quiet" >"$t/cmdline"
export ESP=$t/esp MANGMI_CONF=$t/conf CMDLINE_FILE=$t/cmdline MODULES=$t/mod
"$here/system/tools/usr/bin/mangmi-boot-update"
e=$t/esp/loader/entries/mangmi.conf
grep -qx "linux      /Image-mangmi" "$e"
grep -qx "version    7.2.15-mangmi" "$e"
grep -qx "options    root=PARTUUID=12345678-02 rw rootwait quiet" "$e"
! grep -q devicetree "$e"
grep -q "systemd.unit=multi-user.target" "$t/esp/loader/entries/mangmi-safe.conf"
grep -qx "default mangmi.conf" "$t/esp/loader/loader.conf"
"$here/system/tools/usr/bin/mangmi-boot-update" --model mq66
grep -qx "devicetree /dtbs/qcom/sm6115-mangmi-air-x-mq66.dtb" "$e"
if "$here/system/tools/usr/bin/mangmi-boot-update" --model mq65 2>/dev/null; then
  echo "expected failure for a missing dtb" >&2; exit 1
fi
grep -qx mq66 "$t/conf/model"   # failed pin keeps the old one
"$here/system/tools/usr/bin/mangmi-boot-update" --model auto
! grep -q devicetree "$e"
[[ -z $(ls -A "$t/esp/loader/entries" | grep -v '\.conf$') ]]
echo "boot-update: ok"
