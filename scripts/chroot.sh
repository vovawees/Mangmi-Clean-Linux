#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Arch Linux ARM build environment.
#
# Kernel, packages, root file system and disk image are all produced inside an
# Arch Linux ARM chroot, so the host needs nothing but bash, curl, tar, sudo and
# an aarch64 CPU (x86_64 works too with qemu-user-static registered in binfmt).
#
#   chroot.sh setup          create (or update) the environment
#   chroot.sh root CMD...    run CMD as root inside it
#   chroot.sh user CMD...    run CMD as the unprivileged 'builder' user
#   chroot.sh shell          interactive shell (as builder)
#
# Inside: /build/src = this repository, /build/out = OUT_DIR,
#         /build/cache = CACHE_DIR, /build/work = WORK_DIR/stage
. "$(dirname "$0")/lib.sh"

CHROOT="${CHROOT:-${WORK_DIR}/chroot}"
STAGE="${WORK_DIR}/stage"
BUILD_UID="${SUDO_UID:-$(id -u)}"
((BUILD_UID == 0)) && BUILD_UID=1000
SETUP_REV=3   # bump to force a fresh environment
mkdir -p "${STAGE}" "${CACHE_DIR}/pacman/pkg" "${CACHE_DIR}/sources" "${OUT_DIR}/repo"
# The builder user owns everything it writes to (also when started via sudo).
own_dirs() {
  as_root chown "${BUILD_UID}:${BUILD_UID}" "${OUT_DIR}" "${CACHE_DIR}" "${STAGE}" "${CACHE_DIR}/sources"
  as_root chown -R "${BUILD_UID}:${BUILD_UID}" "${OUT_DIR}/repo"
}

check_arch() {
  [[ "$(uname -m)" == aarch64 ]] && return 0
  [[ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]] \
    || die "aarch64 host required (or install qemu-user-static with binfmt support)"
  warn "foreign host: running Arch Linux ARM through qemu-user (slow)"
}

MOUNTS=()
mnt() { # mnt [mount args...] TARGET
  local target="${*: -1}"
  as_root mkdir -p "${target}"
  as_root mount "$@"
  MOUNTS+=("${target}")
}
mount_all() {
  local m
  for m in var/cache/pacman/pkg build/work build/cache build/out build/src run dev sys proc; do
    if mountpoint -q "${CHROOT}/${m}"; then
      warn "removing stale mount ${CHROOT}/${m}"
      as_root umount -R "${CHROOT}/${m}" 2>/dev/null || as_root umount -Rl "${CHROOT}/${m}"
    fi
  done
  mnt -t proc proc "${CHROOT}/proc"
  mnt --rbind /sys "${CHROOT}/sys"; as_root mount --make-rslave "${CHROOT}/sys"
  mnt --rbind /dev "${CHROOT}/dev"; as_root mount --make-rslave "${CHROOT}/dev"
  mnt -t tmpfs -o mode=0755,nosuid,nodev tmpfs "${CHROOT}/run"
  mnt --bind "${MCL_ROOT}" "${CHROOT}/build/src"
  mnt --bind "${OUT_DIR}" "${CHROOT}/build/out"
  mnt --bind "${CACHE_DIR}" "${CHROOT}/build/cache"
  mnt --bind "${STAGE}" "${CHROOT}/build/work"
  mnt --bind "${CACHE_DIR}/pacman/pkg" "${CHROOT}/var/cache/pacman/pkg"
  as_root rm -f "${CHROOT}/etc/resolv.conf"
  as_root cp -L /etc/resolv.conf "${CHROOT}/etc/resolv.conf" 2>/dev/null || true
}
umount_all() {
  local i
  for ((i = ${#MOUNTS[@]} - 1; i >= 0; i--)); do
    as_root umount -R "${MOUNTS[i]}" 2>/dev/null || as_root umount -Rl "${MOUNTS[i]}" 2>/dev/null || true
  done
  MOUNTS=()
}
trap umount_all EXIT

CHROOT_BIN="$(command -v chroot 2>/dev/null || echo /usr/sbin/chroot)"

# Environment passed into the chroot (everything else is reset).
chroot_env() {
  local v
  echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/bin" "LANG=C.UTF-8" "TERM=${TERM:-dumb}"
  echo "MCL_SRC=/build/src" "WORK_DIR=/build/work" "OUT_DIR=/build/out" "CACHE_DIR=/build/cache"
  for v in JOBS FORCE IMAGE_FLAVOUR DEFAULT_MODEL DISTRO_VERSION DEFAULT_USER DEFAULT_PASSWORD \
           DEFAULT_HOSTNAME DEFAULT_LOCALE DEFAULT_TIMEZONE IMAGE_ROOT_MB IMAGE_COMPRESS \
           USE_CCACHE KERNEL_SCHED_EXT MCL_KERNEL_PKGREL GITHUB_ACTIONS CI; do
    [[ -n "${!v:-}" ]] && printf '%s=%s\n' "${v}" "${!v}"
  done
}
run_root() {
  local envs; mapfile -t envs < <(chroot_env | tr ' ' '\n')
  as_root env -i "${envs[@]}" HOME=/root "${CHROOT_BIN}" "${CHROOT}" "$@"
}
run_user() {
  local envs; mapfile -t envs < <(chroot_env | tr ' ' '\n')
  as_root env -i "${envs[@]}" HOME=/home/builder USER=builder LOGNAME=builder \
    "${CHROOT_BIN}" --userspec="${BUILD_UID}:${BUILD_UID}" "${CHROOT}" "$@"
}

setup() {
  check_arch
  if [[ -f "${CHROOT}/.mangmi-chroot" && "$(cat "${CHROOT}/.mangmi-chroot")" == "${SETUP_REV}" ]]; then
    mount_all
    run_root pacman -Syu --noconfirm --needed
    ok "build environment up to date"
    return 0
  fi

  local tarball="${CACHE_DIR}/ArchLinuxARM-aarch64-latest.tar.gz" md5=""
  md5="$(curl -fsSL --retry 5 "${ALARM_ROOTFS_URL}.md5" 2>/dev/null | awk '{print $1}')" || true
  if [[ ! -f "${tarball}" ]] || { [[ -n "${md5}" ]] && ! echo "${md5}  ${tarball}" | md5sum -c --status; }; then
    rm -f "${tarball}"
    fetch "${ALARM_ROOTFS_URL}" "${tarball}"
    [[ -z "${md5}" ]] || echo "${md5}  ${tarball}" | md5sum -c --status || die "ALARM rootfs md5 mismatch"
  fi

  log "creating build environment in ${CHROOT}"
  [[ -d "${CHROOT}" ]] && as_root rm -rf --one-file-system "${CHROOT}"
  as_root mkdir -p "${CHROOT}"
  if command -v bsdtar >/dev/null; then
    as_root bsdtar -xpf "${tarball}" -C "${CHROOT}"
  else
    as_root tar --numeric-owner -xpzf "${tarball}" -C "${CHROOT}" 2>/dev/null
  fi

  local pc="${CHROOT}/etc/pacman.conf"
  echo "Server = ${ALARM_MIRROR}/\$arch/\$repo" | as_root tee "${CHROOT}/etc/pacman.d/mirrorlist" >/dev/null
  as_root sed -i -E -e 's/^#?ParallelDownloads.*/ParallelDownloads = 8/' -e '/^CheckSpace/d' \
    -e 's/^DownloadUser/#DownloadUser/' -e 's/^#?Color$/Color/' "${pc}"
  grep -q '^DisableSandbox' "${pc}" || as_root sed -i '/^\[options\]/a DisableSandbox' "${pc}"
  # Locally built packages (scripts/build-packages.sh) take precedence.
  as_root sed -i '/^\[core\]/i [mangmi]\nSigLevel = Optional TrustAll\nServer = file:///build/out/repo\n' "${pc}"
  if [[ ! -e "${OUT_DIR}/repo/mangmi.db" ]]; then
    as_root tar -czf "${OUT_DIR}/repo/mangmi.db.tar.gz" -T /dev/null
    as_root ln -sf mangmi.db.tar.gz "${OUT_DIR}/repo/mangmi.db"
  fi
  own_dirs

  mount_all
  run_root bash -euo pipefail -c '
    pacman-key --init >/dev/null
    pacman-key --populate archlinuxarm >/dev/null
    # a build environment needs no kernel, firmware or initramfs
    mapfile -t rm < <(pacman -Qq | grep -E "^(linux-aarch64|linux-firmware.*|mkinitcpio)$" || true)
    ((${#rm[@]} == 0)) || pacman -Rdd --noconfirm "${rm[@]}" >/dev/null
    pacman -Syu --noconfirm --needed base-devel git python arch-install-scripts \
      dosfstools mtools e2fsprogs util-linux xz zstd squashfs-tools libarchive \
      bc cpio pahole libelf openssl perl ccache rsync
    gpgconf --kill all 2>/dev/null || true
  '
  run_root bash -euo pipefail -s "${BUILD_UID}" <<'SETUP'
uid=$1
other=$(getent passwd "$uid" | cut -d: -f1 || true)
[[ -n $other && $other != builder ]] && userdel -r "$other" 2>/dev/null
getent group "$uid" >/dev/null && [[ $(getent group "$uid" | cut -d: -f1) != builder ]] \
  && groupdel "$(getent group "$uid" | cut -d: -f1)"
id builder >/dev/null 2>&1 || { groupadd -g "$uid" builder; useradd -m -u "$uid" -g builder builder; }
echo 'builder ALL=(ALL:ALL) NOPASSWD: ALL' >/etc/sudoers.d/builder
chmod 0440 /etc/sudoers.d/builder
git config --system safe.directory '*'
mkdir -p /etc/makepkg.conf.d
cat >/etc/makepkg.conf.d/mangmi.conf <<'CONF'
PACKAGER="Mangmi Clean Linux <vovawees@gmail.com>"
MAKEFLAGS="-j$(nproc)"
BUILDENV=(!distcc color !ccache check !sign)
OPTIONS=(strip docs !libtool !staticlibs emptydirs zipman purge !debug !lto)
PKGEXT='.pkg.tar.zst'
COMPRESSZST=(zstd -c -T0 -10 -)
CONF
SETUP
  echo "${SETUP_REV}" | as_root tee "${CHROOT}/.mangmi-chroot" >/dev/null
  ok "build environment ready (builder uid ${BUILD_UID})"
}

cmd="${1:-}"; shift || true
case "${cmd}" in
  setup) setup ;;
  root)  [[ -f "${CHROOT}/.mangmi-chroot" ]] || setup; ((${#MOUNTS[@]})) || mount_all; own_dirs; run_root "$@" ;;
  user)  [[ -f "${CHROOT}/.mangmi-chroot" ]] || setup; ((${#MOUNTS[@]})) || mount_all; own_dirs; run_user "$@" ;;
  shell) ((${#MOUNTS[@]})) || mount_all; run_user bash -l ;;
  *) die "usage: $0 setup | root CMD... | user CMD... | shell" ;;
esac
