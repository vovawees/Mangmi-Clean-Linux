# Эмуляторы и системы

Игры запускаются из **ES-DE**; для каждой системы уже выбран самый быстрый на Snapdragon 662 эмулятор,
и все они **предустановлены** — ничего докачивать и настраивать не нужно. Поменять эмулятор:
ES-DE → *Настройки* → *Other settings* → *Alternative emulators* (для системы) или *Edit this game's
metadata* → *Alternative emulator* (для одной игры).

- Игры: **`~/ROMs/<папка>/`** — папки для всех систем ниже создаются автоматически.
- BIOS: **`~/BIOS/`** — одна папка для RetroArch, DuckStation и ARMSX2.
- Сохранения RetroArch: `~/.config/retroarch/saves`, `states`; скриншоты — `~/Pictures`.

## Nintendo

| Система | Папка | По умолчанию | Также установлены |
|---|---|---|---|
| NES / Famicom / FDS | `nes` | Mesen | Nestopia UE, FCEUmm |
| SNES / Super Famicom | `snes` | Snes9x | Mesen-S |
| Game Boy / Color | `gb`, `gbc` | Gambatte | SameBoy, mGBA, Mesen-S |
| Game Boy Advance | `gba` | mGBA | gpSP (быстрее, менее точный) |
| Nintendo DS | `nds` | melonDS DS (JIT) | melonDS (отдельный) |
| Nintendo 3DS | `n3ds` | Citra | — (только лёгкие игры) |
| Nintendo 64 | `n64` | Mupen64Plus-Next | ParaLLEl N64 |
| GameCube / Wii | `gc`, `wii` | Dolphin | — (лёгкие игры, профиль `max`) |
| Virtual Boy | `virtualboy` | Beetle VB | |
| Pokémon Mini | `pokemini` | PokeMini | |

## Sony

| Система | Папка | По умолчанию | Также установлены |
|---|---|---|---|
| PlayStation | `psx` | PCSX ReARMed | DuckStation (отдельный, Vulkan, апскейл), SwanStation |
| PlayStation 2 | `ps2` | ARMSX2 (PCSX2 для ARM64) | |
| PSP | `psp` | PPSSPP | PPSSPP (отдельный) |

## Sega

| Система | Папка | По умолчанию | Также установлены |
|---|---|---|---|
| SG-1000 / Master System / Game Gear | `sg-1000`, `mastersystem`, `gamegear` | Genesis Plus GX | Gearsystem, PicoDrive |
| Mega Drive / Genesis | `megadrive`, `genesis` | Genesis Plus GX | PicoDrive |
| Mega-CD / Sega CD | `megacd`, `segacd` | Genesis Plus GX | PicoDrive |
| 32X | `sega32x` | PicoDrive | |
| Saturn | `saturn` | YabaSanshiro | |
| Dreamcast / NAOMI | `dreamcast`, `naomi` | Flycast | |

## Аркады и SNK

| Система | Папка | По умолчанию | Также установлены |
|---|---|---|---|
| Аркады | `arcade`, `fbneo` | FinalBurn Neo | MAME 2003-Plus, Flycast (NAOMI/Atomiswave) |
| MAME | `mame` | MAME 2003-Plus (романсет 0.78) | FinalBurn Neo |
| Neo Geo | `neogeo` | FinalBurn Neo | |
| Neo Geo CD | `neogeocd` | NeoCD | FinalBurn Neo |
| Neo Geo Pocket / Color | `ngp`, `ngpc` | Beetle NeoPop | |

## Остальные консоли

| Система | Папка | Эмулятор |
|---|---|---|
| PC Engine / TurboGrafx (+CD) | `pcengine`, `pcenginecd` | Beetle PCE FAST (+ Beetle SuperGrafx) |
| WonderSwan / Color | `wonderswan`, `wonderswancolor` | Beetle Cygne |
| Atari 2600 / 5200 / 7800 | `atari2600`, `atari5200`, `atari7800` | Stella / Atari800 / ProSystem |
| Atari Lynx / Jaguar | `atarilynx`, `atarijaguar` | Handy / Virtual Jaguar |
| 3DO | `3do` | Opera |
| ColecoVision | `colecovision` | blueMSX |
| Intellivision | `intellivision` | FreeIntv |
| Vectrex | `vectrex` | vecx |
| Magnavox Odyssey 2 | `odyssey2` | O2EM |
| TIC-80 | `tic80` | TIC-80 |

## Компьютеры

| Система | Папка | Эмулятор |
|---|---|---|
| DOS | `dos` | DOSBox Pure (игры можно класть zip-архивом) |
| ScummVM | `scummvm` | ScummVM |
| Amiga | `amiga` | PUAE |
| Commodore 64 | `c64` | VICE x64sc |
| ZX Spectrum | `zxspectrum` | Fuse |
| Amstrad CPC | `amstradcpc` | Caprice32 |
| Atari 800 | `atari800` | Atari800 |
| MSX / MSX2 | `msx`, `msx2` | blueMSX |

`ports` — для своих скриптов и нативных игр (`.sh`, `.AppImage`).

## BIOS

Некоторым системам нужны файлы BIOS из **вашей** консоли (в образ они не входят). Кладите в `~/BIOS`:

| Система | Файлы |
|---|---|
| PlayStation | `scph5500.bin`, `scph5501.bin`, `scph5502.bin` (PCSX ReARMed работает и без них, но хуже совместимость) |
| PlayStation 2 | любой дамп BIOS PS2 (`*.bin`) |
| Sega CD / Mega-CD | `bios_CD_U.bin`, `bios_CD_E.bin`, `bios_CD_J.bin` |
| Saturn | `saturn_bios.bin` |
| Dreamcast / NAOMI | `dc/dc_boot.bin`, `dc/naomi.zip` |
| PC Engine CD | `syscard3.pce` |
| Neo Geo | `neogeo.zip` (в папку с играми или в `~/BIOS`) |
| Neo Geo CD | `neocd/neocd.bin` (или `neocd_z.rom` …) |
| 3DO | `panafz10.bin` |
| Nintendo DS | не обязателен (встроенный FreeBIOS) |
| Atari 5200 / 7800 / Lynx | `5200.rom`, `7800 BIOS (U).rom`, `lynxboot.img` |
| Amiga | `kick34005.A500`, `kick40068.A1200` |
| MSX / ColecoVision | `Machines/` и `Databases/` из пакета blueMSX |

Полный список имён — в [документации libretro](https://docs.libretro.com/) для соответствующего ядра.

## Отдельные эмуляторы

| Эмулятор | Зачем | Версия |
|---|---|---|
| **DuckStation** | PS1: точность, Vulkan (Turnip), апскейл, PGXP | AppImage aarch64, фиксированная версия |
| **ARMSX2** | PS2 (форк PCSX2 под ARM64 с JIT) | AppImage aarch64 (4K-страницы) |
| **PPSSPP** | PSP с Vulkan, лучше ядра в тяжёлых играх | пакет Arch Linux ARM |
| **melonDS** | DS с JIT и удобной раскладкой экранов | AppImage aarch64 |
| **RetroArch** | всё остальное (ядра libretro) | пакет Arch Linux ARM + ядра buildbot |

Все запускаются через `mangmi-run` (профиль производительности, большие ядра, `games.slice`) и
обновляются вместе с системой (`mangmi-update`).
