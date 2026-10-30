# Fresh ALGO02 baseline failure audit

Read-only inspection on 2026-10-30 of the frozen 400-fast-acquisition comparison.
No inference was rerun, no baseline or scientific source changed, and no member
was removed. Paths below are relative to this study directory. Numerical source
references identify the retained `runtime-baseline-production` snapshot.
`baseline-final-inventory.json` preserves all 400 receipt hashes and final counts;
this audit explains its nine failed baselines, including the two propagation
assertions grouped there as `other`.

## Findings

| DS26 case | Actual retained failure | Evidence |
| --- | --- | --- |
| 0132 | Orbit interpolation rejected the negative phase derivative sample | `cases/DS26-0132/algo02/algo02.log`: `prepare_phase_geometry`, line 27, calls `phase_shifted_states(phases - derivative_step_s)` and raises `orbit phase interpolation never extrapolates` |
| 0156, 0181, 0281 | Orbit interpolation rejected the central phase sample | Each `cases/DS26-CASE/algo02/algo02.log`: `prepare_phase_geometry`, line 25, calls `phase_shifted_states(phases)` with the same exception |
| 0285 | Previous causal TLE propagation failed during family-weighting confidence | `cases/DS26-0285/algo02/algo02.log`: `infer_algo02` → `confidence_for` → `phase_widths` → `previous_bank`, `assert good.all()` |
| 0289 | Previous causal TLE propagation failed during fresh-discovery orbit-mode construction | `cases/DS26-0289/algo02/algo02.log`: `fresh_discovery` → `standard_problem` → `build_modes` → `previous_bank`, `assert good.all()` |
| 0191, 0199 | Family-excluded calibration phase failed its convergence gate | Each `cases/DS26-CASE/algo02/family.log` and `inference/family_cavity/SCAN_nominations.json`: `family-excluded calibration phase did not converge` |
| 0273 | Whole baseline budget exhausted during the ALGO02 stage | `cases/DS26-0273/algo02/terminal.json`: `TimeoutExpired`, remaining child timeout 1009.9781488031149 s, whole elapsed 1200.0142245949246 s; baseline receipt elapsed 1200.5132461078465 s |

The earlier grouping of 0285/0289 with phase interpolation failures was incorrect.
Their retained exceptions concern previous-TLE propagation instead. DS26-0273
has now published its timeout receipt and is no longer pending.

## Phase padding versus allowed phase

`tools/evaluate_ds23_phase_refreshed.py:78` builds the bank using
`arange(-17, ceil(duration) + 18)`. Retained bank and track artifacts give:

| Case | Bank support, seconds | Observation support, seconds | Full-track phase interval with ±0.05 s derivative margin |
| --- | --- | --- | --- |
| DS26-0132 | [-17, 317] | [0.0100000, 299.9648356] | [-16.9600000, 16.9851644] |
| DS26-0156 | [-17, 317] | [0.0542493, 299.8023363] | [-17.0042493, 17.1476637] |
| DS26-0181 | [-17, 318] | [0.2755879, 300.0365369] | [-17.2255879, 17.9134631] |
| DS26-0281 | [-17, 318] | [0.0100000, 300.0228142] | [-16.9600000, 17.9271858] |

These intervals are calculated directly from preserved `bank.npz:time_s` and
`tracks.json`, without propagating or fitting anything. They comfortably contain
the declared ±15 s expansion domain and its derivative samples. Padding is
therefore sufficient for that domain; simply declaring an insufficient ±15 s
bank margin would misidentify the failure.

The code exposes an inconsistent transition between posterior phases and
bounded numerical expansion references. `tools/dsx01_joint_marginal.py:176`
returns Gaussian posterior phases without clipping. At the end of
`tools/run_dsx01_clean_region.py:fresh_discovery`, candidate seeds retain that
`problem.state` output. `tools/evaluate_ds23_phase_refreshed.py:321` passes the
best seed directly to `explore`. In contrast, the ordinary geographic exploration
in `tools/run_dsx01_clean_region.py` passes `reference_state(...)`, which clips
expansion phases to ±15 s. `tools/iterate_dsx01_profiled_identity.py:117` replaces
only nominated satellite phases; other inherited posterior phases remain.
Thus the refreshed proposal route can request geometry outside the bank despite
bounded newly nominated phases. The retained tracebacks establish the actual
out-of-domain requests; the exact failing satellite and phase values were not
persisted, so their values cannot be recovered from these logs alone.

For 0285/0289, `tools/prototype_s01_causal_shape.py:63` propagates previous causal
TLEs at 0/150/300 s and requires every object to be usable. `ecef_states` returns
`PropagationResult.usable`, meaning zero SGP4 errors at every knot. The assertion
therefore establishes at least one propagation error. The logs do not retain
the offending NORAD or error code. This is separate from interpolation padding.

For 0191/0199, `tools/probe_ds23_family_cavity_nominations.py:47` permits five
fixed-position phase refreshes, clipping phase values to ±15 s, and requires the
last maximum phase change to be at most 0.01 s. The gate fails, so nominations
are saved with `status=failed` and no cavity position is produced. The outer
worker's missing `family_cavity/position/SCAN.json` error is a downstream symptom.
The family subprocess exits zero after recording the failed nomination; the
outer worker correctly publishes no qualified position.

## Why ALGO03 cannot recover these cases in this comparison

This ALGO03 release is recovery conditioned on a completed, validated ALGO02
baseline, its paired c arms, incumbent support and calibration. It is not an
independent replacement for initial baseline fitting. The complete v2 contract
requires the embedded v1 terminal to be complete
(`src/leo/contracts/fast_graph_position_v2.py:70`); the production worker rejects
an unqualified baseline before recovery. The frozen evaluation runner preserves
these acquisitions and records candidate `unavailable`, reason `baseline_failed`
(`tools/run_algo03_dataset_evaluation.py:257`). No valid fallback position exists
when ALGO02 itself has no qualified position. Intermediate numerical results
cannot be substituted for a qualified baseline or used to shrink the denominator.

Any correction to these baseline paths requires a separately versioned and
reviewed comparison. None was made during this audit.
