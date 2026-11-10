// Button-only dormant standby; flush failed slot activation before shutdown.
#include "manual_power.h"
#include "bt.h"
#include "audio.h"
#include "config.h"
#include "oled_status.h"
#include "usb.h"
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "pico/cyw43_arch.h"
#include "pico/bootrom.h"
#include "boot/picoboot_constants.h"
#include "hardware/clocks.h"
#include "hardware/pll.h"
#include "hardware/xosc.h"
#include "hardware/watchdog.h"
#include "hardware/sync.h"
#include "hardware/structs/rosc.h"
#include "hardware/structs/watchdog.h"
#include "device/usbd.h"
#if PICO_RP2350
#include "hardware/structs/io_qspi.h"
#include "hardware/structs/pads_qspi.h"
#include "hardware/structs/sio.h"
#include "hardware/structs/xosc.h"
#endif

namespace {
constexpr uint kWakeButton = 17; // OLED KEY1: active low
constexpr uint32_t kResumeMagic = 0x4d505752;
constexpr uint32_t kSearchWindowMs = 30000;
constexpr uint32_t kSlotTag = 0x534c0000;
constexpr uint32_t kSlotCheck = 0x7195a3ce;
uint8_t resume_slot = 0xFF;
uint32_t resume_fingerprint = 0;
bool sleep_requested = false;
bool link_seen = false;
uint32_t search_started_ms = 0;
uint32_t awake_until_ms = 0;
enum class PowerState { Searching, Connecting, Ready, Stopping };
PowerState power_state = PowerState::Searching;
uint32_t state_started_ms = 0;
bool disconnect_requested = false;
ManualPowerState request_state = ManualPowerState::Idle;
ManualPowerError request_error = ManualPowerError::None;
bool waiting_host_reply = false;
uint32_t host_request_ms = 0;
uint32_t shutdown_not_before_ms = 0;

void cancel_sleep(ManualPowerError error) {
    sleep_requested = false;
    waiting_host_reply = false;
    link_seen = false;
    request_state = ManualPowerState::Failed;
    request_error = error;
    power_state = PowerState::Searching;
    disconnect_requested = false;
    manual_power_note_activity();
}

#if PICO_RP2350
// Called only after core1 reset, radio/USB teardown and interrupt masking.
// Once CSn is floated, EVERYTHING until its restoration must stay in RAM:
// no SDK function calls, logging, timers, IRQ handlers or flash constants.
static void __no_inline_not_in_flash_func(dormant_wait_with_bootsel)() {
    constexpr uint32_t cs = 1;
    constexpr uint32_t cs_low = IO_QSPI_DORMANT_WAKE_INTE_GPIO_QSPI_SS_LEVEL_LOW_BITS;
    constexpr uint32_t cs_edges = IO_QSPI_INTR_GPIO_QSPI_SS_EDGE_LOW_BITS |
                                  IO_QSPI_INTR_GPIO_QSPI_SS_EDGE_HIGH_BITS;
    const uint32_t saved_ctrl = io_qspi_hw->io[cs].ctrl;
    const uint32_t saved_pad = pads_qspi_hw->io[cs];
    const uint32_t saved_wake = io_qspi_hw->dormant_wake_irq_ctrl.inte;

    // CSn normally drives high while idle. Release its output so BOOTSEL
    // can pull the pin low; enable a defined, non-floating input for wake.
    pads_qspi_hw->io[cs] = (saved_pad | PADS_QSPI_GPIO_QSPI_SS_IE_BITS |
                           PADS_QSPI_GPIO_QSPI_SS_PUE_BITS) &
                          ~(PADS_QSPI_GPIO_QSPI_SS_PDE_BITS | PADS_QSPI_GPIO_QSPI_SS_ISO_BITS);
    io_qspi_hw->io[cs].ctrl =
        (saved_ctrl & ~(IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_BITS | IO_QSPI_GPIO_QSPI_SS_CTRL_IRQOVER_BITS)) |
        (GPIO_OVERRIDE_LOW << IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_LSB);
    __dsb();
    io_qspi_hw->intr = cs_edges;
    io_qspi_hw->dormant_wake_irq_ctrl.inte = saved_wake | cs_low;
    __dsb();

    // GPIO17 is also armed by the caller. Hardware wakes XOSC directly;
    // there is no periodic CPU/BOOTSEL poll during dormant sleep.
    xosc_hw->dormant = XOSC_DORMANT_VALUE_DORMANT;
    while (!(xosc_hw->status & XOSC_STATUS_STABLE_BITS)) {
        __asm volatile ("nop");
    }
    io_qspi_hw->dormant_wake_irq_ctrl.inte = saved_wake;

    // Wait for BOTH keys to stay released for at least 30 ms before
    // returning to flash or normal reboot. This consumes the wake press,
    // preventing a held BOOTSEL from becoming pairing-delete/bootloader input.
    // SYS is still the un-divided XOSC at this point; no timer API is needed.
    uint32_t released_ms = 0;
    while (released_ms < 30) {
        busy_wait_at_least_cycles(XOSC_HZ / 1000);
        const bool cs_released = (sio_hw->gpio_hi_in & SIO_GPIO_HI_IN_QSPI_CSN_BITS) != 0;
        const bool oled_released = (sio_hw->gpio_in & (1u << kWakeButton)) != 0;
        released_ms = cs_released && oled_released ? released_ms + 1 : 0;
    }
    io_qspi_hw->intr = cs_edges;
    io_qspi_hw->io[cs].ctrl = saved_ctrl;
    pads_qspi_hw->io[cs] = saved_pad;
    __dsb();
    __isb();
}
#endif

void enter_dormant() {
    // Never tear down USB/radio while waiting indefinitely for a held button.
    static bool released = false;
    static uint32_t release_since = 0;
    const uint32_t now = to_ms_since_boot(get_absolute_time());
    if (!gpio_get(kWakeButton)) { released = false; return; }
    if (!released) { released = true; release_since = now; return; }
    if (now - release_since < 30) return;
#if !ENABLE_SERIAL
    watchdog_enable(8000, true); // bound shutdown/config-retry stages
#endif
    if (!config_flush_pending_activation()) {
        cancel_sleep(ManualPowerError::SaveFailed);
#if !ENABLE_SERIAL
        watchdog_enable(1000, true);
#endif
        return;
    }
    if (!audio_prepare_sleep()) {
        // Leave the working system intact if the worker could not park safely.
        cancel_sleep(ManualPowerError::WorkerStopFailed);
#if !ENABLE_SERIAL
        watchdog_enable(1000, true);
#endif
        return;
    }
    uint8_t slot = 0xFF;
    uint32_t fingerprint = 0;
    if (active_profile_resume_state(slot, fingerprint)) {
        watchdog_hw->scratch[1] = kSlotTag | slot;
        watchdog_hw->scratch[2] = fingerprint;
        watchdog_hw->scratch[3] = (kSlotTag | slot) ^ fingerprint ^ kSlotCheck;
    } else {
        watchdog_hw->scratch[1] = 0;
        watchdog_hw->scratch[2] = 0;
        watchdog_hw->scratch[3] = 0;
    }
    oled_status_prepare_sleep();
    usb_cancel_reconnect();
    tud_disconnect();
    // Core1 can otherwise access flash or encode while clocks are changed.
    multicore_reset_core1();
#ifndef CYW43_WL_GPIO_SMPS_PIN
#define CYW43_WL_GPIO_SMPS_PIN 1
#endif
    cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, false);
    cyw43_arch_gpio_put(CYW43_WL_GPIO_SMPS_PIN, false);
    // Deinit closes BTstack/driver and removes the wireless polling context.
    cyw43_arch_deinit();

    gpio_init(kWakeButton);
    gpio_set_dir(kWakeButton, GPIO_IN);
    gpio_pull_up(kWakeButton);

    // XOSC dormant with GPIO wake follows the Pico extras clock preparation:
    // switch SYS/REF away from PLLs, stop peripheral clocks, disable both PLLs
    // and ROSC, then stop XOSC. Restart through reset rather than reviving USB,
    // multicore queues and the Bluetooth stack in partially deinitialized state.
    watchdog_disable();
    save_and_disable_interrupts();
    clock_configure(clk_ref, CLOCKS_CLK_REF_CTRL_SRC_VALUE_XOSC_CLKSRC,
                    0, XOSC_HZ, XOSC_HZ);
    clock_configure(clk_sys, CLOCKS_CLK_SYS_CTRL_SRC_VALUE_CLK_REF,
                    0, XOSC_HZ, XOSC_HZ);
    clock_stop(clk_adc);
    clock_stop(clk_usb);
#if PICO_RP2350
    clock_stop(clk_hstx);
#endif
    clock_stop(clk_peri);
    pll_deinit(pll_sys);
    pll_deinit(pll_usb);
    hw_write_masked(&rosc_hw->ctrl,
                    ROSC_CTRL_ENABLE_VALUE_DISABLE << ROSC_CTRL_ENABLE_LSB,
                    ROSC_CTRL_ENABLE_BITS);
    while (rosc_hw->status & ROSC_STATUS_STABLE_BITS) tight_loop_contents();

    // Level wake avoids losing a press between arming and entering dormant.
    gpio_acknowledge_irq(kWakeButton, GPIO_IRQ_EDGE_FALL | GPIO_IRQ_EDGE_RISE);
    gpio_set_dormant_irq_enabled(kWakeButton, GPIO_IRQ_LEVEL_LOW, true);
#if PICO_RP2350
    dormant_wait_with_bootsel();
#else
    xosc_dormant();
#endif

    gpio_set_dormant_irq_enabled(kWakeButton, GPIO_IRQ_LEVEL_LOW, false);
    hw_write_masked(&rosc_hw->ctrl,
                    ROSC_CTRL_ENABLE_VALUE_ENABLE << ROSC_CTRL_ENABLE_LSB,
                    ROSC_CTRL_ENABLE_BITS);
    while (!(rosc_hw->status & ROSC_STATUS_STABLE_BITS)) tight_loop_contents();
    watchdog_hw->scratch[0] = kResumeMagic;
    manual_power_reboot();
}
} // namespace

bool manual_power_boot_is_resume() {
    const bool resumed = watchdog_caused_reboot() &&
                         watchdog_hw->scratch[0] == kResumeMagic;
    watchdog_hw->scratch[0] = 0;
    const uint32_t tagged_slot = watchdog_hw->scratch[1];
    const uint32_t fingerprint = watchdog_hw->scratch[2];
    const uint32_t check = watchdog_hw->scratch[3];
    watchdog_hw->scratch[1] = 0;
    watchdog_hw->scratch[2] = 0;
    watchdog_hw->scratch[3] = 0;
    resume_slot = 0xFF;
    if (resumed && (tagged_slot & 0xffffff00u) == kSlotTag &&
        (tagged_slot & 0xffu) < SLOT_COUNT &&
        check == (tagged_slot ^ fingerprint ^ kSlotCheck)) {
        resume_slot = static_cast<uint8_t>(tagged_slot);
        resume_fingerprint = fingerprint;
    }
    return resumed;
}

void manual_power_restore_profile() {
    if (resume_slot != 0xFF) {
        active_profile_restore(resume_slot, resume_fingerprint);
        resume_slot = 0xFF;
    }
}

void manual_power_init() {
    search_started_ms = to_ms_since_boot(get_absolute_time());
    awake_until_ms = search_started_ms + kSearchWindowMs;
    power_state = PowerState::Searching;
    sleep_requested = waiting_host_reply = false;
    request_state = ManualPowerState::Idle;
    request_error = ManualPowerError::None;
}

void manual_power_note_activity(uint32_t grace_ms) {
    const uint32_t now = to_ms_since_boot(get_absolute_time());
    const uint32_t next = now + (grace_ms > 60000 ? 60000 : grace_ms);
    if (static_cast<int32_t>(now - awake_until_ms) >= 0 ||
        static_cast<int32_t>(next - awake_until_ms) > 0) awake_until_ms = next;
}

[[noreturn]] void manual_power_reboot() {
#if PICO_RP2350
    // Ask the boot ROM explicitly for normal application boot.
    rom_reboot(REBOOT2_FLAG_REBOOT_TYPE_NORMAL | REBOOT2_FLAG_NO_RETURN_ON_SUCCESS,
               10, 0, 0);
#endif
    watchdog_reboot(0, 0, 10); // RP2040 / ROM error fallback
    while (true) tight_loop_contents();
}

void manual_power_request_sleep() {
    if (sleep_requested) return;
    waiting_host_reply = false; // physical key may override an unread host request
    sleep_requested = true;
    shutdown_not_before_ms = to_ms_since_boot(get_absolute_time());
    request_state = ManualPowerState::Scheduled;
    request_error = ManualPowerError::None;
}

void manual_power_request_host_sleep() {
    if (sleep_requested || waiting_host_reply) return; // idempotent; keep deadlines
    host_request_ms = to_ms_since_boot(get_absolute_time());
    waiting_host_reply = true;
    request_state = ManualPowerState::WaitingReply;
    request_error = ManualPowerError::None;
    manual_power_note_activity(5000);
}

void manual_power_sleep_reply_read() {
    if (!waiting_host_reply) return;
    waiting_host_reply = false;
    sleep_requested = true;
    // The callback prepared GET_REPORT data; leave time for its USB transfer.
    shutdown_not_before_ms = to_ms_since_boot(get_absolute_time()) + 250;
    request_state = ManualPowerState::Scheduled;
}

ManualPowerState manual_power_state() { return request_state; }
ManualPowerError manual_power_error() { return request_error; }

void manual_power_task() {
    const uint32_t now = to_ms_since_boot(get_absolute_time());
    const bool connected = bt_is_connected();
    if (waiting_host_reply) {
        if (now - host_request_ms >= 3000) cancel_sleep(ManualPowerError::ReplyTimeout);
        return;
    }
    if (sleep_requested) {
        if (static_cast<int32_t>(now - shutdown_not_before_ms) < 0) return;
        if (power_state != PowerState::Stopping) {
            // Fail while USB/BT are still available, before turning the pad off.
            if (!config_flush_pending_activation()) {
                cancel_sleep(ManualPowerError::SaveFailed);
                return;
            }
            power_state = PowerState::Stopping;
            state_started_ms = now;
            disconnect_requested = false;
            request_state = ManualPowerState::Stopping;
            if (connected) bt_power_off_controller();
        }
        if (!connected) { enter_dormant(); return; }
        if (!disconnect_requested && now - state_started_ms >= 150) {
            bt_disconnect();
            disconnect_requested = true;
        }
        if (now - state_started_ms >= 3000) enter_dormant();
        return;
    }
    if (bt_is_ready()) {
        power_state = PowerState::Ready;
        link_seen = true;
        manual_power_note_activity(3000);
        return;
    }
    if (connected) {
        if (power_state != PowerState::Connecting) {
            power_state = PowerState::Connecting;
            state_started_ms = now;
            disconnect_requested = false;
        }
        if (!disconnect_requested && now - state_started_ms >= 10000) {
            bt_disconnect();
            disconnect_requested = true;
        }
        if (device_auto_dormant() && now - state_started_ms >= 13000) enter_dormant();
        return;
    }
    if (link_seen) {
        // Unexpected loss gets a short recovery window; explicit stop bypasses it.
        link_seen = false;
        manual_power_note_activity(3000);
    }
    power_state = PowerState::Searching;
    if (device_auto_dormant() && static_cast<int32_t>(now - awake_until_ms) >= 0) enter_dormant();
}
