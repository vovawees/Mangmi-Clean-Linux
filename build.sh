#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Mangmi Clean Linux - build entry point.
#
#   ./build.sh all         kernel + packages + root file system + image
#   ./build.sh kernel      Linux kernel (scripts/build-kernel.sh)
#   ./build.sh packages    pacman packages -> out/repo  [pkgbase...]
#   ./build.sh rootfs      root file system -> work/stage/target
#   ./build.sh image       microSD image -> out/images/*.img.xz
#   ./build.sh chroot      create/update the Arch Linux ARM build environment
#   ./build.sh shell       shell inside the build environment
#   ./build.sh dtbs        device trees only (any host, quick check)
#   ./build.sh clean       remove work/ (keeps cache/ and out/)
#
# Host: aarch64 Linux (or x86_64 with qemu-user-static binfmt) with bash, curl,
# tar (bsdtar preferred), sudo. Everything else runs in the build environment.
# Settings: config/build.conf, overrides in config/local.conf or the environment
# (IMAGE_FLAVOUR=full|console, DEFAULT_MODEL=mq65|mq66|mq66b|auto, JOBS=N, ...).
set -Eeuo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
. "${here}/scripts/lib.sh"
C="${here}/scripts/chroot.sh"

step() {
  case "$1" in
    chroot)   "${C}" setup ;;
    kernel)   "${C}" user /build/src/scripts/build-kernel.sh ;;
    packages) shift; "${C}" user /build/src/scripts/chroot/packages.sh "$@" ;;
    rootfs)   "${C}" root /build/src/scripts/chroot/rootfs.sh ;;
    image)    "${C}" root /build/src/scripts/chroot/image.sh ;;
    dtbs)     DTBS_ONLY=1 "${here}/scripts/build-kernel.sh" ;;
    shell)    "${C}" shell ;;
    clean)    [[ -d "${WORK_DIR}/chroot/proc" ]] && mountpoint -q "${WORK_DIR}/chroot/proc" \
                && die "build environment still mounted"
              as_root rm -rf --one-file-system "${WORK_DIR}" ;;
    all)      step chroot; step kernel; step packages; step rootfs; step image ;;
    *)        sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
  esac
}

start=$(date +%s)
step "${@:-help}"
ok "done in $(( ($(date +%s) - start) / 60 )) min"
