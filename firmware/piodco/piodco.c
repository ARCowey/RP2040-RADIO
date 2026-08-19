#include "piodco.h"
#include "dco2.pio.h"
#include <string.h>

static volatile int32_t precise_cycles_q24;

int piodco_init(PioDco *dco, int gpio, uint32_t cpu_clock_hz) {
    if (!dco || cpu_clock_hz == 0) return -1;
    memset(dco, 0, sizeof(*dco));
    dco->pio = pio0;
    dco->gpio = gpio;
    dco->clkfreq_hz = cpu_clock_hz;
    dco->offset = pio_add_program(dco->pio, &dco_program);
    dco->sm = pio_claim_unused_sm(dco->pio, true);
    dco_program_init(dco->pio, dco->sm, dco->offset, gpio);
    pio_sm_set_enabled(dco->pio, dco->sm, false);
    return 0;
}

int piodco_set_frequency(PioDco *dco, uint32_t hz, int32_t millihz) {
    if (!dco || hz == 0) return -1;
    const int64_t denominator = 2000LL * (int64_t)hz + (int64_t)millihz;
    const int64_t scaled = ((int64_t)dco->clkfreq_hz * (1LL << 24) * 1000LL + (denominator >> 1)) / denominator;
    precise_cycles_q24 = (int32_t)scaled - (PIODCO_DELAY_CYCLES << 24);
    return 0;
}

void piodco_start(PioDco *dco) {
    pio_sm_set_enabled(dco->pio, dco->sm, true);
}

void piodco_stop(PioDco *dco) {
    pio_sm_set_enabled(dco->pio, dco->sm, false);
}

void __not_in_flash_func(piodco_worker)(PioDco *dco) {
    int32_t accumulated_error = 0;
    for (;;) {
        int32_t reg = precise_cycles_q24;
        uint32_t whole_cycles = (uint32_t)((reg - accumulated_error) >> 24);
        pio_sm_put_blocking(dco->pio, dco->sm, whole_cycles);
        accumulated_error += ((int32_t)(whole_cycles << 24)) - reg;
    }
}
