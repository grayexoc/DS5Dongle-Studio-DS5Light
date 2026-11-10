# exp.22 native host-flags trial

Evidence: user reports exp.12 works, exp.13/17/20 fail for CrimsonPulse; exp.21 failed both CrimsonPulse and independent RAW waveform tactile tests, despite four-channel PCM reaching Pico. This trial isolates the exp.13 motor-intent inheritance candidate. Exact exp.12/13 source correspondence is not established.

STUDIO_TEST_NATIVE_HOST_FLAGS defaults OFF. In this trial ON, state_update does not inherit old motor fields from the host cache for reports without detected motor authority, only when USB mode is DualSense/Edge and auto_haptics_enable=0. Incoming selector bits/values are applied directly. XInput and automatic Mix/Replace preserve existing inheritance. Send-time motor refresh, native state-section removal, transport, DSP and exp.17 fix remain unchanged.

This is a diagnostic rollback of one behavior relative to exp.21, not a faithful exp.12 rebuild. Risk: ordinary DualSense rumble can be interrupted by subsequent LED/volume-only reports in the trial path. Normal builds remain unaffected. Do not reset profiles or change gain for the comparison.

Tests: production host-path test passes with switch OFF and ON, including native empty-report behavior, XInput preservation and Mix inheritance. Other six regression scripts pass. Full separate-directory Release build succeeded. UF2 headers and embedded version checked. Existing warnings remain. No flashing or physical validation performed.

After applying, reconnect controller, verify DualSense USB mode and automatic haptics OFF. Restart CrimsonPulse so it binds the re-enumerated endpoint; test the same roll/run/attack as exp.12. Improvement supports inheritance investigation; no improvement does not rule out interactions with later firmware changes. Next isolated variable is queued motor refresh, not wholesale firmware rollback.

SHA256: b96889b0a26efbca5f31758e54dc912a990678f589865998532a17c1a483d08e

## Hardware feedback
2026-11-09: user confirms exp.22 works. Combined boundary: exp.12 works; exp.13/17/20/21 fail; exp.22 works. The tested change disables cached motor-intent inheritance in DualSense native mode. This strongly implicates that path in this reproduced failure; it does not prove an exact erroneous selector without a HID/BT trace. Earlier independent one-shot native selection did not restore output on exp.21, so do not claim one initialization command alone explains the complete sequence.

Next production work should preserve legitimate LED/volume-only motor inheritance while accepting the native-start/control pattern that currently reuses stale motor intent. Retain explicit XInput/Mix/Replace behavior and the exp.17 fix. The exp.22 trial can regress held ordinary rumble after unrelated reports; not yet a general compatibility approval. No follow-up source change/build performed when recording this result.
