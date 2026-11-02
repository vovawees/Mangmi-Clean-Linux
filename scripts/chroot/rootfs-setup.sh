#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-or-later
# (inside the target root file system) System configuration of the image.
# Environment comes from scripts/chroot/rootfs.sh.
set -Eeuo pipefail
trap 'echo "rootfs-setup: failed at line $LINENO: $BASH_COMMAND" >&2' ERR
log() { echo "  rootfs: $*"; }

# --- locale, time, names -------------------------------------------------------------
for l in en_US.UTF-8 "${DEFAULT_LOCALE}"; do
  sed -i -E "s/^#[[:space:]]*(${l//./\\.} UTF-8)/\1/" /etc/locale.gen
done
locale-gen >/dev/null
echo "LANG=${DEFAULT_LOCALE}" >/etc/locale.conf
ln -sf "/usr/share/zoneinfo/${DEFAULT_TIMEZONE}" /etc/localtime
echo "${DEFAULT_HOSTNAME}" >/etc/hostname
cat >/etc/hosts <<EOT
127.0.0.1   localhost
::1         localhost
127.0.1.1   ${DEFAULT_HOSTNAME}
EOT
printf 'KEYMAP=us\nFONT=ter-v32n\n' >/etc/vconsole.conf

rm -f /etc/os-release
cat >/etc/os-release <<EOT
NAME="${DISTRO_NAME}"
PRETTY_NAME="${DISTRO_NAME} ${DISTRO_VERSION}"
ID=${DISTRO_ID}
ID_LIKE=arch
VERSION_ID=${DISTRO_VERSION}
BUILD_ID=${BUILD_ID}
VARIANT_ID=${FLAVOUR}
IMAGE_VERSION=${GIT_COMMIT}
ANSI_COLOR="38;2;23;147;209"
LOGO=archlinux-logo
HOME_URL="https://github.com/vovawees/Mangmi-Clean-Linux"
DOCUMENTATION_URL="https://github.com/vovawees/Mangmi-Clean-Linux/tree/main/docs"
SUPPORT_URL="https://github.com/vovawees/Mangmi-Clean-Linux/issues"
BUG_REPORT_URL="https://github.com/vovawees/Mangmi-Clean-Linux/issues"
EOT
printf '%s %s (\\l)\n\n' "${DISTRO_NAME}" "${DISTRO_VERSION}" >/etc/issue

# --- pacman: [mangmi] repository, slim installs ---------------------------------------------
pc=/etc/pacman.conf
sed -i -E -e 's/^#?ParallelDownloads.*/ParallelDownloads = 5/' -e 's/^#?Color$/Color/' "$pc"
awk -v ne="$(cat /root/noextract.conf)" '{print} /^\[options\]/{print ne; print "NoUpgrade   = etc/os-release"}' \
  "$pc" >"$pc.new" && mv "$pc.new" "$pc"
if [[ -n ${MANGMI_REPO_URL} ]]; then
  sed -i "/^\[core\]/i # Mangmi Clean Linux packages (kernel, device support, emulators)\n[mangmi]\nSigLevel = Never\nServer = ${MANGMI_REPO_URL}\n" "$pc"
fi
echo 'Server = http://mirror.archlinuxarm.org/$arch/$repo' >/etc/pacman.d/mirrorlist

# --- user ------------------------------------------------------------------------------------------
useradd -m -u 1000 -U -G wheel,video,audio,input,render -s /bin/bash "${DEFAULT_USER}"
echo "${DEFAULT_USER}:${DEFAULT_PASSWORD}" | chpasswd
passwd -q -l root
printf '%%wheel ALL=(ALL:ALL) ALL\n' >/etc/sudoers.d/10-wheel
chmod 0440 /etc/sudoers.d/10-wheel

# --- services ------------------------------------------------------------------------------------
systemctl preset-all >/dev/null 2>&1
systemctl --global preset-all >/dev/null 2>&1
systemctl disable getty@tty1.service >/dev/null 2>&1 || :
systemctl enable "mangmi-session@${DEFAULT_USER}.service"
systemctl set-default graphical.target
# NetworkManager drives Wi-Fi through iwd (faster scans and reconnects, the
# same stack ROCKNIX uses on this chip).
mkdir -p /etc/NetworkManager/conf.d
printf '[device]\nwifi.backend=iwd\n' >/etc/NetworkManager/conf.d/10-iwd.conf
systemctl enable iwd.service >/dev/null 2>&1

# --- storage and boot ----------------------------------------------------------------------------
cat >/etc/fstab <<EOT
# <file system>              <dir>  <type> <options>                                         <dump> <pass>
PARTUUID=${ROOT_PARTUUID}  /      ext4   rw,noatime,commit=30                               0      0
PARTUUID=${ESP_PARTUUID}  /boot  vfat   rw,noatime,fmask=0022,dmask=0022,utf8,errors=remount-ro,noauto,x-systemd.automount,x-systemd.idle-timeout=60  0  2
EOT
mkdir -p /etc/kernel
cat >/etc/kernel/cmdline <<EOT
root=PARTUUID=${ROOT_PARTUUID} rw rootwait rootfstype=ext4 quiet loglevel=3 video=efifb:off console=tty0 gpt ssbd=force-off kpti=off mitigations=off cgroup.memory=nokmem,nosocket nowatchdog vt.global_cursor_default=0 systemd.show_status=auto udev.log_level=3
EOT
# the initramfs records the root file system's UUID too (image.sh formats it
# with this UUID), so that it finds this system whatever root= it is given
export MANGMI_ROOT_FSUUID=${ROOT_FSUUID}
if [[ ${DEFAULT_MODEL:-auto} != auto ]]; then
  mangmi-boot-update --model "${DEFAULT_MODEL}"
else
  mangmi-boot-update
fi
install -Dm644 /dev/stdin /boot/mangmi-version.txt <<EOT
${DISTRO_NAME} ${DISTRO_VERSION} (${FLAVOUR}, build ${BUILD_ID}, ${GIT_COMMIT})
EOT

log "configured: user ${DEFAULT_USER}, locale ${DEFAULT_LOCALE}, model ${DEFAULT_MODEL:-auto}"
