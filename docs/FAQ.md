# FAQ

**Android удалится?**
При установке на microSD — нет: меняется только загрузчик (на OpenABL), Android грузится как раньше
(выньте карту или держите «Громкость +» при включении). При установке во внутреннюю память стираются
**данные** Android (раздел `userdata`), сам Android остаётся, но запускать его нельзя, пока установлен Linux.
Вернуть всё можно — см. [INSTALL.md](INSTALL.md).

**Загрузка из внутренней памяти зависает на сообщениях ядра (старые сборки).**
Сборки до 2 ноября 2026 не умели запускаться из раздела `userdata`: ядро не видит таблицу разделов
внутри раздела и бесконечно ждёт корневой раздел. Теперь это делает initramfs (`loop` + `--partscan`).
Запишите свежий nightly заново (`fastboot flash userdata …`). Если система всё равно не находит корень,
через 30 секунд появится список накопителей и аварийная консоль — пришлите фото экрана в issue.

**Висит на `waiting for the root file system (PARTUUID=…)` с чужим PARTUUID.**
Ядро получило командную строку не из загрузочной записи этого образа. С ноября 2026 initramfs не
доверяет ей вслепую: через секунду он ищет корень *своей* системы (PARTUUID и UUID записаны в
initramfs при сборке), через 5 секунд — раздел с меткой `MANGMI_ROOT`. Корень можно указать и явно
параметром ядра `mangmi.root=` (он важнее `root=`). Аварийный экран показывает командную строку ядра.

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

**Где взять игры? Как закинуть свои ROM без SFTP?**
ES-DE → *Mangmi Air X* → **Game Store**: бесплатные homebrew-игры Game Boy / Color / Advance и квесты
ScummVM скачиваются одной кнопкой. Свои дампы — с компьютера по Wi-Fi: в папке с играми на ПК выполните
`python -m http.server 8000` и добавьте в магазине папку `http://<IP-компьютера>:8000/`
(подробнее — [EMULATORS.md](EMULATORS.md#магазин-игр-game-store)). Wi-Fi настраивается там же.

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
Да: образ записывается в раздел `userdata` через fastboot из меню OpenABL — см. [INSTALL.md](INSTALL.md).
Ограничения: стираются данные Android, нет TRIM внутри образа.

**Это официальная прошивка Mangmi?**
Нет, это независимый открытый проект на базе Arch Linux ARM, наработок ROCKNIX и OpenABL.

**Где заголовки C/C++, статические библиотеки, документация?**
Ради места они не устанавливаются (`NoExtract` в `/etc/pacman.conf`). Для сборки программ на самой консоли
удалите строки с `usr/include`, `*.a` и `usr/lib/cmake` из `NoExtract` и переустановите нужные пакеты
(`sudo pacman -S glibc linux-api-headers …`).

**Нужен другой язык интерфейса?**
Ради места ставятся не все переводы (список — в [PERFORMANCE.md](PERFORMANCE.md)). Чтобы добавить,
например, шведский: допишите `!usr/share/locale/sv/*` в конец строки `NoExtract = usr/share/locale/*`
в `/etc/pacman.conf` и переустановите пакеты с переводами:
`sudo pacman -S $(pacman -Qoq /usr/share/locale)`.
