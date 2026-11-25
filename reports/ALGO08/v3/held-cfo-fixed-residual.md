# Fixed-state residual audit of two held half-blends

The authenticated publications cannot establish whether the signed CFO edits reduced RF error with the ordinary model held fixed. They identify every edit and owner, and preserve one all-owner RMS per arm. They omit the signed per-observation residuals or exact fixed predictions needed to calculate the effect. The aggregate bounds include both improvement and deterioration in all four arms. [Frozen protocol](held-cfo-fixed-residual-protocol.md) · [Numerical evidence](measurements/held-cfo-fixed-residual.json)

## What the saved evidence supports

An observation ID hashes the UTF-8 text `session_id:receiver_id:valid_start_counter`. The native winner is the peak with the largest passed fractional margin, with lower candidate rank breaking ties. Each sealed edit matches the only candidate at its original lane and counter, and changes only `fractional_tracking_cfo_hz`. All 11,588 other opportunities on DS30-0019 and all 13,027 on DS30-0274 match exactly, including empty lanes. The original owners include 2,552 and 3,713 unedited controls respectively in each calibration arm. At frozen state, the control residual shift is exactly zero because the measured CFO, alias lifts and prediction are unchanged. [Identity and edit readback](held_cfo_fixed_residual.py) · [Original edit splice](held_shrink_0019.py)

The installed `history_position.make_problem` sets the conditional residual to the lifted measured CFO minus the calibrated prediction. `event_position.attach_event_predictive` uses the same sign for the raw predictive residual, before the predictive likelihood profiles its track offset. `presentation.localization_v3.prepare_packet` passes these values to `residual_hz` and records `prediction_hz = measured_cfo_hz − residual_hz`. With both the Graph and likelihood alias lifts fixed, a native CFO difference `d` changes the signed residual from `r` to `r + d`. The sum-of-squares change is `2⟨r,d⟩ + ‖d‖²`. [Conditional likelihood](../../../src/leo/analysis/localization_v3/history_position.py) · [Predictive likelihood](../../../src/leo/analysis/localization_v3/event_position.py) · [Publication rows](../../../src/leo/presentation/localization_v3.py)

The `exact_named_raw` witness drops the numeric fields when it retains the ordered `(observation_id, NORAD, role)` triples. The fit witness persists the endpoint, receiver coefficients and family phases, but only hashes the track arrays, design arrays, causal ephemerides and orbital-mode geometry. The standard publication writes aggregate arm summaries, plots, optimizer path and a numerical position grid. Its residual plots are raster renderings of the fitted-`c` arm. None of those artifacts supplies exact signed residual values for either calibration arm. The cleaned owner registries and CFO edits identify the subset, but provide no signed inner product. [Witness filtering](exact_named_raw.py) · [Fit fingerprint](named_survivor_fit.py) · [Residual renderer](direct_residual_figures.py)

| Recording | Calibration | Original owners / edited-owned | Original all-owner RMS (Hz) | Possible fixed-state RMS (Hz) | Possible fixed-state ΔSSE (million Hz²) |
|---|---|---:|---:|---:|---:|
| DS30-0019 | `c = 0` | 2,842 / 290 | 196.480 | 169.880 to 223.079 | −27.695 to +31.717 |
| DS30-0019 | Fitted `c` | 2,842 / 290 | 184.347 | 157.748 to 210.947 | −25.861 to +29.882 |
| DS30-0274 | `c = 0` | 4,139 / 426 | 163.385 | 140.838 to 185.932 | −28.391 to +32.599 |
| DS30-0274 | Fitted `c` | 4,139 / 426 | 152.646 | 130.099 to 175.194 | −26.387 to +30.595 |

These outer intervals use `‖r‖ = RMS × √N`, the exact edit-vector norm on the original owners and Cauchy–Schwarz. The edited-owned subset contains 263 conditional and 27 predictive observations on DS30-0019, and 378 conditional and 48 predictive observations on DS30-0274. Exact residual matches total zero for both subsets. The subset RMS before and after the edit, its ΔSSE and the exact all-owner fixed-state effect all remain unknown.

## What changed after rebuilding and fitting

| Recording | Common / added / dropped owners | Edited common / added / dropped | Common role changes | Graph tracks |
|---|---:|---:|---:|---:|
| DS30-0019 | 2,519 / 155 / 323 | 252 / 22 / 38 | 10 | 117 → 120 |
| DS30-0274 | 4,095 / 137 / 44 | 423 / 17 / 3 | 79 | 168 → 166 |

Both calibration arms have the same incidence changes within each recording. Every shared ID retained its NORAD. The rebuilt endpoints and receiver coefficients changed in all four comparisons. The fitted coefficient moved from −416.4 to −486.6 Hz/GHz on DS30-0019 and −275.0 to −238.1 Hz/GHz on DS30-0274. The available rows cannot apportion the aggregate change among common, added, dropped or unedited owners. The table below uses the published refitted states and their own owner sets. [0019 saved comparison](held-shrink-0019-ram.md) · [0274 saved comparison](held-shrink-0274.md)

| Recording | Calibration | Conditional RF RMS before → after (Hz) | All-owner RF RMS before → after (Hz) |
|---|---|---:|---:|
| DS30-0019 | `c = 0` | 174.592 → 171.841 | 196.480 → 196.559 |
| DS30-0019 | Fitted `c` | 174.734 → 171.906 | 184.347 → 182.942 |
| DS30-0274 | `c = 0` | 130.288 → 127.131 | 163.385 → 164.158 |
| DS30-0274 | Fitted `c` | 130.241 → 127.082 | 152.646 → 153.197 |

Three focused tests passed. This audit used metadata and arithmetic on CPU 3 with zero solver, Graph, waveform, TLE, survey or 0218 reads. [Tests](../../../tests/pipeline_eval/test_held_cfo_fixed_residual.py)
