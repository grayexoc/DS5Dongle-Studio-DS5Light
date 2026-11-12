# Getting started with DS5Light

[한국어](SETUP_KO.md) · [Application guide](README.txt) · [Versions and release notes](RELEASE_NOTES.md)

## Package and firmware

For the local test build, use `DS5Light-win-x64-v1.0.9-Experimental.zip` with `ds5-studio-light_v38.uf2` on Pico 2 W. The instructions below also cover the published release.

Use the complete `DS5Light-win-x64-v1.0.6.zip` package on Windows 10/11 x64. Extract it into a writable folder, keep `_internal` beside `DS5Light.exe`, and run the executable. Python is not required for the packaged app.

The combined release is v1.0.6, the app is v1.0.6, and the firmware is Studio v34. Firmware is a separate release attachment: `ds5-studio-light_v34.uf2`. That attachment is for Raspberry Pi Pico 2 W; it is not for RP2040 Pico W or Waveshare boards. The app does not flash firmware automatically.

Back up current settings and slots before changing firmware or saving profiles. This fork's additional settings and diagnostics require corresponding firmware support. An existing compatible Studio installation may support basic audio forwarding without all of these additions. A flash_nuke reset is not part of the routine setup.

## Set up Studio inside the app

1. Connect the dongle and controller. Stop DS5Light audio processing and any other application sending audio to the dongle before saving settings.
2. Open **Studio settings** (`Studio설정`). The app reads the current configuration when entering the tab; use **Refresh** if the device or profile has changed. If multiple devices are listed, select the intended device.
3. Open **Recommended presets** and choose one of the three included presets. Their files are in `Studio Presert` next to the executable:

| File | App preset | Purpose |
| --- | --- | --- |
| `Audio_Haptic_01.json` | Stable audio haptics | Greater suppression of background responses; a starting point for audio haptics. |
| `Audio_Haptic_02.json` | Responsive audio haptics | Retains more response, including more background activity. |
| `DS_Native.json` | Native preset | Disables audio-derived haptics for native haptics and conventional game rumble; game and connection support are required. |

4. Select **Save slot**, then **Save and use**. Review an overwrite prompt before confirming. Keep your own slots intact by choosing an empty slot.
5. Wait for the save and activation result. If the result is unconfirmed or a reconnect is requested, refresh and check the active profile before continuing. Do not treat an uncertain save as successful.

Recommended presets change only the allowed **audio-haptics fields of the current configuration**. Current device, gyro, trigger and macro settings are retained. The resulting current configuration is saved to the chosen slot: overwriting a slot does not preserve that slot's previous non-audio settings. A full-profile import/restore or loading an existing dongle slot has a different scope and can change other settings.


## Start audio haptics

1. Keep the original game audio on your usual speakers/headphones.
2. In **Audio haptics**, select whole-device or selected-game capture. For a game, start it, refresh the process list and select its actual executable. Select the intended dongle output in the connection controls.
3. New preferences default to **PC suppression filter on**, **Balanced**, 55% suppression, 85% impact preservation, 100% gain and automatic channel selection. Existing saved preferences take precedence; check the controls before starting.
4. Start processing. Adjust suppression, impact preservation and gain separately. The filter does not fully separate music, dialogue and effects.
5. Store useful settings in one of the 12 PC game presets. PC presets and dongle profile slots are separate: saving or loading PC settings does not itself activate a dongle slot.

Automatic, stereo, 5.1 and 7.1 capture are supported. Center, LFE and rear/side contributions require multichannel input; stereo cannot recover channels already mixed together. Automatic capture is not proof of a game's internal audio format. Selected-game capture requires Windows build 20348 or later; earlier Windows 10 builds can use whole-device capture.

## Native haptics and troubleshooting

- Stop audio processing before using the Native preset or a suitable existing native profile. Turning off only the PC filter leaves audio forwarding active.
- The audio-haptics tab can load existing dongle slots. Loading a slot applies its entire saved configuration, including triggers and gyro.
- No haptics: check the controller connection, selected output, active Studio profile and its audio-haptics mode, then check capture activity and gain.
- Additional device settings/tests depend on firmware support. XInput is experimental and differs from DualSense mode.
- Timing shown in diagnostics is PC-side timing or a queue-based estimate, not a measurement of physical controller latency.

Settings and presets are described in [README.txt](README.txt). Original projects: [Studio](https://github.com/artzox/DS5Dongle-Studio) and [DS5Light](https://github.com/fnflwkd/DS5Light).
