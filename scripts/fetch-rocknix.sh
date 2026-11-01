#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Sparse, shallow checkout of the pinned ROCKNIX commit: only the files that
# Mangmi Clean Linux consumes (kernel patches, SM6115 device tree + config,
# audio UCM, InputPlumber maps, emulator configs).
. "$(dirname "$0")/lib.sh"

ROCKNIX_DIR="${ROCKNIX_DIR:-${CACHE_DIR}/rocknix}"
need git

git_fetch_commit "${ROCKNIX_REPO}" "${ROCKNIX_DIR}" "${ROCKNIX_COMMIT}" \
  "/LICENSE*" \
  "/projects/ROCKNIX/packages/linux/patches/mainline/" \
  "/projects/ROCKNIX/packages/linux/patches/7.2/" \
  "/projects/ROCKNIX/devices/SM6115/" \
  "/projects/ROCKNIX/packages/audio/alsa-ucm-conf/sources/ucm2/Qualcomm/sm6115/" \
  "/projects/ROCKNIX/packages/audio/alsa-ucm-conf/sources/ucm2/conf.d/sm4250/" \
  "/projects/ROCKNIX/packages/graphics/mesa/patches/" \
  "/projects/ROCKNIX/packages/hardware/quirks/platforms/SM6115/" \
  "/projects/ROCKNIX/packages/emulators/libretro/retroarch/sources/SM6115/" \
  "/projects/ROCKNIX/packages/emulators/standalone/*/config/SM6115/" \
  "/projects/ROCKNIX/packages/emulators/standalone/*/sources/SM6115/"

echo "${ROCKNIX_DIR}"
