# Codex Project Rules — DS5Light Unified Haptics V3

These instructions apply to work in this repository.

## Authority and reading order
1. Read `docs/codex-v3/V3_MASTER_SPEC_V2.1.md` before any V3 work.
2. Read the relevant subsystem specification before changing that subsystem.
3. Read `DECISION_LOG.md` before proposing an architectural change.
4. Update `PHASE_STATUS.md` and the decision log when approved project state changes.

## Non-negotiable rules
- Preserve existing behavior unless a V3 requirement explicitly replaces it and the user approves the change.
- Do not modify source code, firmware, build configuration, dependencies, or existing presets during Phase 0 audit.
- Do not flash hardware or change device settings without explicit user approval.
- Never assume a channel count proves channel meaning. Verify metadata, descriptor semantics, runtime stream layout, and physical routing.
- Never assume Studio telemetry proves physical actuator vibration. Distinguish commanded, received, processed, and physically measured output.
- Do not apply legacy recommended presets as defaults or optimization ground truth. Legacy values are unverified references only.
- Initial AI model is Tiny Causal GRU. TCN is deferred unless GRU fails acceptance gates or the user requests it.
- No online learning. Training is offline only.
- Keep DSP Only fully functional without AI.
- Audio callback / real-time thread must never wait for AI, disk, UI, network, or firmware configuration operations.
- Preserve causal processing and avoid added lookahead. Proposed 5 ms DSP blocks and 10 ms AI cadence are targets to verify, not proven end-to-end latency.
- Keep one shared feature extraction path. Do not duplicate filters or spectral analysis for DSP and AI.
- Keep one Decision Fusion and one Event-to-Haptic mapping authority.
- PC Unified Profile is the desired-state source of truth for DS5Light audio/haptics settings. Studio retains ownership of unrelated controller settings and reports applied state.
- Apply settings with validation, readback where supported, partial-failure handling, and rollback/recovery.
- Low confidence means no structural remapping or unsafe setting change. Preserve the last verified configuration or fall back safely.
- Use existing modules and protocols before creating new ones. Avoid parallel implementations.
- Do not claim a test, build, hardware check, or physical measurement succeeded unless it was actually executed and its result recorded.

## Required workflow
Default collaboration: Sol investigates/implements/tests -> Astra reviews complex decisions and risks -> Sol revises.
- Astra 6.2: architecture, difficult DSP/GRU/fusion decisions, firmware/protocol risk review, safety, acceptance criteria, and final review.
- Sol 6.2: repository inventory, implementation, scripts, tests, builds, training pipeline, documentation, diagnostics, and routine iteration.
The 15–20% Astra / 80–85% Sol split is a planning heuristic, not a quota. Model selection is performed by the user; Codex must not claim it can switch models itself.

## Phase gates
- Phase 0 is read-only repository and hardware-path audit. No source edits.
- Do not start a later phase until the prior phase deliverables and user approval gate are satisfied.
- Any change to USB channel semantics, Studio firmware output, Native Haptics mixing, Bluetooth, controller safety limits, or firmware flashing requires explicit user approval.

## Documentation discipline
- Record verified repository facts separately from hypotheses and hardware assumptions.
- Include branch, commit, file paths, tests executed, and unverified items in audit reports.
- Update the relevant specification and decision log before implementing an approved architectural change.

## Continuation and reporting
- When the user says to continue, carry out the next in-scope steps consecutively while their prerequisites are met. A completed subtask or focused test is not a reason to stop for another confirmation.
- Skip routine intermediate reports when the user requests quiet execution. Surface only a blocker requiring user action, an explicitly required approval, or the final milestone result.
- During implementation, run only checks needed for the change at hand. Record deferrable tests in the phase status and run them together at final integration. Keep the existing explicit hardware and phase approval gates.
- Before ending a continuation task, recheck the requested milestone, the worktree and the deferred-test list. Continue through independent remaining work. If the milestone cannot advance, report the concrete blocker and what remains.
