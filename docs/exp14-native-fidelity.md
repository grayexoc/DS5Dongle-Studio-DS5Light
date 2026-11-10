# exp.14

Native restore (byte0 selector 01, improved rumble clear) discards residual motor bytes before caching, preventing the nonzero-motor workaround from selecting rumble again. Unrelated LED reports continue retaining prior motor intent; all-zero/no-authority reports remain ambiguous and are not treated as native restore.

Native PCM bypasses Studio additional smoothing both with automatic haptics disabled and in Mix. Mix native level and global haptics gain still apply; remaining headroom carries generated signals. mix_native_filter is retained in the wire/storage layout but is now ignored. haptics_aa affects generated signals only. Existing app labels may therefore describe the old behavior. Resampling remains 48kHz to 3kHz, with 8-bit BT samples.

On FIFO pressure only the oldest queued 0x36 audio packet is removed. Other queued reports retain order. A pending retry packet is not evicted, and 48ms audio expiry remains. This is selective eviction in the existing fixed queue, not a port of Bridge separate scheduling. It cannot guarantee lossless audio or remove head-of-line blocking.

Host tests passed: native restore with residual motor values; existing haptic delivery, rumble shaping, LED, BOOTSEL, upstream reliability; queue full with audio, control ordering and control-only full queue. Physical tactile equivalence and wireless stress are unverified.
