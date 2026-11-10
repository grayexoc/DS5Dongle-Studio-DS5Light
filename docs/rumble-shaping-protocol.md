# Native rumble gain and release (pending build)

No web portal or DS5Light source changes. Included from studio-oled-v1.4.10.

## Fields for DS5Light

Use existing config field read/write and profile-save protocols.

| ID | Wire type | Value | Default |
| --- | --- | --- | --- |
| 0xC3 | u8 | Native rumble gain, 100..200 percent | 100 |
| 0xC4 | u8 | 0 off, 1 short (20ms), 2 medium (40ms) | 0 |

An application slider labelled `일반 진동 강화` may show **0..100% added gain**;
write `100 + slider` to 0xC3. Thus slider 0 means unchanged, not mute. If instead
showing absolute strength, display 100..200%. Above full-scale input, gain clips
at the controller report limit (255); 200% is not twice the motor's physical maximum.

Probe both fields first; unsupported fields must disable these controls without
writing to an older firmware. Preserve the last-read baseline and use existing
apply/save-to-slot flows. Both fields belong to each profile and backups.
No USB reconnect or new interface is required. Updating these controls while
Auto-Haptics is Mix/Replace stores them but does not shape that signal.

## Behavior and isolation

- Only the controller-emulated native rumble state with Auto-Haptics OFF is shaped.
- Gain is applied independently to the left/right motor intensities, with saturation.
- Input increases replace a remaining release immediately; tails never accumulate.
- Falls interpolate linearly toward the new target for 20/40ms. Identical target
  reports do not restart the envelope. This includes falls between nonzero levels.
- Native PCM haptics, Mix/Replace, raw rumble feeding rumble-to-trigger and trigger
  effect bytes are unchanged. An explicit switch to native-haptics mode cancels release.
- During release only, the existing state scheduler uses a 5ms cadence, including
  the final target/zero. Host output continues to be processed immediately. Idle
  synthesis retains its existing 300ms stale-host watchdog before any release.
- Shaped changes and the final stop remain pending until matching L2CAP submission
  succeeds. Queue admission, expiry, failure or an older colour/state packet do
  not acknowledge a newer rumble value. This is not a controller-level acknowledgement.
- Connection reset/disconnect, suspend and profile activation clear shaping and
  cached rumble. Settings changes clear the envelope on its next processing pass.
- Existing profiles normalize missing 0xFF fields to 100/off. Config version 21,
  body 301 bytes, previous fields unchanged. Previous profile fingerprints for
  raw 295/299-byte records are accepted only if the respective extension is absent.

Successful compilation of host tests and ARM syntax checks is not device validation.
Check stop envelopes, rapid repeated impacts, native haptics coexistence, profile
switches and sleep on hardware after an explicitly requested build/flash.

## DS5Light project handoff prompt

Pico Studio firmware now provides native-rumble shaping fields: 0xC3 u8 gain
100..200 (default 100), 0xC4 u8 release 0=off, 1=20ms, 2=40ms (default off).
Add `일반 진동 강화` slider 0..100% (wire value 100+slider) and `잔향` selector
끔/짧게/보통 to General Haptics. Probe support before enabling, read back after
apply, and include the fields in existing profile/backup workflows. Explain that
they apply only when Auto-Haptics is OFF; do not force a mode change. When firmware
does not support the fields, disable controls without speculative writes. Do not
modify the web portal, audio processing, USB descriptors or reconnect behavior.
