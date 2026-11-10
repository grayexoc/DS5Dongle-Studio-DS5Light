# Mix peak limiter

The derived generator's tanh remains unchanged. Mix now adds derived audio haptics and converted rumble before limiting. Below 90% of the helper's available amplitude range, the sum passes unchanged. Above that knee, a continuous rational curve approaches the ceiling. With no native component, 0.7 remains 0.7, 1.0 becomes 0.95, and 2.0 becomes approximately 0.9917.

This replaces the always-active derived/(1+abs(derived)) compression. The existing later native-priority headroom clamp and final sample clamp remain unchanged. Replace and native-only paths are unchanged. No buffer, lookahead, profile field, or DS5Light change is added.

The 90% knee is an initial engineering choice, not a physically calibrated value. Existing Mix profiles can feel stronger. This does not eliminate the later native-priority clipping when native haptics consume the available range.

Validation: production helper host regressions cover linear range, sum/cancellation, symmetry, monotonicity, ceiling, native headroom, and existing motor/stream transitions. Nine firmware regression scripts and the exp.29 ARM build pass; artifact and source hashes are recorded in build/xinput-exp29/validation.json. No device output or perceptual comparison performed.
