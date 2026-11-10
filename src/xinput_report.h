#pragma once
#include <cstdint>

inline void xinput_encode_report(uint8_t (&out)[20], const uint8_t *ds) {
    // USB DualSense report body (without report ID).
    constexpr uint8_t dpad[] = {1, 9, 8, 10, 2, 6, 4, 5, 0};
    const uint8_t hat = ds[7] & 15;
    out[0] = 0;
    out[1] = sizeof(out);
    out[2] = hat < sizeof(dpad) ? dpad[hat] : 0;
    out[2] |= ((ds[8] & 0x20) >> 1) | ((ds[8] & 0x10) << 1) | ((ds[8] & 0xc0));
    out[3] = (ds[8] & 3) | ((ds[9] & 1) << 2);
    out[3] |= ((ds[7] & 0x20) >> 1) | ((ds[7] & 0x40) >> 1) |
              ((ds[7] & 0x10) << 2) | (ds[7] & 0x80);
    out[4] = ds[4];
    out[5] = ds[5];
    for (uint8_t i = 0; i < 4; ++i) {
        const int32_t delta = int32_t(ds[i]) - 128;
        int32_t value = delta < 0 ? delta * 256 : delta * 32767 / 127;
        if (i & 1) value = value == -32768 ? 32767 : -value;
        out[6 + i * 2] = uint8_t(value);
        out[7 + i * 2] = uint8_t(uint16_t(value) >> 8);
    }
    for (uint8_t i = 14; i < sizeof(out); ++i) out[i] = 0;
}

inline bool xinput_decode_rumble(const uint8_t *data, uint32_t length, uint8_t &left, uint8_t &right) {
    if (!data || length < 8 || data[0] != 0 || data[1] != 8) return false;
    left = data[3];
    right = data[4];
    return true;
}
