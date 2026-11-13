# Profile change notifications (protocol v1)

Optional vendor HID top-level collection: Usage Page FF00, Usage 52.
Report ID 8F, INPUT and FEATURE payloads both 15 bytes (16 including report ID).
Existing gamepad, Feature 81/84, audio and saved profile formats are unchanged.

Offsets including report ID:
- 0: 8F
- 1..4: ASCII SLP1
- 5: protocol version 1
- 6..9: little-endian u32 sequence (wrap permitted)
- 10: current slot 0..31 or FF unknown
- 11: edited 0/1
- 12: audio haptics 0 Off, 1 Mix, 2 Replace
- 13: microphone button used by macro 0/1
- 14..15: zero, reserved

GET_FEATURE 8F validates support and starts/renews a 65-second RAM-only lease.
DS5Light renews every 30 seconds. No flash writes or profile edits.
During a lease the USB loop samples lightweight RAM status at most every 100ms,
without reading slot data/CRC from flash. State changes are coalesced and sent
once when the existing HID IN endpoint is ready; failed sends remain pending.
The event never replaces a whole controller/audio output packet.
The vendor collection separates notifications from the Windows gamepad input
queue, so DS5Light does not consume ordinary gamepad reports.

DS5Light pins the collection to the selected serial, or exact collection-normalized
HID interface path when serial is absent or the selected Edge has hidden its serial.
Ambiguous matches are not opened.
It verifies framing/version/length/ranges and confirms current profile through
the existing locked feature-query path after a notification. Duplicates are ignored.
DS5Light handles notifications on a 200 ms UI callback. An occupied command
channel is retried without losing the forced mode check. The 0x67 response on
report 0x81 may include ASCII SLP2 at offsets 23..26 (including the report ID)
followed by audio-haptics mode, native Mix level and DSP input source at 27..29.
The event sequence also advances on a profile save or either Mix field change, retaining the
v1 event layout and reserved bytes. A valid SLP2 snapshot and confirmed event
input allow 30-second safety reads. Each lease renewal must yield an input
report within three seconds, including an unchanged sequence as acknowledgement.
Legacy or failed notifications retain the three-second header and ten-second
mode checks. These paths do not enumerate the slot list.
A notification cannot activate a slot, write settings or restart a manually stopped engine.
Studio drafts remain intact; visible clean settings can be re-read, dirty drafts are marked stale.

No firmware image build, flash, or physical USB enumeration test is implied by host tests.
Required hardware checks: DualSense/Edge/XInput enumeration, profile changes by
macro/OLED/app while running and stopped, Off stopping transmission, manual stop
preservation, reconnect and multiple Pico identity, browser concurrent use, and audio continuity.
