#pragma once
#include <cstdint>
// Preserve all non-motor fields in queued output (LEDs, triggers, volume).
inline void refresh_rumble_fields(uint8_t *queued, const uint8_t *current) {
    queued[0] = (queued[0] & ~3u) | (current[0] & 3u);
    queued[38] = (queued[38] & ~4u) | (current[38] & 4u);
    queued[2] = current[2]; queued[3] = current[3];
}

// Track control fields until successful delivery, not merely queue admission.
class RumbleSent {
    uint8_t value_[63]{};
    bool valid_ = false;
    static uint8_t field(const uint8_t *p, unsigned i) {
        if (i == 1) return p[i] & 0xe3; // RGB/player LEDs have separate delivery tracking
        if (i == 38) return p[i] & 4;
        if (i >= 32 && i != 36 && i != 37) return 0;
        return p[i];
    }
public:
    void reset() { valid_ = false; }
    bool pending(const uint8_t *p) const {
        if (!valid_) return true;
        for (unsigned i=0; i<63; ++i) if (value_[i] != field(p,i)) return true;
        return false;
    }
    void accepted(const uint8_t *p) {
        for (unsigned i=0; i<63; ++i) value_[i] = field(p,i);
        valid_ = true;
    }
};
