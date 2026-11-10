# Audit/review fixes (source only)

No new UF2 or device flash in this change.

- USB string lookup rejects unknown indices before strlen.
- USB speaker set/get use inverse mappings and the same speaker setting; sync also updates the headset.
- USB microphone mute produces zero PCM without stopping the stream clock.
- Successful-output tracking covers audio control and triggers as well as rumble. Dropped control state remains pending.
- Repeated unchanged native trigger requests are limited to 8 ms; other unchanged reports are suppressed during speaker streaming. Identical queued 0x31 reports share one queue entry.
- Native audio still omits cached controller state. Volume/gain updates are delivered by the separate state path. Profile activation uses the shared live config application path.
- Stream close, 60 ms inactivity, mode change and link change invalidate partial buffers and queued audio, and reset DSP history before the next block.
- Profile sectors and macro storage use a shared redo image and commit record at flash sectors -23/-24. Existing slot/macro addresses are unchanged. Boot recovers before configuration loading and before core1 starts. Firmware size checks reserve the added space. One 4 KB RAM work buffer is shared by save and recovery.
- Duplicated packet/queue test implementations were replaced by tests extracting production paths.

Validation: run_audit_fixes_test.py exercises 2,176 save interruption points and 1,056 recovery interruption points with mocked flash; USB controls/string/mic, stream/DSP reset, queue admission/discard and native packet layout. Existing haptic delivery, rumble shaping, LED, lightbar/profile migration, upstream reliability and BOOTSEL regressions also pass. ARM syntax checks use the experimental compile configuration.

Limits: flash tests model torn writes/erases, not physical brownout behavior or bit rot. The redo scheme adds flash writes/erase time to explicit slot/macro saves. No full firmware link, device power-loss test, BT congestion measurement or wired/native tactile comparison was performed. Older firmware does not replay this new redo record; finish recovery on this firmware before downgrading after an interrupted save.
