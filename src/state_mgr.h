//
// Created by awalol on 2026/5/15.
//

#ifndef DS5_BRIDGE_STATE_MGR_H
#define DS5_BRIDGE_STATE_MGR_H
#include <cstdint>

void state_init();
void state_rumble_reset();
bool state_rumble_wants_report();
bool state_prepare_report(uint8_t *data, bool force); // Writes a full candidate for immediate enqueue.
bool state_release_for_suspend();
bool state_suspend_release_pending();
void state_cancel_suspend_release();
void state_suspend_release_sent(const uint8_t *data);
uint32_t state_synth_interval_ms();
bool state_synth_tick(); // main loop: recompose from live positions + cached host intent; true = state changed, push it
void state_refresh_rumble(uint8_t *data); // Full state buffer; changes only motor fields.
void state_set(uint8_t *data, uint8_t size);
bool player_led_wants_report(void);
bool lightbar_fixed_wants_report();
bool state_report_is_lightbar_restore(const uint8_t *data);
void state_report_sent(const uint8_t *data, bool lightbar_restore);
bool state_update(const uint8_t *data, uint8_t size);
void set_volume(uint8_t value);
void set_volume(uint8_t speaker, uint8_t headset);
void state_diagnostic_snapshot(uint8_t *data); // 25 bytes: validity + host/current/sent
void state_output_test(uint8_t kind); // 0 stop, 1..3 rumble, 4..5 triggers, 6 native PCM

#endif //DS5_BRIDGE_STATE_MGR_H
