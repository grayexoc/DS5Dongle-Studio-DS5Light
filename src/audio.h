//
// Created by awalol on 2026/3/5.
//

#ifndef DS5_BRIDGE_AUDIO_H
#define DS5_BRIDGE_AUDIO_H

#include <cstdint>

void audio_init();
bool audio_profile_chime();
void audio_loop();
void audio_reset_stream();
bool audio_strip_speaker_payload(uint8_t *report, uint16_t length, bool native);
bool audio_prepare_sleep();
bool audio_processing_active();
bool audio_haptics_stream_active();
uint8_t audio_diagnostic_route();
void audio_diagnostic_snapshot(uint8_t *data);
void core1_entry();
void set_headset(bool state);
void set_mic_active(bool active);
bool audio_mic_active();
void mic_add_queue(uint8_t *data, uint16_t len);
void update_mic_status();

#endif //DS5_BRIDGE_AUDIO_H
