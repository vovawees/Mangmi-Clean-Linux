#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# CI: publish build results through the GitHub REST API.
#   out/repo/*    -> release "repo"     pacman repository [mangmi] (stale assets removed)
#   out/images/*  -> release "nightly"  (pushes to main, pre-release, tag moved to HEAD)
#                 -> release "vX.Y"     (pushed tags)
# env: GH_TOKEN, GITHUB_REPOSITORY, GITHUB_SHA, GITHUB_REF (provided by Actions)
set -euo pipefail
: "${GH_TOKEN:?}" "${GITHUB_REPOSITORY:?}" "${GITHUB_SHA:?}"
OUT_DIR="${OUT_DIR:-out}"
api="https://api.github.com/repos/${GITHUB_REPOSITORY}"
up="https://uploads.github.com/repos/${GITHUB_REPOSITORY}"
auth=(-H "Authorization: Bearer ${GH_TOKEN}" -H "Accept: application/vnd.github+json"
      -H "X-GitHub-Api-Version: 2022-11-28")
MAX_ASSET=$((2000 * 1024 * 1024))   # GitHub limit is 2 GiB per asset

gh_api() { curl -fsS --retry 3 "${auth[@]}" "$@"; }

release_id() { # tag title prerelease(true|false) body-file
  local id
  id=$(gh_api "${api}/releases/tags/$1" 2>/dev/null | jq -r '.id // empty') || id=""
  if [[ -z ${id} ]]; then
    id=$(jq -n --arg t "$1" --arg n "$2" --rawfile b "$4" --arg c "${GITHUB_SHA}" --argjson p "$3" \
          '{tag_name:$t, name:$n, body:$b, target_commitish:$c, prerelease:$p,
            make_latest:(if $p then "false" else "true" end)}' \
         | gh_api -X POST "${api}/releases" -d @- | jq -r .id)
  else
    jq -n --arg n "$2" --rawfile b "$4" '{name:$n, body:$b}' \
      | gh_api -X PATCH "${api}/releases/${id}" -d @- >/dev/null
  fi
  echo "${id}"
}
assets() { gh_api "${api}/releases/$1/assets?per_page=100" | jq -r '.[] | "\(.id) \(.name)"'; }
delete_asset() { gh_api -X DELETE "${api}/releases/assets/$1" >/dev/null; }
upload() { # release-id file [asset-name]
  local name="${3:-$(basename "$2")}"
  echo "  upload ${name} ($(du -h "$2" | cut -f1))"
  gh_api -X POST -H "Content-Type: application/octet-stream" -T "$2" \
    "${up}/releases/$1/assets?name=$(jq -rn --arg n "${name}" '$n|@uri')" >/dev/null
}
# replace RELEASE-ID FILE... : upload files (splitting >2 GiB), drop every other asset
replace_assets() {
  local id=$1; shift
  local -A have=() keep=()
  local f n
  while read -r aid n; do [[ -n ${n} ]] && have[${n}]=${aid}; done < <(assets "${id}")
  for f in "$@"; do
    n=$(basename "${f}")
    case ${n} in   # pacman fetches <repo>.db / <repo>.files
      mangmi.db.tar.*)    n=mangmi.db ;;
      mangmi.files.tar.*) n=mangmi.files ;;
    esac
    if (( $(stat -c %s "${f}") > MAX_ASSET )); then
      split -b "${MAX_ASSET}" -d -a 2 "${f}" "${f}.part"
      for p in "${f}".part*; do
        keep[$(basename "${p}")]=1
        [[ -n ${have[$(basename "${p}")]:-} ]] && delete_asset "${have[$(basename "${p}")]}"
        upload "${id}" "${p}"
      done
      continue
    fi
    keep[${n}]=1
    [[ -n ${have[${n}]:-} ]] && delete_asset "${have[${n}]}"
    upload "${id}" "${f}" "${n}"
  done
  for n in "${!have[@]}"; do
    [[ -n ${keep[${n}]:-} ]] || { echo "  remove ${n}"; delete_asset "${have[${n}]}"; }
  done
}

notes=$(mktemp)
kernel=$(cat "${OUT_DIR}/kernel/kernelrelease" 2>/dev/null || echo "?")
short=${GITHUB_SHA:0:7}

# 1. package repository ------------------------------------------------------------------
if compgen -G "${OUT_DIR}/repo/*.pkg.tar.*" >/dev/null; then
  cat >"${notes}" <<TXT
Репозиторий pacman **[mangmi]** — пакеты Mangmi Clean Linux (ядро, поддержка железа, эмуляторы).
Устройства получают их командой \`mangmi-update\` (или пунктом *System Update* в ES-DE).

pacman repository [mangmi] used by Mangmi Clean Linux devices. Updated automatically by CI.

Commit: ${short} · kernel ${kernel}
TXT
  echo "== repository"
  id=$(release_id repo "Package repository [mangmi]" true "${notes}")
  mapfile -t pk < <(find "${OUT_DIR}/repo" -maxdepth 1 -type f -name '*.pkg.tar.*' | sort)
  replace_assets "${id}" "${pk[@]}" "${OUT_DIR}/repo/mangmi.db.tar.gz" "${OUT_DIR}/repo/mangmi.files.tar.gz"
fi

# 2. image ----------------------------------------------------------------------------------
mapfile -t img < <(find "${OUT_DIR}/images" -maxdepth 1 -type f 2>/dev/null | sort)
((${#img[@]})) || { echo "no images"; exit 0; }
if [[ ${GITHUB_REF:-} == refs/tags/v* ]]; then
  tag=${GITHUB_REF#refs/tags/}; title="Mangmi Clean Linux ${tag}"; pre=false
else
  tag=nightly; title="Mangmi Clean Linux — nightly (${short})"; pre=true
  # move the nightly tag to this commit
  gh_api -X PATCH "${api}/git/refs/tags/nightly" -d "{\"sha\":\"${GITHUB_SHA}\",\"force\":true}" >/dev/null 2>&1 \
    || gh_api -X POST "${api}/git/refs" -d "{\"ref\":\"refs/tags/nightly\",\"sha\":\"${GITHUB_SHA}\"}" >/dev/null
fi
cat >"${notes}" <<TXT
**Mangmi Clean Linux** для Mangmi Air X (MQ65 / MQ66 / MQ66B) · commit ${short} · Linux ${kernel}

1. Один раз установите OpenABL — [docs/INSTALL.md](https://github.com/${GITHUB_REPOSITORY}/blob/main/docs/INSTALL.md).
2. Внутренняя память: распакуйте образ и в меню OpenABL (Громкость −) выполните
   \`fastboot flash userdata mangmi-clean-linux-…-full.img\` (стирает данные Android).
   microSD: запишите \`*.img.xz\` (balenaEtcher / Rufus / \`xzcat … | sudo dd of=/dev/sdX bs=4M\`).
3. OpenABL: Boot mode → Linux, Boot source → Auto, Start. Пользователь \`mangmi\`, пароль \`mangmi\`.

Install OpenABL once, then either \`fastboot flash userdata\` the decompressed image (internal eMMC)
or write the \`.img.xz\` to a microSD card (docs/INSTALL.md), boot.
Default login: mangmi / mangmi. Packages: \`*.packages.txt\`. Verify with \`sha256sum -c\`.
TXT
[[ ${pre} == true ]] && printf '\n> Nightly build from `main` — automatically built, not individually tested on hardware.\n' >>"${notes}"
echo "== release ${tag}"
id=$(release_id "${tag}" "${title}" "${pre}" "${notes}")
replace_assets "${id}" "${img[@]}"
echo "published: https://github.com/${GITHUB_REPOSITORY}/releases/tag/${tag}"
