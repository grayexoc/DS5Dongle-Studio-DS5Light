# Unified DSP Specification

## Unified DSP & Feature Engine
Extend the current DSP rather than rewrite it. Initial source to audit: `DS5Light/core.py`, `DS5Light/offline.py`, `DS5Light/audio.py`.

Responsibilities:
- causal multiband filtering;
- band energy and log-energy;
- fast/slow envelope and ratio;
- transient/onset evidence;
- sustainedness/background statistics;
- stereo energy balance/correlation;
- optional spectral features only where justified;
- FeatureFrame generation for replay diagnostics.

Feature extraction must reuse existing DSP states. Do not calculate a duplicate filter bank or duplicate RMS path for replay diagnostics.

### Phase 2 offline replay

Run `python offline.py input.wav output.wav --features-jsonl features.jsonl` from `DS5Light/`. The WAV path preserves the existing replay routing. The optional JSONL uses `FeatureFrameV1` with schema ID `ds5light.band-evidence.raw.v1`. The 16 values are grouped by instantaneous mean-square, fast envelope, slow envelope, and onset score, in that order. Within each group the bands are below 120 Hz, 120–600 Hz, 600–2500 Hz and above 2500 Hz, using the existing complementary filter differences. Energy values are in squared normalized PCM units. Onset scores are dimensionless, from 0 to 1.

Each record uses the index of the last processed sample on the 48 kHz replay output clock. Sequence starts at zero per run; generation and inference epoch are 1 and profile revision is 0 for a standalone replay. Capture rates other than 48 kHz may produce variable block lengths. These raw block records are evidence for evaluation.


Potential frequency split changes such as 0–60 / 60–120 Hz are experiments. Existing 120 / 600 / 2500 Hz boundaries are current implementation facts to audit, not immutable V3 choices.

### Studio DSP Only live mapping

The managed Studio rear-control route uses the same low-band hit evidence for attack shaping and optional steering as the offline rehearsal. Attack shape follows the dominant protected band below the 600 Hz crossover. Steering requires a two-channel capture and a clear left/right energy rise. Other input layouts use equal rear targets. Layout changes clear the direction envelope, and the existing output ramp smooths target changes. This DSP behavior does not classify game events from their meaning. Stereo diagnostic WAV conversion uses the same mapper.

## DSP invariants
- Preserve causal behavior.
- No lookahead.
- No blocking on UI, disk, network, or firmware settings.
- Avoid abrupt gain changes; use bounded smoothing.
- Separate transient protection from sustained/background evidence.
- Protect small effects and repeated impacts from background-estimator contamination.
- Verify stereo/shared-control decisions against real output semantics.

## Feature schema
The previously proposed 16-feature vector is a starting candidate only. Candidate feature families:
- four band log energies;
- band fast/slow ratios;
- spectral flux/centroid/high-frequency content/flatness if measured value justifies cost;
- crest/transient measures;
- stereo balance/correlation;
- low-band sustainedness.

Freeze names, units, normalization, order, timestamp semantics and schema version before changing the feature schema.

## Evaluation
Compare identical source material:
A. existing baseline;
B. V3 DSP.

Use music-only, music+shots, repeated shots, explosion, footsteps, reload, sword/metal, ricochet, projectile/pass-by, engine, vehicle and stereo-direction cases.
