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
s = s.replace(
    '#include "pico_fractional_pll.h"',
    '#include "piodco/piodco.h"\n#include "hardware/clocks.h"'
)
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
new_init = '''            uint32_t freq_center = g_transmit_freq_base_hz + CENTER_FREQ_OFFS;\n            if (piodco_init(&g_gp6_dco, 6, clock_get_hz(clk_sys)) != 0) {\n                while (1) { }\n            }\n            // GP6 must have fast edges for a usable 3rd harmonic around 90 MHz.\n            // Keep this as a short-range/lab RF output; do not attach a long antenna.\n            gpio_set_drive_strength(6, GPIO_DRIVE_STRENGTH_12MA);\n            gpio_set_slew_rate(6, GPIO_SLEW_RATE_FAST);\n            gp6_set_rf_hz(freq_center);\n            piodco_start(&g_gp6_dco);\n            multicore_launch_core1(gp6_dco_core1);\n'''
if old_init not in s:
    raise SystemExit("Could not find fractional PLL init block")
s = s.replace(old_init, new_init)

# The upstream PWM divider is hard-coded for a 48 MHz clk_sys.  GP6 DCO needs
# clk_sys=270 MHz, so leaving those values unchanged consumes PCM ~5.625x too
# fast and walks beyond the USB audio buffer.  Derive the PWM rate from the
# actual clk_sys while keeping the original audio cadence (Fs / 2).
old_pwm = '''            // 22050 or 24000, 441 or 480, 147 or 160\n            // sys_clk 48,000,000Hz / 24,000Hz = 2,0000.0, 2,000.0 / 255 = 7.84, 2,000 / 10 = 200\n            // sys_clk 48,000,000Hz / 22,050Hz = 2,176.87, 2,176.87 / 255 = 8.54, 2,176 / 9 = 241.875 = int:241 + frac:14\n\n            pwm_config config = pwm_get_default_config();\n            if (g_current_sample_freq == 44100) {\n                pwm_config_set_clkdiv_int_frac(&config, 241, 14);\n                pwm_config_set_wrap(&config, (9 - 1));\n            }\n            else {  // 48000\n                pwm_config_set_clkdiv_int(&config, 200);\n                pwm_config_set_wrap(&config, (10 - 1));\n            }\n            pwm_init(slice_num, &config, true);\n'''
new_pwm = '''            // Modulation interrupt rate is one half of the USB sample rate.\n            // Use wrap=255 and a 4-bit fractional PWM divider calculated from\n            // the *actual* system clock (270 MHz for the GP6 DCO build).\n            const uint32_t modulation_rate_hz = g_current_sample_freq / 2u;\n            const uint32_t pwm_wrap = 255u;\n            const uint32_t sys_hz = clock_get_hz(clk_sys);\n            uint32_t divider_x16 = (uint32_t)(((uint64_t)sys_hz * 16u +\n                                      ((uint64_t)modulation_rate_hz * (pwm_wrap + 1u) / 2u)) /\n                                      ((uint64_t)modulation_rate_hz * (pwm_wrap + 1u)));\n            if (divider_x16 < 16u) divider_x16 = 16u;\n            if (divider_x16 > (255u * 16u + 15u)) divider_x16 = 255u * 16u + 15u;\n\n            pwm_config config = pwm_get_default_config();\n            pwm_config_set_clkdiv_int_frac(&config, divider_x16 >> 4u, divider_x16 & 0x0fu);\n            pwm_config_set_wrap(&config, pwm_wrap);\n            pwm_init(slice_num, &config, true);\n'''
if old_pwm not in s:
    raise SystemExit("Could not find original 48 MHz PWM timing block")
s = s.replace(old_pwm, new_pwm)

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

# The old sample calls pico_add_extra_outputs(), which performs post-link passes
# not required for the flash image.  Generate the UF2 directly.
usb_cmake = playground / "apps/usb_sound_card/CMakeLists.txt"
s = usb_cmake.read_text()
old_outputs = '''    target_link_libraries(usb_sound_card_fm_transmitter pico_stdlib usb_device pico_audio_fm_transmitter pico_multicore)\n    pico_add_extra_outputs(usb_sound_card_fm_transmitter)\n    pico_set_binary_type(usb_sound_card_fm_transmitter copy_to_ram)\n'''
new_outputs = '''    target_link_libraries(usb_sound_card_fm_transmitter pico_stdlib usb_device pico_audio_fm_transmitter pico_multicore)\n    pico_set_binary_type(usb_sound_card_fm_transmitter copy_to_ram)\n    pico_add_uf2_output(usb_sound_card_fm_transmitter)\n'''
if old_outputs not in s:
    raise SystemExit("Could not find FM target output block")
s = s.replace(old_outputs, new_outputs)
usb_cmake.write_text(s)

print("Patched upstream FM transmitter for RP2040-Zero GP6 / 90 MHz third harmonic")
print("FM PWM timing now follows clk_sys, so 270 MHz does not overrun USB PCM")
