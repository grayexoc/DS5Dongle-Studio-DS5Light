# exp.13 haptic delivery changes

- Automatic haptics takes motor ownership only while USB playback frames arrive (60 ms grace, independent of microphone activity). Existing synth cadence restores classic rumble after a stream stops, normally within about 60-110 ms. Silent PCM remains an active stream.
- Mix preserves configured native contribution without the former shared soft compression. Derived audio retains soft compression; derived and converted rumble together are limited to remaining symmetric headroom. Native filters and user gains are unchanged; Replace is unchanged while streaming.
- LED/volume-only host reports preserve held motor intent without renewing the DualSense 300 ms motor timeout. XInput continues holding until STOP/replacement.
- Queued state-bearing packets refresh only motor values/flags immediately before transmission and recompute CRC. Successful L2CAP send acknowledges the motor state; failed/dropped sends remain eligible for retry at the existing synth cadence. Latest state wins, so intermediate transitions under congestion can coalesce. This does not rewrite already encoded PCM or guarantee radio delivery.
- Added host regressions for stream timeout/wrap/disconnect, native unity/headroom, left/right, STOP preservation, unrelated field isolation, ownership hand-back and DS-only watchdog. Existing BOOTSEL, LED, lightbar, rumble-shape and upstream-reliability suites passed. ARM build succeeded.
- Build retained four existing volatile-deprecation warnings. No flashing, tactile A/B, radio congestion stress or long-session hardware validation was performed.

Artifact: build/xinput/studio-xinput-exp.13.uf2
SHA256: 616A2D3ECBF63D6437D84BEA67D63017B04BB99BCAA96E5BF3C45C4F289C5DA1
