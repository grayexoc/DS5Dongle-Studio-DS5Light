#pragma once
#include <cstdint>
// Interrupts disabled; core1 parked via flash_safe_execute, or not yet launched at boot.
bool storage_redo_write(uint32_t target, const uint8_t *image, uint32_t bytes);
bool storage_redo_recover();
