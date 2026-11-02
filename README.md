# Mangmi Clean Linux

**Чистый, быстрый и полностью свободный Linux для портативной консоли Mangmi Air X (MQ65 / MQ66 / MQ66B).**
Гибрид «консоль + ПК»: включаете — попадаете в игровой интерфейс (ES-DE) с настроенными эмуляторами;
одна кнопка — и перед вами полноценный рабочий стол KDE Plasma с браузером, файловым менеджером и магазином приложений.

> English summary: a clean, speed-first Arch Linux ARM based OS for the Mangmi Air X (Snapdragon 662 / SM6115)
> handheld. Hybrid console (ES-DE + RetroArch + standalone emulators) and full desktop (KDE Plasma) modes,
> mainline 7.2 kernel with ROCKNIX device enablement, Mesa Freedreno/Turnip (OpenGL ES 3.2 / Vulkan),
> full hardware support (stick RGB LEDs, fan, rumble, audio, Wi-Fi, Bluetooth, battery, touchscreen).

## Возможности

| | |
|---|---|
| **Ядро** | Linux 7.2.y (mainline) + патчи ROCKNIX для SM6115 (панели, геймпад, звук, Wi-Fi, зарядка, разгон GPU до 1050 МГц) |
| **Графика** | Mesa Freedreno (OpenGL / GLES 3.2) и Turnip (Vulkan 1.3), Wayland |
| **Режим «Консоль»** | Sway-киоск + ES-DE на весь экран, RetroArch и отдельные эмуляторы, хоткеи как в ROCKNIX |
| **Режим «ПК»** | KDE Plasma 6 (Wayland), стики работают как мышь, экранная клавиатура, Discover/Flatpak |
| **Железо** | RGB-подсветка стиков (эффекты, индикация заряда), вентилятор (авто/тихий/макс), вибрация, профили производительности CPU/GPU |
| **Скорость** | крошечный initramfs (1,5 МБ, busybox), zram (lz4), MGLRU, BFQ, PREEMPT + 1000 Гц, привязка прерываний к ядрам A53, большие ядра A73 для тяжёлых эмуляторов, авто-профиль под каждую систему |
| **Эмуляторы** | 55+ систем из коробки в одном RetroArch (40+ ядер, простое меню на русском) — у каждой системы уже выбран самый быстрый эмулятор; PS2 (ARMSX2), DuckStation, melonDS, PPSSPP, Dolphin ставятся одной кнопкой |
| **Магазин игр** | Game Store для геймпада: ~1100 бесплатных homebrew-игр GB/GBC/GBA, бесплатные квесты ScummVM, ROM со своего ПК/NAS по сети — в один клик; настройка Wi-Fi прямо в режиме «Консоль» |
| **Обновления** | `mangmi-update` — система (pacman), ядро, эмуляторы и ядра RetroArch одним действием (свой репозиторий `[mangmi]`) |

## Статус

Проект в активной разработке. Сборка образа полностью автоматизирована (`build.sh`, GitHub Actions),
аппаратная часть основана на проверенной работе проекта [ROCKNIX](https://rocknix.org) для SM6115.
⚠️ На реальной консоли образ ещё не проверялся — отчёты в [Issues](../../issues) очень помогут.

## Быстрый старт

1. Скачайте образ `mangmi-clean-linux-*.img.xz` последнего выпуска со страницы [Releases](../../releases/latest)
   (сборка ветки разработки — релиз **nightly**).
2. Один раз установите загрузчик **OpenABL** (вместо стокового ABL) — см. [docs/INSTALL.md](docs/INSTALL.md).
3. Установите систему:
   - **во внутреннюю память (eMMC)**: распакуйте `.img.xz`, включите консоль с зажатой **Громкостью −** (меню OpenABL)
     и выполните `fastboot flash userdata mangmi-clean-linux-…-full.img` (⚠️ стирает данные Android);
   - **или на microSD** (Android остаётся): balenaEtcher, Rufus или `xzcat образ.img.xz | sudo dd of=/dev/sdX bs=4M status=progress`.
4. В меню OpenABL выберите *Boot mode → Linux*, *Boot source → Auto* и *Start*. Вход: `mangmi` / `mangmi`.

Подробности: [установка](docs/INSTALL.md) · [режимы](docs/MODES.md) · [горячие клавиши](docs/HOTKEYS.md) ·
[эмуляторы](docs/EMULATORS.md) · [производительность](docs/PERFORMANCE.md) · [железо](docs/HARDWARE.md) ·
[сборка из исходников](docs/BUILD.md) · [FAQ](docs/FAQ.md)

## Сборка

```sh
git clone https://github.com/vovawees/Mangmi-Clean-Linux.git
cd Mangmi-Clean-Linux
./build.sh all             # ядро + пакеты + rootfs + образ (aarch64-хост, x86_64 + qemu или CI)
```

Все внешние источники зафиксированы по версии и sha256/коммиту в [`config/build.conf`](config/build.conf).

## Лицензия и благодарности

Код проекта — GPL-2.0-or-later (см. [LICENSE](LICENSE)). Поддержка железа взята из
[ROCKNIX](https://github.com/ROCKNIX/distribution) (GPL-2.0), загрузчик — [OpenABL](https://github.com/OpenHandheldCollective/OpenABL) (GPL-3.0).
Проприетарные прошивки (GPU zap-shader, DSP, Wi-Fi) не хранятся в репозитории — они скачиваются во время сборки.
Полный список — в [CREDITS.md](CREDITS.md).
