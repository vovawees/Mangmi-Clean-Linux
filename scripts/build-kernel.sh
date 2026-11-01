#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Build the Mangmi Clean Linux kernel (linux-mangmi):
#   kernel.org release + stable patch -> ROCKNIX SM6115 patches + device trees
#   -> ROCKNIX config + kernel/mangmi.config -> Image, modules, DTBs, headers.
#
# Output: ${OUT_DIR}/kernel/{Image,dtbs/,modules/,headers/,config,System.map,kernelrelease}
#         (headers/ only from native builds)
#
# Works natively on aarch64 or cross on x86_64 (set CROSS_COMPILE=aarch64-linux-gnu-).
# env: DTBS_ONLY=1  - only build the device trees (quick validation, any host)
#      JOBS=N       - parallel jobs (default: nproc)
. "$(dirname "$0")/lib.sh"

need curl xz tar make patch bc flex bison perl
KSRC="${WORK_DIR}/kernel/linux-${KERNEL_STABLE}"
KOUT="${OUT_DIR}/kernel"
ARCH=arm64
export ARCH
if [[ "$(uname -m)" != "aarch64" && -z "${CROSS_COMPILE:-}" && "${DTBS_ONLY:-0}" != 1 ]]; then
  command -v aarch64-linux-gnu-gcc >/dev/null && export CROSS_COMPILE=aarch64-linux-gnu- \
    || die "not on aarch64: install aarch64-linux-gnu-gcc or set CROSS_COMPILE"
fi
[[ -n "${CROSS_COMPILE:-}" ]] && export CROSS_COMPILE
export KBUILD_BUILD_USER=mangmi KBUILD_BUILD_HOST=clean-linux
# USE_CCACHE=1: compiler cache in ${CACHE_DIR}/ccache (CI keeps it between runs)
kcc=()
if [[ "${USE_CCACHE:-0}" == 1 ]] && command -v ccache >/dev/null; then
  export CCACHE_DIR="${CCACHE_DIR:-${CACHE_DIR}/ccache}" CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-2G}"
  export CCACHE_SLOPPINESS=time_macros,include_file_mtime,include_file_ctime CCACHE_COMPILERCHECK=content
  kcc=(CC="ccache ${CROSS_COMPILE:-}gcc")
fi

# 1. sources ---------------------------------------------------------------------
fetch "${KERNEL_MIRROR}/linux-${KERNEL_BASE}.tar.xz" "${CACHE_DIR}/linux-${KERNEL_BASE}.tar.xz" "${KERNEL_BASE_SHA256}"
if [[ "${KERNEL_STABLE}" != "${KERNEL_BASE}" ]]; then
  fetch "${KERNEL_MIRROR}/patch-${KERNEL_STABLE}.xz" "${CACHE_DIR}/patch-${KERNEL_STABLE}.xz" "${KERNEL_STABLE_SHA256}"
fi
fetch "https://cdn.kernel.org/pub/software/network/wireless-regdb/wireless-regdb-${REGDB_VERSION}.tar.xz" \
  "${CACHE_DIR}/wireless-regdb-${REGDB_VERSION}.tar.xz" "${REGDB_SHA256}"
ROCKNIX_DIR="$("${MCL_ROOT}/scripts/fetch-rocknix.sh" | tail -n1)"

# 2. fresh, patched tree ----------------------------------------------------------
own_patches_hash() {
  find "${MCL_ROOT}/kernel/patches" "${MCL_ROOT}/kernel/dts" \( -name '*.patch' -o -name '*.dtsi' \) -type f -print0 2>/dev/null \
    | sort -z | xargs -0 -r cat | sha256sum | cut -c1-12
}
stamp="${KERNEL_STABLE}-${ROCKNIX_COMMIT:0:12}-$(own_patches_hash)-$(echo "${KERNEL_PATCH_EXCLUDE}" | sha256sum | cut -c1-8)"
if [[ ! -f "${KSRC}/.mangmi-stamp" || "$(cat "${KSRC}/.mangmi-stamp")" != "${stamp}" ]]; then
  log "preparing kernel tree ${KERNEL_STABLE}"
  rm -rf "${KSRC}" "${WORK_DIR}/kernel/linux-${KERNEL_BASE}"
  mkdir -p "${WORK_DIR}/kernel"
  tar -C "${WORK_DIR}/kernel" -xf "${CACHE_DIR}/linux-${KERNEL_BASE}.tar.xz"
  if [[ "${KERNEL_STABLE}" != "${KERNEL_BASE}" ]]; then
    mv "${WORK_DIR}/kernel/linux-${KERNEL_BASE}" "${KSRC}"
    xz -dc "${CACHE_DIR}/patch-${KERNEL_STABLE}.xz" | patch -d "${KSRC}" -p1 -s -N
  fi
  KERNEL_PATCH_EXCLUDE="${KERNEL_PATCH_EXCLUDE}" \
    "${MCL_ROOT}/scripts/kernel-apply-patches.sh" "${KSRC}" "${ROCKNIX_DIR}" "${MCL_ROOT}/kernel/patches"
  log "adding SM6115 device trees"
  cp -a "${ROCKNIX_DIR}/projects/ROCKNIX/devices/SM6115/linux/dts/." "${KSRC}/arch/arm64/boot/dts/"
  # Our board fixes: kernel/dts/qcom/<board>-fixes.dtsi goes at the end of <board>.dts.
  for f in "${MCL_ROOT}"/kernel/dts/qcom/*-fixes.dtsi; do
    [[ -f "${f}" ]] || continue
    b="${KSRC}/arch/arm64/boot/dts/qcom/$(basename "${f%-fixes.dtsi}").dts"
    [[ -f "${b}" ]] || die "${f##*/}: ${b##*/} not found"
    cp "${f}" "${KSRC}/arch/arm64/boot/dts/qcom/"
    printf '\n#include "%s"\n' "${f##*/}" >>"${b}"
    log "device tree fixes: ${f##*/}"
  done
  mkdir -p "${KSRC}/external-firmware"
  tar -C "${WORK_DIR}/kernel" -xf "${CACHE_DIR}/wireless-regdb-${REGDB_VERSION}.tar.xz"
  cp "${WORK_DIR}/kernel/wireless-regdb-${REGDB_VERSION}"/regulatory.db{,.p7s} "${KSRC}/external-firmware/"
  echo "${stamp}" >"${KSRC}/.mangmi-stamp"
fi
[[ "$(make -s -C "${KSRC}" kernelversion)" == "${KERNEL_STABLE}" ]] || die "unexpected kernel version"

# 3. configuration -----------------------------------------------------------------
fragments=("${MCL_ROOT}/kernel/mangmi.config")
[[ "${KERNEL_SCHED_EXT}" == 1 ]] && fragments+=("${MCL_ROOT}/kernel/sched-ext.config")
[[ -f "${MCL_ROOT}/config/local-kernel.config" ]] && fragments+=("${MCL_ROOT}/config/local-kernel.config")

log "configuring (ROCKNIX SM6115 base + ${#fragments[@]} fragment(s))"
cp "${ROCKNIX_DIR}/projects/ROCKNIX/devices/SM6115/linux/linux.aarch64.conf" "${KSRC}/.config"
(cd "${KSRC}" && KCONFIG_CONFIG=.config ./scripts/kconfig/merge_config.sh -m -Q .config "${fragments[@]}" >/dev/null)
"${KSRC}/scripts/config" --file "${KSRC}/.config" \
  --set-str EXTRA_FIRMWARE "regulatory.db regulatory.db.p7s" \
  --set-str EXTRA_FIRMWARE_DIR "external-firmware"
make -C "${KSRC}" "${kcc[@]}" -s olddefconfig

# Every explicit request in our fragments must survive olddefconfig.
bad=0
while IFS= read -r line; do
  if [[ "${line}" =~ ^(CONFIG_[A-Za-z0-9_]+)=(.*)$ ]]; then
    key="${BASH_REMATCH[1]}" want="${BASH_REMATCH[2]}"
    got="$(grep -E "^${key}=" "${KSRC}/.config" | head -n1 | cut -d= -f2- || true)"
    [[ "${got}" == "${want}" || ( "${want}" == m && "${got}" == y ) ]] && continue
    warn "${key}: wanted ${want}, got ${got:-unset}"; bad=1
  elif [[ "${line}" =~ ^#\ (CONFIG_[A-Za-z0-9_]+)\ is\ not\ set ]]; then
    key="${BASH_REMATCH[1]}"
    grep -qE "^${key}=[ym]" "${KSRC}/.config" && { warn "${key}: should be disabled"; bad=1; }
  fi
done < <(cat "${fragments[@]}")
if ((bad)); then
  if [[ "${DTBS_ONLY:-0}" == 1 ]]; then
    warn "config mismatch ignored for a DTB-only build (host compiler is not aarch64)"
  else
    die "kernel config fragment not honoured"
  fi
fi
ok "config: $(grep -c '=y' "${KSRC}/.config") built-in, $(grep -c '=m' "${KSRC}/.config") modules"

# 4. build -----------------------------------------------------------------------------
read -r -a dtbs <<<"${DTBS}"
mk() { make -C "${KSRC}" "${kcc[@]}" -j"$(nproc_build)" DTC_FLAGS=-@ "$@"; }

if [[ "${DTBS_ONLY:-0}" == 1 ]]; then
  log "building device trees only"
  mk "${dtbs[@]}"
else
  KCFLAGS="${KCFLAGS:-}"
  # Tune (not -march: no ISA change) for the big.LITTLE A73/A53 pair.
  if echo 'int x;' | "${CROSS_COMPILE:-}gcc" -mtune=cortex-a73.cortex-a53 -x c -c -o /dev/null - 2>/dev/null; then
    KCFLAGS+=" -mtune=cortex-a73.cortex-a53"
  fi
  export KCFLAGS
  log "building Image + modules (${KCFLAGS:-default flags})"
  mk Image modules "${dtbs[@]}"
fi

# 5. collect ------------------------------------------------------------------------------
rm -rf "${KOUT}"
mkdir -p "${KOUT}/dtbs/qcom"
for d in "${dtbs[@]}"; do cp "${KSRC}/arch/arm64/boot/dts/${d}" "${KOUT}/dtbs/qcom/"; done
cp "${KSRC}/.config" "${KOUT}/config"
if [[ "${DTBS_ONLY:-0}" != 1 ]]; then
  krel="$(make -C "${KSRC}" -s kernelrelease)"
  echo "${krel}" >"${KOUT}/kernelrelease"
  cp "${KSRC}/arch/arm64/boot/Image" "${KOUT}/Image"
  cp "${KSRC}/System.map" "${KOUT}/System.map"
  make -C "${KSRC}" -s INSTALL_MOD_PATH="${KOUT}/modules" INSTALL_MOD_STRIP=1 DEPMOD=/bin/true modules_install
  rm -f "${KOUT}/modules/lib/modules/${krel}/"{build,source}
  # Headers carry the kernel's build tools, so they only make sense from a native build
  # (CI builds on arm64); a cross build would ship host binaries in them.
  if [[ -z "${CROSS_COMPILE:-}" ]]; then
    "${MCL_ROOT}/scripts/kernel-headers.sh" "${KSRC}" "${KOUT}/headers/usr/lib/modules/${krel}/build"
  else
    log "cross build: skipping linux-mangmi-headers (needs a native aarch64 build)"
  fi
  ok "kernel ${krel}: $(du -h "${KOUT}/Image" | cut -f1) Image, $(find "${KOUT}/modules" -name '*.ko*' | wc -l) modules"
  ((${#kcc[@]})) && ccache -s 2>/dev/null | grep -Ei 'hit|miss' | head -3 >&2 || true
fi
ok "device trees: $(cd "${KOUT}/dtbs" && find . -name '*.dtb' | sort | tr '\n' ' ')"
