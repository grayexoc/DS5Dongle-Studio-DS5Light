#pragma once
#include <cstdint>

bool manual_power_boot_is_resume();
void manual_power_restore_profile();
void manual_power_init();
void manual_power_request_sleep();
enum class ManualPowerState : uint8_t {
    Idle = 0, WaitingReply = 1, Scheduled = 2, Stopping = 3, Failed = 4
};
enum class ManualPowerError : uint8_t {
    None = 0, SaveFailed = 1, WorkerStopFailed = 2, ReplyTimeout = 3
};
void manual_power_request_host_sleep();
void manual_power_sleep_reply_read();
ManualPowerState manual_power_state();
ManualPowerError manual_power_error();
void manual_power_task();
void manual_power_note_activity(uint32_t grace_ms = 30000);
[[noreturn]] void manual_power_reboot();
