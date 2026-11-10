# Sources and rights

- **Device diagnostics and short output tests:** UI/workflow ideas reviewed from [DS5 Web debugging console](https://luoshengjin.netlify.app/) and its public JavaScript. Reuse permission was confirmed by the project owner/user on 2026-11-09. Implementation uses this project's Studio protocol and Windows audio binding; no site JavaScript is bundled or executed. Stick calibration is excluded.

- **Studio bridge:** [artzox/DS5Dongle-Studio](https://github.com/artzox/DS5Dongle-Studio), commit `8613a5388baa77f8d9e389b20069d6918e3067a1`. Functions from `vendor/ds5audio_original.py` are loaded via AST. The original MIT notice is preserved in `vendor/LICENSE-Studio.txt`.
- **DSP:** Independently implemented adaptive band-level background estimation, change detection and gain smoothing. Background-estimation concepts were informed by [noisereduce](https://github.com/timsainb/noisereduce); its implementation is not copied into the runtime.
- **Process capture:** C# implementation using Microsoft's application-loopback API; [official documentation/sample](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/).
- **PyAudioWPatch 0.2.12.8:** Exact source and wheel provenance is recorded in `licenses/PyAudioWPatch-0.2.12.8/PROVENANCE.json`; Apache text and original PyAudio/PortAudio notices are retained.
- **Dependencies:** See `requirements*.txt` and the built release's `THIRD_PARTY/manifest.json`. Third-party components retain their own terms.
- Separate StudioProxy evaluation code, research source archives, videos, conversations and unrelated device backups are excluded from this repository.
- **Localization (0.9.0):** UI-only English strings and an independent language preference. Audio DSP, channel mixing, capture and preset schema are unchanged from 0.8.7. English license translation does not replace the controlling Korean original.


## Modified build: Studio slot client

`studio_slots.py` ports the slot metadata/current-profile/activation protocol from the user-provided `DS5Light-OG/studio_slots.py`. The device protocol and source notices are covered by `vendor/LICENSE-Studio.txt` (also distributed in THIRD_PARTY). The compact slot row reads and explicitly activates saved slots. The native Studio settings tab described below adds explicit settings, effects, macro and slot writes. hidapi 0.15.0 is bundled with its actual package license files.

## Modified build: SVG wordmark

The user-provided `assets/ds5-light-logo.svg` is rendered directly at the header icon height. The Windows x64 TkSVG 0.16 runtime is from the [upstream release](https://github.com/tcltk-depot/tksvg/releases/tag/0.16). Its download URL and SHA-256 are recorded in `vendor/tksvg0.16/SOURCE.json`; the archive digest matches the upstream release asset digest. TkSVG and NanoSVG notices are retained in that directory and the release's `THIRD_PARTY/tksvg-0.16/`. No Python TkSVG wrapper or raster wordmark file is bundled.

The wordmark's CSS class declarations are expanded into SVG presentation attributes to preserve its white and gold strokes in TkSVG. Path geometry is unchanged; the viewBox is trimmed to visible artwork so the drawing matches the adjacent icon height. Content credentials for the unmodified input are omitted from the modified artwork. The original input and rendering diagnosis are retained in the local `reports/` directory.

## Integrated native Studio settings editor

The original field definitions in studio_fields.py are data extracted from the local user-provided DS5Dongle-Studio-master/ds5-config-portal.html (v1.42.0). Firmware command references are src/cmd.cpp, src/config.h, src/macro.h and src/input_buttons.h. Original Studio notices remain in vendor/LICENSE-Studio.txt. The native Tkinter editor, staged document, validation and worker integration are implemented in studio_settings_ui.py, studio_document.py, studio_settings_protocol.py, studio_records.py and studio_backup.py. The app also supports firmware-specific settings and Pico mapping extensions; see SETUP.md and MAPPING_GUIDE_KO.md for the current workflow and limits.
