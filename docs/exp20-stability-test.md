# exp.20 stability trial

Fixes review findings 1-3. Native recovery now tracks progress from the first outstanding native frame, refreshed by successful native L2CAP submission. Oldest-frame eviction cannot reset this epoch; a fresh idle-to-active transition does. 120 ms without progress triggers stream cleanup at send-ready. Physical delivery is not confirmed by L2CAP submission.

Microphone packets carry core0 generation through core1 decode. The decoder resets when its input generation changes; USB playback rejects obsolete generation results, including decode completed after close/reopen. Inactive mic input is rejected.

Speaker IDs are assigned before PCM queue admission and retained through Opus publication. PCM creation/drop counters and encoder/resampler failure counters supplement output queue diagnostics. IDs now expose front-end drops instead of only numbering successful output. Counters are RAM diagnostics, with single writers for PCM and encode failure fields.

Clean-directory build exposed an earlier erroneous CMake deletion during trial-option retirement. Restored WDL/Opus targets, RAM relocation, signed-char/memory-override options, flash divider selection and XInput source/definition. Full compilation and linking succeeded after restoration. Existing Opus conversion and volatile warnings remain.

Host regressions: continuous 220 ms stall with FIFO eviction now recovers; normal idle does not; stale microphone generation is rejected; PCM overflow preserves original IDs and counts losses. All seven regression scripts passed. Hardware behavior remains untested, no flashing performed.

Version: studio-xinput-exp.20-stability-test
UF2: build/xinput-exp20-stability-test/studio-xinput-exp.20-stability-test.uf2
SHA256: d301eefdcdff1c3db1de00853b4e28cb6a7b65d832077da5c4b9c1732132d1fc
