# Unified DSP and Tiny Causal GRU Specification

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
- FeatureFrame generation for GRU.

Feature extraction must reuse existing DSP states. Do not calculate a duplicate filter bank or duplicate RMS path for AI.

Potential frequency split changes such as 0–60 / 60–120 Hz are experiments. Existing 120 / 600 / 2500 Hz boundaries are current implementation facts to audit, not immutable V3 choices.

## DSP invariants
- Preserve causal behavior.
- No lookahead.
- No blocking on AI, UI, disk, network, or firmware settings.
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

Freeze names, units, normalization, order, timestamp semantics and schema version before training. Feature schema and model metadata must match exactly.

## GRU
- Initial model: one-layer unidirectional causal GRU.
- Compare H16/H24/H32; H24 initial candidate.
- Multi-label event outputs and confidence.
- Train offline only.
- No online adaptation or cloud service.
- Runtime CPU only; FP32 first, INT8 only after measured comparison.
- ONNX Runtime is a candidate, not a requirement if measured overhead is poor.
- TCN deferred.

## Worker and state
- Consume FeatureFrames in sequence.
- Bounded queue.
- Do not drop arbitrary frames and continue the same hidden state.
- On overflow, discontinuity, schema mismatch or stale sequence: reset hidden state and mark AI invalid.
- DSP Only remains active during AI warm-up or failure.
- Discard stale outputs.
- Audio thread never waits for GRU.
- Measure inference p50/p95/p99, CPU, memory, queue delay and impact on audio thread.

## Evaluation
Compare identical source material:
A. existing baseline;
B. V3 DSP Only;
C. V3 DSP + GRU.

Use music-only, music+shots, repeated shots, explosion, footsteps, reload, sword/metal, ricochet, projectile/pass-by, engine, vehicle and stereo-direction cases.

GRU is accepted only if it improves recall at similar false-positive rate or reduces false positives at similar recall, while preserving latency/resource/stability and real-device subjective quality. Otherwise ship DSP Only as default and revisit only with user approval.
