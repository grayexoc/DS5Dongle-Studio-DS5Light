#pragma once

#include <algorithm>

class HapticImpactTexture {
public:
    static constexpr bool uses_front(int mode, int source) {
        return source == 0 && (mode == 1 || mode == 2);
    }

    // 48 kHz. A smoothed onset detector rejects carrier-cycle peaks and
    // rearms after a valley or when the attack has settled into a steady bed.
    float update(float envelope, float gated_envelope,
                 float lower_band = 0.0f, float upper_band = 0.0f) {
        const bool past_crest = envelope <= fast;
        fast += .006f * (envelope - fast);
        if (fast <= .80f * slow) armed = true;
        if (!armed && remaining == 0) {
            const bool settled = fast >= .95f * slow && fast <= 1.05f * slow &&
                envelope >= .95f * fast && envelope <= 1.05f * fast;
            settled_samples = settled ? settled_samples + 1 : 0;
            if (settled_samples >= 192) armed = true; // 4 ms
        }
        bool follow_up = false;
        if (remaining != 0) {
            attack_peak = std::max(attack_peak, fast);
        } else if (follow_up_samples > 0) {
            --follow_up_samples;
            attack_valley = std::min(attack_valley, fast);
            if (valley_samples < valley_hold_samples) {
                const bool near_valley = fast <= 1.05f * attack_valley &&
                    envelope >= .90f * fast && envelope <= 1.05f * fast;
                valley_samples = near_valley ? valley_samples + 1 : 0;
            }
            // A fresh rise from the tail can be distinct even while slow still
            // contains the first hit. Require a real decay and a steep new edge.
            follow_up = valley_samples >= valley_hold_samples && attack_valley < .75f * attack_peak &&
                gated_envelope > .012f && fast > 1.08f * attack_valley + .005f &&
                envelope > 1.16f * fast + .013f;
        }
        const bool onset = remaining == 0 && armed &&
            ((gated_envelope > .012f && fast > 1.65f * slow + .006f) ||
             // Wait for the crest before accepting a weaker but distinct onset.
             (past_crest && gated_envelope > .003f && fast > 2.20f * slow + .004f));
        if (onset || follow_up) {
            remaining = attack_samples;
            armed = false;
            settled_samples = 0;
            blend_reduction = 0.0f;
            attack_peak = attack_valley = fast;
            valley_samples = 0;
            follow_up_samples = 5760; // 120 ms after this texture ends
        }
        // Give the existing crossover time to settle while the original attack plays.
        if (remaining == band_check_remaining) {
            const float band_sum = lower_band + upper_band;
            if (band_sum > 1e-6f && lower_band > .60f * band_sum) {
                const float low_share = lower_band / band_sum;
                blend_reduction = std::min(.20f, low_share - .60f);
            }
        }
        slow += .0007f * (fast - slow);
        if (!remaining) return 0.0f;
        const float rise = (attack_samples - remaining) * (1.0f / ramp_samples);
        float decay = remaining * (1.0f / (attack_samples - ramp_samples));
        float peak_blend = .40f;
        if (blend_reduction > 0.0f) {
            const float progress = std::min((band_check_remaining - remaining) * (1.0f / ramp_samples), 1.0f);
            peak_blend -= blend_reduction * progress;
            // Fade the upper harmonic faster on low-dominant hits.
            decay *= 1.0f - blend_reduction * progress * (1.0f - decay);
        }
        if (--remaining == 0) attack_valley = fast;
        return peak_blend * std::min(rise, decay);
    }

    float steer_onset(float blend, const HapticImpactTexture &other) {
        if (remaining == attack_samples - 1) {
            const float rise = std::max(0.0f, fast - slow);
            const float other_rise = other.fast - other.slow;
            // Latch at onset so a shift in balance cannot change an ongoing pulse.
            direction_gain = other_rise >= .012f && rise <= .5f * other_rise ? .50f : 1.0f;
        }
        return blend * direction_gain;
    }

private:
    static constexpr int attack_samples = 768; // 16 ms
    static constexpr int ramp_samples = 96; // 2 ms
    static constexpr int valley_hold_samples = 96; // 2 ms
    static constexpr int band_check_remaining = attack_samples - 480; // 10 ms after onset
    float fast = 0.0f, slow = 0.0f;
    float attack_peak = 0.0f;
    float attack_valley = 0.0f;
    float blend_reduction = 0.0f;
    float direction_gain = 1.0f;
    int remaining = 0;
    int settled_samples = 0;
    int follow_up_samples = 0;
    int valley_samples = 0;
    bool armed = true;
};
