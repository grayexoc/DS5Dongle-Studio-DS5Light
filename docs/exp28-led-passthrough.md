# exp.28: LED passthrough and restoration

- Updated 2026-11-11: distinguish an unseen host colour from explicit black/off. Do not send startup LIGHT_OUT or RGB in an untouched passthrough profile. Run Bluetooth setup when a colour/override requires ownership. Restore actual host RGB, including black; when no host colour exists, release a previous override to the controller instead of inventing black. Controller-managed appearance after release requires physical validation. No invented blue fallback.
- Capture release/setup commands only from original host reports, not synthesized cached ticks. Retry pending commands after queue failures, then stop replaying them after successful L2CAP submission.
- Keep game RGB while a fixed/off profile owns the lightbar. On returning to passthrough, submit the latest game colour, including black/off, until a matching restore report succeeds.
- Host release invalidates the cached player pattern, not RGB. Explicit LIGHT_OUT clears cached RGB before applying any RGB included in the same host report. Player patterns follow release/setup in a subsequent report.
- Restore host/default LED brightness when a user brightness override returns to passthrough. Battery notification output cannot acknowledge restoration of the game colour.
- Repeated identical host colours do not request additional idle reports. No periodic LED sender, profile schema change, app protocol change or audio processing change.

References reviewed: Sony's Linux `hid-playstation.c` (`dualsense_reset_leds`, USB/BT shared output fields), and SundayMoments/DS5_Bridge `controller_output_state.cpp` (release/player-cache handling).

Host checks cover setup/drop/reconnect, late queued commands, fixed/off transitions, black RGB, host changes under an override, one-shot commands, short reports, output-field isolation, brightness restoration and notification hand-back. The nine firmware regression scripts were run; see `build/exp28-run_*.log`.

Physical USB-vs-Bluetooth LED animation timing and controller acknowledgement are unverified. L2CAP success proves transport submission, not physical display. No device flashing performed.
