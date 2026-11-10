#include <cassert>
#include <cstdint>
#include <cstdio>

// Register constants below come from the actual RP2350 SDK headers.
#include "bootsel_register_extract.h"
#define __no_inline_not_in_flash_func(name) name
constexpr unsigned kWakeButton = 17;
constexpr unsigned GPIO_OVERRIDE_LOW = 2;
constexpr uint32_t XOSC_HZ = 12000000;
struct IoPin { uint32_t ctrl; };
struct Irq { uint32_t inte; };
struct IoQspi { IoPin io[6]; uint32_t intr; Irq dormant_wake_irq_ctrl; } io_mock{};
struct Pads { uint32_t io[6]; } pads_mock{};
struct Sio { uint32_t gpio_hi_in, gpio_in; } sio_mock{};
static auto *io_qspi_hw = &io_mock;
static auto *pads_qspi_hw = &pads_mock;
static auto *sio_hw = &sio_mock;
static unsigned samples, barriers;
static int scenario;
static uint32_t wake_before;

struct DormantRegister {
    void operator=(uint32_t value) {
        assert(value == XOSC_DORMANT_VALUE_DORMANT);
        assert((io_mock.io[1].ctrl & IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_BITS) ==
               (GPIO_OVERRIDE_LOW << IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_LSB));
        assert((pads_mock.io[1] & (PADS_QSPI_GPIO_QSPI_SS_IE_BITS | PADS_QSPI_GPIO_QSPI_SS_PUE_BITS)) ==
               (PADS_QSPI_GPIO_QSPI_SS_IE_BITS | PADS_QSPI_GPIO_QSPI_SS_PUE_BITS));
        assert(!(pads_mock.io[1] & (PADS_QSPI_GPIO_QSPI_SS_PDE_BITS | PADS_QSPI_GPIO_QSPI_SS_ISO_BITS)));
        assert(io_mock.dormant_wake_irq_ctrl.inte == (wake_before | IO_QSPI_DORMANT_WAKE_INTE_GPIO_QSPI_SS_LEVEL_LOW_BITS));
        assert(barriers >= 2);
        // Simulate a hardware wake with the selected key still held.
        if (scenario != 1) sio_mock.gpio_hi_in &= ~SIO_GPIO_HI_IN_QSPI_CSN_BITS;
        if (scenario != 0) sio_mock.gpio_in &= ~(1u << kWakeButton);
    }
};
struct Xosc { DormantRegister dormant; uint32_t status; } xosc_mock{};
static auto *xosc_hw = &xosc_mock;
static void __dsb() { ++barriers; }
static void __isb() { ++barriers; }
static void busy_wait_at_least_cycles(uint32_t cycles) {
    assert(cycles == XOSC_HZ / 1000);
    assert(io_mock.dormant_wake_irq_ctrl.inte == wake_before); // Wake source disarmed before release wait.
    ++samples;
    // Release at 5 ms, one bounce at 12 ms, then both high from 13 ms.
    if (samples >= 5) {
        sio_mock.gpio_hi_in |= SIO_GPIO_HI_IN_QSPI_CSN_BITS;
        sio_mock.gpio_in |= 1u << kWakeButton;
    }
    if (samples == 12) {
        if (scenario != 1) sio_mock.gpio_hi_in &= ~SIO_GPIO_HI_IN_QSPI_CSN_BITS;
        if (scenario != 0) sio_mock.gpio_in &= ~(1u << kWakeButton);
    }
    assert(samples < 100); // Catch a release-wait regression in the model.
}
#include "bootsel_dormant_extract.h"

int main() {
    for (scenario = 0; scenario < 3; ++scenario) {
        samples = barriers = 0;
        io_mock.io[1].ctrl = 0x300001f;
        pads_mock.io[1] = 0x36;
        io_mock.dormant_wake_irq_ctrl.inte = wake_before = 0x100000;
        const auto control_before = io_mock.io[1].ctrl;
        const auto pads_before = pads_mock.io[1];
        sio_mock.gpio_hi_in = sio_mock.gpio_in = 0xffffffff;
        xosc_mock.status = XOSC_STATUS_STABLE_BITS;
        dormant_wait_with_bootsel();
        assert(samples == 42); // 30 consecutive released samples after bounce.
        assert(io_mock.io[1].ctrl == control_before);
        assert(pads_mock.io[1] == pads_before);
        assert(io_mock.dormant_wake_irq_ctrl.inte == wake_before);
        assert(barriers >= 4);
    }
    puts("PASS: actual RAM routine with mocked registers: BOOTSEL/OLED/both wake, held key and bounce consumption, CS/pad/IRQ restoration");
}
