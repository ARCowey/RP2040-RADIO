# RP2040-RADIO

Firmware experimental para **Waveshare RP2040-Zero** que recibe audio por USB y genera una señal FM para pruebas de laboratorio.

## Objetivo de esta rama

- Salida RF digital por **GP6**.
- Centro de recepción objetivo: **90.000 MHz**.
- La fundamental PIO se genera alrededor de **30 MHz** y se utiliza su **tercer armónico** para llegar a la banda de FM.
- El dispositivo se presenta al PC como dispositivo de audio USB.
- GitHub Actions genera `RP2040-Zero-GP6-90MHz-USB-Audio.uf2` automáticamente.

La rama `gp6-usb-fm` es la rama de validación del firmware y dispara el workflow de compilación en cada actualización.

## Seguridad RF

No conectes una antena ni un cable largo directamente a GP6. La salida digital contiene armónicos y espurias. Para cualquier uso radiado se necesita filtrado RF apropiado y cumplir la normativa local.

## Origen técnico

La implementación combina el ejemplo USB Sound Card/FM de `kaduhi/pico-playground` y `kaduhi/pico-extras` con un DCO PIO simplificado derivado de `RPiks/pico-hf-oscillator` (MIT).
