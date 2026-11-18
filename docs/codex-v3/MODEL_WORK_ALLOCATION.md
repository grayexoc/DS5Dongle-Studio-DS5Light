# Model Work Allocation — Astra 6.2 / Sol 6.2

## Roles
### Astra 6.2 — design authority and reviewer
- system architecture and boundaries;
- difficult DSP filter/event/protection decisions;
- GRU architecture, labels and acceptance gates;
- Decision Fusion and output safety;
- USB/firmware protocol and routing risk;
- optimizer objective, bounds and confidence policy;
- phase reviews and final acceptance.

### Sol 6.2 — implementation and verification
- repository audit and source inventory;
- coding and refactoring after approval;
- tests, scripts, WAV tools and benchmarks;
- offline dataset/training pipeline and ONNX experiments;
- UI and diagnostics;
- firmware implementation/builds after approval;
- documentation and routine fixes;
- performance measurement and reports.

## Default collaboration loop
1. Sol investigates and prepares evidence.
2. Astra reviews the evidence and decides complex technical questions.
3. Sol implements the approved decision.
4. Sol tests and reports.
5. Astra reviews the result and acceptance evidence.
6. Sol makes corrections.

## Workload guideline
Astra approximately 15–20% of effort; Sol approximately 80–85%. This is a planning heuristic, not a quota or promise of model capability.

## Phase allocation
| Phase | Astra | Sol |
|---|---|---|
| 0 Audit | review architecture, risk and unknowns | inspect files, tests, paths, runtime |
| 1 Contracts | decide schemas, ownership, safety | map to current code, draft/validate contracts |
| 2 I/O + DSP | approve channel confidence and DSP design | implement existing-module extensions, tests |
| 3 GRU | approve labels/model/evaluation gates | offline data, training, export, runtime benchmarks |
| 4 Fusion/Mapper | approve event priority and protection | implement and replay-test |
| 5 Studio | review protocol, routing, firmware safety | implement approved extensions and tests |
| 6 Optimizer/UI | approve objective, bounds, UX policy | implement optimizer, profile/apply, UI |
| 7 Validation | final quality and risk approval | measure, A/B, calibration, release docs |

## Important limitation
The user selects Astra or Sol in the ChatGPT/Codex product. Repository instructions cannot force a specific model. If only one model is available, follow the same role split as task categories and request human review for high-risk decisions.
