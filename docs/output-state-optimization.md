# Output-state composition optimization (source only)

Implemented in the recommended order:
1. state_refresh_rumble copies only the four motor fields from live state and applies the same audio-haptics stream ownership rule as full composition. state_set uses this shared rule; state_report_sent compares those fields without composing LEDs, battery notifications or lightbar policy.
2. BT audio state refresh calls the same narrow path. Existing non-motor queued control fields remain untouched; queued 0x31 control transitions are not rewritten. Live values are still read at send time, rather than reusing an enqueue-time snapshot.
3. The periodic main-loop path computes the original synth/battery force condition, then state_prepare_report composes one candidate for both pending comparisons and immediate enqueue. Player-mode transition tracking is skipped on forced output, retaining the original short-circuit behavior. No global snapshot cache or time-to-live introduced. The host USB report path retains its existing independent full pending check.

Validation: all seven regression scripts passed, including ARM syntax checks on connected sources. Narrow-field equivalence across Native/Mix/Replace and active/inactive stream was checked; unrelated bytes/bits remain intact. Existing LED debounce/blink/hand-back and submission acknowledgment tests passed. Frozen-time sequential comparison of legacy and new periodic paths checked 1200 combinations of mode, brightness, fixed/off RGB, stream state, battery and intermittent acknowledgments; output-needed decisions and output bytes matched. This shared-state mock comparison does not replace independent on-device timing or radio tests. Composition-call reduction was asserted via battery override invocation counts.

No UF2 built or flashed. Existing exp.20 UF2 predates these edits and earlier post-build optimizations. Actual CPU-time savings and hardware output timing remain unmeasured.
