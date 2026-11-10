# Post-exp.20 source optimization (not built)

1. Replaced native_audio_waiting queue rotation/copies with a core0-owned count of queued native frames. Enqueue, removal into pending, overflow eviction, stream discard and disconnect maintain the count. Pending ownership is checked separately. Control-only queues and normal idle still preserve recovery epoch semantics.
2. Cached the bitmask of macro records that bind mute. Reload and successful record edits invalidate the cache. Enable/disable masks are applied on each query, so changing profiles/settings takes effect immediately without another table scan. No output-state composition changes.
4. ARM syntax tests now discover compile_commands.json belonging to this checkout under its own build directory. They no longer depend on source/firmware-standard-xpack. Shared SDK/compiler/Python paths remain necessary. If no configured build exists, tests fail with configuration guidance rather than using an older checkout.

Validation: all seven regression scripts and ARM macro.cpp syntax passed. Native queue-count consistency exercised over 500 enqueue/send/discard transitions. Existing stale-head/retry/overflow/recovery checks remain. Current exp.20 UF2 predates these source edits; no new UF2 built. Physical timing savings are unmeasured.
