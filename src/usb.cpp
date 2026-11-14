//
// Created by awalol on 2026/3/4.
//

#include <algorithm>

#include "bt.h"
#include "tusb.h"
#include "bsp/board_api.h"
#include "config.h"
#include "state_mgr.h"
#include "usb.h"
#include "wake.h"
#include "pico/time.h"

namespace {
bool reconnect_pending = false;
uint32_t reconnect_at_ms = 0;
}

void usb_schedule_reconnect() {
    wake_note_usb_reconnect();
    if (usb_xinput_active() != (get_config().usb_gamepad_mode == 1)) state_rumble_reset();
    tud_disconnect();
    reconnect_at_ms = to_ms_since_boot(get_absolute_time()) + 250;
    reconnect_pending = true;
}

void usb_cancel_reconnect() { reconnect_pending = false; }
bool usb_reconnect_pending() { return reconnect_pending; }

void usb_reconnect_task() {
    if (reconnect_pending &&
        static_cast<int32_t>(to_ms_since_boot(get_absolute_time()) - reconnect_at_ms) >= 0) {
        reconnect_pending = false;
        usb_select_host_mode();
        tud_connect();
    }
}

uint8_t mute[2]; // 0: SPEAKER(0x02) 1: MIC(0x05)
float volume[2] = {-100.0f,0.0f}; // 0: SPEAKER(0x02) 1: MIC(0x05)

#define UAC1_ENTITY_SPK_FEATURE_UNIT    0x02
#define UAC1_ENTITY_MIC_FEATURE_UNIT    0x05

// UAC1 transmits signed dB in units of 1/256 dB.
static constexpr int speaker_volume_span = 100 * 256;
static constexpr int controller_volume_max = 127;

static uint8_t speaker_level_from_usb(int16_t db_q8) {
    const int offset = std::clamp(speaker_volume_span + db_q8, 0, speaker_volume_span);
    return (offset * controller_volume_max + speaker_volume_span / 2) / speaker_volume_span;
}

static int16_t speaker_level_to_usb(uint8_t level) {
    const int clamped = std::min<int>(level, controller_volume_max);
    return (clamped * speaker_volume_span + controller_volume_max / 2) / controller_volume_max -
           speaker_volume_span;
}

/*int main() {
    board_init();

    tusb_rhport_init_t dev_init = {
        .role = TUSB_ROLE_DEVICE,
        .speed = TUSB_SPEED_AUTO
    };
    tusb_init(BOARD_TUD_RHPORT, &dev_init);

    board_init_after_tusb();

    while (1) {
        tud_task();
    }
}*/

//--------------------------------------------------------------------+
// Audio Callback Functions
//--------------------------------------------------------------------+

//--------------------------------------------------------------------+
// UAC1 Helper Functions
//--------------------------------------------------------------------+

static bool audio10_set_req_entity(tusb_control_request_t const *p_request, uint8_t *pBuff) {
    uint8_t channelNum = TU_U16_LOW(p_request->wValue);
    uint8_t ctrlSel = TU_U16_HIGH(p_request->wValue);
    uint8_t entityID = TU_U16_HIGH(p_request->wIndex);
    uint8_t index = entityID == UAC1_ENTITY_SPK_FEATURE_UNIT ? 0 : 1;

    // If request is for our speaker feature unit
    if (entityID == UAC1_ENTITY_SPK_FEATURE_UNIT || entityID == UAC1_ENTITY_MIC_FEATURE_UNIT) {
        switch (ctrlSel) {
            case AUDIO10_FU_CTRL_MUTE:
                switch (p_request->bRequest) {
                    case AUDIO10_CS_REQ_SET_CUR:
                        // Only 1st form is supported
                        TU_VERIFY(p_request->wLength == 1);

                        mute[index] = pBuff[0];

                        TU_LOG2("    Set Mute: %d of entity: %u\r\n", mute[index], entityID);
                        return true;

                    default:
                        return false; // not supported
                }

            case AUDIO10_FU_CTRL_VOLUME:
                switch (p_request->bRequest) {
                    case AUDIO10_CS_REQ_SET_CUR: {
                        // Only 1st form is supported
                        TU_VERIFY(p_request->wLength == 2);

                        const auto db_q8 = static_cast<int16_t>(pBuff[0] | (uint16_t(pBuff[1]) << 8));
                        if (index == 0) {
                            auto &c = get_config();
                            if (c.lock_volume) return true;
                            const auto level = speaker_level_from_usb(db_q8);
                            c.speaker_volume = level;
                            if (c.sync_spk_headset_volume) c.headset_volume = level;
                            set_volume(c.speaker_volume, c.headset_volume);
                            volume[index] = speaker_level_to_usb(level) / 256.0f;
                        } else {
                            volume[index] = std::clamp(db_q8 / 256.0f, 0.0f, 48.0f);
                        }

                        TU_LOG2("    Set Volume: %d dB of entity: %u\r\n", static_cast<int>(volume[index]), entityID);
                        return true;
                    }

                    default:
                        return false; // not supported
                }

            // Unknown/Unsupported control
            default:
                TU_BREAKPOINT();
                return false;
        }
    }

    return false;
}

static bool audio10_get_req_entity(uint8_t rhport, tusb_control_request_t const *p_request) {
    uint8_t channelNum = TU_U16_LOW(p_request->wValue);
    uint8_t ctrlSel = TU_U16_HIGH(p_request->wValue);
    uint8_t entityID = TU_U16_HIGH(p_request->wIndex);
    uint8_t index = entityID == UAC1_ENTITY_SPK_FEATURE_UNIT ? 0 : 1;

    // If request is for our speaker feature unit
    if (entityID == UAC1_ENTITY_SPK_FEATURE_UNIT || entityID == UAC1_ENTITY_MIC_FEATURE_UNIT) {
        switch (ctrlSel) {
            case AUDIO10_FU_CTRL_MUTE:
                // Audio control mute cur parameter block consists of only one byte - we thus can send it right away
                // There does not exist a range parameter block for mute
                TU_LOG2("    Get Mute of entity: %u\r\n", entityID);
                return tud_audio_buffer_and_schedule_control_xfer(rhport, p_request, &mute[index], 1);

            case AUDIO10_FU_CTRL_VOLUME:
                switch (p_request->bRequest) {
                    case AUDIO10_CS_REQ_GET_CUR:
                        TU_LOG2("    Get Volume of entity: %u\r\n", entityID); {
                            int16_t vol = index == 0 ? speaker_level_to_usb(get_config().speaker_volume) :
                                static_cast<int16_t>(volume[index] * 256);
                            return tud_audio_buffer_and_schedule_control_xfer(rhport, p_request, &vol, sizeof(vol));
                        }

                    case AUDIO10_CS_REQ_GET_MIN:
                        TU_LOG2("    Get Volume min of entity: %u\r\n", entityID); {
                            uint8_t min[2];
                            if (entityID == UAC1_ENTITY_SPK_FEATURE_UNIT) {
                                min[0] = 0x00;
                                min[1] = 0x9c;
                            }else {
                                min[0] = 0x00;
                                min[1] = 0x00;
                            }
                            return tud_audio_buffer_and_schedule_control_xfer(rhport, p_request, &min, sizeof(min));
                        }

                    case AUDIO10_CS_REQ_GET_MAX:
                        TU_LOG2("    Get Volume max of entity: %u\r\n", entityID); {
                            uint8_t max[2];
                            if (entityID == UAC1_ENTITY_SPK_FEATURE_UNIT) {
                                max[0] = 0x00;
                                max[1] = 0x00;
                            }else {
                                max[0] = 0x00;
                                max[1] = 0x30;
                            }
                            return tud_audio_buffer_and_schedule_control_xfer(rhport, p_request, &max, sizeof(max));
                        }

                    case AUDIO10_CS_REQ_GET_RES:
                        TU_LOG2("    Get Volume res of entity: %u\r\n", entityID); {
                            uint8_t res[2];
                            if (entityID == UAC1_ENTITY_SPK_FEATURE_UNIT) {
                                res[0] = 0x00;
                                res[1] = 0x01;
                            }else {
                                res[0] = 0x7a;
                                res[1] = 0x00;
                            }
                            return tud_audio_buffer_and_schedule_control_xfer(rhport, p_request, &res, sizeof(res));
                        }
                    // Unknown/Unsupported control
                    default:
                        TU_BREAKPOINT();
                        return false;
                }
                break;

            // Unknown/Unsupported control
            default:
                TU_BREAKPOINT();
                return false;
        }
    }

    return false;
}

// Invoked when audio class specific get request received for an entity
bool tud_audio_get_req_entity_cb(uint8_t rhport, tusb_control_request_t const *p_request) {
    (void) rhport;

    return audio10_get_req_entity(rhport, p_request);
}

// Invoked when audio class specific set request received for an entity
bool tud_audio_set_req_entity_cb(uint8_t rhport, tusb_control_request_t const *p_request, uint8_t *buf) {
    (void) rhport;

    return audio10_set_req_entity(p_request, buf);
}

void tud_hid_report_complete_cb(uint8_t instance, uint8_t const *report, uint16_t len) {
    (void) instance;
    (void) len;
}

#ifndef ENABLE_WAKE_HID

void tud_suspend_cb(bool remote_wakeup_en) {
    printf("[USB PM] invoke tud_suspend_cb\n");
    if (!get_config().enable_wake) return; // wake off: leave the controller's BT alone on a USB suspend (see wake.cpp)
    bt_power_off_controller();
}

#endif

// Event-only vendor collection: no command reply buffers or flash writes.
#include "macro.h"
#include <cstring>
namespace {
bool profile_event_subscribed = false;
uint8_t profile_event_data[15] = {'S','L','P','1',1};
uint8_t profile_event_state[6] = {255,255,255,255,255,255};
uint32_t profile_event_seq = 0, profile_event_next = 0, profile_event_lease = 0;
bool profile_event_pending = false, profile_event_slot_dirty = false;
}
void usb_profile_event_slot_saved() { profile_event_slot_dirty = true; }
uint16_t usb_profile_event_get(uint8_t *buffer, uint16_t length) {
    if (length < sizeof(profile_event_data)) return 0;
    profile_event_subscribed = true;
    profile_event_lease = to_ms_since_boot(get_absolute_time());
    profile_event_pending = true;
    memcpy(buffer, profile_event_data, sizeof(profile_event_data));
    return sizeof(profile_event_data);
}
void usb_profile_event_task() {
    if (!profile_event_subscribed || usb_served_idle_pid() || usb_reconnect_pending()) return;
    const uint32_t now = to_ms_since_boot(get_absolute_time());
    if (now - profile_event_lease >= 65000) { profile_event_subscribed = false; return; }
    if (static_cast<int32_t>(now - profile_event_next) >= 0) {
        profile_event_next = now + 100;
        uint8_t slot; bool edited;
        active_profile_get(slot, edited, nullptr);
        const auto &cfg = get_config();
        const uint8_t state[6] = {slot, uint8_t(edited), cfg.auto_haptics_enable,
#ifdef ENABLE_WAKE_HID
            uint8_t(macro_uses_mute_button()),
#else
            0,
#endif
            cfg.mix_native_level, cfg.ah_dsp_source
        };
        if (profile_event_slot_dirty || memcmp(state, profile_event_state, sizeof(state))) {
            profile_event_slot_dirty = false;
            memcpy(profile_event_state, state, sizeof(state));
            ++profile_event_seq;
            memcpy(profile_event_data + 5, &profile_event_seq, 4);
            // Keep the v1 wire layout. New clients read the extra state via 0x67.
            memcpy(profile_event_data + 9, state, 4);
            profile_event_pending = true;
        }
    }
    if (profile_event_pending && tud_hid_ready() &&
        tud_hid_report(0x8f, profile_event_data, sizeof(profile_event_data)))
        profile_event_pending = false;
}
