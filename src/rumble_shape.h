#pragma once
#include <cstdint>

// No buffers or allocation. Input increases attack immediately; only falling
// edges interpolate. Repeated identical input never restarts the release.
class RumbleShape {
    struct Channel {
        uint8_t target = 0, start = 0;
        uint32_t since = 0;
        uint8_t value(uint32_t now, uint32_t duration) const {
            const uint32_t elapsed = now - since;
            if (!duration || elapsed >= duration) return target;
            return target + (uint32_t(start - target) * (duration - elapsed)) / duration;
        }
        uint8_t step(uint8_t next, uint32_t now, uint32_t duration) {
            const uint8_t current = value(now, duration);
            if (!duration || next > target) { target = start = next; since = now; }
            else if (next != target) { start = current; target = next; since = now; }
            if (now - since >= duration) start = target;
            return value(now, duration);
        }
    } left_, right_;
    uint8_t gain_ = 100, release_ = 0;
public:
    void reset() { left_ = {}; right_ = {}; }
    static uint32_t duration(uint8_t release) { return release == 1 ? 20 : release == 2 ? 40 : 0; }
    bool active() const {
        // Keep scheduling until the final zero has actually been composed.
        return left_.start != left_.target || right_.start != right_.target;
    }
    void apply(uint8_t &left, uint8_t &right, uint32_t now, uint8_t gain, uint8_t release) {
        if (gain != gain_ || release != release_) { reset(); gain_ = gain; release_ = release; }
        const auto scale = [gain](uint8_t v) -> uint8_t {
            const uint32_t n = (uint32_t(v) * gain + 50) / 100;
            return n > 255 ? 255 : n;
        };
        left = left_.step(scale(left), now, duration(release));
        right = right_.step(scale(right), now, duration(release));
    }
};
