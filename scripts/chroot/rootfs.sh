#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# (inside the build chroot, as root) Install and configure the target root file
# system in /build/work/target from config/packages/*.list and the local
# [mangmi] repository. Writes the partition identifiers to /build/work/image.env.
. /build/src/scripts/lib.sh

T=/build/work/target
FLAVOUR="${IMAGE_FLAVOUR:-full}"
case "${FLAVOUR}" in
  full)    lists=(base console emulators desktop) ;;
  console) lists=(base console emulators) ;;
  *) die "IMAGE_FLAVOUR must be full or console" ;;
esac
mapfile -t pkgs < <(for l in "${lists[@]}"; do
  sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "/build/src/config/packages/${l}.list"; done)
log "root file system: ${FLAVOUR} (${#pkgs[@]} packages + dependencies)"

# 1. fresh target --------------------------------------------------------------------
if [[ -d "${T}" ]]; then
  findmnt -R -n -l -o TARGET "${T}" 2>/dev/null | sort -r | xargs -r -n1 umount -l 2>/dev/null || true
  rm -rf --one-file-system "${T}"
fi
mkdir -p "${T}"

# Documentation is never needed on the device (licenses are kept).
NOEXTRACT='NoExtract   = usr/share/doc/* usr/share/gtk-doc/* usr/share/man/* usr/share/info/*
NoExtract   = usr/share/help/* !usr/share/help/C/* !usr/share/help/en* !usr/share/help/ru*'
conf=/build/work/pacman-install.conf
awk -v ne="${NOEXTRACT}" '{print} /^\[options\]/{print ne}' /etc/pacman.conf >"${conf}"

pacman -Sy --noconfirm >/dev/null
pacstrap -C "${conf}" -c -G -M "${T}" "${pkgs[@]}"

# 2. identity of this build's partitions ------------------------------------------------
cat >/build/work/image.env <<ENV
ROOT_PARTUUID=$(uuidgen)
ESP_PARTUUID=$(uuidgen)
ROOT_FSUUID=$(uuidgen)
ESP_VOLID=$(od -An -N4 -tx1 /dev/urandom | tr -d ' \n' | tr a-f A-F)
ENV
. /build/work/image.env

# 3. configuration (runs inside the target) ------------------------------------------------
install -Dm755 /build/src/scripts/chroot/rootfs-setup.sh "${T}/root/rootfs-setup.sh"
printf '%s\n' "${NOEXTRACT}" >"${T}/root/noextract.conf"
BUILD_ID="$(date -u +%Y%m%d%H%M)"
GIT_COMMIT="$(git -C /build/src rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
export DISTRO_NAME DISTRO_ID DISTRO_VERSION DEFAULT_USER DEFAULT_PASSWORD DEFAULT_HOSTNAME \
       DEFAULT_LOCALE DEFAULT_TIMEZONE DEFAULT_MODEL ROOT_PARTUUID ESP_PARTUUID FLAVOUR \
       BUILD_ID GIT_COMMIT \
       MANGMI_REPO_URL="${MANGMI_REPO_URL-https://github.com/vovawees/Mangmi-Clean-Linux/releases/download/repo}"
arch-chroot "${T}" /root/rootfs-setup.sh
rm -f "${T}/root/rootfs-setup.sh" "${T}/root/noextract.conf"

# 4. image hygiene ------------------------------------------------------------------------------
rm -rf "${T}"/var/cache/pacman/pkg/* "${T}"/var/lib/pacman/sync/* "${T}"/etc/pacman.d/gnupg \
       "${T}"/var/log/journal/* "${T}"/var/tmp/* "${T}"/tmp/* "${T}"/root/.cache \
       "${T}"/etc/ssh/ssh_host_* "${T}"/var/lib/systemd/random-seed
find "${T}/var/log" -type f -delete
: >"${T}/etc/machine-id"
# never let the clock start before this build (no RTC battery backup assumed)
touch "${T}/usr/lib/clock-epoch"

du_mb=$(du -sxm "${T}" | cut -f1)
ok "root file system ready: ${du_mb} MiB, $(pacman -r "${T}" -Qq | wc -l) packages"
pacman -r "${T}" -Q >/build/out/packages-${FLAVOUR}.txt
