# Codex Kickoff — Phase 0 Only

You are working on DS5Light Unified Haptics V3.

## Before doing anything
1. Read repository-root `AGENTS.md`.
2. Read `docs/codex-v3/V3_MASTER_SPEC_V2.1.md`.
3. Read all relevant subsystem specifications.
4. Read `DECISION_LOG.md` and `PHASE_STATUS.md`.

## First task
Perform Phase 0 Repository Audit only. This is read-only.

Inspect:
- current branch, HEAD, worktree status and uncommitted user changes;
- source tree and current UI entry points/navigation;
- PC capture and Process Loopback implementation;
- input format negotiation and channel policy;
- PC output buffer and channel order;
- USB audio descriptors and Studio source selection;
- firmware audio DSP, Native Haptics, Effect Leak and output diagnostics;
- PC/Studio settings protocol, profile ownership and readback;
- existing tests, build instructions and actual test/build status.

Trace one sample path from game process capture to physical DualSense output. Separate facts visible in source from facts requiring runtime/hardware verification.

## Deliverables
Create a read-only audit report (new documentation file only if requested/approved) containing:
- branch and commit;
- exact source paths and call graph;
- current UI map;
- input/output channel contract and evidence;
- PC vs Studio DSP ownership table;
- reusable code map;
- settings and diagnostics protocol map;
- tests/builds actually run and results;
- latency measurement gaps;
- hardware unknowns and risk register;
- recommended Phase 1 contract decisions.

## Do not
- edit source or firmware;
- change dependencies or build configuration;
- run formatters over source;
- change presets or device settings;
- train models;
- build/flash firmware;
- change USB channel semantics;
- commit or push implementation work.

Stop after reporting the audit and wait for user approval before Phase 1.
