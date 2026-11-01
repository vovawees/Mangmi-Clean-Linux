# Установка

> ⚠️ Проект новый и пока **не проверен на реальной консоли** — только сборка, тесты и эмуляция.
> Установка на microSD ничего не стирает во внутренней памяти: Android остаётся, а если что-то
> не запустится, просто выньте карту. Единственный «системный» шаг — замена загрузчика на
> OpenABL (его можно откатить, см. ниже).

## Что понадобится

- Mangmi Air X: **MQ65**, MQ66 или MQ66B (ревизия написана на коробке / в «Об устройстве»).
- microSD от 16 ГБ, лучше 64 ГБ+ класса **A2 / U3** (от карты напрямую зависит скорость загрузки игр).
- Компьютер для записи образа.

## 1. Скачать и записать образ

1. Откройте [Releases](https://github.com/vovawees/Mangmi-Clean-Linux/releases) → **nightly**
   (или последнюю версию `v*`) и скачайте `mangmi-clean-linux-<версия>-full.img.xz` и файл `.sha256`.
   Если образ разбит на части (`….img.xz.part00`, `….part01`), склейте их:
   `cat mangmi-clean-linux-*.img.xz.part* > mangmi.img.xz` (Windows: `copy /b файл.part00+файл.part01 mangmi.img.xz`).
2. Запишите образ на карту:
   - **balenaEtcher** / **Rufus** / **Raspberry Pi Imager** — умеют `.img.xz` напрямую;
   - Linux/macOS: `xzcat mangmi.img.xz | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress`.
3. (Необязательно) Откройте на карте раздел **MANGMI_BOOT** и заполните `mangmi-setup.txt`:

   | Ключ | Что делает |
   |---|---|
   | `WIFI_SSID`, `WIFI_PASSWORD` | сеть Wi-Fi, к которой подключиться сразу |
   | `PASSWORD` | новый пароль пользователя `mangmi` (по умолчанию `mangmi`) |
   | `MODEL` | `mq65` (по умолчанию в образе), `mq66`, `mq66b` или `auto` (брать «Device model» из меню OpenABL) |
   | `TIMEZONE` | например `Europe/Moscow` (по умолчанию) |
   | `LOCALE` | например `ru_RU.UTF-8` (по умолчанию), `en_US.UTF-8` |
   | `HOSTNAME` | имя устройства в сети |
   | `SSH` | `yes` — включить SSH-сервер |

   Пароли стираются из файла сразу после применения.

## 2. Установить загрузчик OpenABL (один раз)

Стоковый загрузчик Qualcomm умеет запускать только Android. [OpenABL](https://github.com/OpenHandheldCollective/OpenABL) —
это тот же загрузчик с добавленным меню и загрузкой Linux (с microSD, USB или внутренней памяти);
Android продолжает работать как раньше. Это тот же способ, что использует [ROCKNIX](https://rocknix.org).
Все файлы уже лежат на карте в папке **`MANGMI_BOOT/openabl/`**.

Выберите **один** способ:

### Способ A — из Android с root-доступом (без компьютера)

1. Скопируйте папку `openabl` с карты во внутреннюю память (чтобы получилось `/sdcard/openabl/`).
2. В терминале Android (Termux, adb shell и т.п.):
   ```sh
   su -c sh /sdcard/openabl/backup_abl.sh   # сохраняет стоковый загрузчик (abl_a/abl_b-stock.img)
   su -c sh /sdcard/openabl/flash_abl.sh    # прошивает OpenABL в оба слота и проверяет запись
   ```
3. Скопируйте `abl_a-stock.img` и `abl_b-stock.img` на компьютер — это ваша страховка.

### Способ B — через fastboot (разблокированный загрузчик)

1. В Android включите «Параметры разработчика» → **Разблокировка OEM** и **Отладка по USB**.
2. На компьютере (Android platform-tools):
   ```sh
   adb reboot bootloader
   fastboot flashing unlock        # ⚠️ стирает данные Android! (если уже разблокирован — пропустите)
   fastboot flash abl_a abl_signed-SM6115.elf
   fastboot flash abl_b abl_signed-SM6115.elf
   fastboot reboot
   ```
   На некоторых прошивках для записи `abl` дополнительно нужна команда `fastboot flashing unlock_critical`.

### Способ C — из кастомного recovery

Установите `openabl-recovery-flashable-sm6115.zip` как обычный zip.

**Откат:** `su -c sh /sdcard/openabl/restore_abl.sh` (способ A) или `fastboot flash abl_a abl_a-stock.img` +
`fastboot flash abl_b abl_b-stock.img`. Также подойдёт стоковый `abl` из официальной прошивки Mangmi.

## 3. Первый запуск

1. Выключите консоль, вставьте карту.
2. Включите, **удерживая «Громкость −»** — откроется меню OpenABL
   (Громкость +/− — выбор, Power — подтвердить):
   - **Boot mode → Linux** (запоминается; потом консоль сама грузит Linux, если карта вставлена);
   - **Boot source → Auto** или **SD card**;
   - **Start**.
3. Первая загрузка занимает дольше обычного: раздел расширяется на всю карту, применяется `mangmi-setup.txt`.
   Затем открывается **ES-DE** (режим «Консоль»).

**MQ66 / MQ66B:** образ по умолчанию настроен на MQ65. Либо заранее впишите `MODEL=mq66` (или `mq66b`)
в `mangmi-setup.txt`, либо в меню OpenABL откройте **Boot entries** и выберите
*Mangmi Clean Linux (MQ66 board)* / *(MQ66B board)*. Если экран остался чёрным — почти наверняка выбрана
не та ревизия.

Другие пункты меню **Boot entries**: *safe mode* — текстовая консоль без графики (для диагностики).
Удержание **«Громкость +»** при включении запускает Android, даже если выбран режим Linux.

## Пользователь и пароль

- Пользователь **`mangmi`**, пароль **`mangmi`** (смените: `passwd` или `PASSWORD=` в `mangmi-setup.txt`).
- `sudo` работает для `mangmi`; вход под root отключён.

## Куда класть игры и BIOS

- Игры: `~/ROMs/<система>/` (папки уже созданы: `snes`, `psx`, `ps2`, `nds`, `n64`… — см. [EMULATORS.md](EMULATORS.md)).
- BIOS: `~/BIOS/` (общая папка для RetroArch, DuckStation и ARMSX2).
- Способы копирования: по Wi-Fi через SFTP (`SSH=yes` в `mangmi-setup.txt`, затем в WinSCP/FileZilla/Dolphin
  адрес `sftp://mangmi@<ip-консоли>`), с флешки в режиме «ПК» (файловый менеджер Dolphin),
  или прямо с карты на компьютере с Linux (раздел MANGMI_ROOT, папка `home/mangmi/ROMs`).

## Обновление системы

ES-DE → *Mangmi Air X* → **System Update**, «Обновление системы» в меню приложений режима «ПК» или `mangmi-update`
в терминале — обновляет пакеты Arch Linux ARM, ядро, эмуляторы и Flatpak-приложения.
