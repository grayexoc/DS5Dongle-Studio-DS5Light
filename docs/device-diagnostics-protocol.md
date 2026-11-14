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
