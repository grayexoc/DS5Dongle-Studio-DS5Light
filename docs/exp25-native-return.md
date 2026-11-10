# exp.25 native return after emulated-rumble stop

Evidence: after focus event 2321803092, user reports all CrimsonPulse haptics stop while wired works. exp.24 still receives PCM; later events remain queued. A one-shot native selector 01 restored tactile output without restarting the app/controller. The exact offending input report sequence has not been captured.

Change: in DualSense/Edge USB mode with automatic haptics OFF, once an explicitly selected emulated-rumble path has zero effective output on both motors, restore selector 01 and clear improved/rumble selection. This runs after rumble shaping, so configured release finishes before hand-back. It also covers the selector left by the existing DS 300 ms watchdog. Only a changed output marks a pending report; repeated zero STOP packets do not create a new periodic mode-rearm sender. Next nonzero explicit rumble still takes effect immediately. XInput hold/stop selection and Mix/Replace behavior are unchanged.

This uses emulated-rumble control output, not PCM amplitude or silence inference. Unflagged nonzero motor bytes still cannot authorize rumble (exp.17 preserved). exp.23 neutral-report handling and exp.24 exception fixes/save acknowledgment remain included.

Tests: all seven host regression scripts and ARM syntax checks passed. New production integration block tests cover classic/improved selectors, no release/20/40 ms release, final native restore, immediate new attack, XInput exclusion, repeated STOP pending suppression and watchdog-shaped zero-selector input. Full hardware focus-event sequence remains untested. Existing waveform tests do not prove RF delivery.

Known compatibility limit: a DualSense-mode app intentionally selecting zero-strength rumble while PCM plays will now allow PCM after the zero/release; that is the intended new policy. Continuous nonzero explicit rumble remains authoritative. No app-specific event ID special case, profile migration or DS5Light change.

After flashing: restart CrimsonPulse once, verify Native/auto OFF, enter/exit focus repeatedly then run/roll/attack without app restart. Also check ordinary rumble STOP/release, native special attacks, speaker audio and XInput long rumble. No flashing performed by this task.
