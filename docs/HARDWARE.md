# Железо Mangmi Air X и как оно поддерживается

| Компонент | Чип / интерфейс | Драйвер / путь в системе | Статус |
|---|---|---|---|
| SoC | Qualcomm Snapdragon 662 (SM6115): 4× Cortex-A73 до 2,0 ГГц (cpu4–7) + 4× Cortex-A53 1,8 ГГц (cpu0–3) | `cpufreq` policy0 / policy4, EAS + schedutil | ✅ |
| GPU | Adreno 610, до **1050 МГц** (патч ROCKNIX) | `msm` DRM, Mesa Freedreno (GL/GLES) + Turnip (Vulkan), devfreq `/sys/devices/platform/soc@0/5900000.gpu/devfreq/5900000.gpu` | ✅ |
| Память | 4 ГБ LPDDR4X | zram (lz4) ≈ 100 % RAM, MGLRU | ✅ |
| Накопители | eMMC 64 ГБ, microSD (SDR104) | `sdhci-msm`, планировщик BFQ; установка в `userdata` — образ подключается initramfs через `loop` (direct I/O, без TRIM) | ✅ |
| Экран | 5,5" 1920×1080 IPS (портретная матрица, поворот 270°), сенсор | панели `mangmi,td4310` (MQ65), `mangmi,hx83112a` (MQ66), `mangmi,bm5460bb1` (MQ66B); сенсор MQ66 — Himax (SPI), MQ65 — Synaptics RMI4 (I²C 0x20, 🧪 экспериментально) | ✅ / 🧪 |
| Подсветка | PWM PM6125 | `/sys/class/backlight/*` | ✅ |
| Геймпад | MCU на UART0 | `rocknix,mangmi-air-x-joypad` → evdev **MANGMI Air X Joypad** (кнопки, крестовина, 2 стика, аналоговые триггеры) → InputPlumber (виртуальный DualSense + клавиатура + мышь) | ✅ |
| RGB стиков | 2× Awinic AW20036 (I²C 0x3a/0x3b), 18 RGB-зон | `/sys/class/leds/rgb:l1…l9`, `rgb:r1…r9` (`multi_intensity`, `brightness`) → `mangmi-hwd` | ✅ |
| Вентилятор | GPIO (вкл/выкл) | `gpio-fan` как cooling device для термозон cpu/gpu/battery → `mangmi-hwd` (режимы auto/quiet/max) | ✅ |
| Вибрация | PWM | `pwm-vibrator` (force-feedback через InputPlumber) | ✅ |
| Звук | ES8326 + 2× AW88261 | ASoC `MangmiAirX` + UCM-профили ROCKNIX, PipeWire/WirePlumber | ✅ |
| Wi-Fi / BT | WCN3990-совместимый (Wi-Fi 5, BT 5) | `ath10k_snoc`, `hci_uart` (qca); нужны `qrtr`, `pd-mapper`, `rmtfs`, `tqftpserv` | ✅ |
| Батарея / зарядка | CW221x, SGM41515, FUSB302 (USB-C PD) | `/sys/class/power_supply/battery` | ✅ |
| Громкость | GPIO-кнопки | `gpio-keys` | ✅ |
| Видеовыход | — | у устройства нет видеовыхода | — |

## Модели

| Модель | Панель | Device tree |
|---|---|---|
| MQ65 | TD4310 | `qcom/sm6115-mangmi-air-x-mq65.dtb` |
| MQ66 | Himax HX83112A | `qcom/sm6115-mangmi-air-x-mq66.dtb` |
| MQ66B | BM5460BB1 | `qcom/sm6115-mangmi-air-x-mq66b.dtb` |

Неправильный DTB = чёрный экран (неверная панель). Пункты загрузки для всех трёх моделей есть в меню OpenABL.

**MQ65:** в device tree ROCKNIX для всех моделей включён SPI-сенсор Himax, но на MQ65 этот блок QUP
работает как I²C, отсюда ошибка `geni_spi 4a88000.spi: Invalid proto 3` при загрузке. Mangmi Clean Linux
отключает SPI на MQ65 (`kernel/dts/qcom/sm6115-mangmi-air-x-mq65-fixes.dtsi`) и пробует сенсор TD4310 как
Synaptics RMI4 на I²C. Если сенсор не работает, пришлите вывод `dmesg | grep -i -e rmi4 -e i2c` в issue.

## Термозоны (из device tree)

`cpu0123-thermal`, `cpu45-thermal`, `cpu67-thermal`, `gpu-thermal`, `battery` — вентилятор привязан к ним
через trip-точки (CPU ≈ 70 °C с гистерезисом 10 °C). `mangmi-hwd` меняет эти точки в зависимости от режима вентилятора.

## Источник

Описание железа и вся поддержка устройства основаны на ROCKNIX (`projects/ROCKNIX/devices/SM6115`),
закреплённом коммитом в `config/build.conf`.
