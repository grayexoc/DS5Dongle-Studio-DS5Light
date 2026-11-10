#pragma once

#include <cstdint>

void ps_shortcut_tick(const uint8_t *data, uint16_t len);
void ps_shortcut_reset();
void ps_shortcut_task();
bool ps_shortcut_owns_keyboard();
