# Current improvement and validation list

Updated 2026-11-14. This is the active list; it supersedes earlier conversational lists. Explicitly deferred or withdrawn feature requests are not active items.

| Item | Evidence and decision |
| --- | --- |
| Build current source | Studio v44 for Pico 2 W was built and its UF2 verified on 2026-11-13; see ../DS5Dongle-Studio-build/local-v44-studio/verification.json from the source root. The current comment-only correction needs no new binary. Build later runtime changes only when requested. |
| Hardware regression | Required: repeated rumble start/stop, native special attack, microphone gain/mute. Host tests cannot establish tactile/audio results. |
| Cached motor ownership | Worth targeted sequence tests. Upstream v0.8.0 forward_output_report copies the current host body; Studio preserves prior motor fields for reports without motor authority. Do not replace this with another inference without proving STOP/native/LED-only cases. |
| 60 ms stream inactivity | Keep for now. Link/interface-close resets are explicit; a timeout is a fallback. No inspected reference establishes 60 ms as optimal. Separate partial-buffer cleanup from mode hand-back if a supply-gap test proves a defect. |
| DualSense 300 ms rumble watchdog | Keep pending a reproduced held-command case. XInput remains exempt. Upstream forwarding alone does not prove indefinite hold is safe for Studio synthesis. |
| Audio expiry/retry | Native has no blanket 48 ms age expiry: it uses a 20 ms failed-send retry budget (six total attempts) and 120 ms without progress triggers recovery at send-ready. Mix/Replace retains 48 ms expiry and 10 ms / three attempts. These are provisional policies, not measured latency bounds; see native-latency-followup.md. |
| Trigger synthesis 3 s game ownership | Test only with synthesis enabled. Explicit game trigger OFF versus a quiet active effect is the critical distinction; no inspected reference validates this timeout. |
| Earlier DSP/transport changes | Reassess individually, not blanket rollback. Upstream uses double-frame packing and 48 kHz to 3 kHz resampling; exp.17 success identifies mode inference but does not establish necessity of every prior change. |
| Game compatibility | Native special attack fixed by user test. Games relying on unflagged-rumble inference remain untested; never restore the global inference merely because another game might need it. |
| Long-session reliability | Still required: congestion, reconnect, power-cut recovery and feature-specific validation. Host fault-injection results are not physical power-cut results. |

References inspected:
- https://github.com/awalol/DS5Dongle/releases/tag/v0.8.0
- https://github.com/SundayMoments/DS5_Bridge/releases/tag/v2.0.1
- Local DS5Dongle-0.8.0/src/main.cpp: forward_output_report.
- Local DS5-Haptic-Compare/bridge-v2.0.1-bt.cpp: AUDIO_SEND_QUEUE_MAX_DEPTH, AUDIO_STREAM_QUEUE_LATE_US, output counters and overflow handling.

These are evidence-based priorities, not confirmation of additional hardware defects. No firmware behavior or build changed in this assessment.
