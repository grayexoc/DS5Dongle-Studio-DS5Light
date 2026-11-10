#pragma once
#include <cmath>
inline float haptic_mix(float native, float derived, float rumble) {
    native = native < -1.0f ? -1.0f : (native > 1.0f ? 1.0f : native);
    const float added = derived + rumble;
    const float room = 1.0f - std::fabs(native);
    if (room <= 0.0f) return native;
    const float knee = room * 0.9f;
    const float magnitude = std::fabs(added);
    if (magnitude <= knee) return native + added;
    // Only the combined peak consumes the soft knee; ordinary signals stay linear.
    const float span = room - knee;
    const float excess = magnitude - knee;
    const float limited = knee + span * (excess / (span + excess));
    return native + (added < 0.0f ? -limited : limited);
}
