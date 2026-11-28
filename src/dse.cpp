//
// DualSense Edge profile support. See dse.h for the protocol overview.
//

#include "dse.h"
#include "bt.h"
#include <cstdio>
#include <cstring>
#include <vector>
#include <unordered_map>
#include "pico/time.h"

// Provided by bt.cpp
extern std::unordered_map<uint8_t, std::vector<uint8_t> > feature_data;
enum class UnlockPhase { Idle, Handshake, Unlock, Wait };
static UnlockPhase unlock_phase = UnlockPhase::Idle;
static uint32_t unlock_started_ms = 0;
static bool edge_connected = false;

// False from connect until the unlock + prefetch completes. While false the
// USB GET handler NAKs profile reads so the PS app retries (it polls these
// repeatedly during load) instead of caching an empty snapshot. This avoids
// any USB enumeration delay.
static bool profiles_ready = false;

// Post-save snapshot regeneration tracking.
static uint32_t post_save_step_ms = 0;
static uint32_t post_save_attempt_ms = 0;
static uint8_t post_save_stage = 0;

// Paced profile prefetch sequencer. Fetching all 12 profile reports as a
// burst overflows the L2CAP control channel and silently drops requests
// (observed as one profile showing "not assigned"). One GET per 80ms is
// reliable.
static uint8_t prefetch_next = 0;       // 0 = idle, else next report id
static uint32_t prefetch_last_ms = 0;
static uint16_t prefetch_received = 0;
static uint8_t prefetch_round = 0;

static bool request_feature(uint8_t report_id) {
    const uint8_t request[]{0x43, report_id};
    return bt_control_send(request, sizeof(request));
}

static bool request_unlock() {
    // SET 0x80 needs a CRC32 trailer. set_feature_data appends it.
    uint8_t unlock[59]{0x70, 0x01};
    return set_feature_data(0x80, unlock, sizeof(unlock));
}

static void prefetch_start() {
    prefetch_received = 0;
    prefetch_round = 0;
    prefetch_next = 0x70;
    prefetch_last_ms = 0;
    profiles_ready = false;
    for (uint8_t id=0x70; id<=0x7b; ++id) feature_data.erase(id);
}

bool dse_is_profile_report(uint8_t reportId) {
    return reportId >= 0x70 && reportId <= 0x7B;
}

bool dse_profiles_ready() {
    return profiles_ready;
}

void dse_on_disconnect() {
    edge_connected = false;
    unlock_phase = UnlockPhase::Idle;
    unlock_started_ms = 0;
    profiles_ready = false;
    prefetch_next = 0;
    prefetch_last_ms = 0;
    prefetch_received = 0;
    prefetch_round = 0;
    post_save_stage = 0;
    post_save_step_ms = 0;
    post_save_attempt_ms = 0;
}

void dse_on_connect() {
    dse_on_disconnect();
    edge_connected = true;
    unlock_phase = UnlockPhase::Handshake;
    unlock_started_ms = to_ms_since_boot(get_absolute_time()) - 80;
}

void dse_on_control_packet(const uint8_t *packet, uint16_t size) {
    if (!edge_connected || !packet || !size) return;
    if (packet[0] == 0xA3 && size >= 2 && dse_is_profile_report(packet[1])) {
        if (size != DSE_PROFILE_PACKET_SIZE || unlock_phase != UnlockPhase::Idle) return;
        const uint8_t report_id = packet[1];
        feature_data[report_id].assign(packet + 1, packet + size);
        prefetch_received |= 1u << (report_id - 0x70);
        if (prefetch_received == 0x0fff) profiles_ready = true;
    }
    // 1-byte HID HANDSHAKE in response to a SET command:
    // 0x00 = SUCCESS, 0x04 = ERR_INVALID_PARAMETER (command rejected).
    if (size == 1 && (packet[0] & 0xF0) == 0x00) {
        printf("[DSE] HID HANDSHAKE: 0x%02X (%s)\n", packet[0],
               packet[0] == 0x00 ? "success" : "rejected");
    }
}

void dse_on_profile_write(uint8_t reportId) {
    if (edge_connected && reportId >= 0x60 && reportId <= 0x62) {
        post_save_step_ms = to_ms_since_boot(get_absolute_time());
        post_save_attempt_ms = post_save_step_ms;
        post_save_stage = 1;
    }
}

void dse_task() {
    if (!edge_connected) return;
    const uint32_t now = to_ms_since_boot(get_absolute_time());

    if (unlock_phase == UnlockPhase::Handshake) {
        if (now - unlock_started_ms < 80) return;
        unlock_started_ms = now;
        const auto fw = feature_data.find(0x20);
        if (fw == feature_data.end() || fw->second.size() < 62) {
            request_feature(0x20);
            return;
        }
        uint8_t handshake[63]{0x53, 0x65};
        memcpy(handshake + 2, fw->second.data() + 1, 61);
        if (!bt_control_send(handshake, sizeof(handshake))) return;
        unlock_phase = UnlockPhase::Unlock;
        unlock_started_ms = now - 80;
    }
    if (unlock_phase == UnlockPhase::Unlock) {
        if (now - unlock_started_ms < 80) return;
        unlock_started_ms = now;
        if (!request_unlock()) return;
        unlock_phase = UnlockPhase::Wait;
    }
    if (unlock_phase == UnlockPhase::Wait) {
        if (now - unlock_started_ms < 4000) return;
        prefetch_start();
        unlock_phase = UnlockPhase::Idle;
        printf("[DSE] Unlock wait done, prefetching profile reports\n");
    }

    // Pace attempts even if the control queue is full.
    if (prefetch_next != 0 && now - prefetch_last_ms >= 80) {
        prefetch_last_ms = now;
        if (profiles_ready) {
            prefetch_next = 0;
        } else if (prefetch_next == 0x7c) {
            if (++prefetch_round >= 3) {
                prefetch_next = 0;
                printf("[DSE] Profile snapshot incomplete; reads remain gated\n");
            } else {
                prefetch_next = 0x70;
            }
        } else if ((prefetch_received & (1u << (prefetch_next - 0x70))) ||
                   request_feature(prefetch_next)) {
            ++prefetch_next;
        }
    }

    // Replay the post-save unlock, six spaced status polls, and refetch.
    if (post_save_stage == 0 || now - post_save_attempt_ms < 80) return;
    const uint32_t elapsed = now - post_save_step_ms;
    if (post_save_stage == 1 && elapsed >= 500) {
        post_save_attempt_ms = now;
        if (!request_unlock()) return;
        post_save_stage = 2;
        post_save_step_ms = now;
        printf("[DSE] Post-save: re-sent 0x80\n");
    } else if (post_save_stage >= 2 && post_save_stage <= 7 &&
               elapsed >= (post_save_stage == 2 ? 500 : 250)) {
        post_save_attempt_ms = now;
        if (!request_feature(0x81)) return;
        ++post_save_stage;
        post_save_step_ms = now;
    } else if (post_save_stage == 8 && elapsed >= 3250) {
        prefetch_start();
        post_save_stage = 0;
        printf("[DSE] Post-save: profile snapshot refetch started\n");
    }
}
