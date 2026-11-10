#pragma once
#include <cstdint>

// Core0 only. A finite speaker-only cue; no settings or haptic samples change.
class ProfileChime {
    uint32_t start_ms = 0, synth_us = 0, sample = 0;
    bool running = false;
public:
    void start(uint32_t now_ms, uint32_t now_us) {
        start_ms = now_ms; synth_us = now_us; sample = 0; running = true;
    }
    void stop() { running = false; }
    bool active(uint32_t now_ms) {
        if (running && now_ms - start_ms >= 100) running = false;
        return running;
    }
    bool synthetic_due(uint32_t now_us) {
        if (!running || now_us - synth_us < 1000) return false;
        synth_us = now_us; return true;
    }
    void host_input(uint32_t now_us) { synth_us = now_us; }
    float next() {
        if (!running || sample >= 2880) return 0.0f;
        const uint32_t n = sample++;
        const float fade = n < 240 ? n / 240.0f : n > 2640 ? (2880 - n) / 240.0f : 1.0f;
        const uint32_t phase = n % 48;
        const float wave = phase < 24 ? phase / 12.0f - 1.0f : 3.0f - phase / 12.0f;
        return wave * fade * 0.06f;
    }
};
