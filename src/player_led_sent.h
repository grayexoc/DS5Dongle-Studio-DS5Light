#pragma once
#include <cstdint>

// Track accepted output, never merely composed output. Audio reports can
// satisfy a pending LED change without an additional control report.
class PlayerLedSent {
    uint8_t pattern_ = 0, brightness_ = 0;
    bool pattern_valid_ = false, brightness_valid_ = false;
public:
    void reset() { pattern_valid_ = brightness_valid_ = false; }
    void release_pattern() { pattern_valid_ = false; }
    void restore_brightness(uint8_t *data) const {
        // Returning from a user override must restore the host/default brightness too.
        if (brightness_valid_ && brightness_ != data[42]) data[38] |= 1;
    }
    bool pending(const uint8_t *data) const {
        return ((data[1] & 0x10) && (!pattern_valid_ || pattern_ != data[43])) ||
               ((data[38] & 1) && (!brightness_valid_ || brightness_ != data[42]));
    }
    void accepted(const uint8_t *data) {
        if (data[1] & 0x10) { pattern_ = data[43]; pattern_valid_ = true; }
        if (data[38] & 1) { brightness_ = data[42]; brightness_valid_ = true; }
    }
};
