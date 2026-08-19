from pathlib import Path

root = Path(__file__).resolve().parents[1]
extras = Path("pico-extras")
playground = Path("pico-playground")

fm_dir = extras / "src/rp2_common/pico_audio_fm_transmitter"
(fm_dir / "piodco").mkdir(parents=True, exist_ok=True)
for name in ("piodco.h", "piodco.c", "dco2.pio"):
    (fm_dir / "piodco" / name).write_bytes((root / "firmware/piodco" / name).read_bytes())

cmake = fm_dir / "CMakeLists.txt"
s = cmake.read_text()
s = s.replace(
    "pico_generate_pio_header(pico_audio_fm_transmitter ${CMAKE_CURRENT_LIST_DIR}/audio_fm_transmitter.pio)",
    "pico_generate_pio_header(pico_audio_fm_transmitter ${CMAKE_CURRENT_LIST_DIR}/audio_fm_transmitter.pio)\n"
    "    pico_generate_pio_header(pico_audio_fm_transmitter ${CMAKE_CURRENT_LIST_DIR}/piodco/dco2.pio)"
)
s = s.replace(
    "${CMAKE_CURRENT_LIST_DIR}/sample_encoding.cpp\n            )",
    "${CMAKE_CURRENT_LIST_DIR}/sample_encoding.cpp\n            ${CMAKE_CURRENT_LIST_DIR}/piodco/piodco.c\n            )"
)
s = s.replace("    add_subdirectory(${CMAKE_CURRENT_LIST_DIR}/pico-fractional-pll)\n", "")
s = s.replace("            pico_multicore\n            pico_fractional_pll)", "            pico_multicore)")
cmake.write_text(s)

src = fm_dir / "audio_fm_transmitter.c"
s = src.read_text()
s = s.replace('#include "pico_fractional_pll.h"', '#include "piodco/piodco.h"')
s = s.replace(
    "static uint32_t g_transmit_freq_base_hz = 87900000;",
    "static uint32_t g_transmit_freq_base_hz = 89992500;\n"
    "static PioDco g_gp6_dco;\n"
    "static void gp6_dco_core1(void) { piodco_worker(&g_gp6_dco); }\n"
    "static inline void gp6_set_rf_hz(uint32_t rf_hz) {\n"
    "    uint32_t fundamental_hz = rf_hz / 3u;\n"
    "    int32_t fundamental_millihz = (int32_t)((rf_hz % 3u) * 1000u / 3u);\n"
    "    piodco_set_frequency(&g_gp6_dco, fundamental_hz, fundamental_millihz);\n"
    "}"
)
s = s.replace("        pico_fractional_pll_set_freq_u32(freq);", "        gp6_set_rf_hz(freq);")
old_init = '''            uint32_t freq_low = g_transmit_freq_base_hz;\n            uint32_t freq_high = g_transmit_freq_base_hz + FM_BANDWIDTH;\n            uint32_t freq_center = g_transmit_freq_base_hz + CENTER_FREQ_OFFS;\n            if (pico_fractional_pll_init(pll_sys, CLOCK_GPOUT0_PIN, freq_low, freq_high, GPIO_DRIVE_STRENGTH_12MA, GPIO_SLEW_RATE_FAST) != 0) {\n                // ahhhh, the specified frequency range (freq_low ~ freq_high) cannot be within the two PLL divider values\n                // therefore, the pico_fractional_pll cannot work!\n                while (1) { }\n            }\n            pico_fractional_pll_set_freq_u32(freq_center);\n            pico_fractional_pll_enable_output(true);\n'''
new_init = '''            uint32_t freq_center = g_transmit_freq_base_hz + CENTER_FREQ_OFFS;\n            if (piodco_init(&g_gp6_dco, 6, clock_get_hz(clk_sys)) != 0) {\n                while (1) { }\n            }\n            gp6_set_rf_hz(freq_center);\n            piodco_start(&g_gp6_dco);\n            multicore_launch_core1(gp6_dco_core1);\n'''
if old_init not in s:
    raise SystemExit("Could not find fractional PLL init block")
s = s.replace(old_init, new_init)
s = s.replace(
    "            pico_fractional_pll_enable_output(false);\n            pico_fractional_pll_deinit();",
    "            piodco_stop(&g_gp6_dco);\n            multicore_reset_core1();"
)
s = s.replace("#define CLOCK_GPOUT0_PIN    21\n", "")
src.write_text(s)

usb = playground / "apps/usb_sound_card/usb_sound_card.c"
s = usb.read_text()
s = s.replace("#define FM_TRANSMITTER_TX_FREQ_BASE 87900000", "#define FM_TRANSMITTER_TX_FREQ_BASE 89992500")
s = s.replace('"Pico Examples Sound Card"', '"RP2040-Zero GP6 FM"')
s = s.replace("    set_sys_clock_48mhz();", "    set_sys_clock_khz(270000, true);")
usb.write_text(s)

print("Patched upstream FM transmitter for RP2040-Zero GP6 / 90 MHz third harmonic")
