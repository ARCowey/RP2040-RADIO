#pragma once

#include <stdint.h>
#include "pico/stdlib.h"
#include "hardware/pio.h"

typedef struct {
    PIO pio;
    uint sm;
    uint offset;
    pio_sm_config sm_config;
    int gpio;
    uint32_t clkfreq_hz;
} PioDco;

int piodco_init(PioDco *dco, int gpio, uint32_t cpu_clock_hz);
int piodco_set_frequency(PioDco *dco, uint32_t hz, int32_t millihz);
void piodco_start(PioDco *dco);
void piodco_stop(PioDco *dco);
void __not_in_flash_func(piodco_worker)(PioDco *dco);
