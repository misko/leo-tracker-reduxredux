# Replacing causal orbit states in the full southern saved solve

The simulator's later orbital elements improved the southern fitted position by about 700 m on each of two offers. The solver still published a fix when the receiver was 100 m outside the search square. Both experiments use the same public waveform. The later data were supplied only to this research diagnostic. [Predeclared protocol](oracle-orbit-solve-protocol.md)

| Offer | State source | Zero-calibration error | Fitted error | Fitted RF RMS | Fitted position inside face |
|---|---|---:|---:|---:|---:|
| 100 m inside | Capture-era | 817 m | 1,101 m | 6.392 Hz | 383 m |
| 100 m inside | Generator | 565 m | 399 m | 6.322 Hz | 499 m |
| 100 m outside | Capture-era | 817 m | 1,102 m | 6.392 Hz | 183 m |
| 100 m outside | Generator | 566 m | 397 m | 6.322 Hz | 297 m |

The receiver was at (−32.951113°, 21.468646°). On the containing offer the generator-state solve returned (−32.951033°, 21.464373°) with fitted calibration. Both calibration arms retained the same satellite assignments and 266 associated observations. Both generator-state solutions landed inside the omitted square, so the stock guard's condition for performing its exterior check was false. [Full-roster results, coordinates and intermediate fits](measurements/oracle-south-full-v2.json.gz)

The capture-era catalogue had 10,937 satellite IDs. Three were absent from the generator catalogue, including one of the 1,618 IDs in the regional bank. Repeating both offers with only the intersection, for both orbit choices, reproduced the corresponding endpoints and decisions. All four prespecified generator-state solves were used on this southern east–west comparison. In the earlier rotated causal comparison, the fitted endpoints were (−32.952014°, 21.463822°) inside and (−32.950212°, 21.463462°) on the omitted offer. The rotated generator-state comparison remains unmeasured. [Matched intersection results](measurements/oracle-south-intersection.json.gz) · [Rotated causal study](north-south-faces.md)

The runner overlays the orbit states in memory, preserves the causal candidate and prior policy, checks catalogue IDs, and opens the public answer for scoring after the solves. Run `oracle_orbit_solve_trial run BENCH NEW_OUTPUT original full` and repeat with `intersection` in a separate directory. The `score BENCH OUTPUT OUTPUT/scored.json` action binds the two offers to the published reference. Use the module under `reports.ALGO08.single-core-2x` and the shared low-priority Gauss slot. [Implementation](oracle_orbit_solve_trial.py) · [Tests](../../../tests/pipeline_eval/test_oracle_orbit_solve_trial.py)
