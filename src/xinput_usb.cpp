// Xbox 360 USB interface layout follows the GP2040-CE MIT implementation:
// https://github.com/OpenStickCommunity/GP2040-CE/tree/main/src/drivers/xinput
#include "xinput_usb.h"
#include "xinput_report.h"
#include "state_mgr.h"
#include "utils.h"
#include "bt.h"
#include "tusb.h"
#include "device/usbd_pvt.h"
#include <cstring>

namespace {
constexpr uint8_t input_ep = 0x89;
constexpr uint8_t output_ep = 0x09;
constexpr uint8_t xusb_interface = 4;
constexpr uint8_t device[] = {
    18, 1, 0x10, 0x02, 0xef, 2, 1, 64,
    // pid.codes private test ID. Not unique or suitable for distribution.
    0x09, 0x12, 0x01, 0x00, 0x02, 0x02, 1, 2, 3, 1,
};
constexpr uint8_t gamepad[] = {
    9, 4, xusb_interface, 0, 2, 0xff, 0x5d, 1, 0,
    17, 0x21, 0, 1, 1, 0x25, input_ep, 20, 0, 0, 0, 0, 0x13, output_ep, 8, 0, 0,
    7, 5, input_ep, 3, 32, 0, 1,
    7, 5, output_ep, 3, 32, 0, 8,
};
static_assert(sizeof(gamepad) == 40 && gamepad[21] == 0x13 && gamepad[22] == output_ep);
alignas(4) uint8_t input[20]{};
alignas(4) uint8_t output[32]{};
bool endpoints_open = false;
bool host_rumble = false;
uint8_t usb_port = 0;

void send_rumble(uint8_t left, uint8_t right) {
    if (!bt_is_ready()) return;
    // Use the normal Studio output handler so gain, release, and packet
    // retry all apply to Xbox rumble as they do to DualSense USB output.
    uint8_t state[sizeof(SetStateData)]{};
    state[0] = 3; // compatible rumble, controller-emulated mode
    state[2] = right;
    state[3] = left;
    tud_hid_set_report_cb(0, 2, HID_REPORT_TYPE_OUTPUT, state, sizeof(state));
    host_rumble = left || right;
}

void init() {}
void reset(uint8_t) {
    endpoints_open = false;
    if (host_rumble) {
        state_rumble_reset();
        send_rumble(0, 0);
        host_rumble = false;
    }
}
bool deinit() { reset(usb_port); return true; }

uint16_t open(uint8_t port, const tusb_desc_interface_t *itf, uint16_t remaining) {
    if (itf->bInterfaceClass != TUSB_CLASS_VENDOR_SPECIFIC || itf->bInterfaceNumber != xusb_interface ||
        itf->bInterfaceSubClass != 0x5d || itf->bInterfaceProtocol != 1 || remaining < sizeof(gamepad)) return 0;
        const auto *desc = reinterpret_cast<const uint8_t *>(itf);
        if (!usbd_edpt_open(port, reinterpret_cast<const tusb_desc_endpoint_t *>(desc + 26)) ||
            !usbd_edpt_open(port, reinterpret_cast<const tusb_desc_endpoint_t *>(desc + 33))) return 0;
        usb_port = port;
        endpoints_open = usbd_edpt_xfer(port, output_ep, output, sizeof(output));
        if (!endpoints_open) return 0;
    return sizeof(gamepad);
}

bool control(uint8_t, uint8_t, const tusb_control_request_t *) { return false; }

bool transfer(uint8_t port, uint8_t ep, xfer_result_t result, uint32_t length) {
    if (ep == output_ep) {
        uint8_t left, right;
        if (result == XFER_RESULT_SUCCESS && xinput_decode_rumble(output, length, left, right))
            send_rumble(left, right);
        usbd_edpt_xfer(port, output_ep, output, sizeof(output));
    }
    return true;
}

const usbd_class_driver_t driver = {
    "XUSB", init, deinit, reset, open, control, transfer, nullptr, nullptr,
};
}

extern "C" const usbd_class_driver_t *usbd_app_driver_get_cb(uint8_t *count) {
    *count = 1;
    return &driver;
}

const uint8_t *xinput_device_descriptor() { return device; }
const uint8_t *xinput_configuration_descriptor(const uint8_t *base, uint16_t size, uint8_t interval) {
    static uint8_t configuration[512];
    constexpr uint8_t audio_iad[] = {8, 11, 0, 3, 1, 1, 0, 5};
    const bool needs_iad = size > 10 && base[10] != TUSB_DESC_INTERFACE_ASSOCIATION;
    const uint16_t extra = needs_iad ? sizeof(audio_iad) : 0;
    if (size < 11 || size + extra + sizeof(gamepad) > sizeof(configuration)) return nullptr;
    memcpy(configuration, base, 9);
    if (needs_iad) memcpy(configuration + 9, audio_iad, extra);
    memcpy(configuration + 9 + extra, base + 9, size - 9);
    size += extra;
    uint16_t insert = size;
    for (uint16_t offset = 0; offset < size;) {
        const uint8_t length = configuration[offset];
        if (length < 2 || offset + length > size) return nullptr;
        const auto type = configuration[offset + 1];
        if (type == TUSB_DESC_INTERFACE_ASSOCIATION && length >= 8 && configuration[offset + 2] == 0) configuration[offset + 7] = 5;
        if (type == TUSB_DESC_INTERFACE && length >= 9 && configuration[offset + 5] == 1) configuration[offset + 8] = 5;
        if (((type == TUSB_DESC_INTERFACE && length >= 9) ||
             (type == TUSB_DESC_INTERFACE_ASSOCIATION && length >= 8)) &&
            configuration[offset + 2] >= xusb_interface) {
            if (insert == size) insert = offset;
            ++configuration[offset + 2];
        }
        offset += length;
    }
    memmove(configuration + insert + sizeof(gamepad), configuration + insert, size - insert);
    memcpy(configuration + insert, gamepad, sizeof(gamepad));
    configuration[insert + 32] = interval;
    const uint16_t total = size + sizeof(gamepad);
    configuration[2] = uint8_t(total);
    configuration[3] = uint8_t(total >> 8);
    ++configuration[4];
    return configuration;
}

bool xinput_report_ready() {
    return endpoints_open && tud_ready() && !usbd_edpt_busy(usb_port, input_ep);
}

void xinput_send_report(const uint8_t *dualsense_report) {
    xinput_encode_report(input, dualsense_report);
    usbd_edpt_xfer(usb_port, input_ep, input, sizeof(input));
}
