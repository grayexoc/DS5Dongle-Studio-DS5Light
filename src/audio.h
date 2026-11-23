//
// Created by awalol on 2026/3/5.
//

#ifndef DS5_BRIDGE_AUDIO_H
#define DS5_BRIDGE_AUDIO_H

#include <cstdint>

void audio_init();
bool audio_profile_chime();
void audio_loop();
extern bool spk_active;
void audio_reset_stream();
void audio_rear_link_disconnected();
void audio_rear_sync();
uint32_t audio_rear_request(uint8_t operation, uint32_t attempt, uint32_t revision,
                            uint32_t link_epoch, uint32_t generation, uint32_t sequence);
void audio_usb_session_reset();
void audio_usb_playback_alt(uint8_t alt);
void audio_usb_playback_invalidate();
void audio_diagnostic_usb_playback(uint8_t *data);
bool audio_strip_speaker_payload(uint8_t *report, uint16_t length, bool native);
bool audio_prepare_sleep();
bool audio_processing_active();
bool audio_haptics_stream_active();
bool audio_rear_idle_for_settings();
uint8_t audio_diagnostic_route();
void audio_diagnostic_snapshot(uint8_t *data);
uint32_t audio_diagnostic_haptics_packet();
void core1_entry();
void set_headset(bool state);
void set_mic_active(bool active);
void audio_mic_policy_changed();
bool audio_mic_active();
void mic_add_queue(uint8_t *data, uint16_t len);
void update_mic_status();

#endif //DS5_BRIDGE_AUDIO_H
