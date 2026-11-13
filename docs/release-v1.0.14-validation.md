# v1.0.14 validation scope

- Pair: DS5Light v1.0.14 / Studio v44 / Pico 2 W, XInput enabled in the firmware build; default profile remains Native.
- Current app checks: 112 targeted tests passed (release metadata, UI state, volume, failure recovery, battery, glyphs, channel mixing, gain, runtime optimization, speaker UI and dependencies). Python source syntax checks passed.
- Rebuilt the Windows app from the published source snapshot. Isolated packaged UI smoke passed with no audio started or hardware output test. ZIP CRC and packaged current setup/release documents were checked.
- Reused the existing Studio v44 Release UF2 after matching all 58 entries in its source SHA-256 manifest to the current local source. Its previous build record reports 14 host tests passed and no hardware flash. UF2 block magic/alignment and recorded SHA-256 were checked again for this release.
- Cleanup removed four unreferenced legacy PNGs from the fork and the unused process-refresh timer assignment. Source, cache and private preferences are excluded from the app ZIP as appropriate; upstream attribution and the archived upstream README remain.
- No new formal-verification run: this release preparation changes documentation, unused state and assets only. The existing ProfileWatchReplies model identifies the current profile-watch source hash; publication of the model is not a claim that formal checks were rerun here.
- Not checked here: physical haptic feel, actual speaker/headset volume behavior, OLED hardware, firmware flashing and Native/XInput round trips. Host tests and packaged startup do not establish these behaviors.
