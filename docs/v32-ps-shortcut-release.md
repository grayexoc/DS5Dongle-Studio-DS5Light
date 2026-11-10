# Studio v32 — PS shortcut release

Pico 2 W / SDK 2.2.0 / Release / experimental runtime Native-XInput switching.
Companion app remains DS5Light v1.0.1; no new command or UI option is required.

- PS shortcut reset keeps a pending key-up until the keyboard report is accepted.
- A main-loop task services key-up even without another BT report, with the
  shortcut disabled or with PS reassigned as the Shift key.
- Rejected submissions keep their retry state; failed key-down does not acquire
  ownership. No pending key means no periodic USB report is generated.
- The existing 30 ms pulse deadline handles uint32 millisecond wrap.
- Wake owns the keyboard during its F15 sequence. PS shortcut does not start
  during wake, suspend, or macro playback/held/pending keyboard state. Macros
  defer keyboard submissions while a PS shortcut is waiting for key-up.
- Includes the source fixes after v31: command 0x20 dispatch, macro key-up
  retry across resets, stable profile-key release, virtual L2/R2 reset.
- Haptic processing, native watchdog, Bluetooth timing and settings layouts
  are unchanged by this fix. Existing v31 UF2 is preserved.

Tests: the real PS engine with mocked USB acceptance/time/ownership; macro
engine playback and hold arbitration; the existing 10 firmware regression
runners. Validation logs are in build/v32-validation and build/ps-shortcut-tests.
Host tests cannot confirm real Windows keyboard state or controller behavior.
All 11 runners passed. The clean ARM Release build linked successfully;
picotool confirmed version 32, SDK 2.2.0, Pico 2 W and RP2350 ARM Secure image
metadata. UF2 block-format checks passed. Artifact/source SHA256 and test
results are recorded in build/v32-validation/validation.json.

Build directory: build/xinput-v32. Artifact: ds5-studio-light_v32.uf2.
The new directory uses the existing working xPack compiler, host pioasm and
picotool. Python3_EXECUTABLE is explicit to avoid the Windows Store alias;
OPUS_FORTIFY_SOURCE=OFF matches the previous build's cached setting.
No device is flashed by the build.

Full-build warnings remain in unchanged Opus float conversion and SILK decoder
sources, and volatile counter/delay expressions. They are recorded in build.log;
this change does not silence or modify those third-party warnings.
