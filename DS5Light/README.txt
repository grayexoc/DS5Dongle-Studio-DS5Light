DS5Light v1.2.2 — Studio
Combined release v1.2.2 / DS5Light v1.2.2 / Studio firmware v53 (Pico 2 W).
SETUP.md · RELEASE_NOTES.md

Run
Extract the entire ZIP and launch DS5Light.exe. Keep the _internal directory beside it.
Use a DS5Dongle Studio dongle connected to a DualSense. This application does not install firmware automatically.

Audio haptics
Without saved preferences, the first-run defaults are whole-device capture, PC filter on, and sorting by audio output activity.
The application processes a copy of whole-device or selected-game audio and sends it to the dongle. It does not alter the original game sound played by your speakers/headphones.
For process capture, run the game, refresh the process list, and select its actual executable.
The list refreshes on request and once when selected-process capture becomes active in an audio-haptics profile. Sort by recent start, CPU usage, or audio output activity. Whole-device automatic capture does not depend on this list.
Channels can be automatic, stereo, 5.1 or 7.1. Automatic follows the capture format; it does not inspect game audio content.
The PC filter helps reduce sustained background responses while preserving impacts. It does not fully separate music or dialogue.
Channel mixing still applies with the filter off. Stored app gain ranges from 0.5x to 3x, with 1x (100%) as the starting point and output-mode limits. Shared output applies gain only when Studio confirms controller-speaker auto-mute; otherwise it remains at 1x. Exclusive Rear applies gain only to rear haptic PCM.
The bridge stops automatically when the selected process exits.

Settings and profiles
Last options and window size are saved in preferences.json beside the executable; this directory must be writable.
preferences.json is created after running the app. Older AppData preferences are not imported automatically.
Game presets use LocalAppData/DS5Light/presets.json. UI language uses LocalAppData/DS5Light/ui.json.
The Studio slot list reads profiles stored on the dongle. Loading a slot may also change triggers, gyro and other settings in that profile.
Without a saved profile selected, the Load button queries the available profiles again.
In Studio settings → Profile slots → Recommended presets, review Mix or Replace, choose a save slot, then Save and use. Stop dongle audio and back up the destination slot first. Existing slots are not upgraded automatically.
Studio Presert contains DS_Native.json, Audio_Haptic_01.json and Audio_Haptic_02.json.
Only audio-haptics fields in the current configuration change; current triggers, gyro and macros remain. The resulting current configuration replaces the chosen slot, including its other settings.
Use these presets as the comparison reference, with the app filter on, background reduction / impact preservation of 40% / 90% for Mix or 50% / 95% for Replace and app strength 1x (100%). Both use Front input; Mix also combines raw rear native haptics. Perceived response depends on Windows and game/application volume; other settings assume defaults unless specified.

Microphone button keyboard mapping
Enable the feature under Devices & launch and select Set keys. The default is disabled / F8.
One common binding is used without automatic per-game selection. It can operate while the audio engine is stopped, as long as DS5Light remains open.
One button press produces one key tap; holding Mute does not repeat it. Input is skipped in DS5Light's own windows and while related keyboard keys are already held.
Elevated targets, games blocking synthetic input, or exclusive/hidden HID devices may prevent operation. The original Mute action is not suppressed.

Diagnostics
Devices & launch shows processing status and PC-side timing. This excludes USB/Bluetooth transport and physical controller playback latency.
Process capture requires Windows build 20348 or later. Use whole-device capture on older Windows 10 builds.
Game compatibility, haptic behavior and hardware latency depend on the actual setup.

Distribution
Retain LICENSE.txt, LICENSE_EN.txt, DISTRIBUTION_POLICY_KO.md, SOURCES.md and the THIRD_PARTY notices.
Third-party components keep their original licenses. Separate Microsoft runtime terms are in THIRD_PARTY/upstream/Python-3.12.10-CRT-LICENSE.txt.
