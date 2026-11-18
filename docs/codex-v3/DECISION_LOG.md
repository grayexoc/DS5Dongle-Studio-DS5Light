# V3 Decision Log

| ID | Decision | Status | Notes |
|---|---|---|---|
| D-001 | DSP Only and DSP + Tiny Causal GRU modes | Approved | DSP Only must remain fully functional |
| D-002 | Tiny Causal GRU is initial AI model | Approved | TCN deferred |
| D-003 | TCN comparison deferred | Approved | Reconsider only on GRU failure or user request |
| D-004 | Offline training only; no online learning | Approved | Runtime CPU inference |
| D-005 | One shared Unified DSP & Feature Engine | Approved | Avoid duplicate filters/features |
| D-006 | One Decision Fusion | Approved | DSP and AI do not independently control output |
| D-007 | One Event-to-Haptic Mapper | Approved | Single event-to-pattern authority |
| D-008 | Adaptive I/O Supervisor | Approved | Orchestration and safe adaptation |
| D-009 | Auto channel detection default + validation + manual override | Approved | Never infer semantics from channel count alone |
| D-010 | Input and output layouts are separate contracts | Approved | Must be verified end-to-end |
| D-011 | PC semantic analysis; Studio hardware output/safety | Approved in principle | Avoid duplicate DSP; audit exact filter ownership |
| D-012 | PC Unified Profile is desired-state source of truth | Approved | Studio reports actual applied state; unrelated settings remain Studio-owned |
| D-013 | Legacy recommended presets untrusted | Approved | Reference/import only, visibly unverified |
| D-014 | Self-judged optimizer | Approved | Audio + firmware capabilities + measured response + user preference |
| D-015 | Software telemetry is not physical actuator measurement | Approved | External accelerometer preferred for development |
| D-016 | Studio firmware numeric settings included in optimization | Approved | Only supported fields, validated ranges and readback |
| D-017 | Runtime changes bounded and slower than DSP loop | Approved | Hysteresis, dwell, rate limit, rollback |
| D-018 | Astra/Sol role split | Approved | Astra design/review; Sol implementation/testing |
| D-019 | 4-channel target CH0/1 audio, CH2/3 haptic control | Candidate pending validation | Source evidence exists; end-to-end physical semantics unverified |
| D-020 | 5 ms DSP and 10 ms GRU cadence | Initial targets | Not end-to-end latency guarantees |
| D-021 | H24 initial GRU candidate, compare H16/H24/H32 | Proposed experiment | Not final until benchmark |
| D-022 | UI five areas | Proposed design | Must map against actual current UI in Phase 0 |

## Rejected or deferred
- TCN in initial V3.
- Online learning.
- Cloud inference and runtime GPU inference.
- Legacy presets as defaults/ground truth.
- Automatic firmware source modification or flashing.
- Full profile rewrites during transient gameplay.
- Claiming physical calibration from firmware counters alone.
