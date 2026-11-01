#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# (inside the build chroot, as root) Turn /build/work/target into a bootable
# microSD image:
#
#   GPT  p1  MANGMI_BOOT  FAT32, ESP type   kernel, device trees, BLS entries,
#                                            mangmi-setup.txt, OpenABL files
#        p2  MANGMI_ROOT  ext4, ARM64 root  everything else (grown on first boot)
#
# Output: /build/out/images/<name>.img.xz + .sha256
. /build/src/scripts/lib.sh
. /build/work/image.env

T=/build/work/target
[[ -x "${T}/usr/bin/pacman" ]] || die "no root file system - run ./build.sh rootfs first"
FLAVOUR="${IMAGE_FLAVOUR:-full}"
NAME="mangmi-clean-linux-${DISTRO_VERSION}-${FLAVOUR}"
OUT=/build/out/images
W=/build/work/image
IMG="${W}/${NAME}.img"
rm -rf "${W}"; mkdir -p "${W}" "${OUT}"

# 1. boot partition contents -----------------------------------------------------------
ESP="${W}/esp"
mkdir -p "${ESP}/openabl"
cp -a "${T}/boot/." "${ESP}/"
cp /build/src/overlay/esp/mangmi-setup.txt "${ESP}/"
fetch "${OPENABL_URL}/abl_signed-SM6115.elf" "${CACHE_DIR}/openabl-${OPENABL_VERSION}/abl_signed-SM6115.elf" "${OPENABL_ELF_SHA256}"
fetch "${OPENABL_URL}/openabl-recovery-flashable-sm6115.zip" \
  "${CACHE_DIR}/openabl-${OPENABL_VERSION}/openabl-recovery-flashable-sm6115.zip" "${OPENABL_ZIP_SHA256}"
cp "${CACHE_DIR}/openabl-${OPENABL_VERSION}"/* "${ESP}/openabl/"
cat >"${ESP}/openabl/README.txt" <<TXT
OpenABL ${OPENABL_VERSION} for Snapdragon 662 (SM6115) - https://github.com/OpenHandheldCollective/OpenABL
Install once (Android keeps working), see docs/INSTALL.md:
  fastboot flash abl_a abl_signed-SM6115.elf
  fastboot flash abl_b abl_signed-SM6115.elf
or flash openabl-recovery-flashable-sm6115.zip from a custom recovery.
TXT
esp_used=$(du -sm "${ESP}" | cut -f1)
ESP_MB="${IMAGE_ESP_MB:-512}"
((esp_used + 64 < ESP_MB)) || die "boot files (${esp_used} MiB) do not fit into ${ESP_MB} MiB"

# 2. sizes --------------------------------------------------------------------------------
used_mb=$(du -sxm "${T}" | cut -f1)
files=$(find "${T}" -xdev | wc -l)
ROOT_MB=$(( (used_mb * 112 / 100 + 640 + 63) / 64 * 64 ))
[[ -n "${IMAGE_ROOT_MB:-}" && "${IMAGE_ROOT_MB}" -gt "${ROOT_MB}" ]] && ROOT_MB="${IMAGE_ROOT_MB}"
TOTAL_MB=$((1 + ESP_MB + ROOT_MB + 1))
log "image ${NAME}: boot ${ESP_MB} MiB, root ${ROOT_MB} MiB (${used_mb} MiB used, ${files} files)"

# 3. partition table -------------------------------------------------------------------------
truncate -s "${TOTAL_MB}M" "${IMG}"
sfdisk -q "${IMG}" <<SFDISK
label: gpt
unit: sectors
first-lba: 2048
start=2048, size=$((ESP_MB * 2048)), type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, uuid=${ESP_PARTUUID}, name="MANGMI_BOOT"
start=$(((1 + ESP_MB) * 2048)), size=$((ROOT_MB * 2048)), type=B921B045-1DF0-41C3-AF44-4C6F280D3FAE, uuid=${ROOT_PARTUUID}, name="MANGMI_ROOT"
SFDISK

# 4. FAT32 boot partition (built aside, then placed) ---------------------------------------------
truncate -s "${ESP_MB}M" "${W}/esp.img"
mkfs.fat -F 32 -n MANGMI_BOOT -i "${ESP_VOLID}" "${W}/esp.img" >/dev/null
export MTOOLS_SKIP_CHECK=1
shopt -s dotglob
mcopy -Q -s -m -i "${W}/esp.img" "${ESP}"/* ::/
shopt -u dotglob
fsck.fat -n "${W}/esp.img" >/dev/null || die "boot partition check failed"
dd if="${W}/esp.img" of="${IMG}" bs=1M seek=1 conv=notrunc,sparse status=none
rm -f "${W}/esp.img"

# 5. ext4 root, written straight into the image at its offset ------------------------------------
off=$(((1 + ESP_MB) * 1024 * 1024))
hold="${W}/boot.hold"
mv "${T}/boot" "${hold}"
mkdir -m 0755 "${T}/boot"
restore_boot() { [[ -d "${hold}" ]] && rmdir "${T}/boot" 2>/dev/null && mv "${hold}" "${T}/boot"; true; }
trap restore_boot EXIT
mkfs.ext4 -q -F -L MANGMI_ROOT -U "${ROOT_FSUUID}" -m 1 -I 256 \
  -E "offset=${off},nodiscard,lazy_itable_init=0,lazy_journal_init=0" -d "${T}" "${IMG}" "${ROOT_MB}M"
restore_boot; trap - EXIT
e2fsck -fn "${IMG}?offset=${off}" >/dev/null 2>&1 && ok "root file system check passed" \
  || warn "could not verify the root file system in place (non-fatal)"
sfdisk -d "${IMG}" | sed 's/^/   /'

# 6. compress ---------------------------------------------------------------------------------------
if [[ "${IMAGE_COMPRESS:-xz}" == none ]]; then
  mv -f "${IMG}" "${OUT}/"
  final="${OUT}/${NAME}.img"
else
  log "compressing (xz -T0)"
  xz -T0 -6 -f -c "${IMG}" >"${OUT}/${NAME}.img.xz.part"
  mv -f "${OUT}/${NAME}.img.xz.part" "${OUT}/${NAME}.img.xz"
  rm -f "${IMG}"
  final="${OUT}/${NAME}.img.xz"
fi
(cd "${OUT}" && sha256sum "${final##*/}" >"${final##*/}.sha256")
cp -f "/build/out/packages-${FLAVOUR}.txt" "${OUT}/${NAME}.packages.txt" 2>/dev/null || true
ok "$(du -h "${final}" | cut -f1)  ${final}"
