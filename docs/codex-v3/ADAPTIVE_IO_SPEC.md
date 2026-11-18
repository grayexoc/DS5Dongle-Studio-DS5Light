# Adaptive I/O Supervisor Specification

## Purpose
Observe and safely coordinate input/output changes across Windows audio, game process capture, Studio firmware and DualSense routing. It is an orchestrator, not a replacement for Channel Resolver, Auto Optimizer, Apply Manager or DSP.

## Existing code to inspect/reuse
- `DS5Light/windows_audio.py`
- `DS5Light/process_audio.py`
- `DS5Light/native/ProcessCapture.cs`
- `DS5Light/channel_policy.py`
- `DS5Light/channel_mix.py`
- `DS5Light/device_binding.py`
- `DS5Light/device_diagnostics.py`
- `DS5Light/reconnect_policy.py`
- `DS5Light/stream_health.py`
- `DS5Light/studio_settings_protocol.py`

Exact APIs and current call graph must be confirmed in Phase 0.

## Input resolution sequence
1. Identify process/session and selected endpoint.
2. Query endpoint format, sample rate, channel count and channel mask/layout where available.
3. Negotiate a supported capture format using existing policy.
4. Verify actual frame shape and channel order delivered by capture implementation.
5. Analyze per-channel energy, correlation, silence, clipping and duplication as corroborating evidence.
6. Compare with last verified mapping.
7. Assign separate confidence dimensions: metadata confidence, layout confidence, signal confidence, process identity confidence.
8. Apply automatic mapping only when the evidence meets the approved policy.
9. If ambiguous, retain last verified mapping or request manual selection; never guess semantic channel roles from energy alone.

## Process loopback
Reuse existing Process Loopback implementation where supported. Confirm Windows version support, process tree behavior, channel mask, capture format, and whether the captured layout is preserved. Do not assume process loopback automatically gives original game-engine channel semantics.

## Output supervision
Query Studio capability and current settings. Track distinct states:
- desired by PC;
- command sent;
- acknowledged/received;
- processed/applied;
- read back;
- physically measured (only if external sensor measurement exists).

Firmware telemetry alone cannot prove physical actuator motion.

## Trigger events
Re-evaluate on endpoint/default-device change, process/session start/stop, stream format change, Studio connect/disconnect, firmware capability change, profile switch, and explicit user action. Prefer event-driven notifications over high-frequency polling. Re-query final device state after notifications because event ordering can vary.

## Safe reconfiguration
- Use stable-state checks and debounce.
- No channel remapping on a transient sound.
- Use hysteresis, minimum dwell time and change-rate limits.
- Apply only changed fields.
- Verify supported readback.
- On partial failure, restore previous values where possible and report any field that could not be restored.
- Keep last verified configuration.
- If confidence is low, do not change structural mapping.
- Do not automatically raise firmware safety limits.
- No firmware flashing or source-code self-modification.

## Calibration
Software calibration: verify stream format, channel levels, firmware values and telemetry.
Physical calibration: use an external accelerometer during development to measure actuator response by side/frequency/amplitude. Record sensor, mounting, sampling rate, measurement bandwidth and uncertainty.
Internal controller IMU is exploratory until its bandwidth and sample rate can measure the haptic frequency range reliably.

## Performance
Do not poll or query firmware on the real-time audio thread. Use a background worker with bounded frequency and cancellation. Device reconfiguration must not block audio callback; use a safe transition/mute/fallback policy.
