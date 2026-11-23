# V3 Architecture and Component Boundaries

## Canonical flow

Game/process audio
-> Audio Capture
-> Input Format + Channel Resolver
-> Unified DSP & Feature Engine
-> DSP Fast Path
-> Decision Fusion
-> Event-to-Haptic Mapper
-> Output Router
-> Studio USB audio
-> Studio hardware/output DSP
-> DualSense

Adaptive I/O Supervisor observes device, stream, firmware and output state. Auto Optimizer computes candidate settings. Apply Manager performs safe configuration changes. Unified Profile Manager stores desired DS5Light state.

## Component contracts

| Component | Owns | Must not own |
|---|---|---|
| Audio Capture | Windows/process capture, timestamps, format | Event semantics |
| Channel Resolver | input format/layout validation, confidence, manual override | Studio output layout |
| Unified DSP & Feature Engine | causal filter bank, envelopes, energy, spectral features when needed | Physical output routing |
| Decision Fusion | final scores/protection decision | filter implementation or pattern synthesis |
| Event-to-Haptic Mapper | event pattern, left/right output frames | device discovery |
| Adaptive I/O Supervisor | state observation, reconfiguration orchestration | direct DSP parameter math |
| Auto Optimizer | candidate PC and Studio values | applying settings itself |
| Apply Manager | validation, apply, readback, rollback | deciding perceptual objective |
| Unified Profile | desired DS5Light audio/haptic settings | unrelated controller configuration |
| Studio firmware | hardware conditioning, carrier/output, safety, telemetry | game semantic classification |

## Ownership invariants
- One logical owner per parameter.
- One shared feature computation path.
- One final event decision.
- One pattern generator.
- Input channel layout and output channel layout are separate.
- PC desired state and Studio applied state are distinct.
- Hardware safety limits are firmware-owned.
- Studio DSP remains active only for functions intentionally assigned to hardware. Avoid double gate/envelope/LP/background suppression.

## Four-channel routing hypothesis requiring proof

Source inspection found a 4-channel descriptor mask value 0x0033 and a selectable Studio Auto-Haptics DSP source. The PC output path appears to duplicate the first stereo pair into the second pair in at least one path. Target design is CH0/1 original L/R audio and CH2/3 dedicated L/R haptic-control signals. Treat this as a hypothesis until validated end-to-end:
1. descriptor and channel cluster;
2. WASAPI stream format and channel mask;
3. PC interleaved buffer order;
4. Studio source selection and DSP input;
5. Native Haptics mixing;
6. physical left/right response.

## Data flow and timing
- DSP target block: 5 ms, subject to actual capture cadence.
- Audio thread never blocks for configuration.
- Structural reconfiguration occurs only on stable device/format events.

## Offline Fusion and Mapper

For model-independent Phase 4 replay, the existing DSP supplies protected transient and onset detail amplitudes. Fusion accepts detail only when protection is present and reserves the protected amplitude before allocating remaining headroom. The offline mapper interpolates from its previous level to the current target over the block, emits centered L/R in the absence of verified direction, and writes candidate HapticFrameV1 records to a separate artifact. The existing WAV and live device routes retain their own output behavior. Each replay starts at zero.

## Optimization loops
- Fast: per-block DSP and output envelope.
- Medium: stable event/audio statistics and limited runtime correction.
- Slow: device/session/profile changes, capability discovery and full optimization.
No structural remapping or full profile rewrite on transient audio events.
