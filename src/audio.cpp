//
// Created by awalol on 2026/3/5.
//
// Audio auto-haptics modifications (c) 2026 artzox — MIT License.
// The audio-derived auto-haptics here were inspired by loteran's earlier
// auto-haptics work on the DS5Dongle; the DSP was rewritten, but loteran's
// state_set-in-RAM insight made stock-clock actuation possible. With thanks.
//

/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at https://mozilla.org/MPL/2.0/.
 */

#include "audio.h"
#include "haptic_mix.h"
#include "bt.h"
#include "resample.h"
#include "tusb.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <atomic>
#include "opus.h"
#include "utils.h"
#include "pico/multicore.h"
#include "pico/platform.h"
#include "pico/flash.h"
#include "pico/util/queue.h"
#include "config.h"
#include "state_mgr.h"
#include "usb.h"

#define INPUT_CHANNELS    4
#define OUTPUT_CHANNELS   2
#define SAMPLE_SIZE       64
#define REPORT_SIZE       398
#define REPORT_ID         0x36
// #define VOLUME_GAIN       2
// #define BUFFER_LENGTH     48
#define MIC_CHANNELS      1
#define MIC_FRAMES        480
#define MIC_OPUS_SIZE     71   // bytes per opus-encoded mic frame from the DualSense

using std::clamp;
using std::max;

static WDL_Resampler resampler;
static uint8_t reportSeqCounter = 0;
static uint8_t packetCounter = 0;
static bool plug_headset = false;
static uint32_t mic_stream_generation = 0;
static bool mic_active = false; // host has opened the mic IN interface (alt != 0)
alignas(8) static uint32_t audio_core1_stack[8192];
queue_t audio_fifo;
queue_t mic_fifo;
queue_t mic_decode_fifo;
// Diagnostic: live channel detection, read via config field 0x20.
volatile uint16_t g_diag_bytes_read = 0;
volatile uint16_t g_diag_ch01_peak = 0; // peak |sample| ch0-1 (DSP input)
volatile uint16_t g_diag_ch23_peak = 0; // peak |sample| ch2-3 (native actuators)
volatile uint8_t  g_diag_actual_ch  = 0;
// Incoming DS4Windows rumble-emulation motor values (0-255), blended into the
// actuator signal in Mix mode when auto-haptics is on.
volatile uint8_t g_rumble_l = 0;
volatile uint8_t g_rumble_r = 0;
// Peak-hold copies for diagnostics. The portal polls once per second while a
// rumble burst can last 100 ms, so an instantaneous reading misses most of
// them and "zero" proves nothing. These latch the highest value seen and are
// cleared when the portal reads them, so ANY rumble in the interval shows up.
volatile uint8_t g_rumble_peak_l = 0;
volatile uint8_t g_rumble_peak_r = 0;
// Sticky OR of the host's rumble-related request flags (bit0 EnableRumble-
// Emulation, bit1 UseRumbleNotHaptics), also cleared on read: shows what the
// game ASKED for, independent of what it actually put in the motor bytes.
volatile uint8_t g_rumble_flags_seen = 0;
// Auto-haptics activity + level meters (portal Device tab). Same sampling-proof
// design as the rumble peaks above: a ~1 Hz poll must not miss a short burst, so
// each latches its max and is cleared when the portal reads it.
//  g_ah_frames   - audio frames delivered on the USB audio-out endpoint since the
//                  last read. Non-zero => the bridge (ds5audio.py) is streaming,
//                  even during game silence; zero => nothing arriving (the usual
//                  reason auto-haptics "does nothing" is the script not running).
//  g_ah_in_peak  - peak |ch0/1 input sample| 0-255: the DSP's audio source level.
//  g_ah_out_peak - peak derived-haptic OUTPUT 0-255 the DSP is generating, taken
//                  before native passthrough / converted rumble are mixed in, so
//                  it reflects only what auto-haptics itself produces.
volatile uint16_t g_ah_frames   = 0;
volatile uint8_t  g_ah_in_peak  = 0;
volatile uint8_t  g_ah_out_peak = 0;
// Short-window peak holds for the OLED graph. Unlike the portal meters above,
// these are consumed at the display cadence (8 Hz) and do not require polling.
volatile uint8_t  g_oled_ah_input_peak = 0;
volatile uint8_t  g_oled_ah_output_peak = 0;
// Latest L2 (left trigger) analog position from the controller's input report,
// used by the L2-gated R2 adaptive-trigger feature.
volatile uint8_t g_l2_pos = 0;
volatile uint8_t g_r2_pos = 0; // R2 (right trigger) analog position, for r2t on-press gating
volatile uint8_t g_l1_btn = 0; // L1 shoulder (digital), for shoulder-gated adaptive triggers
volatile uint8_t g_r1_btn = 0; // R1 shoulder (digital)
struct SpeakerFrame { uint8_t data[200]; uint32_t encoded_ms, sequence; };
static SpeakerFrame opus_frames[2];
static uint8_t opus_head = 0, opus_count = 0;
struct SpeakerStats {
    uint32_t published = 0, consumed = 0, overflow = 0, stale = 0, underrun = 0;
    uint32_t rejected_generation = 0, last_sequence = 0, resets = 0;
    // Single writer per field: PCM counters on core0, encode failures on core1.
    uint32_t pcm_created = 0, pcm_dropped = 0, encode_failed = 0;
};
SpeakerStats g_speaker_stats;
critical_section_t opus_cs;
// Protected by opus_cs. Only core0 changes the generation; core1 tags results.
static uint32_t speaker_generation = 1;
// All result queue access, including reset, is protected by opus_cs.
static uint8_t opus_silence_buf[200]{};
static bool opus_silence_valid = false;
static bool speaker_was_enabled = true;
static bool speaker_filters_reset = false;
static std::atomic<bool> audio_link_active{false};
// 0=running, 1=request, 2=prepared (cancellable), 3=committed.
static std::atomic<uint8_t> audio_stop_state{0};
static std::atomic<bool> audio_worker_failed{false};
static uint32_t last_audio_input_ms = 0;
static bool audio_input_seen = false;
static bool stream_reset_requested = false;
void audio_reset_stream() { stream_reset_requested = true; audio_input_seen = false; }
static_assert(std::atomic<bool>::is_always_lock_free);
static_assert(std::atomic<uint8_t>::is_always_lock_free);

bool audio_prepare_sleep() {
#if !DISABLE_SPEAKER_PROC
    if (audio_worker_failed.load(std::memory_order_acquire)) return true;
    audio_stop_state.store(1, std::memory_order_release);
    __sev();
    const uint32_t started = to_ms_since_boot(get_absolute_time());
    while (audio_stop_state.load(std::memory_order_acquire) != 2) {
        if (to_ms_since_boot(get_absolute_time()) - started >= 2000) {
            uint8_t requested = 1;
            if (audio_stop_state.compare_exchange_strong(requested, 0)) {
                __sev();
                return false;
            }
            if (requested == 2) break;
        }
        sleep_ms(1);
    }
    audio_stop_state.store(3, std::memory_order_release);
    __sev();
#endif
    return true;
}

bool audio_haptics_stream_active() {
    return bt_is_ready() && audio_input_seen &&
        to_ms_since_boot(get_absolute_time()) - last_audio_input_ms < 60;
}

bool audio_processing_active() {
    return bt_is_ready() && (mic_active ||
        (audio_input_seen && to_ms_since_boot(get_absolute_time()) - last_audio_input_ms < 200));
}

struct audio_raw_element {
    uint32_t sequence;
    uint32_t generation;
    float data[512 * 2];
};
// Three fixed blocks: at most two waiting and one owned by the encoder.
static audio_raw_element speaker_blocks[3];
static queue_t free_speaker_blocks;

static void __not_in_flash_func(release_speaker_block)(uint8_t index) {
    const bool released = queue_try_add(&free_speaker_blocks, &index);
    hard_assert(released); // ownership invariant; never duplicate a free index
}

static void __not_in_flash_func(discard_speaker_queue)() {
    uint8_t index;
    while (queue_try_remove(&audio_fifo, &index)) release_speaker_block(index);
}

static void __not_in_flash_func(publish_speaker_block)(const float *samples, uint32_t generation) {
    const uint32_t sequence = ++g_speaker_stats.pcm_created;
    uint8_t index;
    bool free = queue_try_remove(&free_speaker_blocks, &index);
    if (!free && queue_try_remove(&audio_fifo, &index)) {
        ++g_speaker_stats.pcm_dropped;
        free = true;
    }
    if (!free) { ++g_speaker_stats.pcm_dropped; return; }
    speaker_blocks[index].sequence = sequence;
    speaker_blocks[index].generation = generation;
    memcpy(speaker_blocks[index].data, samples, sizeof(speaker_blocks[index].data));
    if (queue_is_full(&audio_fifo)) {
        uint8_t old;
        if (queue_try_remove(&audio_fifo, &old)) { ++g_speaker_stats.pcm_dropped; release_speaker_block(old); }
    }
    if (!queue_try_add(&audio_fifo, &index)) { ++g_speaker_stats.pcm_dropped; release_speaker_block(index); }
}
struct mic_element {
    uint32_t generation;
    uint8_t data[MIC_OPUS_SIZE];
};
struct mic_decode_element {
    uint32_t generation;
    int16_t data[MIC_FRAMES * MIC_CHANNELS];
    uint16_t len;
};

void set_headset(bool state) {
    plug_headset = state;
}

// Called from tud_audio_set_itf_cb when the host opens/closes the mic IN
// interface. Gates controller-mic streaming so it only runs while recording.
void set_mic_active(bool active) {
    if (mic_active != active) ++mic_stream_generation;
    mic_active = active;
    update_mic_status();
}

bool audio_mic_active() {
    return mic_active;
}

void update_mic_status() {
    uint8_t pkt[142]{};
    pkt[0] = 0x32;
    pkt[1] = reportSeqCounter << 4;
    reportSeqCounter = (reportSeqCounter + 1) & 0x0F;
    pkt[2] = 0x11 | 0 << 6 | 1 << 7;
    pkt[3] = 7;
    pkt[4] = (mic_active && !get_config().disable_mic) ? 0b11111111 : 0b11111110;
    const auto buf_len = get_config().audio_buffer_length;
    pkt[5] = buf_len;
    pkt[6] = buf_len;
    pkt[7] = buf_len;
    pkt[8] = buf_len;
    pkt[9] = buf_len;
    pkt[10] = packetCounter++;
    bt_write(pkt,sizeof(pkt));
}

static void publish_speaker_frame(const uint8_t *data, uint32_t generation, uint32_t sequence) {
    critical_section_enter_blocking(&opus_cs);
    if (generation == speaker_generation) {
        if (opus_count == 2) { opus_head ^= 1; --opus_count; ++g_speaker_stats.overflow; }
        auto &frame = opus_frames[(opus_head + opus_count) % 2];
        memcpy(frame.data, data, sizeof(frame.data));
        frame.encoded_ms = to_ms_since_boot(get_absolute_time());
        ++g_speaker_stats.published;
        frame.sequence = sequence;
        ++opus_count;
    } else { ++g_speaker_stats.rejected_generation; }
    critical_section_exit(&opus_cs);
}

static bool take_speaker_frame(uint8_t *data) {
    bool found = false;
    critical_section_enter_blocking(&opus_cs);
    const uint32_t now = to_ms_since_boot(get_absolute_time());
    while (opus_count) {
        const auto &frame = opus_frames[opus_head];
        opus_head ^= 1;
        --opus_count;
        if (now - frame.encoded_ms >= 25) { ++g_speaker_stats.stale; continue; }
        memcpy(data, frame.data, sizeof(frame.data));
        ++g_speaker_stats.consumed;
        g_speaker_stats.last_sequence = frame.sequence;
        found = true;
        break;
    }
    if (!found) ++g_speaker_stats.underrun;
    critical_section_exit(&opus_cs);
    return found;
}

void __not_in_flash_func(audio_loop)() {
    const bool connected = bt_is_ready();
    if (audio_link_active.exchange(connected, std::memory_order_relaxed) != connected) __sev();
    static bool was_connected = false;
    static float audio_buf[512 * 2];
    static uint audio_buf_pos = 0;
    static int8_t haptic_buf[SAMPLE_SIZE];
    static int haptic_buf_pos = 0;
    static uint8_t usb_remainder[CFG_TUD_AUDIO_FUNC_1_N_CHANNELS_RX * sizeof(int16_t)]{};
    static uint usb_remainder_bytes = 0;
    static uint8_t previous_mode = 0xff;
    const uint8_t mode = get_config().auto_haptics_enable;
    const bool reset_stream = stream_reset_requested || connected != was_connected ||
        previous_mode != mode || (audio_input_seen &&
        to_ms_since_boot(get_absolute_time()) - last_audio_input_ms >= 60);
    const bool discard_usb = stream_reset_requested || connected != was_connected;
    previous_mode = mode;
    stream_reset_requested = false;
    if (reset_stream) {
        bt_discard_audio();
        speaker_filters_reset = true;
        was_connected = connected;
        audio_input_seen = false;
        audio_buf_pos = 0;
        haptic_buf_pos = 0;
        usb_remainder_bytes = 0;
        resampler.Reset();
        if (discard_usb) tud_audio_clear_ep_out_ff();
    }
    const bool speaker_enabled = connected && !get_config().disable_speaker;
#if !DISABLE_SPEAKER_PROC
    // Observe transitions even when no USB audio arrives. Never reset core1's
    // encoder/resampler here: the worker owns those objects.
    if (speaker_enabled != speaker_was_enabled || reset_stream) {
        speaker_was_enabled = speaker_enabled;
        speaker_filters_reset = true;
        critical_section_enter_blocking(&opus_cs);
        ++speaker_generation;
        opus_head = opus_count = 0;
        ++g_speaker_stats.resets;
        critical_section_exit(&opus_cs);
        discard_speaker_queue();
    }
#endif
    if (!connected) {
        ++mic_stream_generation;
        // Wake-enabled USB identities may still receive host audio. Discard it
        // without DSP/encoding and without carrying backlog into the next link.
        tud_audio_clear_ep_out_ff();
        while (queue_try_remove(&mic_fifo, nullptr)) {}
        while (queue_try_remove(&mic_decode_fifo, nullptr)) {}
        g_oled_ah_input_peak = 0;
        g_oled_ah_output_peak = 0;
        return;
    }
    // Mic playback: drain decoded mic PCM into the USB IN endpoint
    static mic_decode_element mic_pb{};
    static int16_t mic_stereo[MIC_FRAMES * 2];
    static uint16_t mic_pending = 0, mic_offset = 0;
    static uint32_t mic_started_ms = 0, mic_generation = 0;
    const uint32_t mic_now = to_ms_since_boot(get_absolute_time());
    if (!mic_active || mic_generation != mic_stream_generation ||
        (mic_pending && mic_now - mic_started_ms >= 20)) {
        mic_pending = mic_offset = 0;
        mic_generation = mic_stream_generation;
    }
    if (!mic_active) {
        while (queue_try_remove(&mic_decode_fifo, nullptr)) {}
    } else if (!mic_pending && queue_try_remove(&mic_decode_fifo, &mic_pb)) {
        if (mic_pb.generation != mic_stream_generation) return;
        // The controller mic is mono, but the USB descriptor presents a 2-channel
        // mic (matching the real DS5) so Windows doesn't conflict with its cached
        // DS5 audio format. Duplicate each mono sample into L and R.
        const int mono_samples = mic_pb.len / 2;
        const float mic_gain = std::pow(10.0f, std::clamp(volume[1], 0.0f, 48.0f) / 20.0f);
        for (int i = 0; i < mono_samples; i++) {
            const auto sample = static_cast<int16_t>(std::clamp(
                mic_pb.data[i] * mic_gain, -32768.0f, 32767.0f));
            mic_stereo[2 * i] = sample;
            mic_stereo[2 * i + 1] = sample;
        }
        if (mute[1]) memset(mic_stereo, 0, mono_samples * 2 * sizeof(int16_t));
        mic_pending = static_cast<uint16_t>(mono_samples * 2 * sizeof(int16_t));
        mic_offset = 0;
        mic_started_ms = mic_now;
    }
    if (mic_pending) {
        if (mute[1]) memset(mic_stereo, 0, sizeof(mic_stereo));
        const uint16_t written = tud_audio_write(reinterpret_cast<uint8_t *>(mic_stereo) + mic_offset, mic_pending);
        mic_offset += written;
        mic_pending -= written;
    }

    // 1. 读取 USB 音频数据
    if (!tud_audio_available()) return;

    int16_t raw[192];
    memcpy(raw, usb_remainder, usb_remainder_bytes);
    const uint32_t bytes_read = usb_remainder_bytes + tud_audio_read(
        reinterpret_cast<uint8_t *>(raw) + usb_remainder_bytes,
        sizeof(raw) - usb_remainder_bytes);
    // Both published UAC1 playback descriptors advertise four int16 channels.
    // Short reads do not change the negotiated format. Keep partial frames.
    constexpr int actual_ch = CFG_TUD_AUDIO_FUNC_1_N_CHANNELS_RX;
    static_assert(actual_ch == 4, "Update playback descriptors with the channel format");
    constexpr uint kFrameBytes = actual_ch * sizeof(int16_t);
    usb_remainder_bytes = bytes_read % kFrameBytes;
    memcpy(usb_remainder, reinterpret_cast<const uint8_t *>(raw) +
           bytes_read - usb_remainder_bytes, usb_remainder_bytes);
    // Diagnostic: expose the live detection so the portal can show what's
    // actually happening (esp. under DS4Windows).
    extern volatile uint16_t g_diag_bytes_read;
    extern volatile uint8_t  g_diag_actual_ch;
    g_diag_bytes_read = (uint16_t)bytes_read;
    g_diag_actual_ch  = (uint8_t)actual_ch;
    int frames = bytes_read / (actual_ch * (int)sizeof(int16_t));
    if (frames == 0) {
        return;
    }
    last_audio_input_ms = to_ms_since_boot(get_absolute_time());
    audio_input_seen = true;
    // Never join a pre-disable partial block to newly enabled speaker audio.
    if (!speaker_enabled || speaker_filters_reset) audio_buf_pos = 0;
    // 2. 从4ch中提取ch3/ch4，转换为float输入重采样器
    WDL_ResampleSample *in_buf;
    int nframes = resampler.ResamplePrepare(frames, OUTPUT_CHANNELS, &in_buf);

    // Core0 owns configuration writes; copy only audio fields once per block.
    const auto &live_config = get_config();
    const struct AudioBlockSettings {
        decltype(Config_body::ah_dsp_source) ah_dsp_source;
        decltype(Config_body::ah_high_gain) ah_high_gain;
        decltype(Config_body::ah_low_gain) ah_low_gain;
        decltype(Config_body::ah_xover_hz) ah_xover_hz;
        decltype(Config_body::audio_buffer_length) audio_buffer_length;
        decltype(Config_body::auto_haptics_enable) auto_haptics_enable;
        decltype(Config_body::auto_haptics_gain) auto_haptics_gain;
        decltype(Config_body::auto_haptics_gate) auto_haptics_gate;
        decltype(Config_body::auto_haptics_lowpass_hz) auto_haptics_lowpass_hz;
        decltype(Config_body::auto_haptics_slope) auto_haptics_slope;
        decltype(Config_body::auto_haptics_smooth) auto_haptics_smooth;
        decltype(Config_body::auto_mute_mix) auto_mute_mix;
        decltype(Config_body::auto_mute_replace) auto_mute_replace;
        decltype(Config_body::disable_mic) disable_mic;
        decltype(Config_body::effect_leak_attack) effect_leak_attack;
        decltype(Config_body::effect_leak_decay) effect_leak_decay;
        decltype(Config_body::effect_leak_hold) effect_leak_hold;
        decltype(Config_body::effect_leak_hp_hz) effect_leak_hp_hz;
        decltype(Config_body::effect_leak_lp_hz) effect_leak_lp_hz;
        decltype(Config_body::effect_leak_max_burst) effect_leak_max_burst;
        decltype(Config_body::effect_leak_output_hp_hz) effect_leak_output_hp_hz;
        decltype(Config_body::effect_leak_sensitivity) effect_leak_sensitivity;
        decltype(Config_body::effect_leak_volume) effect_leak_volume;
        decltype(Config_body::haptics_aa) haptics_aa;
        decltype(Config_body::haptics_gain) haptics_gain;
        decltype(Config_body::mix_native_filter) mix_native_filter;
        decltype(Config_body::mix_native_level) mix_native_level;
        decltype(Config_body::rumble_haptic_strength) rumble_haptic_strength;
    } cfg{
        live_config.ah_dsp_source,
        live_config.ah_high_gain,
        live_config.ah_low_gain,
        live_config.ah_xover_hz,
        live_config.audio_buffer_length,
        live_config.auto_haptics_enable,
        live_config.auto_haptics_gain,
        live_config.auto_haptics_gate,
        live_config.auto_haptics_lowpass_hz,
        live_config.auto_haptics_slope,
        live_config.auto_haptics_smooth,
        live_config.auto_mute_mix,
        live_config.auto_mute_replace,
        live_config.disable_mic,
        live_config.effect_leak_attack,
        live_config.effect_leak_decay,
        live_config.effect_leak_hold,
        live_config.effect_leak_hp_hz,
        live_config.effect_leak_lp_hz,
        live_config.effect_leak_max_burst,
        live_config.effect_leak_output_hp_hz,
        live_config.effect_leak_sensitivity,
        live_config.effect_leak_volume,
        live_config.haptics_aa,
        live_config.haptics_gain,
        live_config.mix_native_filter,
        live_config.mix_native_level,
        live_config.rumble_haptic_strength,
    };
    const float haptics_gain = cfg.haptics_gain;
    const uint8_t auto_mode = cfg.auto_haptics_enable;
    const uint8_t aa_mode = cfg.haptics_aa; // native-haptics smoothing (1=off,2=light,3=strong)
    // Speaker-data mute: silence the speaker AUDIO CONTENT (not the volume) when
    // Windows mutes, or via auto-mute. Zeroing the speaker buffer leaves
    // VolumeSpeaker untouched, so the controller still scales HAPTICS normally
    // (it scales haptic output by speaker volume — lowering volume kills haptics).
    extern uint8_t mute[2];
    const bool mute_for_mode =
        (auto_mode == 2 && cfg.auto_mute_replace) ||
        (auto_mode == 1 && cfg.auto_mute_mix);
    const float spk_gain = (mute[0] || mute_for_mode) ? 0.0f : 1.0f;
    // Intensity maps 0-100 to a perceptual gain. The carrier makeup is folded in
    // here (modest, ~2.5x) instead of a fixed 12x that saturated the soft-clip and
    // crushed the whole usable range into the bottom few percent. Now the slider
    // spans weak->strong roughly linearly.
    // Intensity curve: the 90 Hz carrier sits in the actuator's most responsive
    // band, so the response to linear gain is very non-linear — low values already
    // actuate. Use a curve (power 1.5) so the slider has fine control low down AND
    // strong headroom up top. intensity 0..200 -> 0..1, curved, scaled to a usable
    // peak. ~100 = firm, 200 = very strong, low values = subtle.
    static int cached_intensity = -1;
    static float intensity_curved = 0.0f;
    const int intensity = cfg.auto_haptics_gain;
    if (auto_mode > 0 && cached_intensity != intensity) {
        cached_intensity = intensity;
        const float intensity_n = intensity / 200.0f;
        intensity_curved = intensity_n * sqrtf(intensity_n);
    }
    const float auto_gain = (auto_mode > 0)
        ? intensity_curved * 9.0f * haptics_gain : 0.0f;
    // Clamp cutoff defensively so a 0/garbage config value can't zero the filter
    // coefficient (which would silence auto-haptics entirely).
    uint16_t lp_fc = cfg.auto_haptics_lowpass_hz;
    if (lp_fc < 20 || lp_fc > 400) lp_fc = 60;
    static float lp_a = 0.0f; static uint16_t lp_fc_cached = 0;
    if (auto_mode > 0 && lp_fc != lp_fc_cached) {
        lp_fc_cached = lp_fc;
        lp_a = 1.0f - expf(-2.0f * (float)M_PI * (float)lp_fc / 48000.0f);
    }
    static float lp_l = 0.0f, lp_r = 0.0f;
    static float lp2_l = 0.0f, lp2_r = 0.0f; // cascade stages for steeper slopes
    static float lp3_l = 0.0f, lp3_r = 0.0f;
    static float lp4_l = 0.0f, lp4_r = 0.0f;
    // Frequency split (v1.5.0): xover 0 = OFF -> the block below is bypassed and
    // the single-band path is byte-identical to previous firmware. When ON, a
    // 12 dB/oct LP at the crossover carves the LOW band out of the input; the
    // HIGH band is the existing filtered signal minus the low band (i.e. the
    // crossover..LP-cutoff range). Each band gets its own envelope, weighted by
    // its gain, then summed into the SAME gate + carrier chain - so the felt
    // character is unchanged, only the per-band contribution is adjustable.
    uint16_t xover_fc = cfg.ah_xover_hz;
    const bool split_on = (auto_mode > 0) && xover_fc >= 30 && xover_fc <= 200;
    static float xo_a = 0.0f; static uint16_t xo_fc_cached = 0;
    if (split_on && xover_fc != xo_fc_cached) {
        xo_fc_cached = xover_fc;
        xo_a = 1.0f - expf(-2.0f * (float)M_PI * (float)xover_fc / 48000.0f);
    }
    static float xo1_l = 0.0f, xo2_l = 0.0f, xo1_r = 0.0f, xo2_r = 0.0f; // split LP stages
    static float envlo_l = 0.0f, envlo_r = 0.0f, envhi_l = 0.0f, envhi_r = 0.0f;
    const float split_lo_g = cfg.ah_low_gain  / 100.0f;
    const float split_hi_g = cfg.ah_high_gain / 100.0f;
    static float env_l = 0.0f, env_r = 0.0f;
    constexpr float ENV_ATK = 0.15f;
    // Smoothing: maps 0-100 to envelope release rate. Lower release coefficient =
    // longer decay = smoother/more continuous. smooth=0 -> snappy (0.03),
    // smooth=100 -> very smooth (0.002). Lets you dial the feel manually.
    const uint8_t smooth_cfg = cfg.auto_haptics_smooth > 100 ? 50 : cfg.auto_haptics_smooth;
    static int cached_ENV_REL = -1;
    static float ENV_REL = 0.0f;
    if (auto_mode > 0 && cached_ENV_REL != smooth_cfg) {
        cached_ENV_REL = smooth_cfg;
        ENV_REL = 0.030f - (smooth_cfg / 100.0f) * 0.028f;
    }
    // Filter slope: number of cascaded 1-pole stages. 1 = 6 dB/oct, 2 = 12 dB/oct,
    // 4 = 24 dB/oct. Steeper = sharper voice/bass separation. Config stores the
    // dB/oct value (6/12/24); map to pole count.
    const uint8_t slope_db = cfg.auto_haptics_slope;
    const int n_poles = (slope_db >= 24) ? 4 : (slope_db >= 12) ? 2 : 1;
    // Effect leak (transient detection): when auto-mute would fully silence the
    // speaker, only open it briefly during sharp ONSETS — sudden level jumps like
    // impacts, shots, clinks — and keep it closed for sustained sound (dialog,
    // music, ambience). A plain high-pass leaks all sustained high-frequency
    // content (hiss, music treble); transient detection instead reacts to how
    // FAST the level rises, so only percussive effects pass. leak_vol 0 = off.
    const float leak_vol = cfg.effect_leak_volume / 100.0f;
    const bool leak_active = (mute_for_mode && !mute[0] && leak_vol > 0.0f);
    // Detection runs on a high-passed copy so low-frequency dialog onsets don't
    // trigger it. The configured "high-pass" value doubles as the detection band.
    static float hp_l = 0.0f, hp_r = 0.0f;          // high-pass state (for detection input)
    // Output BAND-PASS window (v1.2.0): the leak output passes through a 12 dB/oct
    // high-pass (low wall — speaker pop protection + dialog-fundamental rejection)
    // followed by a 12 dB/oct low-pass (high wall — kills the treble sizzle/click
    // that made the leak crackly). Only sound INSIDE the window ever leaks, so the
    // window placement IS the selectivity: e.g. 400-3500 Hz passes impacts and
    // effect bodies while rejecting both voice fundamentals and hiss/sparkle.
    static float ohp1_l = 0.0f, ohp2_l = 0.0f, ohp1_r = 0.0f, ohp2_r = 0.0f; // 2-stage HP
    static float olp1_l = 0.0f, olp2_l = 0.0f, olp1_r = 0.0f, olp2_r = 0.0f; // 2-stage LP
    const float ohp_fc = (float)cfg.effect_leak_output_hp_hz;
    static float ohp_a = 0.0f;
    static float ohp_fc_cached = -1.0f;
    if (leak_active && ohp_fc != ohp_fc_cached) {
        ohp_fc_cached = ohp_fc;
        ohp_a = 1.0f - expf(-2.0f * (float)M_PI * ohp_fc / 48000.0f);
    }
    const float olp_fc = (float)cfg.effect_leak_lp_hz;
    static float olp_a = 0.0f;
    static float olp_fc_cached = -1.0f;
    if (leak_active && olp_fc != olp_fc_cached) {
        olp_fc_cached = olp_fc;
        olp_a = 1.0f - expf(-2.0f * (float)M_PI * olp_fc / 48000.0f);
    }
    // Window make-up gain (v1.5.2): the band-pass walls overlap, so narrowing the
    // window used to also make the leak QUIETER (a 400-3500 window lost ~16 dB of
    // perceived level vs the pre-window firmware because the controller's tiny
    // speaker is loudest in the 3-8 kHz range the LP removes). Compensate by the
    // window's response at its geometric-center frequency so the volume slider
    // owns loudness and the window owns character. Clamped to x4 (+12 dB).
    static float leak_makeup = 1.0f;
    static uint32_t mk_key = 0;
    const uint32_t mk_now = ((uint32_t)ohp_fc << 16) | (uint32_t)olp_fc;
    if (leak_active && mk_now != mk_key) {
        mk_key = mk_now;
        const float fc = sqrtf(ohp_fc * olp_fc);           // window center
        const float whp = fc / ohp_fc, wlp = fc / olp_fc;  // normalized freqs
        const float g1 = whp / sqrtf(1.0f + whp * whp);    // one HP pole @ center
        const float g2 = 1.0f / sqrtf(1.0f + wlp * wlp);   // one LP pole @ center
        float g = (g1 * g1) * (g2 * g2);                   // two poles each
        if (g < 0.25f) g = 0.25f;                          // clamp make-up to x4
        leak_makeup = 1.0f / g;
    }
    // Gate hold + hysteresis (v1.2.0): once a transient opens the gate, keep it
    // open a minimum time (hold) and only close when the level falls clearly below
    // the OPEN threshold (hysteresis). Without this the transient test flickers
    // when the envelope hovers at the threshold — the gate chatters open/closed,
    // which is exactly the "missing and poppy" artifact: hits get chopped short
    // (missing) and each re-open clicks (poppy).
    const uint32_t hold_samples = (uint32_t)cfg.effect_leak_hold * 240u; // x5 ms @48kHz
    // Max burst (v1.12.0): cap one gate opening at N ms. 0 = unlimited (classic).
    const uint32_t burst_samples = (uint32_t)cfg.effect_leak_max_burst * 240u; // x5 ms @48kHz
    static bool     gate_open = false;
    static bool     refractory = false; // closed by the cap; no re-open until the signal truly falls
    static uint32_t hold_left = 0;
    static uint32_t burst_left = 0;
    static float env_fast = 0.0f, env_slow = 0.0f;  // fast/slow level envelopes
    static float leak_gain = 0.0f;                   // smoothed open/close gain
    const float hp_fc = (float)cfg.effect_leak_hp_hz;
    static float hp_a = 0.0f;
    static float hp_fc_cached = -1.0f;
    if (leak_active && hp_fc != hp_fc_cached) {
        hp_fc_cached = hp_fc;
        hp_a = 1.0f - expf(-2.0f * (float)M_PI * hp_fc / 48000.0f);
    }
    // Sensitivity: how much the fast envelope must exceed the slow one to count as
    // a transient. Higher sensitivity (config 0-100) -> lower ratio -> opens more
    // easily (more sound leaks). Maps 0->ratio 3.0 (very selective, only big hits)
    // .. 100->ratio 1.2 (eager, most onsets pass). Default ~50 -> ~2.1.
    const uint8_t sens_cfg = cfg.effect_leak_sensitivity > 100 ? 50 : cfg.effect_leak_sensitivity;
    static int cached_TRANS_RATIO = -1;
    static float TRANS_RATIO = 0.0f;
    if (leak_active && cached_TRANS_RATIO != sens_cfg) {
        cached_TRANS_RATIO = sens_cfg;
        TRANS_RATIO = 3.0f - (sens_cfg / 100.0f) * 1.8f;
    }
    const float ENV_FAST_A  = 0.65f;  // fast envelope attack — quicker detection (less delay)
    const float ENV_SLOW_A  = 0.0020f;// slow envelope (~tracks the ongoing level)
    // Gate ramps: opening too fast creates a click at the onset (crackle); a few
    // ms ramp removes the click while staying responsive. Close SLOWLY so the hit
    // rings out and fades gradually instead of stopping abruptly. The close rate
    // (decay/fade-out length) is configurable: higher decay -> smaller coefficient
    // -> longer, more gradual tail. 0 -> ~0.004 (quick), 100 -> ~0.0004 (very long).
    const uint8_t decay_cfg = cfg.effect_leak_decay > 100 ? 40 : cfg.effect_leak_decay;
    // Attack (responsiveness): how fast the gate opens once a transient is
    // detected. Faster = more immediate hit (less perceived delay) but can add a
    // faint click on the sharpest onsets; slower = smoother but feels delayed.
    // Configurable 0-100: 0 -> 0.03 (smooth), 100 -> 0.40 (near-instant).
    const uint8_t atk_cfg = cfg.effect_leak_attack > 100 ? 50 : cfg.effect_leak_attack;
    static int cached_GATE_OPEN = -1;
    static float GATE_OPEN = 0.0f;
    if (leak_active && cached_GATE_OPEN != atk_cfg) {
        cached_GATE_OPEN = atk_cfg;
        GATE_OPEN = 0.03f + (atk_cfg / 100.0f) * 0.37f;
    }
    static int cached_GATE_CLOSE = -1;
    static float GATE_CLOSE = 0.0f;
    if (leak_active && cached_GATE_CLOSE != decay_cfg) {
        cached_GATE_CLOSE = decay_cfg;
        GATE_CLOSE = 0.004f - (decay_cfg / 100.0f) * 0.0036f;
    } // 0.004 .. 0.0004
    static float gsm_l = 0.0f, gsm_r = 0.0f;
    static float carrier_ph = 0.0f;
    static float rc_lo_ph = 0.0f, rc_hi_ph = 0.0f;
    static float native_lp_l = 0.0f, native_lp_r = 0.0f;
    static float aa1_l = 0.0f, aa1_r = 0.0f, aa2_l = 0.0f, aa2_r = 0.0f;
    if (speaker_filters_reset) {
        lp_l = lp_r = lp2_l = lp2_r = lp3_l = lp3_r = lp4_l = lp4_r = 0;
        xo1_l = xo2_l = xo1_r = xo2_r = 0;
        envlo_l = envlo_r = envhi_l = envhi_r = env_l = env_r = 0;
        gsm_l = gsm_r = carrier_ph = rc_lo_ph = rc_hi_ph = 0;
        native_lp_l = native_lp_r = aa1_l = aa1_r = aa2_l = aa2_r = 0;
        hp_l = hp_r = 0.0f;
        ohp1_l = ohp2_l = ohp1_r = ohp2_r = 0.0f;
        olp1_l = olp2_l = olp1_r = olp2_r = 0.0f;
        env_fast = env_slow = leak_gain = 0.0f;
        gate_open = refractory = false;
        hold_left = burst_left = 0;
        speaker_filters_reset = false;
    }
    const bool dsp_rear = cfg.ah_dsp_source == 1 && actual_ch == 4;
    const float native_lvl = cfg.mix_native_level / 100.0f;
    const float rumble_str = cfg.rumble_haptic_strength / 100.0f;
    const uint8_t gate_cfg = cfg.auto_haptics_gate;
    const float GATE_THRESH = (gate_cfg > 100 ? 0 : gate_cfg) * 0.001f;
    float ah_out_pk = 0.0f;   // peak derived-haptic magnitude this block (diag meter)
    // Fold the raw-input diagnostics into the existing per-sample DSP pass so
    // reading channel peaks does not require a second full scan of the packet.
    int p01 = 0, p23 = 0;
    for (int i = 0; i < nframes; i++) {
        int a0 = raw[i * actual_ch];     if (a0 < 0) a0 = -a0;
        int a1 = raw[i * actual_ch + 1]; if (a1 < 0) a1 = -a1;
        if (a0 > p01) p01 = a0;
        if (a1 > p01) p01 = a1;
        if (actual_ch == 4) {
            int a2 = raw[i * actual_ch + 2]; if (a2 < 0) a2 = -a2;
            int a3 = raw[i * actual_ch + 3]; if (a3 < 0) a3 = -a3;
            if (a2 > p23) p23 = a2;
            if (a3 > p23) p23 = a3;
        }
 #if !DISABLE_SPEAKER_PROC
        if (speaker_enabled) {
        float spk_l_out, spk_r_out;
        if (leak_active) {
            const float in_l = raw[i * actual_ch]     / 32768.0f;
            const float in_r = raw[i * actual_ch + 1] / 32768.0f;
            // High-pass (signal - low-pass) — used ONLY for transient DETECTION,
            // not for output. Outputting the thin treble-only signal is what
            // caused the crackle; we detect on highs but play the full sound.
            hp_l += hp_a * (in_l - hp_l);
            hp_r += hp_a * (in_r - hp_r);
            const float hpf_l = in_l - hp_l;
            const float hpf_r = in_r - hp_r;
            const float mag = 0.5f * ((hpf_l<0?-hpf_l:hpf_l) + (hpf_r<0?-hpf_r:hpf_r));
            // Fast envelope reacts to onsets; slow envelope tracks the baseline.
            env_fast += ((mag > env_fast) ? ENV_FAST_A : ENV_FAST_A*0.25f) * (mag - env_fast);
            env_slow += ENV_SLOW_A * (mag - env_slow);
            // Gate state machine with hysteresis + minimum hold. OPEN on a clear
            // transient; once open, stay open at least `hold_samples`, then close
            // only when the level drops well below the open threshold (0.65x). The
            // gate makes one clean open/close per hit instead of chattering.
            if (!gate_open) {
                if (refractory) {
                    // Burst-capped close: re-arming waits until the signal has
                    // GENUINELY fallen (same release test as a normal close) -
                    // otherwise a sustained sound would re-trigger every N ms and
                    // machine-gun chirps instead of leaking once.
                    if (env_fast <= env_slow * (TRANS_RATIO * 0.65f) + 0.0006f)
                        refractory = false;
                } else if (env_fast > env_slow * TRANS_RATIO + 0.0008f) {
                    gate_open = true;
                    hold_left = hold_samples;
                    burst_left = burst_samples; // 0 = unlimited
                }
            } else {
                if (burst_samples && burst_left && --burst_left == 0) {
                    gate_open = false;      // cap reached: force the close
                    refractory = true;      // one sustained sound = one burst
                } else {
                    if (hold_left > 0) hold_left--;
                    else if (env_fast <= env_slow * (TRANS_RATIO * 0.65f) + 0.0006f)
                        gate_open = false;
                }
            }
            const float target = gate_open ? 1.0f : 0.0f;
            leak_gain += ((target > leak_gain) ? GATE_OPEN : GATE_CLOSE) * (target - leak_gain);
            // Band-pass the output: 12 dB/oct high-pass (two cascaded poles) removes
            // speaker-popping lows and voice fundamentals; 12 dB/oct low-pass removes
            // the treble sizzle that reads as crackle. Only the window leaks.
            ohp1_l += ohp_a * (in_l - ohp1_l);  float bp_l = in_l - ohp1_l;
            ohp2_l += ohp_a * (bp_l - ohp2_l);  bp_l -= ohp2_l;
            ohp1_r += ohp_a * (in_r - ohp1_r);  float bp_r = in_r - ohp1_r;
            ohp2_r += ohp_a * (bp_r - ohp2_r);  bp_r -= ohp2_r;
            olp1_l += olp_a * (bp_l - olp1_l);
            olp2_l += olp_a * (olp1_l - olp2_l);
            olp1_r += olp_a * (bp_r - olp1_r);
            olp2_r += olp_a * (olp1_r - olp2_r);
            spk_l_out = olp2_l * leak_gain * leak_vol * leak_makeup;
            spk_r_out = olp2_r * leak_gain * leak_vol * leak_makeup;
        } else {
            spk_l_out = raw[i * actual_ch]     / 32768.0f * spk_gain;
            spk_r_out = raw[i * actual_ch + 1] / 32768.0f * spk_gain;
        }
        audio_buf[audio_buf_pos++] = spk_l_out;
        audio_buf[audio_buf_pos++] = spk_r_out;
        if (audio_buf_pos == 512 * 2) {
            publish_speaker_block(audio_buf, speaker_generation);
            audio_buf_pos = 0;
        }
        }
#endif
        // Native haptic channels (ch2/3) only exist in 4ch mode. In 2ch mode
        // (Windows/DS4Windows) there are no dedicated haptic channels.
        const float native_input_gain = auto_mode == 0 ? 1.0f : haptics_gain;
        float preserved_native_l = 0.0f, preserved_native_r = 0.0f;
        float h_l = (actual_ch == 4) ? raw[i * 4 + 2] / 32768.0f * native_input_gain : 0.0f;
        float h_r = (actual_ch == 4) ? raw[i * 4 + 3] / 32768.0f * native_input_gain : 0.0f;

        // Auto-haptics runs when the user enables it (mix/replace). Unlike
        // loteran, 2ch input does NOT force it on — so with auto-haptics OFF you
        // still get pure native rumble->DualSense conversion (awalol behavior),
        // even under DS4Windows. Mode is authoritative.
        if (auto_mode > 0) {
            const float spk_l = raw[i * actual_ch    ] / 32768.0f;
            const float spk_r = raw[i * actual_ch + 1] / 32768.0f;
            // DSP source select: ch0/1 (default) or ch2/3. The speaker and the
            // effect leak always read ch0/1, so pointing the DSP at ch2/3 lets
            // the script feed (ds5audio --map rear) drive auto-haptics while
            // ch0/1 carries only the game's own native speaker audio - the one
            // way to have derived haptics without the script's audio reaching
            // the speaker or leaking through the effect leak.
            const float src_l = dsp_rear ? raw[i * actual_ch + 2] / 32768.0f : spk_l;
            const float src_r = dsp_rear ? raw[i * actual_ch + 3] / 32768.0f : spk_r;
            lp_l += lp_a * (src_l - lp_l);
            lp_r += lp_a * (src_r - lp_r);
            // Cascade additional poles for steeper slopes. Each stage adds
            // 6 dB/oct. A single pole leaks male voice fundamentals (85-180 Hz)
            // when the cutoff is near there; more poles reject voice harder.
            float fl = lp_l, fr = lp_r;
            if (n_poles >= 2) {
                lp2_l += lp_a * (lp_l - lp2_l);
                lp2_r += lp_a * (lp_r - lp2_r);
                fl = lp2_l; fr = lp2_r;
                if (n_poles >= 4) {
                    lp3_l += lp_a * (lp2_l - lp3_l);
                    lp3_r += lp_a * (lp2_r - lp3_r);
                    lp4_l += lp_a * (lp3_l - lp4_l);
                    lp4_r += lp_a * (lp3_r - lp4_r);
                    fl = lp4_l; fr = lp4_r;
                }
            }
            const float abs_l = fl < 0.0f ? -fl : fl;
            const float abs_r = fr < 0.0f ? -fr : fr;
            env_l = (abs_l > env_l) ? env_l + ENV_ATK*(abs_l-env_l) : env_l + ENV_REL*(abs_l-env_l);
            env_r = (abs_r > env_r) ? env_r + ENV_ATK*(abs_r-env_r) : env_r + ENV_REL*(abs_r-env_r);
            float use_env_l = env_l, use_env_r = env_r;
            if (split_on) {
                // Low band: 12 dB/oct LP at the crossover on the raw input.
                xo1_l += xo_a * (src_l - xo1_l); xo2_l += xo_a * (xo1_l - xo2_l);
                xo1_r += xo_a * (src_r - xo1_r); xo2_r += xo_a * (xo1_r - xo2_r);
                const float lo_l = xo2_l,      lo_r = xo2_r;
                // High band: everything the main LP kept, minus the low band
                // (phase ripple from the subtraction is irrelevant - only the
                // band's ENVELOPE is used, never its waveform).
                const float hi_l = fl - lo_l,  hi_r = fr - lo_r;
                const float alo_l = lo_l < 0 ? -lo_l : lo_l, alo_r = lo_r < 0 ? -lo_r : lo_r;
                const float ahi_l = hi_l < 0 ? -hi_l : hi_l, ahi_r = hi_r < 0 ? -hi_r : hi_r;
                envlo_l = (alo_l > envlo_l) ? envlo_l + ENV_ATK*(alo_l-envlo_l) : envlo_l + ENV_REL*(alo_l-envlo_l);
                envlo_r = (alo_r > envlo_r) ? envlo_r + ENV_ATK*(alo_r-envlo_r) : envlo_r + ENV_REL*(alo_r-envlo_r);
                envhi_l = (ahi_l > envhi_l) ? envhi_l + ENV_ATK*(ahi_l-envhi_l) : envhi_l + ENV_REL*(ahi_l-envhi_l);
                envhi_r = (ahi_r > envhi_r) ? envhi_r + ENV_ATK*(ahi_r-envhi_r) : envhi_r + ENV_REL*(ahi_r-envhi_r);
                use_env_l = envlo_l * split_lo_g + envhi_l * split_hi_g;
                use_env_r = envlo_r * split_lo_g + envhi_r * split_hi_g;
            }
            // Noise gate with SMOOTHED gain: a hard gate flickers on/off when the
            // bass envelope hovers near the threshold, chopping the output (jagged
            // feel). Compute a target gate gain, then slew toward it so the gate
            // opens/closes smoothly instead of switching.
            const float GATE_KNEE   = 0.04f; // wider knee = gentler transition
             // smoothed gate gain memory
            // Gate slew: ~5 ms open, ~60 ms close, at 48 kHz frame rate.
            constexpr float GATE_OPEN = 0.20f, GATE_CLOSE = 0.02f;
            float genv_l = use_env_l, genv_r = use_env_r;
            if (GATE_THRESH > 0.0f) {
                float tgt_l = (use_env_l - GATE_THRESH) / GATE_KNEE;
                float tgt_r = (use_env_r - GATE_THRESH) / GATE_KNEE;
                tgt_l = tgt_l < 0.0f ? 0.0f : (tgt_l > 1.0f ? 1.0f : tgt_l);
                tgt_r = tgt_r < 0.0f ? 0.0f : (tgt_r > 1.0f ? 1.0f : tgt_r);
                gsm_l += ((tgt_l > gsm_l) ? GATE_OPEN : GATE_CLOSE) * (tgt_l - gsm_l);
                gsm_r += ((tgt_r > gsm_r) ? GATE_OPEN : GATE_CLOSE) * (tgt_r - gsm_r);
                genv_l = use_env_l * gsm_l;
                genv_r = use_env_r * gsm_r;
            }
            // Bass envelope amplitude-modulates a 90 Hz carrier so the voice-coil
            // actuator can render it (a near-DC low-passed signal produces no
            // motion; the carrier puts energy in the actuator's responsive band).

            carrier_ph += 2.0f * (float)M_PI * 90.0f / 48000.0f;
            if (carrier_ph > 2.0f*(float)M_PI) carrier_ph -= 2.0f*(float)M_PI;
            const float carrier = sinf(carrier_ph);
            // Separate carriers for CONVERTED RUMBLE. The two motor values a game
            // sends are not interchangeable: left is the heavy/low-frequency
            // motor, right the light/high-frequency one. Rendering both on the
            // same 90 Hz tone threw away that distinction and sat between the two
            // frequencies the actuators render most convincingly, which is a large
            // part of why converted rumble felt thin next to the controller's own
            // rumble emulation. 60 Hz reads as a heavy churn, 160 Hz as a sharp
            // buzz - together they feel like actual dual-motor rumble.

            rc_lo_ph += 2.0f * (float)M_PI * 60.0f  / 48000.0f;
            rc_hi_ph += 2.0f * (float)M_PI * 160.0f / 48000.0f;
            if (rc_lo_ph > 2.0f*(float)M_PI) rc_lo_ph -= 2.0f*(float)M_PI;
            if (rc_hi_ph > 2.0f*(float)M_PI) rc_hi_ph -= 2.0f*(float)M_PI;
            // Keep phase progression unchanged even while a motor is silent.
            const uint8_t rumble_l = g_rumble_l, rumble_r = g_rumble_r;
            const bool rumble_active = auto_mode == 1 && rumble_str > 0.0f;
            const float rc_lo = rumble_active && rumble_l != 0 ? sinf(rc_lo_ph) : 0.0f;
            const float rc_hi = rumble_active && rumble_r != 0 ? sinf(rc_hi_ph) : 0.0f;
            float al = genv_l * carrier * auto_gain;
            float ar = genv_r * carrier * auto_gain;
            // Keep the generator's tanh shaping; Mix limits only combined peaks afterwards.
            al = tanhf(al);
            ar = tanhf(ar);
            // Derived-haptic meter: capture al/ar here, before Mix folds in native
            // passthrough and converted rumble, so the meter shows only what
            // auto-haptics itself produces (al/ar are not reassigned in Mix).
            { const float aa = al < 0 ? -al : al, ab = ar < 0 ? -ar : ar;
              const float mx = aa > ab ? aa : ab; if (mx > ah_out_pk) ah_out_pk = mx; }
            if (auto_mode == 2) {
                // Replace: derived only
                h_l = al; h_r = ar;
            } else {
                // Native fidelity: apply the profile level, without the derived-audio filter.

                native_lp_l += lp_a * (h_l - native_lp_l);
                native_lp_r += lp_a * (h_r - native_lp_r);
                const float nat_l = cfg.mix_native_filter ? native_lp_l : h_l;
                const float nat_r = cfg.mix_native_filter ? native_lp_r : h_r;
                // Converted rumble: DS4Windows sends motor intensities (0-255) for
                // Xbox360/DS4 emulation. Turn them into an actuator vibration using
                // the same 90 Hz carrier and blend in, scaled by a configurable
                // strength so native rumble doesn't overpower the audio haptics.
                const float rl = (rumble_l / 255.0f) * rc_lo * rumble_str;
                const float rr = (rumble_r / 255.0f) * rc_hi * rumble_str;
                // Keep native amplitude; additional signals use remaining headroom.
                preserved_native_l = clamp(nat_l * native_lvl, -1.0f, 1.0f);
                preserved_native_r = clamp(nat_r * native_lvl, -1.0f, 1.0f);
                h_l = haptic_mix(0.0f, al, rl);
                h_r = haptic_mix(0.0f, ar, rr);
            }
        }
        // Anti-aliasing for the 48k->3k haptic decimation below (CONFIGURABLE —
        // portal "Native Haptics" section). The unfiltered 16x decimation folds
        // content above 1.5 kHz back as gritty noise; filtering removes the grit
        // but also softens transient snap, so the strength is a preference:
        //   1 = off    — raw pre-1.0.4 texture (gritty but sharp)
        //   2 = light  — single pole ~2.4 kHz: kills most fold-back, keeps snap
        //   3 = strong — two poles ~1.3 kHz: maximum smoothness (can feel muted)
        if (auto_mode > 0 && aa_mode >= 2) {

            if (aa_mode == 2) {
                constexpr float A = 0.27f;   // ~2.4 kHz @ 48 kHz
                aa1_l += A * (h_l - aa1_l);
                aa1_r += A * (h_r - aa1_r);
                h_l = aa1_l;
                h_r = aa1_r;
            } else {
                constexpr float A = 0.157f;  // ~1.3 kHz @ 48 kHz
                aa1_l += A * (h_l - aa1_l);
                aa1_r += A * (h_r - aa1_r);
                aa2_l += A * (aa1_l - aa2_l);
                aa2_r += A * (aa1_r - aa2_r);
                h_l = aa2_l;
                h_r = aa2_r;
            }
        }
        if (auto_mode == 1) {
            const float room_l = 1.0f - fabsf(preserved_native_l);
            const float room_r = 1.0f - fabsf(preserved_native_r);
            h_l = preserved_native_l + clamp(h_l, -room_l, room_l);
            h_r = preserved_native_r + clamp(h_r, -room_r, room_r);
        }
        in_buf[i * 2]     = static_cast<WDL_ResampleSample>(clamp(h_l, -1.0f, 1.0f));
        in_buf[i * 2 + 1] = static_cast<WDL_ResampleSample>(clamp(h_r, -1.0f, 1.0f));
    }
    // Keep the same block peak and activity semantics; only the sample scan is
    // shared with the DSP loop above. Feed mode makes nframes equal `frames`.
    {
        extern volatile uint16_t g_diag_ch01_peak, g_diag_ch23_peak;
        extern volatile uint16_t g_ah_frames;
        extern volatile uint8_t g_ah_in_peak;
        g_diag_ch01_peak = (uint16_t)p01;
        g_diag_ch23_peak = (uint16_t)p23;
        const uint32_t f = (uint32_t)g_ah_frames + (uint32_t)frames;
        g_ah_frames = f > 0xFFFF ? 0xFFFF : (uint16_t)f;
        const uint8_t v = (uint8_t)(p01 >> 7);
        if (v > g_ah_in_peak) g_ah_in_peak = v;
    }
    { extern volatile uint8_t g_ah_out_peak;
      const uint8_t v = ah_out_pk >= 1.0f ? 255 : (uint8_t)(ah_out_pk * 255.0f);
      if (v > g_ah_out_peak) g_ah_out_peak = v;
      extern volatile uint8_t g_oled_ah_input_peak, g_oled_ah_output_peak;
      const uint8_t input_v = p01 >= 32768 ? 255 : static_cast<uint8_t>(p01 >> 7);
      if (input_v > g_oled_ah_input_peak) g_oled_ah_input_peak = input_v;
      if (v > g_oled_ah_output_peak) g_oled_ah_output_peak = v;
      }

    // 3. 48kHz -> 3kHz 重采样
    static WDL_ResampleSample out_buf[SAMPLE_SIZE]; // 64 floats = 32帧 × 2ch
    const int out_frames = resampler.ResampleOut(out_buf, nframes, nframes / 4, OUTPUT_CHANNELS);


    // 4. 转换为int8并缓冲，满64字节即组包发送
    for (int i = 0; i < out_frames; i++) {
        int val_l = static_cast<int>(out_buf[i * 2] * 127.0f * (auto_mode == 0 ? haptics_gain : 1.0f));
        int val_r = static_cast<int>(out_buf[i * 2 + 1] * 127.0f * (auto_mode == 0 ? haptics_gain : 1.0f));
        haptic_buf[haptic_buf_pos++] = (int8_t) clamp(val_l, -128, 127); // 似乎clamp有点多余？还是以防万一吧
        haptic_buf[haptic_buf_pos++] = (int8_t) clamp(val_r, -128, 127);

        if (haptic_buf_pos != SAMPLE_SIZE) {
            continue;
        }
        uint8_t pkt[REPORT_SIZE]{};
        pkt[0] = REPORT_ID;
        pkt[1] = reportSeqCounter << 4;
        reportSeqCounter = (reportSeqCounter + 1) & 0x0F;
        pkt[2] = 0x11 | 0 << 6 | 1 << 7;
        pkt[3] = 7;
        // bit0 enables controller mic streaming. Gate it on the host actually
        // opening the mic IN interface (set_mic_active from tud_audio_set_itf_cb)
        // AND on the user not disabling the mic (config.disable_mic), so the
        // DualSense only streams mic audio -- and core1 only decodes it -- while
        // an app is recording. Other bits (speaker/haptics) stay enabled.
        pkt[4] = (mic_active && !cfg.disable_mic) ? 0b11111111 : 0b11111110;
        const auto buf_len = cfg.audio_buffer_length;
        pkt[5] = buf_len;
        pkt[6] = buf_len;
        pkt[7] = buf_len;
        pkt[8] = buf_len; // 这 4 个字节的作用未知，调整没有效果
        pkt[9] = buf_len; // audio buffer length 只有调整这个字节生效。
        pkt[10] = packetCounter++;
        // SetStateData
        pkt[11] = 0x10 | 0 << 6 | 1 << 7;
        pkt[12] = 63;
        if (auto_mode != 0) state_set(pkt + 13,63);
        // Haptics Audio Data
        pkt[76] = 0x12 | 0 << 6 | 1 << 7;
        pkt[77] = SAMPLE_SIZE;
        memcpy(pkt + 78, haptic_buf, SAMPLE_SIZE);
#if !DISABLE_SPEAKER_PROC
        // Speaker Audio Data -- omitted entirely when the user disables the
        // speaker/headset (config.disable_speaker), so the controller's speaker
        // amp isn't driven (mirrors the Pico W no-speaker report).
        if (speaker_enabled) {
            pkt[142] = (plug_headset ? 0x16 : 0x13) | 0x80;
            pkt[143] = 200;
            if (!take_speaker_frame(pkt + 144)) {
                if (opus_silence_valid) memcpy(pkt + 144, opus_silence_buf, 200);
                else { pkt[142] = 0; pkt[143] = 0; }
            }
        }
#endif

        if (auto_mode == 0) {
            // Native audio carries no cached controller state; host/synth use 0x31.
            memmove(pkt + 11, pkt + 76, sizeof(pkt) - 76 - 4);
            memset(pkt + sizeof(pkt) - 65 - 4, 0, 65);
        }
        bt_write(pkt, sizeof(pkt));
        haptic_buf_pos = 0;
    }
}

void audio_init() {
    resampler.SetMode(true, 0, false);
    resampler.SetRates(48000, 3000);
    resampler.SetFeedMode(true);
    resampler.Prealloc(2, 24, 6);
    // Mic queues are read from audio_loop on core0 every iteration, so they
    // must exist regardless of the speaker-proc build flag.
    queue_init(&mic_fifo, sizeof(mic_element), 2);
    queue_init(&mic_decode_fifo, sizeof(mic_decode_element), 2);
#if !DISABLE_SPEAKER_PROC
    // Depth 2 (upstream change): with a 1-deep queue, any scheduling slip between
    // core0 (producer) and core1 (speaker_proc) dropped a whole 10.67 ms block via
    // the full->remove-oldest branch — an audible/tactile discontinuity. One frame
    // of slack absorbs the cross-core variance.
    queue_init(&audio_fifo, sizeof(uint8_t), 2);
    queue_init(&free_speaker_blocks, sizeof(uint8_t), 3);
    for (uint8_t index = 0; index < 3; ++index) {
        const bool added = queue_try_add(&free_speaker_blocks, &index);
        hard_assert(added);
    }
    critical_section_init(&opus_cs);
    multicore_launch_core1_with_stack(core1_entry, audio_core1_stack, sizeof(audio_core1_stack));
#endif
}

static OpusEncoder *encoder;
static OpusDecoder *decoder; // mic decoder
static WDL_Resampler resampler_audio;

// Speaker path: USB OUT PCM (core0 audio_fifo) -> resample -> opus encode ->
// the bounded result queue for the haptics/speaker BT report. Non-blocking so core1 can also
// service the mic path. Kept in RAM to remove XIP miss latency from the loop.
static void __not_in_flash_func(encode_speaker_block)(const audio_raw_element &audio_element) {
    // Drain disabled speaker work without resampling/encoding; mic still runs.
    critical_section_enter_blocking(&opus_cs);
    const bool current = audio_element.generation == speaker_generation;
    critical_section_exit(&opus_cs);
    if (!current) return;
    static uint32_t worker_generation = 1;
    if (worker_generation != audio_element.generation) {
        resampler_audio.Reset();
        if (opus_encoder_ctl(encoder, OPUS_RESET_STATE) != OPUS_OK) return;
        worker_generation = audio_element.generation;
    }
    // 将 512 frames 重采样成 480 frames 以解决噪音问题。感谢 @Junhoo
    WDL_ResampleSample *in_buf;
    int nframes = resampler_audio.ResamplePrepare(512, 2, &in_buf);
    if (nframes < 0 || nframes > 512 || in_buf == nullptr) { ++g_speaker_stats.encode_failed; return; }
    for (int i = 0; i < nframes * 2; i++) {
        in_buf[i] = audio_element.data[i];
    }
    static WDL_ResampleSample out_buf[480 * 2];
    if (resampler_audio.ResampleOut(out_buf, nframes, 480, 2) != 480) { ++g_speaker_stats.encode_failed; return; }

    static uint8_t out[200];
    const opus_int32 encoded_bytes = opus_encode_float(
        encoder, out_buf, 480, out, static_cast<opus_int32>(sizeof(out)));
    // The Bluetooth speaker report always carries a 200-byte Opus payload.
    // With this encoder's fixed 160 kb/s, 10 ms CBR configuration a successful
    // frame is exactly 200 bytes. Keep the last valid packet on any failure or
    // unexpected short frame instead of publishing a partial/stale-tail packet.
    if (encoded_bytes != static_cast<opus_int32>(sizeof(out))) {
        ++g_speaker_stats.encode_failed;
#if ENABLE_VERBOSE
        printf("[Audio] OpusEncoder encode returned %ld bytes (expected %u)\n",
               static_cast<long>(encoded_bytes), static_cast<unsigned>(sizeof(out)));
#endif
        return;
    }
    publish_speaker_frame(out, audio_element.generation, audio_element.sequence);
}

static void __not_in_flash_func(speaker_proc)() {
    uint8_t index;
    if (!queue_try_remove(&audio_fifo, &index)) return;
    encode_speaker_block(speaker_blocks[index]);
    release_speaker_block(index);
}

// Mic path: opus packets from the controller (core0 mic_fifo) -> opus decode ->
// PCM into mic_decode_fifo for audio_loop to push to the USB IN endpoint.
static void __not_in_flash_func(mic_proc)() {
    if (decoder == nullptr) {
        queue_try_remove(&mic_fifo, nullptr);
        return;
    }
    static mic_element mic_packet{};
    if (!queue_try_remove(&mic_fifo, &mic_packet)) {
        return;
    }
    static uint32_t decoder_generation = 0;
    if (decoder_generation != mic_packet.generation) {
        if (opus_decoder_ctl(decoder, OPUS_RESET_STATE) != OPUS_OK) return;
        decoder_generation = mic_packet.generation;
    }
    static int16_t decoded_data[MIC_FRAMES * MIC_CHANNELS];
    auto decoded_samples = opus_decode(decoder, mic_packet.data, MIC_OPUS_SIZE, decoded_data, MIC_FRAMES, false);
    if (decoded_samples <= 0) {
        // Gated behind ENABLE_VERBOSE: printf pulls the newlib formatting chain
        // (flash) onto core1's path. Release builds compile it out so core1's
        // audio loop stays fully RAM-resident (no XIP fetches on this core).
#if ENABLE_VERBOSE
        printf("[Audio] OpusDecoder decode failed: %d\n", decoded_samples);
#endif
        return;
    }
    static mic_decode_element decode_element{};
    decode_element.generation = mic_packet.generation;
    decode_element.len = decoded_samples * MIC_CHANNELS * sizeof(int16_t);
    memcpy(decode_element.data, decoded_data, decode_element.len);
    if (queue_is_full(&mic_decode_fifo)) {
        queue_try_remove(&mic_decode_fifo, NULL);
    }
    queue_try_add(&mic_decode_fifo, &decode_element);
}

void __not_in_flash_func(core1_entry)() {
    // Register core1 as a flash-safe victim so core0's flash_safe_execute() really
    // parks this core while flash is accessed, instead of letting it fault on XIP.
    // Used by config_save() (flash erase/program) and the BOOTSEL poll (which briefly
    // floats QSPI CSn) - the latter makes polling BOOTSEL safe while audio streams on
    // core1. Requires PICO_FLASH_ASSUME_CORE1_SAFE=0.
    flash_safe_execute_core_init();
    int error = 0;
    encoder = opus_encoder_create(48000, 2,OPUS_APPLICATION_RESTRICTED_LOWDELAY, &error);
    if (error != 0) {
        printf("[Audio] OpusEncoder create failed\n");
        audio_worker_failed.store(true, std::memory_order_release);
        return;
    }
    if (opus_encoder_ctl(encoder, OPUS_SET_EXPERT_FRAME_DURATION(OPUS_FRAMESIZE_10_MS)) != OPUS_OK ||
        opus_encoder_ctl(encoder, OPUS_SET_BITRATE(200 * 8 * 100)) != OPUS_OK ||
        opus_encoder_ctl(encoder, OPUS_SET_VBR(false)) != OPUS_OK ||
        opus_encoder_ctl(encoder, OPUS_SET_COMPLEXITY(0)) != OPUS_OK) {
        printf("[Audio] OpusEncoder configuration failed\n");
        opus_encoder_destroy(encoder);
        encoder = nullptr;
        audio_worker_failed.store(true, std::memory_order_release);
        return;
    }
    // Generate one valid CBR silence packet for encoder starvation/error gaps.
    // Startup-only read from flash; this adds no permanent PCM scratch buffer.
    static const float silent_pcm[480 * 2]{};
    uint8_t silent_packet[200];
    const int silence_bytes = opus_encode_float(encoder, silent_pcm, 480,
                                               silent_packet, sizeof(silent_packet));
    const int reset_status = opus_encoder_ctl(encoder, OPUS_RESET_STATE);
    critical_section_enter_blocking(&opus_cs);
    if (silence_bytes == sizeof(silent_packet) && reset_status == OPUS_OK) {
        memcpy(opus_silence_buf, silent_packet, sizeof(silent_packet));
        opus_silence_valid = true;
    }
    critical_section_exit(&opus_cs);
    if (reset_status != OPUS_OK) {
        opus_encoder_destroy(encoder);
        encoder = nullptr;
        audio_worker_failed.store(true, std::memory_order_release);
        return;
    }
    resampler_audio.SetMode(true, 0, false);
    resampler_audio.SetRates(51200, 48000);
    resampler_audio.SetFeedMode(true);
    resampler_audio.Prealloc(2, 512, 480);
    decoder = opus_decoder_create(48000, MIC_CHANNELS, &error);
    if (error != 0) {
        printf("[Audio] OpusDecoder create failed\n");
    }

    while (true) {
        uint8_t requested = 1;
        if (audio_stop_state.compare_exchange_strong(requested, 2)) {
            while (audio_stop_state.load(std::memory_order_acquire) == 2) __wfe();
            if (audio_stop_state.load(std::memory_order_acquire) == 3)
                while (true) __wfe();
        }
        if (!audio_link_active.load(std::memory_order_relaxed)) {
            __wfe();
            continue;
        }
        speaker_proc();
        mic_proc();
        // Queue publication/stop/link changes issue SEV. A notification that
        // races with this check remains pending, so no fixed wake latency is added.
        if (queue_is_empty(&audio_fifo) && queue_is_empty(&mic_fifo)) __wfe();
    }
}

// data points at the opus mic payload, len is the bytes available there.
// In RAM (consistent with the BT-receive path) and validates len so a short
// or malformed report can't over-read past the packet buffer.
void __not_in_flash_func(mic_add_queue)(uint8_t *data, uint16_t len) {
    if (!mic_active || len < MIC_OPUS_SIZE) return;
    static mic_element mic_packet{};
    mic_packet.generation = mic_stream_generation;
    memcpy(mic_packet.data, data, MIC_OPUS_SIZE);
    if (queue_is_full(&mic_fifo)) {
        queue_try_remove(&mic_fifo, NULL);
    }
    queue_try_add(&mic_fifo, &mic_packet);
}
