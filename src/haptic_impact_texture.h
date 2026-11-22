#pragma once

#include <algorithm>

class HapticImpactTexture {
public:
    // 48 kHz. A smoothed onset detector rejects carrier-cycle peaks and
    // rearms only after the signal falls below the trailing envelope.
    float update(float low_envelope, float gated_envelope) {
        fast += .006f * (low_envelope - fast);
        if (fast <= .80f * slow || gated_envelope <= .004f) armed = true;
        if (armed && remaining == 0 && gated_envelope > .012f &&
            fast > 1.65f * slow + .006f) {
            remaining = 768;
            armed = false;
        }
        slow += .0007f * (fast - slow);
        if (!remaining) return 0.0f;
        const float rise = (768 - remaining) * (1.0f / 96.0f);
        const float decay = remaining * (1.0f / 672.0f);
        --remaining;
        return .40f * std::min(rise, decay);
    }

private:
    float fast = 0.0f, slow = 0.0f;
    int remaining = 0;
    bool armed = true;
};
