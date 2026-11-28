# Control transport, Edge snapshot and microphone fixes

These control, Edge and microphone fixes are included in the integrated Studio firmware.

- HID control commands use a core0-owned queue of eight MTU-sized entries. Send-ready events perform transmission. ACL buffer exhaustion allows three total attempts, retaining command order; other errors and queue overflow are logged. Queue contents are cleared on control-channel close/disconnect.
- `set_feature_data` returns queue admission, not controller acknowledgement. Edge post-write regeneration begins only after successful L2CAP submission. Bluetooth submission still does not prove controller storage succeeded.
- Edge profile reads stay gated until all twelve reports have a complete 65-byte Bluetooth HIDP response. The size follows the Edge descriptor's 63-byte payload plus report ID and HIDP header. Prefetch clears the prior cache and requests missing reports over at most three paced rounds. A full control queue delays handshake, unlock, prefetch and post-save polls without advancing their stages. Closing either required HID channel or losing the ACL discards pending Edge work and cached replies.
- Microphone PCM retains an unsent tail and retries on later loop passes. Only one block is retained, for at most 20 ms; old data is dropped to bound latency. Closing/reopening the mic or disconnecting invalidates the tail. Mute also clears retained audio.

Regression checks execute extracted production code: control ordering, buffer-full retry and exhaustion, queue admission, delayed/missing Edge responses, reconnect, mic gain/mute, partial writes, close/reopen and pending age. ARM syntax-only checks passed for audio, Bluetooth, Edge, main and USB. No new dependency, profile format or DS5Light command was added.

Enabled mute-button mappings/macros suppress the automatic mute LED. Suppression changes composed output only; removing the binding restores the cached host LED intent. The mute LED allow bit participates in delivery tracking. Regression checks cover controller mappings, keyboard macros, disabled entries and host-value restoration.

Hardware verification remains pending, especially mute LED behavior, Edge profile loading/saving and microphone continuity under USB load. Current build instructions are in release-versioning.md.
