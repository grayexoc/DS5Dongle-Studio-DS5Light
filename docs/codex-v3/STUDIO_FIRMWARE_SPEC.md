# Studio Firmware Integration Specification

## Principle
Studio firmware is not merely a passive output device. Existing firmware already contains audio/haptics DSP and output logic. V3 must reuse and clarify ownership rather than duplicate or rewrite it.

## Existing source to audit
- `src/audio.cpp`
- `src/audio.h`
- `src/usb_descriptors.cpp`
- `src/tusb_config.h`
- `src/cmd.cpp`
- `src/config.cpp`
- `src/output_diagnostics.h`
- `src/haptic_math.h`
- existing protocol docs under `docs/`

## Responsibility split
PC:
- game/process audio semantic analysis;
- background/music estimation and suppression;
- transient/event classification;
- optional GRU;
- event priority and left/right haptic-control generation.

Studio:
- hardware-facing filter/conditioning intentionally retained;
- carrier generation;
- output amplitude and safety limits;
- left/right actuator routing;
- Native Haptics coexistence;
- anti-aliasing/output handling;
- firmware telemetry and actual applied settings.

Do not run duplicate background gate, envelope, LP, or smoothing stages unintentionally. For each parameter, declare the owning stage and whether another stage is fixed, bypassed, or intentionally complementary.

## Candidate settings to optimize
Only if actually exposed and supported by firmware:
- low-pass cutoff;
- crossover;
- low/high gain;
- filter slope;
- smoothing/envelope;
- gate;
- carrier;
- global haptic gain;
- Native Haptics mix/level;
- other exposed audio-haptics values discovered in Phase 0.

Exact config keys, units, ranges, persistence and side effects must be read from current firmware source and protocol. Do not infer names/ranges from UI labels.

## Capability and apply model
Query capabilities and active settings before optimization. Report supported fields and min/max/step where feasible. PC optimizer proposes candidate values; Apply Manager validates against firmware limits. Read back actual values after apply. Keep desired state separate from applied state. Partial apply must be reported and recovered. Never raise hardware safety limits automatically.

## Four-channel routing
Current source inspection indicates a four-channel descriptor with channel mask 0x0033 and an Auto Haptics source selector. The PC output path has a stereo-to-second-pair duplication behavior in at least one implementation path. Proposed target: CH0/1 preserve speaker L/R, CH2/3 carry dedicated L/R haptic-control signals. This is not approved as physically proven until end-to-end verification of descriptor, host channel order, buffer construction, firmware source, mixing, and physical actuator response.

## Native Haptics and other controller features
Preserve Native Haptics, Effect Leak, rumble, triggers, gyro, macro, USB/Bluetooth operation and unrelated controller settings. The PC Unified Profile must not take ownership of unrelated Studio settings.

## Firmware change policy
Prefer extending existing settings/diagnostic protocol. Add a new capability command only if current metadata is insufficient. Do not rewrite the firmware or flash devices during documentation/audit. User approval is mandatory before USB channel semantic changes, output behavior changes or firmware flashing.
