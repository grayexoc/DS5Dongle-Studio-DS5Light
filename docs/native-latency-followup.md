# Native continuity / latency follow-up (source only)

The user's exp.19 improvement was subjective and uncertain; it is not proof of the cause.

Changes:
1. Main-loop USB catch-up handles at most three 384-byte blocks. It yields to BT/USB between blocks, exits on no progress, and checks a 500 us budget after each block. This is not a hard execution-time bound: a single block can exceed it. Normal one-block operation adds no buffering.
2. Send-ready scans at most eleven pending/queued entries, discarding expired heads before attempting one actual L2CAP send in the same opportunity. It never busy-retries a real send in that loop. FIFO control order is retained.
3. Encoded speaker results use a two-entry FIFO under the existing critical section. Each result is consumed once. Overflow evicts oldest; the existing 25 ms freshness limit is retained. Empty/stale results use the existing valid Opus silence frame without waiting for core1. Generation change clears results and rejects old worker completions. This removes latest-result duplication but does NOT establish sample-exact speaker/haptic alignment: the asynchronous encoder can still lag, overflow or underrun.
4. Native mode skips inactive auto-haptic coefficient updates; inactive effect leak skips its coefficient updates. Caches refresh on the first enabled block. Native PCM scaling/resampling and speaker processing remain intact.
5. Native 0x36 frames no longer expire merely at 48 ms, in all builds. Mixed/replacement frames retain 48 ms. Policy is stamped when enqueued; the experimental CMake switch is retired. Existing queue pressure threshold 8 / total capacity 10 and oldest-audio eviction remain; failed audio retry budget remains 10 ms, control 40 ms, at most three send attempts. Stream reset/disconnect cleanup remains. These bounds prevent unbounded memory and retries, NOT a hard end-to-end latency bound during a radio stall.

Core0 RAM diagnostic g_audio_transport_stats counts successful L2CAP submissions, overflow, age expiry, retry timeout, retry-count exhaustion and other errors, plus maximum audio age at a send attempt. It is a debugger-visible symbol, not a new DS5Light command or web setting. L2CAP acceptance does not confirm physical delivery; counters wrap after uint32 limits. Stream-reset discards are not counted as transport loss.

Validation: production-path host regressions cover catch-up bounds/no-progress/timer wrap; result FIFO order/single-consumption/overflow/stale/generation/wrap; native retention, mixed expiry, same-event skip, retry bounds and enqueue-time policy; inactive DSP cache updates and reactivation. Existing storage, USB, haptics, lightbar, BOOTSEL, reliability and rumble tests passed. ARM syntax checks passed for audio.cpp, bt.cpp and main.cpp, with the existing volatile increment warning in main.cpp. No UF2 was built or flashed.

Hardware pending: continuous native speaker + footsteps/running, special attacks, repeated stop/start, headset route switch and radio congestion. Check speaker gaps and delayed haptics as well as strength. Existing exp.19 UF2 does not contain these follow-up edits.

## Stability follow-up (supersedes earlier native limits)

Native packets aged >=120 ms at send-ready now purge queued/pending audio and request the existing full stream reset. Control reports remain. The next audio service clears partial buffers/USB input, resets resampling and invalidates old speaker generations. Recovery is deferred until send-ready returns; this is not an RF latency bound. Overflow/retry loss can still occur earlier.

Native ACL-full retries: 20 ms from first failure, at most 6 total attempts. Mix/Replace retain 10 ms / 3 attempts; control retains 40 ms / 3. Other errors are dropped/counted. No fixed delay added. 120 ms is about eleven native frames, above the roughly 85 ms of eight buffered frames; 20 ms is almost two frames. These are provisional values, not measured optimal settings. Recovery can produce a gap.

Speaker result frames now carry sequence IDs. Under the existing lock, counters track published/consumed frames, last consumed ID, overflow, stale, underrun, old-generation rejection and resets. RAM diagnostics only, no UI/protocol changes.

Host tests pass: 119 ms retention/120 ms recovery and following delivery; 20 ms retry expiry and six-attempt exhaustion; 100 repeated profile/reset/disconnect cycles; 100 speaker-generation changes rejecting late worker output. ARM syntax checks pass for audio.cpp and bt.cpp. No firmware build, flashing or physical validation performed.
