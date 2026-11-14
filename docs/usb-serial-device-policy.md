# USB serial number: device policy

The app places **USB 시리얼 숨기기 / Hide USB serial number** below the dock-disconnect option in **Pico 설정 / Pico settings**. It saves immediately, separately from profiles. Both ordinary DualSense and Edge Native USB identities can omit `iSerialNumber`. XInput retains its existing descriptors; a stored choice takes effect when returning to Native mode. The controller-off identity is unchanged.

## Migration and persistence

On first boot, the previously saved current configuration's `disable_usb_sn` is adopted once. The common value and an initialized bit are stored in the CRC-protected config-journal identity, outside profile bodies. Existing profile layout, slot CRCs and profile fingerprints are retained. Old profile bytes remain for layout compatibility but do not drive USB descriptors. Loading or restoring an old OFF profile cannot turn off an initialized ON policy; an explicitly saved common OFF also cannot be re-enabled by old ON profiles.

`USB_SERIAL_HIDE_BIT=0x08000000` and `USB_SERIAL_INITIALIZED_BIT=0x04000000` do not overlap the profile tag or existing device-policy flags. Initial migration uses the existing idle-safe deferred save path. Successful common-policy writes and normal config saves also persist the initialization marker. If a newer journal body is complete but its footer is torn, common policy is recovered from the latest complete CRC-valid device identity. Before initialization, the legacy value is read from that same committed record. This avoids importing a subsequently loaded profile after an interrupted migration save.

## App protocol

New command `0x21` uses the same framing as standby/dock device policies:

- `[0]`: read; `[1, enabled]`: persist with enabled 0 or 1.
- Feature report `0x84`: `66 21 status 01 actual_value`, padded to 63 bytes.
- Status 0 succeeds; 1 is invalid request; 2 rejects/failed persistence. Failure reports the unchanged actual value.
- Existing journal verification and audio-active write restrictions remain. The command does not save a profile or reconnect USB before its reply can be read.
- After a confirmed change in Native mode, the app explicitly reconnects USB and verifies the selected Pico via the existing USB-port identity recovery. It invalidates old audio identity and does not resume audio automatically. In XInput mode it stores the policy without re-enumerating.

Legacy profile writes to `0x0d`, `0xc7`, `0xc8` are accepted but ignored. New app profile reads/writes/import/export and slot backup/restore exclude this key. New app with older firmware shows the common option unavailable; it does not silently fall back to changing a profile. Older firmware still interprets the legacy profile byte after a downgrade.

## Validation scope

The targeted app suite passed 91 tests, with two additional UI tests checked afterward (the USB policy module has 8 tests, including English help and failed-save display). Production journal/policy paths passed host tests for ON/OFF migration, explicit common OFF, old-profile immunity, preservation of unrelated settings/profile identity, write rejection and 160 simulated power-cut points. Existing USB/auth/initialization regression, ARM syntax checks and a real firmware build passed.

Formal verification was not rerun: this changes sequential journal policy/metadata rather than the existing audio ownership, sleep handover or profile-watch concurrency rules. Actual production journal code was exercised with bounded fault injection instead. Host tests are not a physical brownout or USB/audio compatibility test. No hardware flash, app-package release or GitHub publication was performed.
