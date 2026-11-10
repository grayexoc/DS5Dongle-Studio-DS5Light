# Historical regression baselines

These three source snapshots are required by the signal-equivalence tests; they are not app runtime files or release-package contents.

- `causal-envelope/core.py`: original `reports/causal-envelope-quality/before/core.py`, used by `test_causal_envelope.py` to check detector equivalence while testing causal smoothing.
- `oled-signal/channel_mix.py`, `oled-signal/output_gain.py`: original `reports/oled-integration-20261027/before/` snapshots, used by `test_oled_integration.py` for exact PCM/transition comparisons.

The files were copied unchanged from the local development reports. Keeping only these required snapshots makes the tests independent of unpublished reports and their working directory. They retain the application's source license.
