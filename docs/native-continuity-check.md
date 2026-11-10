# Native texture follow-up

User comparison: exp.18, audio haptics OFF; footsteps/running feel weaker in bass/rough texture than wired. Bridge v2.0.1 feels similar to wired. Missing special-attack effects were previously resolved separately.

Source changes after exp.18:
- Remove invented blue RGB on fixed-lightbar release. Restore cached host RGB verbatim, including black/off. Untouched mode still leaves incoming lightbar requests unchanged.
- New/invalid settings default to haptics_gain=1.2 and haptics_aa=1 (off). Existing valid saved values remain unchanged. AA is already bypassed in audio-haptics OFF mode, so this default is not evidence of a native filtering fix. Gain above unity can clip peaks.

Continuity regression uses the production bt_write and interrupt send-ready logic with a mocked transport. 200 successive native packets at 11 ms spacing arrive in order without loss. A transient ACL-full failure recovers in order. A packet delayed 48 ms is discarded by the existing expiry policy. Queue overflow eviction is covered by the existing queue tests.

This proves the tested host-side behavior only. It does not measure the Pico's real send gaps, RF retransmissions, controller buffering or actual footsteps. The earlier q1 capture observes PC-to-Pico USB, not Bluetooth delivery. Confirming the game symptom requires runtime send/drop/gap observations or a Bluetooth trace; do not remove expiry, increase gain further or redesign scheduling based only on this synthetic result.

No new UF2 built for these changes. exp.18 remains the previous artifact.
