#pragma once
#include <cmath>

struct NativeMixLowpass {
    float left = 0.0f, right = 0.0f;
    bool primed = false;

    void reset() { primed = false; }

    void process(float &input_left, float &input_right, float coefficient) {
        if (!primed) {
            // Start from the current raw sample after a bypass or stream reset.
            left = input_left;
            right = input_right;
            primed = true;
            return;
        }
        left += coefficient * (input_left - left);
        right += coefficient * (input_right - right);
        input_left = left;
        input_right = right;
    }
};

inline float haptic_mix(float native, float added) {
    const float total = native + added; // native is already clamped to [-1, 1].
    if (std::fabs(total) <= 0.9f || added == 0.0f) return total;

    // Limit only toward the rail the additional signal is moving toward.
    const bool negative = added < 0.0f;
    const float room = negative ? 1.0f + native : 1.0f - native;
    const float span = room < 0.1f ? room : 0.1f;
    const float knee = room - span;
    const float excess = std::fabs(added) - knee;
    if (excess <= 0.0f) return total;
    const float limited = knee + span * (excess / (span + excess));
    return native + (negative ? -limited : limited);
}
