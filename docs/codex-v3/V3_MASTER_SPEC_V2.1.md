# DS5Light Unified Haptics V3 — Master Development Specification V2.1

- Status: authoritative planning baseline; implementation not yet approved
- Repository: `grayexoc/DS5Dongle-Studio-DS5Light`
- Baseline branch: `custom/studio-ds5light`
- Baseline commit inspected: `052d39611e39f11bc1eb0aa0fc49fe4b4e3a6277`
- Documentation handoff branch: `docs/codex-v3-handoff`
- Scope: PC application, Studio firmware integration, DualSense haptic output, Codex workflow
- This document records design decisions; it does not claim hardware validation.

## 1. Product goal

Evolve DS5Light into a low-latency, resource-conscious, adaptive haptics system that preserves important game effects while suppressing unwanted background/music-driven vibration. The system should express:
- Impact: weight and impulse (shots, collisions, explosions)
- Texture: metallic contact, scraping, material feel
- Transient: short, sharp effects (sword clashes, ricochets, reloads)
- Motion: directional pass-by, projectile movement, left/right sweeps

The goal is perceptual quality, not maximum vibration amplitude.

## 2. Approved decisions

1. Use DSP for audio haptics. Pitch Matching, generic metal detection, and the Tiny Causal GRU prototype were retired.
2–4. Retired AI decisions.
5. Reuse the Unified DSP & Feature Engine. Do not compute the same filter bank, energy, or spectral features twice.
6. One Decision Fusion module combines deterministic DSP evidence.
7. One Event-to-Haptic Mapper creates event patterns and output frames.
8. Adaptive I/O Supervisor is a formal V3 component for input/output observation, confidence evaluation, safe reconfiguration, and recovery.
9. Automatic channel recognition is the default, but metadata and runtime signal validation are required. Manual override is supported.
10. Input capture layout and Studio output layout are separate contracts. Never infer one from the other.
11. PC DSP owns semantic analysis, background estimation/suppression, event detection, and haptic-control signal generation.
12. Studio owns hardware-facing filtering that is still required, carrier/signal generation, output limiting, actuator routing, Native Haptics coexistence, and hardware safety. Remove or bypass duplicate processing only after measured A/B validation.
13. PC Unified Profile is the desired-state source of truth for DS5Light audio/haptics settings. Studio reports capabilities and actual applied state. Unrelated controller settings remain owned by existing Studio settings/profile mechanisms.
14. Existing recommended presets (including Audio Haptic 01/02) are untrusted. They may be retained as clearly marked, unverified import/reference data, but never as defaults, ground truth, or optimizer targets.
15. Auto optimization must calculate values from verified game audio characteristics, actual firmware capabilities/settings, measured actuator response where available, and explicit user preferences.
16. Distinguish software telemetry from physical actuator measurement. External accelerometer measurement is the preferred development calibration method. Internal IMU use remains exploratory until its sampling rate, bandwidth, and vibration contamination are validated.
17. All setting changes require confidence checks, bounds, hysteresis/dwell time, rate limits, apply/readback verification where supported, partial-failure handling, and rollback/recovery.
18. Low confidence must not trigger structural channel remapping or risky Studio changes.
19. Initial UI uses a simple default layer and a separate advanced/diagnostic layer.
20. Model allocation: Astra 6.2 owns complex design/review/acceptance; Sol 6.2 owns most implementation/testing/build/documentation. Default loop is Sol investigate/implement -> Astra review/decide -> Sol revise.

## 3. System architecture

### 3.1 Main path
Game/process audio capture
-> Input format and channel validation
-> Unified DSP & Feature Engine
-> DSP Fast Path
-> Decision Fusion
-> Event-to-Haptic Mapper
-> output layout/router
-> Studio USB audio path
-> Studio hardware DSP/output stage
-> DualSense actuators

Adaptive I/O Supervisor observes the path and requests controlled reconfiguration. It must not own every algorithm or bypass subsystem ownership.

### 3.2 Component ownership
- Audio Capture: Windows capture and frame timing.
- Channel Resolver: input layout negotiation, validation, confidence, manual override.
- Unified DSP & Feature Engine: causal filter bank, envelopes, energy, event evidence, and shared replay features.
- Decision Fusion: final event scores/protection decisions.
- Event-to-Haptic Mapper: event pattern and left/right output frame generation.
- Adaptive I/O Supervisor: device/stream/firmware state monitoring and reconfiguration orchestration.
- Auto Optimizer: computes candidate PC and Studio settings; does not directly mutate hardware.
- Apply Manager: validates, applies, reads back, records, and rolls back settings.
- Studio Firmware: hardware capability reporting, accepted setting ranges, output processing, safety, telemetry.
- Unified Profile Manager: desired-state profile and revision tracking.

### 3.3 Avoid over-fragmentation
These are logical responsibilities, not a requirement to create one source file per name. Reuse current modules and only split code where a stable interface or independent test boundary is needed.

## 4. PC DSP

### DSP
- Preserve the existing causal real-time path where possible.
- Current repository inspection found a 48 kHz / 240-sample processing path in `core.py`, with existing band/envelope/background/transient logic. Verify exact current behavior before changing it.
- Existing crossover candidates 120 / 600 / 2500 Hz are implementation facts to audit, not final V3 design constraints.
- Low-frequency subdivision (e.g. 0–60, 60–120 Hz) is a candidate experiment, not a predetermined final filter design.
- No lookahead. No blocking calls on the audio thread.
- Shared features should reuse DSP state. FFT/spectral analysis is computed only when needed and at a justified cadence.

## 5. Adaptive I/O and automatic optimization

### Input
- Prefer existing Windows metadata, WASAPI negotiation, process loopback where supported, and current channel policy code.
- Verify endpoint identity, sample rate, channel count, channel mask/layout, process identity, and actual captured frame layout.
- Use signal analysis as corroboration, not as the sole source of speaker/channel semantics.
- Automatic mode is default; offer Auto + Verify and Manual Mapping.
- On ambiguous mapping, retain last verified mapping or use an explicitly safe fallback; do not guess.
- Re-check on device/session/process/format changes rather than polling heavily.

### Output
- Query actual Studio firmware capabilities and current values.
- Track commanded, transmitted, received, processed, and read-back states separately.
- Output telemetry does not prove physical vibration.
- Use external accelerometer measurements for development calibration when available.
- Internal controller IMU is exploratory only until bandwidth/sample rate are validated.

### Optimization
Two separate operations:
1. Static Auto Optimization on game/device/profile changes: calculate candidate PC DSP and Studio settings together.
2. Adaptive Runtime Control during gameplay: small, bounded changes to permitted runtime parameters only.

The optimizer uses verified audio statistics, firmware capabilities and ranges, calibration measurements (or explicitly labeled estimates), and user preferences. It must not treat untrusted legacy presets as ground truth.

Studio settings candidates include low-pass cutoff, crossover, low/high gain, filter slope, smoothing/envelope, gate, carrier, global haptic gain, and Native Haptics mix/levels where the firmware exposes them. Exact field names, ranges, persistence behavior, and ownership must be confirmed from source and firmware before implementation.

### Safe adaptation policy
- Separate fast DSP loop (target 5 ms), medium statistical loop, and slow device/profile reconfiguration loop.
- No structural channel remapping during transient gameplay changes.
- Use confidence thresholds, hysteresis, minimum dwell time, parameter rate limits, and stable-state checks.
- Apply only changed fields.
- Read back actual values where supported.
- Detect partial apply; restore prior values or enter documented safe state.
- Never raise hardware safety limits automatically.
- If telemetry is unavailable or contradictory, do not claim success.

## 6. PC/Studio responsibility and four-channel routing

Repository inspection indicates a four-channel USB audio configuration and a descriptor channel mask value reported as 0x0033, plus a firmware-selectable Auto Haptics DSP source. The source code also contains a path that duplicates the first stereo pair into the second pair. These facts do not by themselves prove end-to-end physical routing on all devices.

V3 target to investigate:
- CH0/CH1: preserve original left/right speaker audio.
- CH2/CH3: dedicated left/right haptic-control signal candidate.

This target must be proven through descriptor interpretation, host stream format, PC output buffer construction, firmware source selection/mixing, controller routing, and physical A/B measurement. Do not implement based solely on channel labels.

PC owns semantic classification and haptic-control signal generation. Studio owns necessary hardware-facing signal conditioning, carrier/output generation, limiting, and safe actuator routing. Avoid duplicate background gates, duplicate envelopes, or duplicate low-pass processing unless deliberately designed and measured.

## 7. Studio firmware integration

- Reuse existing USB audio, settings protocol, diagnostics, profile/readback, filters, carrier and output code where possible.
- Do not rewrite firmware wholesale.
- Add capability reporting only where existing metadata is insufficient.
- Keep Native Haptics, Effect Leak, trigger, gyro, macro, Bluetooth/USB controller functions intact.
- Host-managed behavior must be explicit and reversible.
- PC profile applies only DS5Light-owned audio/haptic fields; Studio continues to own unrelated controller settings.
- Hardware safety limits remain firmware-owned and cannot be raised by optimizer.

## 8. UI information architecture

Five main areas:
1. Home / Auto Optimize: game, input, Studio connection, optimization status, overall intensity.
2. Haptics: impact, background suppression, metallic/sword effects, projectile/pass-by, directionality.
3. Audio & Devices: input device, channel mode/status, verification, channel test, Studio output route, reconnect.
4. Advanced: DSP bands, envelope/gate, firmware-exposed advanced parameters.
5. Diagnostics & Calibration: input meters, event probabilities, output telemetry, latency breakdown, calibration status and guided test.

Default view is simple. Advanced parameters are hidden until requested. Do not expose duplicate PC/Studio controls for the same logical function. Legacy preset recommendations are removed from the default choice UI; any importer must mark imported values unverified.

## 9. Performance and quality gates

- 48 kHz input and 5 ms DSP block are starting assumptions to verify.
- No added lookahead; no audio-thread waiting.
- Measure full path latency separately: capture, DSP, feature extraction, fusion, output write/queue, USB/firmware processing, and physical onset where instrumentation exists.
- Measure p50/p95/p99, CPU, memory, queue depth, drops, underruns, and audio glitches.
- Compare the existing baseline and V3 DSP on identical WAVs and real-game captures.
- Initial candidate quality targets (e.g. +5 percentage points recall or 20% fewer false positives at similar recall) are goals to validate, not guaranteed results.
- Subjective blind A/B testing and physical measurement are required before claiming perceptual improvement.

## 10. Phase plan and approvals

### Phase 0 — Read-only repository audit
Sol: inspect branch/commit/status, source tree, app UI, capture path, channel layout, PC output path, Studio firmware, settings/readback, tests/builds; document exact files and unknowns.
Astra: review architecture, identify conflicts/risks, approve contracts to draft.
No source modifications. No firmware flash.

### Phase 1 — Contracts and architecture freeze
Astra: decide input/output layout contract, profile ownership, feature/AI/result/output schemas, firmware capability/apply/readback semantics, and safety rules.
Sol: map contracts to existing code, draft schemas/protocol docs, test serialization/compatibility without changing production behavior.
User approval required before implementation.

### Phase 2 — Adaptive I/O + Unified DSP/Feature
Astra: review channel confidence policy, DSP ownership, filter design, latency budget and fallback.
Sol: extend existing capture/channel modules and DSP; add feature extraction, deterministic tests, WAV analysis and benchmarks.
Acceptance: DSP Only works, no duplicate analysis, low-confidence changes are blocked, baseline path remains stable.

### Phase 3 — Retired AI prototype

### Phase 4 — Decision Fusion + Event-to-Haptic
Astra: approve event priority, protection invariants, direction confidence and overlap/limiter policy.
Sol: implement fusion, pattern mapper, stereo routing, deterministic replay tests.
Acceptance: transient protection remains safe; event patterns do not clip or mask each other.

### Phase 5 — Studio firmware integration
Astra: review USB/firmware semantics, output ownership, Native Haptics coexistence, safety and protocol changes.
Sol: reuse/extend firmware and host settings/diagnostics, implement capability query and safe apply/readback/rollback.
Explicit user approval before firmware flashing or changes to USB channel semantics.
Acceptance: correct end-to-end routing, settings readback, existing controller functions preserved.

### Phase 6 — Auto Optimizer + UI
Astra: approve objective/constraints, confidence and change policy, user-facing explanations.
Sol: implement desired/applied profiles, optimizer, apply manager, five-area UI, manual overrides and diagnostics.
Acceptance: no untrusted preset defaults; all auto changes explainable, bounded, reversible.

### Phase 7 — Hardware validation and release
Astra: final quality/risk review and release approval.
Sol: real-device tests, accelerometer calibration where available, A/B, latency/resource reports, recovery package and release docs.
Acceptance: physical and subjective tests support quality claims; DSP Only fallback works; no regressions in Native Haptics/controller behavior.

## 11. Model allocation

- Astra 6.2: high-complexity architecture, DSP/fusion decisions, protocol and firmware risk, safety, acceptance criteria, final review.
- Sol 6.2: implementation, tests, builds, training pipeline, ONNX/runtime experiments, diagnostics, UI, docs, routine iteration.
- Default loop: Sol investigates/implements -> Astra reviews/decides -> Sol revises.
- 15–20% Astra and 80–85% Sol is a workload heuristic.
- User selects the model in the product; Codex cannot guarantee or enforce model switching.

## 12. Explicit non-goals and deferred work

- TCN implementation/comparison in initial V3.
- Online learning.
- Cloud or real-time GPU inference.
- Firmware source self-modification or automatic firmware flashing.
- Unverified legacy presets as defaults.
- Continuous full-profile rewriting during gameplay.
- Claims of physical actuator calibration from firmware telemetry alone.

## 13. First execution instruction

Start with Phase 0 only. Produce a read-only audit report with branch, commit, file map, exact audio data path, actual channel semantics, current UI navigation/settings map, PC/Studio DSP overlap, protocol and diagnostics reuse, test/build status, and hardware unknowns. Do not modify source or firmware. Submit findings for Astra review and user approval before Phase 1.
