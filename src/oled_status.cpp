// Single-page Waveshare Pico-OLED-1.3 status display for Studio.
// Panel driver and 5x7 font are based on DS5Dongle-OLED-Edition (MIT).
#include "oled_status.h"
#include "manual_power.h"

#include "oled_font.h"
#include "nyan_full2_8fps.h"
#include "xbox_logo_slow.h"
#include "dualsense_buttons_8fps.h"
#include "bt.h"
#include "config.h"
#include "wake.h"
#include "usb.h"

#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "device/usbd.h"
#include "pico/stdlib.h"

#include <cstdio>
#include <cstring>

extern uint8_t interrupt_in_data[63];
extern volatile uint8_t g_oled_ah_input_peak;
extern volatile uint8_t g_oled_ah_output_peak;

namespace {

constexpr int kWidth = 128;
constexpr int kHeight = 64;
constexpr int kRowBytes = kWidth / 8;
constexpr int kFramebufferBytes = kRowBytes * kHeight;

constexpr uint kPinDc = 8;
constexpr uint kPinCs = 9;
constexpr uint kPinClock = 10;
constexpr uint kPinMosi = 11;
constexpr uint kPinReset = 12;
constexpr uint kPinButton1 = 15; // OLED KEY0
constexpr uint kPinButton2 = 17; // OLED KEY1
constexpr uint32_t kButtonDebounceMs = 30;
constexpr int kGraphSamples = 31;
constexpr int kGraphLeft = 3;
constexpr int kGraphTop = 21;
constexpr int kGraphBottom = 53;
constexpr uint32_t kGraphMuteTransitionMs = 1000;

// SH1107 contrast is a register value, not a calibrated optical percentage.
// 0x0F is 6% of the 0..255 register range and remains fixed for this build.
constexpr uint8_t kFixedContrast = 0x0F;

uint8_t framebuffer[kFramebufferBytes]{};
uint8_t sent_framebuffer[kFramebufferBytes]{};
bool panel_in_sync = false;
bool panel_enabled = false;
bool panel_wake_pending = false;
bool status_refresh_requested = true;
bool frame_transfer_pending = false;
int transfer_row = 0;
uint32_t last_frame_ms = 0;
uint32_t title_step_ms = 0;
int title_offset = 0;

struct ButtonState {
    bool initialized = false;
    bool raw_released = true;
    bool stable_released = true;
    uint32_t raw_changed_ms = 0;
};

ButtonState button1_state;
ButtonState button2_state;
uint8_t audio_history[kGraphSamples]{};
uint8_t haptic_history[kGraphSamples]{};
uint8_t graph_count = 0;
bool graph_mute_screen = true;
bool graph_transition_pending = false;
bool graph_transition_to_active = false;
uint32_t graph_transition_started_ms = 0;
uint8_t graph_pending_audio_peak = 0;
uint8_t graph_pending_haptic_peak = 0;

void reset_graph_state() {
    memset(audio_history, 0, sizeof(audio_history));
    memset(haptic_history, 0, sizeof(haptic_history));
    graph_count = 0;
    graph_mute_screen = true;
    graph_transition_pending = false;
    graph_transition_to_active = false;
    graph_transition_started_ms = 0;
    graph_pending_audio_peak = graph_pending_haptic_peak = 0;
    g_oled_ah_input_peak = 0;
    g_oled_ah_output_peak = 0;
}

bool button_pressed_event(uint pin, ButtonState &state, uint32_t now) {
    const bool raw_released = gpio_get(pin) != 0;
    if (!state.initialized) {
        state.initialized = true;
        state.raw_released = raw_released;
        state.stable_released = raw_released;
        state.raw_changed_ms = now;
        return false;
    }
    if (raw_released != state.raw_released) {
        state.raw_released = raw_released;
        state.raw_changed_ms = now;
        return false;
    }
    if (raw_released != state.stable_released &&
        now - state.raw_changed_ms >= kButtonDebounceMs) {
        state.stable_released = raw_released;
        return !raw_released;
    }
    return false;
}

void activate_other_profile() {
    manual_power_note_activity();
    uint8_t active_slot = 0xFF;
    bool edited = false;
    uint8_t active_name[SLOT_NAME_LEN]{};
    active_profile_get(active_slot, edited, active_name);
    const uint8_t target_slot = (active_slot == 0) ? 1 : 0;

    uint8_t name[SLOT_NAME_LEN]{};
    uint8_t valid = 0;
    uint8_t version = 0;
    if (!slot_info(target_slot, name, valid, version) || !valid) {
        printf("[OLED] Profile %u is empty; cannot switch\n",
               static_cast<unsigned>(target_slot + 1));
        return;
    }

    bool needs_reenum = false;
    uint8_t fail_stage = 0;
    const uint8_t result = slot_activate(target_slot, needs_reenum, fail_stage);
    if (result == 0) {
        printf("[OLED] Profile %u activation failed at stage %u\n",
               static_cast<unsigned>(target_slot + 1),
               static_cast<unsigned>(fail_stage));
        return;
    }
    printf("[OLED] Activated profile %u%s\n",
           static_cast<unsigned>(target_slot + 1),
           result == 2 ? " (flash save deferred)" : "");

    if (needs_reenum) usb_schedule_reconnect();
}

void poll_buttons(uint32_t now) {
    if (button_pressed_event(kPinButton1, button1_state, now)) {
        activate_other_profile();
        status_refresh_requested = true;
        last_frame_ms = 0;
    }
    if (button_pressed_event(kPinButton2, button2_state, now)) {
        manual_power_request_sleep();
    }
}

void send_commands(const uint8_t *commands, size_t length) {
    gpio_put(kPinDc, 0);
    gpio_put(kPinCs, 0);
    spi_write_blocking(spi1, commands, length);
    gpio_put(kPinCs, 1);
}

void send_command(uint8_t command) {
    send_commands(&command, 1);
}

void send_data(const uint8_t *data, size_t length) {
    gpio_put(kPinDc, 1);
    gpio_put(kPinCs, 0);
    spi_write_blocking(spi1, data, length);
    gpio_put(kPinCs, 1);
}

uint8_t reverse_bits(uint8_t value) {
    value = static_cast<uint8_t>(((value & 0x55u) << 1) | ((value & 0xAAu) >> 1));
    value = static_cast<uint8_t>(((value & 0x33u) << 2) | ((value & 0xCCu) >> 2));
    return static_cast<uint8_t>((value << 4) | (value >> 4));
}

void set_pixel(int x, int y) {
    if (x < 0 || x >= kWidth || y < 0 || y >= kHeight) return;
    framebuffer[y * kRowBytes + x / 8] |= static_cast<uint8_t>(1u << (7 - (x % 8)));
}

void clear_pixel(int x, int y) {
    if (x < 0 || x >= kWidth || y < 0 || y >= kHeight) return;
    framebuffer[y * kRowBytes + x / 8] &= static_cast<uint8_t>(~(1u << (7 - (x % 8))));
}

void draw_text(int x, int y, const char *text, int advance = 6) {
    for (; *text && x < kWidth; ++text, x += advance) {
        const unsigned char ch = static_cast<unsigned char>(*text);
        if (ch < 0x20 || ch > 0x7E) continue;
        const uint8_t *glyph = kFont5x7[ch - 0x20];
        for (int col = 0; col < kFontW; ++col)
            for (int row = 0; row < kFontH; ++row)
                if (glyph[col] & (1u << row)) set_pixel(x + col, y + row);
    }
}

void draw_centered(int y, const char *text) {
    const int width = static_cast<int>(strlen(text)) * 6 - 1;
    draw_text((kWidth - width) / 2, y, text);
}

void draw_title(uint32_t now) {
    constexpr char title[] = "Studio-DS5Light v" PICO_PROGRAM_VERSION_STRING "   ";
    constexpr int cycle_width = (sizeof(title) - 1) * 6;
    const uint32_t delay_ms = title_offset == 0 ? 1000 : 125;
    if (now - title_step_ms >= delay_ms) {
        title_offset = (title_offset + 1) % cycle_width;
        title_step_ms = now;
    }
    // Clip each column to eight character cells; the signal stays fixed.
    for (int x = 0; x < 8 * 6; ++x) {
        const int source_x = (title_offset + x) % cycle_width;
        const int col = source_x % 6;
        if (col >= kFontW) continue;
        const uint8_t bits = kFont5x7[title[source_x / 6] - 0x20][col];
        for (int row = 0; row < kFontH; ++row)
            if (bits & (1u << row)) set_pixel(1 + x, 1 + row);
    }
}

void draw_nyan(uint32_t now) {
    constexpr uint32_t kFrameDurationMs = 125;
    const uint8_t frame = static_cast<uint8_t>((now / kFrameDurationMs) % 8);
    constexpr int y0 = 23;
    for (int y = 0; y < kNyanHeight; ++y) {
        for (int x = 0; x < kNyanWidth; ++x) {
            const uint8_t bits = kNyanFrames[frame][y * kNyanStride + x / 8];
            if (bits & (1u << (7 - (x % 8)))) set_pixel(x, y0 + y);
        }
    }
}

void draw_xbox(uint32_t now) {
    constexpr uint32_t kLoopMs = 2000;
    constexpr uint32_t kFrameCount = sizeof(kXboxFrames) / sizeof(kXboxFrames[0]);
    const auto &frame = kXboxFrames[(now % kLoopMs) * kFrameCount / kLoopMs];
    for (int y = 0; y < kXboxHeight; ++y) {
        for (int x = 0; x < kXboxWidth; ++x) {
            if (frame[y * kXboxStride + x / 8] & (0x80u >> (x % 8))) set_pixel(x, 19 + y);
        }
    }
}

void draw_dualsense_buttons(uint32_t now) {
    constexpr uint32_t kFrameDurationMs = 125;
    const uint8_t frame = static_cast<uint8_t>((now / kFrameDurationMs) % 8);
    constexpr int y0 = 19;
    for (int y = 0; y < kBtnHeight; ++y) {
        for (int x = 0; x < kBtnWidth; ++x) {
            const uint8_t bits = kBtnFrames[frame][y * kBtnStride + x / 8];
            if (bits & (1u << (7 - (x % 8)))) set_pixel(x, y0 + y);
        }
    }
}

void draw_battery(int percent) {
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    char text[8];
    snprintf(text, sizeof(text), "%d%%", percent);
    const int text_width = static_cast<int>(strlen(text)) * 6 - 1;
    constexpr int kGap = 4;
    constexpr int kBodyWidth = 47;
    constexpr int kBodyHeight = 7;
    constexpr int kCapGap = 0;
    constexpr int kCapWidth = 2;
    const int total_width = text_width + kGap + kBodyWidth + kCapGap + kCapWidth;
    constexpr int kBodyY = 56;
    const int start_x = (kWidth - total_width) / 2;
    const int body_x = start_x + text_width + kGap;

    draw_text(start_x, kBodyY, text);
    for (int x = 0; x < kBodyWidth; ++x) {
        set_pixel(body_x + x, kBodyY);
        set_pixel(body_x + x, kBodyY + kBodyHeight - 1);
    }
    for (int y = 0; y < kBodyHeight; ++y) {
        set_pixel(body_x, kBodyY + y);
        set_pixel(body_x + kBodyWidth - 1, kBodyY + y);
    }

    const int cap_x = body_x + kBodyWidth + kCapGap;
    for (int y = kBodyY + 2; y < kBodyY + 5; ++y)
        for (int x = 0; x < kCapWidth; ++x)
            set_pixel(cap_x + x, y);

    constexpr int kInnerX = 1;
    constexpr int kInnerY = 1;
    constexpr int kInnerWidth = kBodyWidth - 2;
    constexpr int kInnerHeight = kBodyHeight - 2;
    const int fill = (kInnerWidth * percent + 50) / 100;
    for (int y = 0; y < kInnerHeight; ++y)
        for (int x = 0; x < fill; ++x)
            set_pixel(body_x + kInnerX + x, kBodyY + kInnerY + y);
}

bool audio_bar_contains(int x, int y) {
    const int offset = x - kGraphLeft;
    if (offset < 0) return false;
    const int column = offset / 4;
    if (column >= graph_count || (offset % 4) >= 3) return false;
    const int index = column;
    const int amplified = static_cast<int>(audio_history[index]) * 2;
    const int level = amplified > 255 ? 255 : amplified;
    const int height = (level * (kGraphBottom - kGraphTop - 1) + 127) / 255;
    if (height <= 0 || y < kGraphBottom - height || y >= kGraphBottom) return false;
    // A one-pixel horizontal slit sits 1 px below each bar's top.
    return height < 2 || y != kGraphBottom - height + 1;
}

void draw_solid_line(int x0, int y0, int x1, int y1, int thickness = 1) {
    const int dx = x1 > x0 ? x1 - x0 : x0 - x1;
    const int sx = x0 < x1 ? 1 : -1;
    const int dy = y1 > y0 ? y0 - y1 : y1 - y0;
    const int sy = y0 < y1 ? 1 : -1;
    int error = dx + dy;
    for (;;) {
        for (int t = 0; t < thickness; ++t) set_pixel(x0 + t, y0);
        if (x0 == x1 && y0 == y1) break;
        const int twice_error = 2 * error;
        if (twice_error >= dy) { error += dy; x0 += sx; }
        if (twice_error <= dx) { error += dx; y0 += sy; }
    }
}

void draw_mute_icon() {
    // Bounds x=47..80, y=28..46 center the complete mark on the panel.
    // The speaker-to-cross gap is reduced by about half from the previous layout.
    draw_solid_line(47, 33, 53, 33);
    draw_solid_line(53, 33, 61, 28);
    draw_solid_line(61, 28, 61, 46);
    draw_solid_line(61, 46, 53, 41);
    draw_solid_line(53, 41, 47, 41);
    draw_solid_line(47, 41, 47, 33);
    draw_solid_line(53, 33, 53, 41); // divider between speaker body and cone

    draw_solid_line(66, 30, 79, 44, 2);
    draw_solid_line(66, 44, 79, 30, 2);
}

void draw_graph_line(int x0, int y0, int x1, int y1) {
    int dx = x1 > x0 ? x1 - x0 : x0 - x1;
    int sx = x0 < x1 ? 1 : -1;
    int dy = y1 > y0 ? y0 - y1 : y1 - y0;
    int sy = y0 < y1 ? 1 : -1;
    int error = dx + dy;
    int step = 0;
    for (;;) {
        // Dotted trace; erase alternate pixels over bars so it stays distinct
        // from the filled, dithered input columns.
        if (audio_bar_contains(x0, y0)) {
            if ((step & 1) == 0) set_pixel(x0, y0);
            else clear_pixel(x0, y0);
        } else if ((step & 1) == 0) set_pixel(x0, y0);
        ++step;
        if (x0 == x1 && y0 == y1) break;
        const int twice_error = 2 * error;
        if (twice_error >= dy) { error += dy; x0 += sx; }
        if (twice_error <= dx) { error += dx; y0 += sy; }
    }
}

void draw_audio_haptics_graph(uint32_t now) {
    uint8_t audio_peak = g_oled_ah_input_peak;
    uint8_t haptic_peak = g_oled_ah_output_peak;
    g_oled_ah_input_peak = 0;
    g_oled_ah_output_peak = 0;

    const bool signal_active = audio_peak != 0 || haptic_peak != 0;
    if (graph_mute_screen) {
        // Latch even a single short impact across the requested 1-second delay.
        if (signal_active && !graph_transition_pending) {
            graph_transition_pending = true;
            graph_transition_to_active = true;
            graph_transition_started_ms = now;
        }
        if (audio_peak > graph_pending_audio_peak) graph_pending_audio_peak = audio_peak;
        if (haptic_peak > graph_pending_haptic_peak) graph_pending_haptic_peak = haptic_peak;
        if (graph_transition_pending && now - graph_transition_started_ms >= kGraphMuteTransitionMs) {
            graph_mute_screen = false;
            graph_transition_pending = false;
            memset(audio_history, 0, sizeof(audio_history));
            memset(haptic_history, 0, sizeof(haptic_history));
            graph_count = 0;
            audio_peak = graph_pending_audio_peak;
            haptic_peak = graph_pending_haptic_peak;
            graph_pending_audio_peak = graph_pending_haptic_peak = 0;
        }
    } else if (signal_active) {
        graph_transition_pending = false;
    } else if (!graph_transition_pending) {
        graph_transition_pending = true;
        graph_transition_to_active = false;
        graph_transition_started_ms = now;
    } else if (now - graph_transition_started_ms >= kGraphMuteTransitionMs) {
        reset_graph_state();
    }

    if (graph_mute_screen) {
        draw_mute_icon();
        return;
    }
    if (graph_count < kGraphSamples) {
        audio_history[graph_count] = audio_peak;
        haptic_history[graph_count] = haptic_peak;
        ++graph_count;
    } else {
        memmove(audio_history, audio_history + 1, kGraphSamples - 1);
        memmove(haptic_history, haptic_history + 1, kGraphSamples - 1);
        audio_history[kGraphSamples - 1] = audio_peak;
        haptic_history[kGraphSamples - 1] = haptic_peak;
    }

    int previous_x = -1, previous_y = -1;
    for (int column = 0; column < graph_count; ++column) {
        const int index = column;
        const int x = kGraphLeft + column * 4;
        const int graph_height = kGraphBottom - kGraphTop - 1;
        const int amplified = static_cast<int>(audio_history[index]) * 2;
        const int level = amplified > 255 ? 255 : amplified;
        const int bar_height = (level * graph_height + 127) / 255;
        for (int h = 1; h <= bar_height; ++h) {
            const int y = kGraphBottom - h;
            // Restore solid bars; leave a 1 px horizontal gap 1 px below
            // the top edge when the bar is tall enough to contain it.
            if (bar_height >= 2 && h == bar_height - 1) continue;
            set_pixel(x, y);
            set_pixel(x + 1, y);
            set_pixel(x + 2, y);
        }
    }

    // The audio bars rise from the bottom; the haptic trace runs top-to-bottom
    // with increasing output, giving the two series different visual directions.
    for (int column = 0; column < graph_count; ++column) {
        const int index = column;
        const int x = kGraphLeft + column * 4;
        const uint8_t level = haptic_history[index];
        const int graph_height = kGraphBottom - kGraphTop - 1;
        const int y = kGraphTop + (static_cast<int>(level) * graph_height + 127) / 255;
        if (previous_x >= 0) draw_graph_line(previous_x, previous_y, x, y);
        else set_pixel(x, y);
        previous_x = x;
        previous_y = y;
    }
}

void draw_status() {
    memset(framebuffer, 0, sizeof(framebuffer));

    const bool connected = bt_is_connected();
    static int8_t rssi = 0;
    static uint32_t last_rssi_request_ms = 0;
    static bool rssi_requested = false;
    const uint32_t now = to_ms_since_boot(get_absolute_time());
    if (connected && (status_refresh_requested || !rssi_requested || now - last_rssi_request_ms >= 1000)) {
        bt_get_signal_strength(&rssi);
        last_rssi_request_ms = now;
        rssi_requested = true;
    } else if (!connected) {
        rssi = 0;
        rssi_requested = false;
    }
    const bool rssi_valid = connected && bt_signal_valid();

    static uint32_t last_profile_read_ms = 0;
    static bool profile_read = false;
    static bool has_profile = false;
    static uint8_t profile_slot = 0xFF;
    static bool profile_edited = false;
    static uint8_t profile_name[SLOT_NAME_LEN]{};
    if (status_refresh_requested || !profile_read || now - last_profile_read_ms >= 1000) {
        has_profile = active_profile_get(profile_slot, profile_edited, profile_name);
        last_profile_read_ms = now;
        profile_read = true;
    }
    status_refresh_requested = false;

    draw_title(now);
    char line[16];
    if (rssi_valid) snprintf(line, sizeof(line), "%ddB", static_cast<int>(rssi));
    else snprintf(line, sizeof(line), "--");
    const int signal_width = static_cast<int>(strlen(line)) * 6 - 1;
    const int signal_x = kWidth - signal_width - 1;
    draw_text(signal_x, 1, line);

    if (has_profile) {
        char profile[SLOT_NAME_LEN + 2]{};
        size_t n = 0;
        while (n < SLOT_NAME_LEN && profile_name[n] != 0) {
            const uint8_t ch = profile_name[n];
            profile[n] = (ch >= 0x20 && ch <= 0x7E) ? static_cast<char>(ch) : '_';
            ++n;
        }
        profile[n] = '\0';
        if (n == 0) snprintf(profile, sizeof(profile), "Slot");
        n = strlen(profile);
        if (config_activation_save_pending()) profile[n++] = '!';
        else if (profile_edited) profile[n++] = '*';
        profile[n] = '\0';
        draw_centered(11, profile);
    } else {
        draw_centered(11, "Custom Profile");
    }

    if (usb_xinput_active()) {
        reset_graph_state();
        draw_xbox(now);
    } else if (get_config().auto_haptics_enable != 0) {
        draw_audio_haptics_graph(now);
    } else {
        reset_graph_state();
        if (has_profile && profile_slot == 0) draw_dualsense_buttons(now);
        else draw_nyan(now);
    }

    if (connected) {
        int percent = (interrupt_in_data[52] & 0x0F) * 10;
        if (percent > 100) percent = 100;
        draw_battery(percent);
    } else {
        draw_battery(0);
    }
}

void flush_frame() {
    // Keep this frame immutable until sent; yield after at most four rows.
    int rows_sent = 0;
    while (transfer_row < kHeight && rows_sent < 4) {
        const int row = transfer_row++;
        const uint8_t *source = framebuffer + row * kRowBytes;
        const uint8_t *previous = sent_framebuffer + row * kRowBytes;
        if (panel_in_sync && memcmp(source, previous, kRowBytes) == 0) continue;

        if (rows_sent == 0) send_command(0xB0);
        ++rows_sent;
        const uint8_t col = static_cast<uint8_t>(kHeight - 1 - row);
        const uint8_t address[] = {static_cast<uint8_t>(col & 0x0F),
                                   static_cast<uint8_t>(0x10 | (col >> 4))};
        send_commands(address, sizeof(address));
        uint8_t bytes[kRowBytes];
        for (int i = 0; i < kRowBytes; ++i) bytes[i] = reverse_bits(source[i]);
        send_data(bytes, sizeof(bytes));
        memcpy(sent_framebuffer + row * kRowBytes, source, kRowBytes);
    }
    if (transfer_row == kHeight) {
        panel_in_sync = true;
        frame_transfer_pending = false;
        if (panel_wake_pending) {
            // Display RAM survives sleep. Reveal only the complete fresh frame.
            send_command(0xAF);
            panel_wake_pending = false;
        }
    }
}

}  // namespace

void oled_status_init() {
    spi_init(spi1, 10 * 1000 * 1000);
    gpio_set_function(kPinClock, GPIO_FUNC_SPI);
    gpio_set_function(kPinMosi, GPIO_FUNC_SPI);
    gpio_init(kPinCs); gpio_set_dir(kPinCs, GPIO_OUT); gpio_put(kPinCs, 1);
    gpio_init(kPinDc); gpio_set_dir(kPinDc, GPIO_OUT); gpio_put(kPinDc, 0);
    gpio_init(kPinReset); gpio_set_dir(kPinReset, GPIO_OUT); gpio_put(kPinReset, 1);
    gpio_init(kPinButton1); gpio_set_dir(kPinButton1, GPIO_IN); gpio_pull_up(kPinButton1);
    gpio_init(kPinButton2); gpio_set_dir(kPinButton2, GPIO_IN); gpio_pull_up(kPinButton2);

    gpio_put(kPinReset, 0); sleep_ms(20);
    gpio_put(kPinReset, 1); sleep_ms(20);
    send_command(0xAE);
    send_command(0x00); send_command(0x10);
    send_command(0xB0);
    send_command(0xDC); send_command(0x00);
    send_command(0x81); send_command(kFixedContrast);
    send_command(0x21);
    send_command(0xA0);
    send_command(0xC0);
    send_command(0xA4);
    send_command(0xA6);
    send_command(0xA8); send_command(0x3F);
    send_command(0xD3); send_command(0x60);
    send_command(0xD5); send_command(0x41);
    send_command(0xD9); send_command(0x22);
    send_command(0xDB); send_command(0x35);
    send_command(0xAD); send_command(0x8A);
    sleep_ms(20);
    send_command(0xAE);
    panel_in_sync = false;
    panel_enabled = false;
    panel_wake_pending = false;
    status_refresh_requested = true;
    reset_graph_state();
    last_frame_ms = 0;
}

void oled_status_prepare_sleep() {
    send_command(0xAE);
    panel_enabled = false;
    panel_wake_pending = false;
    panel_in_sync = false;
    frame_transfer_pending = false;
    reset_graph_state();
}

void oled_status_loop() {
    const uint32_t now = to_ms_since_boot(get_absolute_time());
    poll_buttons(now);
    if (!bt_is_connected()) {
        if (panel_enabled) {
            send_command(0xAE);
            panel_enabled = false;
            panel_wake_pending = false;
            panel_in_sync = false;
            frame_transfer_pending = false;
            transfer_row = 0;
            reset_graph_state();
        }
        return;
    }
    if (!panel_enabled) {
        reset_graph_state();
        title_offset = 0;
        title_step_ms = now;
        status_refresh_requested = true;
        panel_enabled = true;
        panel_wake_pending = true;
        panel_in_sync = false;
        frame_transfer_pending = false;
        last_frame_ms = now - 125;
    }
    if (frame_transfer_pending) {
        flush_frame();
        return;
    }
    if (now - last_frame_ms < 125) return;
    last_frame_ms = now;
    draw_status();
    transfer_row = 0;
    frame_transfer_pending = true;
    flush_frame();
}


