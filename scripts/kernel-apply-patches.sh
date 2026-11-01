#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Apply kernel patches to a source tree in the exact order ROCKNIX uses for
# the SM6115 device, followed by Mangmi Clean Linux's own patches.
#
# Patches that are already part of the selected stable release are detected
# (reverse dry-run succeeds) and skipped, so a newer 7.2.y can be used.
#
# usage: kernel-apply-patches.sh <kernel-src> <rocknix-checkout> <extra-patch-dir>
# env:   KERNEL_PATCH_EXCLUDE="name1.patch name2.patch"  (basenames to skip)
set -Eeuo pipefail

SRC="$1" RNX="$2" OWN="${3:-}"

series=()
excluded() { local n; for n in ${KERNEL_PATCH_EXCLUDE:-}; do [[ "$(basename "$1")" == "$n" ]] && return 0; done; return 1; }
add_dir() {
  local d="$1" f
  [[ -d "$d" ]] || return 0
  for f in "$d"/*.patch; do
    [[ -f "$f" ]] || continue
    if excluded "$f"; then echo "  EXCL   ${f#"${RNX}"/}"; continue; fi
    series+=("$f")
  done
}

# Order mirrors ROCKNIX scripts/unpack with PKG_PATCH_DIRS="mainline SM6115 default"
# and PKG_VERSION=7.2 for the project-local linux package.
add_dir "${RNX}/projects/ROCKNIX/packages/linux/patches/mainline"
add_dir "${RNX}/projects/ROCKNIX/packages/linux/patches/7.2"
add_dir "${RNX}/projects/ROCKNIX/devices/SM6115/patches/linux"
[[ -n "${OWN}" ]] && add_dir "${OWN}"

applied=0 skipped=0
for p in "${series[@]}"; do
  name="${p#"${RNX}"/}"
  if grep -qE '^GIT binary patch$|^rename from|^rename to' "$p"; then
    if (cd "$SRC" && git apply -p1 --whitespace=nowarn --check "$p" 2>/dev/null); then
      (cd "$SRC" && git apply -p1 --whitespace=nowarn "$p")
      applied=$((applied + 1)); echo "  APPLY  ${name}"
    elif (cd "$SRC" && git apply -p1 -R --check "$p" 2>/dev/null); then
      skipped=$((skipped + 1)); echo "  SKIP   ${name} (already applied)"
    else
      echo "  FAIL   ${name}" >&2; exit 1
    fi
    continue
  fi
  if patch -d "$SRC" -p1 -N -s --dry-run -F2 <"$p" >/dev/null 2>&1; then
    patch -d "$SRC" -p1 -N -s -F2 --no-backup-if-mismatch <"$p" >/dev/null
    applied=$((applied + 1)); echo "  APPLY  ${name}"
  elif patch -d "$SRC" -p1 -R -s --dry-run -F2 <"$p" >/dev/null 2>&1; then
    skipped=$((skipped + 1)); echo "  SKIP   ${name} (already in this kernel)"
  else
    echo "  FAIL   ${name}" >&2
    patch -d "$SRC" -p1 -N --dry-run -F2 <"$p" | tail -20 >&2 || true
    exit 1
  fi
done
echo "patches: ${applied} applied, ${skipped} skipped (of ${#series[@]})"
