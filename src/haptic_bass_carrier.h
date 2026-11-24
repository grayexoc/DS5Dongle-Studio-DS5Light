#pragma once

#include <algorithm>
#include "haptic_math.h"

class HapticBassCarrier {
public:
    bool upper_dominates() const {
        return upper_energy > 1.05f * low_energy;
    }

    // Read the same filtered stereo input that drives the derived envelope.
    // At 6 kHz, a complementary 65 Hz split estimates the low-band share.
    float phase(float original_phase, float left, float right, float gated, bool attack) {
        sum_l += left;
        sum_r += right;
        if (++sample_count == 8) {
            sample_count = 0;
            // Average before decimation so out-of-band tones have less influence.
            left = sum_l * .125f;
            right = sum_r * .125f;
            sum_l = sum_r = 0.0f;
            low_l += .0658f * (left - low_l);
            low_r += .0658f * (right - low_r);
            const float upper_l = left - low_l, upper_r = right - low_r;
            low_energy += .0138f * (low_l * low_l + low_r * low_r - low_energy);
            upper_energy += .0138f * (upper_l * upper_l + upper_r * upper_r - upper_energy);
            // Hysteresis keeps the carrier steady around the crossover. The
            // attack harmonic retains its own existing 180 Hz phase.
            if (attack) attack_samples_left = 900; // 150 ms at 6 kHz.
            if (attack_samples_left) --attack_samples_left;
            if (!attack_samples_left || gated <= .008f || low_energy <= 1.65f * upper_energy) {
                low_samples = 0;
                deep = false;
            } else if (!deep && low_energy > 2.0f * upper_energy) {
                deep = ++low_samples >= 96; // 16 ms at 6 kHz.
            }
        }
        if (!active) {
            if (!deep) return original_phase;
            shifted_phase = original_phase;
            active = true;
            return shifted_phase;
        }
        const float target = deep ? 72.0f : 90.0f;
        frequency += std::clamp(target - frequency, -.025f, .025f);
        if (!deep && frequency == 90.0f && gated < .001f) {
            active = false;
            return original_phase;
        }
        shifted_phase += haptic_math::phase_end * frequency / 48000.0f;
        if (shifted_phase > haptic_math::phase_end) shifted_phase -= haptic_math::phase_end;
        return shifted_phase;
    }

private:
    float sum_l = 0.0f, sum_r = 0.0f;
    float low_l = 0.0f, low_r = 0.0f;
    float low_energy = 0.0f, upper_energy = 0.0f;
    float frequency = 90.0f, shifted_phase = 0.0f;
    unsigned sample_count = 0;
    unsigned low_samples = 0;
    unsigned attack_samples_left = 0;
    bool deep = false, active = false;
};
