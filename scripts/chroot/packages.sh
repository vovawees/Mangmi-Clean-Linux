#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# (inside the build chroot, as 'builder') Build the Mangmi Clean Linux packages
# into the local pacman repository /build/out/repo ([mangmi]).
# Packages whose inputs did not change since the last build are skipped
# (FORCE=1 rebuilds everything).
#   packages.sh [pkgbase...]
. /build/src/scripts/lib.sh

REPO=/build/out/repo
DB="${REPO}/mangmi.db.tar.gz"
PB=/build/work/pkgbuild
ORDER=(qrtr pd-mapper rmtfs tqftpserv mangmi-firmware linux-mangmi mangmi
       es-de-bin duckstation-bin melonds-bin armsx2-bin mangmi-cores)
(($#)) && ORDER=("$@")

mkdir -p "${REPO}/.stamps" "${PB}" /build/work/makepkg /build/cache/sources
rsync -a --delete /build/src/packages/ "${PB}/"

# Content hash of everything that goes into a package.
inputs_hash() {
  local paths=("packages/$1")
  case "$1" in
    mangmi) paths+=(system mangmi LICENSE) ;;
    *-bin) paths+=(packages/appimage.sh) ;;
  esac
  {
    (cd /build/src && find "${paths[@]}" -type f ! -name '*.pyc' ! -path '*/__pycache__/*' -print0 \
      | sort -z | xargs -0 sha256sum)
    if [[ "$1" == linux-mangmi ]]; then
      sha256sum /build/out/kernel/Image /build/out/kernel/config /build/out/kernel/kernelrelease
      echo "${MCL_KERNEL_PKGREL:-1}"
    fi
  } | sha256sum | cut -c1-16
}

sudo pacman -Sy --noconfirm >/dev/null
built=0
for p in "${ORDER[@]}"; do
  [[ -f "${PB}/${p}/PKGBUILD" ]] || die "no package ${p}"
  if [[ "${p}" == linux-mangmi && ! -f /build/out/kernel/Image ]]; then
    die "linux-mangmi: build the kernel first (./build.sh kernel)"
  fi
  h="$(inputs_hash "${p}")"
  if [[ "${FORCE:-0}" != 1 && -f "${REPO}/.stamps/${p}" && "$(cat "${REPO}/.stamps/${p}")" == "${h}" ]]; then
    ok "${p}: up to date"
    continue
  fi
  log "building ${p}"
  rm -rf /build/work/pkgdest && mkdir -p /build/work/pkgdest
  (
    cd "${PB}/${p}" || exit 1
    export MCL_KERNEL_OUT=/build/out/kernel PKGDEST=/build/work/pkgdest SRCDEST=/build/cache/sources \
           BUILDDIR=/build/work/makepkg
    if [[ "${p}" == linux-mangmi ]]; then
      MCL_KERNEL_VERSION="$(cut -d- -f1 /build/out/kernel/kernelrelease)"
      export MCL_KERNEL_VERSION
    fi
    makepkg --syncdeps --force --noconfirm --needed --cleanbuild --clean
  )
  mapfile -t files < <(find /build/work/pkgdest -name '*.pkg.tar.*' ! -name '*.sig')
  ((${#files[@]})) || die "${p}: makepkg produced nothing"
  mv -f "${files[@]}" "${REPO}/"
  (cd "${REPO}" && repo-add -q -R "${DB}" "${files[@]##*/}")
  echo "${h}" >"${REPO}/.stamps/${p}"
  sudo pacman -Sy --noconfirm >/dev/null
  ok "${p}: ${files[*]##*/}"
  built=$((built + 1))
done
ok "repository ${REPO}: $(find "${REPO}" -maxdepth 1 -name '*.pkg.tar.*' | wc -l) packages (${built} rebuilt)"
