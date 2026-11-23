# V3 Decision Log

| ID | Decision | Status | Notes |
|---|---|---|---|
| D-001 | Audio haptics processing | Current | DSP only |
| D-002 | Tiny Causal GRU prototype | Retired | Removed on 2026-11-23 |
| D-003 | TCN comparison | Closed | AI experiment retired |
| D-004 | Offline training and runtime inference | Retired | Removed on 2026-11-23 |
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
| D-020 | 5 ms DSP cadence | Initial target | Measure end-to-end latency separately |
| D-021 | H16/H24/H32 model comparison | Closed | AI experiment retired |
| D-022 | UI five areas | Proposed design | Must map against actual current UI in Phase 0 |

## Rejected or deferred
- TCN in initial V3.
- Online learning.
- Cloud inference and runtime GPU inference.
- Legacy presets as defaults/ground truth.
- Automatic firmware source modification or flashing.
- Full profile rewrites during transient gameplay.
- Claiming physical calibration from firmware counters alone.

## Phase 1 drafting

- 2026-11-20: Phase 0 review completed and user authorized Phase 1 contract drafting. The [draft](PHASE_1_CONTRACTS.md) proposes preserving existing Native Mix and evaluating a separate rear-DSP route. Contract approval and implementation approval are pending.
- 2026-11-20: Phase 1 host interchange schema and compatibility checks completed. Final model tuning and hardware activation remain gated by their phase-specific evidence. Contract freeze approval is pending.
- 2026-11-20: User approved contract freeze and Phase 2. The first change preserves the existing output path and exposes shared band features in offline replay. GRU, dedicated rear DSP activation and firmware changes remain outside this increment.
- 2026-11-20: Phase 2 host checks and Astra review completed. Per user direction, real-game capture comparison, live endpoint transition and physical latency remain deferred. Phase 3 is awaiting approval.

## Offline work while training is pending

- User requested that HT-GRU-Lab-Lite artifacts remain usable later and that independent work continue. Phase 3 model training and runtime integration remain pending. The model-independent portion of Phase 4 may run in offline replay only. Retain the existing DSP protection authority, require protection evidence before assigning onset detail, and use centered output until directional evidence is available.

## Phase 5 Studio integration

- User approved USB semantics and firmware output work. Astra confirmed that the existing Replace/rear DSP pair implements the necessary rear input. Start with explicit host PCM construction and firmware packet observability. The current comparison evidence does not justify bypassing filters or changing existing Native Mix. Device installation remains a separate approval.
- Added a host-tested rear-control authorization prototype under tests. The prototype starts from a discarded closed USB generation and rejects changes to revision, Bluetooth link or USB generation before permitting output. The bounded TLA+ model remains the design reference. The sequential prototype is covered by the existing C++ host regression runner. Production integration is gated on confirming how exclusive acquisition relates to SET_INTERFACE and covering asynchronous HID and audio sequencing.

## Phase 6 read-only preview

- The conditional write increment uses a firmware-side revision and checksum comparison and updates only the candidate route fields in RAM. A one-use firmware record allows restoring the previous route only while the applied token is current. On a lost acknowledgement or inconsistent readback, refresh before any further write. Live installation and application require separate approval.

- User authorized starting Phase 6 with a DSP Only candidate preview. The first candidate is based on the verified Studio route contract and explicit user output intent. It presents observed and proposed values with a reason, does not guess a gain or change channel mapping, preserves active Native Mix, and does not issue writes.
- Device identity, endpoint, firmware capability, and stable profile revision are prerequisites for a live Studio route candidate. Missing evidence produces a reason to abstain. Application of a candidate and numerical optimization are separate design steps.
- User authorized conditional intensity write implementation and simulation. The intensity operation uses a separate versioned command and firmware-owned restore record. It accepts only a decrease on the idle verified route and never writes flash. The PC requires the measured PC controls to match the current controls before sending it.

## Phase 6 capture and settings UI

- The approved simplified page keeps capture scope, the relevant source selector, output selection, and transport controls. Advanced holds existing PC DSP, channel controls, presets, profile controls, and the explicit Studio exclusive output selector.
- The device-wide mode follows the opened endpoint format. Manual process capture settings retain their stored value when switching scopes. Diagnostics distinguish the requested and opened formats, unsupported-format negotiation, and the conservative device-wide stereo fallback.
- Selecting Studio live exclusive output authorizes the session's conditional route adjustment through the existing command 0x25. The ordinary output route retains existing behavior. The worker requires a verified endpoint and device revision, respects native-only and Native Mix profiles, and attempts conditional restoration after the renderer closes. An unknown acknowledgement or unverified restoration is shown to the user. The intensity setting remains under the existing user and optimizer policies.

- The user revised the layout to a single main audio-haptics page. The process table remains in place, with the original whole-device and Native Haptics overlays. The channel row exposes one dropdown. Explicit 5.1 and 7.1 use center, surrounds and LFE with hard clipping. The PC filter exposes bypass, background reduction and impact preservation. Enabling the filter activates the associated DSP stages.

- The user moved device selection back to Settings & Diagnostics and placed PC gain beneath the channel row. A fresh Studio Replace/Rear profile now selects exclusive rear control at startup. The worker rechecks that output route before a temporary write. If the device, capability, or exclusive acquisition cannot be verified, startup fails with a status message. A profile change that requires a different output path stops the current capture and requires a fresh start.

- The user chose a low-band policy for DSP Only to reduce background audio leakage. The filtered PC output uses the two bands below the existing 600 Hz crossover. Rear control requires meaningful low-band energy. Full-band features remain available for evaluation and a future model can use high-band event evidence under a separate acceptance policy.
- The user deferred actual-game feel and trained GRU validation and continued the remaining work. Enable the host-tested direction and attack mapping on the existing managed Studio route. Use direction only for captured stereo, retain centered control for other input layouts, and retain the current routing, lease, and PCM bounds.

### 2026-11-21 — Publish current development source

At user direction, package the current V3 development work as DS5Light v1.1.0 with Studio v49 for Pico 2 W, and publish a regular release. Skip inspection and test runs for this release. Keep prior pending validation recorded and describe the implemented DSP features without claiming physical or game validation. Document updated haptic presets and touchpad mouse controls in the bilingual release materials.

### 2026-11-22 — v1.1.1 / Studio v50 release

Publish the current app and firmware together as DS5Light v1.1.1 / Studio v50. Keep the single custom/studio-ds5light branch. Describe the implemented changes without claiming measured latency or physical haptics results. No tests or hardware operations are added to this release action.

### 2026-11-22 — v1.2.0 / Studio v51 release

The user authorized release of the current source with app and firmware versions aligned to DS5Light 1.2.0 and Studio 51. Bilingual release materials state that recommended presets in Studio profile-slot settings provide the comparison reference, perceived response depends on Windows and game/application volume, and other settings use defaults unless specified. This release action continues the user's instruction to omit inspection and test execution. Previous validation records retain their original scope.

### 2026-11-23 — Studio speaker accents

Expose the existing Front transient path as an opt-in speaker setting. Gate it on mode auto-mute and normal speaker permission, suspend it on the headset route, and flush only speaker state on audio policy changes. Keep valid saved tuning intact and use the shorter gate defaults for uninitialized values.

### 2026-11-23 retirement of experimental haptics

The user retired Pitch Matching, generic metal-impact detection, and the Tiny Causal GRU prototype. Remove their runtime hooks, model assets, offline training tools, and generated experiment files. Retain the released v51 fixed 90/180 Hz Front impact texture, stereo steering, and DSP-only audio paths.

### Shared output gain and DSP state

Shared PCM carries speaker audio and can also feed the Front haptics generator. The app applies boost on shared output only when the active Studio mode reports auto-mute. The existing profile event signals changes to either auto-mute field, and the profile reply carries both values in an optional trailing byte. Older replies leave shared gain at unity. Managed Rear keeps applying gain to Rear PCM.

Native Mix leakage filtering uses a fixed 120 Hz pole. The audio-haptics cutoff applies only to the generated path. Retain the legacy speaker accent fields for slot and HID compatibility while removing the retired rendering branch.

### 2026-11-23 — v1.2.1 / Studio v52 release preparation

The user requested checking all current local changes, consolidating recommended-preset instructions from prior releases, refreshing README, and publishing after release checks. Version identifiers advance to DS5Light 1.2.1 / Studio 52. Include follow-up impacts, rear continuity, shared output gain, startup/reconnect recovery, current AA behavior, and removal of retired experiments. Run application regression, bilingual UI checks, affected firmware host tests, and package/UF2 checks. Keep physical Edge, tactile, real-game and end-to-end latency claims within existing evidence.

### 2026-11-23 — v1.2.1 / Studio v52 release checks

Completed the requested current-source release preparation and bilingual preset/README consolidation. Full app discovery ran 886 tests (878 passed, one obsolete help-text assertion failed, seven English-only checks skipped). After correcting that test assertion, all 19 tests in the four affected modules passed. The isolated UI runner passed 69 Korean and 15 English tests. All four selected firmware host runners and their ARM syntax checks passed. The Pico 2 W v52 UF2 and v1.2.1 app ZIP built; packaged Korean/English smoke checks, ZIP CRC, 82 embedded-source comparisons, 143 native-binary inventory hashes and preset/guide comparisons passed. See docs/release-v1.2.1-validation.md for exact evidence and limits. Physical hardware acceptance remains unchanged; no firmware flashing or game/tactile testing was performed.