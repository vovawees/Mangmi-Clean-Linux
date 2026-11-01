# Сборка из исходников

Вся сборка — один скрипт `build.sh`. Внутри он разворачивает чистое окружение Arch Linux ARM (chroot),
собирает ядро и пакеты, ставит систему в отдельный каталог и упаковывает образ для microSD.
Все внешние источники зафиксированы по версии и sha256/коммиту в [`config/build.conf`](../config/build.conf).

## Требования

- Linux-хост **aarch64** (быстро) или **x86_64** с `qemu-user-static` + binfmt (медленно, но работает).
- `bash`, `curl`, `git`, `bsdtar` (libarchive-tools), `sudo`, ~30 ГБ свободного места, 4+ ГБ ОЗУ.

## Шаги

```sh
git clone https://github.com/vovawees/Mangmi-Clean-Linux.git && cd Mangmi-Clean-Linux
./build.sh chroot      # окружение Arch Linux ARM (work/chroot)
./build.sh kernel      # ядро linux-mangmi            -> out/kernel
./build.sh packages    # все пакеты (ядро, прошивки, mangmi-*, эмуляторы) -> out/repo
./build.sh rootfs      # система                      -> work/stage/target
./build.sh image       # образ                         -> out/images/*.img.xz (+ .sha256)
# или всё сразу:
./build.sh all
```

Полезное:

| Команда / переменная | Что делает |
|---|---|
| `./build.sh packages mangmi es-de-bin` | пересобрать только указанные пакеты (остальные — по хэшу исходников) |
| `./build.sh dtbs` | только device tree (любой хост, ~1 мин) — быстрая проверка патчей |
| `./build.sh shell` | shell внутри окружения сборки |
| `IMAGE_FLAVOUR=console` | образ без рабочего стола (только игровой режим) |
| `DEFAULT_MODEL=mq66` | ревизия платы по умолчанию (`mq65` \| `mq66` \| `mq66b` \| `auto`) |
| `IMAGE_COMPRESS=none` | не сжимать образ (`.img`) |
| `JOBS=N`, `USE_CCACHE=1` | потоки сборки, ccache для ядра |
| `WORK_DIR`, `OUT_DIR`, `CACHE_DIR` | каталоги (по умолчанию `work/`, `out/`, `cache/`) |
| `config/local.conf` | локальные переопределения любых переменных из `build.conf` |

### Быстрая сборка ядра на x86_64 (кросс-компиляция)

Под qemu ядро собирается часами; с кросс-компилятором — минуты:

```sh
CROSS_COMPILE=aarch64-linux-gnu- ./scripts/build-kernel.sh   # результат в out/kernel
./build.sh packages                                           # упакует готовое ядро
```

## GitHub Actions

[`.github/workflows/build.yml`](../.github/workflows/build.yml): проверки (shellcheck, юнит-тесты,
тесты загрузочных записей, сборка DTB) → ядро на `ubuntu-24.04-arm` → пакеты, rootfs и образ.
Результат публикуется автоматически:

- **`nightly`** (pre-release) — свежий образ из `main`; тег `v*` создаёт обычный релиз;
- **`repo`** (pre-release) — pacman-репозиторий `[mangmi]`, из которого установленные системы получают
  обновления ядра, инструментов и эмуляторов (`mangmi-update`).

Ручной запуск: Actions → *build* → *Run workflow* (параметры: `flavour`, `publish`, `kernel_from_run`).

> Если задания не стартуют с сообщением *«The job was not started because your account is locked due to a
> billing issue»* — это ограничение аккаунта GitHub (Settings → Billing and plans), а не ошибка проекта.
> Для публичных репозиториев стандартные раннеры бесплатны, но аккаунт должен быть разблокирован.

## Структура

| Путь | Что там |
|---|---|
| `kernel/` | фрагменты конфигурации ядра (`mangmi.config`, `sched-ext.config`) |
| `scripts/` | сборка: окружение, ядро, пакеты, rootfs, образ, публикация |
| `packages/` | PKGBUILD: ядро, прошивки, Qualcomm-службы (qrtr, rmtfs, pd-mapper, tqftpserv), mangmi-*, эмуляторы |
| `mangmi/` | Python-демоны железа: `mangmi-hwd` (подсветка, вентилятор, профили, IRQ), `mangmi-hotkeyd`, `mangmi-ctl` + тесты |
| `system/` | файлы системы по пакетам: `tools` (службы, udev, sysctl, звук, InputPlumber), `session` (режимы), `emulators` |
| `config/packages/*.list` | состав образа: `base`, `console`, `emulators`, `desktop` |
| `overlay/esp/` | файлы загрузочного раздела (`mangmi-setup.txt`, скрипты OpenABL) |
| `tests/` | тесты генератора загрузочных записей |

## Тесты

```sh
(cd mangmi && python3 -m unittest discover -s tests -v)
bash tests/boot-update.sh
shellcheck -S warning build.sh scripts/*.sh scripts/chroot/*.sh
```
