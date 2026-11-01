# FAQ

**Android удалится?**
Нет. Linux живёт на microSD. Меняется только загрузчик (на OpenABL), и Android грузится как раньше:
выньте карту или держите «Громкость +» при включении. Загрузчик можно вернуть — см. [INSTALL.md](INSTALL.md).

**Чёрный экран после загрузки.**
Почти всегда выбрана не та ревизия платы. В меню OpenABL (держать «Громкость −») → *Boot entries* →
*Mangmi Clean Linux (MQ66 board)* / *(MQ66B board)*, затем закрепите выбор: `MODEL=` в `mangmi-setup.txt`
или `sudo mangmi-boot-update --model mq66`.

**Как понять, что вообще происходит при загрузке?**
*Boot entries* → *safe mode* — текстовая консоль с логом (вход `mangmi`/`mangmi`), или в меню OpenABL
*ABL mode → Verbose*. Логи: `journalctl -b`, служба железа: `journalctl -u mangmi-hwd`.

**Нет звука / Wi-Fi / Bluetooth.**
Нужны прошивки и службы Qualcomm (`rmtfs`, `pd-mapper`, `tqftpserv`) — они в образе и включены.
Проверьте `systemctl status rmtfs pd-mapper tqftpserv` и `dmesg | grep -i remoteproc`. DSP стартует
через несколько секунд после загрузки — звук и Wi-Fi появляются чуть позже интерфейса, это нормально.

**Игра не запускается из ES-DE.**
1) BIOS: положите файлы в `~/BIOS` (PS1 — `scph5501.bin` и т.д., PS2 — BIOS вашей консоли, Sega CD, Saturn, NDS — по желанию).
2) Эмулятор: ES-DE → меню системы → *Alternative emulators* — попробуйте другой.
3) Лог: `~/ES-DE/logs/es_log.txt`.

**Где сохранения?**
RetroArch: `~/.config/retroarch/saves` и `states`; отдельные эмуляторы — в их каталогах в `~/.config`
и `~/.local/share`. Скриншоты — `~/Pictures`.

**Как обновиться?**
ES-DE → *Mangmi Air X* → *System Update*, или `mangmi-update`. Обновляются Arch Linux ARM, ядро,
эмуляторы, ядра RetroArch и Flatpak-приложения.

**Можно ставить свои программы?**
Да: `sudo pacman -S …` (репозитории Arch Linux ARM), Flatpak/Discover в режиме «ПК»,
AppImage для aarch64.

**Почему не Steam / Windows-игры?**
Это ARM-устройство. Через FEX/Box64 + Wine теоретически можно, но на Snapdragon 662 смысла почти нет.
Steam Link (стриминг с ПК) работает через Flatpak.

**Установка на внутреннюю память?**
Пока нет — только microSD. Это безопаснее, а скорость A2-карт для эмуляции достаточна.

**Это официальная прошивка Mangmi?**
Нет, это независимый открытый проект на базе Arch Linux ARM, наработок ROCKNIX и OpenABL.

**Нужен другой язык интерфейса?**
Ради места ставятся не все переводы (список — в [PERFORMANCE.md](PERFORMANCE.md)). Чтобы добавить,
например, шведский: допишите `!usr/share/locale/sv/*` в конец строки `NoExtract = usr/share/locale/*`
в `/etc/pacman.conf` и переустановите пакеты с переводами:
`sudo pacman -S $(pacman -Qoq /usr/share/locale)`.
