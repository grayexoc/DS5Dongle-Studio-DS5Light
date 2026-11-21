# Opt-in device diagnostics and short output tests

First built as exp.26 after the review fixes. No web configuration changes.
The DS5Light implementation is in `C:/Users/graye/Documents/Codex/DS5Light/device_diagnostics*.py`.

All requests are 64-byte HID feature reports: `80 66 command selector tag[4] zero-padding`.
Read report `84`, 64 bytes including the report ID. Its 63-byte body is:
`66 command status version selector tag[4] data...`.
Version is 1; status 0 = success, 1 = malformed/unsupported selector or rejected test.
Clients must match command, version, selector and all four random tag bytes. Never resend START.
Command IDs and configuration field IDs are separate namespaces.

## 0x1E: read-only snapshot

No flash writes, profile changes, counter resets, device wake extension or periodic sender.
Page 0, body offsets:

| Offset | Value |
| --- | --- |
| 9 | bits: connected, ready, audio processing, haptic stream, valid RSSI |
| 10 | active USB mode: 0 DualSense, 1 XInput |
| 11 | auto-haptics mode |
| 12 | most recently observed PCM channel count |
| 13, 15 | LE16 latest front/rear PCM block absolute peaks; can remain stale after stop |
| 17 | signed RSSI, meaningful only with validity bit |
| 18 | bit 0 last host valid, bit 1 last L2CAP-accepted state valid |
| 19, 27, 35 | eight bytes each: last original host request, current normalized state, last accepted state |
| 43 | LE32 monotonic uptime milliseconds |
| 47 | Optional USB audio fields version, 1 when present, 0 on older firmware |
| 48, 50 | LE16 raw rear-left and rear-right PCM peaks of the latest USB block, 0–32768 |
| 52 | LE32 cumulative USB audio read blocks with at least one complete frame, since boot |
| 56 | Rumble comparison capability, 1 for extended test selectors |
| 59 | Optional haptic packet diagnostic version, 1 when present |
| 60–61 | Absolute left/right quantized peaks (0–128) from the latest packet submitted to the Bluetooth send function |
| 62 | Bit 0 indicates a packet has been submitted since the last audio stream reset. Bit 1 advertises tagged page 3 |

The USB block count excludes internally generated profile chimes. Compare its
delta with page 1 over the same sampling interval. A USB block and a Bluetooth
audio packet have different durations.

The eight control bytes use SetStateData offsets `0,1,2,3,9,36,38,39`:
flags0, flags1, right/left rumble, mute/power, motor reduction, flags2, haptic filter.
Short host reports zero-fill absent bytes; they are the original request, not inherited authority.
Current normalized state precedes final profile/test composition. Last accepted state includes it.
State validity is cleared on reconnect. These values do not establish controller receipt or motor motion.

Page 1: nine LE32 values at offset 9: audio packets accepted by L2CAP, overflow,
mixed-audio age expiry, retry budget expiry, retry exhaustion, other send errors,
maximum attempted packet age in ms, native recovery count, actual audio retry attempts.
LE16 pending+queued packet depth at offset 45. Counters are cumulative since boot,
wrap modulo 2^32, and are never reset by this command. Pages are not one atomic instant.

### Page 3 — USB playback observation

Body offset 9 is extension version 1. Offset 10 has bit 0 for observed alternate setting and bit 1 for active playback. From offset 11 are five little-endian uint32 values: observation generation, accepted nonzero playback alternate-setting events, accepted alt-0 events, USB session invalidations, and current configuration revision. Counts wrap modulo 2^32. A repeated accepted SET_INTERFACE event counts because the USB implementation can recreate the endpoint. A reset or unmount callback invalidates the observation, and only SET_INTERFACE makes it known again. Offset 31 is zero on earlier builds, 1 when local discard completion is unconfirmed, and 2 when the core-0 reset has completed for the current known inactive generation. Completion covers the dongle USB FIFO, partial haptic frames and resampler, queued Bluetooth audio and pending local retry, and invalidation of old speaker encode results. A new SET_INTERFACE or invalidation clears completion. Reports already accepted by L2CAP and controller-side buffers are outside this observation.

## 0x1F: explicit output test

Selector 0 stops the current test (safe no-op when no test exists).
1/2/3 = left/right/both classic rumble at 64/255, 4/5 = L2/R2 light resistance,
6 = native PCM selection for a separately generated audio test.
7–9 = left/right/both classic rumble at 128/255, 10–12 = improved rumble at 64/255,
and 13–15 = improved rumble at 128/255.
START requires BT ready, no active PCM processing, auto-haptics OFF and idle power state.
No profile setting is changed or saved. Existing rumble and cached game trigger effects are cleared
at test start, including the game-ownership recency latch. Profile trigger settings are preserved;
new game commands still cancel the test and take control normally.

The firmware overrides only motor mode, motor strength and trigger effect fields while testing.
LED, volume, mute and power fields retain the profile/host state. The light trigger effect is
`21 FC 03 80 24 49 12 00 00 00 00` (zones 2..9, force 2/7).
The 2-second lease expires using unsigned monotonic subtraction, including timer wrap.
Expiration or STOP requests zero rumble, native mode and both trigger OFF effects, retried until
a matching state is accepted by L2CAP. Successful cleanup returns composition to the active profile.
Any new host state request, profile/reset or suspend cancels a test. Disconnect/reconnect clears it.
There is no new periodic BT transmission during normal use; tests reuse existing state scheduling.
As with any wireless STOP, device-local expiry cannot guarantee physical release during radio failure.

## DS5Light behavior

Settings/diagnostics -> Device diagnostics & tests. Nothing starts when opening the dialog.
Explicit status collection and five-second native-HID read timing can run during audio;
output tests require DS5Light audio stopped. A shared Studio lock serializes transactions.
XInput configuration HID input timing is unavailable; it is not reported as zero polling rate.
Statistics describe PC HID reads, not RF loss or end-to-end latency.

Audio probes enumerate and open paused within one PortAudio instance, using the selected,
identity-bound four-channel WASAPI endpoint at 48 kHz,
12% peak and 10 ms start/end ramps over 1.5 seconds: 80 Hz on channel 3 or 4 for grips, 440 Hz on channels 1/2
for the speaker. Native test selection starts after stream preparation, just before playback.
A monotonic two-second deadline rejects late stream start/write. No default-device fallback,
gain increase or profile mutation occurs.
Profile mute/volume/power choices can still prevent a physical response.
Cancellation/close waits for worker cleanup and attempts STOP even if START acknowledgement was lost.
PortAudio termination is attempted even when stream stop/close fails. Diagnostic mode decoding
recognizes the improved-rumble flag independently of the classic rumble flag.
The firmware lease also covers host crashes; audio-driver calls themselves may block independently.
An unsupported firmware remains usable; JSON includes a diagnostic error rather than fabricated data.
JSON includes device identifiers/paths. Review them before sharing the file.

Ideas reviewed from https://luoshengjin.netlify.app/; the user confirmed reuse permission.
No website JavaScript is executed or shipped. Stick inspection and factory calibration are excluded.

### Tagged rear-control command 0x24

The playback diagnostic advertises command version at byte 36. Byte offsets 32–35 contain the current little-endian Bluetooth link epoch. The HID request body after the command byte contains version 1, operation 1 (arm), 2 (commit), or 3 (renew), a four-byte request tag, then five little-endian uint32 values in order (attempt, revision, link epoch, USB generation, renewal sequence). Arm uses attempt and sequence zero. Commit uses sequence zero and the opened generation. Renew echoes the active generation and the next sequence. The fixed-length HID feature report pads the request. The reply body is 0x66, 0x24, status, echoed version, operation and tag, followed by the granted attempt ID in bytes 9–12. Status 0 grants only the operation acknowledged by the matching tag. Arm alone never authorizes control samples.

### Conditional route command 0x25

Playback diagnostic byte 37 advertises version 1. The request body after the command contains version 1, operation 1 (apply) or 2 (roll back), a four-byte request tag, the expected config revision and checksum as two little-endian uint32 values, and the observed and target routes. Each route contains three bytes in order: Auto Haptics mode, DSP source, Replace auto-mute.

The firmware checks the token and observed values before changing the live configuration. Bluetooth must be ready and USB playback, DSP processing, and haptic streaming must be idle. XInput mode is refused. Apply permits Replace with Rear and auto-mute enabled, unless Native Mix is active. Active Native Mix may move its DSP source from Rear to Front while retaining its mode and auto-mute. Rollback restores only the route saved by the most recent successful apply, with its exact resulting token, and consumes that saved route. Restart clears the rollback record. The command does not save a slot or write flash.

Feature report 0x84 returns body bytes 0x66, 0x25, status, echoed version, operation and tag, followed at offsets 9–16 by the resulting token on success. Status 0 acknowledges the change and status 1 refuses it. The host verifies readback between two matching profile tokens. An ambiguous reply or readback requires refreshing the current profile before any further write. The host does not automatically resend or restore an ambiguous write.

### Conditional intensity command 0x26

Playback diagnostic byte 38 advertises version 1. The request body after the command contains version 1, operation 1 (decrease) or 2 (restore), a four-byte tag, the expected little-endian revision and checksum, and one byte each for observed and requested intensity. The operation requires an idle, locally drained Replace/Rear/auto-mute route and no pending or active rear-control authorization. It changes only the live Auto Haptics intensity. Restore requires the prior value recorded by firmware and the exact token returned by the decrease.

The reply uses report 0x84 and the same layout and status as 0x25, with command byte 0x26. The PC verifies intensity and route before sending the command, then reads both back under the acknowledged token. Slot save, playback and automatic retry are outside this command.
