#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Common helpers for Mangmi Clean Linux build scripts.

set -Eeuo pipefail

MCL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MCL_ROOT

# shellcheck source=../config/build.conf
. "${MCL_ROOT}/config/build.conf"

# Local overrides (not committed): config/local.conf
if [[ -f "${MCL_ROOT}/config/local.conf" ]]; then
  # shellcheck disable=SC1091
  . "${MCL_ROOT}/config/local.conf"
fi

WORK_DIR="${WORK_DIR:-${MCL_ROOT}/work}"
OUT_DIR="${OUT_DIR:-${MCL_ROOT}/out}"
CACHE_DIR="${CACHE_DIR:-${MCL_ROOT}/cache}"
export WORK_DIR OUT_DIR CACHE_DIR
mkdir -p "${WORK_DIR}" "${OUT_DIR}" "${CACHE_DIR}"

if [[ -t 2 ]]; then
  _c_info=$'\e[1;34m' _c_ok=$'\e[1;32m' _c_warn=$'\e[1;33m' _c_err=$'\e[1;31m' _c_off=$'\e[0m'
else
  _c_info="" _c_ok="" _c_warn="" _c_err="" _c_off=""
fi

log()  { printf '%s==>%s %s\n' "${_c_info}" "${_c_off}" "$*" >&2; }
ok()   { printf '%s ok%s %s\n' "${_c_ok}" "${_c_off}" "$*" >&2; }
warn() { printf '%s!!%s %s\n' "${_c_warn}" "${_c_off}" "$*" >&2; }
die()  { printf '%sxx%s %s\n' "${_c_err}" "${_c_off}" "$*" >&2; exit 1; }

trap 'die "failed at ${BASH_SOURCE[0]}:${LINENO}: ${BASH_COMMAND}"' ERR

need() {
  local missing=()
  for c in "$@"; do command -v "$c" >/dev/null 2>&1 || missing+=("$c"); done
  ((${#missing[@]} == 0)) || die "missing tools: ${missing[*]}"
}

nproc_build() { echo "${JOBS:-$(nproc)}"; }

# fetch URL DEST [SHA256]
# Downloads into the cache (resumable, retried) and verifies the checksum if given.
fetch() {
  local url="$1" dest="$2" sum="${3:-}"
  mkdir -p "$(dirname "${dest}")"
  if [[ -f "${dest}" && -n "${sum}" ]] && echo "${sum}  ${dest}" | sha256sum -c --status; then
    ok "cached $(basename "${dest}")"
    return 0
  fi
  log "download ${url}"
  curl -fL --retry 5 --retry-delay 3 --retry-all-errors -C - -o "${dest}.part" "${url}" \
    || curl -fL --retry 5 --retry-delay 3 --retry-all-errors -o "${dest}.part" "${url}"
  mv -f "${dest}.part" "${dest}"
  if [[ -n "${sum}" ]]; then
    echo "${sum}  ${dest}" | sha256sum -c --status || die "sha256 mismatch: ${dest}"
    ok "verified $(basename "${dest}")"
  fi
}

# git_fetch_commit URL DIR COMMIT [sparse paths...]
# Shallow, optionally sparse checkout of an exact commit.
git_fetch_commit() {
  local url="$1" dir="$2" commit="$3"; shift 3
  if [[ -d "${dir}/.git" ]] && [[ "$(git -C "${dir}" rev-parse HEAD 2>/dev/null)" == "${commit}" ]]; then
    ok "$(basename "${dir}") @ ${commit:0:12}"
    return 0
  fi
  rm -rf "${dir}"
  mkdir -p "${dir}"
  git -C "${dir}" init -q
  git -C "${dir}" remote add origin "${url}"
  if (($#)); then
    git -C "${dir}" config core.sparseCheckout true
    git -C "${dir}" sparse-checkout set --no-cone "$@"
  fi
  git -C "${dir}" fetch -q --depth 1 --filter=blob:none origin "${commit}"
  git -C "${dir}" checkout -q FETCH_HEAD
  ok "$(basename "${dir}") @ ${commit:0:12}"
}

# Run a command as root (works both as root and via sudo).
as_root() {
  if [[ ${EUID} -eq 0 ]]; then "$@"; else sudo "$@"; fi
}
