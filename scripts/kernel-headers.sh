#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Install the subset of a built kernel tree needed to compile out-of-tree
# modules (DKMS etc.), modelled on Arch Linux's linux-headers packaging.
# usage: kernel-headers.sh <built-kernel-tree> <destination build dir>
set -Eeuo pipefail
src="$1" dst="$2"
rm -rf "${dst}"
mkdir -p "${dst}"
cd "${src}"

install -Dt "${dst}" -m644 .config Makefile Module.symvers System.map
[[ -f localversion ]] && install -Dt "${dst}" -m644 localversion*
install -Dt "${dst}/kernel" -m644 kernel/Makefile
install -Dt "${dst}/arch/arm64" -m644 arch/arm64/Makefile
cp -a scripts "${dst}/"
cp -a include "${dst}/"
cp -a arch/arm64/include "${dst}/arch/arm64/"
install -Dt "${dst}/arch/arm64/kernel" -m644 arch/arm64/kernel/asm-offsets.s 2>/dev/null || true
for d in tools/objtool/objtool tools/bpf/resolve_btfids/resolve_btfids; do
  if [[ -x "$d" ]]; then install -Dt "${dst}/$(dirname "$d")" "$d"; fi
done
install -Dt "${dst}/drivers/md" -m644 drivers/md/*.h
install -Dt "${dst}/net/mac80211" -m644 net/mac80211/*.h
find . -name 'Kconfig*' -not -path './Documentation/*' -exec install -Dm644 {} "${dst}/{}" \;
# BTF-carrying vmlinux (debug info stripped) lets DKMS modules get BTF too.
if [[ -f vmlinux ]]; then
  "${CROSS_COMPILE:-}objcopy" --strip-debug vmlinux "${dst}/vmlinux"
fi
find -L "${dst}" -type l -delete
find "${dst}" -type f \( -name '*.o' -o -name '*.cmd' \) -delete
find "${dst}/arch" -mindepth 1 -maxdepth 1 -not -name arm64 -exec rm -rf {} +
echo "headers: $(du -sh "${dst}" | cut -f1)"
