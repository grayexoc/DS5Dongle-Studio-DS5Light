#include "storage_redo.h"
//
// Created by awalol on 2026/5/4.
//

#include "config.h"
#include <cstddef>
#include "flash_map.h"
#include "macro.h"
#include "audio.h"
#include "pico/time.h"

#include <cmath>
#include <cstring>

#include "state_mgr.h"
#include "usb.h"
#include "utils.h"
#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/cyw43_arch.h"
#include "pico/flash.h"

constexpr uint32_t CONFIG_MAGIC = 0x66ccff00;
constexpr uint16_t CONFIG_VERSION = 22;
// btstack's TLV flash bank (BT link keys + this project's pairing blacklist tag)
// occupies the LAST TWO flash sectors by pico-sdk default
// (PICO_FLASH_BANK_STORAGE_OFFSET) - and config + profile slots used to sit in
// those exact sectors. Every TLV write (link-key churn on controller
// sleep/wake/re-pair) could clobber them; the first visible casualty was profile
// slot 0 reading "empty" after a sleep/wake cycle. Retain the relocated -3
// config as a read-only import source. New settings use the A/B journal below
// the fixed slot reservation and macro sector (see flash_map.h).
constexpr uint32_t CONFIG_FLASH_OFFSET        = PICO_FLASH_SIZE_BYTES - 3 * FLASH_SECTOR_SIZE;
constexpr uint32_t LEGACY_CONFIG_FLASH_OFFSET = PICO_FLASH_SIZE_BYTES - FLASH_SECTOR_SIZE;
static Config config{};
static bool activation_save_pending = false;
static uint32_t activation_retry_at_ms = 0;
static uint32_t activation_idle_since_ms = 0;
static bool activation_idle_tracking = false;
static uint8_t activation_save_attempts = 0;
bool is_dse = false;

// 编译期保护
// 判断Config结构体是否能放进flash 256bytes
// The binding limit is NOT the flash page - the sector is erased whole and the
// write length now follows the struct. It is the SLOT stride: every slot stores a
// Config_body, eight to a 4 KB sector, so a body larger than the stride minus the
// record's own header cannot be saved to a slot at all.
static_assert(sizeof(Config_body) <= SLOT_MAX_BODY_LEN,
              "Config_body must still fit a profile slot - drop SLOTS_PER_SECTOR to 4 first");
// 配置区起始地址必须按 flash sector 对齐。
static_assert(CONFIG_FLASH_OFFSET % FLASH_SECTOR_SIZE == 0);

uint32_t calc_config_crc(const Config &con) {
    return crc32(reinterpret_cast<const uint8_t *>(&con.body), sizeof(Config_body));
}

const Config *flash_config() {
    return reinterpret_cast<const Config *>(XIP_BASE + CONFIG_FLASH_OFFSET);
}

static void config_body_valid(Config_body &value);

void config_valid() {
    // valid config and set default value
    if (config.magic != CONFIG_MAGIC) {
        config.magic = CONFIG_MAGIC;
        printf("[Config] Config Magic Header is invalid\n");
    }
    if (config.size != sizeof(Config_body)) {
        config.size = sizeof(Config_body);
        printf("[Config] Config Body size is invalid\n");
    }
    config_body_valid(config.body);
}

static void config_body_valid(Config_body &value) {
    auto body = &value;
    if (std::isnan(body->haptics_gain) || body->haptics_gain < 1.0f || body->haptics_gain > 2.0f) {
        body->haptics_gain = 1.0f;
        printf("[Config] Haptics Gain value is invalid\n");
    }
    if (body->speaker_volume < 0 || body->speaker_volume > 127) {
        body->speaker_volume = 100;
        printf("[Config] Speaker Volume is invalid\n");
    }
    if (body->headset_volume < 0 || body->headset_volume > 127) {
        body->headset_volume = 100;
        printf("[Config] Headset Volume is invalid\n");
    }
    if (body->sync_spk_headset_volume > 1) {
        body->sync_spk_headset_volume = 1;
        printf("[Config] sync_spk_headset_volume is invalid\n");
    }
    if (body->speaker_gain < 0 || body->speaker_gain > 7) {
        body->speaker_gain = 2;
        printf("[Config] speaker_gain is invalid\n");
    }
    if (body->inactive_time < 5 || body->inactive_time > 60) {
        body->inactive_time = 30;
        printf("[Config] Inactive time is invalid\n");
    }
    if (body->disable_inactive_disconnect > 1) {
        body->disable_inactive_disconnect = 0;
        printf("[Config] disable_auto_disconnect is invalid\n");
    }
    if (body->disable_pico_led > 1) {
        body->disable_pico_led = 0;
        printf("[Config] disable_pico_led is invalid\n");
    }
    if (body->polling_rate_mode > 2) {
        body->polling_rate_mode = 0;
        printf("[Config] polling_rate_mode is invalid\n");
    }
    if (body->audio_buffer_length < 16 || body->audio_buffer_length > 128) {
        body->audio_buffer_length = 64;
        printf("[Config] haptics_buffer_length is invalid\n");
    }
    if (body->controller_mode > 2) {
        body->controller_mode = 2;
        printf("[Config] controller_mode is invalid\n");
    }
    if (body->config_version != CONFIG_VERSION) {
        body->config_version = CONFIG_VERSION;
        printf("[Config] Warning: Config may breaking change\n");
    }
    if (body->lock_volume > 1) {
        body->lock_volume = 0;
        printf("[Config] lock_volume is invalid\n");
    }
    if (body->disable_usb_sn > 1) {
        body->disable_usb_sn = 0;
        printf("[Config] Warning: disable_usb_sn is invalid\n");
    }
    if (body->ps_shortcut_enabled > 1) {
        body->ps_shortcut_enabled = 0;
        printf("[Config] ps_shortcut_enabled is invalid\n");
    }
    if (body->disable_mic > 1) {
        body->disable_mic = 0;
        printf("[Config] disable_mic is invalid\n");
    }
    if (body->disable_speaker > 1) {
        body->disable_speaker = 0;
        printf("[Config] disable_speaker is invalid\n");
    }
    if (body->auto_haptics_enable > 2) body->auto_haptics_enable = 0;
    if (body->auto_haptics_gain > 200) body->auto_haptics_gain = 100; // 0 is a VALID value (silence); >200 covers fresh-flash 0xFF
    if (body->auto_haptics_lowpass_hz < 20 || body->auto_haptics_lowpass_hz > 400) body->auto_haptics_lowpass_hz = 60;
    if (body->auto_mute_replace > 1) body->auto_mute_replace = 1;
    if (body->auto_mute_mix > 1) body->auto_mute_mix = 0;
    if (body->auto_haptics_gate > 100) body->auto_haptics_gate = 20;
    if (body->auto_haptics_slope != 6 && body->auto_haptics_slope != 12 && body->auto_haptics_slope != 24) body->auto_haptics_slope = 12;
    if (body->lightbar_off > 1) body->lightbar_off = 0;
    if (body->lightbar_fixed > 1) body->lightbar_fixed = 0;
    if (body->rumble_gain < 100 || body->rumble_gain > 200) body->rumble_gain = 100;
    if (body->rumble_release > 2) body->rumble_release = 0;
    if (body->rumble_mode > 2) body->rumble_mode = 0;
    if (body->usb_gamepad_mode > 1) body->usb_gamepad_mode = 0;
    if (body->auto_haptics_smooth > 100) body->auto_haptics_smooth = 40;
    // Staged battery notification. An upgraded config arrives with this tail
    // 0xFF-filled, so every value has to be clamped into range rather than
    // trusted - 0xFF blinks would flash for eight minutes.
    if (body->batt_notify_enable > 1) body->batt_notify_enable = 0;
    if (body->touch_mouse > 1) body->touch_mouse = 0;
    if (body->tilt_steer > 1) body->tilt_steer = 0;
    if (body->tilt_steer_range == 0 || body->tilt_steer_range > 90) body->tilt_steer_range = 45;
    // 70, not 25. At 25 the offset never clears a racing game's own steering
    // dead zone, so the feature looked broken while working exactly as written.
    // Below roughly 60 nothing of consequence happens.
    if (body->tilt_steer_amount > 100) body->tilt_steer_amount = 70;
    if (body->tilt_steer_deadzone > 30) body->tilt_steer_deadzone = 3;
    if (body->tilt_steer_invert > 1) body->tilt_steer_invert = 0;
    if (body->tilt_steer_y > 1) body->tilt_steer_y = 0;
    if (body->tilt_steer_y_amount > 100) body->tilt_steer_y_amount = 70;
    if (body->tilt_steer_y_invert > 1) body->tilt_steer_y_invert = 0;
    if (body->flick_angle == 0 || body->flick_angle > 180) body->flick_angle = 90;
    if (body->player_led_mode > 2) body->player_led_mode = 0;
    if (body->player_led_bright > 3) body->player_led_bright = 0;
    if (body->trigger_reduce > 10) body->trigger_reduce = 0;
    if (body->touch_mouse_sens == 0 || body->touch_mouse_sens > 250) body->touch_mouse_sens = 100;
    if (body->touch_mouse_min > 20) body->touch_mouse_min = 1;
    if (body->touch_mouse_invert > 3) body->touch_mouse_invert = 0;
    if (body->touch_mouse_trackball > 1) body->touch_mouse_trackball = 0;
    if (body->touch_mouse_friction == 0 || body->touch_mouse_friction > 100) body->touch_mouse_friction = 10;
    for (int i = 0; i < 3; i++) {
        if (body->batt_stage_level[i] > 10)  body->batt_stage_level[i] = 0;   // 0 = stage off
        if (body->batt_stage_blinks[i] > 20) body->batt_stage_blinks[i] = 5;
        if (body->batt_stage_blinks[i] == 0) body->batt_stage_blinks[i] = 5;
        if (body->batt_stage_on[i] > 1) body->batt_stage_on[i] = 0;
    }
    if (body->bt_flush_timeout > 0x07FF) body->bt_flush_timeout = 0; // 0=off, max per BT spec
    if (body->bt_qos_latency_us > 50000) body->bt_qos_latency_us = 0; // 0=off
    if (body->rumble_haptic_strength > 200) body->rumble_haptic_strength = 100; // >100 = deliberate overdrive
    if (body->effect_leak_volume > 100) body->effect_leak_volume = 0; // 0=off
    if (body->effect_leak_hp_hz < 100 || body->effect_leak_hp_hz > 5000) body->effect_leak_hp_hz = 800;
    if (body->effect_leak_sensitivity > 100) body->effect_leak_sensitivity = 50;
    if (body->effect_leak_decay > 100) body->effect_leak_decay = 40;
    if (body->effect_leak_attack > 100) body->effect_leak_attack = 50;
    if (body->effect_leak_output_hp_hz < 50 || body->effect_leak_output_hp_hz > 2000) body->effect_leak_output_hp_hz = 200;
    // Rumble-to-trigger defaults (feature OFF by default).
    if (body->at_pushback > 100) body->at_pushback = 0;     // 0=off (fresh flash 0xFF lands here)
    if (body->at_pushback_src > 2) body->at_pushback_src = 2;
    if (body->at_pushback_freq < 10 || body->at_pushback_freq > 200) body->at_pushback_freq = 35; // fresh flash 0xFF lands here
    // Leak band-pass window + hold defaults (fresh flash 0xFF/0xFFFF lands here).
    if (body->effect_leak_lp_hz < 500 || body->effect_leak_lp_hz > 12000) body->effect_leak_lp_hz = 8000; // default raised in 1.5.2: 3500 gutted perceived loudness (tiny speaker is loudest 3-8 kHz)
    if (body->effect_leak_hold > 100) body->effect_leak_hold = 20; // x5 = 100 ms default
    if (body->at_kick_style > 1) body->at_kick_style = 0;          // R2 kick: vibration thump
    if (body->at_l2_mode > 3) body->at_l2_mode = 0;                 // 0=off,1=R2-gated,2=always,3=R1-shoulder-gated
    if (body->at_l2_strength > 100) body->at_l2_strength = 70;
    if (body->at_l2_threshold < 1) body->at_l2_threshold = 30;      // ~12% pull arms it
    if (body->at_l2_start_pos > 9) body->at_l2_start_pos = 0;
    if (body->at_l2_pushback > 100) body->at_l2_pushback = 0;       // 0 = no kick on L2
    if (body->at_l2_pushback_freq < 10 || body->at_l2_pushback_freq > 200) body->at_l2_pushback_freq = 35;
    if (body->at_l2_kick_style > 1) body->at_l2_kick_style = 0;
    // Frequency split: 0=off. Out-of-range values CLAMP to the nearest bound
    // instead of silently disabling the feature (a user entering 500 previously
    // got split=off with no feedback and concluded the gains did nothing).
    // 0xFFFF (fresh flash) still lands on off via the upper clamp exception.
    if (body->ah_xover_hz != 0) {
        if (body->ah_xover_hz == 0xFFFF) body->ah_xover_hz = 0;          // fresh flash
        else if (body->ah_xover_hz < 30)  body->ah_xover_hz = 30;
        else if (body->ah_xover_hz > 200) body->ah_xover_hz = 200;
    }
    if (body->ah_low_gain > 100) body->ah_low_gain = 100;
    if (body->ah_high_gain > 100) body->ah_high_gain = 100;
    // Trigger resistance shapes (fresh flash 0xFF lands on defaults)
    if (body->at_shape > 3) body->at_shape = 0;    // 3 = weapon break (v1.12.0)
    if (body->at_strength_b > 100) body->at_strength_b = 70;
    if (body->at_detent_pos > 9) body->at_detent_pos = 5;
    if (body->at_l2_shape > 3) body->at_l2_shape = 0;
    if (body->at_l2_strength_b > 100) body->at_l2_strength_b = 70;
    if (body->at_l2_detent_pos > 9) body->at_l2_detent_pos = 5;
    if (body->at_deadzone > 9) body->at_deadzone = 0;
    if (body->at_l2_deadzone > 9) body->at_l2_deadzone = 0;
    if (body->mix_native_level > 100) body->mix_native_level = 0; // no native passthrough by default
    if (body->mix_native_filter > 1) body->mix_native_filter = 1;  // suppress mirrored audio when passthrough is enabled
    if (body->ah_dsp_source > 1) body->ah_dsp_source = 0;         // fresh flash (0xff) -> ch0/1, as before
    if (body->rstick_invert > 3) body->rstick_invert = 0;        // fresh flash (0xff) -> no inversion
    if (body->effect_leak_max_burst > 100) body->effect_leak_max_burst = 0; // 0=off; covers fresh-flash 0xFF
    // Custom captured-effect action (v1.14.0): validate scalar controls; state
    // bytes are raw (any value valid). Fresh-flash 0xFF -> safe defaults.
    if (body->ce_r2_enable > 1) body->ce_r2_enable = 0;
    if (body->ce_r2_condition > 2) body->ce_r2_condition = 0;
    if (body->ce_r2_thresh > 9) body->ce_r2_thresh = 0; // default: re-arm only at full release
    if (body->ce_r2_rate < 1 || body->ce_r2_rate > 100) body->ce_r2_rate = 40;
    if (body->ce_r2_state_count > 5) body->ce_r2_state_count = 0;
    if (body->ce_l2_enable > 1) body->ce_l2_enable = 0;
    if (body->ce_l2_condition > 2) body->ce_l2_condition = 0;
    if (body->ce_l2_thresh > 9) body->ce_l2_thresh = 0;
    if (body->ce_l2_rate < 1 || body->ce_l2_rate > 100) body->ce_l2_rate = 40;
    if (body->ce_l2_state_count > 5) body->ce_l2_state_count = 0;
    if (body->ce_r2_yield > 2) body->ce_r2_yield = 0;
    if (body->ce_l2_yield > 2) body->ce_l2_yield = 0;
    if (body->r2t_mode > 3) body->r2t_mode = 0;            // 0=off
    if (body->r2t_on_press > 1) body->r2t_on_press = 0;    // 0=always
    if (body->r2t_strength > 100) body->r2t_strength = 100; // full strength
    if (body->r2t_frequency < 1) body->r2t_frequency = 60;  // ~mid tactile buzz
    // Adaptive triggers Stage 1 defaults (OFF by default).
    if (body->at_mode > 3) body->at_mode = 0;   // 0=off,1=L2-gated,2=always,3=L1-shoulder-gated
    if (body->at_strength > 100) body->at_strength = 70;
    if (body->at_threshold < 1) body->at_threshold = 30;   // ~12% pull arms it
    if (body->at_start_pos > 9) body->at_start_pos = 0;    // resist from the start of travel
    // Gyro aiming defaults (OFF by default).
    if (body->gyro_mode > 7) body->gyro_mode = 0; // 5=R2, 6=L1, 7=R1 gates (v1.11.0)
    if (body->gyro_sens < 1 || body->gyro_sens > 100) body->gyro_sens = 50;
    // 2 = player space (accelerometer-derived). The clamp was still 1 when that
    // option was added, so selecting it was silently rewritten to yaw and the
    // new mode could never be tested - it behaved identically to the old one,
    // which is precisely what it looked like. Any new enum value has to move
    // this line with it.
    if (body->gyro_axis > 2) body->gyro_axis = 0;
    if (body->gyro_invert > 3) body->gyro_invert = 0;
    // Native-haptics smoothing: 0 is invalid so a fresh config defaults to Light (2).
    if (body->haptics_aa < 1 || body->haptics_aa > 3) body->haptics_aa = 1;
    if (body->synth_force > 1) body->synth_force = 0;
    // Two-stage triggers. A slot written before v1.21 reads back 0xFF here, so
    // the OFF default has to come from the clamp, not from the stored value.
    if ((body->t2_mode & T2_AXIS_MASK) > T2_AXIS_RESCALE ||
        (body->t2_mode & ~(T2_AXIS_MASK | T2_RELEASE_STAGE1))) body->t2_mode = 0;
    if ((body->t2_l2_mode & T2_AXIS_MASK) > T2_AXIS_RESCALE ||
        (body->t2_l2_mode & ~(T2_AXIS_MASK | T2_RELEASE_STAGE1))) body->t2_l2_mode = 0;
    if (body->t2_button >= T2BTN_COUNT) body->t2_button = T2BTN_NONE;
    if (body->gyro_sens_y > 100) body->gyro_sens_y = 0;   // 0 = follow X
    if (body->gyro_output > 2) body->gyro_output = 0;   // 0xFF fill from an older slot -> stick
    // Stick-to-mouse. Every one of these must be clamped here: a slot saved
    // before the fields existed carries 0xFF, and slot_activate() compares
    // CLAMPED values on both sides, so an unclamped byte would make every
    // activation of that slot look like a mouse-interface change.
    if (body->stick_mouse > 2) body->stick_mouse = 0;
    // NO 0xFF sentinel here: it made 255 - the fastest setting - silently mean
    // 0, i.e. the SLOWEST. The fill from an older slot is harmless anyway,
    // because stick_mouse itself clamps to 0 (off) in that slot, so the speed
    // is never used. 0 still means "use the default"; 1..255 are real speeds.
    if (body->stick_mouse_sens > 20000) body->stick_mouse_sens = 0;   // 0xFFFF fill -> default
    if (body->stick_mouse_sens_y > 20000) body->stick_mouse_sens_y = 0; // 0 = follow X
    // 0xFF is the fresh-flash fill, so this also picks the DEFAULT for a new
    // install: Natural, now that it is calibrated rather than nominal. An
    // existing profile stores its own 0 or 1 and is untouched.
    if (body->gyro_sens_mode > 1) body->gyro_sens_mode = 1;
    if (body->gyro_natural_x10 == 0 || body->gyro_natural_x10 == 0xFF) body->gyro_natural_x10 = 10; // 1.0x
    if (body->gyro_natural_y_x10 == 0xFF) body->gyro_natural_y_x10 = 0;  // 0 = follow X
    if (body->gyro_scale_trim_x100 == 0 || body->gyro_scale_trim_x100 > 1000) body->gyro_scale_trim_x100 = 100;
    if (body->stick_mouse_deadzone > 50) body->stick_mouse_deadzone = 8;
    if (body->stick_mouse_curve == 0xFF || body->stick_mouse_curve < 10 ||
        body->stick_mouse_curve > 40) body->stick_mouse_curve = 18;
    if (body->stick_mouse_invert > 3) body->stick_mouse_invert = 0;
    // Flick Stick also owns the right stick. Two owners would both write the
    // report and both centre it; the explicit stick mode yields, since it is
    // the one the user just chose from a list that names the conflict.
    if (body->gyro_output == 2 && body->stick_mouse == 1) body->stick_mouse = 0;
    // Flick calibration. Anything outside a plausible range - including 0, and
    // including the 0xFFFF an older slot's tail fill produces - becomes a usable
    // default rather than disabling the flick. A zero here meant selecting
    // "Mouse + Flick Stick" did nothing at all until a second, separate field was
    // also set, which reads as the feature being broken. The MODE selector is
    // what turns the flick on; this only decides how far it turns.
    if (body->flick_counts_360 < 500 || body->flick_counts_360 > 50000) {
        body->flick_counts_360 = 6500;   // ~40cm/360 at 400 dpi; mid-range start
    }
    if (body->t2_l2_button >= T2BTN_COUNT) body->t2_l2_button = T2BTN_NONE;
    // pos 0 disables the stage; 0xFF from an old slot would put the boundary at
    // the very top of travel, which is indistinguishable from unreachable.
    if (body->t2_pos == 0xFF) body->t2_pos = 0;
    if (body->t2_l2_pos == 0xFF) body->t2_l2_pos = 0;
    if (body->enable_wake > 1) {
        body->enable_wake = 0;
        printf("[Config] enable_wake is invalid\n");
    }
}

static void migrate_legacy_slots(); // defined after the slot machinery below

// One-shot migration from the legacy (btstack-bank-colliding) locations. Runs at
// boot before BT init, so the bank cannot be mid-write while we read. Strict CRC
// validation: anything the TLV bank already clobbered is skipped (unrecoverable).
static void migrate_legacy_storage() {
    // Active-config recovery is read-only in config_load; never overwrite a
    // corrupt record merely by booting. Slot migration keeps its own CRC gate.
    // Slot migration lives after the slot machinery is defined.
    migrate_legacy_slots();
}

// Self-describing journal: header CRC protects the sequence/length/body CRC,
// and the body CRC protects exactly the stored span across future tail growth.
constexpr uint32_t CONFIG_JOURNAL_MAGIC = 0x32474643; // "CFG2"
struct __attribute__((packed)) ConfigJournalHeader {
    uint32_t magic;
    uint32_t sequence;
    uint16_t body_bytes;
    uint16_t format;
    uint32_t body_crc;
    uint32_t header_crc;
};
static_assert(sizeof(ConfigJournalHeader) == 20);
// Device policy lives in the CRC-protected journal metadata, outside slots.
static constexpr uint32_t DORMANT_POLICY_BIT = 0x80000000u;
static constexpr uint32_t DOCK_DISCONNECT_BIT = 0x20000000u;
static constexpr uint32_t DEVICE_POLICY_MASK = DORMANT_POLICY_BIT | DOCK_DISCONNECT_BIT;
static bool dormant_policy = false;
static bool dock_disconnect_policy = false;
bool device_auto_dormant() { return dormant_policy; }


struct __attribute__((packed)) ConfigProfileIdentity {
    uint32_t tagged_slot;
    uint32_t fingerprint;
    uint32_t crc;
};
constexpr uint32_t CONFIG_PROFILE_TAG = 0x534c0000;
static_assert((CONFIG_PROFILE_TAG & DEVICE_POLICY_MASK) == 0);
static_assert(sizeof(ConfigProfileIdentity) == 12);

static const ConfigJournalHeader *config_journal_read(uint32_t offset) {
    const auto *header = reinterpret_cast<const ConfigJournalHeader *>(XIP_BASE + offset);
    if (header->magic != CONFIG_JOURNAL_MAGIC || header->format != 1 ||
        header->body_bytes == 0 || header->body_bytes > sizeof(Config_body) ||
        header->header_crc != crc32(reinterpret_cast<const uint8_t *>(header),
                                   offsetof(ConfigJournalHeader, header_crc))) return nullptr;
    const auto *body = reinterpret_cast<const uint8_t *>(header) + sizeof(*header);
    if (body[0] == 0 || body[0] > CONFIG_VERSION ||
        header->body_crc != crc32(body, header->body_bytes)) return nullptr;
    return header;
}

static const ConfigJournalHeader *config_journal_latest(uint32_t &offset) {
    const auto *a = config_journal_read(CONFIG_JOURNAL_A_OFFSET);
    const auto *b = config_journal_read(CONFIG_JOURNAL_B_OFFSET);
    if (b && (!a || static_cast<int32_t>(b->sequence - a->sequence) > 0)) {
        offset = CONFIG_JOURNAL_B_OFFSET;
        return b;
    }
    offset = a ? CONFIG_JOURNAL_A_OFFSET : 0;
    return a;
}

// Optional trailer: older journal readers still understand the header/body.
// Corrupt/missing identity never invalidates an otherwise valid settings body.
static bool config_journal_identity(const ConfigJournalHeader *header, ConfigProfileIdentity &identity) {
    if (!header) return false;
    memcpy(&identity, reinterpret_cast<const uint8_t *>(header) + sizeof(*header) +
           header->body_bytes, sizeof(identity));
    if (identity.crc != (crc32(reinterpret_cast<const uint8_t *>(&identity),
                              offsetof(ConfigProfileIdentity, crc)) ^
                         header->sequence ^ header->body_crc)) return false;
    const uint32_t tag = identity.tagged_slot & ~DEVICE_POLICY_MASK;
    return (tag == 0 && identity.fingerprint == 0) ||
        ((tag & 0xffffff00u) == CONFIG_PROFILE_TAG &&
         (identity.tagged_slot & 0xffu) < SLOT_COUNT);
}

static Config_body boot_config_body;

static bool recovery_ok = false;
static void recover_storage(void *) {
    const auto irq = save_and_disable_interrupts();
    recovery_ok = storage_redo_recover();
    restore_interrupts(irq);
}
void config_load() {
    // Boot only: core1 is not launched until audio_init(), after config_load().
    recover_storage(nullptr);
    if (!recovery_ok) panic("Profile storage recovery failed");
    auto adopt = [](const Config *record) {
        // Old layouts CRC the original stored body span, not today's tail.
        const uint16_t bytes = record->size;
        if (record->magic != CONFIG_MAGIC || bytes == 0 ||
            bytes > sizeof(Config_body) || record->body.config_version == 0 ||
            record->body.config_version > CONFIG_VERSION ||
            record->crc32 != crc32(reinterpret_cast<const uint8_t *>(&record->body), bytes))
            return false;
        memset(&config, 0xff, sizeof(config));
        config.magic = CONFIG_MAGIC;
        config.size = sizeof(Config_body);
        memcpy(&config.body, &record->body, bytes);
        return true;
    };
    uint32_t journal_offset;
    const auto *journal = config_journal_latest(journal_offset);
    if (journal) {
        memset(&config, 0xff, sizeof(config));
        config.magic = CONFIG_MAGIC;
        config.size = sizeof(Config_body);
        memcpy(&config.body, reinterpret_cast<const uint8_t *>(journal) + sizeof(*journal),
               journal->body_bytes);
    } else if (!adopt(flash_config()) &&
        !adopt(reinterpret_cast<const Config *>(XIP_BASE + LEGACY_CONFIG_FLASH_OFFSET))) {
        // Explicit defaults, while preserving damaged Flash for recovery.
        memset(&config, 0xff, sizeof(config));
        printf("[Config] No valid CRC record; using RAM defaults\n");
    }
    config_valid();
    if (!journal) boot_config_body = config.body;
    migrate_legacy_storage();
    ConfigProfileIdentity identity{};
    const bool identity_valid = config_journal_identity(journal, identity);
    dormant_policy = identity_valid && (identity.tagged_slot & DORMANT_POLICY_BIT);
    dock_disconnect_policy = identity_valid && (identity.tagged_slot & DOCK_DISCONNECT_BIT);
    if (identity_valid && (identity.tagged_slot & ~DEVICE_POLICY_MASK) != 0) {
        // Restore the name/baseline only; leave the loaded live settings intact.
        active_profile_restore(static_cast<uint8_t>(identity.tagged_slot), identity.fingerprint);
    }
}

// Runs with core1 parked (flash_safe_execute) and core0 interrupts disabled, so
// neither core touches XIP flash while the sector is erased/programmed. Without
// the core1 park this races the audio core and corrupts audio (buzzing).
// Program the journal header and body rounded up to whole pages. The old writer
// used a hard-coded single page, which is why Config_body could
// not grow past 246 bytes even though the sector has 4 KB and the slot records
// have room for far more.
//
// THE TRAP, and it is not hypothetical - a downstream fork hit it: relaxing the
// size assert WITHOUT widening this write leaves the tail of the struct never
// written. Settings then apply live and silently revert on the next boot, which
// looks like anything except a flash bug. The assert below and this length must
// move together.
constexpr uint32_t CONFIG_WRITE_LEN =
    ((sizeof(ConfigJournalHeader) + sizeof(Config_body) + sizeof(ConfigProfileIdentity) + FLASH_PAGE_SIZE - 1) /
     FLASH_PAGE_SIZE) * FLASH_PAGE_SIZE;
static_assert(CONFIG_WRITE_LEN >= sizeof(ConfigJournalHeader) + sizeof(Config_body) + sizeof(ConfigProfileIdentity));
static_assert(CONFIG_WRITE_LEN <= FLASH_SECTOR_SIZE, "config must fit its sector");
static uint32_t config_write_offset = CONFIG_JOURNAL_A_OFFSET;

static bool config_journal_fits_firmware() {
    extern const uint8_t __flash_binary_end[];
    return reinterpret_cast<uintptr_t>(__flash_binary_end) <=
           XIP_BASE + STORAGE_REDO_META;
}

static void config_save_flash_op(void *param) {
    const uint8_t *page = static_cast<const uint8_t *>(param);
    const uint32_t interrupts = save_and_disable_interrupts();
    flash_range_erase(config_write_offset, FLASH_SECTOR_SIZE);
    flash_range_program(config_write_offset, page, CONFIG_WRITE_LEN);
    restore_interrupts(interrupts);
}

static bool config_journal_write(const uint8_t *body, uint16_t bytes, ConfigProfileIdentity identity, uint32_t timeout_ms) {
    if (!config_journal_fits_firmware()) return false;
    const uint32_t body_crc = crc32(body, bytes);
    uint32_t latest_offset;
    const auto *stored = config_journal_latest(latest_offset);
    ConfigProfileIdentity previous_identity{};
    if (stored && stored->body_bytes == bytes &&
        stored->body_crc == body_crc &&
        memcmp(reinterpret_cast<const uint8_t *>(stored) + sizeof(*stored),
               body, bytes) == 0 &&
        config_journal_identity(stored, previous_identity) &&
        identity.tagged_slot == previous_identity.tagged_slot &&
        identity.fingerprint == previous_identity.fingerprint) {
        return true;
    }
    // Config saves run on core0 only; keep the flash page off the USB stack.
    alignas(4) static uint8_t page[CONFIG_WRITE_LEN];
    memset(page, 0xff, sizeof(page));
    ConfigJournalHeader header{};
    header.magic = CONFIG_JOURNAL_MAGIC;
    header.sequence = stored ? stored->sequence + 1 : 1;
    header.body_bytes = bytes;
    header.format = 1;
    header.body_crc = body_crc;
    header.header_crc = crc32(reinterpret_cast<const uint8_t *>(&header),
                             offsetof(ConfigJournalHeader, header_crc));
    memcpy(page, &header, sizeof(header));
    memcpy(page + sizeof(header), body, bytes);
    identity.crc = crc32(reinterpret_cast<const uint8_t *>(&identity),
                         offsetof(ConfigProfileIdentity, crc)) ^ header.sequence ^ header.body_crc;
    memcpy(page + sizeof(header) + bytes, &identity, sizeof(identity));
    // Never erase the latest validated copy. The legacy -3 record is untouched.
    config_write_offset = latest_offset == CONFIG_JOURNAL_A_OFFSET ?
                          CONFIG_JOURNAL_B_OFFSET : CONFIG_JOURNAL_A_OFFSET;

    const int rc = flash_safe_execute(config_save_flash_op, page, timeout_ms);
    if (rc != PICO_OK) {
        printf("[Config] config_save flash_safe_execute failed: %d\n", rc);
        return false;
    }

    const auto *verify = config_journal_read(config_write_offset);
    if (verify && verify->sequence == header.sequence &&
        verify->body_bytes == bytes && verify->body_crc == body_crc &&
        memcmp(reinterpret_cast<const uint8_t *>(verify) + sizeof(*verify),
               body, bytes) == 0 &&
        config_journal_identity(verify, previous_identity) &&
        memcmp(&identity, &previous_identity, sizeof(identity)) == 0) {
        printf("[Config] Config write flash verify success\n");
        return true;
    }
    printf("[Config] Config write flash verify failed\n");
    return false;
}

static bool config_save_impl(uint32_t timeout_ms) {
    config.crc32 = calc_config_crc(config);
    ConfigProfileIdentity identity{};
    uint8_t slot;
    uint32_t fingerprint;
    if (active_profile_resume_state(slot, fingerprint)) {
        identity.tagged_slot = CONFIG_PROFILE_TAG | slot;
        identity.fingerprint = fingerprint;
    }
    if (dormant_policy) identity.tagged_slot |= DORMANT_POLICY_BIT;
    if (dock_disconnect_policy) identity.tagged_slot |= DOCK_DISCONNECT_BIT;
    if (!config_journal_write(reinterpret_cast<const uint8_t *>(&config.body),
                              sizeof(Config_body), identity, timeout_ms)) return false;
    activation_save_pending = false;
    return true;
}

static bool save_device_policy(uint32_t bit, bool enabled, bool &policy) {
    if (enabled == policy) return true;
    if (audio_processing_active()) return false;

    uint32_t offset;
    const auto *stored = config_journal_latest(offset);
    ConfigProfileIdentity identity{};
    if (!config_journal_identity(stored, identity)) identity = {};
    identity.tagged_slot &= ~bit;
    if (enabled) identity.tagged_slot |= bit;
    // Keep the saved profile identity and settings, including older layouts.
    const auto *body = stored ? reinterpret_cast<const uint8_t *>(stored) + sizeof(*stored)
                              : reinterpret_cast<const uint8_t *>(&boot_config_body);
    const uint16_t bytes = stored ? stored->body_bytes : sizeof(boot_config_body);
    if (!config_journal_write(body, bytes, identity, 10)) return false;
    policy = enabled;
    return true;
}

bool device_set_auto_dormant(bool enabled) {
    return save_device_policy(DORMANT_POLICY_BIT, enabled, dormant_policy);
}

bool device_disconnect_on_dock() { return dock_disconnect_policy; }

bool device_set_disconnect_on_dock(bool enabled) {
    return save_device_policy(DOCK_DISCONNECT_BIT, enabled, dock_disconnect_policy);
}

bool config_save() { return config_save_impl(1000); }

static void config_defer_activation_save() {
    activation_save_pending = true;
    activation_save_attempts = 0;
    activation_idle_tracking = false;
    activation_retry_at_ms = to_ms_since_boot(get_absolute_time()) + 60;
}

void config_task() {
    if (!activation_save_pending || activation_save_attempts >= 3) return;
    const uint32_t now = to_ms_since_boot(get_absolute_time());
    if (audio_processing_active()) { activation_idle_tracking = false; return; }
    if (static_cast<int32_t>(now - activation_retry_at_ms) < 0) return;
    if (!activation_idle_tracking) {
        activation_idle_tracking = true;
        activation_idle_since_ms = now;
        return;
    }
    if (now - activation_idle_since_ms < 500) return;
    ++activation_save_attempts;
    if (!config_save_impl(10)) {
        activation_idle_tracking = false;
        activation_retry_at_ms = now + 1000;
    }
}

Config_body& get_config() {
    return config.body;
}

bool config_flush_pending_activation() {
    return !activation_save_pending || config_save();
}

bool config_activation_save_pending() { return activation_save_pending; }

void set_config(const uint8_t *new_config, const uint16_t len) {
    const auto copy_len = len < sizeof(Config_body) ? len : sizeof(Config_body);
    memmove(&config.body, new_config, copy_len);
    config_valid();
    if (config.body.disable_pico_led) {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, false);
    }else {
        cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, true);
    }
    set_volume(config.body.speaker_volume,config.body.headset_volume);
    set_gain(config.body.speaker_gain);
}

// ============================ Profile slots ================================
// One flash sector (4 KB), 8 records of 512 bytes each. Updating any slot
// rewrites the whole sector from a RAM image (flash erase granularity), using
// the same core1-parked flash_safe_execute path as config_save.
constexpr uint32_t SLOTS_FLASH_OFFSET        = PICO_FLASH_SIZE_BYTES - 4 * FLASH_SECTOR_SIZE;
constexpr uint32_t LEGACY_SLOTS_FLASH_OFFSET = PICO_FLASH_SIZE_BYTES - 2 * FLASH_SECTOR_SIZE;
static_assert(SLOTS_FLASH_OFFSET % FLASH_SECTOR_SIZE == 0);
constexpr uint32_t SLOT_STRIDE = FLASH_SECTOR_SIZE / SLOTS_PER_SECTOR; // 512
static_assert(SLOT_COUNT % SLOTS_PER_SECTOR == 0, "whole sectors only");
// Slots span multiple sectors (v1.9.0: 16 slots = 2 sectors). Sector 0 stays at
// the original -4 location so pre-existing slots 1-8 are preserved IN PLACE with
// no migration; additional sectors grow DOWNWARD (-5, -6, ...), away from the
// config sector (-3) and the btstack bank (-2/-1). Each sector is still erased
// and rewritten independently, so saving slot 12 never touches slots 1-8.
// The reservation and the macro sector anchor live in flash_map.h, which owns
// the whole top-of-flash map so no two regions can be declared into each other.
static constexpr uint32_t slot_sector_offset(uint8_t sector) {
    return slot_sector_offset_at(sector);
}

constexpr uint32_t SLOT_MAGIC_V1 = 0x53355344; // "DS5S" — legacy: fixed-size body, layout-fragile
constexpr uint32_t SLOT_MAGIC_V2 = 0x54355344; // "DS5T" — v2: explicit body_len, survives body growth

// v2 record: body_len makes the CRC span self-describing, so future firmware with
// a LARGER Config_body can still validate and read records written by older
// firmware (the missing tail bytes simply default via config_valid()). This is
// what keeps profile slots alive across firmware upgrades from now on.
struct __attribute__((packed)) SlotRecordV2 {
    uint32_t magic;      // SLOT_MAGIC_V2
    uint16_t body_len;   // sizeof(Config_body) at the time of writing
    uint8_t  name[SLOT_NAME_LEN];
    Config_body body;    // body_len bytes of it are meaningful
    uint32_t crc32;      // over name + body_len bytes of body, stored right after them
};
static_assert(sizeof(SlotRecordV2) <= SLOT_STRIDE, "slot record must fit its stride");

// Legacy v1 record (pre-1.4.0): magic, name, body (no length), crc right after.
// Its validity check hardcoded sizeof(Config_body), so any firmware whose body
// size differed silently saw "empty" slots. A previous fix listed the historical
// body sizes relative to sizeof(Config_body) - which silently went stale every
// time the config grew (it already had, by 1.5.0). Instead: brute-force the body
// length. A v1 record is name + body + crc32(name+body); we scan every plausible
// body length and accept the one whose CRC matches. Runs only for records bearing
// the v1 magic (which no firmware writes since 1.3.2), so in practice only during
// boot-time legacy migration - the scan cost (<500 CRC checks over <=0.5 KB) is a
// few milliseconds once, and it recovers records from ANY historical layout,
// forever, with zero maintenance.

static const uint8_t *flash_slot_raw_at(uint32_t base_offset, uint8_t idx) {
    return reinterpret_cast<const uint8_t *>(XIP_BASE + base_offset + idx * SLOT_STRIDE);
}
static const uint8_t *flash_slot_raw(uint8_t idx) {
    return flash_slot_raw_at(SLOTS_FLASH_OFFSET, idx);
}

// Unified reader: returns true and fills name/body if the slot holds a valid
// record in ANY known format. Missing tail bytes (older, smaller bodies) are
// 0xFF-filled so config_valid() lands them on defaults.
static bool slot_read_ptr(const uint8_t *p, uint8_t name_out[SLOT_NAME_LEN], Config_body &body_out) {
    uint32_t magic;
    memcpy(&magic, p, 4);
    if (magic == SLOT_MAGIC_V2) {
        uint16_t blen;
        memcpy(&blen, p + 4, 2);
        if (blen == 0) return false;                       // degenerate record
        if (blen > sizeof(Config_body)) {
            // Written by NEWER firmware with a bigger body? Accept the prefix we
            // understand (fields only ever append), CRC over the stored span.
            if (blen > SLOT_STRIDE - 4 - 2 - SLOT_NAME_LEN - 4) return false;
        }
        const uint8_t *name = p + 4 + 2;
        const uint8_t *body = name + SLOT_NAME_LEN;
        uint32_t stored;
        memcpy(&stored, body + blen, 4);
        if (stored != crc32(name, (uint32_t)SLOT_NAME_LEN + blen)) return false;
        memcpy(name_out, name, SLOT_NAME_LEN);
        memset(&body_out, 0xFF, sizeof(Config_body));
        memcpy(&body_out, body, (blen < sizeof(Config_body)) ? blen : sizeof(Config_body));
        return true;
    }
    if (magic == SLOT_MAGIC_V1) {
        const uint8_t *name = p + 4;
        const uint8_t *body = name + SLOT_NAME_LEN;
        constexpr uint16_t BLEN_MAX = (uint16_t)(SLOT_STRIDE - 4 - SLOT_NAME_LEN - 4);
        for (uint16_t blen = 16; blen <= BLEN_MAX; ++blen) {
            uint32_t stored;
            memcpy(&stored, body + blen, 4);
            if (stored == crc32(name, (uint32_t)SLOT_NAME_LEN + blen)) {
                memcpy(name_out, name, SLOT_NAME_LEN);
                memset(&body_out, 0xFF, sizeof(Config_body));
                memcpy(&body_out, body, blen < sizeof(Config_body) ? blen : sizeof(Config_body));
                return true;
            }
        }
    }
    return false;
}

// RAM image of the whole slots sector for read-modify-erase-write. Static so it
// doesn't live on a task stack; only touched from the USB command path.
alignas(4) static uint8_t slot_sector_image[FLASH_SECTOR_SIZE];

static uint32_t slot_op_offset = SLOTS_FLASH_OFFSET; // which sector the op targets
static bool slot_write_ok = false;
static void slots_flash_op(void *) {
    const uint32_t interrupts = save_and_disable_interrupts();
    slot_write_ok = storage_redo_write(slot_op_offset, slot_sector_image, FLASH_SECTOR_SIZE);
    restore_interrupts(interrupts);
}

// Linear-base reader: used ONLY for the legacy (pre-1.4.0) location during boot
// migration, where all 8 slots were contiguous in one sector.
static bool slot_read_at(uint32_t base_offset, uint8_t idx, uint8_t name_out[SLOT_NAME_LEN], Config_body &body_out) {
    return slot_read_ptr(flash_slot_raw_at(base_offset, idx), name_out, body_out);
}
// Sector-mapped reader for the live slot store.
static bool slot_read(uint8_t idx, uint8_t name_out[SLOT_NAME_LEN], Config_body &body_out) {
    const uint8_t *p = reinterpret_cast<const uint8_t *>(
        XIP_BASE + slot_sector_offset(idx / SLOTS_PER_SECTOR) + (idx % SLOTS_PER_SECTOR) * SLOT_STRIDE);
    return slot_read_ptr(p, name_out, body_out);
}

// --- Currently-loaded profile tracking (RAM only, v1.18.22) -----------------
// slot_activate() and slot_save() below are the ONLY paths that make a slot the
// live config, and BOTH the portal and the Playnite automation reach the device
// through slot_activate() (HID cmd 0x09) - so recording the slot here means the
// dongle knows which profile is live no matter who loaded it. RAM-only by design:
// after a power cycle this reads back "unknown" until the next activation (a
// config field would be wrong - it would get saved *into* every slot). The
// snapshot is the config body as loaded; active_profile_get() reports "edited"
// by comparing the live body to it, so any later field change flips the flag
// without needing a hook on every write path.
// Manual dormant resume may explicitly restore this identity from a validated
// scratch-register token; ordinary cold boots keep the original unknown state.
static int16_t     g_active_slot = -1;         // -1 = unknown / not from a slot
static Config_body g_active_snapshot;          // config body as it was loaded
static bool        g_active_snapshot_valid = false;

static void active_profile_set(uint8_t idx) {
    g_active_slot           = (int16_t)idx;
    g_active_snapshot       = config.body;     // post-clamp, as it will be compared
    g_active_snapshot_valid = true;
}

// slot_out = 0xFF and returns false when nothing is being tracked (fresh boot or
// a config not loaded from a slot). Otherwise fills the source slot's name and
// sets edited when the live config has diverged from the loaded snapshot.
bool active_profile_get(uint8_t &slot_out, bool &edited_out, uint8_t name_out[SLOT_NAME_LEN]) {
    if (g_active_slot < 0 || !g_active_snapshot_valid) {
        slot_out = 0xFF;
        edited_out = false;
        if (name_out) memset(name_out, 0, SLOT_NAME_LEN);
        return false;
    }
    slot_out   = (uint8_t)g_active_slot;
    // Compare the live config to the snapshot to decide "edited", but IGNORE the
    // three fields the firmware syncs from hardware at runtime - speaker_volume,
    // headset_volume and speaker_gain (state_mgr.cpp). Otherwise a hardware volume
    // change, or the audio re-sync the host performs right after a USB
    // re-enumeration, rewrites those fields and masquerades as a user edit.
    // Compare the spans around them instead of copying two complete bodies.
    constexpr size_t volume = offsetof(Config_body, speaker_volume);
    constexpr size_t headset = offsetof(Config_body, headset_volume);
    constexpr size_t gain = offsetof(Config_body, speaker_gain);
    static_assert(headset == volume + 1 && gain > headset + 1);
    const auto *a = reinterpret_cast<const uint8_t *>(&config.body);
    const auto *b = reinterpret_cast<const uint8_t *>(&g_active_snapshot);
    edited_out = memcmp(a, b, volume) != 0 ||
        memcmp(a + headset + 1, b + headset + 1, gain - headset - 1) != 0 ||
        memcmp(a + gain + 1, b + gain + 1, sizeof(Config_body) - gain - 1) != 0;
    if (!name_out) return true; // Event status does not read/CRC the slot in flash.
    Config_body bd;
    if (!slot_read((uint8_t)g_active_slot, name_out, bd)) {
        memset(name_out, 0, SLOT_NAME_LEN);    // slot since deleted/overwritten
    }
    return true;
}

static uint32_t resume_slot_fingerprint(const uint8_t *name, const Config_body &body) {
    return crc32(name, SLOT_NAME_LEN) ^
           crc32(reinterpret_cast<const uint8_t *>(&body), sizeof(body));
}

bool active_profile_resume_state(uint8_t &slot, uint32_t &fingerprint) {
    slot = 0xFF;
    fingerprint = 0;
    if (g_active_slot < 0 || !g_active_snapshot_valid) return false;
    uint8_t name[SLOT_NAME_LEN]{};
    Config_body body{};
    if (!slot_read(static_cast<uint8_t>(g_active_slot), name, body)) return false;
    slot = static_cast<uint8_t>(g_active_slot);
    fingerprint = resume_slot_fingerprint(name, body);
    return true;
}

bool active_profile_restore(uint8_t slot, uint32_t fingerprint) {
    uint8_t name[SLOT_NAME_LEN]{};
    Config_body body{};
    if (slot >= SLOT_COUNT || !slot_read(slot, name, body)) return false;
    if (resume_slot_fingerprint(name, body) != fingerprint) {
        // Prior firmware fingerprinted the raw slot (including 0xFF padding).
        // Accept its old span only when this extension is entirely absent.
        const bool old_tail = body.lightbar_fixed == 0xff && body.lightbar_r == 0xff &&
                              body.lightbar_g == 0xff && body.lightbar_b == 0xff;
        const bool new_tail = body.rumble_gain == 0xff && body.rumble_release == 0xff;
        const auto prefix_id = [&](size_t bytes) {
            return crc32(name, SLOT_NAME_LEN) ^ crc32(reinterpret_cast<const uint8_t *>(&body), bytes);
        };
        const bool previous_layout = prefix_id(offsetof(Config_body, rumble_mode)) == fingerprint;
        const bool older_layout = body.usb_gamepad_mode == 0xff &&
            (prefix_id(offsetof(Config_body, usb_gamepad_mode)) == fingerprint ||
             (new_tail && prefix_id(offsetof(Config_body, rumble_gain)) == fingerprint) ||
             (new_tail && old_tail && prefix_id(offsetof(Config_body, lightbar_fixed)) == fingerprint));
        if (body.rumble_mode != 0xff || !(previous_layout || older_layout)) return false;
    }
    // Validate a private copy. Restore identity/baseline only: never activate a
    // slot or overwrite the saved live settings loaded by config_load().
    config_body_valid(body);
    g_active_snapshot = body;
    g_active_slot = slot;
    g_active_snapshot_valid = true;
    return true;
}

bool slot_save(uint8_t idx, const uint8_t *name, uint8_t name_len) {
    if (idx >= SLOT_COUNT) return false;
    const uint32_t sec_off = slot_sector_offset(idx / SLOTS_PER_SECTOR);
    const uint8_t  local   = idx % SLOTS_PER_SECTOR;
    memcpy(slot_sector_image, reinterpret_cast<const void *>(XIP_BASE + sec_off), FLASH_SECTOR_SIZE);
    SlotRecordV2 rec{};
    rec.magic = SLOT_MAGIC_V2;
    rec.body_len = (uint16_t)sizeof(Config_body);
    memset(rec.name, 0, SLOT_NAME_LEN);
    if (name && name_len) memcpy(rec.name, name, (name_len < SLOT_NAME_LEN) ? name_len : SLOT_NAME_LEN);
    rec.body = config.body;
    rec.crc32 = crc32(rec.name, (uint32_t)SLOT_NAME_LEN + sizeof(Config_body));
    memset(slot_sector_image + local * SLOT_STRIDE, 0xff, SLOT_STRIDE);
    memcpy(slot_sector_image + local * SLOT_STRIDE, &rec, sizeof(rec));
    slot_op_offset = sec_off;
    int rc = flash_safe_execute(slots_flash_op, nullptr, 500);
    if (rc != PICO_OK || !slot_write_ok) {
        printf("[Config] slot_save flash_safe_execute failed: %d\n", rc);
        return false;
    }
    uint8_t nm[SLOT_NAME_LEN]; Config_body bd;
    if (!slot_read(idx, nm, bd)) return false;
    active_profile_set(idx);   // the live config now IS this slot
    return true;
}

uint8_t slot_activate(uint8_t idx, bool &needs_reenum, uint8_t &fail_stage) {
    needs_reenum = false;
    fail_stage = 0;
    if (idx >= SLOT_COUNT) { fail_stage = 1; return 0; }
    uint8_t nm[SLOT_NAME_LEN];
    static Config_body slot_body; // static: off the USB task stack
    if (!slot_read(idx, nm, slot_body)) { fail_stage = 2; return 0; }
    // Fields that change USB descriptors / enumeration-time behavior; if any
    // differ, the caller should issue the reconnect command (0x03) afterwards.
    //
    // COMPARE CLAMPED VALUES ON BOTH SIDES. config_valid() normalises the LIVE
    // config only, so comparing it against the RAW stored body made any byte a
    // slot holds unclamped differ forever - and a slot saved before a field
    // existed carries 0xFF there. gyro_output is the clearest case: 0xFF reads
    // as ">= 1", i.e. "mouse interface needed", while the live clamped value is
    // 0, so every activation of that slot looked like an interface change and
    // reconnected the device. Re-activating the SAME slot did it too, because
    // the stored bytes never change. Normalise first, then compare: apply the
    // slot, clamp it, and diff against a copy of what was live before.
    static Config_body prev_body;   // static: keep it off the USB task stack
    prev_body = config.body;
    set_config(reinterpret_cast<const uint8_t *>(&slot_body), sizeof(slot_body));
    macro_reset();
    state_rumble_reset();            // never carry a release across profile boundaries
    extern void gyro_cal_cancel();
    gyro_cal_cancel();
    const Config_body &o = prev_body;
    const Config_body &n = config.body;
    needs_reenum =
#ifdef STUDIO_XINPUT_EXPERIMENT
                   (o.usb_gamepad_mode != n.usb_gamepad_mode) ||
#endif
                   (o.controller_mode      != n.controller_mode)      ||
                   (o.polling_rate_mode    != n.polling_rate_mode)    ||
                   (o.disable_mic          != n.disable_mic)          ||
                   (o.disable_speaker      != n.disable_speaker)      ||
                   (o.enable_wake          != n.enable_wake)          ||
                   (usb_edge_serial_hidden(o) != usb_edge_serial_hidden(n))       ||
                   // The keyboard interface is shared by wake, the PS shortcut
                   // and macros, so what matters is whether it is PRESENT - not
                   // which of the three asked for it. Testing them separately
                   // reconnected when nothing had changed: with wake already on,
                   // enabling a macro leaves the descriptor identical, yet it
                   // dropped the device on every slot switch that altered the
                   // macro set. enable_wake keeps its own test above because it
                   // also moves bcdUSB, the BOS descriptor and REMOTE_WAKEUP.
                   (usb_kbd_iface_needed(o)   != usb_kbd_iface_needed(n))   ||
                   // The mouse is its own interface, and it implies the keyboard -
                   // so the keyboard test above does not cover losing the mouse.
                   (usb_mouse_iface_needed(o) != usb_mouse_iface_needed(n));
    active_profile_set(idx); // record the loaded slot (RAM) for the portal readout
    // During playback, apply RAM immediately and coalesce persistence at idle.
    // Explicit Save and the pre-dormant flush keep synchronous durability.
    if (audio_processing_active()) {
        config_defer_activation_save();
        return 2;
    }
    if (config_save_impl(10)) return 1;
    fail_stage = 3;
    config_defer_activation_save();
    return 2;
}

// Public: load a slot's full config body (for backup/export). Returns false if
// the slot is empty or unreadable. The body is validated the same way a live
// load is, so an exported profile is always a coherent config.
bool slot_load_body(uint8_t idx, Config_body &out) {
    if (idx >= SLOT_COUNT) return false;
    uint8_t nm[SLOT_NAME_LEN]{};
    return slot_read(idx, nm, out);
}

bool slot_info(uint8_t idx, uint8_t name_out[SLOT_NAME_LEN], uint8_t &valid, uint8_t &cfg_version) {
    if (idx >= SLOT_COUNT) return false;
    uint8_t nm[SLOT_NAME_LEN];
    static Config_body bd; // static: off the USB task stack
    if (slot_read(idx, nm, bd)) {
        valid = 1;
        cfg_version = bd.config_version;
        memcpy(name_out, nm, SLOT_NAME_LEN);
    } else {
        valid = 0;
        cfg_version = 0;
        memset(name_out, 0, SLOT_NAME_LEN);
    }
    return true;
}

// If the NEW slots sector has no valid records but the legacy (btstack-colliding)
// one has any - tolerant reader: v2 + all known v1 layouts - rebuild here. Records
// the TLV bank already clobbered fail CRC and are skipped.
static void migrate_legacy_slots() {
    bool new_has = false;
    uint8_t nm[SLOT_NAME_LEN]; static Config_body bd;
    for (uint8_t i = 0; i < SLOT_COUNT && !new_has; ++i)
        new_has = slot_read(i, nm, bd);
    if (new_has) return;
    uint8_t migrated = 0;
    memset(slot_sector_image, 0xff, FLASH_SECTOR_SIZE);
    // The old store occupied ONE sector (8 slots), even though the current
    // format exposes 32 slots in four separately mapped sectors.
    for (uint8_t i = 0; i < SLOTS_PER_SECTOR && i < SLOT_COUNT; ++i) {
        if (!slot_read_at(LEGACY_SLOTS_FLASH_OFFSET, i, nm, bd)) continue;
        SlotRecordV2 rec{};
        rec.magic = SLOT_MAGIC_V2;
        rec.body_len = (uint16_t)sizeof(Config_body);
        memcpy(rec.name, nm, SLOT_NAME_LEN);
        rec.body = bd;
        rec.crc32 = crc32(rec.name, (uint32_t)SLOT_NAME_LEN + sizeof(Config_body));
        memcpy(slot_sector_image + i * SLOT_STRIDE, &rec, sizeof(rec));
        migrated++;
    }
    if (migrated) {
        slot_op_offset = slot_sector_offset(0);
        if (flash_safe_execute(slots_flash_op, nullptr, 1000) == PICO_OK && slot_write_ok)
            printf("[Config] migrated %u profile slot(s) from legacy sector\n", migrated);
    }
}

void set_config(const Config_body &new_config) {
    set_config(reinterpret_cast<const uint8_t *>(&new_config), sizeof(new_config));
}
