# DS5Light V3 UI Specification

## Design objective
Replace the split PC suppression / Studio audio-haptics mental model with one user-facing haptic system. The UI should expose user outcomes first and technical controls only in Advanced. Never create two controls for the same logical parameter.

## Proposed navigation

### 1. Home / Auto Optimize
Show:
- selected game/process and capture source;
- input device and channel validation state;
- Studio connection and firmware capability state;
- DSP Only / DSP + GRU mode;
- optimization state: Not analyzed / Analyzing / Ready / Applied / Partial / Failed;
- overall haptic intensity;
- last profile revision and whether desired/applied states match.

Primary action: Analyze & Optimize. Show a concise explanation of the changes proposed before apply when changes are material.

### 2. Haptics
User-oriented controls:
- Impact / weight
- Background vibration suppression
- Metallic / sword / sharp transient detail
- Projectile / pass-by / motion detail
- Directionality
- Overall intensity

Controls must map to a documented parameter group. Do not expose raw duplicate PC and Studio controls here.

### 3. Audio & Devices
- Automatic detection (default)
- Auto + Verify
- Manual channel mapping
- process capture selection where supported
- input channel meters and layout label
- channel test with safe, low-level test signal
- Studio output layout and route status
- device reconnect and last verified mapping

Clearly distinguish detected metadata from verified runtime mapping. Never call a channel “left haptic” merely because it is channel index 2 without evidence.

### 4. Advanced
Grouped sections:
- PC DSP: crossover/bands, envelope, background estimator, transient protection.
- AI: enable GRU, model/schema version, worker status, inference latency, stale/discontinuity counters. Hide model internals by default.
- Studio hardware: only settings exposed by firmware capability discovery, including LP/crossover/gain/slope/smoothing/gate/carrier/native mix when supported.
- Routing: read-only by default; edits require confirmation and validation.
- Profile: desired vs applied values and revision history.

### 5. Diagnostics & Calibration
- capture format and process identity
- per-channel meters
- DSP block duration and processing percentiles
- Feature/GRU timing and queue health
- event probabilities and Fusion decision
- USB/firmware received/processed/readback counters
- output limiter and underrun telemetry
- calibration status: estimated vs physically measured
- guided external accelerometer workflow for development

## First-run workflow
1. Detect audio endpoint and Studio device.
2. Read format, channel layout and firmware capabilities.
3. Validate signal/channel mapping.
4. If confidence is low, ask user to test or choose manual mapping.
5. Run safe software diagnostics.
6. If physical calibration is absent, label response as estimated.
7. Calculate candidate profile.
8. Show a change summary and apply only after user consent for first-time or structural changes.
9. Read back and verify.
10. Save desired/applied revisions.

## Runtime states
- Connected / disconnected
- Capturing / idle / capture degraded
- Layout detected / verified / ambiguous / manual
- Firmware compatible / limited / unknown
- Profile synchronized / pending / partial / failed
- AI ready / disabled / stale / error (DSP Only continues)

## UI rules
- Keep simple controls on Home/Haptics.
- Advanced values are capability-driven.
- Show why an automatic change occurred.
- Provide revert to last verified profile.
- No automatic legacy preset recommendation.
- Imported legacy values are visibly marked Unverified.
- Never show a green success state until readback confirms supported applied fields.
