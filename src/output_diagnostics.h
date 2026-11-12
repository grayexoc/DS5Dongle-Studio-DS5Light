#pragma once
#include <cstdint>
#include <cstring>

// Only retain the control bytes needed to distinguish PCM from emulated rumble.
struct OutputDiagnostics {
    static constexpr unsigned offsets[8] = {0, 1, 2, 3, 9, 36, 38, 39};
    uint8_t host[8]{}, sent[8]{};
    uint8_t valid = 0;
    void reset() { *this = {}; }
    static void select(uint8_t *out, const uint8_t *data, unsigned size) {
        for (unsigned i = 0; i < 8; ++i) out[i] = offsets[i] < size ? data[offsets[i]] : 0;
    }
    void received(const uint8_t *data, unsigned size) { select(host, data, size); valid |= 1; }
    void accepted(const uint8_t *data) { select(sent, data, 47); valid |= 2; }
};

// Opt-in output tests expire on the device even if the host application dies.
inline void discard_test_trigger_intent(uint8_t *data) {
    data[0] |= 0x0c;
    std::memset(data + 10, 0, 22);
    data[10] = data[21] = 0x05;
}

struct OutputTest {
    uint8_t kind = 0;
    uint32_t started = 0;
    bool release = false;
    void reset() { *this = {}; }
    void start(uint8_t value, uint32_t now) { kind = value; started = now; release = !value; }
    bool pending() const { return kind || release; }
    void apply(uint8_t *data, uint32_t now) {
        if (kind && uint32_t(now - started) >= 2000) { kind = 0; release = true; }
        if (!pending()) return;
        // 1..3: classic 64; 7..9: classic 128; 10..12: improved 64; 13..15: improved 128.
        const bool improved = kind >= 10;
        const uint8_t sides = kind >= 7 ? (kind - 7) % 3 + 1 : (kind <= 3 ? kind : 0);
        const uint8_t strength = (kind >= 7 && kind <= 9) || kind >= 13 ? 128 : 64;
        data[0] = (data[0] & ~3u) | (improved ? 2u : (sides ? 3u : 1u));
        data[38] = (data[38] & ~4u) | (improved ? 4u : 0u);
        data[2] = sides & 2 ? strength : 0; // right motor
        data[3] = sides & 1 ? strength : 0;
        // Tests never leave trigger resistance behind; restore the profile after ACK.
        data[0] |= 0x0c;
        std::memset(data + 10, 0, 22);
        data[10] = data[21] = 0x05; // OFF
        if (kind == 4 || kind == 5) {
            auto *effect = data + (kind == 4 ? 21 : 10);
            effect[0] = 0x21; effect[1] = 0xfc; effect[2] = 3;
            uint32_t levels = 0;
            for (unsigned i = 2; i < 10; ++i) levels |= 2u << (i * 3);
            for (unsigned i = 0; i < 4; ++i) effect[3 + i] = levels >> (i * 8);
        }
    }
    void accepted(const uint8_t *data) {
        if (release && (data[0] & 15) == 13 && !data[2] && !data[3] &&
            !(data[38] & 4) && data[10] == 5 && data[21] == 5) release = false;
    }
};
