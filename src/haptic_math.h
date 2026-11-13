#pragma once
#include <algorithm>
#include <array>
#include <cmath>

namespace haptic_math {
constexpr unsigned intervals = 1024;
constexpr double pi = 3.14159265358979323846;
constexpr float phase_end = 2.0f * static_cast<float>(pi);

// Constant evaluation creates read-only tables without startup or audio-loop work.
constexpr double sine_constant(double x) {
    if (x > pi) x -= 2.0 * pi;
    double term = x, sum = x;
    for (int i = 1; i < 14; ++i) {
        term *= -x * x / ((2 * i) * (2 * i + 1));
        sum += term;
    }
    return sum;
}

constexpr double tanh_constant(double x) {
    double term = 1.0, sum = 1.0;
    for (int i = 1; i < 80; ++i) {
        term *= 2.0 * x / i;
        sum += term;
    }
    return (sum - 1.0) / (sum + 1.0);
}

constexpr std::array<float, intervals + 1> sine_table() {
    std::array<float, intervals + 1> table{};
    for (unsigned i = 0; i <= intervals; ++i)
        table[i] = static_cast<float>(sine_constant(2.0 * pi * i / intervals));
    table[intervals / 2] = table[intervals] = 0.0f;
    return table;
}

constexpr std::array<float, intervals + 1> tanh_table() {
    std::array<float, intervals + 1> table{};
    for (unsigned i = 0; i <= intervals; ++i)
        table[i] = static_cast<float>(tanh_constant(10.0 * i / intervals));
    return table;
}

inline constexpr auto sine_values = sine_table();
inline constexpr auto tanh_values = tanh_table();

// The existing oscillator keeps phase in [0, phase_end].
inline float sine_phase(float phase) {
    const float position = phase * (intervals / phase_end);
    const unsigned index = std::min(static_cast<unsigned>(position), intervals - 1);
    const float fraction = position - index;
    return sine_values[index] + (sine_values[index + 1] - sine_values[index]) * fraction;
}

inline float soft_clip(float x) {
    if (std::isnan(x)) return x;
    const float magnitude = std::fabs(x);
    if (magnitude >= 10.0f) return std::copysign(1.0f, x);
    const float position = magnitude * (intervals / 10.0f);
    const unsigned index = std::min(static_cast<unsigned>(position), intervals - 1);
    const float fraction = position - index;
    const float value = tanh_values[index] + (tanh_values[index + 1] - tanh_values[index]) * fraction;
    return std::copysign(value, x);
}
}
