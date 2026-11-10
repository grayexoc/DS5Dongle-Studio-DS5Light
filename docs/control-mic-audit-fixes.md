# Control transport, Edge snapshot and microphone fixes

Source validated and built as studio-xinput-exp.18 after the user's final build request.

- HID control commands use a core0-owned queue of eight MTU-sized entries. Send-ready events perform transmission. ACL buffer exhaustion allows three total attempts, retaining command order; other errors and queue overflow are logged. Queue contents are cleared on control-channel close/disconnect.
- `set_feature_data` returns queue admission, not controller acknowledgement. Edge post-write regeneration begins only after successful L2CAP submission. Bluetooth submission still does not prove controller storage succeeded.
- Edge prefetch clears stale profile cache and requires responses for all twelve profile reports. Missing reports are requested over at most three paced rounds. Incomplete snapshots stay gated; late replies can complete them. Reconnection resets prior post-save work.
- Microphone PCM retains an unsent tail and retries on later loop passes. Only one block is retained, for at most 20 ms; old data is dropped to bound latency. Closing/reopening the mic or disconnecting invalidates the tail. Mute also clears retained audio.

Regression checks execute extracted production code: control ordering, buffer-full retry and exhaustion, queue admission, delayed/missing Edge responses, reconnect, mic gain/mute, partial writes, close/reopen and pending age. ARM syntax-only checks passed for audio, Bluetooth, Edge, main and USB. No new dependency, profile format or DS5Light command was added.

The earlier intermediate build was superseded by the final exp.18 build, including all follow-up fixes and automatic mute LED suppression for enabled mute-button mappings/macros. Suppression changes composed output only; removing the binding restores the cached host LED intent. The mute LED allow bit participates in delivery tracking. Regression checks cover controller mappings, keyboard macros, disabled entries and host-value restoration.

Final artifact: build/xinput/studio-xinput-exp.18.uf2. Older versioned UF2s are preserved. No device was flashed. Hardware verification remains pending, especially mute LED behavior, Edge profile loading/saving and microphone continuity under USB load.
