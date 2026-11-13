#pragma once

// Stored in the existing record: no change to record size, slot stride or CRC.
constexpr uint8_t MACRO_FLAG_SHIFT = 0x20;
constexpr uint8_t MACRO_FLAG_CHIME = 0x40;
constexpr uint8_t MACRO_PROFILE_FIRST = 23;
constexpr uint8_t MACRO_PROFILE_LAST = 30;
constexpr uint8_t MACRO_SHIFT_KEY = 31;
constexpr uint8_t MACRO_POWER_OFF = 32;
inline bool macro_is_profile(uint8_t out) {
    return out >= MACRO_PROFILE_FIRST && out <= MACRO_PROFILE_LAST;
}

template<class Table>
uint32_t macro_layer_mask(const Table &table, uint32_t disabled, bool shifted) {
    uint32_t result = disabled;
    for (uint8_t i = 0; i < MACRO_COUNT; ++i) {
        const auto &base = table.rec[i].entry;
        if (base.out_btn == MACRO_SHIFT_KEY ||
            (!shifted && (base.flags & MACRO_FLAG_SHIFT))) result |= 1u << i;
        if (!shifted || (base.flags & MACRO_FLAG_SHIFT) || (disabled & (1u << i))) continue;
        for (uint8_t j = 0; j < MACRO_COUNT; ++j) {
            const auto &alt = table.rec[j].entry;
            if (!(disabled & (1u << j)) && (alt.flags & MACRO_FLAG_SHIFT) &&
                alt.gesture == base.gesture && alt.chord == base.chord) {
                result |= 1u << i;
                break;
            }
        }
    }
    return result;
}
