# v1.2.1 / Studio v52 release validation

Date: 2026-11-23 (Asia/Seoul). Branch: `custom/studio-ds5light`.
Baseline: `09f90e8524b8cf6fc8611a83ec9e27ea3e2f6116` (v1.2.0 / Studio v51).

## Changes and documentation

The release includes the current local Front follow-up impact, Rear bass/continuity, shared-output gain, Native Mix filtering/AA, startup/reconnection, UI and experiment-retirement changes. It does not restore the withdrawn low-volume Mix/Front automatic-compensation experiment.

English and Korean release notes and README consolidate the v1.1.0, v1.1.1 and v1.2.0 preset instructions: review the supplied Mix/Replace presets in Studio profile-slot settings; start with the PC filter on, background reduction 55%, and app strength 1x (100%); stop audio and back up the destination before Save and use. Existing slots are not upgraded automatically. Saving overwrites the destination with the current configuration plus the preset's audio-haptics values. Perceived results depend on Windows and game/application volume. Shared output requires confirmed controller-speaker auto-mute for app gain above unity.

README, setup guides, source TXT guides, preset instructions and release-versioning documentation now use v1.2.1 / Studio v52 and the actual Mix/Replace preset names. Historical release notes are retained.

## Executed software checks

- Application full discovery: **886 tests**, 377.151 seconds. This run had **878 passes, one failure and seven language-specific skips**. The failure was an obsolete assertion for the word `단자` in a deliberately shortened help message. The other stale UI assertions had already been corrected before this run.
- After updating that assertion to the current speaker/headset description, reran all four affected modules (`test_recent_palette_speaker`, `test_recent_ui_changes`, `test_speaker_ui_revision`, `test_release_metadata`): **19 tests passed**, 12.473 seconds. A third full-discovery run was not performed after this test-only change.
- Isolated bilingual UI runner: **69 Korean and 15 English tests passed**. The English run covers checks intentionally skipped in Korean discovery.
- Firmware host regressions: `run_haptic_math_test.py`, `run_profile_events_test.py`, `run_device_diagnostics_test.py`, and `run_audit_fixes_test.py` passed. ARM syntax checks passed for the production translation units selected by the math/profile-event runners.
- Updated the host-test fixtures for the current packet builder and DSP reset path. Packet tests execute production layout generation across Native/Mix/Replace, speaker/headset and buffered/silent combinations. Reset tests cover stream reset, mode/input transitions and preservation in an unchanged mode. Removed expectations for the retired speaker-accent coefficient path; generated-haptics cache assertions remain.
- Host runners accept `DS5_FIRMWARE_TOOLS`; `DS5_FIRMWARE_BUILD` selects compile settings belonging to this checkout. No absolute machine path is committed in those runners.
- Formal model checking was not rerun for this release-preparation task: edits made during preparation were version/documentation and regression-fixture updates. Existing unit and host regressions were used. This is not a new proof of the whole application or firmware.

## Build and package checks

- App built with CPython **3.12.16**, PyInstaller **6.22.3**, pinned build dependencies and a successful dependency consistency check. The build runtime reports OpenSSL **3.5.9** and Tcl/Tk **8.6.15**.
- `DS5Light-win-x64-v1.2.1.zip`: ZIP CRC passed; **82 embedded local Python modules** match the current source, **143 inventoried native binaries** match their SHA-256 inventory, and the packaged guide, native render helpers and three editable Studio JSON presets match source.
- Packaged executable smoke checks passed separately in Korean and English with isolated preference/preset/UI files. No widgets were reported outside the window. Audio was not started, and startup HID polling was disabled. These checks do not establish physical device behavior or complete visual acceptance.
- Firmware built in Release mode for **Pico 2 W / RP2350** with the existing configured toolchain and SDK. `picotool info -a` confirms version **52**, `pico2_w`, RP2350 ARM Secure, SDK **2.2.0**. No device was flashed.
- Final UF2 remains SHA-256 `20662cdc6eca27e58a6b872504ea90ec166d22590e1c96142a2df956c51f9fd7`.
- App ZIP SHA-256: `812978ffc5cbc9ff3bfdbdf291b07831bfa6729f8643ba71ddaff6a948083da9`.

## Evidence and limits

Local logs and receipts: `C:/Users/graye/Documents/Codex/2026-11-10/https-github-com-artzox-ds5dongle-studio/outputs/release-v1.2.1/`.

Power-cut, queue, reconnect, packet and command cases above are host simulations or extracted-production-path tests, not physical power cuts or device trials. Physical DualSense/Edge routing, tactile quality, controller-speaker output, game behavior, extended hardware operation and a fresh Windows installation were not tested in this release task. Software pass results do not resolve those hardware acceptance items.
