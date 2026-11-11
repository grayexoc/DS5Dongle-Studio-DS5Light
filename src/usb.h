//
// Created by awalol on 2026/3/4.
//

#ifndef DS5_BRIDGE_USB_H
#define DS5_BRIDGE_USB_H
#include <cstdint>

extern uint8_t mute[2]; // 0: SPEAKER(0x02) 1: MIC(0x05)
extern float volume[2]; // 0: SPEAKER(0x02) 1: MIC(0x05)

// Present ONLY the wake keyboard (controller away, wake on) so the host keeps a
// device it can be woken from without a phantom gamepad appearing.
void usb_set_idle_pid(bool on);
bool usb_xinput_active();
void usb_select_host_mode();
bool usb_is_idle_pid(void);
// True if the identity the HOST currently has enumerated is the idle one
// (latched at GET_DESCRIPTOR, unlike usb_is_idle_pid which is only intent).
bool usb_served_idle_pid(void);
void usb_schedule_reconnect();
void usb_cancel_reconnect();
bool usb_reconnect_pending();
void usb_reconnect_task();
uint16_t usb_profile_event_get(uint8_t *buffer, uint16_t length);
void usb_profile_event_task();

#endif //DS5_BRIDGE_USB_H
